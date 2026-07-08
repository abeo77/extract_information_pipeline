"""Keyword group merge tests."""

from app.extraction.group_merger import merge_keyword_groups


def test_merge_keyword_groups_deduplicates_representative_keyword():
    groups = [
        {
            "representative_keyword": "Contracting Parties",
            "related_keywords": ["Service Provider", "Client"],
            "context_text": (
                'This Basic Service Agreement is made between Alpha Solutions Ltd. '
                '("Service Provider") and Beta Retail JSC ("Client").'
            ),
            "exact_text": (
                'This Basic Service Agreement is made between Alpha Solutions Ltd. '
                '("Service Provider") and Beta Retail JSC ("Client").'
            ),
            "metadata": {"page": 1},
            "evidences": [
                {
                    "exact_text": (
                        'This Basic Service Agreement is made between Alpha Solutions Ltd. '
                        '("Service Provider") and Beta Retail JSC ("Client").'
                    ),
                    "id": "seg_001",
                }
            ],
        },
        {
            "representative_keyword": "Contracting Parties",
            "related_keywords": ["Alpha Solutions Ltd.", "Beta Retail JSC"],
            "context_text": "Service Provider: Alpha Solutions Ltd.\nClient: Beta Retail JSC",
            "exact_text": "Service Provider: Alpha Solutions Ltd.\nClient: Beta Retail JSC",
            "metadata": {"page": 2, "clause_no": "11"},
            "evidences": [
                {
                    "exact_text": "Service Provider: Alpha Solutions Ltd.\nClient: Beta Retail JSC",
                    "id": "seg_011",
                }
            ],
        },
    ]

    merged = merge_keyword_groups(groups)

    assert len(merged) == 1
    assert merged[0]["representative_keyword"] == "Parties"
    assert merged[0]["metadata"] == {"page": 1}
    assert "made between" in merged[0]["exact_text"]
    assert merged[0]["related_keywords"] == [
        "Service Provider",
        "Client",
        "Contracting Parties",
        "Alpha Solutions Ltd.",
        "Beta Retail JSC",
    ]


def test_merge_keyword_groups_combines_party_roles_only_in_intro_context():
    groups = [
        {
            "representative_keyword": "Service Provider",
            "related_keywords": [],
            "context_text": (
                'This Agreement is made between Alpha Solutions Ltd. ("Service Provider") '
                'and Beta Retail JSC ("Client").'
            ),
        },
        {
            "representative_keyword": "Client",
            "related_keywords": [],
            "context_text": (
                'This Agreement is made between Alpha Solutions Ltd. ("Service Provider") '
                'and Beta Retail JSC ("Client").'
            ),
        },
        {
            "representative_keyword": "Client",
            "related_keywords": [],
            "context_text": "The Client shall pay all invoices within thirty days.",
        },
    ]

    merged = merge_keyword_groups(groups)

    assert [group["representative_keyword"] for group in merged] == ["Parties", "Client"]
    assert "Service Provider" in merged[0]["related_keywords"]


def test_merge_keyword_groups_merges_payment_adjacent_only_same_context():
    groups = [
        {
            "representative_keyword": "Service Fee",
            "related_keywords": ["monthly fee"],
            "context_text": "Client shall pay a monthly service fee of USD 1,000.",
            "metadata": {"id": "seg_001"},
        },
        {
            "representative_keyword": "Payment Terms",
            "related_keywords": ["invoice"],
            "context_text": "Client shall pay a monthly service fee of USD 1,000.",
            "metadata": {"id": "seg_001"},
        },
        {
            "representative_keyword": "Payment Terms",
            "related_keywords": ["Net 30"],
            "context_text": "Invoices for support services are due Net 30.",
            "metadata": {"id": "seg_009"},
        },
    ]

    merged = merge_keyword_groups(groups)

    assert [group["representative_keyword"] for group in merged] == [
        "Payment Terms",
        "Payment Terms",
    ]
    assert "Service Fee" in merged[0]["related_keywords"]
    assert merged[1]["context_text"] == "Invoices for support services are due Net 30."
