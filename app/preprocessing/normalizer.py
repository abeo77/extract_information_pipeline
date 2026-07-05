"""Generic, conservative text normalization for contract pages."""

from __future__ import annotations

import re
import unicodedata
from collections import Counter

from langchain_core.documents import Document


ZERO_WIDTH_RE = re.compile(r"[\u200b-\u200f\u202a-\u202e\u2060\ufeff]")
CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
SECTION_NUMBER_RE = re.compile(r"^(?:\d+\.|\d+(?:\.\d+)+\.?|\([A-Za-z]\))$")
SECTION_START_RE = re.compile(r"^(?:\d+(?:\.\d+)*\.?|\([A-Za-z]\))\s+\S")
LIST_MARKER_RE = re.compile(r"^(?:[-*\u2022]|\([A-Za-z0-9]+\)|[A-Za-z]\.)\s+")
SOURCE_FOOTER_RE = re.compile(r"^(?:\d+\s+)?Source:\s+.+$", re.IGNORECASE)
LEGAL_HEADING_RE = re.compile(r"^(ARTICLE|SECTION|SCHEDULE|EXHIBIT|APPENDIX|ANNEX)\b", re.IGNORECASE)
SAFE_BOUNDARY_WORDS = (
    "All",
    "Any",
    "Each",
    "Either",
    "If",
    "Neither",
    "Notwithstanding",
    "Provided",
    "The",
    "This",
    "Upon",
    "When",
    "Where",
    "Whereas",
)


def normalize_documents(docs: list[Document]) -> list[Document]:
    page_lines = [_clean_lines(doc.page_content or "") for doc in docs]
    repeated_lines = detect_repeated_headers_footers(page_lines)

    normalized_docs = []
    for doc, lines in zip(docs, page_lines, strict=False):
        metadata = dict(doc.metadata)
        page_number = _as_int(metadata.get("page"))
        raw_text = doc.page_content or ""
        normalized_text, removed_footer_count = _normalize_lines(
            lines,
            page_number=page_number,
            repeated_lines=repeated_lines,
        )

        metadata.update(
            {
                "raw_text_length": len(raw_text),
                "normalized_text_length": len(normalized_text),
                "removed_footer_count": removed_footer_count,
            }
        )
        normalized_docs.append(Document(page_content=normalized_text, metadata=metadata))
    return normalized_docs


def normalize_contract_page_text(text: str, page_number: int | None = None) -> str:
    normalized_text, _ = _normalize_lines(
        _clean_lines(text),
        page_number=page_number,
        repeated_lines=set(),
    )
    return normalized_text


def detect_repeated_headers_footers(
    pages: list[list[str]],
    min_repetition_ratio: float = 0.4,
) -> set[str]:
    if len(pages) < 3:
        return set()

    candidates = Counter()
    for lines in pages:
        edge_lines = lines[:3] + lines[-3:]
        candidates.update(set(_canonical_footer_line(line) for line in edge_lines))

    min_count = max(2, int(len(pages) * min_repetition_ratio))
    return {
        line
        for line, count in candidates.items()
        if line and count >= min_count and not _is_repeated_footer_false_positive(line)
    }


def remove_footer_and_page_number(
    lines: list[str],
    page_number: int | None = None,
    repeated_lines: set[str] | None = None,
) -> list[str]:
    repeated_lines = repeated_lines or set()
    page_text = str(page_number) if page_number is not None else None

    return [
        line
        for line in lines
        if not (
            (page_text and line == page_text)
            or SOURCE_FOOTER_RE.match(line)
            or _canonical_footer_line(line) in repeated_lines
        )
        or _is_section_number(line)
    ]


def repair_orphan_section_numbers(lines: list[str]) -> list[str]:
    repaired = []
    index = 0

    while index < len(lines):
        line = lines[index]
        next_line = lines[index + 1] if index + 1 < len(lines) else ""

        if (
            _is_section_number(line)
            and next_line
            and not _is_section_number(next_line)
            and _is_heading_candidate(next_line)
        ):
            repaired.append(f"{line} {next_line}")
            index += 2
            continue

        repaired.append(line)
        index += 1
    return repaired


