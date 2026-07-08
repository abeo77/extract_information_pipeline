"""API response schemas."""

from pathlib import Path

from pydantic import BaseModel


class UploadResponse(BaseModel):
    filename: str
    path: Path


class UploadBatchResponse(BaseModel):
    files: list[UploadResponse]


class PipelineRunResponse(BaseModel):
    output_path: Path
    total_pages: int
    total_segments: int
    keyword_groups: int


class PipelineBatchItemResponse(BaseModel):
    file_path: Path
    output_path: Path | None = None
    status: str
    total_pages: int = 0
    total_segments: int = 0
    keyword_groups: int = 0
    error: str | None = None


class PipelineBatchRunResponse(BaseModel):
    total_files: int
    succeeded: int
    failed: int
    max_parallel_files: int
    results: list[PipelineBatchItemResponse]


class FileJobResponse(BaseModel):
    id: str
    batch_id: str
    filename: str
    input_path: Path
    file_hash: str
    status: str
    stage: str
    progress: int
    output_path: Path | None = None
    total_pages: int = 0
    total_segments: int = 0
    keyword_groups: int = 0
    error: str | None = None
    created_at: str
    updated_at: str
    started_at: str | None = None
    finished_at: str | None = None


class BatchStatusResponse(BaseModel):
    id: str
    status: str
    total_files: int
    max_parallel_files: int
    queued_count: int
    processing_count: int
    succeeded_count: int
    failed_count: int
    cached_count: int
    created_at: str
    updated_at: str
    started_at: str | None = None
    finished_at: str | None = None
    files: list[FileJobResponse]


class ResultListResponse(BaseModel):
    files: list[Path]


class GroundTruthListResponse(BaseModel):
    files: list[Path]
