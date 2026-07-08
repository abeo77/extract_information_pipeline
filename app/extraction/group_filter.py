"""Precision filters for extracted keyword groups before evidence fallback."""

from __future__ import annotations

import re
from typing import Any


BUSINESS_SPECIFIC_TYPES = {
    "payment",
    "services",
    "delivery",
    "compliance",
    "intellectual_property",
    "liability",
    "indemnity",
    "warranties",
    "assignment",
    "force_majeure",
    "schedules_exhibits",
}

SIGNATURE_ALLOWED = {"signatures", "parties"}

RISKY_ANCHORS = {
    "net 30 payment terms": (r"\bnet\s*30\b", r"\bpayment\b.{0,80}\b30\s+days\b"),
    "technology support and upgrades": (
        r"\btechnology\s+(?:support|maintenance|upgrades?)\b",
        r"\bsupport\b.{0,120}\bupgrades?\b",
    ),
    "technology description": (
        r"\btechnology\s+description\b",
        r"\bproducts?\s+approved\s+for\s+sale\b",
        r"\btechnology\b.{0,120}\b(?:platform|content|products?)\b",
    ),
    "data security and access control": (
        r"\bdata\s+security\b",
        r"\bsecurity\s+incidents?\b",
        r"\bsafeguards?\b.{0,120}\bdata\b",
        r"\baccess\b.{0,120}\bauthorized\s+personnel\b",
    ),
    "acceptance criteria": (
        r"\bacceptance\s+criteria\b",
        r"\breview\s+period\b",
        r"\bdeliverable\b.{0,160}\baccept",
        r"\breject\b.{0,120}\bdefects?\b",
    ),
    "grant of rights": (
        r"\bgrants?\b.{0,160}\bright\s+to\b",
        r"\bright\s+to\s+(?:advertise|market|sell|distribute)\b",
        r"\blicense\s+grant\b",
    ),
    "use restrictions": (
        r"\bnot\s+for\s+(?:remarketing|redistribution)\b",
        r"\binternal\s+use\b",
        r"\bunauthorized\s+use\b",
        r"\bdata\s+center\s+environment\b",
    ),
}


def filter_keyword_groups(
    keyword_groups: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    """Remove low-confidence groups that tend to create extra items and LLM2 work."""
    kept = []
    filtered = 0
    for group in keyword_groups:
        if _should_drop(group):
            filtered += 1
            continue
        kept.append(group)
    return kept, filtered


def _should_drop(group: dict[str, Any]) -> bool:
    text = _group_text(group)
    key = _normalize_keyword(group.get("representative_keyword"))
    provision_type = str(group.get("provision_type") or "").strip()
    kind = _context_kind(text)

    if kind == "signature" and provision_type not in SIGNATURE_ALLOWED and key not in SIGNATURE_ALLOWED:
        return True
    if kind in {"opening", "recitals"} and provision_type in BUSINESS_SPECIFIC_TYPES and key not in {"parties"}:
        return True

    risky_patterns = RISKY_ANCHORS.get(key)
    if risky_patterns and not _has_any_pattern(text, risky_patterns):
        return True

    if _is_deterministic(group) and provision_type in BUSINESS_SPECIFIC_TYPES:
        labels = _group_labels(group)
        if labels and not _has_label_overlap(labels, text):
            return True

    return False


def _is_deterministic(group: dict[str, Any]) -> bool:
    metadata = group.get("metadata") if isinstance(group.get("metadata"), dict) else {}
    return metadata.get("coverage_source") == "deterministic"


def _group_text(group: dict[str, Any]) -> str:
    values = [group.get("context_text"), group.get("exact_text")]
    return " ".join(str(value or "") for value in values)


def _group_labels(group: dict[str, Any]) -> list[str]:
    related = group.get("related_keywords") if isinstance(group.get("related_keywords"), list) else []
    return [
        str(value).strip()
        for value in [group.get("representative_keyword"), *related]
        if str(value or "").strip()
    ]


def _has_label_overlap(labels: list[str], text: str) -> bool:
    text_tokens = set(re.findall(r"[a-z0-9]+", text.casefold()))
    for label in labels:
        tokens = {
            token
            for token in re.findall(r"[a-z0-9]+", label.casefold())
            if len(token) > 3 and token not in {"agreement", "contract", "clause", "terms"}
        }
        if tokens and len(tokens & text_tokens) >= min(2, len(tokens)):
            return True
    return False


def _has_any_pattern(text: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL) for pattern in patterns)


def _context_kind(text: str) -> str:
    normalized = _normalize_keyword(text[:600])
    if "signature" in normalized or normalized.startswith("accepted and agreed") or "print name" in normalized:
        return "signature"
    if "recitals" in normalized or normalized.startswith("whereas"):
        return "recitals"
    if (
        len(text.split()) < 240
        and any(value in normalized for value in ("exhibit", "by and between", "made between", "entered into"))
    ):
        return "opening"
    return "body"


def _normalize_keyword(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").casefold()).strip()
