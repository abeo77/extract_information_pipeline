"""CLI entrypoint for the contract keyword pipeline."""

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

from app.pipeline import run_pipeline
from app.services.pipeline_service import (
    DEFAULT_EVIDENCE_BATCH_SIZE,
    DEFAULT_KEYWORD_BATCH_SIZE,
    DEFAULT_MAX_EVIDENCE_SEGMENTS_PER_GROUP,
    DEFAULT_MAX_PARALLEL_LLM_CALLS,
    build_config,
)

load_dotenv()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run contract keyword extraction.")
    parser.add_argument("--file", required=True, type=Path)
    parser.add_argument("--output", type=Path, default=Path("data/output/result.json"))
    parser.add_argument("--llm-provider", default=None)
    parser.add_argument("--llm-model", default=None)
    parser.add_argument("--llm-api-key", default=None)
    parser.add_argument("--llm-base-url", default=None)
    parser.add_argument("--llm1-provider", default=None)
    parser.add_argument("--llm1-model", default=None)
    parser.add_argument("--llm1-api-key", default=None)
    parser.add_argument("--llm1-base-url", default=None)
    parser.add_argument("--llm2-provider", default=None)
    parser.add_argument("--llm2-model", default=None)
    parser.add_argument("--llm2-api-key", default=None)
    parser.add_argument("--llm2-base-url", default=None)
    parser.add_argument(
        "--keyword-batch-size",
        "--grouping-batch-size",
        dest="keyword_batch_size",
        type=int,
        default=DEFAULT_KEYWORD_BATCH_SIZE,
    )
    parser.add_argument("--evidence-batch-size", type=int, default=DEFAULT_EVIDENCE_BATCH_SIZE)
    parser.add_argument(
        "--max-evidence-segments-per-group",
        type=int,
        default=DEFAULT_MAX_EVIDENCE_SEGMENTS_PER_GROUP,
    )
    parser.add_argument(
        "--max-parallel-llm-calls",
        type=int,
        default=DEFAULT_MAX_PARALLEL_LLM_CALLS,
    )
    parser.add_argument("--include-admin-sections", action="store_true", default=None)
    parser.add_argument("--debug-load", action="store_true")
    parser.add_argument("--debug-load-full", action="store_true")
    parser.add_argument("--debug-normalize", action="store_true")
    parser.add_argument("--debug-normalize-full", action="store_true")
    parser.add_argument("--debug-segments", action="store_true")
    parser.add_argument("--debug-segments-full", action="store_true")
    parser.add_argument("--debug-llm1-input", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = build_config(**vars(args))
    try:
        run_pipeline(
            file_path=args.file,
            output_path=args.output,
            config=config,
            debug_load=args.debug_load,
            debug_load_full=args.debug_load_full,
            debug_normalize=args.debug_normalize,
            debug_normalize_full=args.debug_normalize_full,
            debug_segments=args.debug_segments,
            debug_segments_full=args.debug_segments_full,
            debug_llm1_input=args.debug_llm1_input,
        )
    except SystemExit:
        raise
    except Exception as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
