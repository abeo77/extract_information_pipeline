"""Upload endpoints."""

from fastapi import APIRouter, File, HTTPException, UploadFile

from api.schemas.response_schemas import UploadBatchResponse, UploadResponse
from app.services.file_service import save_bytes

router = APIRouter(prefix="/upload", tags=["upload"])
MAX_BATCH_UPLOAD_FILES = 10


@router.post("", response_model=UploadResponse)
async def upload_document(file: UploadFile = File(...)) -> UploadResponse:
    path = save_bytes(file.filename or "document", await file.read())
    return UploadResponse(filename=path.name, path=path)


@router.post("/batch", response_model=UploadBatchResponse)
async def upload_documents(files: list[UploadFile] = File(...)) -> UploadBatchResponse:
    if len(files) > MAX_BATCH_UPLOAD_FILES:
        raise HTTPException(
            status_code=400,
            detail=f"Upload up to {MAX_BATCH_UPLOAD_FILES} files per batch.",
        )

    saved_files = []
    for file in files:
        path = save_bytes(file.filename or "document", await file.read())
        saved_files.append(UploadResponse(filename=path.name, path=path))
    return UploadBatchResponse(files=saved_files)
