"""Prompt templates for the two extraction LLM stages."""

LLM1_KEYWORD_EXTRACTION_PROMPT = """You are LLM1 in a contract keyword extraction and semantic grouping pipeline.

Task: extract important keywords from contract segments and group only keywords that have the same or nearly the same meaning.

Definition of keyword:
A keyword is a concise word or phrase that represents the main legal, commercial, operational, or contractual meaning of a segment. A keyword should describe what the segment is mainly about.

A keyword is NOT:
- a generic word, such as Agreement, Party, Company, Article, Section, Document, Terms
- a full sentence
- a random noun that appears in the text but does not represent an important contractual concept
- an overly broad category if the segment contains a more specific concept

Input: a batch may include source at batch level. Segments may include segment_id, page, parent_section_title, clause_no, and text.

Keyword extraction rules:
1. Read only the provided text.
2. Prefer specific contract concepts over vague labels.
3. Use noun phrases.
4. Extract multiple keywords from one segment only if the segment contains multiple distinct contractual concepts.
5. The representative_keyword should be the cleanest and most standard name for the concept.
6. related_keywords should contain only synonyms, near-equivalent terms, or alternative wording found in the contract.
7. Do not put legally different concepts into related_keywords.
8. Skip generic words such as "agreement", "section", "article", "document", and "terms" unless they have specific legal meaning in context.
9. Skip segments with no meaningful keyword.
10. Set provision_type to one of: parties, effective_date, term, renewal, termination, payment, services, obligations, delivery, confidentiality, intellectual_property, liability, indemnity, warranties, dispute_resolution, governing_law, notices, assignment, amendment, force_majeure, compliance, schedules_exhibits, signatures, other.
11. In metadata, use "id" for segment_id, source from the batch, plus clause_no and parent_section_title when available.
12. Include context_text for each keyword group.
13. context_text must be copied from the original segment text supplied in this batch.
14. context_text must be full enough for LLM2 to select exact_text later: use the full sentence, clause, or paragraph that directly supports the keyword.
15. Do not summarize, rewrite, truncate, or invent context_text.
16. Extract all material sub-provisions in long clauses, not only the heading. If one paragraph covers payment, late charges, taxes, delivery, and records, create separate groups for those distinct concepts.
17. Always inspect Schedule, Exhibit, Appendix, and Annex segments. Extract concrete business terms such as pricing tiers, discounts, payment terms, territory, quotas, minimum commitments, approved products, support, and restrictions.
18. For list-style clauses, create a group for the list heading and separate groups for legally meaningful list items when they impose distinct obligations or rights.

Good keyword examples:
- Contracting Parties
- Service Provider
- Client
- Effective Date
- Start Date
- Commencement Date
- End Date
- Expiration Date
- Contract Term
- Automatic Renewal
- Termination
- Notice Period
- Scope of Services
- Deliverables
- Service Fee
- Payment Terms
- Invoice
- Late Payment
- Taxes
- Expenses
- Confidentiality
- Non-Disclosure
- Intellectual Property
- Ownership
- License
- Data Protection
- Security Requirements
- Indemnification
- Limitation of Liability
- Warranty
- Disclaimer
- Governing Law
- Dispute Resolution
- Jurisdiction
- Assignment
- Subcontracting
- Force Majeure
- Notices

Grouping rules:
Group only same-meaning concepts.

Examples of correct grouping:
- Effective Date, Start Date, Commencement Date -> representative_keyword: Effective Date
- End Date, Expiration Date -> representative_keyword: End Date
- Confidentiality, Non-Disclosure -> representative_keyword: Confidentiality
- Fees, Service Fee, Monthly Fee -> representative_keyword: Service Fee
- Governing Law, Applicable Law -> representative_keyword: Governing Law
- Notice, Written Notice, Notice Requirement -> representative_keyword: Notices
- Intellectual Property Rights, IP Rights -> representative_keyword: Intellectual Property
- Limitation of Liability, Liability Cap -> representative_keyword: Limitation of Liability

Examples of incorrect grouping:
- Do NOT group Effective Date with End Date.
- Do NOT group Contract Term with Termination.
- Do NOT group Automatic Renewal with End Date.
- Do NOT group Termination with Expiration Date.
- Do NOT group Payment Terms with Taxes unless the segment clearly treats taxes as part of the same payment obligation.
- Do NOT group Service Fee with Late Payment.
- Do NOT group Invoice with Payment Due Date unless they refer to the same payment timing obligation.
- Do NOT group Confidentiality with Data Protection.
- Do NOT group Intellectual Property with Confidentiality.
- Do NOT group Indemnification with Limitation of Liability.
- Do NOT group Governing Law with Dispute Resolution.
- Do NOT group Assignment with Subcontracting unless the text treats them as the same restriction.
- Do NOT group Scope of Services with Deliverables.
- Do NOT create duplicate groups with the same representative_keyword and the same source segment.

Output only valid JSON:
{
  "keyword_groups": [
    {
      "representative_keyword": "Payment Terms",
      "provision_type": "payment",
      "related_keywords": ["fees", "invoice", "Net 30"],
      "context_text": "Customer shall pay all invoices within thirty (30) days after receipt.",
      "metadata": {
        "page": 1,
        "id": "segment id if available",
        "segment_id": "same segment id if available",
        "source": "source file if available",
        "clause_no": "clause number if available",
        "parent_section_title": "parent section title if available"
      }
    }
  ]
}
"""


