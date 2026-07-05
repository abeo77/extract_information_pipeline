"""LLM 2 evidence extraction."""

from __future__ import annotations

import copy
import time
from typing import Any

from app.extraction.llm_json import (
    build_json_prompt,
    compact_dict,
    parse_json_response,
    require_list,
    response_text,
)
from app.extraction.prompts import LLM2_EVIDENCE_EXTRACTION_PROMPT
from app.extraction.schemas import DocumentSegment
from app.services.parallel_service import ordered_parallel_map_with_progress


def extract_evidence(
    keyword_groups: list[dict[str, Any]],
    segments: list[DocumentSegment],
    chat_model,
    batch_size: int = 10,
    max_segments_per_group: int = 5,
    max_parallel_calls: int = 1,
    on_llm_event=None,
) -> tuple[list[dict[str, Any]], int]:
    """Attach LLM2 evidences to LLM1 keyword groups in small batches."""
    if batch_size <= 0:
        raise ValueError("batch_size must be greater than 0")
    if max_segments_per_group <= 0:
        raise ValueError("max_segments_per_group must be greater than 0")
    if not keyword_groups:
        return [], 0

    segment_lookup = {segment.segment_id: segment for segment in segments}
    enriched_groups: list[dict[str, Any]] = []
    batches = _build_evidence_batches(
        keyword_groups,
        segments,
        segment_lookup,
        batch_size,
        max_segments_per_group,
    )

    batch_results = ordered_parallel_map_with_progress(
        batches,
        lambda batch: _extract_evidence_batch(batch, chat_model),
        max_workers=max_parallel_calls,
        on_result=lambda index, result: _notify_llm_event(
            on_llm_event,
            "LLM2",
            index,
            len(batches),
            result["trace"],
        ),
    )
    for result in batch_results:
        enriched_groups.extend(result["groups"])

    return enriched_groups, len(batches)


def _extract_evidence_batch(batch: dict[str, Any], chat_model) -> dict[str, Any]:
    prompt = _build_llm2_prompt(batch)
    started = time.perf_counter()
    response = chat_model.invoke(prompt)
    raw_response = response_text(response)
    payload = parse_json_response(raw_response, "LLM2")
    returned_groups = require_list(payload, "keyword_groups", "LLM2")
    merged_groups = _merge_evidence(batch["keyword_groups"], returned_groups)
    return {
        "groups": merged_groups,
        "trace": {
            "prompt": prompt,
            "raw_response": raw_response,
            "parsed_payload": payload,
            "seconds": round(time.perf_counter() - started, 2),
            "input_count": len(batch["keyword_groups"]),
            "output_count": len(merged_groups),
            "summary": _trace_summary(merged_groups),
        },
    }


def _build_evidence_batches(
    keyword_groups: list[dict[str, Any]],
    segments: list[DocumentSegment],
    segment_lookup: dict[str, DocumentSegment],
    batch_size: int,
    max_segments_per_group: int,
) -> list[dict[str, Any]]:
    batches = []
    for start in range(0, len(keyword_groups), batch_size):
        groups = keyword_groups[start : start + batch_size]
        segment_ids = []
        for group in groups:
            for segment_id in _candidate_segment_ids(
                group,
                segments,
                segment_lookup,
                max_segments_per_group,
            ):
                if segment_id not in segment_ids:
                    segment_ids.append(segment_id)

        batches.append(
            {
                "keyword_groups": [_keyword_group_payload(group) for group in groups],
                "segments": [
                    _segment_payload(segment_lookup[segment_id])
                    for segment_id in segment_ids
                    if segment_id in segment_lookup
                ],
            }
        )
    return batches


def _candidate_segment_ids(
    group: dict[str, Any],
    segments: list[DocumentSegment],
    segment_lookup: dict[str, DocumentSegment],
    max_segments_per_group: int,
) -> list[str]:
    metadata = group.get("metadata") if isinstance(group.get("metadata"), dict) else {}
    segment_id = metadata.get("id") or metadata.get("segment_id")
    if segment_id in segment_lookup:
        return [segment_id]

    source = metadata.get("source")
    page = metadata.get("page")
    matches = [
        segment.segment_id
        for segment in segments
        if (source is None or segment.source == source)
        and (page is None or segment.page == page)
    ]
    if matches:
        return matches[:max_segments_per_group]
    return [segment.segment_id for segment in segments[:max_segments_per_group]]


def _keyword_group_payload(group: dict[str, Any]) -> dict[str, Any]:
    return compact_dict(
        {
            "representative_keyword": group.get("representative_keyword"),
            "related_keywords": group.get("related_keywords", []),
            "provision_type": group.get("provision_type"),
            "context_text": group.get("context_text"),
            "exact_text": group.get("exact_text"),
            "metadata": group.get("metadata", {}),
        }
    )


def _segment_payload(segment: DocumentSegment) -> dict[str, Any]:
    return {
        "id": segment.segment_id,
        "page": segment.page,
        "source": segment.source,
        "text": segment.text,
    }


def _build_llm2_prompt(batch: dict[str, Any]) -> str:
    return build_json_prompt(
        LLM2_EVIDENCE_EXTRACTION_PROMPT,
        "Evidence extraction batch JSON",
        batch,
    )


