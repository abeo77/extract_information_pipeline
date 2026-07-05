"""LLM1 payload compaction tests."""

from app.extraction.llm1_input import prepare_llm1_batches, remove_reason_fields
from app.extraction.schemas import DocumentSegment


def test_prepare_llm1_batches_keeps_source_at_batch_level_and_strips_metadata():
    segment = DocumentSegment(
        segment_id="seg_001",
        title="1. Payment Terms",
        page=3,
        source="contract.txt",
        text="1. Payment Terms\nCustomer must pay the invoice within thirty days.",
        metadata={
            "source": "contract.txt",
            "page": 3,
            "parent_section_title": "ARTICLE II COMMERCIAL TERMS",
            "token_count": 42,
            "chunk_index": 1,
        },
    )

    batches = prepare_llm1_batches([segment])

    assert len(batches) == 1
    payload = batches[0].model_dump(exclude_none=True)
    assert payload == {
        "source": "contract.txt",
        "segments": [
            {
                "segment_id": "seg_001",
                "page": 3,
                "parent_section_title": "ARTICLE II COMMERCIAL TERMS",
                "clause_no": "1",
                "text": "Customer must pay the invoice within thirty days.",
            }
        ],
    }


def test_prepare_llm1_batches_keeps_full_text_without_char_limit():
    text = ("This sentence is intentionally repeated for a compact input check. " * 20).strip()
    segment = DocumentSegment(
        segment_id="seg_002",
        page=4,
        source="contract.txt",
        text=text,
    )

    compact = prepare_llm1_batches([segment])[0].segments[0].text

    assert compact == text


def test_prepare_llm1_batches_splits_sources_and_batch_size():
    segments = [
        DocumentSegment(segment_id="seg_001", text="First", source="a.txt"),
        DocumentSegment(segment_id="seg_002", text="Second", source="a.txt"),
        DocumentSegment(segment_id="seg_003", text="Third", source="b.txt"),
    ]

    batches = prepare_llm1_batches(segments, batch_size=1)

    assert [batch.source for batch in batches] == ["a.txt", "a.txt", "b.txt"]
    assert [[segment.segment_id for segment in batch.segments] for batch in batches] == [
        ["seg_001"],
        ["seg_002"],
        ["seg_003"],
    ]


def test_remove_reason_fields_recursively():
    items = [
        {
            "keyword": "payment",
            "reason": "not needed",
            "evidences": [{"text": "pay", "reason": "also not needed"}],
        }
    ]

    assert remove_reason_fields(items) == [
        {"keyword": "payment", "evidences": [{"text": "pay"}]}
    ]
