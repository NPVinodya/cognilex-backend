from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from controllers.lawyerDashboard_Controller import (
    get_lawyer_dashboard_stats, 
    get_lawyer_appointments,
    get_all_lawyer_appointments,
    update_appointment_status,
    get_lawyer_clients,
    get_lawyer_documents,
    add_availability_slot,
    delete_availability_slot,
    get_slot_by_id,
    get_lawyer_profile_settings,
    update_lawyer_profile
)

from controllers.user_controller import UserController
from models.user import UpdatePasswordRequest

router = APIRouter(prefix="/lawyer-dashboard", tags=["Lawyer Dashboard"])

@router.get("/{lawyer_id}/stats")
async def get_dashboard_stats_route(lawyer_id: str):
    try:
        stats = await get_lawyer_dashboard_stats(lawyer_id)
        return JSONResponse(status_code=200, content={"success": True, "stats": stats})
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{lawyer_id}/appointments")
async def get_dashboard_appointments_route(lawyer_id: str):
    try:
        slots = await get_lawyer_appointments(lawyer_id)
        return JSONResponse(status_code=200, content={"success": True, "slots": slots})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{lawyer_id}/all-appointments")
async def get_all_appointments_route(lawyer_id: str, status: str = "all"):
    try:
        appointments = await get_all_lawyer_appointments(lawyer_id, status)
        return JSONResponse(status_code=200, content={"success": True, "appointments": appointments})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.patch("/appointment/{appointment_id}/status")
async def update_status_route(appointment_id: str, new_status: str):
    try:
        result = await update_appointment_status(appointment_id, new_status)
        return JSONResponse(status_code=200, content=result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{lawyer_id}/clients")
async def get_lawyer_clients_route(lawyer_id: str):
    try:
        clients = await get_lawyer_clients(lawyer_id)
        return JSONResponse(status_code=200, content={"success": True, "clients": clients})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{lawyer_id}/documents")
async def get_lawyer_documents_route(lawyer_id: str):
    try:
        documents = await get_lawyer_documents(lawyer_id)
        return JSONResponse(status_code=200, content={"success": True, "documents": documents})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/slot")
async def add_slot_route(lawyer_id: str, date: str, time: str, location: str = "Office", type: str = "Consultation"):
    try:
        result = await add_availability_slot(lawyer_id, date, time, location, type)
        return JSONResponse(status_code=200, content=result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/slot/{slot_id}")
async def delete_slot_route(slot_id: str):
    try:
        result = await delete_availability_slot(slot_id)
        return JSONResponse(status_code=200, content=result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/slot/{slot_id}")
async def get_slot_route(slot_id: str):
    try:
        slot = await get_slot_by_id(slot_id)
        if not slot:
            raise HTTPException(status_code=404, detail="Slot not found")
        return JSONResponse(status_code=200, content={"success": True, "slot": slot})
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- Settings & Profile Routes ---

@router.get("/{lawyer_id}/profile")
async def get_profile_route(lawyer_id: str):
    try:
        result = await get_lawyer_profile_settings(lawyer_id)
        return JSONResponse(status_code=200, content=result)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.patch("/{lawyer_id}/profile")
async def update_profile_route(lawyer_id: str, update_data: dict):
    try:
        result = await update_lawyer_profile(lawyer_id, update_data)
        return JSONResponse(status_code=200, content=result)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/password/update")
async def update_password_route(data: UpdatePasswordRequest):
    try:
        result = UserController.update_user_password(data)
        return JSONResponse(status_code=200, content=result)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
