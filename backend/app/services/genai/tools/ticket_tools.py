from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AssessmentOutOfScopeTicket, Ticket
from app.schemas.genai import GenAIToolColumn, GenAIToolExecuteResponse
from app.services.genai.tools.base import ToolExecutionRequest, ToolMetadata, tool_response
from app.services.genai.tools.validation import (
    ToolValidationError,
    apply_datetime_range,
    apply_project_context,
    cap_rows,
    date_range_from_parameters,
    ensure_allowed,
    max_rows_from_safety,
    month_period_expression,
    normalize_scope,
    normalize_ticket_type,
    normalized_key,
    numeric_percentage,
    project_ids_for_context,
    ticket_canceled_condition,
    ticket_canceled_datetime_expression,
    ticket_closed_condition,
    ticket_completion_datetime_expression,
    ticket_open_condition,
    ticket_status_group_expression,
    ticket_type_values,
)

TICKET_DATA_NOTES = [
    "Generic Tickets includes Incidents and SC Tasks only.",
    "Problems and Changes are excluded.",
    "Ticket tools return aggregate rows only and never expose raw normalized ticket payloads.",
]

DIRECT_TICKET_DIMENSIONS = {
    "functional_track": "functional_track",
    "ams_owner": "ams_owner",
    "assignment_group": "assignment_group",
    "parent_business_application": "parent_application_name",
    "application_owner": "application_owner",
    "supported_by_vendor": "supported_by_vendor",
    "sap_non_sap": "sap_non_sap",
    "architecture_type": "architecture_type",
    "install_type": "install_type",
    "priority": "priority",
    "state": "state",
}

TICKET_FILTER_FIELDS = {
    **DIRECT_TICKET_DIMENSIONS,
    "derived_vendor": "derived_vendor",
    "business_service_ci_name": "business_service_ci_name",
}

TICKET_DISTRIBUTION_DIMENSIONS = (
    "functional_track",
    "ams_owner",
    "functional_track_ams_owner",
    "assignment_group",
    "assignment_group_support_owner",
    "parent_business_application",
    "application_owner",
    "supported_by_vendor",
    "sap_non_sap",
    "architecture_type",
    "install_type",
    "priority",
    "state",
    "status_group",
)
TICKET_METRICS = ("created_count", "resolved_closed_count", "canceled_closed_incomplete_count")


def _ticket_columns() -> list[GenAIToolColumn]:
    return [
        GenAIToolColumn(key="metric", label="Metric", type="string"),
        GenAIToolColumn(key="value", label="Value", type="number"),
    ]


def _models_for_scope(scope: str) -> tuple[type[Any], ...]:
    if scope == "in_scope":
        return (Ticket,)
    if scope == "out_of_scope":
        return (AssessmentOutOfScopeTicket,)
    return (Ticket, AssessmentOutOfScopeTicket)


def _context_project_ids(db: Session, request: ToolExecutionRequest) -> list[Any] | None:
    return project_ids_for_context(
        db,
        customer_id=request.customer_id,
        project_id=request.project_id,
    )


def _apply_common_filters(
    statement: Any,
    model: type[Any],
    db: Session,
    request: ToolExecutionRequest,
    *,
    ticket_type: str,
) -> tuple[Any, dict[str, Any], list[str]]:
    statement = apply_project_context(statement, model, _context_project_ids(db, request))
    statement = statement.where(func.upper(model.ticket_type).in_(ticket_type_values(ticket_type)))
    applied: dict[str, Any] = {"ticket_type": ticket_type}
    warnings: list[str] = []

    for raw_key, raw_values in (request.filters or {}).items():
        key = normalized_key(raw_key)
        if not key:
            continue
        if key not in TICKET_FILTER_FIELDS:
            if raw_values:
                warnings.append(f"Ticket filter '{key}' is not supported by this tool.")
            continue
        values = raw_values if isinstance(raw_values, list) else [raw_values]
        cleaned_values = [str(value).strip() for value in values if str(value).strip()]
        if not cleaned_values:
            continue
        column = getattr(model, TICKET_FILTER_FIELDS[key])
        statement = statement.where(func.btrim(column).in_(cleaned_values))
        applied[key] = cleaned_values
    return statement, applied, warnings


