from __future__ import annotations

import re
from typing import Any

from sqlalchemy import func, literal, or_


def normalize_assignment_group_display(value: str | None) -> str:
    if value is None:
        return ""
    normalized = value.replace("\xa0", " ")
    return re.sub(r"\s+", " ", normalized).strip()


def is_basis_security_assignment_group(assignment_group: str | None) -> bool:
    normalized = normalize_assignment_group_display(assignment_group).casefold()
    return "basis" in normalized or "security" in normalized


def normalized_assignment_group_expression(expression: Any) -> Any:
    without_nbsp = func.replace(
        func.coalesce(expression, literal("")),
        literal("\xa0"),
        literal(" "),
    )
    collapsed = func.regexp_replace(without_nbsp, literal(r"\s+"), literal(" "), literal("g"))
    return func.lower(func.btrim(collapsed))


def basis_security_assignment_group_condition(expression: Any) -> Any:
    normalized = normalized_assignment_group_expression(expression)
    return or_(normalized.like("%basis%"), normalized.like("%security%"))
