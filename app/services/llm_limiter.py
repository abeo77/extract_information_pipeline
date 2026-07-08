"""Process-local limiter for concurrent LLM calls."""

from __future__ import annotations

from contextlib import contextmanager
from threading import BoundedSemaphore, Lock
from typing import Any, Iterator


_LOCK = Lock()
_SEMAPHORES: dict[int, BoundedSemaphore] = {}


def invoke_with_llm_limit(chat_model: Any, prompt: str, max_total_calls: int | None = None):
    """Invoke a chat model while respecting a process-wide concurrency cap."""
    with llm_call_slot(max_total_calls):
        return chat_model.invoke(prompt)


@contextmanager
def llm_call_slot(max_total_calls: int | None = None) -> Iterator[None]:
    if not max_total_calls or max_total_calls <= 0:
        yield
        return

    semaphore = _semaphore_for(max_total_calls)
    semaphore.acquire()
    try:
        yield
    finally:
        semaphore.release()


def _semaphore_for(limit: int) -> BoundedSemaphore:
    with _LOCK:
        semaphore = _SEMAPHORES.get(limit)
        if semaphore is None:
            semaphore = BoundedSemaphore(limit)
            _SEMAPHORES[limit] = semaphore
        return semaphore