def _merge_evidence(
    requested_groups: list[dict[str, Any]],
    returned_groups: list[Any],
) -> list[dict[str, Any]]:
    returned_lookup = {
        _keyword_key(group): group
        for group in returned_groups
        if isinstance(group, dict) and _keyword_key(group)
    }

    merged = []
    for group in requested_groups:
        enriched = copy.deepcopy(group)
        returned = returned_lookup.get(_keyword_key(group), {})
        evidences = returned.get("evidences") if isinstance(returned, dict) else []
        if not evidences and _has_top_level_evidence(returned):
            evidences = [_top_level_evidence(returned)]
        evidences = _normalize_evidences(evidences)
        if not evidences:
            evidences = [_not_found_evidence(group)]
        enriched["evidences"] = evidences
        _copy_primary_evidence_fields(enriched, evidences[0])
        merged.append(enriched)
    return merged


def _normalize_evidences(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []

    evidences = []
    for evidence in value:
        if not isinstance(evidence, dict):
            continue
        validation_status = str(evidence.get("validation_status") or "passed").strip()
        if validation_status not in {"passed", "not_found", "invalid"}:
            validation_status = "not_found"

        evidences.append(
            {
                "context_text": str(
                    evidence.get("context_text")
                    or evidence.get("evidence_text")
                    or evidence.get("exact_text")
                    or ""
                ).strip(),
                "exact_text": str(evidence.get("exact_text") or "").strip(),
                "page": evidence.get("page"),
                "id": evidence.get("id") or evidence.get("segment_id"),
                "segment_id": evidence.get("segment_id") or evidence.get("id"),
                "source": evidence.get("source"),
                "validation_status": validation_status,
                "confidence": _confidence(evidence.get("confidence")),
            }
        )
    return evidences


def _not_found_evidence(group: dict[str, Any]) -> dict[str, Any]:
    metadata = group.get("metadata") if isinstance(group.get("metadata"), dict) else {}
    return {
        "context_text": "",
        "exact_text": "",
        "page": metadata.get("page"),
        "id": metadata.get("id") or metadata.get("segment_id"),
        "segment_id": metadata.get("segment_id") or metadata.get("id"),
        "source": metadata.get("source"),
        "validation_status": "not_found",
        "confidence": 0.0,
    }


def _has_top_level_evidence(value: Any) -> bool:
    return isinstance(value, dict) and any(
        value.get(key) for key in ("context_text", "evidence_text", "exact_text")
    )


def _top_level_evidence(group: dict[str, Any]) -> dict[str, Any]:
    metadata = group.get("metadata") if isinstance(group.get("metadata"), dict) else {}
    return {
        "context_text": group.get("context_text"),
        "exact_text": group.get("exact_text"),
        "page": metadata.get("page"),
        "id": metadata.get("id") or metadata.get("segment_id"),
        "segment_id": metadata.get("segment_id") or metadata.get("id"),
        "source": metadata.get("source"),
        "validation_status": group.get("validation_status") or "passed",
        "confidence": group.get("confidence"),
    }


def _copy_primary_evidence_fields(group: dict[str, Any], evidence: dict[str, Any]) -> None:
    group["context_text"] = evidence.get("context_text") or evidence.get("exact_text") or ""
    group["exact_text"] = evidence.get("exact_text") or ""
    metadata = group.get("metadata") if isinstance(group.get("metadata"), dict) else {}
    metadata.setdefault("page", evidence.get("page"))
    metadata.setdefault("source", evidence.get("source"))
    metadata.setdefault("id", evidence.get("id"))
    metadata.setdefault("segment_id", evidence.get("segment_id") or evidence.get("id"))
    group["metadata"] = {key: value for key, value in metadata.items() if value is not None}


def _normalize_space(value: str) -> str:
    return " ".join(str(value or "").split())


def _keyword_key(group: dict[str, Any]) -> str:
    return str(group.get("representative_keyword") or "").strip().casefold()


def _confidence(value: Any) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return 0.0
    return min(1.0, max(0.0, confidence))


def _trace_summary(groups: list[dict[str, Any]]) -> str:
    found = sum(1 for group in groups if group.get("exact_text"))
    missing = sum(
        1
        for group in groups
        for evidence in group.get("evidences", [])
        if isinstance(evidence, dict)
        and evidence.get("validation_status") == "not_found"
    )
    keywords = [
        str(group.get("representative_keyword") or "").strip()
        for group in groups
        if group.get("representative_keyword")
    ]
    preview = ", ".join(keywords[:6])
    suffix = "" if len(keywords) <= 6 else f", +{len(keywords) - 6} more"
    return (
        f"LLM2 attached evidence for {len(groups)} group(s); "
        f"{found} with exact_text, {missing} not_found. "
        f"Groups: {preview}{suffix}."
    )


def _notify_llm_event(callback, stage: str, index: int, total: int, trace: dict[str, Any]) -> None:
    if not callback:
        return
    callback(
        {
            "stage": stage,
            "batch_index": index + 1,
            "batch_total": total,
            **trace,
        }
    )
