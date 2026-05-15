from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import importlib

import pytest
from bson import ObjectId
from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]


class FakeInsertResult:
    def __init__(self, inserted_id: ObjectId):
        self.inserted_id = inserted_id


class FakeUpdateResult:
    def __init__(self, matched_count: int, modified_count: int):
        self.matched_count = matched_count
        self.modified_count = modified_count


class FakeCursor:
    def __init__(self, docs: list[dict]):
        self.docs = docs
        self._index = 0

    def sort(self, fields):
        """Sort cursor; accept both single tuple and list of tuples."""
        if isinstance(fields, list):
            for field, direction in reversed(fields):
                reverse = direction == -1
                self.docs.sort(key=lambda item: item.get(field), reverse=reverse)
        return self

    def __iter__(self):
        return iter(self.docs)

    def __aiter__(self):
        """Support async iteration for async controllers."""
        self._index = 0
        return self

    async def __anext__(self):
        if self._index < len(self.docs):
            result = self.docs[self._index]
            self._index += 1
            return result
        raise StopAsyncIteration


class FakeCollection:
    def __init__(self, seed_docs: list[dict] | None = None):
        self.docs = [doc.copy() for doc in (seed_docs or [])]

    @staticmethod
    def _matches(doc: dict, query: dict) -> bool:
        if not query:
            return True
        for key, value in query.items():
            if key == "$or":
                if not any(FakeCollection._matches(doc, clause) for clause in value):
                    return False
                continue
            if key == "$nin":
                doc_value = doc.get(key.replace("$", ""))
                if doc_value in value:
                    return False
                continue
            if key == "status" and isinstance(value, dict) and "$nin" in value:
                if doc.get("status") in value["$nin"]:
                    return False
                continue
            if isinstance(value, dict):
                if "$nin" in value and doc.get(key) in value["$nin"]:
                    return False
                continue
            if doc.get(key) != value:
                return False
        return True

    def find_one(self, query: dict):
        for doc in self.docs:
            if self._matches(doc, query):
                return doc
        return None

    def find(self, query: dict):
        matched = [doc for doc in self.docs if self._matches(doc, query)]
        return FakeCursor(matched)

    def insert_one(self, doc: dict):
        stored = doc.copy()
        stored.setdefault("_id", ObjectId())
        self.docs.append(stored)
        return FakeInsertResult(stored["_id"])

    def update_one(self, query: dict, update: dict):
        for doc in self.docs:
            if self._matches(doc, query):
                for key, value in update.get("$set", {}).items():
                    doc[key] = value
                return FakeUpdateResult(1, 1)
        return FakeUpdateResult(0, 0)


class FakeDatabase:
    def __init__(self, appointments_seed=None, users_seed=None, lawyers_seed=None):
        self.collections = {
            "appointments": FakeCollection(appointments_seed),
            "users": FakeCollection(users_seed),
            "lawyers": FakeCollection(lawyers_seed),
        }

    def __getitem__(self, name: str):
        return self.collections[name]


@pytest.fixture()
def main_module(monkeypatch):
    monkeypatch.chdir(ROOT)
    
    # Mock MongoDB connection before importing anything that uses it
    config_db = importlib.import_module("config.cognilex_db")
    monkeypatch.setattr(config_db, "connect_to_mongodb", lambda: None)
    monkeypatch.setattr(config_db, "close_mongodb_connection", lambda: None)
    
    main = importlib.import_module("main")
    monkeypatch.setattr(main, "connect_to_mongodb", lambda: None)
    monkeypatch.setattr(main, "close_mongodb_connection", lambda: None)
    return main


@pytest.fixture()
def client(main_module, monkeypatch):
    from config.cognilex_db import get_database
    
    # Override the get_database dependency for all tests
    def fake_get_db():
        return FakeDatabase()
    
    main_module.app.dependency_overrides[get_database] = fake_get_db
    
    with TestClient(main_module.app) as test_client:
        yield test_client
    
    # Clean up dependency overrides
    main_module.app.dependency_overrides.clear()


