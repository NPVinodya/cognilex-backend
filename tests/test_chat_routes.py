from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import importlib

import pytest
from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]


class FakeInsertResult:
    def __init__(self, inserted_id):
        self.inserted_id = inserted_id


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
        return all(doc.get(key) == value for key, value in query.items())

    def find_one(self, query: dict):
        for doc in self.docs:
            if self._matches(doc, query):
                return doc
        return None

    def find(self, query: dict):
        return FakeCursor([doc for doc in self.docs if self._matches(doc, query)])

    def insert_one(self, doc: dict):
        stored = doc.copy()
        stored.setdefault("_id", f"doc-{len(self.docs) + 1}")
        self.docs.append(stored)
        return FakeInsertResult(stored["_id"])

    def insert_many(self, docs: list[dict]):
        for doc in docs:
            self.insert_one(doc)

    def update_one(self, query: dict, update: dict):
        target = self.find_one(query)
        if not target:
            return None
        for key, value in update.get("$set", {}).items():
            target[key] = value
        return None

    def delete_many(self, query: dict):
        kept = []
        deleted = 0
        for doc in self.docs:
            if self._matches(doc, query):
                deleted += 1
            else:
                kept.append(doc)
        self.docs = kept
        return FakeDeleteResult(deleted)

    def delete_one(self, query: dict):
        for index, doc in enumerate(self.docs):
            if self._matches(doc, query):
                del self.docs[index]
                return FakeDeleteResult(1)
        return FakeDeleteResult(0)


class FakeDatabase(SimpleNamespace):
    pass


class FakeHTTPResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


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
def chat_controller_module():
    return importlib.import_module("controllers.chat_controller")


def _seed_chat_db():
    session_id = "session-1"
    session_doc = {
        "id": session_id,
        "user_id": "user-1",
        "title": "Existing Chat",
        "created_at": datetime(2026, 5, 1, 8, 0, tzinfo=timezone.utc).isoformat(),
        "updated_at": datetime(2026, 5, 1, 9, 0, tzinfo=timezone.utc).isoformat(),
    }
    message_docs = [
        {
            "session_id": session_id,
            "role": "user",
            "content": "What is child abuse?",
            "created_at": datetime(2026, 5, 1, 9, 1, tzinfo=timezone.utc).isoformat(),
        },
        {
            "session_id": session_id,
            "role": "bot",
            "content": "It includes physical, emotional, or sexual abuse.",
            "sources": ["case2.pdf (p.1)"],
            "related_cases": [{"title": "Inoka Gallage v. Kamal Addararachchi"}],
            "latency": "2.10s",
            "mode": "research",
            "created_at": datetime(2026, 5, 1, 9, 2, tzinfo=timezone.utc).isoformat(),
        },
    ]
    return FakeDatabase(
        chat_sessions=FakeCollection([session_doc]),
        chat_messages=FakeCollection(message_docs),
        guest_interactions=FakeCollection(),
    )


