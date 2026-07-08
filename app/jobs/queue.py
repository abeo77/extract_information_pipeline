"""RQ queue helpers."""

from __future__ import annotations

import os

QUEUE_NAME = "pipeline"
DEFAULT_REDIS_URL = "redis://localhost:6379/0"


def redis_url() -> str:
    return os.getenv("REDIS_URL", DEFAULT_REDIS_URL)


def get_queue():
    from redis import Redis
    from rq import Queue

    connection = Redis.from_url(redis_url())
    return Queue(QUEUE_NAME, connection=connection)


def enqueue_batch(batch_id: str):
    from app.workers.tasks import run_batch

    queue = get_queue()
    return queue.enqueue(run_batch, batch_id, job_timeout="2h")


def enqueue_file(job_id: str):
    from app.workers.tasks import run_file

    queue = get_queue()
    return queue.enqueue(run_file, job_id, job_timeout="1h")
