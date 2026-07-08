"""Deterministic coverage pass tests."""

from app.extraction.coverage_extractor import apply_coverage_pass
from app.extraction.schemas import DocumentSegment


def test_coverage_pass_adds_generic_missing_groups_without_duplicates():
    segments = [
        DocumentSegment(
            segment_id="seg_001",
            page=1,
            source="contract.txt",
            text='This Agreement is made between Alpha Ltd. ("Company") and Beta LLC ("Client").',
        ),
        DocumentSegment(
            segment_id="seg_002",
            page=2,
            source="contract.txt",
            text="Late payments will incur a late payment charge of 1.5 percent per month on overdue accounts.",
        ),
    ]
    groups = [
        {
            "representative_keyword": "Parties",
            "related_keywords": ["Company", "Client"],
            "context_text": segments[0].text,
        }
    ]

    enriched, added, candidates = apply_coverage_pass(groups, segments, max_groups=12)

    assert added == 1
    assert candidates >= 1
    assert [group["representative_keyword"] for group in enriched] == ["Parties", "Late Payment"]
    assert enriched[1]["metadata"]["coverage_source"] == "deterministic"


def test_coverage_pass_respects_max_groups():
    segments = [
        DocumentSegment(
            segment_id="seg_001",
            page=1,
            source="contract.txt",
            text=(
                "This Agreement is made between Alpha Ltd. and Beta LLC. "
                "Payment Terms require invoices to be paid. "
                "Late payments incur a late payment charge. "
                "All notices must be sent by registered mail."
            ),
        )
    ]

    enriched, added, _ = apply_coverage_pass([], segments, max_groups=2)

    assert added == 2
    assert len(enriched) == 2


def test_adaptive_coverage_adds_fewer_groups_for_short_simple_documents():
    segments = [
        DocumentSegment(
            segment_id="seg_001",
            page=1,
            source="contract.txt",
            text=(
                "This Agreement is made between Alpha Ltd. and Beta LLC. "
                "Payment Terms require invoices to be paid. "
                "Late payments incur a late payment charge. "
                "All notices must be sent by registered mail."
            ),
        )
    ]
    existing = [{"representative_keyword": f"Existing {index}"} for index in range(12)]

    enriched, added, _ = apply_coverage_pass(existing, segments, max_groups=8, mode="adaptive")

    assert added <= 2
    assert len(enriched) == len(existing) + added


def test_coverage_refuses_business_specific_groups_from_opening_context():
    segments = [
        DocumentSegment(
            segment_id="seg_001",
            page=1,
            source="contract.txt",
            text=(
                "Exhibit 10.16\nMARKETING AFFILIATE AGREEMENT\n"
                "This Agreement is made between Alpha Ltd. and Beta LLC.\nRECITALS"
            ),
        )
    ]

    enriched, added, _ = apply_coverage_pass([], segments, max_groups=8, mode="adaptive")

    representatives = {group["representative_keyword"] for group in enriched}
    assert "Technology Description" not in representatives
    assert "Data Security and Access Control" not in representatives
    assert added <= 2
