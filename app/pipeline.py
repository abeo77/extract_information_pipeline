import json
import sys
from pathlib import Path
from typing import Callable

from app.extraction.evidence_extractor import extract_evidence
from app.extraction.group_merger import merge_keyword_groups
from app.extraction.keyword_extractor import extract_keywords
from app.extraction.llm1_input import prepare_llm1_batches
from app.extraction.schemas import LlmCallStats, PipelineResult
from app.loaders.document_loader import load_document
from app.preprocessing.normalizer import normalize_documents
from app.segmentation.contract_segmenter import segment_documents
from app.services.pipeline_service import PipelineConfig, StepTimer, create_chat_model
from app.services.result_service import compact_result, save_json


def run_pipeline(
    file_path: str | Path,
    output_path: str | Path,
    config: PipelineConfig,
    debug_load: bool = False,
    debug_load_full: bool = False,
    debug_normalize: bool = False,
    debug_normalize_full: bool = False,
    debug_segments: bool = False,
    debug_segments_full: bool = False,
    debug_llm1_input: bool = False,
    on_step: Callable[[dict], None] | None = None,
) -> PipelineResult:
    total = StepTimer()

    timer = StepTimer()
    documents = load_document(file_path)
    if not debug_load and not debug_normalize and not debug_segments:
        print(f"[LOAD] Loaded {len(documents)} page(s) in {timer.elapsed():.2f}s")
    _notify_step(
        on_step,
        "load",
        "Load document",
        timer.elapsed(),
        pages=len(documents),
    )
    if debug_load:
        print_loaded_documents_debug(documents, full_text=debug_load_full)
        raise SystemExit(0)

    timer = StepTimer()
    documents = normalize_documents(documents)
    if not debug_normalize and not debug_segments:
        print(f"[NORMALIZE] Normalized text in {timer.elapsed():.2f}s")
    _notify_step(on_step, "normalize", "Normalize text", timer.elapsed())
    if debug_normalize:
        print_normalized_documents_debug(documents, full_text=debug_normalize_full)
        raise SystemExit(0)

    timer = StepTimer()
    segments = segment_documents(documents)
    if not debug_segments:
        print(f"[SEGMENT] Created {len(segments)} segments in {timer.elapsed():.2f}s")
    _notify_step(
        on_step,
        "segment",
        "Segment contract",
        timer.elapsed(),
        segments=len(segments),
    )
    if debug_segments:
        print_segments_debug(segments, full_text=debug_segments_full)
        raise SystemExit(0)
    if debug_llm1_input:
        print_llm1_input_debug(segments)
        raise SystemExit(0)

    timer = StepTimer()
    llm1_chat_model = create_chat_model(config, stage="llm1")
    keyword_groups, keyword_extraction_batches = extract_keywords(
        segments,
        llm1_chat_model,
        batch_size=config.keyword_batch_size,
        max_parallel_calls=config.max_parallel_llm_calls,
    )
    print(
        f"[LLM1] Extracted {len(keyword_groups)} keyword group(s) "
        f"in {keyword_extraction_batches} batch(es), "
        f"model={config.llm1_provider}/{config.llm1_model}, "
        f"parallel={config.max_parallel_llm_calls}, {timer.elapsed():.2f}s"
    )
    _notify_step(
        on_step,
        "llm1",
        "LLM1 keyword extraction",
        timer.elapsed(),
        keyword_groups=len(keyword_groups),
        batches=keyword_extraction_batches,
    )
    keyword_groups_for_evidence = len(keyword_groups)

    timer = StepTimer()
    llm2_chat_model = create_chat_model(config, stage="llm2")
    keyword_groups, evidence_extraction_batches = extract_evidence(
        keyword_groups,
        segments,
        llm2_chat_model,
        batch_size=config.evidence_batch_size,
        max_segments_per_group=config.max_evidence_segments_per_group,
        max_parallel_calls=config.max_parallel_llm_calls,
    )
    print(
        f"[LLM2] Extracted evidence for {len(keyword_groups)} keyword group(s) "
        f"in {evidence_extraction_batches} batch(es), "
        f"model={config.llm2_provider}/{config.llm2_model}, "
        f"parallel={config.max_parallel_llm_calls}, {timer.elapsed():.2f}s"
    )
    _notify_step(
        on_step,
        "llm2",
        "LLM2 evidence extraction",
        timer.elapsed(),
        keyword_groups=len(keyword_groups),
        batches=evidence_extraction_batches,
    )

    timer = StepTimer()
    keyword_groups = merge_keyword_groups(keyword_groups)
    _notify_step(
        on_step,
        "merge",
        "Merge duplicate keyword groups",
        timer.elapsed(),
        keyword_groups=len(keyword_groups),
    )

    timer = StepTimer()
    result = PipelineResult(
        document_name=Path(file_path).name,
        processing_time_seconds=round(total.elapsed(), 2),
        total_pages=len(documents),
        total_segments=len(segments),
        total_keyword_groups=len(keyword_groups),
        llm_calls=LlmCallStats(
            keyword_extraction_batches=keyword_extraction_batches,
            keyword_groups_for_evidence=keyword_groups_for_evidence,
            evidence_extraction_batches=evidence_extraction_batches,
        ),
        keyword_groups=keyword_groups,
    )
    save_json(compact_result(result.model_dump()), output_path)
    _notify_step(on_step, "export", "Export result JSON", timer.elapsed())
    print(f"[DONE] Wrote keyword output to {output_path}")
    return result


def _notify_step(callback: Callable[[dict], None] | None, key: str, label: str, seconds: float, **metadata) -> None:
    if callback:
        callback(
            {
                "key": key,
                "label": label,
                "seconds": round(seconds, 2),
                **metadata,
            }
        )


def print_segments_debug(segments, full_text: bool = False) -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    payload = {
        "segments": [
            {
                "segment_id": segment.segment_id,
                "title": segment.title,
                "page": segment.page,
                "metadata": segment.metadata,
                "text": segment.text,
            }
            for segment in segments
        ]
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def print_llm1_input_debug(segments) -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    payload = {
        "llm1_batches": [
            batch.model_dump(exclude_none=True)
            for batch in prepare_llm1_batches(segments)
        ]
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def print_loaded_documents_debug(documents, full_text: bool = False) -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    payload = {
        "documents": [
            {
                "metadata": document.metadata,
                "text_length": len(document.page_content),
                "text": document.page_content
                if full_text
                else document.page_content[:1000],
            }
            for document in documents
        ]
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def print_normalized_documents_debug(documents, full_text: bool = False) -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    hidden_metadata = {"page_label", "is_normalized", "normalization_warnings"}
    payload = {
        "segment_input_documents": [
            {
                "metadata": {
                    key: value
                    for key, value in document.metadata.items()
                    if key not in hidden_metadata
                },
                "segment_input_text_length": len(document.page_content),
                "segment_input_text": document.page_content
                if full_text
                else document.page_content[:1000],
            }
            for document in documents
        ]
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))
