from datetime import datetime
from bson import ObjectId
from bson.errors import InvalidId
from fastapi import HTTPException, status

from config.cognilex_db import get_database


def get_30_min_chunks(time_range: str) -> list:
    """
    Split a time range like '09:00 AM - 11:00 AM' or '09.00 AM - 11.00 AM' into 30-min chunks.
    Example: ['09:00 AM - 09:30 AM', '09:30 AM - 10:00 AM', ...]
    """
    try:
        # Normalize the time string (e.g. 09.00 -> 09:00)
        t_range = time_range.replace(".", ":")
        
        # Robust dash splitting (handle ' - ' or '-')
        if " - " in t_range:
            parts = [x.strip() for x in t_range.split(" - ")]
        elif "-" in t_range:
            parts = [x.strip() for x in t_range.split("-")]
        else:
            return [time_range]

        if len(parts) != 2:
            return [time_range]

        start_str, end_str = parts
        
        # Determine the format based on the presence of ':'
        fmt = "%I:%M %p"
        
        start_time = datetime.strptime(start_str, fmt)
        end_time = datetime.strptime(end_str, fmt)

        chunks = []
        current = start_time
        import datetime as dt_lib

        while current < end_time:
            next_t = current + dt_lib.timedelta(minutes=30)
            if next_t > end_time:
                break
            chunks.append(f"{current.strftime('%I:%M %p')} - {next_t.strftime('%I:%M %p')}")
            current = next_t
        return chunks
    except Exception as e:
        print(f"Error splitting time '{time_range}': {e}")
        return [time_range]


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

    appointments_col = db["appointments"]
    cases_col = db["cases"]
    bookings_col = db["bookings"]

    # --- Real-time Stats from Bookings and Appointments ---
    # We check for both String and ObjectId just in case, to be 100% sure we find the data
    query_filter = {"$or": [{"lawyer_id": lawyer_obj_id}, {"lawyer_id": lawyer_id}]}
    
    # 1. Total Bookings (from bookings collection)
    total_bookings = bookings_col.count_documents(query_filter)

    # 2. Total Earnings (sum of amount from bookings collection)
    earnings_pipeline = [
        {"$match": query_filter},
        {"$group": {"_id": None, "total": {"$sum": "$amount"}}}
    ]
    earnings_result = list(bookings_col.aggregate(earnings_pipeline))
    total_earnings = earnings_result[0]["total"] if earnings_result else 0.0

    # 3. Pending Requests (from appointments collection)
    pending_filter = {"$or": [{"lawyer_id": lawyer_obj_id, "status": "pending"}, {"lawyer_id": lawyer_id, "status": "pending"}]}
    pending_requests = appointments_col.count_documents(pending_filter)

    # 4. Active Clients (unique clients in bookings)
    active_clients = len(bookings_col.distinct("client_email", query_filter))

    # 5. Today's Data
    today_str = datetime.utcnow().strftime("%Y-%m-%d")
    today_filter = {"$or": [{"lawyer_id": lawyer_obj_id, "date": today_str}, {"lawyer_id": lawyer_id, "date": today_str}]}
    today_bookings = appointments_col.count_documents({**today_filter, "status": "booked"})
    today_slots = appointments_col.count_documents(today_filter)

    profile_views = int(lawyer.get("profileViews", 2408))
    
    # Calculate Platform Fees and Net Earnings (Fixed LKR 200 per booking)
    # We cast amount to float during aggregation to ensure accuracy
    earnings_pipeline = [
        {"$match": query_filter},
        {"$group": {"_id": None, "total": {"$sum": {"$toDouble": "$amount"}}}}
    ]
    earnings_result = list(bookings_col.aggregate(earnings_pipeline))
    total_earnings = earnings_result[0]["total"] if earnings_result else 0.0

    platform_fees = total_bookings * 200.0
    net_earnings = total_earnings - platform_fees

    # 6. Total & Unread Messages (from user_messages collection)
    messages_filter = {"$or": [{"lawyer_id": str(lawyer_obj_id)}, {"lawyer_id": lawyer_id}]}
    total_messages = db["user_messages"].count_documents(messages_filter)
    unread_messages = db["user_messages"].count_documents({
        "$and": [
            messages_filter,
            {"sender_role": "user"},
            {"is_read": {"$ne": True}},
            {"content": {"$exists": True, "$ne": ""}}
        ]
    })

    # Return keys DIRECTLY as the route wraps this in a 'stats' key
    return {
        "totalBookings": total_bookings,
        "todayBookings": today_bookings,
        "todaySlots": today_slots,
        "profileViews": profile_views,
        "pendingRequests": pending_requests,
        "activeClients": active_clients,
        "totalEarnings": total_earnings, # Gross
        "netEarnings": net_earnings,
        "platformFees": platform_fees,
        "totalMessages": total_messages,
        "unreadMessages": unread_messages,
        "activeCases": cases_col.count_documents({"$or": [{"lawyerId": lawyer_id, "status": "active"}, {"lawyer_id": lawyer_obj_id, "status": "active"}]})
    }

