from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.schemas.genai import GenAIToolColumn, GenAIToolExecuteResponse
from app.services.genai.tools.base import ToolExecutionRequest, ToolMetadata, tool_response
from app.services.genai.tools.ticket_tools import (
    TICKET_DATA_NOTES,
    _apply_common_filters,
    _date_range_label,
    _models_for_scope,
)
from app.services.genai.tools.validation import (
    ToolValidationError,
    apply_datetime_range,
    cap_rows,
    date_range_from_parameters,
    ensure_allowed,
    max_rows_from_safety,
    normalize_scope,
    normalize_ticket_type,
    numeric_percentage,
    ticket_closed_condition,
    ticket_completion_datetime_expression,
)

SLA_OLA_METRICS = ("response", "resolution", "both")
AGREEMENT_TYPES = ("sla", "ola")
SLA_OLA_DIMENSIONS = (
    "supported_by_vendor",
    "derived_vendor",
    "functional_track",
    "ams_owner",
    "functional_track_ams_owner",
    "parent_business_application",
    "assignment_group",
    "sap_non_sap",
    "architecture_type",
    "install_type",
    "priority",
)

SLA_OLA_NOTES = [
    "SLA means end-to-end business/IT service level agreement.",
    "OLA means vendor-specific operational level agreement.",
    "Adherence is calculated as adhered count divided by captured count.",
    "Missing SLA/OLA rows are excluded from the denominator.",
]

DIRECT_SLA_OLA_DIMENSIONS = {
    "supported_by_vendor": "supported_by_vendor",
    "derived_vendor": "derived_vendor",
    "functional_track": "functional_track",
    "ams_owner": "ams_owner",
    "parent_business_application": "parent_application_name",
    "assignment_group": "assignment_group",
    "sap_non_sap": "sap_non_sap",
    "architecture_type": "architecture_type",
    "install_type": "install_type",
    "priority": "priority",
}


def _breach_column_name(agreement_type: str, metric: str) -> str:
    return f"{agreement_type}_{metric}_sla_breached"


def _metric_values(metric: str) -> tuple[str, ...]:
    if metric == "both":
        return ("response", "resolution")
    return (metric,)


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
    return func.nullif(func.btrim(getattr(model, DIRECT_SLA_OLA_DIMENSIONS[dimension])), "")


def _agreement_supported(model: type[Any], agreement_type: str, metric: str) -> bool:
    return hasattr(model, _breach_column_name(agreement_type, metric))


def _summary_counts_for_model(
    db: Session,
    model: type[Any],
    request: ToolExecutionRequest,
    *,
    agreement_type: str,
    metric: str,
    ticket_type: str,
    start: datetime | None,
    end: datetime | None,
) -> tuple[dict[str, int], dict[str, Any], list[str]]:
    if not _agreement_supported(model, agreement_type, metric):
        return (
            {"closed_count": 0, "captured_count": 0, "adhered_count": 0},
            {},
            [
                f"{agreement_type.upper()} {metric} fields are not available for "
                f"{model.__tablename__}.",
            ],
        )
    completion_date = ticket_completion_datetime_expression(model)
    breach_column = getattr(model, _breach_column_name(agreement_type, metric))
    statement = select(
        func.count().filter(ticket_closed_condition(model)).label("closed_count"),
        func.count()
        .filter(ticket_closed_condition(model), breach_column.is_not(None))
        .label(
            "captured_count",
        ),
        func.count()
        .filter(ticket_closed_condition(model), breach_column.is_(False))
        .label(
            "adhered_count",
        ),
    )
    statement, applied, warnings = _apply_common_filters(
        statement,
        model,
        db,
        request,
        ticket_type=ticket_type,
    )
    statement = apply_datetime_range(statement, completion_date, start, end)
    row = db.execute(statement).one()
    return (
        {
            "closed_count": int(row.closed_count or 0),
            "captured_count": int(row.captured_count or 0),
            "adhered_count": int(row.adhered_count or 0),
        },
        applied,
        warnings,
    )


