"""Result endpoints."""

from pathlib import Path

from fastapi import APIRouter, HTTPException

from api.schemas.response_schemas import ResultListResponse
from app.services.file_service import OUTPUT_DIR, ensure_data_dirs
from app.services.result_service import load_json

router = APIRouter(prefix="/results", tags=["results"])


@router.get("", response_model=ResultListResponse)
def list_results() -> ResultListResponse:
    ensure_data_dirs()
    return ResultListResponse(files=sorted(OUTPUT_DIR.glob("*.json")))


@router.get("/{filename}")
def get_result(filename: str) -> dict:
    path = OUTPUT_DIR / Path(filename).name
    if not path.exists():
        raise HTTPException(status_code=404, detail="Result not found")
    return load_json(path)
