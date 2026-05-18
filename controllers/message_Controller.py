from datetime import datetime, timezone

from bson import ObjectId
from fastapi import HTTPException

from config.cognilex_db import get_database
from controllers.lawyerDashboard_Controller import resolve_lawyer_id


async def send_direct_message(user_id: str, lawyer_id: str, content: str, sender_role: str = "user") -> dict:
    """
    Save a direct message between a user and a lawyer.
    """
    db = get_database()
    if db is None:
        raise HTTPException(status_code=500, detail="Database connection not available")

    # Resolve to the actual Lawyer Profile ID
    lawyer_obj_id = await resolve_lawyer_id(db, lawyer_id)
    resolved_lawyer_id = str(lawyer_obj_id)

    message_doc = {
        "user_id": user_id,
        "lawyer_id": resolved_lawyer_id,
        "content": content,
        "sender_role": sender_role,
        "timestamp": datetime.now(timezone.utc),
        "is_read": False
    }

    result = db.user_messages.insert_one(message_doc)

    return {
        "success": True,
        "message_id": str(result.inserted_id),
        "timestamp": message_doc["timestamp"].isoformat()
    }

async def get_lawyer_messages(lawyer_id: str) -> list[dict]:
    """
    Fetch all messages for a specific lawyer, grouped by user.
    """
    db = get_database()
    if db is None:
        return []

    # Resolve to the actual Lawyer Profile ID
    lawyer_obj_id = await resolve_lawyer_id(db, lawyer_id)
    resolved_lawyer_id = str(lawyer_obj_id)

    # Find messages where this lawyer is involved (check both resolved and raw ID just in case)
    # Also exclude empty messages that might cause 'ghost' counts
    query = {
        "$and": [
            {"$or": [{"lawyer_id": resolved_lawyer_id}, {"lawyer_id": lawyer_id}]},
            {"content": {"$exists": True, "$ne": ""}}
        ]
    }
    messages = list(db.user_messages.find(query).sort("timestamp", 1))

    # Enrich with user names
    enriched_messages = []
    user_cache = {}

    for msg in messages:
        uid = msg["user_id"]
        if uid not in user_cache:
            user = db.users.find_one({"_id": ObjectId(uid)}) if ObjectId.is_valid(uid) else db.users.find_one({"id": uid})
            user_cache[uid] = user.get("name", "Unknown User") if user else "Unknown User"

        enriched_messages.append({
            "id": str(msg["_id"]),
            "user_id": uid,
            "userName": user_cache[uid],
            "content": msg["content"],
            "sender_role": msg["sender_role"],
            "timestamp": msg["timestamp"].isoformat(),
            "is_read": msg.get("is_read", False)
        })

    return enriched_messages

async def get_user_messages_with_lawyer(user_id: str, lawyer_id: str) -> list[dict]:
    """
    Fetch conversation history between a specific user and lawyer.
    """
    db = get_database()
    if db is None:
        return []

    # Resolve to the actual Lawyer Profile ID
    lawyer_obj_id = await resolve_lawyer_id(db, lawyer_id)
    resolved_lawyer_id = str(lawyer_obj_id)

    query = {
        "user_id": user_id,
        "$or": [{"lawyer_id": resolved_lawyer_id}, {"lawyer_id": lawyer_id}]
    }

    messages = list(db.user_messages.find(query).sort("timestamp", 1))

    return [{
        "id": str(msg["_id"]),
        "content": msg["content"],
        "sender_role": msg["sender_role"],
        "timestamp": msg["timestamp"].isoformat()
    } for msg in messages]

async def mark_messages_as_read(lawyer_id: str, user_id: str):
    """Mark all messages from a specific user to a lawyer as read."""
    db = get_database()
    if db is not None:
        # Resolve to the actual Lawyer Profile ID
        lawyer_obj_id = await resolve_lawyer_id(db, lawyer_id)
        resolved_lawyer_id = str(lawyer_obj_id)

        db.user_messages.update_many(
            {
                "$or": [{"lawyer_id": resolved_lawyer_id}, {"lawyer_id": lawyer_id}],
                "user_id": user_id,
                "sender_role": "user"
            },
            {"$set": {"is_read": True}}
        )
