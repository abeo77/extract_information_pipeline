"""Helpers for reading generated evaluation reports."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.services.result_service import load_json

DEFAULT_EVALUATION_REPORT_DIR = Path("data/evaluation")
Report = dict[str, Any]


def list_evaluation_reports(report_dir: str | Path = DEFAULT_EVALUATION_REPORT_DIR) -> Report:
    """Return compact per-file metrics plus aggregate totals for generated reports."""
    directory = Path(report_dir)
    reports = [_report_summary(path) for path in _report_files(directory)]
    return {
        "report_dir": directory,
        "files": reports,
        "summary": _aggregate_reports(reports),
    }


def load_evaluation_report(
    filename: str,
    report_dir: str | Path = DEFAULT_EVALUATION_REPORT_DIR,
) -> dict[str, Any]:
    """Load one evaluation report by filename from the configured report directory."""
    path = Path(report_dir) / Path(filename).name
    if not path.exists():
        raise FileNotFoundError(path)
    return load_json(path)


def _report_files(directory: Path) -> list[Path]:
    if not directory.exists():
        return []
    return sorted(directory.glob("*_eval_report.json"), key=_report_sort_key)


def _report_sort_key(path: Path) -> tuple[int, str]:
    prefix = path.name.split("_", 1)[0]
    return (int(prefix) if prefix.isdigit() else 10**9, path.name)


def _report_summary(path: Path) -> Report:
    report = load_json(path)
    summary = report.get("summary", {})
    return {
        "filename": path.name,
        "path": path,
        "document_name": report.get("document_name"),
        "processing_time_seconds": report.get("processing_time_seconds"),
        "overall_accuracy_percent": report.get(
            "overall_accuracy_percent",
            report.get("accuracy_percent"),
        ),
        "precision": report.get("precision", 0),
        "recall": report.get("recall", 0),
        "f1": report.get("f1", 0),
        "expected_items": summary.get("expected_items", report.get("expected", 0)),
        "predicted_items": summary.get("predicted_items", report.get("found", 0)),
        "matched_items": summary.get("matched_items", report.get("matched", 0)),
        "missing_items": summary.get("missing_items", len(report.get("missing", []))),
        "extra_items": summary.get("extra_items", len(report.get("extra", []))),
    }


def _aggregate_reports(reports: list[Report]) -> Report:
    files_evaluated = len(reports)
    expected_items = sum(int(report["expected_items"] or 0) for report in reports)
    predicted_items = sum(int(report["predicted_items"] or 0) for report in reports)
    matched_items = sum(int(report["matched_items"] or 0) for report in reports)
    missing_items = sum(int(report["missing_items"] or 0) for report in reports)
    extra_items = sum(int(report["extra_items"] or 0) for report in reports)
    total_processing_time = sum(float(report["processing_time_seconds"] or 0) for report in reports)

    return {
        "files_evaluated": files_evaluated,
        "average_overall_accuracy_percent": _mean_percent(reports, "overall_accuracy_percent"),
        "average_processing_time_seconds": round(total_processing_time / files_evaluated, 2)
        if files_evaluated
        else 0,
        "average_precision_percent": _mean_ratio_percent(reports, "precision"),
        "average_recall_percent": _mean_ratio_percent(reports, "recall"),
        "average_f1_percent": _mean_ratio_percent(reports, "f1"),
        "expected_items": expected_items,
        "predicted_items": predicted_items,
        "matched_items": matched_items,
        "missing_items": missing_items,
        "extra_items": extra_items,
    }


def _mean_percent(reports: list[Report], key: str) -> float:
    values = [float(report.get(key) or 0) for report in reports]
    return round(sum(values) / len(values), 2) if values else 0


def _mean_ratio_percent(reports: list[Report], key: str) -> float:
    values = [float(report.get(key) or 0) * 100 for report in reports]
    return round(sum(values) / len(values), 2) if values else 0
