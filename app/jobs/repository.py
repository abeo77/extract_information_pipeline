"""SQLite repository for batch and file job state."""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator

DEFAULT_JOB_DB_PATH = Path("data/jobs/jobs.db")
TERMINAL_FILE_STATUSES = {"success", "failed", "cached"}


def job_db_path() -> Path:
    return Path(os.getenv("JOB_DB_PATH", DEFAULT_JOB_DB_PATH))


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    path = job_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA foreign_keys=ON")
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def init_db() -> None:
    with connect() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS batches (
                id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                total_files INTEGER NOT NULL,
                max_parallel_files INTEGER NOT NULL,
                config_json TEXT NOT NULL,
                config_hash TEXT NOT NULL,
                queued_count INTEGER NOT NULL DEFAULT 0,
                processing_count INTEGER NOT NULL DEFAULT 0,
                succeeded_count INTEGER NOT NULL DEFAULT 0,
                failed_count INTEGER NOT NULL DEFAULT 0,
                cached_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                started_at TEXT,
                finished_at TEXT
            );

            CREATE TABLE IF NOT EXISTS file_jobs (
                id TEXT PRIMARY KEY,
                batch_id TEXT NOT NULL REFERENCES batches(id) ON DELETE CASCADE,
                filename TEXT NOT NULL,
                input_path TEXT NOT NULL,
                file_hash TEXT NOT NULL,
                config_hash TEXT NOT NULL,
                status TEXT NOT NULL,
                stage TEXT NOT NULL,
                progress INTEGER NOT NULL DEFAULT 0,
                output_path TEXT,
                total_pages INTEGER NOT NULL DEFAULT 0,
                total_segments INTEGER NOT NULL DEFAULT 0,
                keyword_groups INTEGER NOT NULL DEFAULT 0,
                error TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                started_at TEXT,
                finished_at TEXT
            );

            CREATE TABLE IF NOT EXISTS file_cache (
                file_hash TEXT NOT NULL,
                config_hash TEXT NOT NULL,
                output_path TEXT NOT NULL,
                total_pages INTEGER NOT NULL DEFAULT 0,
                total_segments INTEGER NOT NULL DEFAULT 0,
                keyword_groups INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (file_hash, config_hash)
            );
            """
        )


def create_batch(
    *,
    batch_id: str,
    max_parallel_files: int,
    config: dict[str, Any],
    config_hash: str,
    files: list[dict[str, str]],
) -> dict[str, Any]:
    init_db()
    now = utc_now()
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO batches (
                id, status, total_files, max_parallel_files, config_json, config_hash,
                queued_count, created_at, updated_at
            )
            VALUES (?, 'queued', ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                batch_id,
                len(files),
                max_parallel_files,
                json.dumps(config, sort_keys=True),
                config_hash,
                len(files),
                now,
                now,
            ),
        )
        for file in files:
            connection.execute(
                """
                INSERT INTO file_jobs (
                    id, batch_id, filename, input_path, file_hash, config_hash,
                    status, stage, progress, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, 'queued', 'queued', 0, ?, ?)
                """,
                (
                    file["job_id"],
                    batch_id,
                    file["filename"],
                    file["input_path"],
                    file["file_hash"],
                    config_hash,
                    now,
                    now,
                ),
            )
    return get_batch(batch_id) or {}


def get_batch(batch_id: str) -> dict[str, Any] | None:
    init_db()
    with connect() as connection:
        return row_to_dict(
            connection.execute("SELECT * FROM batches WHERE id = ?", (batch_id,)).fetchone()
        )


def get_file_job(job_id: str) -> dict[str, Any] | None:
    init_db()
    with connect() as connection:
        return row_to_dict(
            connection.execute("SELECT * FROM file_jobs WHERE id = ?", (job_id,)).fetchone()
        )


def list_file_jobs(batch_id: str, statuses: set[str] | None = None) -> list[dict[str, Any]]:
    init_db()
    query = "SELECT * FROM file_jobs WHERE batch_id = ?"
    params: list[Any] = [batch_id]
    if statuses:
        placeholders = ",".join("?" for _ in statuses)
        query += f" AND status IN ({placeholders})"
        params.extend(sorted(statuses))
    query += " ORDER BY created_at, id"
    with connect() as connection:
        return [dict(row) for row in connection.execute(query, params).fetchall()]


def get_batch_with_files(batch_id: str) -> dict[str, Any] | None:
    batch = get_batch(batch_id)
    if batch is None:
        return None
    batch["files"] = list_file_jobs(batch_id)
    return batch


def update_batch_status(batch_id: str, status: str) -> None:
    now = utc_now()
    fields = ["status = ?", "updated_at = ?"]
    params: list[Any] = [status, now]
    if status == "processing":
        fields.append("started_at = COALESCE(started_at, ?)")
        params.append(now)
    if status in {"completed", "failed"}:
        fields.append("finished_at = COALESCE(finished_at, ?)")
        params.append(now)
    params.append(batch_id)
    with connect() as connection:
        connection.execute(
            f"UPDATE batches SET {', '.join(fields)} WHERE id = ?",
            params,
        )


def update_file_job(job_id: str, **updates: Any) -> None:
    if not updates:
        return
    updates["updated_at"] = utc_now()
    assignments = [f"{key} = ?" for key in updates]
    params = list(updates.values())
    params.append(job_id)
    with connect() as connection:
        connection.execute(
            f"UPDATE file_jobs SET {', '.join(assignments)} WHERE id = ?",
            params,
        )


def update_file_progress(job_id: str, stage: str, progress: int) -> None:
    update_file_job(job_id, stage=stage, progress=max(0, min(progress, 99)))


def reset_file_for_retry(job_id: str) -> dict[str, Any] | None:
    job = get_file_job(job_id)
    if job is None or job["status"] != "failed":
        return None
    update_file_job(
        job_id,
        status="queued",
        stage="queued",
        progress=0,
        error=None,
        output_path=None,
        total_pages=0,
        total_segments=0,
        keyword_groups=0,
        started_at=None,
        finished_at=None,
    )
    refresh_batch_counts(job["batch_id"])
    return get_file_job(job_id)


def upsert_cache(
    *,
    file_hash: str,
    config_hash: str,
    output_path: str,
    total_pages: int,
    total_segments: int,
    keyword_groups: int,
) -> None:
    now = utc_now()
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO file_cache (
                file_hash, config_hash, output_path, total_pages, total_segments,
                keyword_groups, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(file_hash, config_hash) DO UPDATE SET
                output_path = excluded.output_path,
                total_pages = excluded.total_pages,
                total_segments = excluded.total_segments,
                keyword_groups = excluded.keyword_groups,
                updated_at = excluded.updated_at
            """,
            (
                file_hash,
                config_hash,
                output_path,
                total_pages,
                total_segments,
                keyword_groups,
                now,
                now,
            ),
        )


