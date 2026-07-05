"""Conservative keyword group merging after batch-level extraction."""

from __future__ import annotations

import copy
import re
from typing import Any


SYNONYM_SETS = (
    ("effective date", "start date", "commencement date"),
    ("end date", "expiration date"),
    ("confidentiality", "non-disclosure", "non disclosure"),
    ("service fee", "monthly fee", "fees"),
    ("governing law", "applicable law"),
    ("notices", "notice", "written notice", "notice requirement"),
    ("intellectual property", "intellectual property rights", "ip rights"),
    ("limitation of liability", "liability cap"),
)


def merge_keyword_groups(keyword_groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge duplicate or clearly synonymous groups without broad-topic merging."""
    merged: list[dict[str, Any]] = []
    index_by_key: dict[str, int] = {}

    for group in keyword_groups:
        key = _merge_key(group)
        if key not in index_by_key:
            index_by_key[key] = len(merged)
            merged.append(copy.deepcopy(group))
            continue

        existing = merged[index_by_key[key]]
        _merge_into(existing, group)

    return merged


def _merge_key(group: dict[str, Any]) -> str:
    representative = str(group.get("representative_keyword") or "").strip()
    normalized = _normalize_keyword(representative)
    for synonym_set in SYNONYM_SETS:
        if normalized in {_normalize_keyword(value) for value in synonym_set}:
            return _normalize_keyword(synonym_set[0])
    return normalized


def _merge_into(target: dict[str, Any], source: dict[str, Any]) -> None:
    target["related_keywords"] = _merged_strings(
        target.get("related_keywords", []),
        source.get("related_keywords", []),
        source.get("representative_keyword"),
    )
    target["evidences"] = _merged_evidences(
        target.get("evidences", []),
        source.get("evidences", []),
    )
    best = _best_group(target, source)
    target["context_text"] = best.get("context_text") or target.get("context_text")
    target["exact_text"] = best.get("exact_text") or target.get("exact_text")
    target["metadata"] = best.get("metadata") or target.get("metadata", {})


def _merged_strings(*values: Any) -> list[str]:
    merged = []
    seen = set()
    for value in values:
        items = value if isinstance(value, list) else [value]
        for item in items:
            text = str(item or "").strip()
            key = _normalize_keyword(text)
            if text and key not in seen:
                seen.add(key)
                merged.append(text)
    return merged


def _best_group(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    return right if _group_score(right) > _group_score(left) else left


def _group_score(group: dict[str, Any]) -> int:
    text = " ".join(
        [
            str(group.get("context_text") or ""),
            str(group.get("exact_text") or ""),
        ]
    ).casefold()
    score = 0
    if group.get("exact_text"):
        score += 5
    if group.get("context_text"):
        score += 3
    if "made between" in text:
        score += 4
    if "service provider" in text:
        score += 2
    if "client" in text:
        score += 2
    if "authorized representative" in text:
        score -= 3
    return score


def _merged_evidences(
    target_evidences: list[Any],
    source_evidences: list[Any],
) -> list[dict[str, Any]]:
    merged = []
    seen = set()
    for evidence in [*target_evidences, *source_evidences]:
        if not isinstance(evidence, dict):
            continue
        key = (
            _normalize_space(evidence.get("exact_text")),
            str(evidence.get("segment_id") or evidence.get("id") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        merged.append(copy.deepcopy(evidence))
    return merged


def _normalize_keyword(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").casefold()).strip()


def _normalize_space(value: str) -> str:
    return " ".join(str(value or "").split())
