from __future__ import annotations

import importlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]


class FakeUpdateResult:
    def __init__(self, modified_count: int):
        self.modified_count = modified_count


class FakeCollection:
    def __init__(self):
        self.last_filter = None
        self.last_update = None
        self.last_upsert = None
        self.next_modified_count = 1

    def update_one(self, filter_doc: dict, update_doc: dict, upsert: bool = False):
        self.last_filter = filter_doc
        self.last_update = update_doc
        self.last_upsert = upsert
        return FakeUpdateResult(self.next_modified_count)


class FakeDatabase:
    def __init__(self):
        self.collections = {
            "availability": FakeCollection(),
            "appointments": FakeCollection(),
        }

    def __getitem__(self, item):
        return self.collections[item]


@pytest.fixture()
def main_module(monkeypatch):
    monkeypatch.chdir(ROOT)
    main = importlib.import_module("main")
    monkeypatch.setattr(main, "connect_to_mongodb", lambda: None)
    monkeypatch.setattr(main, "close_mongodb_connection", lambda: None)
    return main


@pytest.fixture()
def client(main_module):
    with TestClient(main_module.app) as test_client:
        yield test_client


@pytest.fixture()
def lawyer_route_module():
    return importlib.import_module("routes.lawyer_route")


def _lawyer_form_data() -> dict:
    return {
        "fullName": "Jane Lawyer",
        "email": "jane@example.com",
        "phone": "+94770000000",
        "address": "123 Main Street",
        "city": "Colombo",
        "province": "Western",
        "nicNumber": "199012345678",
        "lawyerId": "LAW-001",
        "barCouncilNumber": "BC-12345",
        "specialization": "Criminal Law",
        "yearsOfExperience": "8",
        "lawFirm": "",
        "languagesSpoken": "English,Sinhala",
        "lawSchool": "University of Colombo",
        "graduationYear": "2016",
        "additionalQualifications": "LLM",
        "practiceAreas": '["Criminal","Family"]',
        "consultationFee": "5000",
        "availability": "Mon-Fri",
        "bio": "Experienced litigator",
    }


def _lawyer_files() -> dict:
    return {
        "profilePhoto": ("profile.jpg", b"img", "image/jpeg"),
        "nicFrontPhoto": ("nic-front.jpg", b"img", "image/jpeg"),
        "nicBackPhoto": ("nic-back.jpg", b"img", "image/jpeg"),
        "lawyerIdPhoto": ("lawyer-id.jpg", b"img", "image/jpeg"),
    }


def test_register_lawyer_success(client, lawyer_route_module, monkeypatch):
    async def fake_register_lawyer(lawyer_data, files):
        assert lawyer_data["email"] == "jane@example.com"
        assert lawyer_data["yearsOfExperience"] == 8
        assert lawyer_data["practiceAreas"] == ["Criminal", "Family"]
        assert set(files.keys()) == {"profilePhoto", "nicFrontPhoto", "nicBackPhoto", "lawyerIdPhoto"}
        return "lawyer-abc"

    monkeypatch.setattr(lawyer_route_module, "register_lawyer", fake_register_lawyer)

    response = client.post("/lawyer/register", data=_lawyer_form_data(), files=_lawyer_files())

    assert response.status_code == 201
    assert response.json() == {"success": True, "lawyer_id": "lawyer-abc"}


def test_register_lawyer_invalid_file_type_currently_maps_to_500(client):
    files = _lawyer_files()
    files["profilePhoto"] = ("profile.gif", b"img", "image/gif")

    response = client.post("/lawyer/register", data=_lawyer_form_data(), files=files)

    # Current route wraps all exceptions and returns 500.
    assert response.status_code == 500
    assert "Invalid file type" in response.json()["detail"]


def test_register_lawyer_invalid_practice_area_json_currently_maps_to_500(client):
    data = _lawyer_form_data()
    data["practiceAreas"] = "not-json"

    response = client.post("/lawyer/register", data=data, files=_lawyer_files())

    # Current route wraps all exceptions and returns 500.
    assert response.status_code == 500
    assert "Invalid practice areas format" in response.json()["detail"]