def _metric_date_expression(model: type[Any], metric: str) -> Any:
    if metric == "created_count":
        return model.created_at
    if metric == "canceled_closed_incomplete_count":
        return ticket_canceled_datetime_expression(model)
    return ticket_completion_datetime_expression(model)


def _metric_condition(model: type[Any], metric: str) -> Any:
    if metric == "resolved_closed_count":
        return ticket_closed_condition(model)
    if metric == "canceled_closed_incomplete_count":
        return ticket_canceled_condition(model)
    return model.created_at.is_not(None)


def _count_metric(
    db: Session,
    model: type[Any],
    request: ToolExecutionRequest,
    *,
    ticket_type: str,
    metric: str,
    start: datetime | None,
    end: datetime | None,
) -> tuple[int, dict[str, Any], list[str]]:
    date_expression = _metric_date_expression(model, metric)
    statement = select(func.count()).where(
        _metric_condition(model, metric),
        date_expression.is_not(None),
    )
    statement, applied, warnings = _apply_common_filters(
        statement,
        model,
        db,
        request,
        ticket_type=ticket_type,
    )
    statement = apply_datetime_range(statement, date_expression, start, end)
    return int(db.execute(statement).scalar_one() or 0), applied, warnings


def _sum_metric(
    db: Session,
    request: ToolExecutionRequest,
    *,
    scope: str,
    ticket_type: str,
    metric: str,
    start: datetime | None,
    end: datetime | None,
) -> tuple[int, dict[str, Any], list[str]]:
    total = 0
    applied: dict[str, Any] = {"scope": scope, "ticket_type": ticket_type}
    warnings: list[str] = []
    for model in _models_for_scope(scope):
        count, model_applied, model_warnings = _count_metric(
            db,
            model,
            request,
            ticket_type=ticket_type,
            metric=metric,
            start=start,
            end=end,
        )
        total += count
        applied.update(model_applied)
        warnings.extend(model_warnings)
    return total, applied, warnings


def _date_range_label(start: datetime | None, end: datetime | None) -> str:
    start_label = start.date().isoformat() if start else "all available"
    end_label = end.date().isoformat() if end else "all available"
    return f"{start_label} to {end_label}"


def _dimension_expression(model: type[Any], dimension: str) -> Any:
    if dimension == "functional_track_ams_owner":
        return func.nullif(
            func.concat_ws(
                " / ",
                func.nullif(func.btrim(model.functional_track), ""),
                func.nullif(func.btrim(model.ams_owner), ""),
            ),
            "",
        )
    if dimension == "assignment_group_support_owner":
        return func.nullif(
            func.concat_ws(
                " / ",
                func.nullif(func.btrim(model.assignment_group), ""),
                func.nullif(func.btrim(model.assignment_group_owner), ""),
            ),
            "",
        )
    if dimension == "status_group":
        return ticket_status_group_expression(model)
    return func.nullif(func.btrim(getattr(model, DIRECT_TICKET_DIMENSIONS[dimension])), "")


def _distribution_rows_for_model(
    db: Session,
    model: type[Any],
    request: ToolExecutionRequest,
    *,
    ticket_type: str,
    dimension: str,
    metric: str,
    start: datetime | None,
    end: datetime | None,
) -> tuple[list[tuple[str, int]], dict[str, Any], list[str]]:
    dimension_expr = _dimension_expression(model, dimension)
    display_expr = func.coalesce(dimension_expr, "Unspecified")
    date_expression = _metric_date_expression(model, metric)
    statement = (
        select(display_expr.label("dimension"), func.count().label("value"))
        .where(_metric_condition(model, metric), dimension_expr.is_not(None))
        .group_by(display_expr)
    )
    statement, applied, warnings = _apply_common_filters(
        statement,
        model,
        db,
        request,
        ticket_type=ticket_type,
    )
    statement = apply_datetime_range(statement, date_expression, start, end)
    rows = [(str(row.dimension), int(row.value or 0)) for row in db.execute(statement)]
    return rows, applied, warnings


