from fastapi import APIRouter
from app.db.database import database

router = APIRouter()


@router.get("/ping")
async def ping_database():
    try:
        result = await database.command("ping")
        return {
            "message": "MongoDB connected successfully",
            "result": result
        }
    except Exception as e:
        return {
            "message": "MongoDB connection failed",
            "error": str(e)
        }