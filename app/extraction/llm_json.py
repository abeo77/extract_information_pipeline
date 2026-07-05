"""Shared helpers for JSON-only LLM calls."""

from __future__ import annotations

import json
import re
from typing import Any


def build_json_prompt(instructions: str, payload_label: str, payload: Any) -> str:
    return (
        f"{instructions}\n\n"
        f"{payload_label}:\n"
        f"{json.dumps(payload, ensure_ascii=False)}"
    )


def response_text(response: Any) -> str:
    content = getattr(response, "content", response)
    if isinstance(content, list):
        return "\n".join(str(item) for item in content)
    return str(content)


def parse_json_response(text: str, stage: str) -> dict[str, Any]:
    text = _strip_code_fence(text.strip())
    if not text:
        raise ValueError(f"{stage} returned an empty response")

    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        value = json.loads(_first_json_object(text))

    if not isinstance(value, dict):
        raise ValueError(f"{stage} response must be a JSON object")
    return value


def require_list(payload: dict[str, Any], field: str, stage: str) -> list[Any]:
    value = payload.get(field, [])
    if not isinstance(value, list):
        raise ValueError(f"{stage} response field {field} must be a list")
    return value


def clean_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def compact_dict(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value not in (None, [], {})}


def _strip_code_fence(text: str) -> str:
    if not text.startswith("```"):
        return text
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    return re.sub(r"\s*```$", "", text)


def _first_json_object(text: str) -> str:
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        raise json.JSONDecodeError("No JSON object found", text, 0)
    return match.group(0)
