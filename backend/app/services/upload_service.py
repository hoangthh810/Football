from pathlib import Path
from uuid import uuid4
from datetime import datetime, timezone

from fastapi import UploadFile, HTTPException

from app.db.database import database


ALLOWED_FILES = {
    ".pdf": {
        "file_type": "pdf",
        "content_types": ["application/pdf"],
        "folder": "pdfs",
        "max_size_mb": 10,
    },
    ".mp4": {
        "file_type": "video",
        "content_types": ["video/mp4"],
        "folder": "videos",
        "max_size_mb": 50,
    },
}

CHUNK_SIZE = 1024 * 1024  # 1MB

BACKEND_ROOT = Path(__file__).resolve().parents[2]
UPLOAD_ROOT = BACKEND_ROOT / "uploads"


def get_file_extension(filename: str) -> str:
    return Path(filename).suffix.lower()


def validate_file(file: UploadFile):
    if not file.filename:
        raise HTTPException(status_code=400, detail="Không tìm thấy tên file")

    extension = get_file_extension(file.filename)

    if extension not in ALLOWED_FILES:
        raise HTTPException(
            status_code=400,
            detail="Chỉ chấp nhận file .pdf hoặc .mp4",
        )

    file_config = ALLOWED_FILES[extension]

    if file.content_type not in file_config["content_types"]:
        raise HTTPException(
            status_code=400,
            detail=f"Content-Type không hợp lệ: {file.content_type}",
        )

    return extension, file_config


def validate_expected_file(file: UploadFile, expected_file_type: str):
    extension, file_config = validate_file(file)

    if file_config["file_type"] != expected_file_type:
        raise HTTPException(
            status_code=400,
            detail=f"File {file.filename} không đúng loại {expected_file_type}",
        )

    return extension, file_config


def create_stored_filename(original_filename: str, extension: str) -> str:
    safe_id = uuid4().hex
    original_stem = Path(original_filename).stem

    # Tránh tên quá dài hoặc có ký tự lạ quá nhiều
    safe_stem = original_stem.replace(" ", "_")

    return f"{safe_id}_{safe_stem}{extension}"


async def save_upload_file(
    file: UploadFile,
    destination_path: Path,
    max_size_mb: int,
) -> int:
    max_size_bytes = max_size_mb * 1024 * 1024
    total_size = 0

    try:
        with destination_path.open("wb") as buffer:
            while True:
                chunk = await file.read(CHUNK_SIZE)

                if not chunk:
                    break

                total_size += len(chunk)

                if total_size > max_size_bytes:
                    buffer.close()
                    destination_path.unlink(missing_ok=True)

                    raise HTTPException(
                        status_code=413,
                        detail=f"File quá lớn. Tối đa {max_size_mb}MB",
                    )

                buffer.write(chunk)

        return total_size

    except HTTPException:
        raise

    except Exception as e:
        destination_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=500,
            detail=f"Lỗi khi lưu file: {str(e)}",
        )


def build_upload_document(
    file: UploadFile,
    file_config: dict,
    stored_filename: str,
    file_size: int,
    relative_path: str,
    batch_id: str | None = None,
) -> dict:
    upload_document = {
        "original_filename": file.filename,
        "stored_filename": stored_filename,
        "file_type": file_config["file_type"],
        "content_type": file.content_type,
        "file_size": file_size,
        "storage_path": relative_path,
        "status": "uploaded",
        "created_at": datetime.now(timezone.utc),
    }

    if batch_id:
        upload_document["batch_id"] = batch_id

    return upload_document


async def save_file_to_local(file: UploadFile, extension: str, file_config: dict):
    stored_filename = create_stored_filename(file.filename, extension)

    target_dir = UPLOAD_ROOT / file_config["folder"]
    target_dir.mkdir(parents=True, exist_ok=True)

    destination_path = target_dir / stored_filename

    file_size = await save_upload_file(
        file=file,
        destination_path=destination_path,
        max_size_mb=file_config["max_size_mb"],
    )

    relative_path = destination_path.relative_to(BACKEND_ROOT).as_posix()

    return stored_filename, destination_path, file_size, relative_path


