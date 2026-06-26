from fastapi import APIRouter

from app.api.v1.endpoints import test_db
from app.api.v1.endpoints import upload_file

api_router = APIRouter()

api_router.include_router(upload_file.router, prefix="/upload", tags=["Upload"])
api_router.include_router(test_db.router, prefix="/db", tags=["Database"])