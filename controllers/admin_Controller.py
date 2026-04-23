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

async def update_admin_profile(admin_id: str, data: Dict) -> Dict:
    """Update administrator profile name and email"""
    try:
        db = get_database()
        admins_collection = db["admins"]

        result = admins_collection.update_one(
            {"_id": ObjectId(admin_id)},
            {"$set": {
                "name": data["name"],
                "email": data["email"],
                "updated_at": datetime.now(timezone.utc)
            }}
        )

        if result.matched_count == 0:
            raise ValueError("Administrator not found")

        return {
            "success": True,
            "message": "Profile updated successfully"
        }
    except Exception as e:
        print(f"Error in update_admin_profile: {str(e)}")
        raise

async def change_admin_password(admin_id: str, current_password: str, new_password: str) -> Dict:
    """Change administrator password with verification"""
    try:
        db = get_database()
        admins_collection = db["admins"]

        admin = admins_collection.find_one({"_id": ObjectId(admin_id)})
        if not admin:
            raise ValueError("Administrator not found")

        # Verify current password
        stored_hash = admin.get("password_hash")

        # But since we're in the controller, we can import UserModel
        from models.user import UserModel
        
        # Verify current password (assuming verify_password logic exists or using UserModel)
        try:
            if not UserModel.verify_password(current_password, stored_hash):
                # Check legacy plain text
                if stored_hash != current_password:
                    raise ValueError("Current password is incorrect")
        except:
             if stored_hash != current_password:
                    raise ValueError("Current password is incorrect")

        # Hash new password
        new_hash = UserModel.hash_password(new_password)
        
        admins_collection.update_one(
            {"_id": ObjectId(admin_id)},
            {"$set": {
                "password_hash": new_hash,
                "updated_at": datetime.now(timezone.utc)
            }}
        )

        return {
            "success": True,
            "message": "Password changed successfully"
        }
    except Exception as e:
        print(f"Error in change_admin_password: {str(e)}")
        raise

async def get_platform_settings() -> Dict:
    """Get global platform configuration settings"""
    try:
        db = get_database()
        settings_collection = db["settings"]
        
        config = settings_collection.find_one({"key": "platform_config"})
        if not config:
            # Return defaults if not found
            return {
                "markup_percentage": 20.0,
                "maintenance_mode": False,
                "allow_new_registrations": True
            }
        
        return {
            "markup_percentage": config.get("markup_percentage", 20.0),
            "maintenance_mode": config.get("maintenance_mode", False),
            "allow_new_registrations": config.get("allow_new_registrations", True)
        }
    except Exception as e:
        print(f"Error in get_platform_settings: {str(e)}")
        raise

async def update_platform_settings(data: Dict) -> Dict:
    """Update global platform configuration settings"""
    try:
        db = get_database()
        settings_collection = db["settings"]
        
        update_data = {
            "updated_at": datetime.now(timezone.utc)
        }
        
        if "markup_percentage" in data:
            update_data["markup_percentage"] = float(data["markup_percentage"])
        if "maintenance_mode" in data:
            update_data["maintenance_mode"] = bool(data["maintenance_mode"])
        if "allow_new_registrations" in data:
            update_data["allow_new_registrations"] = bool(data["allow_new_registrations"])
            
        settings_collection.update_one(
            {"key": "platform_config"},
            {"$set": update_data},
            upsert=True
        )
        
        return {
            "success": True,
            "message": "Platform settings updated successfully"
        }
    except Exception as e:
        print(f"Error in update_platform_settings: {str(e)}")
        raise

async def get_admin_preferences(admin_id: str) -> Dict:
    """Get personalized administrative preferences"""
    try:
        db = get_database()
        admins_collection = db["admins"]
        admin = admins_collection.find_one({"_id": ObjectId(admin_id)})
        
        if not admin:
            return {"darkMode": False, "pushNotifications": True}
            
        return admin.get("preferences", {"darkMode": False, "pushNotifications": True})
    except Exception as e:
        print(f"Error in get_admin_preferences: {str(e)}")
        raise

async def update_admin_preferences(admin_id: str, prefs: Dict) -> Dict:
    """Update personalized administrative preferences"""
    try:
        db = get_database()
        admins_collection = db["admins"]
        
        admins_collection.update_one(
            {"_id": ObjectId(admin_id)},
            {"$set": {"preferences": prefs}}
        )
        
        return {"success": True, "message": "Preferences updated"}
    except Exception as e:
        print(f"Error in update_admin_preferences: {str(e)}")
        raise

