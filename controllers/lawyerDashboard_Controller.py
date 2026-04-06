from datetime import datetime
from bson import ObjectId
from bson.errors import InvalidId
from fastapi import HTTPException, status

from config.cognilex_db import get_database


async def resolve_lawyer_id(db, input_id: str) -> ObjectId:
    """
    Resolve a User ID to a Lawyer Profile ID.
    Lawyers log in as Users, but their profile data is in the 'lawyers' collection.
    """
    try:
        obj_id = ObjectId(input_id)
    except:
        return input_id


    lawyer = db["lawyers"].find_one({"_id": obj_id})
    if lawyer:
        return obj_id

    # Check if it's a User ID, then find corresponding Lawyer by email
    user = db["users"].find_one({"_id": obj_id})
    if user and user.get("email"):
        lawyer = db["lawyers"].find_one({"email": user["email"].lower()})
        if lawyer:
            return lawyer["_id"]

    return obj_id

async def get_lawyer_dashboard_stats(lawyer_id: str) -> dict:

    db = get_database()
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database connection not available",
        )

    # Resolve the true Lawyer Profile ID
    lawyer_obj_id = await resolve_lawyer_id(db, lawyer_id)

    lawyer = db["lawyers"].find_one({"_id": lawyer_obj_id})
    if not lawyer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lawyer not found",
        )

    appointments = db["appointments"]
    cases = db["cases"]

    # --- Real-time Stats ---
    total_bookings = appointments.count_documents({"lawyer_id": lawyer_obj_id})

    pending_requests = appointments.count_documents({"lawyer_id": lawyer_obj_id, "status": "pending"})

    active_case_clients = cases.distinct("clientId", {"lawyer_id": lawyer_obj_id, "status": "active"})
    active_clients_count = len(active_case_clients)

    completed_appointments = list(appointments.find({"lawyer_id": lawyer_obj_id, "status": "completed"}))
    total_earnings = sum(float(app.get("consultationFee", 0) or 0) for app in completed_appointments)

    profile_views = int(lawyer.get("profileViews", 2408)) # Default from frontend mockup

    return {
        "stats": {
            "totalBookings": total_bookings,
            "profileViews": profile_views,
            "pendingRequests": pending_requests,
            "activeClients": active_clients_count,
            "totalEarnings": total_earnings,
            "activeCases": cases.count_documents({"lawyerId": lawyer_id, "status": "active"})
        }
    }

async def get_lawyer_appointments(lawyer_id: str) -> list:
    """Return timeline slots for the lawyer dashboard, checking multiple ID formats."""
    db = get_database()
    if db is None:
        return []

    # Resolve the true Lawyer Profile ID (in case lawyer_id is a User ID)
    lawyer_obj_id = await resolve_lawyer_id(db, lawyer_id)

    query = {"lawyer_id": lawyer_obj_id}

    cursor = db["appointments"].find(query).sort("date", 1).limit(50)
    
    slots = []
    for doc in cursor:
        slots.append({
            "id": str(doc["_id"]),
            "date": doc.get("date"),
            "time": doc.get("time"),
            "location": doc.get("location", "Office"),
            "isBooked": doc.get("status") not in ["available", "pending_payment"],
            "clientName": doc.get("clientName", "Legal Client") if doc.get("status") != "available" else "Open Slot",
            "type": doc.get("type", doc.get("appointment_type", "Consultation"))
        })
    
    return slots

async def get_all_lawyer_appointments(lawyer_id: str, status_filter: str = None) -> list:
    """Return all appointments for a lawyer with filtering."""
    db = get_database()
    if db is None:
        return []

    try:
        lawyer_obj_id = ObjectId(lawyer_id)
    except:
        lawyer_obj_id = lawyer_id

    query = {"lawyer_id": lawyer_obj_id}
    if status_filter and status_filter != "all":
        query["status"] = status_filter
    
    cursor = db["appointments"].find(query).sort("date", -1)
    appointments = []
    for doc in cursor:
        appointments.append({
            "id": str(doc["_id"]),
            "clientName": doc.get("clientName", "Legal Client"),
            "type": doc.get("appointment_type", "Consultation"),
            "date": doc.get("date"),
            "time": doc.get("time"),
            "location": doc.get("location", "Virtual Consultation"),
            "status": doc.get("status", "pending")
        })
    return appointments

async def update_appointment_status(appointment_id: str, new_status: str):
    """Update the status of a specific appointment."""
    db = get_database()
    if db is None:
        return {"success": False}
    
    db["appointments"].update_one(
        {"_id": ObjectId(appointment_id)},
        {"$set": {"status": new_status}}
    )
    return {"success": True}

async def get_lawyer_clients(lawyer_id: str) -> list:
    """Return unique clients who have booked with the lawyer."""
    db = get_database()
    if db is None:
        return []

    try:
        lawyer_obj_id = ObjectId(lawyer_id)
    except:
        lawyer_obj_id = lawyer_id

    # Get distinct client emails/ids from appointments
    client_emails = db["appointments"].distinct("email", {"lawyer_id": lawyer_obj_id})
    
    clients = []
    for email in client_emails:
        user = db["users"].find_one({"email": email})
        if user:

            last_app = db["appointments"].find_one({"email": email, "lawyer_id": lawyer_obj_id}, sort=[("date", -1)])
            clients.append({
                "id": str(user["_id"]),
                "name": user.get("name", "User"),
                "email": user.get("email"),
                "phone": user.get("phone", "+94 7X XXX XXXX"),
                "activeCases": db["cases"].count_documents({"email": email, "lawyer_id": lawyer_obj_id, "status": "active"}),
                "status": "Active" if last_app else "Inactive"
            })
    return clients

async def get_lawyer_documents(lawyer_id: str) -> list:
    db = get_database()
    if db is None:
        return []

    try:
        lawyer_obj_id = ObjectId(lawyer_id)
    except:
        lawyer_obj_id = lawyer_id

    cursor = db["documents"].find({"lawyer_id": lawyer_obj_id}).sort("created_at", -1)
    documents = []
    for doc in cursor:
        documents.append({
            "id": str(doc["_id"]),
            "name": doc.get("name", "Unnamed Document"),
            "type": doc.get("type", "File"),
            "date": doc.get("created_at").strftime("%b %d, %Y") if doc.get("created_at") else "N/A",
            "size": doc.get("size", "0 KB"),
            "url": doc.get("url")
        })
    return documents

async def add_availability_slot(lawyer_id: str, date: str, time: str, location: str = "Office", appointment_type: str = "Consultation") -> dict:
    db = get_database()
    if db is None:
        return {"success": False}

    # Resolve the true Lawyer Profile ID (in case lawyer_id is a User ID)
    lawyer_obj_id = await resolve_lawyer_id(db, lawyer_id)

    slot = {
        "lawyer_id": lawyer_obj_id,
        "date": date,
        "time": time,
        "type": appointment_type,
        "status": "available",
        "location": location,
        "created_at": datetime.utcnow()
    }
    
    result = db["appointments"].insert_one(slot)
    return {"success": True, "slot_id": str(result.inserted_id)}

async def delete_availability_slot(slot_id: str) -> dict:
    db = get_database()
    if db is None:
        return {"success": False}

    # Only delete if status is 'available' to prevent deleting active bookings
    result = db["appointments"].delete_one({"_id": ObjectId(slot_id), "status": "available"})
    if result.deleted_count > 0:
        return {"success": True}
    return {"success": False, "message": "Slot is already booked or not found."}
