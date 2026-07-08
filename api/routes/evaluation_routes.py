"""Evaluation endpoints."""

from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile

from api.schemas.request_schemas import EvaluationRequest
from api.schemas.response_schemas import GroundTruthListResponse, UploadResponse
from app.evaluation.evaluate_ground_truth import compare_keywords
from app.services.file_service import GROUND_TRUTH_DIR, ensure_data_dirs, save_ground_truth_bytes
from app.services.result_service import load_json

router = APIRouter(prefix="/evaluation", tags=["evaluation"])


@router.post("/compare")
def compare_with_ground_truth(payload: EvaluationRequest) -> dict:
    return compare_keywords(payload.result_path, payload.ground_truth_path)


@router.post("/ground-truth", response_model=UploadResponse)
async def upload_ground_truth(file: UploadFile = File(...)) -> UploadResponse:
    if not (file.filename or "").lower().endswith(".json"):
        raise HTTPException(status_code=400, detail="Ground truth must be a JSON file.")
    path = save_ground_truth_bytes(file.filename or "ground_truth.json", await file.read())
    try:
        load_json(path)
    except Exception as error:
        path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {error}") from error
    return UploadResponse(filename=path.name, path=path)


@router.get("/ground-truth", response_model=GroundTruthListResponse)
def list_ground_truth() -> GroundTruthListResponse:
    ensure_data_dirs()
    return GroundTruthListResponse(files=sorted(GROUND_TRUTH_DIR.glob("*.json")))
