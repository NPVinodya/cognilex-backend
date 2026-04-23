from typing import Dict, List
from bson import ObjectId
from datetime import datetime, timezone
from fastapi import HTTPException, status

from config.cognilex_db import get_database
from models.feedback import FeedbackCreate

async def create_feedback(data: FeedbackCreate) -> Dict:
    """Save a new feedback submission"""
    try:
        db = get_database()
        if db is None:
            raise Exception("Database connection not available")

        feedback_collection = db["feedback"]
        
        new_feedback = data.model_dump()
        new_feedback["created_at"] = datetime.now(timezone.utc)
        new_feedback["status"] = "pending"

        result = feedback_collection.insert_one(new_feedback)
        
        return {
            "success": True,
            "message": "Feedback submitted successfully",
            "feedback_id": str(result.inserted_id)
        }
    except Exception as e:
        print(f"Error in create_feedback: {str(e)}")
        raise

async def get_all_feedback() -> Dict:
    """Retrieve all feedback submissions for admin"""
    try:
        db = get_database()
        if db is None:
            raise Exception("Database connection not available")

        feedback_collection = db["feedback"]
        # Sort by newest first
        feedbacks = list(feedback_collection.find().sort("created_at", -1))

        for item in feedbacks:
            item["id"] = str(item.pop("_id"))
            # Ensure ISO format for frontend if needed, but datetime objects are fine for FastAPI
            
        return {
            "feedbacks": feedbacks,
            "total": len(feedbacks)
        }
    except Exception as e:
        print(f"Error in get_all_feedback: {str(e)}")
        raise

async def update_feedback_status(feedback_id: str, status_value: str) -> Dict:
    """Update the status of a feedback entry (e.g., mark as read)"""
    try:
        db = get_database()
        if db is None:
            raise Exception("Database connection not available")

        feedback_collection = db["feedback"]
        
        result = feedback_collection.update_one(
            {"_id": ObjectId(feedback_id)},
            {"$set": {"status": status_value}}
        )

        if result.modified_count == 0:
            raise ValueError("Feedback not found or status already set")

        return {
            "success": True,
            "message": f"Status updated to {status_value}"
        }
    except Exception as e:
        print(f"Error in update_feedback_status: {str(e)}")
        raise

async def delete_feedback(feedback_id: str) -> Dict:
    """Delete a feedback entry"""
    try:
        db = get_database()
        if db is None:
            raise Exception("Database connection not available")

        feedback_collection = db["feedback"]
        result = feedback_collection.delete_one({"_id": ObjectId(feedback_id)})

        if result.deleted_count == 0:
            raise ValueError("Feedback not found")

        return {
            "success": True,
            "message": "Feedback deleted successfully"
        }
    except Exception as e:
        print(f"Error in delete_feedback: {str(e)}")
        raise
