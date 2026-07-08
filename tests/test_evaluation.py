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
