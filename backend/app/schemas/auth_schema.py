from pydantic import BaseModel, EmailStr
from typing import Literal


class UserBase(BaseModel):
    user_email: EmailStr


class RegisterRequest(UserBase):
    user_fullname: str
    user_role: Literal["admin", "user"]
    user_password: str


class LoginRequest(UserBase):
    user_password: str


class UserInDB(UserBase):
    user_fullname: str
    user_role: str
    hashed_password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str
    user_email: EmailStr
    user_fullname: str
    user_role: Literal["admin", "user"]