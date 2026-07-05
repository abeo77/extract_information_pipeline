"""Segmenter smoke tests."""

from langchain_core.documents import Document

from app.preprocessing.normalizer import normalize_documents
from app.segmentation.contract_segmenter import segment_documents


def test_segmenter_detects_title_opening_and_clauses():
    docs = [
        Document(
            page_content=(
                "SERVICE AGREEMENT\n"
                "This agreement is made today.\n"
                "1. Parties\nAlpha signs with Beta.\n"
                "2. Payment\nBeta pays Alpha."
            ),
            metadata={"source": "sample.txt", "page": 1},
        )
    ]
    segments = segment_documents(normalize_documents(docs))
    assert [segment.title for segment in segments[-2:]] == ["1. Parties", "2. Payment"]
    assert "Alpha signs with Beta." in segments[-2].text
