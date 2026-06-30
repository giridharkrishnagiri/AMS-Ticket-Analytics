from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models import GenAIChatMessage, GenAIChatSession
from app.services.genai.charts.chart_builder import build_chart_from_tool_result
from app.services.genai.charts.chart_store import store_generated_chart
from app.services.genai.charts.validation import ChartValidationError
from app.services.genai.safety_service import get_or_create_safety_settings


def _chart_metadata(row: Any) -> dict[str, Any]:
    return {
        "chart_id": str(row.id),
        "title": row.title,
        "chart_type": row.chart_type,
        "chart_library": row.chart_library,
        "source_tool_names": row.source_tool_names_json or [],
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def generate_charts_for_agent(
    db: Session,
    *,
    session: GenAIChatSession,
    user_message: GenAIChatMessage,
    context: dict[str, Any],
    question: str,
    tool_results: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    generated: list[dict[str, Any]] = []
    warnings: list[str] = []
    if not tool_results:
        return generated, ["No governed tool results were available for chart generation."]

    safety = get_or_create_safety_settings(db)
    customer_id = context.get("customer_id") or session.customer_id
    project_id = context.get("project_id") or session.project_id

    for result in tool_results:
        if result.get("status") != "success":
            if result.get("status") == "unsupported":
                warnings.append(
                    f"{result.get('tool_name') or 'Governed tool'} did not return chartable data."
                )
            continue
        try:
            built = build_chart_from_tool_result(
                result,
                question=question,
                max_data_points=safety.max_chart_data_points,
            )
        except ChartValidationError as exc:
            warnings.append(str(exc))
            continue
        warnings.extend(warning for warning in built.warnings if warning not in warnings)
        applied_filters = (
            result.get("applied_filters")
            if isinstance(result.get("applied_filters"), dict)
            else {}
        )
        row = store_generated_chart(
            db,
            chart=built,
            customer_id=customer_id,
            project_id=project_id,
            session_id=session.id,
            message_id=user_message.id,
            parameters=applied_filters,
            filters=applied_filters,
        )
        generated.append(_chart_metadata(row))
        break

    if not generated and not warnings:
        warnings.append("The governed tool result was not compatible with Phase 2A charting.")
    return generated, warnings
