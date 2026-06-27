from pathlib import Path
from fastapi import FastAPI, HTTPException


from app.db.database import database

async def get_match_files_from_db() -> list:
  analysis_jobs = []
  try:
    cursor = database["analysis_jobs"].find({}).sort("created_at", -1)
    async for document in cursor:
        document["_id"] = str(document["_id"])
        analysis_jobs.append(document)
  except Exception as e:  
        raise HTTPException(
            status_code=500,
            detail=f"Lỗi database, không thể đọc collection analysis_jobs: {str(e)}",
        )
  return analysis_jobs

async def get_analysis_jobs_service() -> list:
   analysis_jobs = await get_match_files_from_db()
   return analysis_jobs