from __future__ import annotations

from pathlib import Path

import importlib

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]


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
def admin_route_module():
    return importlib.import_module("routes.admin_route")


def test_admin_login_success(client, admin_route_module, monkeypatch):
    async def fake_login_admin(request):
        assert request.email == "admin@example.com"
        return {
            "message": "Admin login successful",
            "user": {"id": "a1", "email": "admin@example.com", "name": "Admin", "role": "admin"},
            "access_token": "token-123",
            "token_type": "bearer",
        }

    monkeypatch.setattr(admin_route_module, "login_admin", fake_login_admin)

    response = client.post("/admin/login", json={"email": "admin@example.com", "password": "Secret123!"})

    assert response.status_code == 200
    assert response.json()["access_token"] == "token-123"


def test_admin_login_returns_controller_http_error(client, admin_route_module, monkeypatch):
    async def fake_login_admin(_request):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    monkeypatch.setattr(admin_route_module, "login_admin", fake_login_admin)

    response = client.post("/admin/login", json={"email": "admin@example.com", "password": "wrong"})

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password"


def test_get_stats_success(client, admin_route_module, monkeypatch):
    async def fake_get_dashboard_stats():
        return {"total_users": 10, "active_lawyers": 2, "chat_sessions": 5, "pending_approvals": 1}

    monkeypatch.setattr(admin_route_module, "get_dashboard_stats", fake_get_dashboard_stats)

    response = client.get("/admin/stats")

    assert response.status_code == 200
    assert response.json()["total_users"] == 10


def test_get_users_success_with_query_params(client, admin_route_module, monkeypatch):
    seen = {}

    async def fake_get_all_users(skip, limit):
        seen["skip"] = skip
        seen["limit"] = limit
        return {"users": [], "total": 0, "skip": skip, "limit": limit}

    monkeypatch.setattr(admin_route_module, "get_all_users", fake_get_all_users)

    response = client.get("/admin/users", params={"skip": 5, "limit": 20})

    assert response.status_code == 200
    assert response.json()["limit"] == 20
    assert seen == {"skip": 5, "limit": 20}


def test_get_users_query_validation_error(client):
    response = client.get("/admin/users", params={"skip": -1, "limit": 0})

    assert response.status_code == 422


def test_pending_lawyers_success(client, admin_route_module, monkeypatch):
    async def fake_get_pending_lawyers():
        return {"lawyers": [{"id": "l1", "name": "Pending Lawyer"}], "total": 1}

    monkeypatch.setattr(admin_route_module, "get_pending_lawyers", fake_get_pending_lawyers)

    response = client.get("/admin/lawyers/pending")

    assert response.status_code == 200
    assert response.json()["total"] == 1


def test_approve_reject_lawyer_success(client, admin_route_module, monkeypatch):
    async def fake_approve_or_reject_lawyer(lawyer_id, action):
        assert lawyer_id == "lawyer-1"
        assert action == "approve"
        return {"success": True, "message": "Lawyer approved successfully"}

    monkeypatch.setattr(admin_route_module, "approve_or_reject_lawyer", fake_approve_or_reject_lawyer)

    response = client.post("/admin/lawyers/approval", json={"lawyer_id": "lawyer-1", "action": "approve"})

    assert response.status_code == 200
    assert response.json()["success"] is True


def test_approve_reject_lawyer_invalid_action_returns_500_current_behavior(client):
    response = client.post("/admin/lawyers/approval", json={"lawyer_id": "lawyer-1", "action": "hold"})

    assert response.status_code == 500
    assert "Internal server error" in response.json()["detail"]


def test_delete_user_returns_404_for_missing_user(client, admin_route_module, monkeypatch):
    async def fake_delete_user(_user_id):
        raise ValueError("User not found")

    monkeypatch.setattr(admin_route_module, "delete_user", fake_delete_user)

    response = client.delete("/admin/users/507f1f77bcf86cd799439011")

    assert response.status_code == 404
    assert response.json()["detail"] == "User not found"


def test_register_admin_success(client, admin_route_module, monkeypatch):
    async def fake_register_admin(request):
        assert request.email == "newadmin@example.com"
        return {"success": True, "message": "Administrator registered successfully", "admin_id": "a2"}

    monkeypatch.setattr(admin_route_module, "register_admin", fake_register_admin)

    response = client.post(
        "/admin/register",
        json={
            "name": "New Admin",
            "email": "newadmin@example.com",
            "password": "Secret123!",
            "added_by": "super-admin",
        },
    )

    assert response.status_code == 200
    assert response.json()["admin_id"] == "a2"


