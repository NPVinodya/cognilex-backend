from fastapi import APIRouter, status
from models.user import RegisterUserRequest, LoginRequest
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






