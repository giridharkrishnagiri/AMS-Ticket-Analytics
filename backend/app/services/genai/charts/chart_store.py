from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import GenAIGeneratedChart
from app.schemas.genai import (
    GenAIChartTable,
    GenAIGeneratedChartListItemResponse,
    GenAIGeneratedChartResponse,
    GenAIToolColumn,
)
from app.services.genai.charts.chart_builder import BuiltChart, build_chart_from_tool_result
from app.services.genai.usage_log_service import create_usage_log


@dataclass(frozen=True)
class GeneratedChartListResult:
    items: list[GenAIGeneratedChart]
    total: int


class GeneratedChartNotFoundError(ValueError):
    pass


def _coerce_uuid(value: UUID | str | None) -> UUID | None:
    if value is None or isinstance(value, UUID):
        return value
    return UUID(str(value))


def _to_table(chart: GenAIGeneratedChart) -> GenAIChartTable:
    table = chart.chart_spec_json.get("table") if isinstance(chart.chart_spec_json, dict) else {}
    columns = table.get("columns") if isinstance(table, dict) else []
    rows = table.get("rows") if isinstance(table, dict) else []
    return GenAIChartTable(
        columns=[GenAIToolColumn(**column) for column in columns if isinstance(column, dict)],
        rows=[row for row in rows if isinstance(row, dict)],
    )


def to_chart_response(chart: GenAIGeneratedChart) -> GenAIGeneratedChartResponse:
    return GenAIGeneratedChartResponse(
        id=chart.id,
        customer_id=chart.customer_id,
        project_id=chart.project_id,
        session_id=chart.session_id,
        message_id=chart.message_id,
        title=chart.title,
        subtitle=chart.subtitle,
        chart_type=chart.chart_type,
        chart_library=chart.chart_library,
        chart_spec=chart.chart_spec_json,
        table=_to_table(chart),
        source_tool_names=chart.source_tool_names_json or [],
        source_tool_results_summary=chart.source_tool_results_summary_json or [],
        parameters=chart.parameters_json or {},
        filters=chart.filters_json or {},
        data_notes=chart.data_notes_json or [],
        warnings=chart.warnings_json or [],
        created_at=chart.created_at,
        updated_at=chart.updated_at,
    )


def to_chart_list_item(chart: GenAIGeneratedChart) -> GenAIGeneratedChartListItemResponse:
    return GenAIGeneratedChartListItemResponse.model_validate(chart)


def store_generated_chart(
    db: Session,
    *,
    chart: BuiltChart,
    customer_id: UUID | str | None = None,
    project_id: UUID | str | None = None,
    session_id: UUID | str | None = None,
    message_id: UUID | str | None = None,
    parameters: dict[str, Any] | None = None,
    filters: dict[str, Any] | None = None,
    log_usage: bool = True,
) -> GenAIGeneratedChart:
    row = GenAIGeneratedChart(
        customer_id=_coerce_uuid(customer_id),
        project_id=_coerce_uuid(project_id),
        session_id=str(session_id) if session_id else None,
        message_id=str(message_id) if message_id else None,
        title=chart.title[:255],
        subtitle=chart.subtitle,
        chart_type=chart.chart_type,
        chart_library=chart.chart_library,
        chart_spec_json=chart.chart_spec,
        source_tool_names_json=chart.source_tool_names,
        source_tool_results_summary_json=chart.source_tool_results_summary,
        parameters_json=parameters or chart.parameters,
        filters_json=filters or chart.filters,
        data_notes_json=chart.data_notes,
        warnings_json=chart.warnings,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    if log_usage:
        create_usage_log(
            db,
            operation="chart_generation",
            status="success",
            customer_id=row.customer_id,
            project_id=row.project_id,
            session_id=row.session_id,
            message_id=row.message_id,
            question=row.title,
            tools_used_json=row.source_tool_names_json,
            error_message="; ".join(row.warnings_json[:3]) if row.warnings_json else None,
        )
    return row


def create_chart_from_tool_result(
    db: Session,
    *,
    tool_result: dict[str, Any],
    customer_id: UUID | str | None = None,
    project_id: UUID | str | None = None,
    session_id: UUID | str | None = None,
    message_id: UUID | str | None = None,
    question: str | None = None,
    chart_type: str | None = None,
    max_data_points: int = 500,
) -> GenAIGeneratedChart:
    built = build_chart_from_tool_result(
        tool_result,
        question=question,
        requested_chart_type=chart_type,
        max_data_points=max_data_points,
    )
    return store_generated_chart(
        db,
        chart=built,
        customer_id=customer_id,
        project_id=project_id,
        session_id=session_id,
        message_id=message_id,
        parameters={},
        filters=built.filters,
    )


def list_generated_charts(
    db: Session,
    *,
    customer_id: UUID | None = None,
    project_id: UUID | None = None,
    session_id: str | None = None,
    chart_type: str | None = None,
    include_archived: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> GeneratedChartListResult:
    statement = select(GenAIGeneratedChart)
    count_statement = select(func.count()).select_from(GenAIGeneratedChart)
    filters = []
    if customer_id is not None:
        filters.append(GenAIGeneratedChart.customer_id == customer_id)
    if project_id is not None:
        filters.append(GenAIGeneratedChart.project_id == project_id)
    if session_id:
        filters.append(GenAIGeneratedChart.session_id == session_id)
    if chart_type:
        filters.append(GenAIGeneratedChart.chart_type == chart_type)
    if not include_archived:
        filters.append(GenAIGeneratedChart.is_archived.is_(False))
    if filters:
        statement = statement.where(*filters)
        count_statement = count_statement.where(*filters)
    statement = (
        statement.order_by(GenAIGeneratedChart.created_at.desc()).limit(limit).offset(offset)
    )
    return GeneratedChartListResult(
        items=db.execute(statement).scalars().all(),
        total=int(db.execute(count_statement).scalar_one() or 0),
    )


def get_generated_chart(db: Session, chart_id: UUID) -> GenAIGeneratedChart:
    chart = db.get(GenAIGeneratedChart, chart_id)
    if chart is None or chart.is_archived:
        raise GeneratedChartNotFoundError("Generated chart was not found.")
    return chart


def attach_charts_to_message(db: Session, chart_ids: list[str], message_id: UUID | str) -> None:
    if not chart_ids:
        return
    parsed_ids = []
    for chart_id in chart_ids:
        try:
            parsed_ids.append(UUID(str(chart_id)))
        except ValueError:
            continue
    if not parsed_ids:
        return
    charts = (
        db.execute(select(GenAIGeneratedChart).where(GenAIGeneratedChart.id.in_(parsed_ids)))
        .scalars()
        .all()
    )
    for chart in charts:
        chart.message_id = str(message_id)
    db.commit()
