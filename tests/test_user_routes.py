from __future__ import annotations

import importlib
from datetime import datetime, timezone
from pathlib import Path

import pytest
from bson import ObjectId
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]


class FakeInsertResult:
    def __init__(self, inserted_id):
        self.inserted_id = inserted_id


class FakeDeleteResult:
    def __init__(self, deleted_count: int):
        self.deleted_count = deleted_count


class FakeUpdateResult:
    def __init__(self, matched_count: int, modified_count: int):
        self.matched_count = matched_count
        self.modified_count = modified_count


class FakeCollection:
    def __init__(self, seed_docs: list[dict] | None = None):
        self.docs = seed_docs[:] if seed_docs else []

    @staticmethod
    def _matches(doc: dict, query: dict) -> bool:
        return all(doc.get(key) == value for key, value in query.items())

    def find_one(self, query: dict):
        for doc in self.docs:
            if self._matches(doc, query):
                return doc
        return None

    def insert_one(self, doc: dict):
        if "_id" not in doc:
            doc["_id"] = ObjectId()
        self.docs.append(doc)
        return FakeInsertResult(doc["_id"])

    def update_one(self, query: dict, update: dict):
        doc = self.find_one(query)
        if not doc:
            return FakeUpdateResult(0, 0)

        for key, value in update.get("$set", {}).items():
            doc[key] = value

        return FakeUpdateResult(1, 1)

    def delete_one(self, query: dict):
        for index, doc in enumerate(self.docs):
            if self._matches(doc, query):
                del self.docs[index]
                return FakeDeleteResult(1)
        return FakeDeleteResult(0)


class FakeDatabase:
    def __init__(self, users_seed: list[dict] | None = None):
        self.collections = {"users": FakeCollection(users_seed)}

    def __getitem__(self, name: str):
        return self.collections[name]


class FakeS3Client:
    def __init__(self):
        self.uploads: list[dict] = []

    def put_object(self, **kwargs):
        self.uploads.append(kwargs)
        return {"ETag": "fake-etag"}


def make_user(
    *,
    email: str,
    name: str = "Test User",
    password_hash: str = "hashed-password",
    user_role: str = "user",
    preferences: dict | None = None,
    avatar_url: str | None = None,
):
    user = {
        "_id": ObjectId(),
        "email": email,
        "name": name,
        "password_hash": password_hash,
        "user-role": user_role,
        "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
    }
    if preferences is not None:
        user["preferences"] = preferences
    if avatar_url is not None:
        user["avatar_url"] = avatar_url
    return user


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
def user_controller_module():
    return importlib.import_module("controllers.user_controller")


