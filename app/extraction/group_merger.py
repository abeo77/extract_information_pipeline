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
    ("indemnification", "indemnity", "hold harmless"),
    ("force majeure", "excusable delay", "beyond reasonable control"),
    ("assignment", "assign", "transfer", "assignment restriction"),
    ("audit rights", "audit", "inspection rights", "records inspection"),
    ("deemed acceptance", "deemed accepted", "acceptance review period"),
    ("entire agreement and amendments", "entire agreement", "prior understandings", "written amendment"),
)
PAYMENT_ADJACENT_KEYS = {
    "payment terms",
    "service fee",
    "fees",
    "amounts due",
    "invoice",
    "payment due date",
    "net 30 payment terms",
    "net 30",
}
PARTY_ROLE_KEYS = {
    "parties",
    "contracting parties",
    "company",
    "client",
    "customer",
    "service provider",
    "marketing affiliate",
    "affiliate",
    "ma",
}
LAW_DISPUTE_KEYS = {
    "governing law",
    "applicable law",
    "dispute resolution",
    "jurisdiction",
    "competent court",
}


def merge_keyword_groups(keyword_groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge duplicate or clearly synonymous groups without broad-topic merging."""
    merged: list[dict[str, Any]] = []
    index_by_key: dict[str, int] = {}

    for group in keyword_groups:
        key = _merge_key(group)
        if key not in index_by_key:
            index_by_key[key] = len(merged)
            copied = copy.deepcopy(group)
            _canonicalize_group(copied, key)
            merged.append(copied)
            continue

        existing = merged[index_by_key[key]]
        _merge_into(existing, group)
        _canonicalize_group(existing, key)

    return merged


def _merge_key(group: dict[str, Any]) -> str:
    representative = str(group.get("representative_keyword") or "").strip()
    normalized = _normalize_keyword(representative)
    if normalized in PARTY_ROLE_KEYS and _has_party_intro_context(group):
        return "parties"
    if normalized in PAYMENT_ADJACENT_KEYS:
        return f"payment terms::{_context_identity(group)}"
    if normalized in LAW_DISPUTE_KEYS and _has_combined_law_dispute_context(group):
        return "governing law and dispute resolution"
    for synonym_set in SYNONYM_SETS:
        if normalized in {_normalize_keyword(value) for value in synonym_set}:
            return _normalize_keyword(synonym_set[0])
    return normalized


def _canonicalize_group(group: dict[str, Any], key: str) -> None:
    if key == "parties":
        _replace_representative(group, "Parties")
    elif key.startswith("payment terms::"):
        _replace_representative(group, "Payment Terms")
    elif key == "governing law and dispute resolution":
        _replace_representative(group, "Governing Law and Dispute Resolution")


def _replace_representative(group: dict[str, Any], representative: str) -> None:
    current = str(group.get("representative_keyword") or "").strip()
    group["representative_keyword"] = representative
    group["related_keywords"] = _merged_strings(
        group.get("related_keywords", []),
        current if current and _normalize_keyword(current) != _normalize_keyword(representative) else None,
    )


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


def _has_party_intro_context(group: dict[str, Any]) -> bool:
    text = _group_text(group)
    if ("service provider:" in text and "client:" in text) or ("company:" in text and "client:" in text):
        return True
    if not any(
        phrase in text
        for phrase in (
            "by and between",
            "made between",
            "entered into",
            "between:",
            "referred to as",
        )
    ):
        return False
    return (
        len({"company", "client", "customer", "service provider", "affiliate", "marketing affiliate"} & set(text.split()))
        >= 1
        or " and " in text
    )


def _has_combined_law_dispute_context(group: dict[str, Any]) -> bool:
    text = _group_text(group)
    has_law = "governed by" in text or "laws of" in text or "law of" in text
    has_dispute = any(value in text for value in ("dispute", "jurisdiction", "court", "arbitration", "negotiation"))
    return has_law and has_dispute


def _group_text(group: dict[str, Any]) -> str:
    values = [
        group.get("representative_keyword"),
        " ".join(group.get("related_keywords", []) if isinstance(group.get("related_keywords"), list) else []),
        group.get("context_text"),
        group.get("exact_text"),
    ]
    return _normalize_space(" ".join(str(value or "") for value in values)).casefold()


def _context_identity(group: dict[str, Any]) -> str:
    metadata = group.get("metadata") if isinstance(group.get("metadata"), dict) else {}
    for key in ("id", "segment_id", "clause_no", "page", "source"):
        value = metadata.get(key)
        if value not in (None, ""):
            return f"{key}:{value}"
    text = _normalize_space(str(group.get("context_text") or ""))[:120]
    return text or "unknown"


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
