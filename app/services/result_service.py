"""Result persistence and evidence merge helpers."""

import json
from pathlib import Path
from typing import Any


def save_json(data: Any, output_path: str | Path) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def load_json(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def compact_result(data: dict) -> dict:
    """Return user-facing result JSON without repeated evidence payloads."""
    result = dict(data)
    keyword_groups = [_compact_keyword_group(group) for group in result.get("keyword_groups", [])]
    result["keyword_groups"] = keyword_groups
    result.pop("keyword_items", None)
    result["total_keyword_groups"] = len(keyword_groups)
    return result


def _compact_keyword_group(group: dict) -> dict:
    evidence = _primary_evidence(group)
    compact = {
        "representative_keyword": group.get("representative_keyword"),
        "related_keywords": group.get("related_keywords", []),
        "context_text": group.get("context_text") or evidence.get("context_text"),
        "exact_text": group.get("exact_text") or evidence.get("exact_text"),
        "metadata": _compact_metadata(group.get("metadata", {}), evidence),
    }
    return {key: value for key, value in compact.items() if value not in (None, "", [], {})}


def _primary_evidence(group: dict) -> dict:
    evidences = group.get("evidences")
    if isinstance(evidences, list) and evidences:
        evidence = evidences[0]
        return evidence if isinstance(evidence, dict) else {}
    return {}


def _compact_metadata(metadata: dict, evidence: dict) -> dict:
    metadata = metadata if isinstance(metadata, dict) else {}
    compact = {
        "page": metadata.get("page") or evidence.get("page"),
        "clause_no": metadata.get("clause_no"),
    }
    return {key: value for key, value in compact.items() if value is not None}
