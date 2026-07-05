"""Small helpers for bounded parallel work."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Callable, TypeVar


T = TypeVar("T")
R = TypeVar("R")


def ordered_parallel_map(
    items: list[T],
    worker: Callable[[T], R],
    max_workers: int = 1,
) -> list[R]:
    """Run worker across items with bounded concurrency while preserving order."""
    if max_workers <= 1 or len(items) <= 1:
        return [worker(item) for item in items]

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        return list(executor.map(worker, items))
