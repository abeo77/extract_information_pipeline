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
