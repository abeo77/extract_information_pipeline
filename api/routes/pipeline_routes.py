"""Pipeline endpoints."""

from pathlib import Path

from fastapi import APIRouter

from api.schemas.request_schemas import PipelineBatchRunRequest, PipelineRunRequest
from api.schemas.response_schemas import (
    PipelineBatchItemResponse,
    PipelineBatchRunResponse,
    PipelineRunResponse,
)
from app.pipeline import run_pipeline
from app.services.file_service import output_path
from app.services.parallel_service import ordered_parallel_map
from app.services.pipeline_service import PipelineConfig, build_config

router = APIRouter(prefix="/pipeline", tags=["pipeline"])


@router.post("/run", response_model=PipelineRunResponse)
def run_contract_pipeline(payload: PipelineRunRequest) -> PipelineRunResponse:
    config = build_config(**payload.model_dump())
    return _run_pipeline(payload.file_path, config, payload.output_path)


@router.post("/run-batch", response_model=PipelineBatchRunResponse)
def run_contract_pipeline_batch(payload: PipelineBatchRunRequest) -> PipelineBatchRunResponse:
    config = build_config(**payload.model_dump())

    def worker(file_path):
        try:
            result = _run_pipeline(file_path, config)
            return PipelineBatchItemResponse(
                file_path=file_path,
                output_path=result.output_path,
                status="success",
                total_pages=result.total_pages,
                total_segments=result.total_segments,
                keyword_groups=result.keyword_groups,
            )
        except Exception as error:
            return PipelineBatchItemResponse(
                file_path=file_path,
                status="error",
                error=str(error),
            )

    results = ordered_parallel_map(
        payload.file_paths,
        worker,
        max_workers=payload.max_parallel_files,
    )
    succeeded = sum(1 for item in results if item.status == "success")
    return PipelineBatchRunResponse(
        total_files=len(results),
        succeeded=succeeded,
        failed=len(results) - succeeded,
        max_parallel_files=payload.max_parallel_files,
        results=results,
    )


def _run_pipeline(
    file_path: Path,
    config: PipelineConfig,
    out: Path | None = None,
) -> PipelineRunResponse:
    out = out or output_path(file_path.name)
    result = run_pipeline(file_path, out, config)
    return PipelineRunResponse(
        output_path=out,
        total_pages=result.total_pages,
        total_segments=result.total_segments,
        keyword_groups=len(result.keyword_groups),
    )
