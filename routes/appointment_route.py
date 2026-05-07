from datetime import UTC, datetime
from typing import Any, Literal, Optional

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from config.cognilex_db import get_database

router = APIRouter(prefix="/api/appointments", tags=["Appointments"])


class AppointmentCreate(BaseModel):
    lawyer_id: str
    client_id: str
    date: str
    time: str
    appointment_type: str
    notes: Optional[str] = None


class AppointmentUpdate(BaseModel):
    action: Literal["accept", "reject", "reschedule"]
    new_date: Optional[str] = None
    new_time: Optional[str] = None
    reason: Optional[str] = None


def parse_object_id(value: str, field_name: str) -> ObjectId:
    try:
        return ObjectId(value)
    except (InvalidId, TypeError):
        raise HTTPException(status_code=400, detail=f"Invalid {field_name}")


@router.post("/create")
def create_appointment(data: AppointmentCreate, db=Depends(get_database)):
    lawyer_id = parse_object_id(data.lawyer_id, "lawyer_id")
    client_id = parse_object_id(data.client_id, "client_id")

    new_appt = {
        "lawyer_id": lawyer_id,
        "client_id": client_id,
        "date": data.date,
        "time": data.time,
        "type": data.appointment_type,
        "status": "pending_payment",
        "notes": data.notes,
        "paid": False,
        "createdAt": datetime.now(UTC),
        "updatedAt": datetime.now(UTC),
    }

    result = db["appointments"].insert_one(new_appt)
    return {
        "success": True,
        "id": str(result.inserted_id),
        "message": "Appointment initiated. Waiting for payment.",
    }


@router.get("/lawyer/{lawyer_id}")
def get_lawyer_appointments(lawyer_id: str, db=Depends(get_database)):
    lawyer_object_id = parse_object_id(lawyer_id, "lawyer_id")
    cursor = db["appointments"].find({"lawyer_id": lawyer_object_id})

    appointments = []
    for doc in cursor:
        doc["_id"] = str(doc["_id"])
        doc["lawyer_id"] = str(doc["lawyer_id"])
        doc["client_id"] = str(doc["client_id"])
        appointments.append(doc)

    return appointments


@router.patch("/{appointment_id}/manage")
def manage_appointment(appointment_id: str, data: AppointmentUpdate, db=Depends(get_database)):
    appointment_object_id = parse_object_id(appointment_id, "appointment_id")
    appointment = db["appointments"].find_one({"_id": appointment_object_id})

    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")

    update_data: dict[str, Any] = {"updatedAt": datetime.now(UTC)}

    if data.action == "reschedule":
        if not data.new_date or not data.new_time:
            raise HTTPException(status_code=400, detail="new_date and new_time are required for reschedule")
        update_data.update(
            {
                "status": "rescheduled",
                "date": data.new_date,
                "time": data.new_time,
                "reschedule_reason": data.reason,
            }
        )
    elif data.action == "reject":
        update_data.update({"status": "cancelled", "cancel_reason": data.reason})
    else:
        update_data.update({"status": "confirmed"})

    db["appointments"].update_one({"_id": appointment_object_id}, {"$set": update_data})

    action_message = {"accept": "accepted", "reject": "rejected", "reschedule": "rescheduled"}
    return {"success": True, "message": f"Appointment {action_message[data.action]} successfully"}


@router.patch("/{appointment_id}/pay-success")
def mark_as_paid(appointment_id: str, db=Depends(get_database)):
    appointment_object_id = parse_object_id(appointment_id, "appointment_id")
    result = db["appointments"].update_one(
        {"_id": appointment_object_id},
        {"$set": {"status": "confirmed", "paid": True, "updatedAt": datetime.now(UTC)}},
    )

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Appointment not found")

    return {"success": True, "message": "Payment verified and appointment confirmed."}


@router.get("/client")
def get_client_appointments(email: str, db=Depends(get_database)):
    # Find user by email to get their _id
    user = db["users"].find_one({"email": email})
    user_id = user["_id"] if user else None

    # Find appointments that belong to this client
    query = {
        "status": {"$nin": ["available", "pending_payment"]},
        "$or": [
            {"email": email},
            {"clientEmail": email},
            {"client_email": email}
        ]
    }
    
    if user_id:
        query["$or"].extend([
            {"client_id": user_id},
            {"client_id": str(user_id)}
        ])

    cursor = db["appointments"].find(query).sort([("date", -1)])
    
    appointments = []
    count = 0
    for doc in cursor:
        count += 1
        # Fetch lawyer details
        lawyer = None
        if "lawyer_id" in doc:
            lawyer = db["lawyers"].find_one({"_id": doc["lawyer_id"]})
            
        # Map status to frontend status
        raw_status = doc.get("status", "pending")
        display_status = "Pending"
        if raw_status == "booked":
            display_status = "Confirmed"
        elif raw_status == "canceled":
            display_status = "Canceled"
        elif raw_status == "completed":
            display_status = "Completed"
            
        appointments.append({
            "id": str(doc["_id"]),
            "lawyerName": lawyer.get("fullName", "Unknown Lawyer") if lawyer else "Unknown Lawyer",
            "lawyerImage": lawyer.get("profilePhotoUrl", "") if lawyer else "",
            "type": doc.get("type", doc.get("appointment_type", "Consultation")),
            "date": doc.get("date"),
            "time": doc.get("time"),
            "location": doc.get("location", "Virtual Consultation"),
            "status": display_status
        })
        
    print(f"[Backend] Fetched {count} appointments for client: {email}")
    return {"success": True, "appointments": appointments}