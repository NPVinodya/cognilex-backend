# python
from fastapi import HTTPException, status
from bson import ObjectId

from config.cognilex_db import get_database
from config.jwt import create_access_token
from models.user import RegisterUserRequest, UserModel, LoginRequest
from pymongo.errors import DuplicateKeyError


class UserController:
    @staticmethod
    def register_user(data: RegisterUserRequest):
        db = get_database()
        users = db["users"]

        user_doc = UserModel.create_user_dict(data)

        try:
            result = users.insert_one(user_doc)
            user_doc["_id"] = result.inserted_id

            return {
                "message": "User created successfully",
                "user": UserModel.user_response(user_doc),
            }
        except DuplicateKeyError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered",
            )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"An error occurred: {str(e)}",
            )

    @staticmethod
    def get_user_by_email(email: str):
        db = get_database()
        users = db["users"]

        user = users.find_one({"email": email})
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )

        return UserModel.user_response(user)

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

        is_valid = UserModel.verify_password(data.password, user["password_hash"])
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
            )

        # Create JWT including user id, email, and role
        user_id = str(user["_id"]) if isinstance(user["_id"], ObjectId) else str(user["_id"])
        user_role = user.get("user-role", "user")
        access_token = create_access_token(
            {
                "sub": user_id,      # subject (user id)
                "email": user["email"],
                "role": user_role,   # user role
            }
        )

        return {
            "message": "Login successful",
            "user": UserModel.user_response(user),
            "access_token": access_token,
            "token_type": "bearer",
        }
