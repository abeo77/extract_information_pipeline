"""Small helpers for bounded parallel work."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
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


def ordered_parallel_map_with_progress(
    items: list[T],
    worker: Callable[[T], R],
    max_workers: int = 1,
    on_result: Callable[[int, R], None] | None = None,
) -> list[R]:
    """Run worker across items, preserve final order, and report completed items."""
    if max_workers <= 1 or len(items) <= 1:
        results = []
        for index, item in enumerate(items):
            result = worker(item)
            if on_result:
                on_result(index, result)
            results.append(result)
        return results

    results: list[R | None] = [None] * len(items)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_lookup = {
            executor.submit(worker, item): index
            for index, item in enumerate(items)
        }
        for future in as_completed(future_lookup):
            index = future_lookup[future]
            result = future.result()
            results[index] = result
            if on_result:
                on_result(index, result)

    return [result for result in results if result is not None]
