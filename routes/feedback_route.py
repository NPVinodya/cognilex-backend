from fastapi import APIRouter, HTTPException, status
from typing import Dict

from controllers.feedback_Controller import (
    create_feedback,
    get_all_feedback,
    update_feedback_status,
    delete_feedback
)
from models.feedback import FeedbackCreate

router = APIRouter(tags=["feedback"])

@router.post("/feedback")
async def submit_feedback(request: FeedbackCreate):
    """Public endpoint to submit feedback from contact page"""
    try:
        return await create_feedback(request)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error submitting feedback: {str(e)}"
        )

@router.get("/admin/feedback")
async def fetch_feedback():
    """Admin endpoint to get all feedback submissions"""
    try:
        return await get_all_feedback()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching feedback: {str(e)}"
        )

@router.patch("/admin/feedback/{feedback_id}/status")
async def mark_feedback(feedback_id: str, status_value: str):
    """Update feedback status (e.g., mark as read)"""
    try:
        return await update_feedback_status(feedback_id, status_value)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating status: {str(e)}"
        )

@router.delete("/admin/feedback/{feedback_id}")
async def remove_feedback(feedback_id: str):
    """Delete a feedback entry"""
    try:
        return await delete_feedback(feedback_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting feedback: {str(e)}"
        )
