"""High-confidence local exact-text extraction before LLM2 fallback.

This module intentionally avoids document-specific provision rules. It only
accepts exact text when generic contract evidence patterns are clear; otherwise
the group falls back to LLM2.
"""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass
from typing import Any

from app.extraction.schemas import DocumentSegment


DATE_RE = r"(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}"
ORDINAL_DATE_RE = r"\d{1,2}\s*(?:st|nd|rd|th)?\s+day\s+of\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}"
NUMERIC_DATE_RE = r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}"
MONEY_RE = r"(?:USD|US\$|\$|EUR|GBP|VND)\s*[\d,]+(?:\.\d+)?"
MONEY_RANGE_RE = rf"{MONEY_RE}\s*(?:to|-|and\s+above)\s*{MONEY_RE}?"
PERCENT_RE = r"(?:\d+(?:\.\d+)?|one(?:\s+and\s+one[-\s]half)?)\s*(?:%|percent)"
NET_TERMS_RE = r"\bNet\s*\d+\s*(?:days?)?\b"
QUANTITY_RE = r"(?:minimum\s+of\s+)?\d[\d,]*\s+(?:Units?|licenses?|seats?|copies?|orders?)"
EMAIL_RE = r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}"
PERIOD_RE = r"(?:\d+\s*\(\d+\)|[A-Za-z]+\s*\(\d+\)|\d+|[A-Za-z]+)\s+(?:business\s+)?(?:days?|hours?|weeks?|months?|years?)"
LAW_RE = r"laws?\s+of\s+[A-Z][A-Za-z ,.-]+"
LEGAL_VERB_RE = re.compile(
    r"\b(shall|must|will|may|agree|agrees|include|includes|excluding|responsible|"
    r"pay|paid|purchase|ship|deliver|provide|notify|sent|approved|accepted|rejected|"
    r"terminate|renew|assign|confidential|liable|indemnify|warrant|governed|within|"
    r"commit|commits|license|grant|restrict)\b",
    flags=re.IGNORECASE,
)
STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "by",
    "for",
    "from",
    "in",
    "is",
    "of",
    "on",
    "or",
    "shall",
    "the",
    "this",
    "to",
    "will",
    "with",
}


@dataclass(frozen=True)
class Candidate:
    text: str
    score: int


def apply_local_evidence(
    keyword_groups: list[dict[str, Any]],
    segments: list[DocumentSegment],
) -> tuple[list[dict[str, Any]], list[int]]:
    """Attach local exact evidence where confidence is high.

    Returns the enriched groups and indexes that still need LLM2.
    """
    segment_lookup = {segment.segment_id: segment for segment in segments}
    enriched_groups: list[dict[str, Any]] = []
    unresolved_indexes: list[int] = []

    for index, group in enumerate(keyword_groups):
        enriched = copy.deepcopy(group)
        evidence = _local_evidence_for_group(enriched, segment_lookup)
        if evidence:
            enriched["context_text"] = evidence["context_text"]
            enriched["exact_text"] = evidence["exact_text"]
            enriched["evidences"] = [evidence]
            enriched["metadata"] = _merged_metadata(enriched.get("metadata"), evidence)
        else:
            unresolved_indexes.append(index)
        enriched_groups.append(enriched)

    return enriched_groups, unresolved_indexes


def _local_evidence_for_group(
    group: dict[str, Any],
    segment_lookup: dict[str, DocumentSegment],
) -> dict[str, Any] | None:
    labels = _candidate_labels(group)
    tokens = _keyword_tokens(labels)
    for context in _contexts_for_group(group, segment_lookup, labels):
        candidate = _best_candidate(labels, tokens, context)
        if not candidate:
            continue

        metadata = group.get("metadata") if isinstance(group.get("metadata"), dict) else {}
        return {
            "context_text": context.strip(),
            "exact_text": candidate.text.strip(),
            "page": metadata.get("page"),
            "id": metadata.get("id") or metadata.get("segment_id"),
            "segment_id": metadata.get("segment_id") or metadata.get("id"),
            "source": metadata.get("source"),
            "validation_status": "passed",
            "confidence": 0.99,
        }
    return None


def _best_candidate(
    labels: list[str],
    tokens: set[str],
    context: str,
) -> Candidate | None:
    candidates = [
        *_label_value_candidates(labels, tokens, context),
        *_entity_sentence_candidates(labels, tokens, context),
        *_keyword_sentence_candidates(labels, tokens, context),
    ]
    candidates = [
        Candidate(text=_clean_candidate_text(candidate.text), score=candidate.score)
        for candidate in candidates
    ]
    candidates = [
        candidate
        for candidate in candidates
        if _is_high_confidence_exact(candidate.text, labels, context)
    ]
    if not candidates:
        return None

    best = max(candidates, key=lambda candidate: (candidate.score, -len(candidate.text)))
    return best if best.score >= 70 else None


