"""High-level job orchestration helpers used by API routes."""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Any

from app.jobs import repository
from app.jobs.queue import enqueue_batch, enqueue_file
from app.services.file_service import available_input_path, ensure_data_dirs
from app.services.pipeline_service import build_config

MAX_BATCH_UPLOAD_FILES = 10
DEFAULT_MAX_PARALLEL_FILES = 2
PIPELINE_CACHE_VERSION = "adaptive-coverage-filter-v1"


def default_max_parallel_files() -> int:
    value = int(os.getenv("DEFAULT_MAX_PARALLEL_FILES", DEFAULT_MAX_PARALLEL_FILES))
    return max(1, min(value, 5))


def pipeline_config_options(**values: Any) -> dict[str, Any]:
    return {key: value for key, value in values.items() if value is not None}


def sanitized_config(options: dict[str, Any]) -> dict[str, Any]:
    config = asdict(build_config(**options))
    for key in list(config):
        if key.endswith("_api_key"):
            config.pop(key)
    config["pipeline_cache_version"] = PIPELINE_CACHE_VERSION
    return config


def config_hash(config: dict[str, Any]) -> str:
    payload = json.dumps(config, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def create_batch_from_uploads(
    *,
    files: list[tuple[str, bytes]],
    max_parallel_files: int,
    config_options: dict[str, Any],
    enqueue: bool = True,
) -> dict[str, Any]:
    if len(files) > MAX_BATCH_UPLOAD_FILES:
        raise ValueError(f"Upload up to {MAX_BATCH_UPLOAD_FILES} files per batch.")
    if not files:
        raise ValueError("Upload at least one file.")

    ensure_data_dirs()
    batch_id = f"batch_{uuid.uuid4().hex[:12]}"
    max_parallel_files = max(1, min(max_parallel_files, 5))
    config = sanitized_config(config_options)
    hash_value = config_hash(config)
    saved_files = []

    for filename, content in files:
        path = available_input_path(filename or "document")
        path.write_bytes(content)
        saved_files.append(
            {
                "job_id": f"job_{uuid.uuid4().hex[:12]}",
                "filename": path.name,
                "input_path": str(path),
                "file_hash": hashlib.sha256(content).hexdigest(),
            }
        )

    batch = repository.create_batch(
        batch_id=batch_id,
        max_parallel_files=max_parallel_files,
        config=config,
        config_hash=hash_value,
        files=saved_files,
    )
    if enqueue:
        try:
            enqueue_batch(batch_id)
        except Exception as error:
            message = f"Queue unavailable: {error}"
            for file in saved_files:
                repository.update_file_job(
                    file["job_id"],
                    status="failed",
                    stage="failed",
                    error=message,
                    finished_at=repository.utc_now(),
                )
            repository.refresh_batch_counts(batch_id)
            raise
    return batch


def retry_file_job(job_id: str) -> dict[str, Any] | None:
    job = repository.reset_file_for_retry(job_id)
    if job is None:
        return None
    enqueue_file(job_id)
    return job


def result_exists(path: str | Path | None) -> bool:
    return bool(path) and Path(path).exists()
