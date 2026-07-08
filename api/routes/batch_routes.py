"""Async batch processing endpoints."""

from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from redis.exceptions import RedisError

from api.schemas.response_schemas import BatchStatusResponse, FileJobResponse
from app.jobs import repository
from app.jobs.service import (
    MAX_BATCH_UPLOAD_FILES,
    create_batch_from_uploads,
    default_max_parallel_files,
    pipeline_config_options,
    retry_file_job,
)

router = APIRouter(prefix="/batches", tags=["batches"])
jobs_router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.post("/upload", response_model=BatchStatusResponse)
async def upload_batch(
    files: list[UploadFile] = File(...),
    max_parallel_files: int | None = Form(default=None),
    llm_provider: str | None = Form(default=None),
    llm_model: str | None = Form(default=None),
    llm_base_url: str | None = Form(default=None),
    llm1_provider: str | None = Form(default=None),
    llm1_model: str | None = Form(default=None),
    llm1_base_url: str | None = Form(default=None),
    llm2_provider: str | None = Form(default=None),
    llm2_model: str | None = Form(default=None),
    llm2_base_url: str | None = Form(default=None),
    keyword_batch_size: int | None = Form(default=None),
    grouping_batch_size: int | None = Form(default=None),
    evidence_batch_size: int | None = Form(default=None),
    max_evidence_segments_per_group: int | None = Form(default=None),
    max_parallel_llm_calls: int | None = Form(default=None),
    include_admin_sections: bool | None = Form(default=None),
) -> BatchStatusResponse:
    if len(files) > MAX_BATCH_UPLOAD_FILES:
        raise HTTPException(
            status_code=400,
            detail=f"Upload up to {MAX_BATCH_UPLOAD_FILES} files per batch.",
        )

    content = [(file.filename or "document", await file.read()) for file in files]
    options = pipeline_config_options(
        llm_provider=llm_provider,
        llm_model=llm_model,
        llm_base_url=llm_base_url,
        llm1_provider=llm1_provider,
        llm1_model=llm1_model,
        llm1_base_url=llm1_base_url,
        llm2_provider=llm2_provider,
        llm2_model=llm2_model,
        llm2_base_url=llm2_base_url,
        keyword_batch_size=keyword_batch_size,
        grouping_batch_size=grouping_batch_size,
        evidence_batch_size=evidence_batch_size,
        max_evidence_segments_per_group=max_evidence_segments_per_group,
        max_parallel_llm_calls=max_parallel_llm_calls,
        include_admin_sections=include_admin_sections,
    )
    try:
        batch = create_batch_from_uploads(
            files=content,
            max_parallel_files=max_parallel_files or default_max_parallel_files(),
            config_options=options,
            enqueue=True,
        )
    except RedisError as error:
        raise HTTPException(
            status_code=503,
            detail=f"Redis queue is unavailable: {error}",
        ) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return _batch_response(batch["id"])


@router.get("/{batch_id}", response_model=BatchStatusResponse)
def get_batch(batch_id: str) -> BatchStatusResponse:
    return _batch_response(batch_id)


@jobs_router.post("/{job_id}/retry", response_model=FileJobResponse)
def retry_job(job_id: str) -> FileJobResponse:
    try:
        job = retry_file_job(job_id)
    except RedisError as error:
        raise HTTPException(
            status_code=503,
            detail=f"Redis queue is unavailable: {error}",
        ) from error
    if job is None:
        raise HTTPException(status_code=404, detail="Failed job not found")
    return FileJobResponse(**job)


def _batch_response(batch_id: str) -> BatchStatusResponse:
    batch = repository.get_batch_with_files(batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="Batch not found")
    return BatchStatusResponse(**batch)
