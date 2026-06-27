from fastapi import APIRouter, UploadFile, File
from app.services.upload_service import upload_match_files_service

router = APIRouter()


@router.post("/match-files")
async def upload_match_files(
  pdf_file: UploadFile = File(...),
  video_file: UploadFile = File(...),
):
  result = await upload_match_files_service(pdf_file, video_file)
  return result
