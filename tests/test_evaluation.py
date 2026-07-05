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
