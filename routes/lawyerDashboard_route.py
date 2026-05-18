from fastapi import APIRouter, Body, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from controllers.lawyerDashboard_Controller import (
    add_availability_slot,
    create_lawyer_case,
    delete_availability_slot,
    delete_lawyer_case,
    finalize_appointment_booking,
    get_all_lawyer_appointments,
    get_lawyer_analytics,
    get_lawyer_appointments,
    get_lawyer_bookings,
    get_lawyer_cases,
    get_lawyer_clients,
    get_lawyer_dashboard_stats,
    get_lawyer_documents,
    get_lawyer_profile_settings,
    get_slot_by_id,
    update_appointment_status,
    update_lawyer_case,
    update_lawyer_profile,
    upload_lawyer_document,
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

@router.post("/{lawyer_id}/documents/upload")
async def upload_lawyer_document_route(
    lawyer_id: str,
    file: UploadFile = File(...),
    note: str = Form(default=""),
    folder: str = Form(default="")
):
    try:
        result = await upload_lawyer_document(lawyer_id, file, note, folder)
        return JSONResponse(status_code=200, content=result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{lawyer_id}/bookings")
async def get_lawyer_bookings_route(lawyer_id: str, type: str = "list", clientEmail: str = None, lawyerId: str = None, period: str = "this-month"):
    try:
        # If lawyer_id in path is "dashboard", it means the ID was likely passed as a query param 'lawyerId'
        # This fix is for compatibility with the frontend proxy call: /lawyer/dashboard/bookings?lawyerId=...
        target_id = lawyerId if (lawyer_id == "dashboard" and lawyerId) else lawyer_id

        if type == "stats":
            result = await get_lawyer_dashboard_stats(target_id)
            return JSONResponse(status_code=200, content={"success": True, "stats": result})
        elif type == "analytics":
            result = await get_lawyer_analytics(target_id, period)
            return JSONResponse(status_code=200, content=result)
        else:
            bookings = await get_lawyer_bookings(target_id, clientEmail)
            return JSONResponse(status_code=200, content={"success": True, "bookings": bookings})
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

@router.post("/appointment/finalize")
async def finalize_booking_route(data: dict):
    try:
        slot_id = data.get("slot_id")
        payment_details = data.get("payment_details")

        if not slot_id or not payment_details:
             raise HTTPException(status_code=400, detail="slot_id and payment_details are required")

        result = await finalize_appointment_booking(slot_id, payment_details)
        if not result["success"]:
            raise HTTPException(status_code=400, detail=result["message"])

        return JSONResponse(status_code=200, content=result)
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

# --- Case Management Routes ---

@router.get("/{lawyer_id}/cases")
async def get_cases_route(lawyer_id: str):
    try:
        cases = await get_lawyer_cases(lawyer_id)
        return JSONResponse(status_code=200, content={"success": True, "cases": cases})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{lawyer_id}/cases")
async def create_case_route(lawyer_id: str, case_data: dict = Body(...)):
    try:
        result = await create_lawyer_case(lawyer_id, case_data)
        return JSONResponse(status_code=201, content=result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/case/{case_id}")
async def delete_case_route(case_id: str):
    try:
        success = await delete_lawyer_case(case_id)
        if not success:
            raise HTTPException(status_code=404, detail="Case not found")
        return JSONResponse(status_code=200, content={"success": True, "message": "Case deleted"})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.patch("/case/{case_id}")
async def update_case_route(case_id: str, update_data: dict = Body(...)):
    try:
        success = await update_lawyer_case(case_id, update_data)
        if not success:
            raise HTTPException(status_code=404, detail="Case not found or no changes made")
        return JSONResponse(status_code=200, content={"success": True, "message": "Case updated successfully"})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