def make_appointment(
    *,
    lawyer_id: ObjectId | str | None = None,
    client_id: ObjectId | str | None = None,
    date: str = "2026-05-20",
    time: str = "10:00",
    appointment_type: str = "Consultation",
    status: str = "pending_payment",
    paid: bool = False,
):
    if lawyer_id is None:
        lawyer_id = ObjectId()
    if client_id is None:
        client_id = ObjectId()
    if isinstance(lawyer_id, str):
        lawyer_id = ObjectId(lawyer_id)
    if isinstance(client_id, str):
        client_id = ObjectId(client_id)

    return {
        "_id": ObjectId(),
        "lawyer_id": lawyer_id,
        "client_id": client_id,
        "date": date,
        "time": time,
        "type": appointment_type,
        "status": status,
        "paid": paid,
        "notes": None,
        "createdAt": datetime(2026, 5, 1, 9, 0, tzinfo=timezone.utc),
        "updatedAt": datetime(2026, 5, 1, 9, 0, tzinfo=timezone.utc),
    }


def make_user(*, email: str, _id: ObjectId | None = None):
    return {
        "_id": _id or ObjectId(),
        "email": email,
        "name": "Test User",
    }


def make_lawyer(*, _id: ObjectId | None = None, fullName: str = "Test Lawyer"):
    return {
        "_id": _id or ObjectId(),
        "fullName": fullName,
        "profilePhotoUrl": "https://example.com/lawyer.jpg",
    }


@pytest.fixture()
def client_with_db(main_module, monkeypatch, request):
    """Client with dynamic fake DB management per test."""
    from config.cognilex_db import get_database
    
    current_db = {"db": FakeDatabase()}
    
    def get_fake_db():
        return current_db["db"]
    
    main_module.app.dependency_overrides[get_database] = get_fake_db
    
    test_client = TestClient(main_module.app)
    test_client.set_db = lambda db: current_db.update({"db": db})
    test_client.get_db = lambda: current_db["db"]
    
    yield test_client
    
    # Clean up
    main_module.app.dependency_overrides.clear()
    test_client.close()


