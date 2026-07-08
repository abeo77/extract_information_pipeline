"""Pipeline tests for the two-stage LLM runtime path."""

from types import SimpleNamespace

from app import pipeline
from app.services.pipeline_service import build_config


def test_run_pipeline_calls_llm2_after_merge(monkeypatch, tmp_path):
    monkeypatch.setattr(
        pipeline,
        "load_document",
        lambda path: [SimpleNamespace(page_content="Effective Date is Jan 1.", metadata={})],
    )
    monkeypatch.setattr(pipeline, "normalize_documents", lambda documents: documents)
    monkeypatch.setattr(
        pipeline,
        "segment_documents",
        lambda documents: [
            SimpleNamespace(
                segment_id="seg_001",
                text="Effective Date is Jan 1.",
                title=None,
                page=1,
                source="contract.txt",
                metadata={},
            )
        ],
    )
    monkeypatch.setattr(
        pipeline,
        "extract_keywords",
        lambda *args, **kwargs: (
            [
                {
                    "representative_keyword": "Effective Date",
                    "related_keywords": ["Start Date"],
                    "context_text": "Effective Date is Jan 1.",
                }
            ],
            1,
        ),
    )
    monkeypatch.setattr(pipeline, "merge_keyword_groups", lambda groups: groups)
    monkeypatch.setattr(
        pipeline,
        "extract_evidence",
        lambda groups, segments, chat_model, **kwargs: (
            [
                {
                    **groups[0],
                    "context_text": "Effective Date is Jan 1.",
                    "exact_text": "Jan 1",
                    "evidences": [
                        {
                            "context_text": "Effective Date is Jan 1.",
                            "exact_text": "Jan 1",
                            "page": 1,
                            "id": "seg_001",
                            "segment_id": "seg_001",
                            "source": "contract.txt",
                            "validation_status": "passed",
                            "confidence": 0.95,
                        }
                    ],
                }
            ],
            1,
        ),
    )
    monkeypatch.setattr(pipeline, "create_chat_model", lambda *args, **kwargs: object())

    result = pipeline.run_pipeline(
        "contract.txt",
        tmp_path / "result.json",
        build_config(),
    )

    assert result.total_keyword_groups == 1
    assert result.keyword_groups[0]["exact_text"] == "Jan 1"
    assert result.llm_calls.keyword_extraction_batches == 1
    assert result.llm_calls.keyword_groups_for_evidence == 1
    assert result.llm_calls.evidence_extraction_batches == 1


def test_run_pipeline_records_coverage_added_groups(monkeypatch, tmp_path):
    segment = SimpleNamespace(
        segment_id="seg_001",
        text="Late payments will incur a late payment charge of 1.5 percent per month.",
        title=None,
        page=1,
        source="contract.txt",
        metadata={},
    )
    coverage_group = {
        "representative_keyword": "Late Payment",
        "related_keywords": ["Late Payment Charge"],
        "context_text": segment.text,
        "metadata": {"id": "seg_001", "page": 1, "source": "contract.txt"},
    }
    monkeypatch.setattr(
        pipeline,
        "load_document",
        lambda path: [SimpleNamespace(page_content=segment.text, metadata={})],
    )
    monkeypatch.setattr(pipeline, "normalize_documents", lambda documents: documents)
    monkeypatch.setattr(pipeline, "segment_documents", lambda documents: [segment])
    monkeypatch.setattr(pipeline, "extract_keywords", lambda *args, **kwargs: ([], 1))
    monkeypatch.setattr(pipeline, "merge_keyword_groups", lambda groups: groups)
    monkeypatch.setattr(
        pipeline,
        "apply_coverage_pass",
        lambda groups, segments, max_groups, mode: ([coverage_group], 1, 1),
    )
    monkeypatch.setattr(pipeline, "filter_keyword_groups", lambda groups: (groups, 0))
    monkeypatch.setattr(
        pipeline,
        "apply_local_evidence",
        lambda groups, segments: (
            [
                {
                    **groups[0],
                    "exact_text": "late payment charge of 1.5 percent per month",
                    "evidences": [
                        {
                            "context_text": segment.text,
                            "exact_text": "late payment charge of 1.5 percent per month",
                            "page": 1,
                            "id": "seg_001",
                            "segment_id": "seg_001",
                            "source": "contract.txt",
                            "validation_status": "passed",
                            "confidence": 0.99,
                        }
                    ],
                }
            ],
            [],
        ),
    )
    monkeypatch.setattr(pipeline, "create_chat_model", lambda *args, **kwargs: object())

    result = pipeline.run_pipeline(
        "contract.txt",
        tmp_path / "result.json",
        build_config(),
    )

    assert result.total_keyword_groups == 1
    assert result.llm_calls.coverage_added_groups == 1
    assert result.llm_calls.coverage_candidate_groups == 1
    assert result.llm_calls.filtered_groups == 0
    assert result.llm_calls.max_total_llm_calls == 8
