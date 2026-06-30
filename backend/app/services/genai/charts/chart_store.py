from __future__ import annotations

from copy import deepcopy
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
from app.services.genai.charts.chart_builder import (
    BuiltChart,
    build_chart_from_table,
    build_chart_from_tool_result,
)
from app.services.genai.safety_service import get_or_create_safety_settings
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
        is_archived=chart.is_archived,
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
    if chart is None:
        raise GeneratedChartNotFoundError("Generated chart was not found.")
    return chart


def _chart_table(chart_spec: dict[str, Any]) -> dict[str, Any]:
    table = chart_spec.get("table") if isinstance(chart_spec, dict) else {}
    return deepcopy(table) if isinstance(table, dict) else {"columns": [], "rows": []}


def _chart_title_text(title: str, subtitle: str | None) -> str:
    return title if not subtitle else f"{title}<br><sup>{subtitle}</sup>"


def _replace_chart_title(
    chart_spec: dict[str, Any],
    *,
    title: str,
    subtitle: str | None,
) -> dict[str, Any]:
    next_spec = deepcopy(chart_spec)
    next_spec["title"] = title
    next_spec["subtitle"] = subtitle
    plotly = next_spec.get("plotly")
    layout = plotly.get("layout") if isinstance(plotly, dict) else None
    if isinstance(layout, dict):
        layout["title"] = {"text": _chart_title_text(title, subtitle)}
    return next_spec


def _current_presentation_settings(chart: GenAIGeneratedChart) -> dict[str, Any]:
    chart_settings = {}
    if isinstance(chart.chart_spec_json, dict):
        value = chart.chart_spec_json.get("presentation_settings")
        if isinstance(value, dict):
            chart_settings = value
    parameters = chart.parameters_json if isinstance(chart.parameters_json, dict) else {}
    parameter_settings = parameters.get("presentation_settings")
    if isinstance(parameter_settings, dict):
        chart_settings = {**chart_settings, **parameter_settings}
    return chart_settings


def update_generated_chart(
    db: Session,
    chart_id: UUID,
    updates: dict[str, Any],
) -> GenAIGeneratedChart:
    chart = get_generated_chart(db, chart_id)
    safety = get_or_create_safety_settings(db)
    parameters = deepcopy(chart.parameters_json or {})
    original_spec = parameters.get("original_chart_spec")
    if not isinstance(original_spec, dict):
        original_spec = deepcopy(chart.chart_spec_json)
        parameters["original_chart_spec"] = deepcopy(original_spec)

    settings = _current_presentation_settings(chart)
    settings.update(updates)
    chart_type = settings.get("chart_type") or chart.chart_type
    title = str(settings.get("title") if "title" in settings else chart.title).strip()
    subtitle = settings.get("subtitle") if "subtitle" in settings else chart.subtitle
    subtitle = str(subtitle).strip() if subtitle not in {None, ""} else None
    show_labels = bool(settings.get("show_labels", True))
    show_legend = bool(settings.get("show_legend", True))
    sort_order = str(settings.get("sort_order") or "original")

    built = build_chart_from_table(
        _chart_table(original_spec),
        title=title,
        subtitle=subtitle,
        current_chart_type=chart.chart_type,
        source_tool_names=chart.source_tool_names_json or [],
        source_tool_results_summary=chart.source_tool_results_summary_json or [],
        parameters=parameters,
        filters=chart.filters_json or {},
        data_notes=original_spec.get("data_notes", chart.data_notes_json or []),
        warnings=original_spec.get("warnings", chart.warnings_json or []),
        chart_type=chart_type,
        orientation=settings.get("orientation"),
        display_mode=settings.get("display_mode"),
        show_labels=show_labels,
        show_legend=show_legend,
        sort_order=sort_order,
        top_n=settings.get("top_n"),
        x_axis_title=settings.get("x_axis_title"),
        y_axis_title=settings.get("y_axis_title"),
        z_axis_title=settings.get("z_axis_title"),
        max_data_points=safety.max_chart_data_points,
    )

    parameters["presentation_settings"] = {
        "title": title,
        "subtitle": subtitle,
        "chart_type": built.chart_type,
        "orientation": "horizontal" if built.chart_type == "horizontal_bar" else "vertical",
        "display_mode": "3d" if built.chart_type == "scatter_3d" else "2d",
        "show_labels": show_labels,
        "show_legend": show_legend,
        "sort_order": sort_order,
        "top_n": settings.get("top_n"),
        "x_axis_title": settings.get("x_axis_title"),
        "y_axis_title": settings.get("y_axis_title"),
        "z_axis_title": settings.get("z_axis_title"),
        "color_by": settings.get("color_by"),
    }

    chart.title = built.title[:255]
    chart.subtitle = built.subtitle
    chart.chart_type = built.chart_type
    chart.chart_library = built.chart_library
    chart.chart_spec_json = built.chart_spec
    chart.parameters_json = parameters
    chart.data_notes_json = built.data_notes
    chart.warnings_json = built.warnings
    db.commit()
    db.refresh(chart)
    create_usage_log(
        db,
        operation="chart_update",
        status="success",
        customer_id=chart.customer_id,
        project_id=chart.project_id,
        session_id=chart.session_id,
        message_id=chart.message_id,
        question=chart.title,
        tools_used_json=chart.source_tool_names_json,
        error_message="; ".join(chart.warnings_json[:3]) if chart.warnings_json else None,
    )
    return chart