def test_create_appointment_success(client_with_db):
    fake_db = FakeDatabase()
    client_with_db.set_db(fake_db)

    lawyer_id = str(ObjectId())
    client_id = str(ObjectId())

    response = client_with_db.post(
        "/api/appointments/create",
        json={
            "lawyer_id": lawyer_id,
            "client_id": client_id,
            "date": "2026-05-20",
            "time": "10:00",
            "appointment_type": "Consultation",
            "notes": "Initial consultation",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["message"] == "Appointment initiated. Waiting for payment."
    assert "id" in payload

    stored = fake_db["appointments"].docs[0]
    assert stored["status"] == "pending_payment"
    assert stored["paid"] is False


def test_create_appointment_invalid_lawyer_id_returns_400(client_with_db, monkeypatch):
    fake_db = FakeDatabase()
    client_with_db.set_db(fake_db)

    response = client_with_db.post(
        "/api/appointments/create",
        json={
            "lawyer_id": "invalid-id",
            "client_id": str(ObjectId()),
            "date": "2026-05-20",
            "time": "10:00",
            "appointment_type": "Consultation",
        },
    )

    assert response.status_code == 400
    assert "Invalid lawyer_id" in response.json()["detail"]


def test_create_appointment_invalid_client_id_returns_400(client_with_db, monkeypatch):
    fake_db = FakeDatabase()
    client_with_db.set_db(fake_db)

    response = client_with_db.post(
        "/api/appointments/create",
        json={
            "lawyer_id": str(ObjectId()),
            "client_id": "not-an-id",
            "date": "2026-05-20",
            "time": "10:00",
            "appointment_type": "Consultation",
        },
    )

    assert response.status_code == 400
    assert "Invalid client_id" in response.json()["detail"]


def test_get_lawyer_appointments_returns_list(client_with_db, monkeypatch):
    lawyer_id = ObjectId()
    client_id = ObjectId()
    appt = make_appointment(lawyer_id=lawyer_id, client_id=client_id)
    fake_db = FakeDatabase(appointments_seed=[appt])
    client_with_db.set_db(fake_db)

    response = client_with_db.get(f"/api/appointments/lawyer/{lawyer_id}")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["type"] == "Consultation"
    assert payload[0]["lawyer_id"] == str(lawyer_id)
    assert payload[0]["client_id"] == str(client_id)


def test_get_lawyer_appointments_invalid_id_returns_400(client_with_db, monkeypatch):
    fake_db = FakeDatabase()
    client_with_db.set_db(fake_db)

    response = client_with_db.get("/api/appointments/lawyer/invalid-id")

    assert response.status_code == 400
    assert "Invalid lawyer_id" in response.json()["detail"]


def test_manage_appointment_reschedule_success(client_with_db, monkeypatch):
    appt = make_appointment(status="confirmed")
    fake_db = FakeDatabase(appointments_seed=[appt])
    client_with_db.set_db(fake_db)

    response = client_with_db.patch(
        f"/api/appointments/{appt['_id']}/manage",
        json={
            "action": "reschedule",
            "new_date": "2026-05-27",
            "new_time": "14:00",
            "reason": "Schedule conflict",
        },
    )

    assert response.status_code == 200
    assert response.json()["message"] == "Appointment rescheduled successfully"

    updated = fake_db["appointments"].docs[0]
    assert updated["status"] == "rescheduled"
    assert updated["date"] == "2026-05-27"
    assert updated["time"] == "14:00"


def test_manage_appointment_reject_success(client_with_db, monkeypatch):
    appt = make_appointment(status="confirmed")
    fake_db = FakeDatabase(appointments_seed=[appt])
    client_with_db.set_db(fake_db)

    response = client_with_db.patch(
        f"/api/appointments/{appt['_id']}/manage",
        json={"action": "reject", "reason": "Unavailable"},
    )

    assert response.status_code == 200
    assert response.json()["message"] == "Appointment rejected successfully"
    assert fake_db["appointments"].docs[0]["status"] == "cancelled"


def test_manage_appointment_accept_success(client_with_db, monkeypatch):
    appt = make_appointment(status="pending_payment")
    fake_db = FakeDatabase(appointments_seed=[appt])
    client_with_db.set_db(fake_db)

    response = client_with_db.patch(
        f"/api/appointments/{appt['_id']}/manage",
        json={"action": "accept"},
    )

    assert response.status_code == 200
    assert response.json()["message"] == "Appointment accepted successfully"
    assert fake_db["appointments"].docs[0]["status"] == "confirmed"


def test_manage_appointment_reschedule_missing_date_returns_400(client_with_db, monkeypatch):
    appt = make_appointment(status="confirmed")
    fake_db = FakeDatabase(appointments_seed=[appt])
    client_with_db.set_db(fake_db)

    response = client_with_db.patch(
        f"/api/appointments/{appt['_id']}/manage",
        json={"action": "reschedule", "reason": "Schedule conflict"},
    )

    assert response.status_code == 400
    assert "new_date and new_time are required" in response.json()["detail"]


def test_manage_appointment_not_found_returns_404(client_with_db, monkeypatch):
    fake_db = FakeDatabase()
    client_with_db.set_db(fake_db)

    response = client_with_db.patch(
        f"/api/appointments/{ObjectId()}/manage",
        json={"action": "accept"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Appointment not found"


def test_mark_as_paid_success(client_with_db, monkeypatch):
    appt = make_appointment(status="pending_payment", paid=False)
    fake_db = FakeDatabase(appointments_seed=[appt])
    client_with_db.set_db(fake_db)

    response = client_with_db.patch(f"/api/appointments/{appt['_id']}/pay-success")

    assert response.status_code == 200
    assert response.json()["message"] == "Payment verified and appointment confirmed."

    updated = fake_db["appointments"].docs[0]
    assert updated["paid"] is True
    assert updated["status"] == "confirmed"


def test_mark_as_paid_not_found_returns_404(client_with_db, monkeypatch):
    fake_db = FakeDatabase()
    client_with_db.set_db(fake_db)

    response = client_with_db.patch(f"/api/appointments/{ObjectId()}/pay-success")

    assert response.status_code == 404
    assert response.json()["detail"] == "Appointment not found"


def test_get_client_appointments_success(client_with_db, monkeypatch):
    user_id = ObjectId()
    lawyer_id = ObjectId()
    user = make_user(email="client@example.com", _id=user_id)
    lawyer = make_lawyer(_id=lawyer_id, fullName="Atty. Silva")
    appt = make_appointment(
        lawyer_id=lawyer_id,
        client_id=user_id,
        status="booked",  # Route maps "booked" to "Confirmed"
        date="2026-05-20",
    )

    fake_db = FakeDatabase(
        appointments_seed=[appt],
        users_seed=[user],
        lawyers_seed=[lawyer],
    )
    client_with_db.set_db(fake_db)

    response = client_with_db.get("/api/appointments/client", params={"email": "client@example.com"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert len(payload["appointments"]) == 1
    assert payload["appointments"][0]["lawyerName"] == "Atty. Silva"
    assert payload["appointments"][0]["status"] == "Confirmed"


def test_get_client_appointments_no_matching_user(client_with_db, monkeypatch):
    fake_db = FakeDatabase()
    client_with_db.set_db(fake_db)

    response = client_with_db.get("/api/appointments/client", params={"email": "notfound@example.com"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert len(payload["appointments"]) == 0


def test_get_client_appointments_filters_excluded_statuses(client_with_db, monkeypatch):
    user_id = ObjectId()
    user = make_user(email="client@example.com", _id=user_id)
    appt_pending = make_appointment(client_id=user_id, status="pending_payment")
    appt_available = make_appointment(client_id=user_id, status="available")
    appt_confirmed = make_appointment(client_id=user_id, status="booked")

    fake_db = FakeDatabase(
        appointments_seed=[appt_pending, appt_available, appt_confirmed],
        users_seed=[user],
    )
    client_with_db.set_db(fake_db)

    response = client_with_db.get("/api/appointments/client", params={"email": "client@example.com"})

    payload = response.json()
    # Only booked appointment should be returned (not pending_payment, not available)
    assert len(payload["appointments"]) == 1
    assert payload["appointments"][0]["status"] == "Confirmed"


def test_get_client_appointments_status_mapping(client_with_db, monkeypatch):
    user_id = ObjectId()
    user = make_user(email="client@example.com", _id=user_id)
    appt_booked = make_appointment(client_id=user_id, status="booked")
    appt_canceled = make_appointment(client_id=user_id, status="canceled")
    appt_completed = make_appointment(client_id=user_id, status="completed")

    fake_db = FakeDatabase(
        appointments_seed=[appt_booked, appt_canceled, appt_completed],
        users_seed=[user],
    )
    client_with_db.set_db(fake_db)

    response = client_with_db.get("/api/appointments/client", params={"email": "client@example.com"})

    payload = response.json()
    statuses = [appt["status"] for appt in payload["appointments"]]
    # Route maps: booked → Confirmed, canceled → Canceled, completed → Completed
    assert "Confirmed" in statuses
    assert "Canceled" in statuses
    assert "Completed" in statuses


def test_get_client_appointments_unknown_lawyer_fallback(client_with_db, monkeypatch):
    user_id = ObjectId()
    user = make_user(email="client@example.com", _id=user_id)
    appt = make_appointment(
        lawyer_id=ObjectId(),  # Non-existent lawyer
        client_id=user_id,
        status="booked",  # Route maps "booked" to "Confirmed" and doesn't filter it
    )

    fake_db = FakeDatabase(appointments_seed=[appt], users_seed=[user])
    client_with_db.set_db(fake_db)

    response = client_with_db.get("/api/appointments/client", params={"email": "client@example.com"})

    payload = response.json()
    assert len(payload["appointments"]) == 1
    assert payload["appointments"][0]["lawyerName"] == "Unknown Lawyer"
    assert payload["appointments"][0]["lawyerImage"] == ""










