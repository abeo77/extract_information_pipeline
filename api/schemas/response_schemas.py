"""API response schemas."""

from pathlib import Path

from pydantic import BaseModel


class UploadResponse(BaseModel):
    filename: str
    path: Path


class PipelineRunResponse(BaseModel):
    output_path: Path
    total_pages: int
    total_segments: int
    keyword_groups: int


class ResultListResponse(BaseModel):
    files: list[Path]
