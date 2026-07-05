"""Pipeline endpoints."""

from fastapi import APIRouter

from api.schemas.request_schemas import PipelineRunRequest
from api.schemas.response_schemas import PipelineRunResponse
from app.pipeline import run_pipeline
from app.services.file_service import output_path
from app.services.pipeline_service import build_config

router = APIRouter(prefix="/pipeline", tags=["pipeline"])


@router.post("/run", response_model=PipelineRunResponse)
def run_contract_pipeline(payload: PipelineRunRequest) -> PipelineRunResponse:
    out = payload.output_path or output_path(payload.file_path.name)
    config = build_config(**payload.model_dump())
    result = run_pipeline(payload.file_path, out, config)
    return PipelineRunResponse(
        output_path=out,
        total_pages=result.total_pages,
        total_segments=result.total_segments,
        keyword_groups=len(result.keyword_groups),
    )
