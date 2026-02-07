from datetime import datetime, timezone
from pydantic import BaseModel, EmailStr, ConfigDict
from argon2 import PasswordHasher

pwd_hasher = PasswordHasher()

class RegisterUserRequest(BaseModel):
    email: EmailStr
    name: str
    password: str

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
            "user-role": "user",
            "password_hash": UserModel.hash_password(data.password),
            "created_at": now,
            "updated_at": now
        }

    @staticmethod
    def user_response(user: dict) -> dict:
        return {
            "id": str(user["_id"]),
            "email": user["email"],
            "name": user["name"],
            "created_at": user["created_at"].isoformat() if isinstance(user["created_at"], datetime) else str(user["created_at"])
        }

class LoginRequest(BaseModel):
    email: EmailStr
    password: str