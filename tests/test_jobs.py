"""Async job system tests."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from app.jobs import repository
from app.jobs.service import create_batch_from_uploads
from app.workers import tasks


@pytest.fixture()
def isolated_jobs(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("JOB_DB_PATH", str(tmp_path / "jobs.db"))
    repository.init_db()
    return tmp_path


def test_create_batch_from_uploads_creates_ten_file_jobs(isolated_jobs):
    batch = create_batch_from_uploads(
        files=[(f"contract_{index}.txt", b"hello") for index in range(10)],
        max_parallel_files=2,
        config_options={"max_parallel_llm_calls": 3},
        enqueue=False,
    )

    stored = repository.get_batch_with_files(batch["id"])

    assert stored["total_files"] == 10
    assert stored["queued_count"] == 10
    assert len(stored["files"]) == 10
    assert {job["status"] for job in stored["files"]} == {"queued"}


def test_create_batch_from_uploads_rejects_more_than_ten_files(isolated_jobs):
    with pytest.raises(ValueError, match="Upload up to 10 files"):
        create_batch_from_uploads(
            files=[(f"contract_{index}.txt", b"hello") for index in range(11)],
            max_parallel_files=2,
            config_options={},
            enqueue=False,
        )


def test_worker_uses_cache_without_running_pipeline(isolated_jobs, monkeypatch):
    batch = create_batch_from_uploads(
        files=[("cached.txt", b"same file")],
        max_parallel_files=2,
        config_options={},
        enqueue=False,
    )
    job = repository.list_file_jobs(batch["id"])[0]
    output = Path("data/output/cached_result.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("{}", encoding="utf-8")
    repository.upsert_cache(
        file_hash=job["file_hash"],
        config_hash=job["config_hash"],
        output_path=str(output),
        total_pages=1,
        total_segments=2,
        keyword_groups=3,
    )

    def fail_if_called(*args, **kwargs):
        raise AssertionError("run_pipeline should not be called")

    monkeypatch.setattr(tasks, "run_pipeline", fail_if_called)

    tasks.run_batch(batch["id"])
    updated = repository.get_batch_with_files(batch["id"])

    assert updated["status"] == "completed"
    assert updated["cached_count"] == 1
    assert updated["files"][0]["status"] == "cached"
    assert updated["files"][0]["keyword_groups"] == 3


def test_worker_continues_when_one_file_fails(isolated_jobs, monkeypatch):
    batch = create_batch_from_uploads(
        files=[("good.txt", b"good"), ("bad.txt", b"bad")],
        max_parallel_files=2,
        config_options={},
        enqueue=False,
    )

    def fake_run_pipeline(file_path, output_path, config, on_step=None, **kwargs):
        if on_step:
            on_step({"key": "segment"})
        if Path(file_path).name == "bad.txt":
            raise RuntimeError("bad file")
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_text("{}", encoding="utf-8")
        return SimpleNamespace(total_pages=1, total_segments=2, keyword_groups=[{}])

    monkeypatch.setattr(tasks, "run_pipeline", fake_run_pipeline)

    tasks.run_batch(batch["id"])
    updated = repository.get_batch_with_files(batch["id"])
    statuses = {job["filename"]: job["status"] for job in updated["files"]}

    assert updated["status"] == "completed"
    assert updated["succeeded_count"] == 1
    assert updated["failed_count"] == 1
    assert statuses == {"good.txt": "success", "bad.txt": "failed"}


def test_core_batch_flow_writes_outputs_for_multiple_files(isolated_jobs, monkeypatch):
    batch = create_batch_from_uploads(
        files=[
            ("contract_a.txt", b"Agreement A"),
            ("contract_b.txt", b"Agreement B"),
            ("contract_c.txt", b"Agreement C"),
        ],
        max_parallel_files=3,
        config_options={"max_parallel_llm_calls": 2},
        enqueue=False,
    )

    def fake_run_pipeline(file_path, output_path, config, on_step=None, **kwargs):
        if on_step:
            on_step({"key": "load"})
            on_step({"key": "segment"})
            on_step({"key": "llm1"})
            on_step({"key": "export"})
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_text(
            '{"document_name":"%s","keyword_groups":[{"representative_keyword":"Payment"}]}'
            % Path(file_path).name,
            encoding="utf-8",
        )
        return SimpleNamespace(
            total_pages=2,
            total_segments=5,
            keyword_groups=[{"representative_keyword": "Payment"}],
        )

    monkeypatch.setattr(tasks, "run_pipeline", fake_run_pipeline)

    tasks.run_batch(batch["id"])
    updated = repository.get_batch_with_files(batch["id"])

    assert updated["status"] == "completed"
    assert updated["succeeded_count"] == 3
    assert updated["failed_count"] == 0
    for job in updated["files"]:
        assert job["status"] == "success"
        assert job["stage"] == "success"
        assert job["progress"] == 100
        assert Path(job["output_path"]).exists()
