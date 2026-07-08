"""Global LLM concurrency limiter tests."""

from concurrent.futures import ThreadPoolExecutor
from threading import Lock
import time

from app.services.llm_limiter import invoke_with_llm_limit


class CountingModel:
    def __init__(self):
        self.active = 0
        self.max_active = 0
        self.lock = Lock()

    def invoke(self, prompt):
        with self.lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        time.sleep(0.02)
        with self.lock:
            self.active -= 1
        return {"prompt": prompt}


def test_invoke_with_llm_limit_caps_concurrent_calls():
    model = CountingModel()

    with ThreadPoolExecutor(max_workers=6) as executor:
        results = list(
            executor.map(
                lambda index: invoke_with_llm_limit(model, f"prompt-{index}", max_total_calls=2),
                range(6),
            )
        )

    assert len(results) == 6
    assert model.max_active <= 2
