"""Evaluation suite command tests."""

import json
import os

from app.evaluation.run_evaluation_suite import newest_result_for_number, run_evaluation_suite


def test_newest_result_for_number_uses_latest_matching_file(tmp_path):
    old_result = tmp_path / "4_result.json"
    new_result = tmp_path / "4_3_result.json"
    unrelated = tmp_path / "14_result.json"

    old_result.write_text("{}", encoding="utf-8")
    new_result.write_text("{}", encoding="utf-8")
    unrelated.write_text("{}", encoding="utf-8")
    os.utime(old_result, (100, 100))
    os.utime(new_result, (200, 200))
    os.utime(unrelated, (300, 300))

    assert newest_result_for_number(4, tmp_path) == new_result


def test_run_evaluation_suite_writes_reports_and_readme(tmp_path):
    result_dir = tmp_path / "output"
    truth_dir = tmp_path / "ground_truth"
    evaluation_dir = tmp_path / "evaluation"
    result_dir.mkdir()
    truth_dir.mkdir()

    (result_dir / "1_result.json").write_text(
        json.dumps(
            {
                "document_name": "1.pdf",
                "processing_time_seconds": 1.25,
                "keyword_groups": [
                    {
                        "representative_keyword": "Payment",
                        "related_keywords": ["Fees"],
                        "context_text": "Payment must be made within 30 days.",
                        "exact_text": "within 30 days",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (truth_dir / "ground_truth_1.json").write_text(
        json.dumps(
            {
                "keyword_groups": [
                    {
                        "representative_keyword": "Payment",
                        "related_keywords": ["Fees"],
                        "context_text": "Payment must be made within 30 days.",
                        "exact_text": "within 30 days",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = run_evaluation_suite(
        result_dir=result_dir,
        ground_truth_dir=truth_dir,
        output_dir=evaluation_dir,
    )

    assert len(result["runs"]) == 1
    assert (evaluation_dir / "1_eval_report.json").exists()
    readme = (evaluation_dir / "README.md").read_text(encoding="utf-8")
    assert "Evaluation Report" in readme
    assert "Average overall accuracy" in readme
    assert "`1_result.json`" in readme
