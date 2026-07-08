"""Pipeline API route tests."""

from pathlib import Path
from types import SimpleNamespace

from api.routes import pipeline_routes
from api.schemas.request_schemas import PipelineBatchRunRequest


def test_run_contract_pipeline_batch_preserves_order_and_reports_errors(monkeypatch):
    def fake_run_pipeline(file_path, output_path, config):
        if Path(file_path).name == "bad.pdf":
            raise RuntimeError("bad file")
        return SimpleNamespace(
            total_pages=1,
            total_segments=2,
            keyword_groups=[{"representative_keyword": "Effective Date"}],
        )

    monkeypatch.setattr(pipeline_routes, "run_pipeline", fake_run_pipeline)

    response = pipeline_routes.run_contract_pipeline_batch(
        PipelineBatchRunRequest(
            file_paths=[
                Path("data/input/a.pdf"),
                Path("data/input/bad.pdf"),
                Path("data/input/c.pdf"),
            ],
            max_parallel_files=2,
        )
    )

    assert response.total_files == 3
    assert response.succeeded == 2
    assert response.failed == 1
    assert response.max_parallel_files == 2
    assert [item.file_path.name for item in response.results] == ["a.pdf", "bad.pdf", "c.pdf"]
    assert [item.status for item in response.results] == ["success", "error", "success"]
    assert response.results[0].output_path == Path("data/output/a_result.json")
    assert response.results[1].error == "bad file"