async def get_lawyer_analytics(lawyer_id: str, period: str = "this-month") -> dict:
    """Aggregate monthly data for revenue and service distribution."""
    db = get_database()
    if db is None:
        return {"success": False}

    # Resolve the true Lawyer Profile ID
    lawyer_obj_id = await resolve_lawyer_id(db, lawyer_id)
    
    bookings_col = db["bookings"]
    # Be extremely flexible with ID field names (some might use lawyerId, others lawyer_id)
    query_filter = {
        "$or": [
            {"lawyer_id": lawyer_obj_id}, 
            {"lawyer_id": lawyer_id},
            {"lawyerId": lawyer_id},
            {"lawyerId": lawyer_obj_id}
        ]
    }
    
    # Debug: Check if ANY bookings exist for this lawyer
    total_in_db = bookings_col.count_documents(query_filter)
    print(f"[Analytics Debug] Total bookings in DB for lawyer {lawyer_id}: {total_in_db}")

    # Aggregate by Month
    from datetime import datetime, timedelta
    now = datetime.utcnow()
    
    start_date = None
    end_date = None
    
    if period == "year":
        # Start of the current year
        start_date = datetime(now.year, 1, 1)
        print(f"[Analytics Debug] Filtering for Current Year since {start_date}")
    elif period == "this-month":
        # Start of current month
        start_date = datetime(now.year, now.month, 1)
        print(f"[Analytics Debug] Filtering for This Month since {start_date}")
    elif period == "last-month":
        # Start and End of last month
        first_of_this_month = datetime(now.year, now.month, 1)
        last_month_dt = first_of_this_month - timedelta(days=1)
        start_date = datetime(last_month_dt.year, last_month_dt.month, 1)
        end_date = first_of_this_month
        print(f"[Analytics Debug] Filtering for Last Month: {start_date} to {end_date}")
    else:
        # Default fallback to This Month
        start_date = datetime(now.year, now.month, 1)
        print(f"[Analytics Debug] Filtering for Default (This Month) since {start_date}")
    
    # Common date filter
    date_filter = {"safeDate": {"$gte": start_date}}
    if end_date:
        date_filter["safeDate"]["$lt"] = end_date

    # Monthly Revenue Pipeline
    monthly_pipeline = [
        {"$match": query_filter},
        # Safe Date Conversion Stage
        {"$addFields": {
            "safeDate": {"$convert": {"input": "$createdAt", "to": "date", "onError": now, "onNull": now}}
        }},
        {"$match": date_filter},
        {"$group": {
            "_id": {
                "month": {"$month": "$safeDate"}, 
                "year": {"$year": "$safeDate"}
            },
            "gross": {"$sum": {"$convert": {"input": "$amount", "to": "double", "onError": 0, "onNull": 0}}},
            "count": {"$sum": 1}
        }},
        {"$sort": {"_id.year": 1, "_id.month": 1}}
    ]
    
    monthly_results = list(bookings_col.aggregate(monthly_pipeline))
    print(f"[Analytics Debug] Monthly records found: {len(monthly_results)}")
    monthly_data = []
    
    for res in monthly_results:
        month_num = res["_id"]["month"]
        month_name = datetime(2026, month_num, 1).strftime("%b")
        count = res["count"]
        gross = res["gross"]
        fees = count * 200.0
        net = gross - fees
        
        monthly_data.append({
            "month": month_name,
            "gross": gross,
            "net": net,
            "fees": fees,
            "bookings": count
        })

    # Service Distribution (Aggregate by appointment type)
    # Be flexible with field names here too
    service_pipeline = [
        {"$match": query_filter},
        {"$lookup": {
            "from": "appointments",
            "localField": "appointment_id",
            "foreignField": "_id",
            "as": "appt"
        }},
        {"$unwind": {"path": "$appt", "preserveNullAndEmptyArrays": True}},
        {"$group": {
            "_id": {"$ifNull": ["$appt.type", {"$ifNull": ["$type", "General Consultation"]}]},
            "count": {"$sum": 1},
            "revenue": {"$sum": {"$convert": {"input": "$amount", "to": "double", "onError": 0, "onNull": 0}}}
        }}
    ]
    
    service_results = list(bookings_col.aggregate(service_pipeline))
    service_distribution = []
    for res in service_results:
        service_distribution.append({
            "name": res["_id"] or "Consultation",
            "value": res["count"],
            "revenue": res["revenue"]
        })

    return {
        "success": True,
        "monthly": monthly_data,
        "services": service_distribution
    }