class TicketVolumeSummaryTool:
    metadata = ToolMetadata(
        tool_name="get_ticket_volume_summary",
        domain="tickets",
        display_name="Ticket Volume Summary",
        description="Returns aggregate ticket volume for Incidents and SC Tasks.",
        allowed_metrics=TICKET_METRICS,
        max_rows=25,
        data_safety_level="aggregate",
    )

    def execute(self, db: Session, request: ToolExecutionRequest) -> GenAIToolExecuteResponse:
        if not request.safety_settings.allow_aggregate_ticket_data:
            raise ToolValidationError("Aggregate ticket data is disabled by GenAI safety settings.")
        scope = normalize_scope(request.parameters)
        ticket_type = normalize_ticket_type(request.parameters)
        start, end, date_notes = date_range_from_parameters(
            request.parameters,
            use_complete_month_cutoff=request.safety_settings.enforce_complete_month_cutoff,
        )

        created_count, applied_filters, warnings = _sum_metric(
            db,
            request,
            scope=scope,
            ticket_type=ticket_type,
            metric="created_count",
            start=start,
            end=end,
        )
        resolved_count, _, resolved_warnings = _sum_metric(
            db,
            request,
            scope=scope,
            ticket_type=ticket_type,
            metric="resolved_closed_count",
            start=start,
            end=end,
        )
        canceled_count, _, canceled_warnings = _sum_metric(
            db,
            request,
            scope=scope,
            ticket_type=ticket_type,
            metric="canceled_closed_incomplete_count",
            start=start,
            end=end,
        )
        incident_count, _, incident_warnings = _sum_metric(
            db,
            request,
            scope=scope,
            ticket_type="incident",
            metric="created_count",
            start=start,
            end=end,
        )
        sc_task_count, _, sc_task_warnings = _sum_metric(
            db,
            request,
            scope=scope,
            ticket_type="sc_task",
            metric="created_count",
            start=start,
            end=end,
        )
        open_backlog = 0
        for model in _models_for_scope(scope):
            statement = select(func.count()).where(ticket_open_condition(model))
            statement, _, model_warnings = _apply_common_filters(
                statement,
                model,
                db,
                request,
                ticket_type=ticket_type,
            )
            statement = apply_datetime_range(statement, model.created_at, start, end)
            open_backlog += int(db.execute(statement).scalar_one() or 0)
            warnings.extend(model_warnings)

        warnings.extend(
            resolved_warnings + canceled_warnings + incident_warnings + sc_task_warnings
        )
        rows = [
            {"metric": "Created count", "value": created_count},
            {"metric": "Resolved/Closed count", "value": resolved_count},
            {"metric": "Canceled/Closed Incomplete count", "value": canceled_count},
            {"metric": "Open backlog count", "value": open_backlog},
            {"metric": "Incident count", "value": incident_count},
            {"metric": "SC Task count", "value": sc_task_count},
        ]

        return tool_response(
            metadata=self.metadata,
            status="success",
            title="Ticket Volume Summary",
            description="Aggregate ticket volume using governed ticket rules.",
            columns=_ticket_columns(),
            rows=rows,
            totals={"date_range_used": _date_range_label(start, end)},
            applied_filters={**applied_filters, "date_range_used": _date_range_label(start, end)},
            data_notes=[*TICKET_DATA_NOTES, *date_notes],
            warnings=sorted(set(warnings)),
        )