def test_register_user_creates_user_and_returns_201(client, user_controller_module, monkeypatch):
    fake_db = FakeDatabase()
    monkeypatch.setattr(user_controller_module, "get_database", lambda: fake_db)
    monkeypatch.setattr(user_controller_module.UserModel, "hash_password", lambda password: "hashed-password")

    response = client.post(
        "/register",
        json={"email": "NewUser@Example.com", "name": "  New User  ", "password": "Secret123!", "role": "user"},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["message"] == "User created successfully"
    assert payload["user"]["email"] == "newuser@example.com"
    assert payload["user"]["name"] == "New User"
    assert fake_db["users"].find_one({"email": "newuser@example.com"})["password_hash"] == "hashed-password"


def test_register_user_rejects_duplicate_email(client, user_controller_module, monkeypatch):
    existing = make_user(email="dup@example.com")
    fake_db = FakeDatabase([existing])
    monkeypatch.setattr(user_controller_module, "get_database", lambda: fake_db)
    monkeypatch.setattr(user_controller_module.UserModel, "hash_password", lambda password: "hashed-password")

    response = client.post(
        "/register",
        json={"email": "dup@example.com", "name": "Duplicate User", "password": "Secret123!", "role": "user"},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Email already registered"


def test_register_oauth_user_creates_user(client, user_controller_module, monkeypatch):
    fake_db = FakeDatabase()
    monkeypatch.setattr(user_controller_module, "get_database", lambda: fake_db)

    response = client.post(
        "/register-oauth",
        json={"appwrite_id": "appwrite-123", "email": "oauth@example.com", "name": "OAuth User", "role": "user"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["message"] == "OAuth user created successfully"
    assert payload["user"]["email"] == "oauth@example.com"
    assert payload["user"]["role"] == "user"
    assert fake_db["users"].find_one({"appwrite_id": "appwrite-123"}) is not None


def test_get_user_by_email_returns_user(client, user_controller_module, monkeypatch):
    existing = make_user(email="lookup@example.com", preferences={"appearance": "dark", "language": "en"})
    fake_db = FakeDatabase([existing])
    monkeypatch.setattr(user_controller_module, "get_database", lambda: fake_db)

    response = client.get("/user/lookup@example.com")

    assert response.status_code == 200
    payload = response.json()
    assert payload["email"] == "lookup@example.com"
    assert payload["name"] == "Test User"
    assert payload["preferences"] == {"appearance": "dark", "language": "en"}


def test_get_user_by_email_returns_404_for_missing_user(client, user_controller_module, monkeypatch):
    fake_db = FakeDatabase()
    monkeypatch.setattr(user_controller_module, "get_database", lambda: fake_db)

    response = client.get("/user/missing@example.com")

    assert response.status_code == 404
    assert response.json()["detail"] == "User not found"


def test_login_user_returns_token(client, user_controller_module, monkeypatch):
    existing = make_user(email="login@example.com")
    fake_db = FakeDatabase([existing])
    monkeypatch.setattr(user_controller_module, "get_database", lambda: fake_db)
    monkeypatch.setattr(user_controller_module.UserModel, "verify_password", lambda plain, hashed: True)
    monkeypatch.setattr(user_controller_module, "create_access_token", lambda payload: "test-token")

    response = client.post("/login", json={"email": "login@example.com", "password": "Secret123!"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["message"] == "Login successful"
    assert payload["access_token"] == "test-token"
    assert payload["token_type"] == "bearer"
    assert payload["user"]["role"] == "user"


def test_login_user_rejects_invalid_password(client, user_controller_module, monkeypatch):
    existing = make_user(email="login-fail@example.com")
    fake_db = FakeDatabase([existing])
    monkeypatch.setattr(user_controller_module, "get_database", lambda: fake_db)
    monkeypatch.setattr(user_controller_module.UserModel, "verify_password", lambda plain, hashed: False)

    response = client.post("/login", json={"email": "login-fail@example.com", "password": "WrongPassword!"})

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password"


def test_update_profile_updates_user(client, user_controller_module, monkeypatch):
    existing = make_user(email="profile@example.com", name="Old Name")
    fake_db = FakeDatabase([existing])
    monkeypatch.setattr(user_controller_module, "get_database", lambda: fake_db)

    response = client.patch(
        "/profile",
        json={"email": "profile@example.com", "name": "Updated Name", "avatar_url": "https://cdn.example.com/avatar.png"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["message"] == "Profile updated successfully"
    assert payload["user"]["name"] == "Updated Name"
    assert payload["user"]["avatar_url"] == "https://cdn.example.com/avatar.png"


def test_update_profile_returns_404_for_missing_user(client, user_controller_module, monkeypatch):
    fake_db = FakeDatabase()
    monkeypatch.setattr(user_controller_module, "get_database", lambda: fake_db)

    response = client.patch("/profile", json={"email": "missing@example.com", "name": "Missing User"})

    assert response.status_code == 404
    assert response.json()["detail"] == "User not found"


def test_update_password_updates_password(client, user_controller_module, monkeypatch):
    existing = make_user(email="password@example.com")
    fake_db = FakeDatabase([existing])
    monkeypatch.setattr(user_controller_module, "get_database", lambda: fake_db)
    monkeypatch.setattr(user_controller_module.UserModel, "verify_password", lambda plain, hashed: True)
    monkeypatch.setattr(user_controller_module.UserModel, "hash_password", lambda password: "new-hash")

    response = client.patch(
        "/password",
        json={"email": "password@example.com", "current_password": "OldPassword!", "new_password": "NewPassword!"},
    )

    assert response.status_code == 200
    assert response.json()["message"] == "Password updated successfully"
    assert fake_db["users"].find_one({"email": "password@example.com"})["password_hash"] == "new-hash"


def test_update_password_rejects_invalid_current_password(client, user_controller_module, monkeypatch):
    existing = make_user(email="password-fail@example.com")
    fake_db = FakeDatabase([existing])
    monkeypatch.setattr(user_controller_module, "get_database", lambda: fake_db)
    monkeypatch.setattr(user_controller_module.UserModel, "verify_password", lambda plain, hashed: False)

    response = client.patch(
        "/password",
        json={"email": "password-fail@example.com", "current_password": "WrongOldPassword!", "new_password": "NewPassword!"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid current password"


def test_update_preferences_updates_preferences(client, user_controller_module, monkeypatch):
    existing = make_user(email="prefs@example.com")
    fake_db = FakeDatabase([existing])
    monkeypatch.setattr(user_controller_module, "get_database", lambda: fake_db)

    response = client.patch(
        "/preferences",
        json={"email": "prefs@example.com", "appearance": "dark", "language": "si"},
    )

    assert response.status_code == 200
    assert response.json()["message"] == "Preferences updated successfully"
    assert fake_db["users"].find_one({"email": "prefs@example.com"})["preferences"] == {
        "appearance": "dark",
        "language": "si",
    }


def test_upload_avatar_uploads_and_stores_url(client, user_controller_module, monkeypatch):
    existing = make_user(email="avatar@example.com")
    fake_db = FakeDatabase([existing])
    fake_s3 = FakeS3Client()

    monkeypatch.setattr(user_controller_module, "get_database", lambda: fake_db)
    monkeypatch.setattr(user_controller_module.boto3, "client", lambda *args, **kwargs: fake_s3)
    monkeypatch.setenv("R2_ACCESS_KEY_ID", "test-access")
    monkeypatch.setenv("R2_SECRET_ACCESS_KEY", "test-secret")
    monkeypatch.setenv("R2_ACCOUNT_ID", "test-account")
    monkeypatch.setenv("R2_BUCKET_NAME", "test-bucket")
    monkeypatch.setenv("R2_PUBLIC_URL", "https://cdn.example.com")

    response = client.post(
        "/avatar/upload",
        params={"email": "avatar@example.com"},
        files={"file": ("avatar.png", b"avatar-bytes", "image/png")},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["message"] == "Avatar uploaded successfully"
    assert payload["avatar_url"].startswith("https://cdn.example.com/users/")
    assert len(fake_s3.uploads) == 1
    assert fake_db["users"].find_one({"email": "avatar@example.com"})["avatar_url"] == payload["avatar_url"]


def test_delete_profile_deletes_user(client, user_controller_module, monkeypatch):
    existing = make_user(email="delete@example.com")
    fake_db = FakeDatabase([existing])
    monkeypatch.setattr(user_controller_module, "get_database", lambda: fake_db)

    response = client.delete("/profile/delete@example.com")

    assert response.status_code == 200
    assert response.json()["message"] == "Account deleted successfully"
    assert fake_db["users"].find_one({"email": "delete@example.com"}) is None


def test_delete_profile_returns_404_for_missing_user(client, user_controller_module, monkeypatch):
    fake_db = FakeDatabase()
    monkeypatch.setattr(user_controller_module, "get_database", lambda: fake_db)

    response = client.delete("/profile/missing@example.com")

    assert response.status_code == 404
    assert response.json()["detail"] == "User not found"

