from __future__ import annotations

import json
import re
from typing import Any


def parse_json_object(text: str | None) -> dict[str, Any] | None:
    if not text:
        return None
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped, flags=re.IGNORECASE)
        stripped = re.sub(r"\s*```$", "", stripped)
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", stripped, flags=re.DOTALL)
        if not match:
            return None
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    return parsed if isinstance(parsed, dict) else None


def compact_json(value: Any, *, max_chars: int = 12000) -> str:
    text = json.dumps(value, default=str, ensure_ascii=False)
    return text if len(text) <= max_chars else f"{text[:max_chars]}..."
