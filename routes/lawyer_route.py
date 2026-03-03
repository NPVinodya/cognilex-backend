from fastapi import APIRouter, File, UploadFile, Form, HTTPException, Body
from fastapi.responses import JSONResponse
from typing import List, Optional
import json
from bson import ObjectId
from datetime import datetime
from config.cognilex_db import get_database

from controllers.lawyer_Controller import (
    register_lawyer,
    get_all_lawyers,
    get_lawyer_by_id,
    approve_lawyer,
    reject_lawyer,
    get_pending_lawyers
)

router = APIRouter(prefix="/lawyer", tags=["Lawyer"])


# --- පවතින නීතිඥ ලියාපදිංචි කිරීමේ මාවත (Registration) ---
@router.post("/register")
async def register_lawyer_route(
        fullName: str = Form(...),
        email: str = Form(...),
        phone: str = Form(...),
        address: str = Form(...),
        city: str = Form(...),
        province: str = Form(...),
        nicNumber: str = Form(...),
        lawyerId: str = Form(...),
        barCouncilNumber: str = Form(...),
        specialization: str = Form(...),
        yearsOfExperience: str = Form(...),
        lawFirm: str = Form(""),
        languagesSpoken: str = Form(...),
        lawSchool: str = Form(...),
        graduationYear: str = Form(...),
        additionalQualifications: str = Form(""),
        practiceAreas: str = Form(...),
        consultationFee: str = Form(...),
        availability: str = Form(...),
        bio: str = Form(...),
        profilePhoto: UploadFile = File(...),
        nicFrontPhoto: UploadFile = File(...),
        nicBackPhoto: UploadFile = File(...),
        lawyerIdPhoto: UploadFile = File(...)
):
    try:
        allowed_types = ["image/jpeg", "image/jpg", "image/png", "image/webp"]
        files_to_check = [profilePhoto, nicFrontPhoto, nicBackPhoto, lawyerIdPhoto]

        for file in files_to_check:
            if file.content_type not in allowed_types:
                raise HTTPException(status_code=400, detail=f"Invalid file type: {file.filename}")

            file.file.seek(0, 2)
            file_size = file.file.tell()
            file.file.seek(0)
            if file_size > 5 * 1024 * 1024:
                raise HTTPException(status_code=400, detail=f"File {file.filename} is too large")

        try:
            practice_areas_list = json.loads(practiceAreas)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid practice areas format")

        lawyer_data = {
            "fullName": fullName,
            "email": email.lower(),
            "phone": phone,
            "address": address,
            "city": city,
            "province": province,
            "nicNumber": nicNumber,
            "lawyerId": lawyerId,
            "barCouncilNumber": barCouncilNumber,
            "specialization": specialization,
            "yearsOfExperience": int(yearsOfExperience),
            "lawFirm": lawFirm if lawFirm else "Independent Practice",
            "languagesSpoken": languagesSpoken,
            "lawSchool": lawSchool,
            "graduationYear": int(graduationYear),
            "additionalQualifications": additionalQualifications,
            "practiceAreas": practice_areas_list,
            "consultationFee": float(consultationFee),
            "availability": availability,
            "bio": bio,
        }

        files = {
            "profilePhoto": profilePhoto,
            "nicFrontPhoto": nicFrontPhoto,
            "nicBackPhoto": nicBackPhoto,
            "lawyerIdPhoto": lawyerIdPhoto
        }

        result = await register_lawyer(lawyer_data, files)
        return JSONResponse(status_code=201, content={"success": True, "lawyer_id": result})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# --- නීතිඥ ලැයිස්තු ලබා ගැනීම ---
@router.get("/all")
async def get_lawyers_route(province: Optional[str] = None, specialization: Optional[str] = None,
                            status: str = "approved"):
    lawyers = await get_all_lawyers(province, specialization, status)
    return JSONResponse(status_code=200, content={"success": True, "count": len(lawyers), "lawyers": lawyers})


@router.get("/pending")
async def get_pending_lawyers_route():
    lawyers = await get_pending_lawyers()
    return JSONResponse(status_code=200, content={"success": True, "count": len(lawyers), "lawyers": lawyers})


@router.get("/{lawyer_id}")
async def get_lawyer_route(lawyer_id: str):
    lawyer = await get_lawyer_by_id(lawyer_id)
    if not lawyer:
        raise HTTPException(status_code=404, detail="Lawyer not found")
    return JSONResponse(status_code=200, content={"success": True, "lawyer": lawyer})


# --- Admin අනුමත කිරීම් ---
@router.post("/{lawyer_id}/approve")
async def approve_lawyer_route(lawyer_id: str):
    result = await approve_lawyer(lawyer_id)
    return JSONResponse(status_code=200, content={"success": True, "message": "Approved"})


@router.post("/{lawyer_id}/reject")
async def reject_lawyer_route(lawyer_id: str, reason: str = Form(...)):
    result = await reject_lawyer(lawyer_id, reason)
    return JSONResponse(status_code=200, content={"success": True, "message": "Rejected"})


# --- 🚀 නව විශේෂාංග: නීතිඥයාට තම වැඩ කරන වේලාවන් (Availability) යාවත්කාලීන කිරීමට ---
@router.put("/{lawyer_id}/availability")
async def update_availability(lawyer_id: str, data: dict = Body(...)):
    """ නීතිඥයාට තමාට හැකි වේලාවන් (Availability) Dashboard එකෙන් වෙනස් කිරීමට මෙය අවශ්‍ය වේ """
    try:
        db = get_database()
        availability = data.get("availability")

        db["availability"].update_one(
            {"lawyerId": lawyer_id},
            {"$set": {"slots": availability, "lastUpdated": datetime.utcnow()}},
            upsert=True
        )
        return JSONResponse(status_code=200, content={"success": True, "message": "Availability updated"})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# --- 📅 නව විශේෂාංග: පාරිභෝගික පත්වීම් (Appointments) කළමනාකරණය ---
@router.patch("/{lawyer_id}/appointments/{appointment_id}/manage")
async def manage_appointment(
        lawyer_id: str,
        appointment_id: str,
        action: str = Form(...),  # "accept", "reject", "reschedule"
        new_date: Optional[str] = Form(None),
        reason: Optional[str] = Form(None)
):
    """ නීතිඥයාට තම පවතින පත්වීම් පිළිගැනීමට හෝ වෙනත් දිනකට මාරු කිරීමට මෙය භාවිතා වේ """
    try:
        db = get_database()
        update_data = {"updatedAt": datetime.utcnow()}

        if action == "reschedule" and new_date:
            update_data.update({"status": "rescheduled", "date": new_date, "reschedule_reason": reason})
        elif action == "reject":
            update_data.update({"status": "cancelled", "cancel_reason": reason})
        else:
            update_data.update({"status": "confirmed"})

        result = db["appointments"].update_one(
            {"_id": ObjectId(appointment_id), "lawyerId": lawyer_id},
            {"$set": update_data}
        )

        if result.modified_count == 0:
            raise HTTPException(status_code=404, detail="Appointment not found or unauthorized")

        return JSONResponse(status_code=200, content={"success": True, "message": f"Appointment {action}ed"})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))