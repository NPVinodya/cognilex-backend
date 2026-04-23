import os
import uuid
import boto3
from datetime import datetime, timezone
from fastapi import HTTPException, status, UploadFile
from bson import ObjectId
from config.cognilex_db import get_database
from config.jwt import create_access_token
from models.user import RegisterUserRequest, UserModel, LoginRequest, RegisterOAuthRequest, UpdateProfileRequest, UpdatePasswordRequest, UpdatePreferencesRequest
from pymongo.errors import DuplicateKeyError


class UserController:
    @staticmethod
    def register_user(data: RegisterUserRequest):
        db = get_database()
        users = db["users"]

        normalized_name = str(data.name).strip()
        if not normalized_name:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Full name is required",
            )

        normalized_email = str(data.email).strip().lower()

        existing_user = users.find_one({"email": normalized_email})
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email already registered",
            )

        user_doc = UserModel.create_user_dict(data)
        user_doc["name"] = normalized_name
        user_doc["email"] = normalized_email
        user_doc["user-role"] = "user"

        try:
            result = users.insert_one(user_doc)
            user_doc["_id"] = result.inserted_id

            return {
                "message": "User created successfully",
                "user": UserModel.user_response(user_doc),
            }
        except DuplicateKeyError:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email already registered",
            )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"An error occurred: {str(e)}",
            )

    @staticmethod
    def register_oauth_user(data: RegisterOAuthRequest):
        """
        Idempotent upsert for users who authenticated via Google/OAuth.
        - If the user already exists (by appwrite_id or email), returns their data.
        - If not, creates a new MongoDB document with role='user' and no password.
        """
        db = get_database()
        users = db["users"]

        normalized_email = str(data.email).strip().lower()
        normalized_name = str(data.name).strip() or normalized_email.split("@")[0]

        # Check by appwrite_id first, then fall back to email
        existing = users.find_one({"appwrite_id": data.appwrite_id})
        if not existing:
            existing = users.find_one({"email": normalized_email})

        if existing:
            # Back-fill appwrite_id if missing (for existing OTP-registered users)
            if not existing.get("appwrite_id"):
                users.update_one(
                    {"_id": existing["_id"]},
                    {"$set": {"appwrite_id": data.appwrite_id}},
                )
                existing["appwrite_id"] = data.appwrite_id
            user_response = UserModel.user_response(existing)
            user_response["role"] = existing.get("user-role", "user")
            return {
                "message": "User already exists",
                "user": user_response,
            }

        now = datetime.now(timezone.utc)
        user_doc = {
            "email": normalized_email,
            "name": normalized_name,
            "user-role": "user",
            "appwrite_id": data.appwrite_id,
            "auth_provider": "google",
            # OAuth users have no local password; mark explicitly so login_user is not used.
            "password_hash": None,
            "created_at": now,
            "updated_at": now,
        }

        try:
            result = users.insert_one(user_doc)
            user_doc["_id"] = result.inserted_id
            user_response = UserModel.user_response(user_doc)
            user_response["role"] = "user"
            return {
                "message": "OAuth user created successfully",
                "user": user_response,
            }
        except DuplicateKeyError:
            # Race condition — another request inserted the same email; fetch and return.
            existing = users.find_one({"email": normalized_email})
            user_response = UserModel.user_response(existing)
            user_response["role"] = existing.get("user-role", "user")
            return {"message": "User already exists", "user": user_response}
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"An error occurred: {str(e)}",
            )

    @staticmethod
    def get_user_by_email(email: str):
        db = get_database()
        users = db["users"]

        normalized_email = str(email).strip().lower()
        user = users.find_one({"email": normalized_email})
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )

        user_response = UserModel.user_response(user)
        user_response["role"] = user.get("user-role", "user")
        return user_response

    # @staticmethod
    # def login_user(data: LoginRequest):
    #     db = get_database()
    #     users = db["users"]
    #
    #     user = users.find_one({"email": data.email})
    #     if not user:
    #         raise HTTPException(
    #             status_code=status.HTTP_401_UNAUTHORIZED,
    #             detail="Invalid email or password",
    #         )
    #
    #     if "password_hash" not in user:
    #         raise HTTPException(
    #             status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    #             detail="Password data not found in database",
    #         )
    #
    #     is_valid = UserModel.verify_password(data.password, user["password_hash"])
    #     if not is_valid:
    #         raise HTTPException(
    #             status_code=status.HTTP_401_UNAUTHORIZED,
    #             detail="Invalid email or password",
    #         )
    #
    #     # Create JWT including user id, email, and role
    #     user_id = str(user["_id"]) if isinstance(user["_id"], ObjectId) else str(user["_id"])
    #     user_role = user.get("user-role", "lawyer")
    #     access_token = create_access_token(
    #         {
    #             "sub": user_id,      # subject (user id)
    #             "email": user["email"],
    #             "role": user_role,   # user role
    #         }
    #     )
    #
    #     return {
    #         "message": "Login successful",
    #         "user": UserModel.user_response(user),
    #         "access_token": access_token,
    #         "token_type": "bearer",
    #     }


    @staticmethod
    def login_user(data: LoginRequest):
        db = get_database()
        users = db["users"]

        user = users.find_one({"email": data.email})
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
            )

        if "password_hash" not in user:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Password data not found in database",
            )

        if not UserModel.verify_password(data.password, user["password_hash"]):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
            )

        user_id = str(user["_id"]) if isinstance(user["_id"], ObjectId) else str(user["_id"])

        # Fetch role from MongoDB document (support both keys).
        user_role = user.get("user-role")
        if not user_role:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="User role not found in database",
            )

        access_token = create_access_token(
            {
                "sub": user_id,
                "email": user["email"],
                "role": user_role,
            }
        )

        user_response = UserModel.user_response(user)
        user_response["role"] = user_role

        return {
            "message": "Login successful",
            "user": user_response,
            "access_token": access_token,
            "token_type": "bearer",
        }

    @staticmethod
    def update_user_profile(data: UpdateProfileRequest):
        db = get_database()
        users = db["users"]

        user = users.find_one({"email": data.email})
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )
        
        update_data = {"name": data.name}
        if data.avatar_url:
            update_data["avatar_url"] = data.avatar_url

        users.update_one({"email": data.email}, {"$set": update_data})
        updated_user = users.find_one({"email": data.email})
        return {
            "message": "Profile updated successfully",
            "user": UserModel.user_response(updated_user),
        }

    @staticmethod
    def update_user_password(data: UpdatePasswordRequest):
        db = get_database()
        users = db["users"]

        user = users.find_one({"email": data.email})
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )

        if "password_hash" not in user or not UserModel.verify_password(data.current_password, user["password_hash"]):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid current password",
            )

        new_hash = UserModel.hash_password(data.new_password)
        users.update_one({"email": data.email}, {"$set": {"password_hash": new_hash}})
        return {"message": "Password updated successfully"}

    @staticmethod
    def update_user_preferences(data: UpdatePreferencesRequest):
        db = get_database()
        users = db["users"]

        user = users.find_one({"email": data.email})
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )
        
        users.update_one({"email": data.email}, {"$set": {"preferences": {"appearance": data.appearance, "language": data.language}}})
        return {"message": "Preferences updated successfully"}

    @staticmethod
    async def upload_user_avatar(email: str, file: UploadFile):
        db = get_database()
        users = db["users"]

        user = users.find_one({"email": email})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Configuration from .env
        r2_access_key = os.getenv("R2_ACCESS_KEY_ID")
        r2_secret_key = os.getenv("R2_SECRET_ACCESS_KEY")
        r2_account_id = os.getenv("R2_ACCOUNT_ID")
        r2_bucket_name = os.getenv("R2_BUCKET_NAME")
        r2_public_url = os.getenv("R2_PUBLIC_URL")
        
        # Endpoint construction
        r2_endpoint_url = f"https://{r2_account_id}.r2.cloudflarestorage.com"

        if not all([r2_access_key, r2_secret_key, r2_bucket_name, r2_endpoint_url]):
            raise HTTPException(status_code=500, detail="Cloudflare R2 configuration is missing")

        s3 = boto3.client(
            "s3",
            endpoint_url=r2_endpoint_url,
            aws_access_key_id=r2_access_key,
            aws_secret_access_key=r2_secret_key,
            region_name="auto" # R2 uses 'auto'
        )

        file_extension = os.path.splitext(file.filename)[1]
        unique_filename = f"users/{str(user['_id'])}-{uuid.uuid4().hex}{file_extension}"

        try:
            # Read file content
            file_content = await file.read()
            
            # Upload to R2
            s3.put_object(
                Bucket=r2_bucket_name,
                Key=unique_filename,
                Body=file_content,
                ContentType=file.content_type
            )

            # Construct the final URL
            # If public URL is provided, use it, otherwise use the bucket URL (if accessible)
            avatar_url = f"{r2_public_url}/{unique_filename}" if r2_public_url else f"{r2_endpoint_url}/{r2_bucket_name}/{unique_filename}"

            # Update database
            users.update_one({"email": email}, {"$set": {"avatar_url": avatar_url}})

            return {
                "message": "Avatar uploaded successfully",
                "avatar_url": avatar_url
            }

        except Exception as e:
            print(f"R2 Upload Error: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Failed to upload image: {str(e)}")

    @staticmethod
    def delete_user_account(email: str):
        db = get_database()
        users = db["users"]

        user = users.find_one({"email": email})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        result = users.delete_one({"email": email})
        if result.deleted_count == 0:
            raise HTTPException(status_code=500, detail="Failed to delete account")

        return {"message": "Account deleted successfully"}