def test_get_all_lawyers_route_success(client, lawyer_route_module, monkeypatch):
    async def fake_get_all_lawyers(province, specialization, status):
        assert province == "Western"
        assert specialization == "Criminal Law"
        assert status == "approved"
        return [{"_id": "l1", "fullName": "Jane Lawyer"}]

    monkeypatch.setattr(lawyer_route_module, "get_all_lawyers", fake_get_all_lawyers)

    response = client.get(
        "/lawyer/all",
        params={"province": "Western", "specialization": "Criminal Law", "status": "approved"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["count"] == 1
    assert payload["lawyers"][0]["_id"] == "l1"


def test_get_pending_lawyers_route_success(client, lawyer_route_module, monkeypatch):
    async def fake_get_pending_lawyers():
        return [{"_id": "p1", "fullName": "Pending Lawyer"}]

    monkeypatch.setattr(lawyer_route_module, "get_pending_lawyers", fake_get_pending_lawyers)

    response = client.get("/lawyer/pending")

    assert response.status_code == 200
    assert response.json()["count"] == 1


def test_get_lawyer_by_id_found(client, lawyer_route_module, monkeypatch):
    async def fake_get_lawyer_by_id(_lawyer_id):
        return {"_id": "l1", "fullName": "Jane Lawyer"}

    monkeypatch.setattr(lawyer_route_module, "get_lawyer_by_id", fake_get_lawyer_by_id)

    response = client.get("/lawyer/l1")

    assert response.status_code == 200
    assert response.json()["lawyer"]["fullName"] == "Jane Lawyer"


def test_get_lawyer_by_id_not_found(client, lawyer_route_module, monkeypatch):
    async def fake_get_lawyer_by_id(_lawyer_id):
        return None

    monkeypatch.setattr(lawyer_route_module, "get_lawyer_by_id", fake_get_lawyer_by_id)

    response = client.get("/lawyer/missing")

    assert response.status_code == 404
    assert response.json()["detail"] == "Lawyer not found"


def test_approve_lawyer_route_success(client, lawyer_route_module, monkeypatch):
    async def fake_approve_lawyer(_lawyer_id):
        return True

    monkeypatch.setattr(lawyer_route_module, "approve_lawyer", fake_approve_lawyer)

    response = client.post("/lawyer/l1/approve")

    assert response.status_code == 200
    assert response.json() == {"success": True, "message": "Approved"}


def test_reject_lawyer_route_success(client, lawyer_route_module, monkeypatch):
    async def fake_reject_lawyer(_lawyer_id, reason):
        assert reason == "Documents not clear"
        return True

    monkeypatch.setattr(lawyer_route_module, "reject_lawyer", fake_reject_lawyer)

    response = client.post("/lawyer/l1/reject", data={"reason": "Documents not clear"})

    assert response.status_code == 200
    assert response.json() == {"success": True, "message": "Rejected"}


def test_update_availability_success(client, lawyer_route_module, monkeypatch):
    fake_db = FakeDatabase()
    monkeypatch.setattr(lawyer_route_module, "get_database", lambda: fake_db)

    response = client.put(
        "/lawyer/lawyer-1/availability",
        json={"availability": ["2026-05-12T10:00:00Z", "2026-05-13T11:00:00Z"]},
    )

    assert response.status_code == 200
    assert response.json() == {"success": True, "message": "Availability updated"}
    assert fake_db["availability"].last_filter == {"lawyerId": "lawyer-1"}
    assert "slots" in fake_db["availability"].last_update["$set"]
    assert fake_db["availability"].last_upsert is True


def test_manage_appointment_accept_success(client, lawyer_route_module, monkeypatch):
    fake_db = FakeDatabase()
    monkeypatch.setattr(lawyer_route_module, "get_database", lambda: fake_db)

    response = client.patch(
        "/lawyer/lawyer-1/appointments/507f1f77bcf86cd799439011/manage",
        data={"action": "accept"},
    )

    assert response.status_code == 200
    assert response.json()["message"] == "Appointment accepted"
    assert fake_db["appointments"].last_filter["lawyerId"] == "lawyer-1"
    assert fake_db["appointments"].last_update["$set"]["status"] == "confirmed"


def test_manage_appointment_reschedule_success(client, lawyer_route_module, monkeypatch):
    fake_db = FakeDatabase()
    monkeypatch.setattr(lawyer_route_module, "get_database", lambda: fake_db)

    response = client.patch(
        "/lawyer/lawyer-1/appointments/507f1f77bcf86cd799439011/manage",
        data={"action": "reschedule", "new_date": "2026-05-20", "reason": "Court conflict"},
    )

    assert response.status_code == 200
    assert response.json()["message"] == "Appointment rescheduleed"
    update_set = fake_db["appointments"].last_update["$set"]
    assert update_set["status"] == "rescheduled"
    assert update_set["date"] == "2026-05-20"


def test_manage_appointment_not_found_currently_maps_to_500(client, lawyer_route_module, monkeypatch):
    fake_db = FakeDatabase()
    fake_db["appointments"].next_modified_count = 0
    monkeypatch.setattr(lawyer_route_module, "get_database", lambda: fake_db)

    response = client.patch(
        "/lawyer/lawyer-1/appointments/507f1f77bcf86cd799439011/manage",
        data={"action": "reject", "reason": "Unavailable"},
    )

    # Current route catches HTTPException and rethrows as 500.
    assert response.status_code == 500
    assert "Appointment not found or unauthorized" in response.json()["detail"]

