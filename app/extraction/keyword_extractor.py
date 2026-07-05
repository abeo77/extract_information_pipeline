"""LLM 1 keyword extraction."""

from __future__ import annotations

import re
import time
from typing import Any

from app.extraction.llm1_input import prepare_llm1_batches, remove_reason_fields
from app.extraction.llm_json import (
    build_json_prompt,
    clean_string_list,
    parse_json_response,
    require_list,
    response_text,
)
from app.extraction.prompts import LLM1_KEYWORD_EXTRACTION_PROMPT
from app.extraction.schemas import DocumentSegment, Llm1BatchInput
from app.services.parallel_service import ordered_parallel_map_with_progress


PROVISION_TYPES = {
    "parties",
    "effective_date",
    "term",
    "renewal",
    "termination",
    "payment",
    "services",
    "obligations",
    "delivery",
    "confidentiality",
    "intellectual_property",
    "liability",
    "indemnity",
    "warranties",
    "dispute_resolution",
    "governing_law",
    "notices",
    "assignment",
    "amendment",
    "force_majeure",
    "compliance",
    "schedules_exhibits",
    "signatures",
    "other",
}


def extract_keywords(
    segments: list[DocumentSegment],
    chat_model,
    batch_size: int = 50,
    max_parallel_calls: int = 1,
    on_llm_event=None,
) -> tuple[list[dict[str, Any]], int]:
    """Extract LLM1 keyword groups from compact segment batches."""
    batches = prepare_llm1_batches(segments, batch_size=batch_size)
    batch_results = ordered_parallel_map_with_progress(
        batches,
        lambda batch: _extract_keyword_batch(batch, chat_model),
        max_workers=max_parallel_calls,
        on_result=lambda index, result: _notify_llm_event(
            on_llm_event,
            "LLM1",
            index,
            len(batches),
            result["trace"],
        ),
    )

    keyword_groups: list[dict[str, Any]] = []
    for result in batch_results:
        keyword_groups.extend(result["groups"])

    return remove_reason_fields(keyword_groups), len(batches)


def _extract_keyword_batch(batch: Llm1BatchInput, chat_model) -> dict[str, Any]:
    prompt = _build_llm1_prompt(batch)
    started = time.perf_counter()
    response = chat_model.invoke(prompt)
    raw_response = response_text(response)
    payload = parse_json_response(raw_response, "LLM1")
    groups = require_list(payload, "keyword_groups", "LLM1")
    normalized_groups = _normalize_keyword_groups(groups, batch)
    return {
        "groups": normalized_groups,
        "trace": {
            "prompt": prompt,
            "raw_response": raw_response,
            "parsed_payload": payload,
            "seconds": round(time.perf_counter() - started, 2),
            "input_count": len(batch.segments),
            "output_count": len(normalized_groups),
            "summary": _trace_summary(normalized_groups),
        },
    }


def _build_llm1_prompt(batch: Llm1BatchInput) -> str:
    return build_json_prompt(
        LLM1_KEYWORD_EXTRACTION_PROMPT,
        "Contract segment batch JSON",
        batch.model_dump(exclude_none=True),
    )


def _normalize_keyword_groups(
    groups: list[Any],
    batch: Llm1BatchInput,
) -> list[dict[str, Any]]:
    segment_lookup = {segment.segment_id: segment for segment in batch.segments}
    normalized = []

    for group in groups:
        if not isinstance(group, dict):
            continue
        representative = str(group.get("representative_keyword", "")).strip()
        if not representative:
            continue

        metadata = group.get("metadata")
        metadata = dict(metadata) if isinstance(metadata, dict) else {}
        segment_id = metadata.get("id") or metadata.get("segment_id")
        if segment_id in segment_lookup:
            segment = segment_lookup[segment_id]
            metadata.setdefault("page", segment.page)
            metadata["id"] = segment.segment_id
            metadata.setdefault("segment_id", segment.segment_id)
            metadata.setdefault("clause_no", segment.clause_no)
            metadata.setdefault("parent_section_title", segment.parent_section_title)
        metadata = {key: value for key, value in metadata.items() if value is not None}
        if batch.source:
            metadata.setdefault("source", batch.source)

        related_keywords = clean_string_list(group.get("related_keywords"))
        context_text = _context_text(group, segment_lookup, metadata)
        normalized.append(
            {
                "representative_keyword": representative,
                "provision_type": _provision_type(group, representative, related_keywords),
                "related_keywords": related_keywords,
                "context_text": context_text,
                "metadata": metadata,
            }
        )
    return normalized


