"""Run all ground-truth evaluations and write a Markdown summary."""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

from app.evaluation.evaluate_ground_truth import compare_keywords
from app.evaluation.report_service import list_evaluation_reports
from app.services.result_service import save_json

DEFAULT_RESULT_DIR = Path("data/output")
DEFAULT_GROUND_TRUTH_DIR = Path("data/ground_truth")
DEFAULT_EVALUATION_DIR = Path("data/evaluation")

README_TITLE = "# Evaluation Report"


@dataclass(frozen=True)
class EvaluationRun:
    number: int
    result_path: Path
    ground_truth_path: Path
    report_path: Path


def run_evaluation_suite(
    *,
    result_dir: str | Path = DEFAULT_RESULT_DIR,
    ground_truth_dir: str | Path = DEFAULT_GROUND_TRUTH_DIR,
    output_dir: str | Path = DEFAULT_EVALUATION_DIR,
    numbers: Iterable[int] | None = None,
) -> dict:
    """Evaluate newest result files and write JSON reports plus README."""
    result_dir = Path(result_dir)
    ground_truth_dir = Path(ground_truth_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    selected_numbers = (
        list(numbers)
        if numbers is not None
        else _available_numbers(ground_truth_dir)
    )
    runs: list[EvaluationRun] = []
    skipped: list[dict[str, str | int]] = []

    for number in selected_numbers:
        ground_truth_path = ground_truth_dir / f"ground_truth_{number}.json"
        result_path = newest_result_for_number(number, result_dir)
        if result_path is None or not ground_truth_path.exists():
            skipped.append(
                {
                    "number": number,
                    "reason": "missing result" if result_path is None else "missing ground truth",
                }
            )
            continue

        report_path = output_dir / f"{number}_eval_report.json"
        report = compare_keywords(result_path, ground_truth_path)
        save_json(report, report_path)
        runs.append(
            EvaluationRun(
                number=number,
                result_path=result_path,
                ground_truth_path=ground_truth_path,
                report_path=report_path,
            )
        )

    summary = list_evaluation_reports(output_dir)
    readme_path = output_dir / "README.md"
    readme_path.write_text(
        build_evaluation_readme(summary=summary, runs=runs, skipped=skipped),
        encoding="utf-8",
    )

    return {
        "output_dir": output_dir,
        "readme_path": readme_path,
        "runs": runs,
        "skipped": skipped,
        "summary": summary["summary"],
    }


def newest_result_for_number(
    number: int,
    result_dir: str | Path = DEFAULT_RESULT_DIR,
) -> Path | None:
    """Return newest result matching forms like 4_result.json or 4_3_result.json."""
    result_dir = Path(result_dir)
    pattern = re.compile(rf"^{number}(?:_\d+)?_result\.json$")
    candidates = [path for path in result_dir.glob("*_result.json") if pattern.match(path.name)]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def build_evaluation_readme(
    *,
    summary: dict,
    runs: list[EvaluationRun],
    skipped: list[dict[str, str | int]],
) -> str:
    """Build README.md content from generated evaluation report summaries."""
    report_summary = summary["summary"]
    report_files = summary["files"]
    run_by_number = {run.number: run for run in runs}

    lines = [
        README_TITLE,
        "",
        f"Generated at: `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`",
        "",
        "Generated from the newest `data/output/*_result.json` for each document number "
        "against `data/ground_truth/ground_truth_*.json`.",
        "",
        "## Summary",
        "",
        *_summary_table(report_summary),
        "",
        "## Per-File Results",
        "",
        *_per_file_header(),
    ]

    for report in report_files:
        number = _number_from_report_filename(report["filename"])
        lines.append(_per_file_row(number, report, run_by_number.get(number)))

    lines.extend(["", "## Highlights", "", *_highlight_lines(report_files)])
    lines.extend(["", "## Generated Files", "", *_generated_file_lines(runs)])
    if skipped:
        lines.extend(["", "## Skipped", "", *_skipped_lines(skipped)])
    lines.extend(["", "## Notes", "", *_note_lines(), ""])
    return "\n".join(lines)


def _summary_table(summary: dict) -> list[str]:
    rows = [
        ("Files evaluated", summary["files_evaluated"]),
        ("Average overall accuracy", _percent(summary["average_overall_accuracy_percent"])),
        (
            "Average processing time",
            f"{summary['average_processing_time_seconds']:.2f} seconds/file",
        ),
        ("Average precision", _percent(summary["average_precision_percent"])),
        ("Average recall", _percent(summary["average_recall_percent"])),
        ("Average F1", _percent(summary["average_f1_percent"])),
        ("Total expected items", summary["expected_items"]),
        ("Total predicted items", summary["predicted_items"]),
        ("Total matched items", summary["matched_items"]),
        ("Total missing items", summary["missing_items"]),
        ("Total extra items", summary["extra_items"]),
    ]
    return [
        "| Metric | Value |",
        "| --- | ---: |",
        *[f"| {key} | {value} |" for key, value in rows],
    ]


def _per_file_header() -> list[str]:
    columns = [
        "File",
        "Document",
        "Result file",
        "Processing time (s)",
        "Overall accuracy",
        "Precision",
        "Recall",
        "F1",
        "Expected",
        "Predicted",
        "Matched",
        "Missing",
        "Extra",
    ]
    alignments = ["---:", "---", "---", *["---:"] * 10]
    return [f"| {' | '.join(columns)} |", f"| {' | '.join(alignments)} |"]


def _per_file_row(number: int, report: dict, run: EvaluationRun | None) -> str:
    result_file = run.result_path.name if run else "-"
    values = [
        number,
        report.get("document_name") or "-",
        f"`{result_file}`",
        f"{float(report.get('processing_time_seconds') or 0):.2f}",
        _percent(report.get("overall_accuracy_percent") or 0),
        _ratio_percent(report.get("precision") or 0),
        _ratio_percent(report.get("recall") or 0),
        _ratio_percent(report.get("f1") or 0),
        report.get("expected_items") or 0,
        report.get("predicted_items") or 0,
        report.get("matched_items") or 0,
        report.get("missing_items") or 0,
        report.get("extra_items") or 0,
    ]
    return f"| {' | '.join(str(value) for value in values)} |"


def _highlight_lines(report_files: list[dict]) -> list[str]:
    if not report_files:
        return ["- No evaluation reports were generated."]

    best = max(report_files, key=_accuracy)
    lowest = min(report_files, key=_accuracy)
    slowest = max(report_files, key=_processing_time)
    return [
        _highlight("Best accuracy", best, _percent(_accuracy(best))),
        _highlight("Lowest accuracy", lowest, _percent(_accuracy(lowest))),
        _highlight("Slowest file", slowest, f"{_processing_time(slowest):.2f}s"),
    ]


def _generated_file_lines(runs: list[EvaluationRun]) -> list[str]:
    if not runs:
        return ["- No JSON reports were generated."]
    return [
        f"- File {run.number}: `{run.report_path.name}` from `{run.result_path.name}`"
        for run in runs
    ]


def _skipped_lines(skipped: list[dict[str, str | int]]) -> list[str]:
    return [f"- File {item['number']}: {item['reason']}" for item in skipped]


def _note_lines() -> list[str]:
    return [
        "- Scores use the weighted evaluator in `app.evaluation.evaluate_ground_truth`.",
        "- If multiple result files share the same leading number, "
        "this report uses the newest one by modification time.",
        "- Re-run with `python -m app.evaluation.run_evaluation_suite`.",
    ]


def _available_numbers(ground_truth_dir: Path) -> list[int]:
    numbers = []
    for path in ground_truth_dir.glob("ground_truth_*.json"):
        match = re.match(r"ground_truth_(\d+)\.json$", path.name)
        if match:
            numbers.append(int(match.group(1)))
    return sorted(numbers)


def _number_from_report_filename(filename: str) -> int:
    prefix = filename.split("_", 1)[0]
    return int(prefix) if prefix.isdigit() else 0


def _highlight(label: str, report: dict, value: str) -> str:
    number = _number_from_report_filename(report["filename"])
    return f"- {label}: file {number} (`{report['filename']}`) at {value}."


def _accuracy(report: dict) -> float:
    return float(report.get("overall_accuracy_percent") or 0)


def _processing_time(report: dict) -> float:
    return float(report.get("processing_time_seconds") or 0)


def _percent(value: float) -> str:
    return f"{float(value):.2f}%"


def _ratio_percent(value: float) -> str:
    return _percent(float(value) * 100)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate newest result files and write reports to data/evaluation."
    )
    parser.add_argument("--result-dir", type=Path, default=DEFAULT_RESULT_DIR)
    parser.add_argument("--ground-truth-dir", type=Path, default=DEFAULT_GROUND_TRUTH_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_EVALUATION_DIR)
    parser.add_argument("--numbers", nargs="*", type=int, default=None)
    args = parser.parse_args(argv)

    result = run_evaluation_suite(
        result_dir=args.result_dir,
        ground_truth_dir=args.ground_truth_dir,
        output_dir=args.output_dir,
        numbers=args.numbers,
    )
    print(f"Generated {len(result['runs'])} evaluation report(s).")
    print(f"README: {result['readme_path']}")
    if result["skipped"]:
        print(f"Skipped {len(result['skipped'])} file(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
