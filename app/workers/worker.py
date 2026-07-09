"""Programmatic RQ worker entrypoint."""

from __future__ import annotations

import os

from redis import Redis
from rq import Queue, SimpleWorker, Worker

from app.jobs.queue import QUEUE_NAME, redis_url


def main() -> None:
    connection = Redis.from_url(redis_url())
    queue = Queue(QUEUE_NAME, connection=connection)
    worker_class = _worker_class()
    worker = worker_class([queue], connection=connection)
    worker.work(with_scheduler=worker_class is Worker)


def _worker_class():
    return SimpleWorker if os.name == "nt" else Worker


if __name__ == "__main__":
    main()
