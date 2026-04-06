from fastapi import APIRouter, HTTPException, Query
from controllers.admin_Controller import (
    get_dashboard_stats,
    get_all_users,
    get_pending_lawyers,
    approve_or_reject_lawyer,
    delete_user,
    login_admin,
)
from models.admin import ApprovalRequest, AdminLoginRequest

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/login")
async def admin_login(request: AdminLoginRequest):
    """Admin login with JWT token generation"""
    try:
        return await login_admin(request)
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error in /admin/login: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/stats")
async def get_stats():
    """Get dashboard statistics"""
    try:
        return await get_dashboard_stats()
    except Exception as e:
        print(f"❌ Error in /admin/stats: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/users")
async def get_users(skip: int = Query(0, ge=0), limit: int = Query(10, ge=1, le=100)):
    """Get all users with pagination"""
    try:
        return await get_all_users(skip, limit)
    except Exception as e:
        print(f"❌ Error in /admin/users: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/lawyers/pending")
async def get_pending():
    """Get pending lawyer approvals"""
    try:
        return await get_pending_lawyers()
    except Exception as e:
        print(f"❌ Error in /admin/lawyers/pending: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/lawyers/approval")
async def approve_reject_lawyer(request: ApprovalRequest):
    """Approve or reject a lawyer"""
    try:
        if request.action not in ["approve", "reject"]:
            raise HTTPException(status_code=400, detail="Action must be 'approve' or 'reject'")

        return await approve_or_reject_lawyer(request.lawyer_id, request.action)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        print(f"❌ Error in /admin/lawyers/approval: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.delete("/users/{user_id}")
async def remove_user(user_id: str):
    """Delete a user"""
    try:
        return await delete_user(user_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        print(f"❌ Error in /admin/users delete: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")