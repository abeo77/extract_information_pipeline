"""Upload endpoints."""

from fastapi import APIRouter, File, UploadFile

from api.schemas.response_schemas import UploadResponse
from app.services.file_service import save_bytes

router = APIRouter(prefix="/upload", tags=["upload"])


@router.post("", response_model=UploadResponse)
async def upload_document(file: UploadFile = File(...)) -> UploadResponse:
    path = save_bytes(file.filename or "document", await file.read())
    return UploadResponse(filename=path.name, path=path)