def _label_value_candidates(labels: list[str], tokens: set[str], context: str) -> list[Candidate]:
    candidates = []
    for label in labels:
        escaped = re.escape(label)
        patterns = [
            rf"\b{escaped}\s*:\s*([^\n]+)",
            rf"\b{escaped}\b\s+(?:is|are|will be|shall be|means|refers to)\s+([^.\n;]+\.?)",
            rf"\b{escaped}\b\s+({DATE_RE}|{ORDINAL_DATE_RE}|{NUMERIC_DATE_RE}|{MONEY_RE}|{PERCENT_RE}|{NET_TERMS_RE}|{QUANTITY_RE}|{PERIOD_RE}|{EMAIL_RE}|{LAW_RE})",
        ]
        for pattern in patterns:
            match = re.search(pattern, context, flags=re.IGNORECASE)
            if not match:
                continue
            text = _clean_candidate_text(match.group(0).strip())
            text = _trim_label_value(text, labels, current_label=label)
            if _requires_entity_pattern(tokens) and not _has_required_entity(tokens, text):
                continue
            candidates.append(Candidate(text=text, score=95))
    return candidates


def _entity_sentence_candidates(
    labels: list[str],
    tokens: set[str],
    context: str,
) -> list[Candidate]:
    candidates = []
    entity_patterns = _entity_patterns_for_tokens(tokens)
    if not entity_patterns:
        return candidates

    for sentence in _sentences(context):
        sentence_tokens = _text_tokens(sentence)
        overlap = len(tokens & sentence_tokens)
        if overlap == 0 and not _has_label(labels, sentence):
            continue
        if any(pattern.search(sentence) for pattern in entity_patterns):
            candidates.append(Candidate(text=sentence.strip(), score=80 + min(overlap, 4)))

    return candidates


def _keyword_sentence_candidates(
    labels: list[str],
    tokens: set[str],
    context: str,
) -> list[Candidate]:
    candidates = []
    if not tokens or _requires_entity_pattern(tokens):
        return candidates

    for sentence in _sentences(context):
        sentence_tokens = _text_tokens(sentence)
        overlap = len(tokens & sentence_tokens)
        has_label = _has_label(labels, sentence)
        has_legal_verb = bool(LEGAL_VERB_RE.search(sentence))
        if not has_label and overlap < max(1, min(2, len(tokens))):
            continue
        if not has_legal_verb and len(_normalize_space(sentence)) > 120:
            continue

        score = 55 + overlap * 8
        if has_label:
            score += 15
        if has_legal_verb:
            score += 8
        candidates.append(Candidate(text=sentence.strip(), score=score))

    return candidates


def _entity_patterns_for_tokens(tokens: set[str]) -> list[re.Pattern]:
    token_text = " ".join(sorted(tokens))
    patterns = []
    if "date" in tokens or "expiration" in tokens or "commencement" in tokens:
        patterns.extend([DATE_RE, ORDINAL_DATE_RE, NUMERIC_DATE_RE])
    if {"fee", "fees", "payment", "amount", "price", "pricing", "compensation"} & tokens:
        patterns.extend([MONEY_RE, MONEY_RANGE_RE, PERCENT_RE, NET_TERMS_RE])
    if {"late", "charge", "discount", "tiers", "tier", "level"} & tokens:
        patterns.extend([PERCENT_RE, MONEY_RANGE_RE])
    if {"quota", "commitment", "minimum", "units", "unit", "purchase"} & tokens:
        patterns.append(QUANTITY_RE)
    if {"notice", "notices", "contact", "email"} & tokens:
        patterns.append(EMAIL_RE)
    if {"term", "period", "duration", "response"} & tokens:
        patterns.append(PERIOD_RE)
    if "law" in tokens or "governing law" in token_text:
        patterns.append(LAW_RE)
    return [re.compile(pattern, flags=re.IGNORECASE) for pattern in patterns]


def _requires_entity_pattern(tokens: set[str]) -> bool:
    return bool(
        {
            "amount",
            "commencement",
            "compensation",
            "contact",
            "date",
            "discount",
            "duration",
            "email",
            "expiration",
            "fee",
            "fees",
            "late",
            "level",
            "law",
            "notice",
            "notices",
            "payment",
            "period",
            "price",
            "pricing",
            "quota",
            "response",
            "term",
            "tier",
            "tiers",
            "unit",
            "units",
        }
        & tokens
    )


def _has_required_entity(tokens: set[str], text: str) -> bool:
    return any(pattern.search(text) for pattern in _entity_patterns_for_tokens(tokens))


def _contexts_for_group(
    group: dict[str, Any],
    segment_lookup: dict[str, DocumentSegment],
    labels: list[str],
) -> list[str]:
    contexts = []
    context = str(group.get("context_text") or "").strip()
    if context:
        contexts.append(context)

    metadata = group.get("metadata") if isinstance(group.get("metadata"), dict) else {}
    segment_id = metadata.get("id") or metadata.get("segment_id")
    segment = segment_lookup.get(segment_id)
    if segment and segment.text.strip():
        contexts.append(segment.text.strip())

    contexts = _dedupe_contexts(contexts)
    representative = labels[0] if labels else ""
    if representative:
        contexts.sort(
            key=lambda value: 0
            if re.search(rf"\b{re.escape(representative)}\b", value, flags=re.IGNORECASE)
            else 1
        )
    return contexts


