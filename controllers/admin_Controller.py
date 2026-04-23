from bson import ObjectId
from typing import Dict
from fastapi import HTTPException, status

from config.cognilex_db import get_database
from config.jwt import create_access_token
from datetime import datetime, timezone
from models.user import UserModel
from models.admin import AdminLoginRequest, AdminCreateRequest, AdminResponse


async def register_admin(data: AdminCreateRequest) -> Dict:
    """Register a new administrator"""
    try:
        db = get_database()

        if db is None:
            raise Exception("Database connection not available")

        admins_collection = db["admins"]

        # Check if admin already exists
        if admins_collection.find_one({"email": data.email}):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Administrator with this email already exists"
            )

        now = datetime.now(timezone.utc)
        new_admin = {
            "name": data.name,
            "email": data.email,
            "password_hash": UserModel.hash_password(data.password),
            "added_by": data.added_by,
            "created_at": now,
            "user-role": "admin"
        }

        result = admins_collection.insert_one(new_admin)

        return {
            "success": True,
            "message": "Administrator registered successfully",
            "admin_id": str(result.inserted_id)
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in register_admin: {str(e)}")
        raise


async def get_all_admins() -> Dict:
    """Get all administrators"""
    try:
        db = get_database()

        if db is None:
            raise Exception("Database connection not available")

        admins_collection = db["admins"]
        admins = list(admins_collection.find())

        for admin in admins:
            admin["id"] = str(admin.pop("_id"))
            admin.pop("password_hash", None)
            admin.pop("password", None)

        return {
            "admins": admins,
            "total": len(admins)
        }
    except Exception as e:
        print(f"Error in get_all_admins: {str(e)}")
        raise


async def get_dashboard_stats() -> Dict:
    """Get dashboard statistics"""
    try:
        db = get_database()

        if db is None:
            raise Exception("Database connection not available")

        users_collection = db["users"]
        lawyers_collection = db["lawyers"]
        chat_sessions_collection = db["chat_sessions"]

        total_users = users_collection.count_documents({})
        active_lawyers = lawyers_collection.count_documents({"status": "approved"})
        chat_sessions = chat_sessions_collection.count_documents({})
        pending_approvals = lawyers_collection.count_documents({"status": "pending"})

        return {
            "total_users": total_users,
            "active_lawyers": active_lawyers,
            "chat_sessions": chat_sessions,
            "pending_approvals": pending_approvals
        }
    except Exception as e:
        print(f"Error in get_dashboard_stats: {str(e)}")
        raise


async def get_all_users(skip: int = 0, limit: int = 10) -> Dict:
    """Get all users with pagination"""
    try:
        db = get_database()

        if db is None:
            raise Exception("Database connection not available")

        users_collection = db["users"]

        users = list(users_collection.find().skip(skip).limit(limit))
        total = users_collection.count_documents({})

        # Convert ObjectId to string and clean up
        for user in users:
            user["id"] = str(user.pop("_id"))
            user.pop("password", None)  # Remove password field
            user["status"] = user.get("status", "Active")
            user["created_at"] = user.get("created_at", None)

        return {
            "users": users,
            "total": total,
            "skip": skip,
            "limit": limit
        }
    except Exception as e:
        print(f"Error in get_all_users: {str(e)}")
        raise


async def get_pending_lawyers() -> Dict:
    """Get all pending lawyer approvals"""
    try:
        db = get_database()

        if db is None:
            raise Exception("Database connection not available")

        lawyers_collection = db["lawyers"]

        lawyers = list(lawyers_collection.find({"status": "pending"}))

        # Convert ObjectId to string
        for lawyer in lawyers:
            lawyer["id"] = str(lawyer.pop("_id"))

        return {
            "lawyers": lawyers,
            "total": len(lawyers)
        }
    except Exception as e:
        print(f"Error in get_pending_lawyers: {str(e)}")
        raise


async def approve_or_reject_lawyer(lawyer_id: str, action: str) -> Dict:
    """Approve or reject a lawyer"""
    try:
        db = get_database()

        if db is None:
            raise Exception("Database connection not available")

        lawyers_collection = db["lawyers"]

        result = lawyers_collection.update_one(
            {"_id": ObjectId(lawyer_id)},
            {"$set": {"status": "approved" if action == "approve" else "rejected"}}
        )

        if result.modified_count == 0:
            raise ValueError("Lawyer not found or already processed")

        return {
            "success": True,
            "message": f"Lawyer {action}d successfully"
        }
    except Exception as e:
        print(f"Error in approve_or_reject_lawyer: {str(e)}")
        raise


async def delete_user(user_id: str) -> Dict:
    """Delete a user"""
    try:
        db = get_database()

        if db is None:
            raise Exception("Database connection not available")

        users_collection = db["users"]

        result = users_collection.delete_one({"_id": ObjectId(user_id)})

        if result.deleted_count == 0:
            raise ValueError("User not found")

        return {
            "success": True,
            "message": "User deleted successfully"
        }
    except Exception as e:
        print(f"Error in delete_user: {str(e)}")
        raise


async def login_admin(data: AdminLoginRequest) -> Dict:
    """Authenticate admin and return JWT access token."""
    try:
        db = get_database()

        if db is None:
            raise Exception("Database connection not available")

        admins_collection = db["admins"]
        admin = admins_collection.find_one({"email": data.email})

        if not admin:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
            )

        if "password_hash" not in admin:
            # LEGACY FALLBACK: Check if there's a plain 'password' field
            if "password" in admin and admin["password"] == data.password:
                admin_role = admin.get("user-role", "admin")
            else:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid email or password",
                )
        else:
            if not UserModel.verify_password(data.password, admin["password_hash"]):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid email or password",
                )

        admin_role = admin.get("user-role", "admin")
        if admin_role != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied",
            )

        admin_id = str(admin["_id"]) if isinstance(admin["_id"], ObjectId) else str(admin["_id"])
        access_token = create_access_token(
            {
                "sub": admin_id,
                "email": admin["email"],
                "role": admin_role,
            }
        )

        return {
            "message": "Admin login successful",
            "user": {
                "id": admin_id,
                "email": admin["email"],
                "name": admin.get("name"),
                "role": admin_role,
            },
            "access_token": access_token,
            "token_type": "bearer",
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in login_admin: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}",
        )
async def delete_admin(admin_id: str) -> Dict:
    """Delete an administrator"""
    try:
        db = get_database()

        if db is None:
            raise Exception("Database connection not available")

        admins_collection = db["admins"]

        result = admins_collection.delete_one({"_id": ObjectId(admin_id)})

        if result.deleted_count == 0:
            raise ValueError("Administrator not found")

        return {
            "success": True,
            "message": "Administrator deleted successfully"
        }
    except Exception as e:
        print(f"Error in delete_admin: {str(e)}")
        raise
