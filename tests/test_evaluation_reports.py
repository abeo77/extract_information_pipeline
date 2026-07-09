"""Evaluation report service and API tests."""

import json

from fastapi.testclient import TestClient

from api.main import app
from api.routes import evaluation_routes
from app.evaluation.report_service import list_evaluation_reports


def _write_report(path, *, accuracy, precision, recall, f1, expected, predicted, matched):
    path.write_text(
        json.dumps(
            {
                "document_name": path.name.replace("_eval_report.json", ".pdf"),
                "processing_time_seconds": 10,
                "overall_accuracy_percent": accuracy,
                "precision": precision,
                "recall": recall,
                "f1": f1,
                "summary": {
                    "expected_items": expected,
                    "predicted_items": predicted,
                    "matched_items": matched,
                    "missing_items": expected - matched,
                    "extra_items": predicted - matched,
                },
            }
        ),
        encoding="utf-8",
    )


def test_list_evaluation_reports_aggregates_metrics(tmp_path):
    _write_report(
        tmp_path / "2_eval_report.json",
        accuracy=50,
        precision=0.5,
        recall=0.75,
        f1=0.6,
        expected=4,
        predicted=6,
        matched=3,
    )
    _write_report(
        tmp_path / "1_eval_report.json",
        accuracy=100,
        precision=1,
        recall=1,
        f1=1,
        expected=2,
        predicted=2,
        matched=2,
    )

    payload = list_evaluation_reports(tmp_path)

    assert [report["filename"] for report in payload["files"]] == [
        "1_eval_report.json",
        "2_eval_report.json",
    ]
    assert payload["summary"]["files_evaluated"] == 2
    assert payload["summary"]["average_overall_accuracy_percent"] == 75
    assert payload["summary"]["average_precision_percent"] == 75
    assert payload["summary"]["expected_items"] == 6
    assert payload["summary"]["predicted_items"] == 8
    assert payload["summary"]["matched_items"] == 5
    assert payload["summary"]["missing_items"] == 1
    assert payload["summary"]["extra_items"] == 3


def test_evaluation_report_endpoints(monkeypatch):
    client = TestClient(app)

    monkeypatch.setattr(
        evaluation_routes,
        "list_evaluation_reports",
        lambda: {"files": [{"filename": "1_eval_report.json"}], "summary": {"files_evaluated": 1}},
    )
    monkeypatch.setattr(
        evaluation_routes,
        "load_evaluation_report",
        lambda filename: {"filename": filename, "matched_items": []},
    )

    list_response = client.get("/evaluation/reports")
    detail_response = client.get("/evaluation/reports/1_eval_report.json")

    assert list_response.status_code == 200
    assert list_response.json()["summary"]["files_evaluated"] == 1
    assert detail_response.status_code == 200
    assert detail_response.json()["filename"] == "1_eval_report.json"


def test_evaluation_report_detail_404(monkeypatch):
    client = TestClient(app)

    def missing_report(filename):
        raise FileNotFoundError(filename)

    monkeypatch.setattr(evaluation_routes, "load_evaluation_report", missing_report)

    response = client.get("/evaluation/reports/missing.json")

    assert response.status_code == 404