async def get_financial_stats(period: str = "daily") -> Dict:
    """Calculate platform-wide financial statistics with period support"""
    try:
        db = get_database()
        bookings_col = db["bookings"]
        
        # 1. Summary Stats
        pipeline = [
            {"$match": {"payment_status": "success"}},
            {"$group": {
                "_id": None,
                "total_revenue": {"$sum": {"$toDouble": "$amount"}},
                "count": {"$sum": 1}
            }}
        ]
        stats_result = list(bookings_col.aggregate(pipeline))
        stats = stats_result[0] if stats_result else {"total_revenue": 0, "count": 0}
        
        count = stats.get("count", 0)
        total_revenue = stats.get("total_revenue", 0)
        platform_fees = count * 200
        lawyer_payouts = total_revenue - platform_fees

        # 2. Trend Data based on period
        from datetime import timedelta
        now = datetime.now(timezone.utc)
        
        if period == "monthly":
            # Last 6 months
            start_date = now - timedelta(days=180)
            group_format = "%Y-%m"
        else:
            # Last 7 days
            start_date = now - timedelta(days=7)
            group_format = "%Y-%m-%d"
            
        daily_pipeline = [
            {"$match": {
                "createdAt": {"$gte": start_date},
                "payment_status": "success"
            }},
            {"$group": {
                "_id": {"$dateToString": {"format": group_format, "date": "$createdAt"}},
                "revenue": {"$sum": {"$toDouble": "$amount"}}
            }},
            {"$sort": {"_id": 1}}
        ]
        trend_data = list(bookings_col.aggregate(daily_pipeline))
        
        # 3. Growth
        current_month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        last_month_start = (current_month_start - timedelta(days=1)).replace(day=1)
            
        curr_month_rev = list(bookings_col.aggregate([
            {"$match": {"createdAt": {"$gte": current_month_start}, "payment_status": "success"}},
            {"$group": {"_id": None, "total": {"$sum": {"$toDouble": "$amount"}}}}
        ]))
        last_month_rev = list(bookings_col.aggregate([
            {"$match": {"createdAt": {"$gte": last_month_start, "$lt": current_month_start}, "payment_status": "success"}},
            {"$group": {"_id": None, "total": {"$sum": {"$toDouble": "$amount"}}}}
        ]))
        
        cur_total = curr_month_rev[0]["total"] if curr_month_rev else 0
        last_total = last_month_rev[0]["total"] if last_month_rev else 0
        growth = round(((cur_total - last_total) / last_total * 100) if last_total > 0 else (100.0 if cur_total > 0 else 0), 1)

        # 4. Recent Transactions with Lawyer Name
        pipeline_tx = [
            {"$match": {"payment_status": "success"}},
            {"$sort": {"createdAt": -1}},
            {"$limit": 10},
            {"$lookup": {
                "from": "users",
                "localField": "lawyer_id",
                "foreignField": "_id",
                "as": "lawyer_info"
            }},
            {"$unwind": {"path": "$lawyer_info", "preserveNullAndEmptyArrays": True}}
        ]
        
        recent_tx_raw = list(bookings_col.aggregate(pipeline_tx))
        recent_tx = []
        
        for tx in recent_tx_raw:
            recent_tx.append({
                "id": str(tx.get("_id")),
                "amount": float(tx.get("amount", 0)),
                "clientName": tx.get("client_name", "Anonymous"),
                "lawyerName": tx.get("lawyer_info", {}).get("fullName", "N/A"),
                "lawyerId": str(tx.get("lawyer_id", "N/A")),
                "date": tx.get("createdAt").isoformat() if tx.get("createdAt") else ""
            })

        return {
            "summary": {
                "totalRevenue": total_revenue,
                "platformFees": platform_fees,
                "lawyerPayouts": lawyer_payouts,
                "totalBookings": count,
                "growth": growth,
                "feeValue": 200
            },
            "trend": trend_data,
            "recentTransactions": recent_tx
        }
    except Exception as e:
        print(f"Error in get_financial_stats: {str(e)}")
        raise
    except Exception as e:
        print(f"Error in get_financial_stats: {str(e)}")
        raise
