from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import importlib

import pytest
from bson import ObjectId
from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]


class FakeInsertResult:
    def __init__(self, inserted_id: ObjectId):
        self.inserted_id = inserted_id


class FakeUpdateManyResult:
    def __init__(self, matched_count: int, modified_count: int):
        self.matched_count = matched_count
        self.modified_count = modified_count


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

    def _match_condition(self, doc: dict, key: str, condition):
        if isinstance(condition, dict):
            if "$exists" in condition:
                exists = key in doc
                if exists != condition["$exists"]:
                    return False
            if "$ne" in condition and doc.get(key) == condition["$ne"]:
                return False
            return True
        return doc.get(key) == condition

    def _matches(self, doc: dict, query: dict) -> bool:
        for key, value in query.items():
            if key == "$or":
                if not any(self._matches(doc, clause) for clause in value):
                    return False
                continue
            if key == "$and":
                if not all(self._matches(doc, clause) for clause in value):
                    return False
                continue
            if not self._match_condition(doc, key, value):
                return False
        return True

    def find(self, query: dict):
        matched = [doc for doc in self.docs if self._matches(doc, query)]
        return FakeCursor(matched)

    def find_one(self, query: dict):
        for doc in self.docs:
            if self._matches(doc, query):
                return doc
        return None

    def insert_one(self, doc: dict):
        stored = doc.copy()
        stored.setdefault("_id", ObjectId())
        self.docs.append(stored)
        return FakeInsertResult(stored["_id"])

    def update_many(self, query: dict, update: dict):
        matched_count = 0
        modified_count = 0
        for doc in self.docs:
            if self._matches(doc, query):
                matched_count += 1
                for key, value in update.get("$set", {}).items():
                    if doc.get(key) != value:
                        doc[key] = value
                        modified_count += 1
        return FakeUpdateManyResult(matched_count, modified_count)


class FakeDatabase(SimpleNamespace):
    pass


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
def message_controller_module():
    return importlib.import_module("controllers.message_Controller")


def _seed_db():
    user_oid = ObjectId()
    user_messages = FakeCollection(
        [
            {
                "_id": ObjectId(),
                "user_id": str(user_oid),
                "lawyer_id": "resolved-lawyer-1",
                "content": "Hello from user",
                "sender_role": "user",
                "timestamp": datetime(2026, 5, 1, 10, 0, tzinfo=timezone.utc),
                "is_read": False,
            },
            {
                "_id": ObjectId(),
                "user_id": str(user_oid),
                "lawyer_id": "resolved-lawyer-1",
                "content": "Reply from lawyer",
                "sender_role": "lawyer",
                "timestamp": datetime(2026, 5, 1, 10, 5, tzinfo=timezone.utc),
                "is_read": False,
            },
            {
                "_id": ObjectId(),
                "user_id": str(user_oid),
                "lawyer_id": "resolved-lawyer-1",
                "content": "",
                "sender_role": "user",
                "timestamp": datetime(2026, 5, 1, 10, 10, tzinfo=timezone.utc),
                "is_read": False,
            },
        ]
    )
    users = FakeCollection([{"_id": user_oid, "name": "Sample User"}])
    return FakeDatabase(user_messages=user_messages, users=users), str(user_oid)


def test_send_message_returns_success(client, message_controller_module, monkeypatch):
    fake_db = FakeDatabase(user_messages=FakeCollection(), users=FakeCollection())

    async def fake_resolve(_db, _lawyer_id):
        return "resolved-lawyer-1"

    monkeypatch.setattr(message_controller_module, "get_database", lambda: fake_db)
    monkeypatch.setattr(message_controller_module, "resolve_lawyer_id", fake_resolve)

    response = client.post(
        "/api/messages/send",
        json={
            "user_id": "u-100",
            "lawyer_id": "lawyer-public-id",
            "content": "Need legal guidance",
            "sender_role": "user",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert "message_id" in payload
    assert payload["timestamp"].endswith("+00:00")

    inserted = fake_db.user_messages.docs[0]
    assert inserted["lawyer_id"] == "resolved-lawyer-1"
    assert inserted["content"] == "Need legal guidance"


def test_send_message_returns_500_when_db_unavailable(client, message_controller_module, monkeypatch):
    async def fake_resolve(_db, _lawyer_id):
        return "resolved-lawyer-1"

    monkeypatch.setattr(message_controller_module, "get_database", lambda: None)
    monkeypatch.setattr(message_controller_module, "resolve_lawyer_id", fake_resolve)

    response = client.post(
        "/api/messages/send",
        json={"user_id": "u-100", "lawyer_id": "lawyer-public-id", "content": "Message"},
    )

    assert response.status_code == 500
    assert response.json()["detail"] == "Database connection not available"


def test_get_lawyer_messages_enriches_user_name(client, message_controller_module, monkeypatch):
    fake_db, user_id = _seed_db()

    async def fake_resolve(_db, _lawyer_id):
        return "resolved-lawyer-1"

    monkeypatch.setattr(message_controller_module, "get_database", lambda: fake_db)
    monkeypatch.setattr(message_controller_module, "resolve_lawyer_id", fake_resolve)

    response = client.get("/api/messages/lawyer/lawyer-public-id")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 2
    assert payload[0]["user_id"] == user_id
    assert payload[0]["userName"] == "Sample User"
    assert payload[0]["content"] == "Hello from user"
    assert payload[1]["content"] == "Reply from lawyer"


def test_get_conversation_returns_chronological_messages(client, message_controller_module, monkeypatch):
    fake_db, user_id = _seed_db()

    async def fake_resolve(_db, _lawyer_id):
        return "resolved-lawyer-1"

    monkeypatch.setattr(message_controller_module, "get_database", lambda: fake_db)
    monkeypatch.setattr(message_controller_module, "resolve_lawyer_id", fake_resolve)

    response = client.get(f"/api/messages/conversation/{user_id}/lawyer-public-id")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 3
    assert payload[0]["content"] == "Hello from user"
    assert payload[1]["sender_role"] == "lawyer"


def test_mark_read_marks_only_user_messages(client, message_controller_module, monkeypatch):
    fake_db, user_id = _seed_db()

    async def fake_resolve(_db, _lawyer_id):
        return "resolved-lawyer-1"

    monkeypatch.setattr(message_controller_module, "get_database", lambda: fake_db)
    monkeypatch.setattr(message_controller_module, "resolve_lawyer_id", fake_resolve)

    response = client.post(f"/api/messages/read/lawyer-public-id/{user_id}")

    assert response.status_code == 200
    assert response.json() == {"success": True}

    user_messages = [doc for doc in fake_db.user_messages.docs if doc["sender_role"] == "user"]
    lawyer_messages = [doc for doc in fake_db.user_messages.docs if doc["sender_role"] == "lawyer"]
    assert all(doc["is_read"] is True for doc in user_messages)
    assert all(doc["is_read"] is False for doc in lawyer_messages)


def test_list_endpoints_return_empty_when_db_is_none(client, message_controller_module, monkeypatch):
    async def fake_resolve(_db, _lawyer_id):
        return "resolved-lawyer-1"

    monkeypatch.setattr(message_controller_module, "get_database", lambda: None)
    monkeypatch.setattr(message_controller_module, "resolve_lawyer_id", fake_resolve)

    lawyer_resp = client.get("/api/messages/lawyer/any")
    conversation_resp = client.get("/api/messages/conversation/user-1/lawyer-1")

    assert lawyer_resp.status_code == 200
    assert lawyer_resp.json() == []
    assert conversation_resp.status_code == 200
    assert conversation_resp.json() == []