LLM2_EVIDENCE_EXTRACTION_PROMPT = """You are LLM2 in a contract analysis pipeline.

Task: find exact evidence in the original contract segments for each keyword group provided by LLM1.

Input:
1. keyword_groups from LLM1
2. normalized contract segments with id, page, source, and text

Rules:
1. Use only the provided contract text.
2. Find the most relevant evidence for each representative keyword.
3. Evidence must be directly supported by the segment text.
4. Copy exact_text exactly from the original segment, but select only the shortest complete span that answers the representative_keyword.
5. Do not summarize, rewrite, invent, over-summarize, or make legal conclusions.
6. The evidence must directly support the representative_keyword.
7. If one segment contains several distinct concepts, keep evidence focused on the specific representative_keyword.
8. If no clear evidence exists, use validation_status "not_found".
9. Preserve page, id, segment_id, and source from the source segment.
10. context_text should also be copied from the original segment and may include the full sentence, clause, or paragraph needed for surrounding context.
11. exact_text is the precise answer span, not the surrounding context. For value-style fields such as Effective Date, Commencement Date, Start Date, End Date, Expiration Date, Contract End Date, payment amount, notice period, governing law, or party names, exact_text should normally be the label plus value or just the value if that is the clearest exact answer.
12. When a context contains multiple date labels, choose only the label/value pair matching the representative_keyword or one of its related_keywords. Do not include other date fields. For example, for representative_keyword "End Date", exact_text should be "End Date: December 31, 2026" or "December 31, 2026", not text about Effective Date or Start Date.
13. exact_text must be a contiguous substring copied from the provided segment text.
14. exact_text must not be only a section heading, clause number, or keyword label. Include the shortest contiguous text that answers the keyword.
15. For enumerated lists, exact_text may include the list introduction plus the relevant list items when the items are the answer.
16. For Schedule, Exhibit, Appendix, or Annex terms, include concrete values such as percentages, price levels, territory names, units, quotas, dates, and Net payment terms.

Output only valid JSON:
{
  "keyword_groups": [
    {
      "representative_keyword": "Payment Terms",
      "related_keywords": ["fees", "invoice", "Net 30"],
      "evidences": [
        {
          "context_text": "Customer shall pay all invoices within thirty (30) days after receipt.",
          "exact_text": "Customer shall pay all invoices within thirty (30) days after receipt.",
          "page": 2,
          "id": "seg_012",
          "segment_id": "seg_012",
          "source": "contract.pdf",
          "validation_status": "passed",
          "confidence": 0.95
        }
      ]
    }
  ]
}
"""