def test_chat_ask_success_with_updated_rag_shape(client, chat_controller_module, monkeypatch):
    fake_db = _seed_chat_db()
    captured_payload = {}

    class FakeAsyncClient:
        def __init__(self, timeout):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, json, headers):
            captured_payload["url"] = url
            captured_payload["json"] = json
            return FakeHTTPResponse(
                200,
                {
                    "answer": "Child abuse includes physical, emotional, or sexual abuse.",
                    "mode": "Research RAG Chat (Llama 3.3 70B — en)",
                    "sources": ["case1.pdf (p.8)", "case2.pdf (p.1)"],
                    "related_cases": [
                        {
                            "title": "Inoka Gallage v. Kamal Addararachchi",
                            "filename": "inoka_gallage_v_kamal.pdf",
                            "relation": "Keyword match",
                        }
                    ],
                    "latency": "3.01s",
                },
            )

    monkeypatch.setattr(chat_controller_module, "get_database", lambda: fake_db)
    monkeypatch.setattr(chat_controller_module.httpx, "AsyncClient", FakeAsyncClient)

    response = client.post(
        "/chat/ask",
        json={
            "question": "Explain child abuse with legal basis",
            "user_id": "user-22",
            "mode": "research",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["answer"].startswith("Child abuse includes")
    assert payload["mode"] == "Research RAG Chat (Llama 3.3 70B — en)"
    assert len(payload["sources"]) == 2
    assert len(payload["related_cases"]) == 1
    assert payload["latency"] == "3.01s"
    assert payload["session_id"]

    # Controller should pass normalized mode + generated session to the RAG API.
    assert captured_payload["url"].endswith("/ask")
    assert captured_payload["json"]["mode"] == "research"
    assert captured_payload["json"]["session_id"] == payload["session_id"]


def test_chat_ask_rag_non_200_maps_to_502(client, chat_controller_module, monkeypatch):
    fake_db = _seed_chat_db()

    class FakeAsyncClient:
        def __init__(self, timeout):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, json, headers):
            return FakeHTTPResponse(503, {"detail": "RAG temporarily unavailable"})

    monkeypatch.setattr(chat_controller_module, "get_database", lambda: fake_db)
    monkeypatch.setattr(chat_controller_module.httpx, "AsyncClient", FakeAsyncClient)

    response = client.post("/chat/ask", json={"question": "Any legal basis?", "user_id": "u-1"})

    assert response.status_code == 502
    assert response.json()["detail"] == "RAG temporarily unavailable"


def test_guest_mode_success(client, chat_controller_module, monkeypatch):
    fake_db = _seed_chat_db()

    class FakeAsyncClient:
        def __init__(self, timeout):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, json, headers):
            return FakeHTTPResponse(
                200,
                {
                    "answer": "General guidance response",
                    "mode": "research",
                    "sources": [],
                    "related_cases": [],
                    "latency": "1.00s",
                },
            )

    monkeypatch.setattr(chat_controller_module, "get_database", lambda: fake_db)
    monkeypatch.setattr(chat_controller_module.httpx, "AsyncClient", FakeAsyncClient)

    response = client.post("/chat/guest_mode", json={"question": "What is legal aid?"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["answer"] == "General guidance response"
    assert payload["mode"] == "research"
    assert len(fake_db.guest_interactions.docs) == 2


def test_fetch_sessions_returns_user_sessions(client, chat_controller_module, monkeypatch):
    fake_db = _seed_chat_db()
    monkeypatch.setattr(chat_controller_module, "get_database", lambda: fake_db)

    response = client.get("/chat/sessions", params={"user_id": "user-1"})

    assert response.status_code == 200
    assert response.json()["sessions"][0]["id"] == "session-1"


def test_fetch_history_returns_messages(client, chat_controller_module, monkeypatch):
    fake_db = _seed_chat_db()
    monkeypatch.setattr(chat_controller_module, "get_database", lambda: fake_db)

    response = client.get("/chat/history", params={"session_id": "session-1"})

    assert response.status_code == 200
    messages = response.json()["messages"]
    assert len(messages) == 2
    assert messages[1]["related_cases"][0]["title"] == "Inoka Gallage v. Kamal Addararachchi"


def test_rename_session_updates_title(client, chat_controller_module, monkeypatch):
    fake_db = _seed_chat_db()
    monkeypatch.setattr(chat_controller_module, "get_database", lambda: fake_db)

    response = client.patch("/chat/session/session-1/title", params={"title": "Renamed chat"})

    assert response.status_code == 200
    assert response.json()["message"] == "Session renamed successfully"
    assert fake_db.chat_sessions.find_one({"id": "session-1"})["title"] == "Renamed chat"


def test_delete_session_success(client, chat_controller_module, monkeypatch):
    fake_db = _seed_chat_db()
    monkeypatch.setattr(chat_controller_module, "get_database", lambda: fake_db)

    response = client.delete("/chat/session/session-1")

    assert response.status_code == 200
    assert response.json()["deleted"] is True
    assert response.json()["messages_removed"] == 2


def test_delete_session_returns_404_when_missing(client, chat_controller_module, monkeypatch):
    fake_db = _seed_chat_db()
    monkeypatch.setattr(chat_controller_module, "get_database", lambda: fake_db)

    response = client.delete("/chat/session/missing-session")

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_share_endpoints_create_get_and_save(client, chat_controller_module, monkeypatch):
    fake_db = _seed_chat_db()
    monkeypatch.setattr(chat_controller_module, "get_database", lambda: fake_db)

    create_resp = client.post("/chat/share", json={"session_id": "session-1"})
    assert create_resp.status_code == 200
    share_id = create_resp.json()["share_id"]

    get_resp = client.get(f"/chat/share/{share_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["title"] == "Existing Chat"
    assert len(get_resp.json()["messages"]) == 2

    save_resp = client.post(f"/chat/share/{share_id}/save", json={"user_id": "new-user"})
    assert save_resp.status_code == 200
    assert save_resp.json()["new_session_id"]


def test_chat_health_endpoint(client):
    response = client.get("/chat/health")

    assert response.status_code == 200
    assert response.json()["rest_api"] == "ok"


def test_chat_request_validation_error(client):
    response = client.post("/chat/ask", json={"question": ""})

    assert response.status_code == 422