async def get_lawyer_appointments(lawyer_id: str) -> list:
    """Return timeline slots for the lawyer dashboard, checking multiple ID formats."""
    db = get_database()
    if db is None:
        return []

    # Resolve the true Lawyer Profile ID (in case lawyer_id is a User ID)
    lawyer_obj_id = await resolve_lawyer_id(db, lawyer_id)
    
    today_str = datetime.utcnow().strftime("%Y-%m-%d")
    print(f"[Backend] Fetching appointments for Lawyer: {lawyer_id} (Resolved: {lawyer_obj_id}) | Date >= {today_str}")

    query = {
        "$or": [
            {"lawyer_id": lawyer_obj_id},
            {"lawyer_id": str(lawyer_obj_id)},
            {"lawyer_id": lawyer_id},
            {"lawyerId": lawyer_obj_id},
            {"lawyerId": str(lawyer_obj_id)},
            {"lawyerId": lawyer_id}
        ],
        "date": {"$gte": today_str}
    }

    # Sort by date and then time. 
    # Note: string sort for time isn't perfect for AM/PM but works for YYYY-MM-DD
    cursor = db["appointments"].find(query).sort([("date", 1), ("time", 1)]).limit(150)
    
    slots = []
    for doc in cursor:
        slots.append({
            "id": str(doc["_id"]),
            "date": doc.get("date"),
            "time": doc.get("time"),
            "location": doc.get("location", "Office"),
            "isBooked": doc.get("status") not in ["available", "pending_payment"],
            "clientName": doc.get("clientName", "Legal Client") if doc.get("status") != "available" else "Open Slot",
            "type": doc.get("type", doc.get("appointment_type", "Consultation")),
            "parent_range": doc.get("parent_range"),
            "status": doc.get("status", "available")
        })
    
    print(f"[Backend] Found {len(slots)} slots for lawyer {lawyer_id}")
    return slots


async def get_slot_by_id(slot_id: str) -> dict:
    """Retrieve details of a single appointment slot."""
    db = get_database()
    if db is None:
        return {}
    
    doc = db["appointments"].find_one({"_id": ObjectId(slot_id)})
    if not doc:
        return {}
        
    return {
        "id": str(doc["_id"]),
        "date": doc.get("date"),
        "time": doc.get("time"),
        "status": doc.get("status"),
        "lawyer_id": str(doc.get("lawyer_id")),
        "parent_range": doc.get("parent_range")
    }

