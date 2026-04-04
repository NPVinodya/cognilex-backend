from fastapi import APIRouter, status, File, UploadFile
from models.user import RegisterUserRequest, LoginRequest, UpdateProfileRequest, UpdatePasswordRequest, UpdatePreferencesRequest
from controllers.user_controller import UserController

router = APIRouter(tags=["Authentication"])

@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(user_data: RegisterUserRequest):
    return UserController.register_user(user_data)

@router.get("/user/{email}")
async def get_user_by_email(email: str):
    return UserController.get_user_by_email(email)

@router.post("/login")
async def login(login_data: LoginRequest):
    return UserController.login_user(login_data)

@router.patch("/profile")
async def update_profile(update_data: UpdateProfileRequest):
    return UserController.update_user_profile(update_data)

@router.patch("/password")
async def update_password(update_data: UpdatePasswordRequest):
    return UserController.update_user_password(update_data)

@router.patch("/preferences")
async def update_preferences(update_data: UpdatePreferencesRequest):
    return UserController.update_user_preferences(update_data)

@router.post("/avatar/upload")
async def upload_avatar(email: str, file: UploadFile = File(...)):
    return await UserController.upload_user_avatar(email, file)

@router.delete("/profile/{email}")
async def delete_profile(email: str):
    return UserController.delete_user_account(email)