def _context_text(
    group: dict[str, Any],
    segment_lookup: dict[str, Any],
    metadata: dict[str, Any],
) -> str:
    context_text = str(group.get("context_text") or "").strip()
    if context_text:
        return context_text

    segment_id = metadata.get("id") or metadata.get("segment_id")
    segment = segment_lookup.get(segment_id)
    return str(getattr(segment, "text", "") or "").strip()


def _provision_type(
    group: dict[str, Any],
    representative: str,
    related_keywords: list[str],
) -> str:
    explicit = _clean_provision_type(group.get("provision_type") or group.get("provision"))
    if explicit:
        return explicit
    return _infer_provision_type(" ".join([representative, *related_keywords]))


def _clean_provision_type(value: Any) -> str | None:
    if value is None:
        return None
    normalized = re.sub(r"[^a-z0-9]+", "_", str(value).strip().lower()).strip("_")
    aliases = {
        "ip": "intellectual_property",
        "intellectual_property_rights": "intellectual_property",
        "governing_law_and_dispute_resolution": "dispute_resolution",
        "disputes": "dispute_resolution",
        "notice": "notices",
        "schedule": "schedules_exhibits",
        "exhibit": "schedules_exhibits",
        "signature": "signatures",
    }
    normalized = aliases.get(normalized, normalized)
    return normalized if normalized in PROVISION_TYPES else None


def _infer_provision_type(value: str) -> str:
    text = value.lower()
    checks = [
        ("payment", ("payment", "fee", "invoice", "pay ", "paid", "amount", "usd", "price")),
        ("effective_date", ("effective date", "commencement date", "start date")),
        ("term", ("contract term", "expiration", "end date", "remain in effect")),
        ("renewal", ("renew", "non-renewal", "successive")),
        ("termination", ("terminate", "termination", "breach", "cure")),
        ("services", ("services", "support", "maintenance", "delivery", "scope")),
        ("confidentiality", ("confidential", "non-public", "disclosed", "disclosure")),
        ("liability", ("liability", "liable", "damages", "consequential")),
        ("indemnity", ("indemn", "hold harmless")),
        ("warranties", ("warranty", "warranties", "representations")),
        ("governing_law", ("governed by", "laws of", "law of")),
        ("dispute_resolution", ("dispute", "arbitration", "mediation", "negotiation")),
        ("notices", ("notice", "notices", "registered mail", "email")),
        ("assignment", ("assign", "assignment", "transfer")),
        ("amendment", ("amend", "amendment", "modify", "modification")),
        ("force_majeure", ("force majeure", "act of god", "beyond reasonable control")),
        ("compliance", ("comply", "compliance", "law", "regulation")),
        ("intellectual_property", ("intellectual property", "ip rights", "copyright", "trademark")),
        ("parties", ("service provider", "client", "customer", "supplier")),
        ("signatures", ("signing", "signed", "signature", "authorized representative")),
        ("schedules_exhibits", ("schedule", "exhibit", "appendix", "annex")),
        ("obligations", ("shall", "must", "obligation", "responsible")),
    ]
    for provision_type, needles in checks:
        if any(needle in text for needle in needles):
            return provision_type
    return "other"


def _trace_summary(groups: list[dict[str, Any]]) -> str:
    keywords = [
        str(group.get("representative_keyword") or "").strip()
        for group in groups
        if group.get("representative_keyword")
    ]
    if not keywords:
        return "LLM1 did not return keyword groups for this batch."
    preview = ", ".join(keywords[:8])
    suffix = "" if len(keywords) <= 8 else f", +{len(keywords) - 8} more"
    return f"LLM1 extracted {len(keywords)} keyword group(s): {preview}{suffix}."


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
