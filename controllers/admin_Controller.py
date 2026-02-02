from bson import ObjectId
from typing import Dict
from config.cognilex_db import get_database


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