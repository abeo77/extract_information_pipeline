"""Ground-truth evaluation for contract keyword extraction results."""

from __future__ import annotations

import argparse
import json
import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from app.services.result_service import compact_result, load_json, save_json


WEIGHTS = {
    "keyword_match_score": 0.25,
    "grouping_match_score": 0.20,
    "context_match_score": 0.25,
    "exact_information_match_score": 0.25,
    "page_match_score": 0.05,
}


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
    """Evaluate result JSON against ground truth using weighted item scores."""
    result = compact_result(load_json(result_path))
    truth = load_json(ground_truth_path)
    predicted_items = _result_items(result)
    truth_items = _truth_items(truth)
    matches = _match_items(predicted_items, truth_items)

    matched_truth_indexes = {match["truth_index"] for match in matches}
    matched_predicted_indexes = {match["predicted_index"] for match in matches}
    missing_items = [
        _missing_item(item)
        for index, item in enumerate(truth_items)
        if index not in matched_truth_indexes
    ]
    extra_items = [
        _extra_item(item)
        for index, item in enumerate(predicted_items)
        if index not in matched_predicted_indexes
    ]
    matched_items = [_score_match(match["predicted"], match["truth"]) for match in matches]

    overall_accuracy = _ratio(
        sum(item["overall_score"] for item in matched_items),
        len(truth_items),
    )
    precision = _ratio(len(matched_items), len(predicted_items))
    recall = _ratio(len(matched_items), len(truth_items))
    f1 = _ratio(2 * precision * recall, precision + recall)
    context_match_rate = _ratio(
        sum(item["scores"]["context_match_score"] for item in matched_items),
        len(matched_items),
    )

    return {
        "document_name": result.get("document_name") or _truth_document_name(truth),
        "processing_time_seconds": result.get("processing_time_seconds"),
        "overall_accuracy": round(overall_accuracy, 4),
        "overall_accuracy_percent": round(overall_accuracy * 100, 2),
        "matched_items": matched_items,
        "missing_items": missing_items,
        "extra_items": extra_items,
        "weights": WEIGHTS,
        "summary": {
            "expected_items": len(truth_items),
            "predicted_items": len(predicted_items),
            "matched_items": len(matched_items),
            "missing_items": len(missing_items),
            "extra_items": len(extra_items),
        },
        # Backward-compatible fields used by existing UI/tests.
        "total_pages": result.get("total_pages"),
        "total_segments": result.get("total_segments"),
        "total_keyword_groups": result.get("total_keyword_groups", len(predicted_items)),
        "expected": len(truth_items),
        "found": len(predicted_items),
        "matched": len(matched_items),
        "missing": sorted(item["normalized_key"] for item in missing_items),
        "extra": sorted(item["normalized_key"] for item in extra_items),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "accuracy_percent": round(overall_accuracy * 100, 2),
        "text_match_rate": round(context_match_rate, 4),
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


def _truth_document_name(truth: dict) -> str | None:
    document = truth.get("document")
    if isinstance(document, dict):
        return document.get("document_name")
    return truth.get("document_name")


def _result_items(result: dict) -> list[dict[str, Any]]:
    return [_item_record(group, source="predicted") for group in result.get("keyword_groups", [])]


def _truth_items(truth: dict) -> list[dict[str, Any]]:
    if isinstance(truth.get("items"), list):
        return [_item_record(item, source="truth") for item in truth.get("items", [])]
    if isinstance(truth.get("keyword_groups"), list):
        return [_item_record(group, source="truth") for group in truth.get("keyword_groups", [])]

    document = truth.get("document")
    provisions = document.get("provisions", []) if isinstance(document, dict) else []
    items = []
    for provision in provisions:
        if not isinstance(provision, dict):
            continue
        specific_keywords = provision.get("specific_keywords", [])
        representative = (
            provision.get("representative_keyword")
            or (specific_keywords[0] if isinstance(specific_keywords, list) and specific_keywords else None)
            or provision.get("provision")
        )
        items.append(
            _item_record(
                {
                    "representative_keyword": representative,
                    "grouped_keywords": specific_keywords,
                    "context_text": provision.get("text"),
                    "exact_extracted_information": provision.get("exact_extracted_information"),
                    "metadata": provision.get("metadata", {}),
                    "page": provision.get("page"),
                },
                source="truth",
            )
        )
    return items


def _item_record(group: dict[str, Any], source: str) -> dict[str, Any]:
    representative = str(group.get("representative_keyword") or "").strip()
    grouped_keywords = _grouped_keywords(group)
    context_text = str(group.get("context_text") or "").strip()
    exact_text = str(
        group.get("exact_extracted_information")
        or group.get("exact_information")
        or group.get("exact_text")
        or ""
    ).strip()
    metadata = group.get("metadata") if isinstance(group.get("metadata"), dict) else {}
    page = group.get("page") or metadata.get("page")
    source_value = group.get("source") or metadata.get("source")
    aliases = {_normalize_key(value) for value in [representative, *grouped_keywords] if str(value).strip()}
    return {
        "id": group.get("id"),
        "source_kind": source,
        "representative_keyword": representative,
        "grouped_keywords": grouped_keywords,
        "aliases": aliases,
        "normalized_key": _normalize_key(representative),
        "context_text": context_text,
        "exact_information": exact_text,
        "page": page,
        "source": source_value,
        "raw": group,
    }


def _grouped_keywords(group: dict[str, Any]) -> list[str]:
    values = group.get("grouped_keywords")
    if values is None:
        values = group.get("related_keywords", [])
    if not isinstance(values, list):
        values = [values]
    return [str(value).strip() for value in values if str(value).strip()]


def _match_items(
    predicted_items: list[dict[str, Any]],
    truth_items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    matches = []
    used_predicted_indexes = set()
    for truth_index, truth in enumerate(truth_items):
        best_index = None
        best_score = -1.0
        for predicted_index, predicted in enumerate(predicted_items):
            if predicted_index in used_predicted_indexes:
                continue
            if not _keyword_alias_match(predicted, truth):
                continue
            score = _grouping_match_score(predicted, truth)
            if score > best_score:
                best_index = predicted_index
                best_score = score
        if best_index is not None:
            used_predicted_indexes.add(best_index)
            matches.append(
                {
                    "truth_index": truth_index,
                    "predicted_index": best_index,
                    "truth": truth,
                    "predicted": predicted_items[best_index],
                }
            )
    return matches


def _keyword_alias_match(predicted: dict[str, Any], truth: dict[str, Any]) -> bool:
    predicted_key = predicted["normalized_key"]
    truth_key = truth["normalized_key"]
    return (
        predicted_key == truth_key
        or truth_key in predicted["aliases"]
        or predicted_key in truth["aliases"]
    )


def _score_match(predicted: dict[str, Any], truth: dict[str, Any]) -> dict[str, Any]:
    scores = {
        "keyword_match_score": _keyword_match_score(predicted, truth),
        "grouping_match_score": _grouping_match_score(predicted, truth),
        "context_match_score": _context_match_score(predicted, truth),
        "exact_information_match_score": _exact_information_match_score(predicted, truth),
        "page_match_score": _page_match_score(predicted, truth),
    }
    overall_score = sum(scores[key] * weight for key, weight in WEIGHTS.items())
    return {
        "ground_truth_id": truth.get("id"),
        "representative_keyword": truth["representative_keyword"],
        "predicted_representative_keyword": predicted["representative_keyword"],
        "overall_score": round(overall_score, 4),
        "scores": {key: round(value, 4) for key, value in scores.items()},
        "ground_truth": _public_item(truth),
        "predicted": _public_item(predicted),
    }


def _keyword_match_score(predicted: dict[str, Any], truth: dict[str, Any]) -> float:
    return 1.0 if _keyword_alias_match(predicted, truth) else 0.0


def _grouping_match_score(predicted: dict[str, Any], truth: dict[str, Any]) -> float:
    truth_aliases = truth["aliases"]
    predicted_aliases = predicted["aliases"]
    if not truth_aliases:
        return 0.0
    return _ratio(len(truth_aliases & predicted_aliases), len(truth_aliases))


def _context_match_score(predicted: dict[str, Any], truth: dict[str, Any]) -> float:
    return _text_similarity(predicted.get("context_text"), truth.get("context_text"))


def _exact_information_match_score(predicted: dict[str, Any], truth: dict[str, Any]) -> float:
    if not _normalize_text(truth.get("exact_information")):
        return 1.0
    return _text_similarity(predicted.get("exact_information"), truth.get("exact_information"))


def _page_match_score(predicted: dict[str, Any], truth: dict[str, Any]) -> float:
    truth_page = truth.get("page")
    truth_source = _normalize_text(truth.get("source"))
    predicted_page = predicted.get("page")
    predicted_source = _normalize_text(predicted.get("source"))
    page_expected = truth_page not in (None, "")
    source_expected = bool(truth_source)

    if not page_expected and not source_expected:
        return 1.0
    page_score = 1.0 if page_expected and str(predicted_page) == str(truth_page) else 0.0
    source_score = 1.0 if source_expected and predicted_source == truth_source else 0.0
    if page_expected and source_expected:
        return (page_score + source_score) / 2
    return page_score if page_expected else source_score


def _text_similarity(predicted_text: object, truth_text: object) -> float:
    predicted = _normalize_text(predicted_text)
    truth = _normalize_text(truth_text)
    if not predicted and not truth:
        return 1.0
    if not predicted or not truth:
        return 0.0
    if predicted in truth or truth in predicted:
        shorter = min(len(predicted), len(truth))
        longer = max(len(predicted), len(truth))
        return max(0.85, _ratio(shorter, longer))

    token_score = _token_f1(predicted, truth)
    sequence_score = SequenceMatcher(None, predicted, truth).ratio()
    return max(token_score, sequence_score)


def _token_f1(predicted: str, truth: str) -> float:
    predicted_tokens = _tokens(predicted)
    truth_tokens = _tokens(truth)
    if not predicted_tokens and not truth_tokens:
        return 1.0
    if not predicted_tokens or not truth_tokens:
        return 0.0
    overlap = len(predicted_tokens & truth_tokens)
    precision = _ratio(overlap, len(predicted_tokens))
    recall = _ratio(overlap, len(truth_tokens))
    return _ratio(2 * precision * recall, precision + recall)


def _missing_item(item: dict[str, Any]) -> dict[str, Any]:
    public = _public_item(item)
    public["normalized_key"] = item["normalized_key"]
    return public


def _extra_item(item: dict[str, Any]) -> dict[str, Any]:
    public = _public_item(item)
    public["normalized_key"] = item["normalized_key"]
    return public


def _public_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item.get("id"),
        "representative_keyword": item.get("representative_keyword"),
        "grouped_keywords": item.get("grouped_keywords", []),
        "context_text": item.get("context_text"),
        "exact_information": item.get("exact_information"),
        "page": item.get("page"),
        "source": item.get("source"),
    }


def _normalize_key(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").casefold()).strip()


def _normalize_text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().casefold())


def _tokens(value: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", value.casefold()))


def _ratio(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate extraction result against ground truth.")
    parser.add_argument("--result", required=True, type=Path)
    parser.add_argument("--ground-truth", required=True, type=Path)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args(argv)

    report = compare_keywords(args.result, args.ground_truth)
    if args.output:
        save_json(report, args.output)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
