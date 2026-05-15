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
    def __init__(self, modified_count: int):
        self.modified_count = modified_count


class FakeDeleteResult:
    def __init__(self, deleted_count: int):
        self.deleted_count = deleted_count


class FakeCursor:
    def __init__(self, docs: list[dict]):
        self.docs = docs

    def sort(self, field: str, direction: int):
        reverse = direction == -1
        self.docs.sort(key=lambda item: item.get(field), reverse=reverse)
        return self

    def __iter__(self):
        return iter(self.docs)


class FakeCollection:
    def __init__(self, seed_docs: list[dict] | None = None):
        self.docs = [doc.copy() for doc in (seed_docs or [])]

    @staticmethod
    def _matches(doc: dict, query: dict) -> bool:
        if not query:
            return True
        return all(doc.get(k) == v for k, v in query.items())

    def insert_one(self, doc: dict):
        stored = doc.copy()
        stored.setdefault("_id", ObjectId())
        self.docs.append(stored)
        return FakeInsertResult(stored["_id"])

    def find(self, query: dict | None = None):
        query = query or {}
        return FakeCursor([doc for doc in self.docs if self._matches(doc, query)])

    def update_one(self, query: dict, update: dict):
        for doc in self.docs:
            if self._matches(doc, query):
                for key, value in update.get("$set", {}).items():
                    doc[key] = value
                return FakeUpdateResult(1)
        return FakeUpdateResult(0)

    def delete_one(self, query: dict):
        for idx, doc in enumerate(self.docs):
            if self._matches(doc, query):
                del self.docs[idx]
                return FakeDeleteResult(1)
        return FakeDeleteResult(0)


class FakeDatabase:
    def __init__(self, feedback_seed: list[dict] | None = None):
        self.collections = {"feedback": FakeCollection(feedback_seed)}

    def __getitem__(self, name: str):
        return self.collections[name]


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
def feedback_controller_module():
    return importlib.import_module("controllers.feedback_Controller")


def test_submit_feedback_success(client, feedback_controller_module, monkeypatch):
    fake_db = FakeDatabase()
    monkeypatch.setattr(feedback_controller_module, "get_database", lambda: fake_db)

    response = client.post(
        "/feedback",
        json={
            "name": "Jane Doe",
            "email": "jane@example.com",
            "phone": "+94771234567",
            "subject": "Support request",
            "message": "Need help with dashboard access.",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["message"] == "Feedback submitted successfully"
    assert "feedback_id" in payload

    stored = fake_db["feedback"].docs[0]
    assert stored["status"] == "pending"
    assert stored["name"] == "Jane Doe"


def test_submit_feedback_returns_500_when_db_unavailable(client, feedback_controller_module, monkeypatch):
    monkeypatch.setattr(feedback_controller_module, "get_database", lambda: None)

    response = client.post(
        "/feedback",
        json={
            "name": "Jane Doe",
            "email": "jane@example.com",
            "subject": "Support request",
            "message": "Need help with dashboard access.",
        },
    )

    assert response.status_code == 500
    assert response.json()["detail"] == "Error submitting feedback: Database connection not available"


def test_submit_feedback_validation_error(client):
    response = client.post(
        "/feedback",
        json={
            "name": "Jane Doe",
            "email": "not-an-email",
            "subject": "Support request",
            "message": "Need help",
        },
    )

    assert response.status_code == 422


def test_fetch_feedback_returns_sorted_records(client, feedback_controller_module, monkeypatch):
    older = {
        "_id": ObjectId(),
        "name": "Old Entry",
        "email": "old@example.com",
        "subject": "Old",
        "message": "Old message",
        "status": "pending",
        "created_at": datetime(2026, 1, 1, 8, 0, tzinfo=timezone.utc),
    }
    newer = {
        "_id": ObjectId(),
        "name": "New Entry",
        "email": "new@example.com",
        "subject": "New",
        "message": "New message",
        "status": "pending",
        "created_at": datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc),
    }
    fake_db = FakeDatabase([older, newer])
    monkeypatch.setattr(feedback_controller_module, "get_database", lambda: fake_db)

    response = client.get("/admin/feedback")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 2
    assert payload["feedbacks"][0]["name"] == "New Entry"
    assert payload["feedbacks"][1]["name"] == "Old Entry"
    assert "id" in payload["feedbacks"][0]


def test_mark_feedback_updates_status(client, feedback_controller_module, monkeypatch):
    feedback_id = ObjectId()
    seed = {
        "_id": feedback_id,
        "name": "Jane Doe",
        "email": "jane@example.com",
        "subject": "Subject",
        "message": "Message",
        "status": "pending",
        "created_at": datetime.now(timezone.utc),
    }
    fake_db = FakeDatabase([seed])
    monkeypatch.setattr(feedback_controller_module, "get_database", lambda: fake_db)

    response = client.patch(f"/admin/feedback/{feedback_id}/status", params={"status_value": "read"})

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert fake_db["feedback"].docs[0]["status"] == "read"


def test_mark_feedback_returns_404_when_feedback_missing(client, feedback_controller_module, monkeypatch):
    fake_db = FakeDatabase()
    monkeypatch.setattr(feedback_controller_module, "get_database", lambda: fake_db)

    response = client.patch(
        f"/admin/feedback/{ObjectId()}/status",
        params={"status_value": "read"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Feedback not found or status already set"


def test_remove_feedback_deletes_record(client, feedback_controller_module, monkeypatch):
    feedback_id = ObjectId()
    seed = {
        "_id": feedback_id,
        "name": "Delete Me",
        "email": "delete@example.com",
        "subject": "Subject",
        "message": "Message",
        "status": "pending",
        "created_at": datetime.now(timezone.utc),
    }
    fake_db = FakeDatabase([seed])
    monkeypatch.setattr(feedback_controller_module, "get_database", lambda: fake_db)

    response = client.delete(f"/admin/feedback/{feedback_id}")

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert fake_db["feedback"].docs == []


def test_remove_feedback_returns_404_when_feedback_missing(client, feedback_controller_module, monkeypatch):
    fake_db = FakeDatabase()
    monkeypatch.setattr(feedback_controller_module, "get_database", lambda: fake_db)

    response = client.delete(f"/admin/feedback/{ObjectId()}")

    assert response.status_code == 404
    assert response.json()["detail"] == "Feedback not found"

