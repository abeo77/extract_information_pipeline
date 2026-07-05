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
    assert merged[0]["representative_keyword"] == "Contracting Parties"
    assert merged[0]["metadata"] == {"page": 1}
    assert "made between" in merged[0]["exact_text"]
    assert merged[0]["related_keywords"] == [
        "Service Provider",
        "Client",
        "Alpha Solutions Ltd.",
        "Beta Retail JSC",
        "Contracting Parties",
    ]
