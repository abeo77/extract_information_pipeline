"""Programmatic RQ worker entrypoint."""

from __future__ import annotations

from redis import Redis
from rq import Queue, Worker

from app.jobs.queue import QUEUE_NAME, redis_url


def main() -> None:
    connection = Redis.from_url(redis_url())
    queue = Queue(QUEUE_NAME, connection=connection)
    worker = Worker([queue], connection=connection)
    worker.work(with_scheduler=True)


if __name__ == "__main__":
    main()