def join_wrapped_lines(lines: list[str]) -> list[str]:
    joined: list[str] = []

    for line in lines:
        if not joined or _starts_new_block(line) or _should_keep_after(joined[-1], line):
            joined.append(line)
            continue

        joined[-1] = _join_line(joined[-1], line)
    return joined


def _normalize_lines(
    lines: list[str],
    page_number: int | None,
    repeated_lines: set[str],
) -> tuple[str, int]:
    before_footer = len(lines)
    lines = remove_footer_and_page_number(lines, page_number, repeated_lines)
    removed_footer_count = before_footer - len(lines)
    lines = repair_orphan_section_numbers(lines)
    lines = join_wrapped_lines(lines)
    return "\n".join(lines).strip(), removed_footer_count


def _clean_lines(text: str) -> list[str]:
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\u00a0", " ").replace("\u037e", ";").replace("\u061b", ";")
    text = ZERO_WIDTH_RE.sub("", text)
    text = CONTROL_RE.sub("", text)
    text = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2\n", text)

    lines = []
    for line in text.splitlines():
        cleaned = _clean_inline_text(line)
        if cleaned:
            lines.append(cleaned)
    return lines


def _clean_inline_text(line: str) -> str:
    line = " ".join(line.split())
    line = re.sub(r"\s+([,.;:!?])", r"\1", line)
    line = re.sub(r"([;:!?])(?=\S)", r"\1 ", line)
    line = re.sub(r"(?<!\d),(?=\S)(?!\d)", ", ", line)
    line = re.sub(r"(?<=[A-Za-z]{2})\.(?=[A-Z])", ". ", line)
    line = _fix_safe_lower_to_upper_boundaries(line)
    return line.strip()


def _is_section_number(line: str) -> bool:
    return bool(SECTION_NUMBER_RE.match(line.strip()))


def _starts_new_block(line: str) -> bool:
    return (
        bool(SECTION_START_RE.match(line))
        or _is_section_number(line)
        or bool(LIST_MARKER_RE.match(line))
        or _looks_table_like(line)
    )


def _should_keep_after(previous: str, current: str) -> bool:
    if _is_heading_candidate(previous):
        return True
    if _looks_table_like(previous) or _looks_table_like(current):
        return True
    return bool(re.search(r'[.;:!?]"?$', previous))


def _join_line(previous: str, current: str) -> str:
    if previous.endswith("-"):
        return previous[:-1] + current
    return f"{previous} {current}"


def _fix_safe_lower_to_upper_boundaries(line: str) -> str:
    boundary_words = "|".join(SAFE_BOUNDARY_WORDS)
    return re.sub(rf"(?<=[a-z])(?=({boundary_words})\b)", " ", line)


def _is_heading_candidate(line: str) -> bool:
    line = re.sub(r"^(?:\d+(?:\.\d+)*\.?|\([A-Za-z]\))\s+", "", line).strip()
    words = line.rstrip(".:").split()
    if not words or len(words) > 12:
        return False
    if line.endswith((",", ";")):
        return False
    if line.isupper() and len(words) <= 10:
        return True
    title_words = sum(1 for word in words if word[:1].isupper())
    return title_words >= max(1, len(words) - 1)


def _looks_table_like(line: str) -> bool:
    if "\t" in line:
        return True
    if re.search(r"\s{2,}", line):
        return True
    return bool(re.search(r"(?:\$|%|\b\d{1,3}(?:,\d{3})+\b)", line))


def _canonical_footer_line(line: str) -> str:
    return re.sub(r"\d+", "#", line.strip().lower())


def _is_repeated_footer_false_positive(line: str) -> bool:
    return bool(LEGAL_HEADING_RE.match(line)) or _is_section_number(line)


def _as_int(value: object) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def normalize_text(text: str) -> str:
    return normalize_contract_page_text(text)