class TicketTrendSummaryTool:
    metadata = ToolMetadata(
        tool_name="get_ticket_trend_summary",
        domain="tickets",
        display_name="Ticket Trend Summary",
        description=(
            "Returns monthly created, resolved/closed, and canceled/closed incomplete counts."
        ),
        allowed_metrics=TICKET_METRICS,
        max_rows=500,
        data_safety_level="aggregate",
    )

    def execute(self, db: Session, request: ToolExecutionRequest) -> GenAIToolExecuteResponse:
        if not request.safety_settings.allow_aggregate_ticket_data:
            raise ToolValidationError("Aggregate ticket data is disabled by GenAI safety settings.")
        grain = normalized_key(request.parameters.get("date_grain"), "month")
        if grain != "month":
            raise ToolValidationError(
                "Only monthly ticket trend summaries are supported in Phase 1D."
            )
        scope = normalize_scope(request.parameters)
        ticket_type = normalize_ticket_type(request.parameters)
        start, end, date_notes = date_range_from_parameters(
            request.parameters,
            use_complete_month_cutoff=request.safety_settings.enforce_complete_month_cutoff,
        )
        periods: dict[str, dict[str, int]] = defaultdict(
            lambda: {
                "created_count": 0,
                "resolved_closed_count": 0,
                "canceled_closed_incomplete_count": 0,
            },
        )
        warnings: list[str] = []
        applied_filters: dict[str, Any] = {"scope": scope, "ticket_type": ticket_type}

        for model in _models_for_scope(scope):
            for metric in TICKET_METRICS:
                date_expression = _metric_date_expression(model, metric)
                period_expr = month_period_expression(date_expression)
                statement = (
                    select(period_expr.label("period"), func.count().label("value"))
                    .where(_metric_condition(model, metric), date_expression.is_not(None))
                    .group_by(period_expr)
                )
                statement, model_applied, model_warnings = _apply_common_filters(
                    statement,
                    model,
                    db,
                    request,
                    ticket_type=ticket_type,
                )
                statement = apply_datetime_range(statement, date_expression, start, end)
                applied_filters.update(model_applied)
                warnings.extend(model_warnings)
                for row in db.execute(statement):
                    periods[str(row.period)][metric] += int(row.value or 0)

        rows = [{"period": period, **values} for period, values in sorted(periods.items())]
        max_rows = min(request.safety_settings.max_chart_data_points, self.metadata.max_rows)
        rows, truncated = cap_rows(rows, max_rows)
        return tool_response(
            metadata=self.metadata,
            status="success",
            title="Ticket Trend Summary",
            description="Monthly governed ticket trend.",
            columns=[
                GenAIToolColumn(key="period", label="Period"),
                GenAIToolColumn(key="created_count", label="Created", type="number"),
                GenAIToolColumn(
                    key="resolved_closed_count",
                    label="Resolved/Closed",
                    type="number",
                ),
                GenAIToolColumn(
                    key="canceled_closed_incomplete_count",
                    label="Canceled/Closed Incomplete",
                    type="number",
                ),
            ],
            rows=rows,
            applied_filters={**applied_filters, "date_range_used": _date_range_label(start, end)},
            data_notes=[*TICKET_DATA_NOTES, *date_notes],
            warnings=sorted(set(warnings)),
            truncated=truncated,
        )


class TicketDistributionTool:
    metadata = ToolMetadata(
        tool_name="get_ticket_distribution",
        domain="tickets",
        display_name="Ticket Distribution",
        description="Returns aggregate ticket counts by an approved dimension.",
        allowed_dimensions=TICKET_DISTRIBUTION_DIMENSIONS,
        allowed_metrics=TICKET_METRICS,
        max_rows=100,
        data_safety_level="aggregate",
    )

    def execute(self, db: Session, request: ToolExecutionRequest) -> GenAIToolExecuteResponse:
        if not request.safety_settings.allow_aggregate_ticket_data:
            raise ToolValidationError("Aggregate ticket data is disabled by GenAI safety settings.")
        scope = normalize_scope(request.parameters)
        ticket_type = normalize_ticket_type(request.parameters)
        dimension = ensure_allowed(
            request.parameters.get("dimension"),
            self.metadata.allowed_dimensions,
            "Dimension",
        )
        metric = ensure_allowed(
            request.parameters.get("metric") or "created_count",
            self.metadata.allowed_metrics,
            "Metric",
        )
        start, end, date_notes = date_range_from_parameters(
            request.parameters,
            use_complete_month_cutoff=request.safety_settings.enforce_complete_month_cutoff,
        )
        max_rows = max_rows_from_safety(
            request.parameters,
            request.safety_settings,
            default=10,
            tool_max_rows=self.metadata.max_rows,
        )
        totals: dict[str, int] = defaultdict(int)
        applied_filters: dict[str, Any] = {"scope": scope, "ticket_type": ticket_type}
        warnings: list[str] = []

        for model in _models_for_scope(scope):
            model_rows, model_applied, model_warnings = _distribution_rows_for_model(
                db,
                model,
                request,
                ticket_type=ticket_type,
                dimension=dimension,
                metric=metric,
                start=start,
                end=end,
            )
            applied_filters.update(model_applied)
            warnings.extend(model_warnings)
            for dimension_value, value in model_rows:
                totals[dimension_value] += value

        rows = [
            {"dimension": key, metric: value}
            for key, value in sorted(totals.items(), key=lambda item: (-item[1], item[0]))[
                : max_rows + 1
            ]
        ]
        rows, truncated = cap_rows(rows, max_rows)
        return tool_response(
            metadata=self.metadata,
            status="success",
            title="Ticket Distribution",
            description="Aggregate ticket counts by approved dimension.",
            columns=[
                GenAIToolColumn(key="dimension", label=dimension.replace("_", " ").title()),
                GenAIToolColumn(key=metric, label=metric.replace("_", " ").title(), type="number"),
            ],
            rows=rows,
            applied_filters={
                **applied_filters,
                "dimension": dimension,
                "metric": metric,
                "date_range_used": _date_range_label(start, end),
            },
            data_notes=[*TICKET_DATA_NOTES, *date_notes],
            warnings=sorted(set(warnings)),
            truncated=truncated,
        )


