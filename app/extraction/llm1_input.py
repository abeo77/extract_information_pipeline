"""Compact segment payloads before keyword extraction by LLM 1."""

from __future__ import annotations

import re
from collections.abc import Iterable

from app.extraction.schemas import DocumentSegment, Llm1BatchInput, Llm1SegmentInput


DEFAULT_LLM1_BATCH_SIZE = 50

CLAUSE_NO_RE = re.compile(
    r"^\s*(?P<num>(?:\d+(?:\.\d+)*\.?)|(?:\([A-Za-z0-9]+\))|(?:[A-Za-z]\.))\s+"
)
WHITESPACE_RE = re.compile(r"\s+")


def prepare_llm1_batches(
    segments: list[DocumentSegment],
    batch_size: int = DEFAULT_LLM1_BATCH_SIZE,
) -> list[Llm1BatchInput]:
    """Build token-lean LLM1 payloads grouped by source.

    Source is kept once at batch level. Per segment we only keep the fields LLM1
    needs for keyword extraction and evidence mapping.
    """
    if batch_size <= 0:
        raise ValueError("batch_size must be greater than 0")

    batches: list[Llm1BatchInput] = []
    for source, source_segments in _group_by_source(segments):
        compact_segments = [
            prepare_llm1_segment_input(segment)
            for segment in source_segments
        ]
        for start in range(0, len(compact_segments), batch_size):
            batches.append(
                Llm1BatchInput(
                    source=source,
                    segments=compact_segments[start : start + batch_size],
                )
            )
    return batches


def prepare_llm1_segment_input(segment: DocumentSegment) -> Llm1SegmentInput:
    text_without_title = _strip_segment_title(segment.text, segment.title)
    clause_no = _extract_clause_no(segment.title) or _extract_clause_no(text_without_title)
    compact_text = _compact_text(text_without_title)

    return Llm1SegmentInput(
        segment_id=segment.segment_id,
        page=segment.page,
        parent_section_title=segment.metadata.get("parent_section_title"),
        clause_no=clause_no,
        text=compact_text,
    )


def remove_reason_fields(items: list[dict]) -> list[dict]:
    """Drop optional LLM1 reason fields before saving or sending to later steps."""
    return [_remove_reason_field(item) for item in items]


def _group_by_source(
    segments: Iterable[DocumentSegment],
) -> list[tuple[str | None, list[DocumentSegment]]]:
    groups: list[tuple[str | None, list[DocumentSegment]]] = []
    positions: dict[str | None, int] = {}

    for segment in segments:
        source = segment.source or segment.metadata.get("source")
        if source not in positions:
            positions[source] = len(groups)
            groups.append((source, []))
        groups[positions[source]][1].append(segment)
    return groups


def _strip_segment_title(text: str, title: str | None) -> str:
    text = (text or "").strip()
    title = (title or "").strip()
    if not text or not title:
        return text

    lines = text.splitlines()
    if lines and _same_heading(lines[0], title):
        return "\n".join(lines[1:]).strip()
    if text.startswith(title):
        return text[len(title) :].lstrip(" \t\r\n-:.;")
    return text


def _same_heading(line: str, title: str) -> bool:
    return _normalize_heading(line) == _normalize_heading(title)


def _normalize_heading(value: str) -> str:
    return WHITESPACE_RE.sub(" ", value.strip().rstrip(".:;")).casefold()


def _extract_clause_no(text: str | None) -> str | None:
    if not text:
        return None
    match = CLAUSE_NO_RE.match(text)
    if not match:
        return None
    return match.group("num").rstrip(".")


def _compact_text(text: str) -> str:
    return WHITESPACE_RE.sub(" ", (text or "").strip())


def _remove_reason_field(value):
    if isinstance(value, dict):
        return {
            key: _remove_reason_field(child)
            for key, child in value.items()
            if key != "reason"
        }
    if isinstance(value, list):
        return [_remove_reason_field(item) for item in value]
    return value