def duplicate_generated_chart(
    db: Session,
    chart_id: UUID,
    *,
    title: str | None = None,
) -> GenAIGeneratedChart:
    source = get_generated_chart(db, chart_id)
    duplicate_title = (title or f"Copy of {source.title}").strip()[:255]
    duplicate_spec = _replace_chart_title(
        source.chart_spec_json,
        title=duplicate_title,
        subtitle=source.subtitle,
    )
    parameters = deepcopy(source.parameters_json or {})
    parameters["source_chart_id"] = str(source.id)
    row = GenAIGeneratedChart(
        customer_id=source.customer_id,
        project_id=source.project_id,
        session_id=source.session_id,
        message_id=source.message_id,
        title=duplicate_title,
        subtitle=source.subtitle,
        chart_type=source.chart_type,
        chart_library=source.chart_library,
        chart_spec_json=duplicate_spec,
        source_tool_names_json=deepcopy(source.source_tool_names_json or []),
        source_tool_results_summary_json=deepcopy(source.source_tool_results_summary_json or []),
        parameters_json=parameters,
        filters_json=deepcopy(source.filters_json or {}),
        data_notes_json=deepcopy(source.data_notes_json or []),
        warnings_json=deepcopy(source.warnings_json or []),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    create_usage_log(
        db,
        operation="chart_duplicate",
        status="success",
        customer_id=row.customer_id,
        project_id=row.project_id,
        session_id=row.session_id,
        message_id=row.message_id,
        question=row.title,
        tools_used_json=row.source_tool_names_json,
    )
    return row


def archive_generated_chart(db: Session, chart_id: UUID) -> GenAIGeneratedChart:
    chart = get_generated_chart(db, chart_id)
    chart.is_archived = True
    db.commit()
    db.refresh(chart)
    create_usage_log(
        db,
        operation="chart_archive",
        status="success",
        customer_id=chart.customer_id,
        project_id=chart.project_id,
        session_id=chart.session_id,
        message_id=chart.message_id,
        question=chart.title,
        tools_used_json=chart.source_tool_names_json,
    )
    return chart


def reset_generated_chart(db: Session, chart_id: UUID) -> GenAIGeneratedChart:
    chart = get_generated_chart(db, chart_id)
    parameters = deepcopy(chart.parameters_json or {})
    original_spec = parameters.get("original_chart_spec")
    if not isinstance(original_spec, dict):
        warning = (
            "Original generated chart spec is not available; chart remains at the last saved "
            "state."
        )
        warnings = list(chart.warnings_json or [])
        if warning not in warnings:
            warnings.append(warning)
        chart.warnings_json = warnings
        if isinstance(chart.chart_spec_json, dict):
            chart.chart_spec_json = {**chart.chart_spec_json, "warnings": warnings}
        db.commit()
        db.refresh(chart)
        return chart

    parameters.pop("presentation_settings", None)
    chart.chart_spec_json = deepcopy(original_spec)
    chart.title = str(original_spec.get("title") or chart.title)[:255]
    subtitle = original_spec.get("subtitle")
    chart.subtitle = str(subtitle) if subtitle not in {None, ""} else None
    chart.chart_type = str(original_spec.get("chart_type") or chart.chart_type)
    chart.data_notes_json = list(original_spec.get("data_notes") or chart.data_notes_json or [])
    chart.warnings_json = list(original_spec.get("warnings") or [])
    chart.parameters_json = parameters
    db.commit()
    db.refresh(chart)
    create_usage_log(
        db,
        operation="chart_reset",
        status="success",
        customer_id=chart.customer_id,
        project_id=chart.project_id,
        session_id=chart.session_id,
        message_id=chart.message_id,
        question=chart.title,
        tools_used_json=chart.source_tool_names_json,
    )
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