def test_get_admins_success(client, admin_route_module, monkeypatch):
    async def fake_get_all_admins():
        return {"admins": [{"id": "a1", "email": "admin@example.com"}], "total": 1}

    monkeypatch.setattr(admin_route_module, "get_all_admins", fake_get_all_admins)

    response = client.get("/admin/admins")

    assert response.status_code == 200
    assert response.json()["total"] == 1


def test_update_profile_success(client, admin_route_module, monkeypatch):
    async def fake_update_admin_profile(admin_id, data):
        assert admin_id == "507f1f77bcf86cd799439011"
        assert data["name"] == "Updated Admin"
        return {"success": True, "message": "Profile updated successfully"}

    monkeypatch.setattr(admin_route_module, "update_admin_profile", fake_update_admin_profile)

    response = client.put(
        "/admin/profile/507f1f77bcf86cd799439011",
        json={"name": "Updated Admin", "email": "updated@example.com"},
    )

    assert response.status_code == 200
    assert response.json()["success"] is True


def test_change_password_maps_value_error_to_400(client, admin_route_module, monkeypatch):
    async def fake_change_admin_password(_admin_id, _current_password, _new_password):
        raise ValueError("Current password is incorrect")

    monkeypatch.setattr(admin_route_module, "change_admin_password", fake_change_admin_password)

    response = client.post(
        "/admin/change-password/507f1f77bcf86cd799439011",
        json={"current_password": "wrong", "new_password": "NewSecret123!"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Current password is incorrect"


def test_settings_endpoints_success(client, admin_route_module, monkeypatch):
    async def fake_get_platform_settings():
        return {"markup_percentage": 20.0, "maintenance_mode": False, "allow_new_registrations": True}

    async def fake_update_platform_settings(data):
        assert data["maintenance_mode"] is True
        return {"success": True, "message": "Platform settings updated successfully"}

    monkeypatch.setattr(admin_route_module, "get_platform_settings", fake_get_platform_settings)
    monkeypatch.setattr(admin_route_module, "update_platform_settings", fake_update_platform_settings)

    get_response = client.get("/admin/settings")
    put_response = client.put("/admin/settings", json={"maintenance_mode": True})

    assert get_response.status_code == 200
    assert put_response.status_code == 200
    assert put_response.json()["success"] is True


def test_preferences_endpoints_success(client, admin_route_module, monkeypatch):
    async def fake_get_admin_preferences(admin_id):
        assert admin_id == "admin-1"
        return {"darkMode": True, "pushNotifications": False}

    async def fake_update_admin_preferences(admin_id, data):
        assert admin_id == "admin-1"
        assert data["darkMode"] is False
        return {"success": True, "message": "Preferences updated"}

    monkeypatch.setattr(admin_route_module, "get_admin_preferences", fake_get_admin_preferences)
    monkeypatch.setattr(admin_route_module, "update_admin_preferences", fake_update_admin_preferences)

    get_response = client.get("/admin/preferences/admin-1")
    put_response = client.put("/admin/preferences/admin-1", json={"darkMode": False, "pushNotifications": True})

    assert get_response.status_code == 200
    assert get_response.json()["darkMode"] is True
    assert put_response.status_code == 200
    assert put_response.json()["success"] is True


def test_finance_stats_and_analytics_success(client, admin_route_module, monkeypatch):
    async def fake_get_financial_stats(period):
        assert period == "monthly"
        return {"summary": {"totalRevenue": 1000}, "trend": [], "recentTransactions": []}

    async def fake_get_user_analytics(period):
        assert period == "daily"
        return {"summary": {"totalMessages": 100}, "trend": []}

    monkeypatch.setattr(admin_route_module, "get_financial_stats", fake_get_financial_stats)
    monkeypatch.setattr(admin_route_module, "get_user_analytics", fake_get_user_analytics)

    finance_response = client.get("/admin/finance/stats", params={"period": "monthly"})
    analytics_response = client.get("/admin/analytics", params={"period": "daily"})

    assert finance_response.status_code == 200
    assert finance_response.json()["summary"]["totalRevenue"] == 1000
    assert analytics_response.status_code == 200
    assert analytics_response.json()["summary"]["totalMessages"] == 100

