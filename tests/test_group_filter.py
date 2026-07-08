"""Low-confidence group filtering tests."""

from app.extraction.group_filter import filter_keyword_groups


def test_filter_drops_unsupported_risky_false_positives():
    groups = [
        {
            "representative_keyword": "Net 30 Payment Terms",
            "provision_type": "payment",
            "context_text": "The Client shall pay invoices within thirty days.",
            "metadata": {"coverage_source": "deterministic"},
        },
        {
            "representative_keyword": "Technology Support and Upgrades",
            "provision_type": "services",
            "context_text": "Exhibit 10.16 Marketing Affiliate Agreement made between Alpha and Beta.",
            "metadata": {"coverage_source": "deterministic"},
        },
        {
            "representative_keyword": "Data Security and Access Control",
            "provision_type": "compliance",
            "context_text": "RECITALS This Agreement is entered into by and between the parties.",
            "metadata": {"coverage_source": "deterministic"},
        },
        {
            "representative_keyword": "Acceptance Criteria",
            "provision_type": "delivery",
            "context_text": "Accepted and Agreed: Signature: /s/ Alpha",
            "metadata": {"coverage_source": "deterministic"},
        },
    ]

    kept, filtered = filter_keyword_groups(groups)

    assert kept == []
    assert filtered == 4


def test_filter_keeps_valid_targeted_legal_clauses():
    groups = [
        {
            "representative_keyword": "Indemnification",
            "provision_type": "indemnity",
            "context_text": "Supplier shall indemnify and hold harmless Customer from third-party claims.",
        },
        {
            "representative_keyword": "Assignment",
            "provision_type": "assignment",
            "context_text": "Neither party may assign this Agreement without prior written consent.",
        },
        {
            "representative_keyword": "Force Majeure",
            "provision_type": "force_majeure",
            "context_text": "Neither party is liable for delays caused by events beyond its reasonable control.",
        },
        {
            "representative_keyword": "Notices",
            "provision_type": "notices",
            "context_text": "All notices must be sent by email or registered mail.",
        },
        {
            "representative_keyword": "Entire Agreement and Amendments",
            "provision_type": "amendment",
            "context_text": "This Agreement is the entire agreement and amendments must be in writing.",
        },
    ]

    kept, filtered = filter_keyword_groups(groups)

    assert filtered == 0
    assert [group["representative_keyword"] for group in kept] == [
        "Indemnification",
        "Assignment",
        "Force Majeure",
        "Notices",
        "Entire Agreement and Amendments",
    ]
