from __future__ import annotations

import json
import re
from typing import Any

ALLOWED_CHART_TYPES = {
    "bar",
    "horizontal_bar",
    "grouped_bar",
    "stacked_bar",
    "line",
    "multi_line",
    "pie",
    "donut",
    "scatter",
    "scatter_3d",
    "table",
}

FORBIDDEN_CHART_MARKERS = (
    "normalized_payload",
    "cmdb_payload",
    "raw_sla",
    "raw_ola",
    "api_key",
    "password",
    "secret",
)

FORBIDDEN_KEY_PATTERN = re.compile(
    "|".join(re.escape(item) for item in FORBIDDEN_CHART_MARKERS),
    re.IGNORECASE,
)


class ChartValidationError(ValueError):
    pass


def validate_chart_type(chart_type: str) -> str:
    normalized = chart_type.strip().lower()
    if normalized not in ALLOWED_CHART_TYPES:
        raise ChartValidationError(f"Chart type '{chart_type}' is not supported.")
    return normalized


def sanitize_chart_json(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for raw_key, child in value.items():
            key = str(raw_key)
            if FORBIDDEN_KEY_PATTERN.search(key):
                continue
            if key in {"function", "callback", "onClick", "onHover", "eval"}:
                continue
            sanitized[key] = sanitize_chart_json(child)
        return sanitized
    if isinstance(value, list):
        return [sanitize_chart_json(item) for item in value]
    if isinstance(value, str):
        text = value
        for marker in FORBIDDEN_CHART_MARKERS:
            text = re.sub(re.escape(marker), "restricted payload fields", text, flags=re.IGNORECASE)
        return text
    return value


def ensure_json_serializable(value: Any) -> Any:
    try:
        json.dumps(value)
    except TypeError as exc:
        raise ChartValidationError("Chart spec must be JSON serializable.") from exc
    return value


def assert_no_forbidden_markers(value: Any) -> None:
    rendered = json.dumps(value, default=str).lower()
    for marker in FORBIDDEN_CHART_MARKERS:
        if marker in rendered:
            raise ChartValidationError("Chart spec contains a forbidden raw payload marker.")
