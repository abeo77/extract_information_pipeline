"""Load PDF/TXT documents while preserving page metadata."""

from pathlib import Path

from langchain_core.documents import Document

SUPPORTED_EXTENSIONS = {".pdf", ".txt"}


def load_document(file_path: str | Path) -> list[Document]:
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"Input file not found: {path}")

    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _load_pdf(path)
    if suffix == ".txt":
        return [
            Document(page_content=path.read_text(encoding="utf-8"), metadata=_meta(path, 0, 1))
        ]
    raise ValueError(f"Unsupported file format '{suffix}'. Use: {sorted(SUPPORTED_EXTENSIONS)}")


def _load_pdf(path: Path) -> list[Document]:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    if reader.is_encrypted:
        reader.decrypt("")

    total = len(reader.pages)
    return [
        Document(page_content=_extract_page_text(page), metadata=_meta(path, index, total))
        for index, page in enumerate(reader.pages)
    ]


def _extract_page_text(page) -> str:
    fragments = []

    def collect(text, _cm, tm, _font_dict, _font_size):
        cleaned = " ".join(text.split())
        if cleaned:
            fragments.append((float(tm[5]), float(tm[4]), cleaned))

    plain_text = page.extract_text() or ""
    page.extract_text(visitor_text=collect)
    if not fragments:
        return plain_text

    if _needs_plain_text_fallback(fragments):
        return plain_text
    rows = _group_fragments_by_line(fragments)
    return "\n".join(" ".join(text for _x, text in row) for _y, row in rows)


def _needs_plain_text_fallback(fragments: list[tuple[float, float, str]]) -> bool:
    zero_y_text = " ".join(
        text
        for y, _x, text in fragments
        if y <= 1.0 and not text.lower().startswith("source:")
    )
    return len(zero_y_text.split()) > 12


def _group_fragments_by_line(
    fragments: list[tuple[float, float, str]],
    y_tolerance: float = 6.0,
) -> list[tuple[float, list[tuple[float, str]]]]:
    rows: list[tuple[float, list[tuple[float, str]]]] = []
    for y, x, text in sorted(fragments, key=lambda item: (-item[0], item[1])):
        for row_index, (row_y, row) in enumerate(rows):
            if abs(row_y - y) <= y_tolerance:
                row.append((x, text))
                rows[row_index] = ((row_y + y) / 2, row)
                break
        else:
            rows.append((y, [(x, text)]))

    return [(y, sorted(row, key=lambda item: item[0])) for y, row in rows]


def _meta(path: Path, page_index: int, total_pages: int) -> dict:
    page = page_index + 1
    return {
        "source": str(path),
        "page": page,
        "page_label": str(page),
        "total_pages": total_pages,
    }
