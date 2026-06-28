from fastapi import APIRouter
from app.schemas.auth_schema import RegisterRequest, LoginRequest, LoginResponse
from app.services.auth_service import handle_register, handle_login

router = APIRouter()


@router.post("/register")
async def register(user_register: RegisterRequest):
    result = await handle_register(user_register)
    return result

@router.post("/login")
async def login(user_login: LoginRequest):
    token = await handle_login(user_login)
    return token

@router.get('/profile')
async def profile():
    pass