def _candidate_labels(group: dict[str, Any]) -> list[str]:
    values = [
        group.get("representative_keyword"),
        *(group.get("related_keywords") if isinstance(group.get("related_keywords"), list) else []),
    ]
    labels = []
    seen = set()
    for value in values:
        text = str(value or "").strip()
        key = _normalize_keyword(text)
        if text and key not in seen:
            seen.add(key)
            labels.append(text)
    return labels


def _is_high_confidence_exact(exact: str | None, labels: list[str], context: str) -> bool:
    if not exact:
        return False
    exact = exact.strip()
    if exact not in context:
        return False

    normalized_exact = _normalize_space(exact)
    normalized_context = _normalize_space(context)
    if len(normalized_exact) < 12:
        return False
    if _normalize_keyword(normalized_exact) in {_normalize_keyword(label) for label in labels}:
        return False
    if (
        len(normalized_exact) > 320
        and len(normalized_context) > 0
        and len(normalized_exact) / len(normalized_context) > 0.95
    ):
        return False
    return True


def _trim_label_value(value: str, labels: list[str], current_label: str) -> str:
    best = value.strip()
    current_key = _normalize_keyword(current_label)
    for label in labels:
        if _normalize_keyword(label) == current_key:
            continue
        match = re.search(rf"\s+\b{re.escape(label)}\b", best, flags=re.IGNORECASE)
        if match:
            best = best[: match.start()]

    for sentence_end in (". ", "; ", "\n"):
        index = best.find(sentence_end)
        if index > 0:
            return best[: index + 1].strip()
    return best.strip(" ;")


def _clean_candidate_text(value: str) -> str:
    text = (value or "").strip()
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) > 1 and _looks_like_heading_line(lines[0]):
        return "\n".join(lines[1:]).strip()
    return text


def _looks_like_heading_line(value: str) -> bool:
    text = value.strip().rstrip(".:;")
    if not text or len(text.split()) > 12:
        return False
    if LEGAL_VERB_RE.search(text):
        return False
    return bool(
        text.isupper()
        or re.match(r"^(?:\d+(?:\.\d+)*\.?\s+)?[A-Z][A-Za-z0-9 '&/()-]+$", text)
    )


def _sentences(context: str) -> list[str]:
    text = (context or "").strip()
    if not text:
        return []
    protected = _protect_abbreviations_and_emails(text)
    parts = re.split(r"(?<=[.!?])\s+", protected)
    parts = [_restore_protected(part) for part in parts]
    if len(parts) == 1:
        return [text]
    return [part.strip() for part in parts if part.strip()]


def _protect_abbreviations_and_emails(text: str) -> str:
    protected = (
        text.replace("a.m.", "a_m_")
        .replace("p.m.", "p_m_")
        .replace("A.M.", "A_M_")
        .replace("P.M.", "P_M_")
        .replace("Pte. Ltd.", "Pte_Ltd_")
        .replace("Corp.", "Corp_")
        .replace("Ltd.", "Ltd_")
    )
    return re.sub(
        EMAIL_RE,
        lambda match: match.group(0).replace(".", "_dot_"),
        protected,
    )


def _restore_protected(text: str) -> str:
    return (
        text.replace("_dot_", ".")
        .replace("a_m_", "a.m.")
        .replace("p_m_", "p.m.")
        .replace("A_M_", "A.M.")
        .replace("P_M_", "P.M.")
        .replace("Pte_Ltd_", "Pte. Ltd.")
        .replace("Corp_", "Corp.")
        .replace("Ltd_", "Ltd.")
    )


def _has_label(labels: list[str], text: str) -> bool:
    return any(re.search(rf"\b{re.escape(label)}\b", text, flags=re.IGNORECASE) for label in labels)


def _keyword_tokens(labels: list[str]) -> set[str]:
    return {
        token
        for label in labels
        for token in _text_tokens(label)
        if token not in STOPWORDS and len(token) > 2
    }


def _text_tokens(value: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", str(value or "").casefold()))


def _dedupe_contexts(contexts: list[str]) -> list[str]:
    deduped = []
    seen = set()
    for context in contexts:
        key = _normalize_space(context)
        if key and key not in seen:
            seen.add(key)
            deduped.append(context)
    return deduped


def _merged_metadata(metadata: Any, evidence: dict[str, Any]) -> dict[str, Any]:
    merged = metadata.copy() if isinstance(metadata, dict) else {}
    merged.setdefault("page", evidence.get("page"))
    merged.setdefault("source", evidence.get("source"))
    merged.setdefault("id", evidence.get("id"))
    merged.setdefault("segment_id", evidence.get("segment_id") or evidence.get("id"))
    return {key: value for key, value in merged.items() if value is not None}


def _normalize_keyword(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").casefold()).strip()


def _normalize_space(value: str) -> str:
    return " ".join(str(value or "").split())
