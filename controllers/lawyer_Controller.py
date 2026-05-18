import os
from datetime import datetime

from bson import ObjectId
from fastapi import UploadFile

from config.cognilex_db import get_database
from config.R2_config import r2_storage


async def save_file_to_r2(file: UploadFile, lawyer_id: str, file_type: str) -> str:
    """
    Save uploaded file to Cloudflare R2

    Args:
        file: The uploaded file
        lawyer_id: Unique lawyer identifier
        file_type: Type of file (profile, nic_front, nic_back, lawyer_id)

    Returns:
        str: Public URL of uploaded file
    """
    # Get file extension
    file_extension = os.path.splitext(file.filename)[1] or ".jpg"

    # Create R2 file key (path in bucket)
    file_key = f"lawyers/{lawyer_id}/{file_type}{file_extension}"

    # Determine content type
    content_type = file.content_type or "image/jpeg"

    # Upload to R2
    public_url = await r2_storage.upload_file(file.file, file_key, content_type)

    return public_url


async def register_lawyer(lawyer_data: dict, files: dict[str, UploadFile]) -> str:
    """
    Register a new lawyer with document uploads to Cloudflare R2

    Args:
        lawyer_data: Dictionary containing lawyer information
        files: Dictionary containing uploaded files

    Returns:
        str: The inserted lawyer ID
    """
    db = get_database()
    lawyers_collection = db["lawyers"]

    # Check if email already exists
    existing_lawyer = lawyers_collection.find_one({"email": lawyer_data["email"]})
    if existing_lawyer:
        raise ValueError("Email already registered")

    # Check if NIC already exists
    existing_nic = lawyers_collection.find_one({"nicNumber": lawyer_data["nicNumber"]})
    if existing_nic:
        raise ValueError("NIC number already registered")

    # Check if Lawyer ID already exists
    existing_lawyer_id = lawyers_collection.find_one({"lawyerId": lawyer_data["lawyerId"]})
    if existing_lawyer_id:
        raise ValueError("Lawyer ID already registered")

    # Generate unique ID for file storage
    temp_id = str(ObjectId())

    # Upload files to Cloudflare R2
    file_urls = {}
    try:
        # Upload profile photo
        file_urls["profilePhotoUrl"] = await save_file_to_r2(
            files["profilePhoto"], temp_id, "profile"
        )

        # Upload NIC front
        file_urls["nicFrontPhotoUrl"] = await save_file_to_r2(
            files["nicFrontPhoto"], temp_id, "nic_front"
        )

        # Upload NIC back
        file_urls["nicBackPhotoUrl"] = await save_file_to_r2(
            files["nicBackPhoto"], temp_id, "nic_back"
        )

        # Upload Lawyer ID
        file_urls["lawyerIdPhotoUrl"] = await save_file_to_r2(
            files["lawyerIdPhoto"], temp_id, "lawyer_id"
        )

    except Exception as e:
        # Cleanup uploaded files if error occurs
        try:
            await r2_storage.delete_folder(f"lawyers/{temp_id}/")
        except:
            pass
        raise Exception(f"File upload failed: {str(e)}")

    # Prepare document for insertion
    lawyer_document = {
        **lawyer_data,
        **file_urls,  # Add all file URLs
        "status": "pending",  # pending, approved, rejected
        "registrationDate": datetime.utcnow(),
        "approvalDate": None,
        "rejectionReason": None,
        "rating": 0.0,
        "totalReviews": 0,
        "totalAppointments": 0,
        "isActive": True
    }

    # Insert into database
    result = lawyers_collection.insert_one(lawyer_document)

    return str(result.inserted_id)


async def get_all_lawyers(
        province: str | None = None,
        specialization: str | None = None,
        status: str = "approved"
) -> list[dict]:
    """
    Get all lawyers with optional filters
    """
    db = get_database()
    lawyers_collection = db["lawyers"]

    # Build query
    query = {"status": status, "isActive": True}
    if province:
        query["province"] = province
    if specialization:
        query["specialization"] = specialization

    # Fetch lawyers (sorted by rating)
    lawyers = list(lawyers_collection.find(query).sort("rating", -1))

    # Convert ObjectId to string and format dates
    for lawyer in lawyers:
        lawyer["_id"] = str(lawyer["_id"])
        lawyer["registrationDate"] = lawyer["registrationDate"].isoformat()
        if lawyer.get("approvalDate"):
            lawyer["approvalDate"] = lawyer["approvalDate"].isoformat()

    return lawyers


