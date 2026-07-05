from pathlib import Path

from app.services.result_service import compact_result, load_json, save_json


def generate_ground_truth_from_result(
    result_path: str | Path,
    ground_truth_path: str | Path | None = None,
) -> dict:
    result = compact_result(load_json(result_path))
    keyword_groups = [_normalize_keyword_group(group) for group in result.get("keyword_groups", [])]
    ground_truth = {
        "document_name": result.get("document_name"),
        "source_result_path": str(result_path),
        "total_keyword_groups": len(keyword_groups),
        "keyword_groups": keyword_groups,
    }

    if ground_truth_path is not None:
        save_json(ground_truth, ground_truth_path)
    return ground_truth


def compare_keywords(result_path: str | Path, ground_truth_path: str | Path) -> dict:
    result = load_json(result_path)
    truth = load_json(ground_truth_path)
    found = {g["representative_keyword"].lower() for g in result.get("keyword_groups", [])}
    expected = {g["representative_keyword"].lower() for g in truth.get("keyword_groups", [])}
    return {
        "expected": len(expected),
        "found": len(found),
        "matched": len(found & expected),
        "missing": sorted(expected - found),
        "extra": sorted(found - expected),
    }


def _normalize_keyword_group(group: dict) -> dict:
    normalized = {
        "representative_keyword": group.get("representative_keyword"),
        "related_keywords": group.get("related_keywords", []),
        "context_text": group.get("context_text"),
        "exact_text": group.get("exact_text"),
        "provision_type": group.get("provision_type"),
        "metadata": group.get("metadata", {}),
    }
    return {key: value for key, value in normalized.items() if value not in (None, "", [], {})}

