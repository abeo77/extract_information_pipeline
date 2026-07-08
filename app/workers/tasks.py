"""RQ tasks for running pipeline batches."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from dotenv import load_dotenv

from app.jobs import repository
from app.pipeline import run_pipeline
from app.services.file_service import output_path
from app.services.pipeline_service import build_config

load_dotenv()

STEP_PROGRESS = {
    "load": 10,
    "normalize": 20,
    "segment": 30,
    "llm1": 80,
    "merge": 93,
    "coverage": 94,
    "filter": 94,
    "local_exact": 95,
    "llm2": 97,
    "export": 98,
}


def run_batch(batch_id: str) -> None:
    batch = repository.get_batch(batch_id)
    if batch is None:
        raise ValueError(f"Batch not found: {batch_id}")

    repository.update_batch_status(batch_id, "processing")
    jobs = repository.list_file_jobs(batch_id, statuses={"queued"})
    if not jobs:
        repository.refresh_batch_counts(batch_id)
        return

    max_workers = max(1, int(batch["max_parallel_files"]))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(_process_job, job["id"]) for job in jobs]
        for future in as_completed(futures):
            future.result()
            repository.refresh_batch_counts(batch_id)

    repository.refresh_batch_counts(batch_id)


def run_file(job_id: str) -> None:
    job = repository.get_file_job(job_id)
    if job is None:
        raise ValueError(f"File job not found: {job_id}")
    _process_job(job_id)
    repository.refresh_batch_counts(job["batch_id"])


def _process_job(job_id: str) -> None:
    job = repository.get_file_job(job_id)
    if job is None or job["status"] != "queued":
        return

    now = repository.utc_now()
    repository.update_file_job(
        job_id,
        status="processing",
        stage="processing",
        progress=5,
        error=None,
        started_at=now,
        finished_at=None,
    )
    repository.refresh_batch_counts(job["batch_id"])

    cache = repository.get_cache(job["file_hash"], job["config_hash"])
    if cache and Path(cache["output_path"]).exists():
        repository.update_file_job(
            job_id,
            status="cached",
            stage="cached",
            progress=100,
            output_path=cache["output_path"],
            total_pages=cache["total_pages"],
            total_segments=cache["total_segments"],
            keyword_groups=cache["keyword_groups"],
            error=None,
            finished_at=repository.utc_now(),
        )
        return

    try:
        batch = repository.get_batch(job["batch_id"])
        if batch is None:
            raise ValueError(f"Batch not found: {job['batch_id']}")
        config_options = json.loads(batch["config_json"])
        config = build_config(**config_options)
        out = output_path(Path(job["input_path"]).name)

        result = run_pipeline(
            job["input_path"],
            out,
            config,
            on_step=lambda step: _record_step(job_id, step),
        )
        repository.update_file_job(
            job_id,
            status="success",
            stage="success",
            progress=100,
            output_path=str(out),
            total_pages=result.total_pages,
            total_segments=result.total_segments,
            keyword_groups=len(result.keyword_groups),
            error=None,
            finished_at=repository.utc_now(),
        )
        repository.upsert_cache(
            file_hash=job["file_hash"],
            config_hash=job["config_hash"],
            output_path=str(out),
            total_pages=result.total_pages,
            total_segments=result.total_segments,
            keyword_groups=len(result.keyword_groups),
        )
    except Exception as error:
        repository.update_file_job(
            job_id,
            status="failed",
            stage="failed",
            error=str(error),
            finished_at=repository.utc_now(),
        )


def _record_step(job_id: str, step: dict) -> None:
    stage = str(step.get("key") or "processing")
    repository.update_file_progress(job_id, stage, STEP_PROGRESS.get(stage, 50))
