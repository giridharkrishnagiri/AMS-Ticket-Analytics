import re
from typing import Any


_NATURAL_ID_PATTERN = re.compile(r"\d+|\D+")


def _natural_id_parts(value: str) -> tuple[tuple[int, int | str], ...]:
    parts: list[tuple[int, int | str]] = []
    for token in _NATURAL_ID_PATTERN.findall(value.strip().lower()):
        if token.isdigit():
            parts.append((0, int(token)))
        else:
            parts.append((1, token))
    return tuple(parts)


def hierarchy_sort_key(item: Any) -> tuple[Any, ...]:
    external_id = str(getattr(item, "external_id", "") or "").strip()
    label = str(getattr(item, "name", None) or getattr(item, "title", None) or "").strip().lower()
    created_at = getattr(item, "created_at", None)

    return (
        0 if external_id else 1,
        _natural_id_parts(external_id),
        label,
        str(created_at or ""),
        str(getattr(item, "id", "")),
    )


def sort_hierarchy_items(items: list[Any]) -> list[Any]:
    return sorted(items, key=hierarchy_sort_key)
