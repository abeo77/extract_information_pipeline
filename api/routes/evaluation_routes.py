"""Evaluation endpoints."""

from fastapi import APIRouter

from api.schemas.request_schemas import EvaluationRequest
from app.evaluation.evaluate_ground_truth import compare_keywords

router = APIRouter(prefix="/evaluation", tags=["evaluation"])


@router.post("/compare")
def compare_with_ground_truth(payload: EvaluationRequest) -> dict:
    return compare_keywords(payload.result_path, payload.ground_truth_path)
