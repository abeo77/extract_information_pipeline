"""Deterministic contract segmentation for normalized pages."""

from __future__ import annotations

import re
from dataclasses import dataclass

from langchain_core.documents import Document

from app.extraction.schemas import DocumentSegment


DEFAULT_MAX_TOKENS = 700
DEFAULT_MIN_TOKENS = 40

TOKEN_RE = re.compile(r"\S+")
NUMBERED_RE = re.compile(r"^(?P<num>\d+\.|\d+(?:\.\d+)+\.?)\s+(?P<body>\S.*)$")
BULLET_RE = re.compile(r"^(?P<num>\([A-Za-z0-9]+\)|[a-z]\.)\s+\S")
STRUCTURE_RE = re.compile(r"^(ARTICLE|SECTION|SCHEDULE|EXHIBIT|APPENDIX|ANNEX)\b.*", re.I)
SIGNATURE_RE = re.compile(
    r"^(IN WITNESS WHEREOF|SIGNATURES?|SIGNED|AGREED AND ACCEPTED|ACCEPTED AND AGREED)\b",
    re.I,
)


@dataclass(frozen=True)
class Line:
    text: str
    page: int | None
    source: str | None


@dataclass(frozen=True)
class Heading:
    index: int
    title: str
    kind: str
    level: int = 1


@dataclass(frozen=True)
class Block:
    lines: list[Line]
    title: str | None
    kind: str
    level: int = 1
    parent_section_title: str | None = None

    @property
    def text(self) -> str:
        return "\n".join(line.text for line in self.lines).strip()

    @property
    def source(self) -> str | None:
        return self.lines[0].source

    @property
    def start_page(self) -> int | None:
        return self.lines[0].page

    @property
    def end_page(self) -> int | None:
        return self.lines[-1].page


def segment_documents(documents: list[Document]) -> list[DocumentSegment]:
    return segment_contract(documents)


def segment_contract(
    documents: list[Document],
    max_tokens: int = DEFAULT_MAX_TOKENS,
    min_tokens: int = DEFAULT_MIN_TOKENS,
) -> list[DocumentSegment]:
    lines = _page_lines(documents)
    blocks = build_section_blocks(lines, detect_headings(lines))
    segments: list[DocumentSegment] = []

    for block in blocks:
        chunks = split_by_max_tokens(block.text, max_tokens, min_tokens)
        for chunk_index, chunk in enumerate(chunks, 1):
            segments.append(_segment(len(segments) + 1, block, chunk, chunk_index, len(chunks)))
    return _number_parent_chunks(segments)


def detect_headings(lines: list[Line]) -> list[Heading]:
    headings = []
    for index, line in enumerate(lines):
        text = line.text.strip()
        if SIGNATURE_RE.match(text):
            headings.append(Heading(index, text, "signature"))
        elif STRUCTURE_RE.match(text):
            headings.append(Heading(index, text, _structure_kind(text)))
        elif match := NUMBERED_RE.match(text):
            number = match.group("num")
            headings.append(Heading(index, _numbered_title(text, match), "section", _level(number)))
        elif match := BULLET_RE.match(text):
            headings.append(Heading(index, match.group("num"), "bullet", 99))
    return headings


def build_section_blocks(lines: list[Line], headings: list[Heading]) -> list[Block]:
    if not lines:
        return []
    if not headings:
        return [Block(lines, None, "document")]

    blocks: list[Block] = []
    parents: dict[int, str] = {}

    if headings[0].index:
        blocks.append(Block(lines[: headings[0].index], None, "opening"))

    for index, heading in enumerate(headings):
        next_index = headings[index + 1].index if index + 1 < len(headings) else len(lines)
        block_lines = lines[heading.index : next_index]
        title = _block_title(heading, block_lines)
        parent = _parent_title(heading, parents)
        _remember_parent(heading, title, parents)

        if _is_empty_parent_heading(block_lines, heading):
            continue
        blocks.append(Block(block_lines, title, heading.kind, heading.level, parent))
    return blocks


def split_by_max_tokens(
    text: str,
    max_tokens: int,
    min_tokens: int = DEFAULT_MIN_TOKENS,
) -> list[str]:
    if max_tokens <= 0:
        raise ValueError("max_tokens must be greater than 0")

    text = text.strip()
    if _token_count(text) <= max_tokens:
        return [text]

    chunks: list[str] = []
    current = ""
    for piece in _pieces_that_fit(text, max_tokens):
        candidate = f"{current}\n{piece}".strip() if current else piece
        if current and _token_count(candidate) > max_tokens:
            chunks.append(current)
            current = piece
        else:
            current = candidate
    if current:
        chunks.append(current)
    return _merge_short_chunks(chunks, max_tokens, min_tokens)


def _page_lines(documents: list[Document]) -> list[Line]:
    rows = []
    for doc in documents:
        metadata = doc.metadata
        for line in (doc.page_content or "").splitlines():
            if line.strip():
                rows.append(Line(line.strip(), metadata.get("page"), metadata.get("source")))
    return rows


