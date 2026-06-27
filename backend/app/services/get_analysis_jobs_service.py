from bson import ObjectId
from fastapi import HTTPException

from app.db.database import database


async def get_job_analysis_and_upload_files_from_db(limit: int, skip: int) -> list:
    analysis_jobs = []
    batch_ids = []

    try:
        cursor_job_analysis = database["analysis_jobs"].find({}).skip(skip).limit(limit)

        async for document in cursor_job_analysis:
            document["_id"] = str(document["_id"])
            analysis_jobs.append(document)

            if "batch_id" in document:
                batch_ids.append(document["batch_id"])
        uploads_files = []
        if batch_ids:
            cursor_uploads = database["uploads"].find({"batch_id": {"$in": batch_ids}})
            async for upload_document in cursor_uploads:
                upload_document["_id"] = str(upload_document["_id"])
                uploads_files.append(upload_document)

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Lỗi database, không thể đọc collection analysis_jobs: {str(e)}",
        )

    return analysis_jobs, uploads_files


async def get_job_analysis_and_upload_files_service(limit: int, skip: int) -> list:
    analysis_jobs, uploads_files = await get_job_analysis_and_upload_files_from_db(
        limit=limit,
        skip=skip,
    )
    return analysis_jobs, uploads_files