def format_upload_response(upload_document: dict, file_id: str):
    return {
        "file_id": file_id,
        "original_filename": upload_document["original_filename"],
        "stored_filename": upload_document["stored_filename"],
        "file_type": upload_document["file_type"],
        "content_type": upload_document["content_type"],
        "file_size": upload_document["file_size"],
        "storage_path": upload_document["storage_path"],
        "status": upload_document["status"],
    }


def serialize_datetime(value):
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def normalize_analysis_info(analysis_info: dict | None) -> dict:
    analysis_info = analysis_info or {}

    return {
        "job_name": str(analysis_info.get("job_name") or "").strip(),
        "match_date": str(analysis_info.get("match_date") or "").strip(),
        "model_version": str(analysis_info.get("model_version") or "").strip(),
        "job_note": str(analysis_info.get("job_note") or "").strip(),
    }


def build_analysis_job_document(
    batch_id: str,
    analysis_info: dict,
    file_ids: list[str],
) -> dict:
    now = datetime.now(timezone.utc)

    return {
        "batch_id": batch_id,
        "analysis_info": normalize_analysis_info(analysis_info),
        "file_ids": file_ids,
        "status": "uploaded",
        "created_at": now,
        "updated_at": now,
    }


def format_analysis_job_response(job_document: dict) -> dict:
    return {
        "job_id": str(job_document["_id"]),
        "batch_id": job_document.get("batch_id"),
        "analysis_info": job_document.get("analysis_info") or {},
        "file_ids": job_document.get("file_ids") or [],
        "files": job_document.get("files") or [],
        "status": job_document.get("status", "uploaded"),
        "created_at": serialize_datetime(job_document.get("created_at")),
        "updated_at": serialize_datetime(job_document.get("updated_at")),
    }

async def upload_match_files_service(pdf_file: UploadFile, video_file: UploadFile, analysis_info: dict):
    pdf_extension, pdf_config = validate_expected_file(pdf_file, "pdf")
    video_extension, video_config = validate_expected_file(video_file, "video")

    batch_id = uuid4().hex
    saved_paths = []

    try:
        pdf_stored_filename, pdf_path, pdf_size, pdf_relative_path = await save_file_to_local(
            file=pdf_file,
            extension=pdf_extension,
            file_config=pdf_config,
        )
        saved_paths.append(pdf_path)

        video_stored_filename, video_path, video_size, video_relative_path = await save_file_to_local(
            file=video_file,
            extension=video_extension,
            file_config=video_config,
        )
        saved_paths.append(video_path)

        pdf_document = build_upload_document(
            file=pdf_file,
            file_config=pdf_config,
            stored_filename=pdf_stored_filename,
            file_size=pdf_size,
            relative_path=pdf_relative_path,
            batch_id=batch_id,
        )
        video_document = build_upload_document(
            file=video_file,
            file_config=video_config,
            stored_filename=video_stored_filename,
            file_size=video_size,
            relative_path=video_relative_path,
            batch_id=batch_id,
        )

        upload_result = await database["uploads"].insert_many([pdf_document, video_document])
        file_ids = [str(inserted_id) for inserted_id in upload_result.inserted_ids]
        files = [
            format_upload_response(pdf_document, file_ids[0]),
            format_upload_response(video_document, file_ids[1]),
        ]
        analysis_job_document = build_analysis_job_document(
            batch_id=batch_id,
            analysis_info=analysis_info,
            file_ids=file_ids,
        )
        analysis_job_result = await database["analysis_jobs"].insert_one(analysis_job_document)

        return {
            "message": "Upload batch successful",
            "job_id": str(analysis_job_result.inserted_id),
            "batch_id": batch_id,
            "analysis_info": analysis_job_document["analysis_info"],
            "status": "uploaded",
            "files": files,
        }

    except HTTPException:
        for saved_path in saved_paths:
            saved_path.unlink(missing_ok=True)
        raise

    except Exception as e:
        for saved_path in saved_paths:
            saved_path.unlink(missing_ok=True)
        try:
            await database["uploads"].delete_many({"batch_id": batch_id})
            await database["analysis_jobs"].delete_many({"batch_id": batch_id})
        except Exception:
            pass
        raise HTTPException(
            status_code=500,
            detail=f"Upload PDF và video thất bại: {str(e)}",
        )
