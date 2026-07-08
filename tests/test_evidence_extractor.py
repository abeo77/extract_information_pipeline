"""LLM2 evidence extractor tests."""

import json
import time

from app.extraction.evidence_extractor import extract_evidence
from app.extraction.local_evidence_extractor import apply_local_evidence
from app.extraction.schemas import DocumentSegment


class FakeChatModel:
    def __init__(self, payload):
        self.payload = payload
        self.prompts = []

    def invoke(self, prompt):
        self.prompts.append(prompt)
        return json.dumps(self.payload)


class PromptAwareFakeChatModel:
    def __init__(self):
        self.prompts = []

    def invoke(self, prompt):
        self.prompts.append(prompt)
        if '"First Keyword"' in prompt:
            time.sleep(0.02)
            keyword = "First Keyword"
            segment_id = "seg_001"
        else:
            keyword = "Second Keyword"
            segment_id = "seg_002"
        return json.dumps(
            {
                "keyword_groups": [
                    {
                        "representative_keyword": keyword,
                        "evidences": [
                            {
                                "evidence_text": keyword,
                                "exact_text": keyword,
                                "page": 1,
                                "id": segment_id,
                                "source": "contract.txt",
                                "validation_status": "passed",
                                "confidence": 0.9,
                            }
                        ],
                    }
                ]
            }
        )


def test_extract_evidence_batches_keyword_groups_with_relevant_segments():
    model = FakeChatModel(
        {
            "keyword_groups": [
                {
                    "representative_keyword": "Payment Terms",
                    "related_keywords": ["monthly service fee", "invoice"],
                    "evidences": [
                        {
                            "evidence_text": "monthly service fee of USD 2,000",
                            "exact_text": "The Client shall pay the Service Provider a monthly service fee of USD 2,000.",
                            "page": 1,
                            "id": "seg_005",
                            "source": "contract.txt",
                            "validation_status": "passed",
                            "confidence": 0.95,
                        }
                    ],
                }
            ]
        }
    )
    keyword_groups = [
        {
            "representative_keyword": "Payment Terms",
            "provision_type": "payment",
            "related_keywords": ["monthly service fee", "invoice"],
            "metadata": {"id": "seg_005", "page": 1, "source": "contract.txt"},
        }
    ]
    segments = [
        DocumentSegment(
            segment_id="seg_004",
            page=1,
            source="contract.txt",
            text="The Service Provider shall provide monitoring services.",
        ),
        DocumentSegment(
            segment_id="seg_005",
            page=1,
            source="contract.txt",
            text="The Client shall pay the Service Provider a monthly service fee of USD 2,000.",
        ),
    ]

    enriched, batch_count = extract_evidence(keyword_groups, segments, model)

    assert batch_count == 1
    batch_json = model.prompts[0].split("Evidence extraction batch JSON:\n", 1)[1]
    assert '"id": "seg_005"' in batch_json
    assert '"id": "seg_004"' not in batch_json
    assert enriched == [
        {
            "representative_keyword": "Payment Terms",
            "provision_type": "payment",
            "related_keywords": ["monthly service fee", "invoice"],
            "metadata": {"id": "seg_005", "page": 1, "source": "contract.txt", "segment_id": "seg_005"},
            "context_text": "monthly service fee of USD 2,000",
            "exact_text": "The Client shall pay the Service Provider a monthly service fee of USD 2,000.",
                "evidences": [
                    {
                        "context_text": "monthly service fee of USD 2,000",
                        "exact_text": "The Client shall pay the Service Provider a monthly service fee of USD 2,000.",
                        "page": 1,
                    "id": "seg_005",
                    "segment_id": "seg_005",
                    "source": "contract.txt",
                    "validation_status": "passed",
                    "confidence": 0.95,
                }
            ],
        }
    ]


def test_extract_evidence_marks_missing_response_group_not_found():
    model = FakeChatModel({"keyword_groups": []})
    keyword_groups = [
        {
            "representative_keyword": "Assignment",
            "provision_type": "assignment",
            "related_keywords": ["assignment"],
            "metadata": {"id": "seg_001", "page": 2, "source": "contract.txt"},
        }
    ]
    segments = [
        DocumentSegment(
            segment_id="seg_001",
            page=2,
            source="contract.txt",
            text="No relevant assignment language appears here.",
        )
    ]

    enriched, _ = extract_evidence(keyword_groups, segments, model)

    assert enriched[0]["evidences"] == [
        {
            "context_text": "",
            "exact_text": "",
            "page": 2,
            "id": "seg_001",
            "segment_id": "seg_001",
            "source": "contract.txt",
            "validation_status": "not_found",
            "confidence": 0.0,
        }
    ]


def test_extract_evidence_parallel_batches_preserve_order():
    model = PromptAwareFakeChatModel()
    keyword_groups = [
        {
            "representative_keyword": "First Keyword",
            "related_keywords": ["First Keyword"],
            "metadata": {"id": "seg_001", "page": 1, "source": "contract.txt"},
        },
        {
            "representative_keyword": "Second Keyword",
            "related_keywords": ["Second Keyword"],
            "metadata": {"id": "seg_002", "page": 1, "source": "contract.txt"},
        },
    ]
    segments = [
        DocumentSegment(segment_id="seg_001", page=1, source="contract.txt", text="First Keyword"),
        DocumentSegment(segment_id="seg_002", page=1, source="contract.txt", text="Second Keyword"),
    ]

    enriched, batch_count = extract_evidence(
        keyword_groups,
        segments,
        model,
        batch_size=1,
        max_parallel_calls=2,
    )

    assert batch_count == 2
    assert [group["representative_keyword"] for group in enriched] == [
        "First Keyword",
        "Second Keyword",
    ]


def test_local_evidence_handles_speed_optimization_patterns():
    segments = [
        DocumentSegment(
            segment_id="seg_001",
            page=1,
            source="contract.txt",
            text="Unless otherwise approved by Company, payment terms are Net 30 days on licensed Technology.",
        ),
        DocumentSegment(
            segment_id="seg_002",
            page=2,
            source="contract.txt",
            text=(
                "A LATE PAYMENT CHARGE of one and one-half percent of the outstanding "
                "balance per month will be imposed on all overdue accounts."
            ),
        ),
        DocumentSegment(
            segment_id="seg_003",
            page=3,
            source="contract.txt",
            text=(
                "Schedule A Technology Pricing and Terms Matrix lists purchase levels: "
                "III $1,000,001 and above with 25% discount."
            ),
        ),
        DocumentSegment(
            segment_id="seg_004",
            page=4,
            source="contract.txt",
            text="The Client shall review each deliverable within five (5) business days after receipt.",
        ),
    ]
    groups = [
        {"representative_keyword": "Net 30 Payment Terms", "metadata": {"id": "seg_001"}},
        {"representative_keyword": "Late Payment Charge", "metadata": {"id": "seg_002"}},
        {"representative_keyword": "Schedule Pricing Tiers", "metadata": {"id": "seg_003"}},
        {
            "representative_keyword": "Acceptance Criteria",
            "related_keywords": ["Review Period"],
            "metadata": {"id": "seg_004"},
        },
    ]

    enriched, unresolved = apply_local_evidence(groups, segments)

    assert unresolved == []
    exact_texts = [group["exact_text"] for group in enriched]
    assert "Net 30 days" in exact_texts[0]
    assert "one and one-half percent" in exact_texts[1]
    assert "25% discount" in exact_texts[2]
    assert "five (5) business days" in exact_texts[3]
