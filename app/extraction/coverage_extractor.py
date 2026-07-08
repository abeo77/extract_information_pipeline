"""Deterministic generic coverage pass for common contract provisions."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.extraction.schemas import DocumentSegment


@dataclass(frozen=True)
class CoverageRule:
    representative_keyword: str
    provision_type: str
    related_keywords: tuple[str, ...]
    patterns: tuple[str, ...]
    duplicate_keywords: tuple[str, ...] = ()


def apply_coverage_pass(
    keyword_groups: list[dict[str, Any]],
    segments: list[DocumentSegment],
    max_groups: int = 12,
    mode: str = "adaptive",
) -> tuple[list[dict[str, Any]], int, int]:
    """Add high-confidence generic provision groups missed by LLM1."""
    mode = (mode or "adaptive").lower()
    if mode == "off" or max_groups <= 0 or not segments:
        return keyword_groups, 0, 0

    effective_max_groups = max_groups if mode == "broad" else _adaptive_max_groups(
        keyword_groups,
        segments,
        max_groups,
    )
    existing = _existing_keywords(keyword_groups)
    candidates = _coverage_candidates(existing, segments, mode)
    added: list[dict[str, Any]] = []
    for rule, segment in candidates:
        if len(added) >= effective_max_groups:
            break
        if _already_present(rule, existing):
            continue
        group = _group_from_rule(rule, segment)
        added.append(group)
        existing.update(_keyword_set(group))

    return [*keyword_groups, *added], len(added), len(candidates)


def _adaptive_max_groups(
    keyword_groups: list[dict[str, Any]],
    segments: list[DocumentSegment],
    configured_max: int,
) -> int:
    segment_count = len(segments)
    predicted_count = len(keyword_groups)
    if segment_count <= 18 and predicted_count >= 12:
        return min(configured_max, 2)
    if segment_count <= 35 and predicted_count >= 18:
        return min(configured_max, 3)
    if predicted_count < max(8, segment_count // 3):
        return min(configured_max, 8)
    return min(configured_max, 5)


def _coverage_candidates(
    existing: set[str],
    segments: list[DocumentSegment],
    mode: str,
) -> list[tuple[CoverageRule, DocumentSegment]]:
    candidates: list[tuple[int, int, CoverageRule, DocumentSegment]] = []
    for rule_index, rule in enumerate(COVERAGE_RULES):
        if _already_present(rule, existing):
            continue
        segment, score = _best_segment(rule, segments, broad=mode == "broad")
        if segment is None:
            continue
        tier_bonus = 1000 if _rule_tier(rule) == "high_precision" else 0
        candidates.append((tier_bonus + score, -rule_index, rule, segment))
    candidates.sort(reverse=True)
    return [(rule, segment) for _, _, rule, segment in candidates]


def _existing_keywords(groups: list[dict[str, Any]]) -> set[str]:
    values: set[str] = set()
    for group in groups:
        values.update(_keyword_set(group))
    return values


def _keyword_set(group: dict[str, Any]) -> set[str]:
    related = group.get("related_keywords") if isinstance(group.get("related_keywords"), list) else []
    values = [group.get("representative_keyword"), *related]
    return {_normalize_keyword(value) for value in values if str(value or "").strip()}


def _already_present(rule: CoverageRule, existing: set[str]) -> bool:
    values = [rule.representative_keyword, *rule.duplicate_keywords]
    if not rule.duplicate_keywords:
        values.extend(rule.related_keywords)
    return any(_normalize_keyword(value) in existing for value in values)


def _best_segment(
    rule: CoverageRule,
    segments: list[DocumentSegment],
    broad: bool = False,
) -> tuple[DocumentSegment, int] | tuple[None, int]:
    best: tuple[int, int, DocumentSegment] | None = None
    compiled = [re.compile(pattern, flags=re.IGNORECASE | re.DOTALL) for pattern in rule.patterns]
    for index, segment in enumerate(segments):
        text = _segment_search_text(segment)
        if not text:
            continue
        score = _match_score(compiled, segment, text, rule)
        threshold = 1 if broad else _score_threshold(rule, segment)
        if score < threshold:
            continue
        current = (score, -index, segment)
        if best is None or current > best:
            best = current
    return (best[2], best[0]) if best else (None, 0)


def _segment_search_text(segment: DocumentSegment) -> str:
    parts = [
        segment.title,
        segment.metadata.get("parent_section_title") if isinstance(segment.metadata, dict) else None,
        segment.text,
    ]
    return "\n".join(str(part) for part in parts if part)


def _match_score(
    patterns: list[re.Pattern],
    segment: DocumentSegment,
    text: str,
    rule: CoverageRule,
) -> int:
    score = 0
    matched = False
    title_text = " ".join(
        str(part or "")
        for part in [
            segment.title,
            segment.metadata.get("parent_section_title") if isinstance(segment.metadata, dict) else None,
        ]
    )
    for pattern in patterns:
        if pattern.search(text):
            matched = True
            score += 10
        if title_text and pattern.search(title_text):
            matched = True
            score += 25
    if matched and _looks_like_schedule(segment):
        score += 5
    if matched and _is_risky_business_rule(rule) and _weak_context_kind(segment) in {"opening", "recitals", "signature"}:
        score -= 30
    return score


def _score_threshold(rule: CoverageRule, segment: DocumentSegment) -> int:
    threshold = 25 if _rule_tier(rule) == "targeted_recall" else 10
    if _is_risky_business_rule(rule) and _weak_context_kind(segment) in {"opening", "recitals", "signature"}:
        threshold += 30
    return threshold


def _rule_tier(rule: CoverageRule) -> str:
    if _normalize_keyword(rule.representative_keyword) in HIGH_PRECISION_KEYS:
        return "high_precision"
    return "targeted_recall"


def _is_risky_business_rule(rule: CoverageRule) -> bool:
    return _normalize_keyword(rule.representative_keyword) in RISKY_BUSINESS_KEYS


def _weak_context_kind(segment: DocumentSegment) -> str:
    text = _segment_search_text(segment).strip()
    normalized = _normalize_keyword(text[:350])
    if "signature" in normalized or normalized.startswith("accepted and agreed") or "print name" in normalized:
        return "signature"
    if "recitals" in normalized or normalized.startswith("whereas"):
        return "recitals"
    if (
        segment.title is None
        and len(text.split()) < 220
        and any(value in normalized for value in ("agreement", "exhibit", "by and between", "entered into"))
    ):
        return "opening"
    return "body"


def _looks_like_schedule(segment: DocumentSegment) -> bool:
    text = _segment_search_text(segment)
    return bool(re.search(r"\b(schedule|exhibit|appendix|annex)\b", text, flags=re.IGNORECASE))


def _group_from_rule(rule: CoverageRule, segment: DocumentSegment) -> dict[str, Any]:
    metadata = dict(segment.metadata) if isinstance(segment.metadata, dict) else {}
    metadata.setdefault("page", segment.page)
    metadata.setdefault("source", segment.source)
    metadata.setdefault("id", segment.segment_id)
    metadata.setdefault("segment_id", segment.segment_id)
    metadata["coverage_source"] = "deterministic"
    return {
        "representative_keyword": rule.representative_keyword,
        "provision_type": rule.provision_type,
        "related_keywords": list(rule.related_keywords),
        "context_text": segment.text.strip(),
        "metadata": {key: value for key, value in metadata.items() if value is not None},
    }


def _normalize_keyword(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").casefold()).strip()


HIGH_PRECISION_KEYS = {
    "parties",
    "agreement date",
    "payment terms",
    "late payment",
    "taxes",
    "notices",
    "assignment",
    "amendment",
    "indemnification",
    "force majeure",
    "audit rights",
    "entire agreement and amendments",
    "deemed acceptance",
}

RISKY_BUSINESS_KEYS = {
    "net 30 payment terms",
    "data security and access control",
    "acceptance criteria",
    "grant of rights",
    "use restrictions",
    "technology description",
    "technology support and upgrades",
    "sales reports",
    "sales records",
    "marketing plan and annual quota",
    "initial order commitment",
    "territory",
    "schedule pricing tiers",
}


COVERAGE_RULES = (
    CoverageRule(
        "Parties",
        "parties",
        ("Contracting Parties", "Company", "Client", "Customer", "Service Provider", "Affiliate"),
        (
            r"\bby\s+and\s+between\b",
            r"\bmade\s+between\b",
            r"\bentered\s+into\b.{0,160}\bbetween\b",
            r"\bbetween\s*:\b",
        ),
        duplicate_keywords=("Parties", "Contracting Parties"),
    ),
    CoverageRule(
        "Agreement Date",
        "effective_date",
        ("Dated", "Execution Date", "Agreement Date"),
        (
            r"\bdated\s*:\s*",
            r"\bentered\s+into\s+this\b",
            r"\bdate\s+of\s+(?:its\s+)?execution\b",
        ),
    ),
    CoverageRule(
        "Contract Term",
        "term",
        ("Term", "Effective Date and Term", "Expiration Date"),
        (
            r"\bshall\s+begin\b.{0,240}\bremain\s+in\s+effect\b",
            r"\bterm\s+of\s+this\s+agreement\b",
            r"\bexpiration\s+date\b",
        ),
    ),
    CoverageRule(
        "Renewal Clause",
        "renewal",
        ("Renewal", "Automatic Renewal", "Renewal Term"),
        (r"\bautomatic(?:ally)?\s+renew", r"\brenewal\s+term\b", r"\bnon[- ]renewal\b"),
    ),
    CoverageRule(
        "Payment Terms",
        "payment",
        ("Fees", "Invoice", "Amounts Due", "Payment Due Date"),
        (r"\bpayment\s+terms\b", r"\bpay(?:ment)?\b.{0,120}\binvoice\b", r"\bamounts?\s+due\b"),
        duplicate_keywords=("Payment Terms", "Fees", "Amounts Due"),
    ),
    CoverageRule(
        "Net 30 Payment Terms",
        "payment",
        ("Net 30", "Schedule A Terms"),
        (r"\bnet\s*30\b", r"\bthirty\s*\(30\)\s*days\b.{0,80}\bpayment\b"),
        duplicate_keywords=("Net 30 Payment Terms", "Net 30"),
    ),
    CoverageRule(
        "Late Payment",
        "payment",
        ("Late Payment Charge", "Overdue Accounts", "Service Suspension"),
        (r"\blate\s+payment\b", r"\boverdue\s+accounts?\b", r"\bunpaid\b.{0,120}\bsuspension\b"),
        duplicate_keywords=("Late Payment", "Late Payment Charge", "Overdue Accounts"),
    ),
    CoverageRule(
        "Taxes",
        "payment",
        ("Excise Tax", "Sales Tax", "Tax Responsibility"),
        (r"\btaxes\b", r"\bexcise\b.{0,80}\bsales\b.{0,80}\btaxes\b"),
        duplicate_keywords=("Taxes", "Tax Responsibility"),
    ),
    CoverageRule(
        "Acceptance Criteria",
        "delivery",
        ("Acceptance", "Review Period", "Deliverable Acceptance"),
        (
            r"\bacceptance\s+criteria\b",
            r"\breview\s+period\b",
            r"\breject\b.{0,120}\bdefects?\b",
            r"\bdeliverable\b.{0,160}\baccept(?:ance|ed)\b",
        ),
        duplicate_keywords=("Acceptance Criteria", "Review Period", "Deliverable Acceptance"),
    ),
    CoverageRule(
        "Data Security and Access Control",
        "compliance",
        ("Data Security", "Access Control", "Safeguards", "Security Incident Reporting"),
        (
            r"\bdata\s+security\b",
            r"\bsafeguards?\b.{0,120}\bdata\b",
            r"\baccess\b.{0,120}\bauthorized\s+personnel\b",
            r"\bsecurity\s+incidents?\b",
        ),
        duplicate_keywords=("Data Security and Access Control", "Data Security", "Access Control"),
    ),
    CoverageRule(
        "Grant of Rights",
        "intellectual_property",
        ("License Grant", "Distribution Rights", "Right to Market", "Right to Sell"),
        (
            r"\bgrants?\b.{0,160}\bright\s+to\b",
            r"\bright\s+to\s+(?:advertise|market|sell|distribute)\b",
            r"\blicense\s+grant\b",
        ),
        duplicate_keywords=("Grant of Rights", "License Grant", "Distribution Rights"),
    ),
    CoverageRule(
        "Use Restrictions",
        "intellectual_property",
        ("Unauthorized Use", "Internal Use", "Redistribution Restriction", "Data Center Restriction"),
        (
            r"\binternal\s+use\b",
            r"\bnot\s+for\s+(?:remarketing|redistribution)\b",
            r"\bunauthorized\s+use\b",
            r"\bdata\s+center\s+environment\b",
        ),
        duplicate_keywords=("Use Restrictions", "Unauthorized Use", "Redistribution Restriction"),
    ),
    CoverageRule(
        "Technology Description",
        "schedules_exhibits",
        ("Technology", "Products", "Platform", "Content"),
        (
            r"\bproducts?\s+approved\s+for\s+sale\b",
            r"\btechnology\b.{0,120}\b(?:platform|content|products?)\b",
            r"\btechnology\s+description\b",
        ),
        duplicate_keywords=("Technology Description", "Technology"),
    ),
    CoverageRule(
        "Technology Support and Upgrades",
        "services",
        ("Support", "Upgrades", "Maintenance", "Technical Support"),
        (
            r"\btechnology\s+maintenance\b",
            r"\bsupport\b.{0,120}\bupgrades?\b",
            r"\btechnical\s+support\b",
        ),
        duplicate_keywords=("Technology Support and Upgrades", "Support and Upgrades"),
    ),
    CoverageRule(
        "Sales Reports",
        "obligations",
        ("Marketing Reports", "Forecasts", "Sales Forecasts"),
        (
            r"\bsales\s+reports?\b",
            r"\breport\s+periodically\b",
            r"\bsales\s+forecasts?\b",
        ),
        duplicate_keywords=("Sales Reports", "Sales Forecasts"),
    ),
    CoverageRule(
        "Sales Records",
        "obligations",
        ("Records", "Books", "Audit Records"),
        (r"\bsales\s+records?\b", r"\bbooks\s+and\s+records\b", r"\bmaintain\s+records?\b"),
        duplicate_keywords=("Sales Records", "Audit Records"),
    ),
    CoverageRule(
        "Marketing Plan and Annual Quota",
        "obligations",
        ("Marketing Plan", "Annual Quota", "Sales Quota"),
        (r"\bannual\s+marketing\s+plan\b", r"\bannual\s+sales\s+quotas?\b", r"\bannual\s+quota\b"),
        duplicate_keywords=("Marketing Plan and Annual Quota", "Annual Quota", "Sales Quota"),
    ),
    CoverageRule(
        "Initial Order Commitment",
        "payment",
        ("Minimum Units", "First Six Months", "Purchase Commitment"),
        (r"\binitial\s+order\s+commitment\b", r"\bminimum\s+of\s+\d+\s+units?\b", r"\bfirst\s+six\s+months\b"),
        duplicate_keywords=("Initial Order Commitment", "Minimum Units"),
    ),
    CoverageRule(
        "Territory",
        "schedules_exhibits",
        ("Authorized Territory", "Resale Territory", "Schedule Territory"),
        (r"\bauthorized\s+territory\b", r"\bterritory\b.{0,120}\bschedule\b", r"\bterritory\s*:\s*"),
        duplicate_keywords=("Territory", "Authorized Territory", "Resale Territory"),
    ),
    CoverageRule(
        "Schedule Pricing Tiers",
        "schedules_exhibits",
        ("Pricing Tiers", "Purchase Level", "Purchase Discount", "Discount Matrix"),
        (
            r"\bpricing\s+(?:tiers|matrix)\b",
            r"\bpurchase\s+levels?\b",
            r"\bpurchase\s+discount\b",
            r"\b\d{1,3}\s*%\s+discount\b",
        ),
        duplicate_keywords=("Schedule Pricing Tiers", "Pricing Tiers", "Purchase Discount"),
    ),
    CoverageRule(
        "Copyrights and Trademarks Protection",
        "intellectual_property",
        ("Copyrights", "Trademarks", "Service Marks", "Proprietary Rights"),
        (
            r"\bcopyrights?\b.{0,160}\btrademarks?\b",
            r"\bservice\s+marks\b",
            r"\bproprietary\s+rights\b",
        ),
        duplicate_keywords=("Copyrights and Trademarks Protection", "Copyrights", "Trademarks"),
    ),
    CoverageRule(
        "Trade Secrets and Source Code",
        "intellectual_property",
        ("Trade Secrets", "Source Code", "Confidential Technology"),
        (r"\btrade\s+secrets?\b", r"\bsource\s+code\b", r"\bconfidential\s+technology\b"),
        duplicate_keywords=("Trade Secrets and Source Code", "Trade Secrets", "Source Code"),
    ),
    CoverageRule(
        "Confidential Information Definition",
        "confidentiality",
        ("Confidential Information", "Personal Data", "Agreement Terms"),
        (
            r"\bconfidential\s+information\b.{0,80}\bincludes\b",
            r"\bpersonally\s+identifiable\b",
            r"\bagreement\s+terms\b.{0,80}\bconfidential\b",
        ),
        duplicate_keywords=("Confidential Information Definition",),
    ),
    CoverageRule(
        "Warranty Disclaimer",
        "warranties",
        ("Disclaimer of Warranties", "No Warranty", "No Guarantee"),
        (
            r"\bdisclaims?\b.{0,120}\bwarrant(?:y|ies)\b",
            r"\bno\s+warranty\b",
            r"\bwarranty\s+disclaimer\b",
        ),
        duplicate_keywords=("Warranty Disclaimer", "Disclaimer of Warranties", "No Warranty"),
    ),
    CoverageRule(
        "Liability",
        "liability",
        ("Limitation of Liability", "Liability Cap", "Consequential Damages"),
        (
            r"\blimitation\s+of\s+liability\b",
            r"\bshall\s+not\s+be\s+liable\b",
            r"\bconsequential\s+damages\b",
            r"\bliability\s+cap\b",
        ),
        duplicate_keywords=("Liability", "Limitation of Liability", "Liability Cap"),
    ),
    CoverageRule(
        "Indemnification",
        "indemnity",
        ("Indemnity", "Defend", "Hold Harmless"),
        (r"\bindemnif", r"\bhold\s+harmless\b", r"\bdefend\b.{0,120}\bclaim\b"),
        duplicate_keywords=("Indemnification", "Indemnity"),
    ),
    CoverageRule(
        "Force Majeure",
        "force_majeure",
        ("Excusable Delay", "Beyond Reasonable Control", "Act of God"),
        (
            r"\bforce\s+majeure\b",
            r"\bbeyond\s+(?:its|their|reasonable)\s+control\b",
            r"\bacts?\s+of\s+god\b",
            r"\bexcusable\s+delay\b",
        ),
        duplicate_keywords=("Force Majeure", "Excusable Delay"),
    ),
    CoverageRule(
        "Audit Rights",
        "obligations",
        ("Audit", "Inspection Rights", "Records Inspection"),
        (
            r"\baudit\s+rights?\b",
            r"\bmay\s+audit\b",
            r"\bright\s+to\s+(?:audit|inspect)\b",
            r"\bsite\s+inspect\b",
        ),
        duplicate_keywords=("Audit Rights", "Audit"),
    ),
    CoverageRule(
        "Deemed Acceptance",
        "delivery",
        ("Deemed Accepted", "Acceptance Review Period", "No Rejection"),
        (
            r"\bdeemed\s+accept(?:ed|ance)\b",
            r"\baccepted\b.{0,160}\bdoes\s+not\s+reject\b",
            r"\bno\s+(?:specific\s+)?defect\s+rejection\b",
        ),
        duplicate_keywords=("Deemed Acceptance", "Deemed Accepted", "Acceptance Review Period"),
    ),
    CoverageRule(
        "Governing Law and Dispute Resolution",
        "dispute_resolution",
        ("Governing Law", "Jurisdiction", "Dispute Resolution", "Court"),
        (
            r"\bgoverned\s+by\b.{0,240}\b(?:jurisdiction|court|dispute|arbitration|negotiation)\b",
            r"\bjurisdiction\b.{0,160}\bgoverned\s+by\b",
            r"\bdispute\s+resolution\b",
        ),
        duplicate_keywords=("Governing Law and Dispute Resolution", "Governing Law", "Jurisdiction"),
    ),
    CoverageRule(
        "Notices",
        "notices",
        ("Notice Delivery", "Email", "Registered Mail", "Deemed Receipt"),
        (r"\bnotices?\s+(?:must|shall|under)\b", r"\bregistered\s+mail\b", r"\bdeemed\s+received\b"),
        duplicate_keywords=("Notices", "Notice Delivery", "Deemed Receipt"),
    ),
    CoverageRule(
        "Assignment",
        "assignment",
        ("Assign", "Transfer", "Assignment Restriction"),
        (r"\bassignment\b", r"\bmay\s+not\s+assign\b", r"\bassign\s+or\s+transfer\b"),
        duplicate_keywords=("Assignment", "Assignment Restriction"),
    ),
    CoverageRule(
        "Amendment",
        "amendment",
        ("Modification", "Written Amendment", "Changes"),
        (r"\bamend(?:ment|ed)?\b", r"\bmodify\b", r"\bchanges?\b.{0,80}\bin\s+writing\b"),
        duplicate_keywords=("Amendment", "Modification", "Written Amendment"),
    ),
    CoverageRule(
        "Entire Agreement and Amendments",
        "amendment",
        ("Entire Agreement", "Prior Understandings", "Written Amendment", "Supersedes"),
        (
            r"\bentire\s+(?:agreement|understanding)\b",
            r"\bsupersedes\b.{0,160}\bprior\b",
            r"\bmodification\s+or\s+amendment\b.{0,120}\bin\s+writing\b",
        ),
        duplicate_keywords=("Entire Agreement and Amendments", "Entire Agreement", "Prior Understandings"),
    ),
    CoverageRule(
        "Electronic Signatures",
        "signatures",
        ("Electronic Signature", "Signature Blocks", "Authorized Representatives"),
        (
            r"\belectronic\s+signature",
            r"\bsign(?:ed|atures?)\s+electronically\b",
            r"\bauthorized\s+representatives?\b.{0,120}\bsign\b",
        ),
        duplicate_keywords=("Electronic Signatures", "Electronic Signature", "Signature Blocks"),
    ),
    CoverageRule(
        "Post-Termination Obligations",
        "termination",
        ("Return of Materials", "Cessation of Marketing", "Post-Termination Non-Use"),
        (
            r"\bfollowing\s+the\s+termination\b",
            r"\bpost[- ]termination\b",
            r"\breturn\b.{0,120}\bmaterials?\b",
            r"\bcease\b.{0,120}\b(?:marketing|using|selling|support)\b",
        ),
        duplicate_keywords=("Post-Termination Obligations", "Return of Materials", "Post-Termination Non-Use"),
    ),
    CoverageRule(
        "Permits and Legal Compliance",
        "compliance",
        ("Compliance", "Permits", "Legal Requirements", "Business Practices"),
        (
            r"\bcomply\b.{0,120}\b(?:laws?|regulations?|ordinances?)\b",
            r"\bpermits?\b.{0,120}\blegal\b",
            r"\bbusiness\s+practices\b",
        ),
        duplicate_keywords=("Permits and Legal Compliance", "Compliance", "Business Practices"),
    ),
)