async def get_lawyer_by_id(lawyer_id: str) -> dict | None:
    """
    Get lawyer details by ID
    """
    db = get_database()
    lawyers_collection = db["lawyers"]
    users_collection = db["users"]

    try:
        lawyer = lawyers_collection.find_one({"_id": ObjectId(lawyer_id)})
        if lawyer:
            lawyer["_id"] = str(lawyer["_id"])
            lawyer["registrationDate"] = lawyer["registrationDate"].isoformat()
            if lawyer.get("approvalDate"):
                lawyer["approvalDate"] = lawyer["approvalDate"].isoformat()
        return lawyer
    except:
        return None


async def approve_lawyer(lawyer_id: str) -> bool:
    """
    Approve a lawyer registration
    """
    db = get_database()
    lawyers_collection = db["lawyers"]

    result = lawyers_collection.update_one(
        {"_id": ObjectId(lawyer_id)},
        {
            "$set": {
                "status": "approved",
                "approvalDate": datetime.utcnow(),
                "isActive": True
            }
        }
    )

    # Send approval email to lawyer

    return result.modified_count > 0


async def reject_lawyer(lawyer_id: str, reason: str) -> bool:
    """
    Reject a lawyer registration
    """
    db = get_database()
    lawyers_collection = db["lawyers"]

    result = lawyers_collection.update_one(
        {"_id": ObjectId(lawyer_id)},
        {
            "$set": {
                "status": "rejected",
                "rejectionReason": reason,
                "approvalDate": datetime.utcnow(),
                "isActive": False
            }
        }
    )

    # Send rejection email to lawyer with reason

    return result.modified_count > 0


async def delete_lawyer(lawyer_id: str) -> bool:
    """
    Soft delete a lawyer (set isActive to False)
    """
    db = get_database()
    lawyers_collection = db["lawyers"]

    result = lawyers_collection.update_one(
        {"_id": ObjectId(lawyer_id)},
        {"$set": {"isActive": False}}
    )

    return result.modified_count > 0


async def get_pending_lawyers() -> list[dict]:
    """
    Get all pending lawyer registrations for admin approval
    """
    db = get_database()
    lawyers_collection = db["lawyers"]

    lawyers = list(lawyers_collection.find({"status": "pending"}).sort("registrationDate", -1))

    for lawyer in lawyers:
        lawyer["_id"] = str(lawyer["_id"])
        lawyer["registrationDate"] = lawyer["registrationDate"].isoformat()

    return lawyers


async def get_lawyer_profile_data(lawyer_id: str) -> dict | None:
    db = get_database()
    try:

        lawyer = db["lawyers"].find_one({"_id": ObjectId(lawyer_id)})

        if lawyer:
            # Frontend types.ts
            lawyer["id"] = str(lawyer["_id"])
            lawyer["fullName"] = lawyer.get("fullName")
            lawyer["practiceAreas"] = lawyer.get("practiceAreas", [])
            lawyer["province"] = lawyer.get("province")
            lawyer["yearsOfExperience"] = lawyer.get("yearsOfExperience", 0)
            lawyer["consultationFee"] = lawyer.get("consultationFee", 0)
            lawyer["barCouncilNumber"] = lawyer.get("barCouncilNumber")
            lawyer["profilePhotoUrl"] = lawyer.get("profilePhotoUrl")
            lawyer["bio"] = lawyer.get("bio")
            lawyer["phone"] = lawyer.get("phone")
            lawyer["email"] = lawyer.get("email")


            if "password" in lawyer: del lawyer["password"]
            del lawyer["_id"]

            return {"success": True, "lawyer": lawyer}
        return {"success": False, "message": "Lawyer not found"}
    except Exception as e:
        print(f"Error fetching lawyer: {e}")
        return None
