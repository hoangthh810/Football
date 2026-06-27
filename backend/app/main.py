from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.v1.api import api_router
from app.services.upload_service import UPLOAD_ROOT

UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)

app = FastAPI(
    title="Detect Football API",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5500",
        "http://localhost:5500",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api/v1")
app.mount("/uploads", StaticFiles(directory=UPLOAD_ROOT), name="uploads")


@app.get("/")
def root():
    return {
        "message": "Detect Football API is running"
    }
