"""Pydantic schemas for the contract keyword pipeline."""

from typing import Any

from pydantic import BaseModel, Field


class DocumentSegment(BaseModel):
    segment_id: str
    text: str
    title: str | None = None
    page: int | None = None
    source: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class Llm1SegmentInput(BaseModel):
    segment_id: str
    page: int | None = None
    parent_section_title: str | None = None
    clause_no: str | None = None
    text: str


class Llm1BatchInput(BaseModel):
    source: str | None = None
    segments: list[Llm1SegmentInput] = Field(default_factory=list)


class LlmCallStats(BaseModel):
    keyword_extraction_batches: int = 0
    keyword_groups_for_evidence: int = 0
    coverage_candidate_groups: int = 0
    coverage_added_groups: int = 0
    filtered_groups: int = 0
    local_exact_groups: int = 0
    llm2_fallback_groups: int = 0
    evidence_extraction_batches: int = 0
    max_total_llm_calls: int | None = None


class PipelineResult(BaseModel):
    document_name: str
    processing_time_seconds: float
    total_pages: int
    total_segments: int
    total_keyword_groups: int = 0
    llm_calls: LlmCallStats = Field(default_factory=LlmCallStats)
    keyword_groups: list[dict[str, Any]] = Field(default_factory=list)