def get_cache(file_hash: str, config_hash: str) -> dict[str, Any] | None:
    init_db()
    with connect() as connection:
        return row_to_dict(
            connection.execute(
                """
                SELECT * FROM file_cache
                WHERE file_hash = ? AND config_hash = ?
                """,
                (file_hash, config_hash),
            ).fetchone()
        )


def refresh_batch_counts(batch_id: str) -> dict[str, Any] | None:
    init_db()
    now = utc_now()
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT status, COUNT(*) AS count
            FROM file_jobs
            WHERE batch_id = ?
            GROUP BY status
            """,
            (batch_id,),
        ).fetchall()
        counts = {row["status"]: row["count"] for row in rows}
        batch = connection.execute(
            "SELECT total_files FROM batches WHERE id = ?",
            (batch_id,),
        ).fetchone()
        if batch is None:
            return None

        queued = counts.get("queued", 0)
        processing = counts.get("processing", 0)
        succeeded = counts.get("success", 0)
        failed = counts.get("failed", 0)
        cached = counts.get("cached", 0)
        terminal = succeeded + failed + cached
        total_files = int(batch["total_files"])

        if terminal == total_files:
            status = "failed" if failed == total_files else "completed"
            finished_at = now
        elif processing:
            status = "processing"
            finished_at = None
        else:
            status = "queued"
            finished_at = None

        connection.execute(
            """
            UPDATE batches
            SET status = ?, queued_count = ?, processing_count = ?,
                succeeded_count = ?, failed_count = ?, cached_count = ?,
                updated_at = ?,
                started_at = CASE
                    WHEN ? = 'processing' THEN COALESCE(started_at, ?)
                    ELSE started_at
                END,
                finished_at = CASE
                    WHEN ? IS NOT NULL THEN COALESCE(finished_at, ?)
                    ELSE NULL
                END
            WHERE id = ?
            """,
            (
                status,
                queued,
                processing,
                succeeded,
                failed,
                cached,
                now,
                status,
                now,
                finished_at,
                finished_at,
                batch_id,
            ),
        )
    return get_batch(batch_id)
