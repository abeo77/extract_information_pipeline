"""Non-UI smoke runner for core batch processing."""

from __future__ import annotations

import argparse
from pathlib import Path

from app.jobs import repository
from app.jobs.service import create_batch_from_uploads, pipeline_config_options
from app.workers.tasks import run_batch


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run core batch processing without UI or Redis.")
    parser.add_argument("files", nargs="+", help="PDF/TXT files to process")
    parser.add_argument("--max-parallel-files", type=int, default=3)
    parser.add_argument("--max-parallel-llm-calls", type=int, default=3)
    parser.add_argument("--max-total-llm-calls", type=int, default=8)
    parser.add_argument("--keyword-batch-size", type=int, default=None)
    parser.add_argument("--evidence-batch-size", type=int, default=50)
    parser.add_argument("--max-evidence-segments-per-group", type=int, default=2)
    parser.add_argument("--no-coverage", action="store_false", dest="coverage_enabled", default=None)
    parser.add_argument("--coverage-max-groups", type=int, default=5)
    parser.add_argument("--coverage-mode", choices=("adaptive", "broad", "off"), default=None)
    parser.add_argument(
        "--no-filter-low-confidence-groups",
        action="store_false",
        dest="filter_low_confidence_groups",
        default=None,
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    uploads = [(Path(file).name, Path(file).read_bytes()) for file in args.files]
    batch = create_batch_from_uploads(
        files=uploads,
        max_parallel_files=args.max_parallel_files,
        config_options=pipeline_config_options(
            max_parallel_llm_calls=args.max_parallel_llm_calls,
            max_total_llm_calls=args.max_total_llm_calls,
            keyword_batch_size=args.keyword_batch_size,
            evidence_batch_size=args.evidence_batch_size,
            max_evidence_segments_per_group=args.max_evidence_segments_per_group,
            coverage_enabled=args.coverage_enabled,
            coverage_max_groups=args.coverage_max_groups,
            coverage_mode=args.coverage_mode,
            filter_low_confidence_groups=args.filter_low_confidence_groups,
        ),
        enqueue=False,
    )
    run_batch(batch["id"])
    report = repository.get_batch_with_files(batch["id"])
    if report is None:
        print("Batch not found after processing.")
        return 1

    print(f"Batch: {report['id']}")
    print(f"Status: {report['status']}")
    print(
        "Counts: "
        f"queued={report['queued_count']} "
        f"processing={report['processing_count']} "
        f"success={report['succeeded_count']} "
        f"cached={report['cached_count']} "
        f"failed={report['failed_count']}"
    )
    for job in report["files"]:
        print(
            f"- {job['filename']} | {job['status']} | "
            f"groups={job['keyword_groups']} | output={job['output_path'] or '-'}"
        )
        if job["error"]:
            print(f"  error: {job['error']}")
    return 0 if report["failed_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
