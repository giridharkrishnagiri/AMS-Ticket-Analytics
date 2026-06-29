from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.schemas.genai import GenAIToolExecuteRequest
from app.services.genai.tools.registry import execute_tool


def _uuid_or_none(value: Any) -> UUID | None:
    if value in (None, ""):
        return None
    if isinstance(value, UUID):
        return value
    return UUID(str(value))


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        text = str(value).strip()
        if text and text not in seen:
            seen.add(text)
            deduped.append(text)
    return deduped


def execute_validated_plan(
    db: Session,
    *,
    plan: list[dict[str, Any]],
    customer_id: Any,
    project_id: Any,
) -> tuple[list[dict[str, Any]], list[str], list[str], list[str]]:
    tool_results: list[dict[str, Any]] = []
    data_notes: list[str] = []
    warnings: list[str] = []
    tools_used: list[str] = []

    for item in plan:
        request = GenAIToolExecuteRequest(
            tool_name=item["tool_name"],
            customer_id=_uuid_or_none(customer_id),
            project_id=_uuid_or_none(project_id),
            parameters=item.get("parameters") or {},
            filters=item.get("filters") or {},
        )
        response = execute_tool(db, request)
        response_json = response.model_dump(mode="json")
        tool_results.append(response_json)
        tools_used.append(response.tool_name)
        data_notes.extend(response.data_notes)
        warnings.extend(response.warnings)
        if response.status != "success":
            warnings.append(
                f"{response.tool_name} returned status '{response.status}'.",
            )
        if response.truncated:
            warnings.append(
                f"{response.tool_name} returned a capped result set; additional rows were omitted.",
            )

    return tool_results, _dedupe(data_notes), _dedupe(warnings), tools_used