async def get_all_lawyer_appointments(lawyer_id: str, status_filter: str = None) -> list:
    """Return all appointments for a lawyer with filtering."""
    db = get_database()
    if db is None:
        return []

    # Resolve the true Lawyer Profile ID
    lawyer_obj_id = await resolve_lawyer_id(db, lawyer_id)
    
    query_filter = {"$or": [{"lawyer_id": lawyer_obj_id}, {"lawyer_id": lawyer_id}]}
    if status_filter and status_filter != "all":
        today_str = datetime.utcnow().strftime("%Y-%m-%d")
        
        if status_filter == "upcoming":
            # Show future/today's slots that are booked, pending, or available
            query_filter["$and"] = [
                {"$or": [{"lawyer_id": lawyer_obj_id}, {"lawyer_id": lawyer_id}]},
                {"status": {"$in": ["booked", "pending", "available"]}},
                {"date": {"$gte": today_str}}
            ]
            # Clean up top-level $or since we moved it into $and
            if "$or" in query_filter: del query_filter["$or"]
            
        elif status_filter == "completed":
            # Show ALL past slots (< today) OR anything explicitly marked 'completed'
            query_filter["$and"] = [
                {"$or": [{"lawyer_id": lawyer_obj_id}, {"lawyer_id": lawyer_id}]},
                {"$or": [
                    {"status": "completed"},
                    {"date": {"$lt": today_str}}
                ]}
            ]
            if "$or" in query_filter: del query_filter["$or"]
        else:
            query_filter["status"] = status_filter
    
    cursor = db["appointments"].find(query_filter).sort("date", -1)
    appointments = []
    for doc in cursor:
        raw_status = doc.get("status", "pending")
        # Map backend status to frontend display status
        display_status = "Pending"
        if raw_status == "booked":
            display_status = "Confirmed"
        elif raw_status == "available":
            display_status = "Available"
        elif raw_status == "canceled":
            display_status = "Canceled"
        elif raw_status == "completed":
            display_status = "Completed"

        appointments.append({
            "id": str(doc["_id"]),
            "clientName": doc.get("clientName", "Legal Client") if raw_status not in ["available", "pending_payment"] else "Open Slot",
            "type": doc.get("type", "Consultation"),
            "date": doc.get("date"),
            "time": doc.get("time"),
            "location": doc.get("location", "Virtual Consultation"),
            "status": display_status,
            "isBooked": raw_status not in ["available", "pending_payment"]
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

async def finalize_appointment_booking(slot_id: str, payment_details: dict) -> dict:
    """
    Atomically lock a slot and create a confirmed booking record.
    Uses find_one_and_update to prevent race conditions (double booking).
    """
    db = get_database()
    if db is None:
        return {"success": False, "message": "Database error"}

    try:
        obj_id = ObjectId(slot_id)
    except Exception:
        return {"success": False, "message": "Invalid slot ID"}

    # Atomic Check & Lock
    # Only update IF status is 'available' or 'pending_payment'
    print(f"[Backend] Attempting to finalize slot: {slot_id}")
    
    current_slot = db["appointments"].find_one({"_id": obj_id})
    if current_slot:
        print(f"[Backend] Current slot status: {current_slot.get('status')}")
    else:
        print(f"[Backend] Error: Slot {slot_id} not found in DB")

    updated_slot = db["appointments"].find_one_and_update(
        {
            "_id": obj_id,
            "status": {"$in": ["available", "pending_payment"]}
        },
        {
            "$set": {
                "status": "booked",
                "paid": True,
                "paymentId": payment_details.get("payment_id"),
                "bookedAt": datetime.utcnow(),
                "clientName": payment_details.get("client_name"),
                "email": payment_details.get("client_email")
            }
        },
        return_document=True
    )

    if not updated_slot:
        print(f"[Backend] Finalization failed: Slot is not available or already booked.")
        # Check if it was already booked
        already_booked = db["appointments"].find_one({"_id": obj_id})
        if already_booked and already_booked.get("status") == "booked":
            return {"success": False, "message": "Slot already booked"}
        return {"success": False, "message": "Slot not found or unavailable"}

    print(f"[Backend] Successfully locked slot! Creating booking record...")

    # Create record in 'bookings' collection
    booking_record = {
        "appointment_id": obj_id,
        "lawyer_id": updated_slot.get("lawyer_id"),
        "client_name": payment_details.get("client_name"),
        "client_email": payment_details.get("client_email"),
        "client_phone": payment_details.get("client_phone"),
        "client_notes": payment_details.get("client_notes"),
        "amount": payment_details.get("amount"),
        "currency": payment_details.get("currency"),
        "payhere_payment_id": payment_details.get("payment_id"),
        "payment_status": "success",
        "createdAt": datetime.utcnow()
    }
    
    db["bookings"].insert_one(booking_record)

    return {"success": True, "message": "Slot locked and booking recorded successfully"}

async def get_lawyer_clients(lawyer_id: str) -> list:
    """Return unique clients from the bookings collection."""
    db = get_database()
    if db is None:
        return []

    # Resolve the true Lawyer Profile ID
    lawyer_obj_id = await resolve_lawyer_id(db, lawyer_id)
    
    print(f"[Clients Debug] Fetching clients for Lawyer ID: {lawyer_obj_id}")
    # Fetch from bookings collection to get Phone and Notes
    bookings_col = db["bookings"]
    query_filter = {"$or": [{"lawyer_id": lawyer_obj_id}, {"lawyer_id": lawyer_id}]}
    cursor = bookings_col.find(query_filter).sort("createdAt", -1)
    
    clients = []
    seen_emails = set()
    
    count = 0
    for doc in cursor:
        count += 1
        email = doc.get("client_email")
        if not email or email in seen_emails:
            continue
        seen_emails.add(email)
        
        clients.append({
            "id": str(doc["_id"]),
            "name": doc.get("client_name", "Legal Client"),
            "email": email,
            "phone": doc.get("client_phone", "N/A"),
            "notes": doc.get("client_notes", "No additional notes"),
            "status": "Active"
        })
    print(f"[Clients Debug] Found {count} records in bookings, returning {len(clients)} unique clients.")
    return clients

async def get_lawyer_bookings(lawyer_id: str, client_email: str = None) -> list:
    """Return all payment records from the bookings collection."""
    db = get_database()
    if db is None:
        return []

    # Resolve the true Lawyer Profile ID
    lawyer_obj_id = await resolve_lawyer_id(db, lawyer_id)

    query_filter = {"$or": [{"lawyer_id": lawyer_obj_id}, {"lawyer_id": lawyer_id}]}
    if client_email:
        query_filter["client_email"] = client_email
        
    cursor = db["bookings"].find(query_filter).sort("createdAt", -1)
    bookings = []
    
    for doc in cursor:
        # Fetch associated appointment details to get Date, Time, Location
        appt_id = doc.get("appointment_id")
        appt_details = {}
        if appt_id:
            appt = db["appointments"].find_one({"_id": ObjectId(appt_id)})
            if appt:
                appt_details = {
                    "date": appt.get("date"),
                    "time": appt.get("time"),
                    "location": appt.get("location", "Virtual Consultation"),
                    "service": appt.get("type", appt.get("appointment_type", "Legal Consultation"))
                }
        
        bookings.append({
            "id": str(doc["_id"]),
            "clientName": doc.get("client_name", "Client"),
            "clientEmail": doc.get("client_email", "N/A"),
            "service": appt_details.get("service", doc.get("service", "Legal Consultation")),
            "appointmentDate": appt_details.get("date", "N/A"),
            "appointmentTime": appt_details.get("time", "N/A"),
            "location": appt_details.get("location", "N/A"),
            "amount": doc.get("amount", 0),
            "currency": doc.get("currency", "LKR"),
            "paidDate": doc.get("createdAt").strftime("%Y-%m-%d %H:%M") if (doc.get("createdAt") and hasattr(doc.get("createdAt"), "strftime")) else "N/A",
            "status": doc.get("payment_status", "success")
        })
    return bookings

async def get_lawyer_documents(lawyer_id: str) -> list:
    db = get_database()
    if db is None:
        return []

    # Resolve the true Lawyer Profile ID
    lawyer_obj_id = await resolve_lawyer_id(db, lawyer_id)
    
    query_filter = {"$or": [{"lawyer_id": lawyer_obj_id}, {"lawyer_id": lawyer_id}]}
    cursor = db["documents"].find(query_filter).sort("created_at", -1)
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
        return {"success": False, "message": "Database error"}

    # Resolve the true Lawyer Profile ID
    lawyer_obj_id = await resolve_lawyer_id(db, lawyer_id)

    # Automatic 30-min session splitting
    time_chunks = get_30_min_chunks(time)
    
    if len(time_chunks) > 1:
        slots_to_insert = []
        for chunk in time_chunks:
            slots_to_insert.append({
                "lawyer_id": lawyer_obj_id,
                "date": date,
                "time": chunk,
                "parent_range": time, # Store range for grouping on frontend
                "type": appointment_type,
                "status": "available",
                "location": location,
                "created_at": datetime.utcnow()
            })
        db["appointments"].insert_many(slots_to_insert)
        return {"success": True, "message": f"Created {len(time_chunks)} sessions."}
    else:
        # Standard single slot
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

async def get_lawyer_profile_settings(lawyer_id: str) -> dict:
    """Fetch profile data specifically for the settings page."""
    db = get_database()
    if db is None:
        raise HTTPException(status_code=500, detail="Database connection not available")

    # Resolve the true Lawyer Profile ID (in case lawyer_id is a User ID)
    lawyer_obj_id = await resolve_lawyer_id(db, lawyer_id)
    
    lawyer = db["lawyers"].find_one({"_id": lawyer_obj_id})
    if not lawyer:
        raise HTTPException(status_code=404, detail="Lawyer profile not found")

    # Map to frontend settings shape
    return {
        "success": True,
        "profile": {
            "fullName": lawyer.get("fullName", ""),
            "email": lawyer.get("email", ""),
            "phone": lawyer.get("phone", ""),
            "bio": lawyer.get("bio", ""),
            "barCouncilNumber": lawyer.get("barCouncilNumber", ""),
            "yearsOfExperience": lawyer.get("yearsOfExperience", 0),
            "practiceAreas": lawyer.get("practiceAreas", []),
            "consultationFee": lawyer.get("consultationFee", 0),
            "province": lawyer.get("province", ""),
            "profilePhotoUrl": lawyer.get("profilePhotoUrl", ""),
            "location": lawyer.get("location", "Office")
        }
    }

async def update_lawyer_profile(lawyer_id: str, update_data: dict) -> dict:
    """Update lawyer profile information and sync with user collection if email changes."""
    db = get_database()
    if db is None:
        raise HTTPException(status_code=500, detail="Database connection not available")

    # Resolve the true Lawyer Profile ID
    lawyer_obj_id = await resolve_lawyer_id(db, lawyer_id)
    
    # Get current profile for email comparison
    current_profile = db["lawyers"].find_one({"_id": lawyer_obj_id})
    if not current_profile:
         raise HTTPException(status_code=404, detail="Lawyer profile not found")

    # 1. Update Lawyer collection
    # Only allow specific fields to be updated via this endpoint
    allowed_fields = [
        "fullName", "phone", "bio", "barCouncilNumber", 
        "yearsOfExperience", "practiceAreas", "consultationFee", 
        "province", "location", "email"
    ]
    
    clean_update = {k: v for k, v in update_data.items() if k in allowed_fields}
    
    if not clean_update:
        return {"success": False, "message": "No valid fields to update"}

    db["lawyers"].update_one(
        {"_id": lawyer_obj_id},
        {"$set": clean_update}
    )

    # 2. Sync Email with User collection if it changed
    if "email" in clean_update and clean_update["email"] != current_profile.get("email"):
        old_email = current_profile.get("email")
        new_email = clean_update["email"]
        
        # Check if new email is already taken in Users
        if db["users"].find_one({"email": new_email}):
             # Revert lawyer email update to maintain integrity if desired
             db["lawyers"].update_one({"_id": lawyer_obj_id}, {"$set": {"email": old_email}})
             raise HTTPException(status_code=400, detail="New email address is already in use by another account")

        db["users"].update_one(
            {"email": old_email},
            {"$set": {"email": new_email, "name": clean_update.get("fullName", current_profile.get("fullName"))}}
        )

    return {"success": True, "message": "Profile updated successfully"}
