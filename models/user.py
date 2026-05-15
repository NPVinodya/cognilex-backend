from datetime import datetime, timezone
from pydantic import BaseModel, EmailStr, ConfigDict
from argon2 import PasswordHasher
from typing import Literal

pwd_hasher = PasswordHasher()

class RegisterUserRequest(BaseModel):
    email: EmailStr
    name: str
    password: str
    role: Literal["user"] = "user"

    model_config = ConfigDict(populate_by_name=True)

class UserModel:
    @staticmethod
    def hash_password(password: str) -> str:
        return pwd_hasher.hash(password)

    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        try:
            return pwd_hasher.verify(hashed_password, plain_password)
        except Exception:
            return False

    @staticmethod
    def create_user_dict(data: RegisterUserRequest) -> dict:
        now = datetime.now(timezone.utc)
        return {
            "email": data.email,
            "name": data.name,
            "user-role": data.role,
            "password_hash": UserModel.hash_password(data.password),
            "created_at": now,
            "updated_at": now
        }

    @staticmethod
    def user_response(user: dict) -> dict:
        resp = {
            "id": str(user["_id"]),
            "email": user["email"],
            "name": user["name"],
            "created_at": user["created_at"].isoformat() if isinstance(user["created_at"], datetime) else str(user["created_at"])
        }
        if "preferences" in user:
            resp["preferences"] = user["preferences"]
        if "avatar_url" in user:
            resp["avatar_url"] = user["avatar_url"]
        return resp

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class RegisterOAuthRequest(BaseModel):
    """Password-less registration for users who sign in via Google / OAuth.
    Appwrite handles authentication; we only need to mirror their profile in MongoDB.
    """
    appwrite_id: str
    email: EmailStr
    name: str
    role: Literal["user"] = "user"

class UpdateProfileRequest(BaseModel):
    email: EmailStr
    name: str
    avatar_url: str = None

class UpdatePasswordRequest(BaseModel):
    email: EmailStr
    current_password: str
    new_password: str

class UpdatePreferencesRequest(BaseModel):
    email: EmailStr
    appearance: str
    language: str
class UpdatePreferencesRequest(BaseModel):
    email: EmailStr
    appearance: str
    language: str