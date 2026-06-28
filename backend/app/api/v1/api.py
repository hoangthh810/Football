from fastapi import APIRouter

from app.api.v1.endpoints import test_db
from app.api.v1.endpoints import upload_file
from app.api.v1.endpoints import auth

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["Auth"])
api_router.include_router(upload_file.router, prefix="/upload", tags=["Upload"])
api_router.include_router(test_db.router, prefix="/db", tags=["Database"])
