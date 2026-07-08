"""CLI entrypoint for the contract keyword pipeline."""

import argparse
import hashlib
import shutil
import sys
from pathlib import Path

from dotenv import load_dotenv

from app.jobs import repository
from app.jobs.service import config_hash, sanitized_config
from app.pipeline import run_pipeline
from app.services.pipeline_service import (
    DEFAULT_EVIDENCE_BATCH_SIZE,
    DEFAULT_KEYWORD_BATCH_SIZE,
    DEFAULT_MAX_EVIDENCE_SEGMENTS_PER_GROUP,
    DEFAULT_MAX_PARALLEL_LLM_CALLS,
    DEFAULT_MAX_TOTAL_LLM_CALLS,
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
    parser.add_argument(
        "--max-total-llm-calls",
        type=int,
        default=DEFAULT_MAX_TOTAL_LLM_CALLS,
    )
    parser.add_argument("--no-fast-exact", action="store_false", dest="fast_exact", default=None)
    parser.add_argument("--no-coverage", action="store_false", dest="coverage_enabled", default=None)
    parser.add_argument("--coverage-max-groups", type=int, default=None)
    parser.add_argument("--coverage-mode", choices=("adaptive", "broad", "off"), default=None)
    parser.add_argument(
        "--no-filter-low-confidence-groups",
        action="store_false",
        dest="filter_low_confidence_groups",
        default=None,
    )
    parser.add_argument("--no-cache", action="store_false", dest="use_cache", default=True)
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
    cache_key = None if _debug_requested(args) else _cache_key(args)
    try:
        if args.use_cache and cache_key:
            cached = repository.get_cache(*cache_key)
            if cached and Path(cached["output_path"]).exists():
                _copy_cached_output(Path(cached["output_path"]), args.output)
                repository.upsert_cache(
                    file_hash=cache_key[0],
                    config_hash=cache_key[1],
                    output_path=str(args.output),
                    total_pages=cached["total_pages"],
                    total_segments=cached["total_segments"],
                    keyword_groups=cached["keyword_groups"],
                )
                print(f"[CACHE] Reused cached output at {args.output}")
                return 0

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
        if args.use_cache and cache_key:
            result = load_result_summary(args.output)
            repository.upsert_cache(
                file_hash=cache_key[0],
                config_hash=cache_key[1],
                output_path=str(args.output),
                total_pages=result["total_pages"],
                total_segments=result["total_segments"],
                keyword_groups=result["keyword_groups"],
            )
    except SystemExit:
        raise
    except Exception as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    return 0


def _cache_key(args: argparse.Namespace) -> tuple[str, str] | None:
    if not args.file.exists() or not args.file.is_file():
        return None
    file_hash = hashlib.sha256(args.file.read_bytes()).hexdigest()
    config = sanitized_config(vars(args))
    return file_hash, config_hash(config)


def _debug_requested(args: argparse.Namespace) -> bool:
    return any(
        [
            args.debug_load,
            args.debug_load_full,
            args.debug_normalize,
            args.debug_normalize_full,
            args.debug_segments,
            args.debug_segments_full,
            args.debug_llm1_input,
        ]
    )


def _copy_cached_output(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if source.resolve() == target.resolve():
        return
    shutil.copyfile(source, target)


def load_result_summary(path: Path) -> dict[str, int]:
    import json

    data = json.loads(path.read_text(encoding="utf-8"))
    return {
        "total_pages": int(data.get("total_pages") or 0),
        "total_segments": int(data.get("total_segments") or 0),
        "keyword_groups": len(data.get("keyword_groups", [])),
    }


if __name__ == "__main__":
    raise SystemExit(main())