class TopApplicationsByTicketVolumeTool:
    metadata = ToolMetadata(
        tool_name="get_top_applications_by_ticket_volume",
        domain="tickets",
        display_name="Top Applications by Ticket Volume",
        description="Returns top parent applications by governed ticket volume.",
        allowed_dimensions=("parent_business_application",),
        allowed_metrics=TICKET_METRICS,
        max_rows=100,
        data_safety_level="aggregate",
    )

    def execute(self, db: Session, request: ToolExecutionRequest) -> GenAIToolExecuteResponse:
        if not request.safety_settings.allow_aggregate_ticket_data:
            raise ToolValidationError("Aggregate ticket data is disabled by GenAI safety settings.")
        scope = normalize_scope(request.parameters)
        ticket_type = normalize_ticket_type(request.parameters)
        metric = ensure_allowed(
            request.parameters.get("metric") or "created_count",
            self.metadata.allowed_metrics,
            "Metric",
        )
        start, end, date_notes = date_range_from_parameters(
            request.parameters,
            use_complete_month_cutoff=request.safety_settings.enforce_complete_month_cutoff,
        )
        max_rows = max_rows_from_safety(
            request.parameters,
            request.safety_settings,
            default=10,
            tool_max_rows=self.metadata.max_rows,
        )
        totals: dict[str, int] = defaultdict(int)
        applied_filters: dict[str, Any] = {"scope": scope, "ticket_type": ticket_type}
        warnings: list[str] = []

        for model in _models_for_scope(scope):
            model_rows, model_applied, model_warnings = _distribution_rows_for_model(
                db,
                model,
                request,
                ticket_type=ticket_type,
                dimension="parent_business_application",
                metric=metric,
                start=start,
                end=end,
            )
            applied_filters.update(model_applied)
            warnings.extend(model_warnings)
            for application, value in model_rows:
                totals[application] += value

        total_volume = sum(totals.values())
        sorted_rows = sorted(totals.items(), key=lambda item: (-item[1], item[0]))[: max_rows + 1]
        rows = [
            {
                "application": application,
                metric: value,
                "percent_of_total": numeric_percentage(value, total_volume),
                "ticket_type": ticket_type,
                "scope": scope,
                "date_range_used": _date_range_label(start, end),
            }
            for application, value in sorted_rows
        ]
        rows, truncated = cap_rows(rows, max_rows)
        return tool_response(
            metadata=self.metadata,
            status="success",
            title="Top Applications by Ticket Volume",
            description="Top Parent Business Applications by selected aggregate ticket metric.",
            columns=[
                GenAIToolColumn(key="application", label="Application"),
                GenAIToolColumn(key=metric, label=metric.replace("_", " ").title(), type="number"),
                GenAIToolColumn(key="percent_of_total", label="Percent of Total", type="number"),
                GenAIToolColumn(key="ticket_type", label="Ticket Type"),
                GenAIToolColumn(key="scope", label="Scope"),
            ],
            rows=rows,
            applied_filters={
                **applied_filters,
                "metric": metric,
                "date_range_used": _date_range_label(start, end),
            },
            data_notes=[
                *TICKET_DATA_NOTES,
                *date_notes,
                "Application is Parent Business Application from normalized ticket fields.",
            ],
            warnings=sorted(set(warnings)),
            truncated=truncated,
        )
