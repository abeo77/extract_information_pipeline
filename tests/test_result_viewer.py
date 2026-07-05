"""UI result table formatting tests."""

from ui.components.result_viewer import _result_rows


def test_result_rows_match_contract_keyword_table_columns():
    data = {
        "keyword_groups": [
            {
                "representative_keyword": "Effective Date",
                "related_keywords": ["Commencement Date", "Start Date"],
                "context_text": "The Effective Date is April 1, 2026.",
                "exact_text": "April 1, 2026",
            }
        ]
    }

    assert _result_rows(data) == [
        {
            "Representative Keyword": "Effective Date",
            "Grouped Keywords": "Effective Date, Commencement Date, Start Date",
            "Context Text": "The Effective Date is April 1, 2026.",
            "Exact Extracted Information": "April 1, 2026",
        }
    ]


def test_result_rows_deduplicate_representative_in_grouped_keywords():
    data = {
        "keyword_groups": [
            {
                "representative_keyword": "Agreement Date",
                "related_keywords": ["Agreement Date", "Contract Date"],
                "context_text": "Agreement Date March 15, 2026",
                "exact_text": "March 15, 2026",
            }
        ]
    }

    assert _result_rows(data)[0]["Grouped Keywords"] == "Agreement Date, Contract Date"
