from fastapi import APIRouter, UploadFile, File, Form
from app.services.upload_service import upload_match_files_service
from app.services.get_analysis_jobs_service import get_analysis_jobs_service

router = APIRouter()


@router.post("/match-files")
async def upload_match_files(
  pdf_file: UploadFile = File(...),
  video_file: UploadFile = File(...),
  job_name: str = Form(...),
  match_date: str = Form(...),
  model_version: str = Form(...),
  job_note: str = Form(""),
):
  analysis_info = {
    "job_name": job_name,
    "match_date": match_date,
    "model_version": model_version,
    "job_note": job_note,
  }
  result = await upload_match_files_service(pdf_file, video_file, analysis_info)
  return result


@router.get("/analysis_jobs")
async def get_match_files():
    return await get_analysis_jobs_service()
  
  
# @router.get("/get_match-files/{file_id}")
# async def get_match_files():
#     pass