def _segment(
    number: int,
    block: Block,
    text: str,
    chunk_index: int,
    chunk_total: int,
) -> DocumentSegment:
    token_count = _token_count(text)
    return DocumentSegment(
        segment_id=f"seg_{number:03d}",
        text=text,
        title=block.title,
        page=block.start_page,
        source=block.source,
        metadata={
            "source": block.source,
            "page": block.start_page,
            "parent_section_title": block.parent_section_title,
            "token_count": token_count,
            "chunk_index": chunk_index,
            "chunk_total": chunk_total,
            "is_continuation": chunk_index < chunk_total,
        },
    )


def _parent_title(heading: Heading, parents: dict[int, str]) -> str | None:
    if heading.kind == "bullet":
        return parents[max(parents)] if parents else None
    if heading.kind != "section" or heading.level == 1:
        return None
    return parents.get(heading.level - 1) or parents.get(1)


def _remember_parent(heading: Heading, title: str, parents: dict[int, str]) -> None:
    if heading.kind != "section":
        return
    parents[heading.level] = title
    for level in list(parents):
        if level > heading.level:
            del parents[level]


def _numbered_title(text: str, match: re.Match[str]) -> str:
    number, body = match.group("num"), match.group("body")
    for stop in re.finditer(r"[.:](?:\s|$)", body):
        candidate = body[: stop.start() + 1]
        if len(candidate) > 140:
            break
        if not re.fullmatch(r"(?:[A-Z]\.\s*)+", candidate):
            return f"{number} {candidate}"
    return text


def _is_empty_parent_heading(lines: list[Line], heading: Heading) -> bool:
    return (
        len(lines) <= 2
        and lines[0].text == heading.title
        and (heading.kind != "section" or heading.level == 1)
        and all(_looks_like_parent_title(line.text) for line in lines[1:])
    )


def _block_title(heading: Heading, lines: list[Line]) -> str:
    if (
        heading.kind == "section"
        and heading.level == 1
        and len(lines) > 1
        and _looks_like_parent_title(lines[1].text)
    ):
        return f"{heading.title} {lines[1].text}"
    return heading.title


def _looks_like_parent_title(text: str) -> bool:
    if text.strip().endswith((".", ";", ",")):
        return False
    words = text.rstrip(".").split()
    return bool(words) and len(words) <= 8 and (
        text.isupper() or sum(word[:1].isupper() for word in words) >= len(words) - 1
    )


def _level(number: str) -> int:
    return len(number.rstrip(".").split("."))


def _structure_kind(text: str) -> str:
    word = text.split()[0].lower()
    return word if word in {"schedule", "exhibit", "appendix", "annex"} else "section"


def _pieces_that_fit(text: str, max_tokens: int) -> list[str]:
    pieces = []
    for paragraph in _paragraphs(text):
        if _token_count(paragraph) <= max_tokens:
            pieces.append(paragraph)
            continue
        for sentence in _sentences(paragraph):
            pieces.extend(_token_windows(sentence, max_tokens))
    return pieces


def _paragraphs(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"\n\s*\n|\n", text) if part.strip()]


def _sentences(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"(?<=[.!?;])\s+(?=[A-Z0-9(\"])", text) if part.strip()]


def _token_windows(text: str, max_tokens: int) -> list[str]:
    spans = [match.span() for match in TOKEN_RE.finditer(text)]
    return [
        text[window[0][0] : window[-1][1]].strip()
        for start in range(0, len(spans), max_tokens)
        if (window := spans[start : start + max_tokens])
    ]


def _merge_short_chunks(chunks: list[str], max_tokens: int, min_tokens: int) -> list[str]:
    if min_tokens <= 0 or len(chunks) < 2:
        return chunks

    merged: list[str] = []
    for chunk in chunks:
        if merged and _token_count(chunk) < min_tokens:
            candidate = f"{merged[-1]}\n{chunk}"
            if _token_count(candidate) <= max_tokens:
                merged[-1] = candidate
                continue
        merged.append(chunk)
    return merged


def _token_count(text: str) -> int:
    return len(TOKEN_RE.findall(text))


def _number_parent_chunks(segments: list[DocumentSegment]) -> list[DocumentSegment]:
    groups: dict[tuple[str | None, str], list[int]] = {}
    for index, segment in enumerate(segments):
        parent = segment.metadata.get("parent_section_title")
        if parent:
            groups.setdefault((segment.source, parent), []).append(index)

    numbered = list(segments)
    for indexes in groups.values():
        total = len(indexes)
        for position, index in enumerate(indexes, 1):
            segment = numbered[index]
            metadata = dict(segment.metadata)
            metadata.update(
                {
                    "chunk_index": position,
                    "chunk_total": total,
                    "is_continuation": position < total,
                }
            )
            numbered[index] = segment.model_copy(update={"metadata": metadata})
    return numbered
