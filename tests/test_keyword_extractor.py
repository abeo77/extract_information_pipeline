"""LLM1 keyword extractor tests."""

import json
import time

from app.extraction.keyword_extractor import extract_keywords
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
        if '"seg_001"' in prompt:
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
                        "related_keywords": [keyword],
                        "metadata": {"id": segment_id},
                    }
                ]
            }
        )


def test_extract_keywords_invokes_llm1_with_compact_payload_and_normalizes_output():
    model = FakeChatModel(
        {
            "keyword_groups": [
                {
                    "representative_keyword": "Payment Terms",
                    "provision_type": "payment",
                    "related_keywords": ["monthly service fee", "invoice"],
                    "text": "monthly service fee of USD 2,000",
                    "reason": "drop this",
                    "metadata": {"id": "seg_001"},
                }
            ]
        }
    )
    segments = [
        DocumentSegment(
            segment_id="seg_001",
            title="4. Payment Terms",
            page=1,
            source="contract.txt",
            text="4. Payment Terms\nThe Client shall pay a monthly service fee of USD 2,000.",
            metadata={"source": "contract.txt", "token_count": 20},
        )
    ]

    keyword_groups, batch_count = extract_keywords(segments, model)

    assert batch_count == 1
    batch_json = model.prompts[0].split("Contract segment batch JSON:\n", 1)[1]
    assert '"source": "contract.txt"' in batch_json
    assert '"title"' not in batch_json
    assert '"metadata"' not in batch_json
    assert keyword_groups == [
        {
            "representative_keyword": "Payment Terms",
            "provision_type": "payment",
            "related_keywords": ["monthly service fee", "invoice"],
            "context_text": "The Client shall pay a monthly service fee of USD 2,000.",
            "metadata": {
                "id": "seg_001",
                "page": 1,
                "segment_id": "seg_001",
                "clause_no": "4",
                "source": "contract.txt",
            },
        }
    ]


def test_extract_keywords_accepts_provision_alias_and_infers_missing_type():
    model = FakeChatModel(
        {
            "keyword_groups": [
                {
                    "representative_keyword": "Notice Requirements",
                    "provision": "notice",
                    "related_keywords": ["registered mail"],
                    "metadata": {"id": "seg_001"},
                },
                {
                    "representative_keyword": "Termination",
                    "related_keywords": ["thirty (30) days' written notice"],
                    "metadata": {"id": "seg_002"},
                },
            ]
        }
    )
    segments = [
        DocumentSegment(
            segment_id="seg_001",
            page=2,
            source="contract.txt",
            text="All notices must be sent by email or registered mail.",
        ),
        DocumentSegment(
            segment_id="seg_002",
            page=3,
            source="contract.txt",
            text="Either party may terminate this Agreement by giving thirty (30) days' written notice.",
        ),
    ]

    keyword_groups, _ = extract_keywords(segments, model)

    assert keyword_groups[0]["provision_type"] == "notices"
    assert keyword_groups[1]["provision_type"] == "termination"


def test_extract_keywords_parallel_batches_preserve_order():
    model = PromptAwareFakeChatModel()
    segments = [
        DocumentSegment(segment_id="seg_001", page=1, source="contract.txt", text="First."),
        DocumentSegment(segment_id="seg_002", page=1, source="contract.txt", text="Second."),
    ]

    keyword_groups, batch_count = extract_keywords(
        segments,
        model,
        batch_size=1,
        max_parallel_calls=2,
    )

    assert batch_count == 2
    assert [group["representative_keyword"] for group in keyword_groups] == [
        "First Keyword",
        "Second Keyword",
    ]