class SlaOlaSummaryTool:
    metadata = ToolMetadata(
        tool_name="get_sla_ola_summary",
        domain="sla_ola",
        display_name="SLA / OLA Summary",
        description="Returns aggregate SLA or OLA response/resolution adherence.",
        allowed_metrics=SLA_OLA_METRICS,
        max_rows=25,
        data_safety_level="aggregate",
    )

    def execute(self, db: Session, request: ToolExecutionRequest) -> GenAIToolExecuteResponse:
        if not request.safety_settings.allow_sla_ola_aggregate_data:
            raise ToolValidationError(
                "SLA/OLA aggregate data is disabled by GenAI safety settings."
            )
        agreement_type = ensure_allowed(
            request.parameters.get("agreement_type") or "ola",
            AGREEMENT_TYPES,
            "Agreement type",
        )
        metric = ensure_allowed(
            request.parameters.get("metric") or "both",
            self.metadata.allowed_metrics,
            "Metric",
        )
        scope = normalize_scope(request.parameters)
        ticket_type = normalize_ticket_type(request.parameters)
        start, end, date_notes = date_range_from_parameters(
            request.parameters,
            use_complete_month_cutoff=request.safety_settings.enforce_complete_month_cutoff,
        )

        rows: list[dict[str, Any]] = []
        applied_filters: dict[str, Any] = {
            "agreement_type": agreement_type,
            "metric": metric,
            "scope": scope,
            "ticket_type": ticket_type,
        }
        warnings: list[str] = []
        for metric_value in _metric_values(metric):
            totals = {"closed_count": 0, "captured_count": 0, "adhered_count": 0}
            for model in _models_for_scope(scope):
                counts, model_applied, model_warnings = _summary_counts_for_model(
                    db,
                    model,
                    request,
                    agreement_type=agreement_type,
                    metric=metric_value,
                    ticket_type=ticket_type,
                    start=start,
                    end=end,
                )
                for key, value in counts.items():
                    totals[key] += value
                applied_filters.update(model_applied)
                warnings.extend(model_warnings)
            rows.append(
                {
                    "agreement_type": agreement_type.upper(),
                    "metric": metric_value,
                    "closed_count": totals["closed_count"],
                    "captured_count": totals["captured_count"],
                    "adhered_count": totals["adhered_count"],
                    "adherence_percent": numeric_percentage(
                        totals["adhered_count"],
                        totals["captured_count"],
                    ),
                    "date_range_used": _date_range_label(start, end),
                },
            )

        return tool_response(
            metadata=self.metadata,
            status="success",
            title="SLA / OLA Summary",
            description="Aggregate adherence summary.",
            columns=[
                GenAIToolColumn(key="agreement_type", label="Agreement Type"),
                GenAIToolColumn(key="metric", label="Metric"),
                GenAIToolColumn(key="closed_count", label="Closed Count", type="number"),
                GenAIToolColumn(key="captured_count", label="Captured Count", type="number"),
                GenAIToolColumn(key="adhered_count", label="Adhered Count", type="number"),
                GenAIToolColumn(key="adherence_percent", label="Adherence %", type="number"),
                GenAIToolColumn(key="date_range_used", label="Date Range Used"),
            ],
            rows=rows,
            applied_filters={**applied_filters, "date_range_used": _date_range_label(start, end)},
            data_notes=[*SLA_OLA_NOTES, *TICKET_DATA_NOTES, *date_notes],
            warnings=sorted(set(warnings)),
        )


