"""Result formatting tests."""

from app.services.result_service import compact_result


def test_compact_result_removes_repeated_evidences():
    result = {
        "document_name": "contract.pdf",
        "total_keyword_groups": 1,
        "keyword_items": [],
        "keyword_groups": [
            {
                "representative_keyword": "Effective Date",
                "related_keywords": ["Commencement Date", "Start Date"],
                "context_text": "Effective Date: January 1, 2026.",
                "metadata": {
                    "page": 1,
                    "id": "seg_003",
                    "segment_id": "seg_003",
                    "source": "contract.pdf",
                    "clause_no": "2",
                },
                "evidences": [
                    {
                        "context_text": "Effective Date: January 1, 2026.",
                        "exact_text": "Effective Date: January 1, 2026.",
                        "page": 1,
                        "id": "seg_003",
                        "segment_id": "seg_003",
                        "source": "contract.pdf",
                        "validation_status": "passed",
                    }
                ],
            }
        ],
    }

    compact = compact_result(result)

    assert compact["keyword_groups"] == [
        {
            "representative_keyword": "Effective Date",
            "related_keywords": ["Commencement Date", "Start Date"],
            "context_text": "Effective Date: January 1, 2026.",
            "exact_text": "Effective Date: January 1, 2026.",
            "metadata": {"page": 1, "clause_no": "2"},
        }
    ]
    assert "keyword_items" not in compact


def test_compact_result_uses_context_as_exact_text_without_llm2_evidence():
    compact = compact_result(
        {
            "keyword_groups": [
                {
                    "representative_keyword": "Termination",
                    "related_keywords": [],
                    "context_text": "Either party may terminate on 30 days notice.",
                }
            ]
        }
    )

    assert compact["keyword_groups"][0]["exact_text"] == (
        "Either party may terminate on 30 days notice."
    )


def test_compact_result_does_not_promote_llm2_context_to_exact_text():
    compact = compact_result(
        {
            "keyword_groups": [
                {
                    "representative_keyword": "End Date",
                    "related_keywords": ["Expiration Date"],
                    "context_text": "End Date: December 31, 2026. Effective Date: January 1, 2026.",
                    "evidences": [
                        {
                            "context_text": "End Date: December 31, 2026. Effective Date: January 1, 2026.",
                            "exact_text": "",
                            "validation_status": "passed",
                        }
                    ],
                }
            ]
        }
    )

    assert "exact_text" not in compact["keyword_groups"][0]
