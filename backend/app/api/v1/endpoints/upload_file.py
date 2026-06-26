from fastapi import APIRouter, UploadFile
from typing import Annotated
from app.services.upload_service import handle_file

router = APIRouter()
  
@router.post("/file")
async def upload_file(file: UploadFile):
  result = await handle_file(file)
  return result