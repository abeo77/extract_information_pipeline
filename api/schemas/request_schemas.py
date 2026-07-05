"""API request schemas."""

from pathlib import Path

from pydantic import BaseModel


class PipelineRunRequest(BaseModel):
    file_path: Path
    output_path: Path | None = None
    llm_provider: str | None = None
    llm_model: str | None = None
    llm_api_key: str | None = None
    llm_base_url: str | None = None
    llm1_provider: str | None = None
    llm1_model: str | None = None
    llm1_api_key: str | None = None
    llm1_base_url: str | None = None
    llm2_provider: str | None = None
    llm2_model: str | None = None
    llm2_api_key: str | None = None
    llm2_base_url: str | None = None
    keyword_batch_size: int | None = None
    grouping_batch_size: int | None = None
    evidence_batch_size: int = 10
    max_evidence_segments_per_group: int = 5
    max_parallel_llm_calls: int = 1
    include_admin_sections: bool | None = None


class EvaluationRequest(BaseModel):
    result_path: Path
    ground_truth_path: Path