class SlaOlaByDimensionTool:
    metadata = ToolMetadata(
        tool_name="get_sla_ola_by_dimension",
        domain="sla_ola",
        display_name="SLA / OLA by Dimension",
        description="Returns SLA or OLA adherence grouped by an approved normalized dimension.",
        allowed_dimensions=SLA_OLA_DIMENSIONS,
        allowed_metrics=SLA_OLA_METRICS,
        max_rows=100,
        data_safety_level="aggregate",
    )

    def execute(self, db: Session, request: ToolExecutionRequest) -> GenAIToolExecuteResponse:
        if not request.safety_settings.allow_sla_ola_aggregate_data:
            raise ToolValidationError(
                "SLA/OLA aggregate data is disabled by GenAI safety settings."
            )
        agreement_type = ensure_allowed(
            request.parameters.get("agreement_type") or "ola",
            AGREEMENT_TYPES,
            "Agreement type",
        )
        dimension = ensure_allowed(
            request.parameters.get("dimension"),
            self.metadata.allowed_dimensions,
            "Dimension",
        )
        metric = ensure_allowed(
            request.parameters.get("metric") or "both",
            self.metadata.allowed_metrics,
            "Metric",
        )
        scope = normalize_scope(request.parameters)
        ticket_type = normalize_ticket_type(request.parameters)
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
        aggregate: dict[tuple[str, str], dict[str, int]] = defaultdict(
            lambda: {"closed_count": 0, "captured_count": 0, "adhered_count": 0},
        )
        applied_filters: dict[str, Any] = {
            "agreement_type": agreement_type,
            "dimension": dimension,
            "metric": metric,
            "scope": scope,
            "ticket_type": ticket_type,
        }
        warnings: list[str] = []

        for model in _models_for_scope(scope):
            dimension_expr = _dimension_expression(model, dimension)
            display_expr = func.coalesce(dimension_expr, "Unspecified")
            completion_date = ticket_completion_datetime_expression(model)
            for metric_value in _metric_values(metric):
                if not _agreement_supported(model, agreement_type, metric_value):
                    warnings.append(
                        f"{agreement_type.upper()} {metric_value} fields are not available "
                        f"for {model.__tablename__}.",
                    )
                    continue
                breach_column = getattr(model, _breach_column_name(agreement_type, metric_value))
                statement = (
                    select(
                        display_expr.label("dimension"),
                        func.count().filter(ticket_closed_condition(model)).label("closed_count"),
                        func.count()
                        .filter(ticket_closed_condition(model), breach_column.is_not(None))
                        .label("captured_count"),
                        func.count()
                        .filter(ticket_closed_condition(model), breach_column.is_(False))
                        .label("adhered_count"),
                    )
                    .where(dimension_expr.is_not(None))
                    .group_by(display_expr)
                )
                statement, model_applied, model_warnings = _apply_common_filters(
                    statement,
                    model,
                    db,
                    request,
                    ticket_type=ticket_type,
                )
                statement = apply_datetime_range(statement, completion_date, start, end)
                applied_filters.update(model_applied)
                warnings.extend(model_warnings)
                for row in db.execute(statement):
                    bucket = aggregate[(str(row.dimension), metric_value)]
                    bucket["closed_count"] += int(row.closed_count or 0)
                    bucket["captured_count"] += int(row.captured_count or 0)
                    bucket["adhered_count"] += int(row.adhered_count or 0)

        rows = []
        for (dimension_value, metric_value), totals in aggregate.items():
            rows.append(
                {
                    "dimension": dimension_value,
                    "agreement_type": agreement_type.upper(),
                    "metric": metric_value,
                    "closed_count": totals["closed_count"],
                    "captured_count": totals["captured_count"],
                    "adhered_count": totals["adhered_count"],
                    "adherence_percent": numeric_percentage(
                        totals["adhered_count"],
                        totals["captured_count"],
                    ),
                },
            )
        rows = sorted(
            rows,
            key=lambda row: (-(row["captured_count"] or 0), row["dimension"], row["metric"]),
        )[: max_rows + 1]
        rows, truncated = cap_rows(rows, max_rows)

        return tool_response(
            metadata=self.metadata,
            status="success",
            title="SLA / OLA by Dimension",
            description="Aggregate adherence by approved dimension.",
            columns=[
                GenAIToolColumn(key="dimension", label=dimension.replace("_", " ").title()),
                GenAIToolColumn(key="agreement_type", label="Agreement Type"),
                GenAIToolColumn(key="metric", label="Metric"),
                GenAIToolColumn(key="closed_count", label="Closed Count", type="number"),
                GenAIToolColumn(key="captured_count", label="Captured Count", type="number"),
                GenAIToolColumn(key="adhered_count", label="Adhered Count", type="number"),
                GenAIToolColumn(key="adherence_percent", label="Adherence %", type="number"),
            ],
            rows=rows,
            applied_filters={**applied_filters, "date_range_used": _date_range_label(start, end)},
            data_notes=[*SLA_OLA_NOTES, *TICKET_DATA_NOTES, *date_notes],
            warnings=sorted(set(warnings)),
            truncated=truncated,
        )
