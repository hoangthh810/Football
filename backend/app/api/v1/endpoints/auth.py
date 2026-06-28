from fastapi import APIRouter, Depends
from app.schemas.auth_schema import RegisterRequest, LoginRequest, LoginResponse
from app.services.auth_service import handle_register, handle_login
from app.api.deps import get_current_user

router = APIRouter()


@router.post("/register")
async def register(user_register: RegisterRequest):
    result = await handle_register(user_register)
    return result

@router.post("/login")
async def login(user_login: LoginRequest):
    token = await handle_login(user_login)
    return token

@router.get("/profile")
async def profile(current_user: dict = Depends(get_current_user)):
    return {
        "user_id": str(current_user["_id"]),
        "user_email": current_user["user_email"],
        "user_fullname": current_user["user_fullname"],
        "user_role": current_user["user_role"],
    }