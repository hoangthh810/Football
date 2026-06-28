from fastapi import APIRouter, UploadFile, File, Form, Depends
from app.services.upload_service import upload_match_files_service
from app.services.get_analysis_jobs_service import (
    get_job_analysis_and_upload_files_service,
)
from app.api.deps import get_current_user

router = APIRouter()


@router.post("/match-files")
async def upload_match_files(
    pdf_file: UploadFile = File(...),
    video_file: UploadFile = File(...),
    job_name: str = Form(...),
    match_date: str = Form(...),
    model_version: str = Form(...),
    job_note: str = Form(""),
    current_user: dict = Depends(get_current_user),
):
    analysis_info = {
        "job_name": job_name,
        "match_date": match_date,
        "model_version": model_version,
        "job_note": job_note,
    }
    result = await upload_match_files_service(
        pdf_file, video_file, analysis_info, user_id=str(current_user["_id"])
    )
    return result


@router.get("/analysis_jobs")
async def get_match_files(
    limit: int = 5,
    skip: int = 0,
    current_user: dict = Depends(get_current_user),
):
    analysis_jobs, uploads_files = await get_job_analysis_and_upload_files_service(
        limit=limit, skip=skip, user_id=str(current_user["_id"])
    )
    return {"analysis_jobs": analysis_jobs, "uploads_files": uploads_files}
