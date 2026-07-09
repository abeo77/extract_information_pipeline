"""Ground-truth evaluation tests."""

import json

from app.evaluation.evaluate_ground_truth import compare_keywords


def test_compare_keywords_reports_missing_and_extra(tmp_path):
    result = tmp_path / "result.json"
    truth = tmp_path / "truth.json"
    result.write_text(json.dumps({"keyword_groups": [{"representative_keyword": "Payment"}]}))
    truth.write_text(json.dumps({"keyword_groups": [{"representative_keyword": "Term"}]}))

    report = compare_keywords(result, truth)
    assert report["matched"] == 0
    assert report["missing"] == ["term"]
    assert report["extra"] == ["payment"]


def test_compare_keywords_supports_document_provision_ground_truth(tmp_path):
    result = tmp_path / "result.json"
    truth = tmp_path / "truth.json"
    result.write_text(
        json.dumps(
            {
                "document_name": "contract.pdf",
                "processing_time_seconds": 12.5,
                "total_segments": 4,
                "keyword_groups": [
                    {
                        "representative_keyword": "Effective Date",
                        "related_keywords": ["Start Date"],
                        "context_text": "Effective Date: April 1, 2026.",
                        "exact_text": "April 1, 2026",
                    }
                ],
            }
        )
    )
    truth.write_text(
        json.dumps(
            {
                "document": {
                    "document_name": "contract.pdf",
                    "provisions": [
                        {
                            "provision": "Effective Date and Contract Term",
                            "specific_keywords": ["Effective Date", "Start Date"],
                            "text": "Effective Date: April 1, 2026.",
                        }
                    ],
                }
            }
        )
    )

    report = compare_keywords(result, truth)

    assert report["processing_time_seconds"] == 12.5
    assert report["matched"] == 1
    assert report["accuracy_percent"] == 100.0


def test_compare_keywords_supports_sponsorship_keyword_group_schema(tmp_path):
    result = tmp_path / "result.json"
    truth = tmp_path / "truth.json"
    result.write_text(
        json.dumps(
            {
                "keyword_groups": [
                    {
                        "representative_keyword": "Payment Terms",
                        "related_keywords": ["Consideration", "amount due"],
                        "context_text": "Hydron shall pay $96,000 as consideration.",
                        "exact_text": "Hydron shall pay $96,000",
                        "metadata": {"page": 1},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    truth.write_text(
        json.dumps(
            {
                "keyword_groups": [
                    {
                        "id": "gt_001",
                        "representative_keyword": "Consideration and Payment",
                        "specific_keywords": ["Consideration", "payment schedule", "fees"],
                        "text": "Hydron shall pay $96,000 as consideration.",
                        "evidences": [
                            {
                                "exact_text": "Hydron shall pay $96,000",
                                "page": 1,
                            }
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    report = compare_keywords(result, truth)

    assert report["matched"] == 1
    assert report["missing"] == []
    assert report["extra"] == []


def test_compare_keywords_matches_minor_label_variants(tmp_path):
    result = tmp_path / "result.json"
    truth = tmp_path / "truth.json"
    result.write_text(
        json.dumps(
            {
                "keyword_groups": [
                    {
                        "representative_keyword": "Non-Recourse",
                        "context_text": "No personal liability shall attach.",
                        "exact_text": "No personal liability shall attach.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    truth.write_text(
        json.dumps(
            {
                "keyword_groups": [
                    {
                        "representative_keyword": "No Recourse",
                        "specific_keywords": ["Non-Recourse Parties"],
                        "text": "No personal liability shall attach.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    report = compare_keywords(result, truth)

    assert report["matched"] == 1
    assert report["missing"] == []
    assert report["extra"] == []
    assert report["accuracy_percent"] >= 85.0
