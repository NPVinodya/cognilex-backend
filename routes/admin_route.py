
from fastapi import APIRouter, HTTPException, Query

from controllers.admin_Controller import (
    approve_or_reject_lawyer,
    change_admin_password,
    delete_admin,
    delete_user,
    get_admin_preferences,
    get_all_admins,
    get_all_users,
    get_dashboard_stats,
    get_financial_stats,
    get_pending_lawyers,
    get_platform_settings,
    get_user_analytics,
    login_admin,
    register_admin,
    update_admin_preferences,
    update_admin_profile,
    update_platform_settings,
)
from models.admin import AdminCreateRequest, AdminLoginRequest, ApprovalRequest

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/login")
async def admin_login(request: AdminLoginRequest):
    """Admin login with JWT token generation"""
    try:
        return await login_admin(request)
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in /admin/login: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/stats")
async def get_stats():
    """Get dashboard statistics"""
    try:
        return await get_dashboard_stats()
    except Exception as e:
        print(f"Error in /admin/stats: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/users")
async def get_users(skip: int = Query(0, ge=0), limit: int = Query(10, ge=1, le=100)):
    """Get all users with pagination"""
    try:
        return await get_all_users(skip, limit)
    except Exception as e:
        print(f"Error in /admin/users: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/lawyers/pending")
async def get_pending():
    """Get pending lawyer approvals"""
    try:
        return await get_pending_lawyers()
    except Exception as e:
        print(f"Error in /admin/lawyers/pending: {str(e)}")
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
        print(f"Error in /admin/lawyers/approval: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.delete("/users/{user_id}")
async def remove_user(user_id: str):
    """Delete a user"""
    try:
        return await delete_user(user_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        print(f"Error in /admin/users delete: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/register")
async def register_new_admin(request: AdminCreateRequest):
    """Register a new administrator"""
    try:
        return await register_admin(request)
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in /admin/register: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/admins")
async def get_admins():
    """Get all administrators"""
    try:
        return await get_all_admins()
    except Exception as e:
        print(f"Error in /admin/admins: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.delete("/admins/{admin_id}")
async def remove_admin(admin_id: str):
    """Delete an administrator"""
    try:
        return await delete_admin(admin_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        print(f"Error in /admin/admins delete: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@router.put("/profile/{admin_id}")
async def update_profile(admin_id: str, data: dict):
    """Update administrator profile"""
    try:
        return await update_admin_profile(admin_id, data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/change-password/{admin_id}")
async def change_password(admin_id: str, data: dict):
    """Change administrator password"""
    try:
        return await change_admin_password(admin_id, data.get("current_password"), data.get("new_password"))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/settings")
async def get_settings():
    """Get global platform settings"""
    try:
        return await get_platform_settings()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/settings")
async def update_settings(data: dict):
    """Update global platform settings"""
    try:
        return await update_platform_settings(data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/preferences/{admin_id}")
async def get_preferences(admin_id: str):
    """Get admin preferences"""
    try:
        return await get_admin_preferences(admin_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/preferences/{admin_id}")
async def update_preferences(admin_id: str, data: dict):
    """Update admin preferences"""
    try:
        return await update_admin_preferences(admin_id, data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/finance/stats")
async def get_finance_stats(period: str = Query("daily")):
    """Get platform financial statistics with period support"""
    try:
        return await get_financial_stats(period)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/analytics")
async def get_analytics(period: str = Query("daily")):
    """Get detailed user interaction and message analytics"""
    try:
        return await get_user_analytics(period)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
