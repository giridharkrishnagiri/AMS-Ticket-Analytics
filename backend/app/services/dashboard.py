from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, time, timedelta
from enum import StrEnum
from typing import Any
from uuid import UUID

from sqlalchemy import Float, and_, case, cast, func, or_, select
from sqlalchemy.orm import Session

from app.models import ApplicationDimension, Ticket

SECONDS_PER_DAY = 86400
SECONDS_PER_HOUR = 3600
FILTER_VALUE_LIMIT = 2000
FINAL_STATES = {"closed", "resolved", "complete", "completed", "cancelled", "canceled"}
DATE_TRUNC_GRAIN = {
    "DAILY": "day",
    "WEEKLY": "week",
    "MONTHLY": "month",
    "QUARTERLY": "quarter",
    "YEARLY": "year",
}


class TimeGrain(StrEnum):
    DAILY = "DAILY"
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"
    QUARTERLY = "QUARTERLY"
    YEARLY = "YEARLY"


class DateFilterBasis(StrEnum):
    CREATED = "CREATED"
    RESOLVED_OR_CLOSED = "RESOLVED_OR_CLOSED"
    CLOSED = "CLOSED"


@dataclass(frozen=True)
class DashboardFilters:
    project_id: UUID
    ticket_type: list[str]
    priority: list[str]
    state: list[str]
    assignment_group: list[str]
    application: list[str]
    customer_name: list[str]
    tower_name: list[str]
    cluster_name: list[str]
    application_group_name: list[str]
    application_name: list[str]
    response_sla_name: list[str]
    resolution_sla_name: list[str]
    start_date: date | None = None
    end_date: date | None = None
    month_key: str | None = None
    time_grain: TimeGrain = TimeGrain.MONTHLY
    date_filter_basis: DateFilterBasis = DateFilterBasis.CREATED


@dataclass(frozen=True)
class Period:
    start: datetime
    next_start: datetime

    @property
    def end(self) -> datetime:
        return self.next_start - timedelta(microseconds=1)

    @property
    def label(self) -> str:
        if self.start.month == 1 and self.next_start.year > self.start.year:
            return f"{self.start:%Y}"
        if self.start.day == 1 and self.next_start.month in {4, 7, 10, 1}:
            quarter = ((self.start.month - 1) // 3) + 1
            if self.next_start.month - self.start.month in {3, -9}:
                return f"{self.start.year} Q{quarter}"
        if self.start.day == 1 and self.next_start.day == 1:
            return f"{self.start:%Y-%m}"
        return f"{self.start:%Y-%m-%d}"


def normalize_ticket_type(ticket_type: str | None) -> str:
    return (ticket_type or "").strip().upper()


def to_utc_datetime(value: date | datetime) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    return datetime.combine(value, time.min, tzinfo=UTC)


def month_key_bounds(month_key: str) -> tuple[date, date]:
    year_text, month_text = month_key.split("-", maxsplit=1)
    year = int(year_text)
    month = int(month_text)
    start = date(year, month, 1)
    if month == 12:
        return start, date(year + 1, 1, 1)
    return start, date(year, month + 1, 1)


def resolve_date_bounds(filters: DashboardFilters) -> tuple[datetime | None, datetime | None]:
    if filters.month_key:
        start, exclusive_end = month_key_bounds(filters.month_key)
        return to_utc_datetime(start), to_utc_datetime(exclusive_end)

    start = to_utc_datetime(filters.start_date) if filters.start_date else None
    exclusive_end = (
        to_utc_datetime(filters.end_date + timedelta(days=1)) if filters.end_date else None
    )
    return start, exclusive_end


def normalize_period_start(value: datetime, grain: TimeGrain) -> datetime:
    value = value if value.tzinfo else value.replace(tzinfo=UTC)
    if grain == TimeGrain.DAILY:
        return datetime(value.year, value.month, value.day, tzinfo=UTC)
    if grain == TimeGrain.WEEKLY:
        start_date = value.date() - timedelta(days=value.weekday())
        return to_utc_datetime(start_date)
    if grain == TimeGrain.MONTHLY:
        return datetime(value.year, value.month, 1, tzinfo=UTC)
    if grain == TimeGrain.QUARTERLY:
        quarter_month = ((value.month - 1) // 3) * 3 + 1
        return datetime(value.year, quarter_month, 1, tzinfo=UTC)
    return datetime(value.year, 1, 1, tzinfo=UTC)


def add_period(value: datetime, grain: TimeGrain) -> datetime:
    if grain == TimeGrain.DAILY:
        return value + timedelta(days=1)
    if grain == TimeGrain.WEEKLY:
        return value + timedelta(weeks=1)
    if grain == TimeGrain.MONTHLY:
        if value.month == 12:
            return datetime(value.year + 1, 1, 1, tzinfo=UTC)
        return datetime(value.year, value.month + 1, 1, tzinfo=UTC)
    if grain == TimeGrain.QUARTERLY:
        month = value.month + 3
        year = value.year
        if month > 12:
            month -= 12
            year += 1
        return datetime(year, month, 1, tzinfo=UTC)
    return datetime(value.year + 1, 1, 1, tzinfo=UTC)


def period_key(value: datetime | None, grain: TimeGrain) -> datetime | None:
    if value is None:
        return None
    return normalize_period_start(value, grain)


def dashboard_base_conditions(filters: DashboardFilters) -> list[Any]:
    conditions: list[Any] = [Ticket.project_id == filters.project_id]
    if filters.ticket_type:
        conditions.append(Ticket.ticket_type.in_([value.upper() for value in filters.ticket_type]))
    if filters.priority:
        conditions.append(Ticket.priority.in_(filters.priority))
    if filters.state:
        conditions.append(Ticket.state.in_(filters.state))
    if filters.assignment_group:
        conditions.append(Ticket.assignment_group.in_(filters.assignment_group))
    if filters.application:
        conditions.append(Ticket.application.in_(filters.application))
    if filters.customer_name:
        conditions.append(ApplicationDimension.customer_name.in_(filters.customer_name))
    if filters.tower_name:
        conditions.append(ApplicationDimension.tower_name.in_(filters.tower_name))
    if filters.cluster_name:
        conditions.append(ApplicationDimension.cluster_name.in_(filters.cluster_name))
    if filters.application_group_name:
        conditions.append(
            ApplicationDimension.application_group_name.in_(filters.application_group_name)
        )
    if filters.application_name:
        conditions.append(ApplicationDimension.application_name.in_(filters.application_name))
    if filters.response_sla_name:
        conditions.append(Ticket.response_sla_name.in_(filters.response_sla_name))
    if filters.resolution_sla_name:
        conditions.append(Ticket.resolution_sla_name.in_(filters.resolution_sla_name))
    return conditions


def has_dimension_filters(filters: DashboardFilters) -> bool:
    return any(
        [
            filters.customer_name,
            filters.tower_name,
            filters.cluster_name,
            filters.application_group_name,
            filters.application_name,
        ]
    )


def dashboard_select(
    statement: Any,
    filters: DashboardFilters,
    *,
    join_dimensions: bool = False,
) -> Any:
    statement = statement.select_from(Ticket)
    if join_dimensions or has_dimension_filters(filters):
        statement = statement.outerjoin(Ticket.application_dimension)
    return statement.where(*dashboard_base_conditions(filters))


def apply_date_bounds(statement: Any, filters: DashboardFilters, date_expression: Any) -> Any:
    start_bound, exclusive_end_bound = resolve_date_bounds(filters)
    if start_bound is not None:
        statement = statement.where(date_expression >= start_bound)
    if exclusive_end_bound is not None:
        statement = statement.where(date_expression < exclusive_end_bound)
    return statement


def effective_completion_expression() -> Any:
    return case(
        (Ticket.ticket_type == "INCIDENT", Ticket.resolved_at),
        (Ticket.ticket_type == "SERVICE_CATALOG_TASK", Ticket.closed_at),
        else_=func.coalesce(Ticket.resolved_at, Ticket.closed_at),
    )


def date_filter_basis_expression(filters: DashboardFilters) -> Any:
    if filters.date_filter_basis == DateFilterBasis.RESOLVED_OR_CLOSED:
        return effective_completion_expression()
    if filters.date_filter_basis == DateFilterBasis.CLOSED:
        return Ticket.closed_at
    return Ticket.created_at


def period_start_expression(date_expression: Any, grain: TimeGrain) -> Any:
    return func.date_trunc(DATE_TRUNC_GRAIN[grain.value], date_expression)


def query_date_bounds(
    db: Session,
    filters: DashboardFilters,
    date_expressions: list[Any],
) -> tuple[datetime | None, datetime | None]:
    minimums: list[datetime] = []
    maximums: list[datetime] = []
    for date_expression in date_expressions:
        statement = select(
            func.min(date_expression).label("minimum"),
            func.max(date_expression).label("maximum"),
        )
        statement = dashboard_select(statement, filters)
        row = db.execute(statement).mappings().one()
        if row["minimum"] is not None:
            minimums.append(row["minimum"])
        if row["maximum"] is not None:
            maximums.append(row["maximum"])
    return (min(minimums) if minimums else None, max(maximums) if maximums else None)


def build_periods_for_dates(
    db: Session,
    filters: DashboardFilters,
    date_expressions: list[Any],
) -> list[Period]:
    start_bound, exclusive_end_bound = resolve_date_bounds(filters)
    if start_bound is None or exclusive_end_bound is None:
        minimum_date, maximum_date = query_date_bounds(db, filters, date_expressions)
        if start_bound is None:
            start_bound = minimum_date
        if exclusive_end_bound is None and maximum_date is not None:
            exclusive_end_bound = add_period(
                normalize_period_start(maximum_date, filters.time_grain),
                filters.time_grain,
            )

    if start_bound is None or exclusive_end_bound is None:
        return []

    current = normalize_period_start(start_bound, filters.time_grain)
    periods: list[Period] = []
    while current < exclusive_end_bound:
        next_start = add_period(current, filters.time_grain)
        periods.append(Period(start=current, next_start=next_start))
        current = next_start
    return periods


def period_row(period: Period) -> dict[str, Any]:
    return {
        "period_start": period.start,
        "period_end": period.end,
        "period_label": period.label,
    }


def int_count(value: Any) -> int:
    return int(value or 0)


def float_or_none(value: Any) -> float | None:
    return float(value) if value is not None else None


def percentage(numerator: int, denominator: int) -> float | None:
    return numerator / denominator * 100 if denominator else None


def incident_only_filters(filters: DashboardFilters) -> DashboardFilters:
    return replace(filters, ticket_type=["INCIDENT"])


def aggregate_by_period(
    db: Session,
    filters: DashboardFilters,
    date_expression: Any,
    columns: list[Any],
    extra_conditions: list[Any] | None = None,
) -> dict[datetime, dict[str, Any]]:
    period_expression = period_start_expression(date_expression, filters.time_grain).label(
        "period_start"
    )
    statement = select(period_expression, *columns)
    statement = dashboard_select(statement, filters)
    statement = apply_date_bounds(statement, filters, date_expression)
    statement = statement.where(date_expression.is_not(None))
    if extra_conditions:
        statement = statement.where(*extra_conditions)
    statement = statement.group_by(period_expression).order_by(period_expression)

    rows_by_period: dict[datetime, dict[str, Any]] = {}
    for row in db.execute(statement).mappings().all():
        key = period_key(row["period_start"], filters.time_grain)
        if key is not None:
            rows_by_period[key] = dict(row)
    return rows_by_period


def created_resolved_open_trend(db: Session, filters: DashboardFilters) -> list[dict[str, Any]]:
    completion_expression = effective_completion_expression()
    periods = build_periods_for_dates(db, filters, [Ticket.created_at, completion_expression])
    if not periods:
        return []

    created_rows = aggregate_by_period(
        db,
        filters,
        Ticket.created_at,
        [func.count(Ticket.id).label("created_count")],
    )
    resolved_rows = aggregate_by_period(
        db,
        filters,
        completion_expression,
        [func.count(Ticket.id).label("resolved_count")],
    )

    state_expression = func.lower(func.coalesce(Ticket.state, ""))
    rows: list[dict[str, Any]] = []
    for period in periods:
        open_condition = or_(
            completion_expression >= period.next_start,
            and_(
                completion_expression.is_(None),
                ~state_expression.in_(FINAL_STATES),
            ),
        )
        open_statement = select(func.count(Ticket.id).label("open_end_count"))
        open_statement = dashboard_select(open_statement, filters)
        open_statement = open_statement.where(
            Ticket.created_at.is_not(None),
            Ticket.created_at < period.next_start,
            open_condition,
        )
        created_row = created_rows.get(period.start, {})
        resolved_row = resolved_rows.get(period.start, {})
        rows.append(
            {
                **period_row(period),
                "created_count": int_count(created_row.get("created_count")),
                "resolved_count": int_count(resolved_row.get("resolved_count")),
                "open_end_count": int_count(db.scalar(open_statement)),
            }
        )
    return rows


def mttr_trend(db: Session, filters: DashboardFilters) -> list[dict[str, Any]]:
    completion_expression = effective_completion_expression()
    periods = build_periods_for_dates(db, filters, [completion_expression])
    if not periods:
        return []

    actual_days_expression = (
        func.extract("epoch", completion_expression - Ticket.created_at) / SECONDS_PER_DAY
    )
    business_days_expression = cast(Ticket.business_duration_seconds, Float) / SECONDS_PER_DAY
    rows_by_period = aggregate_by_period(
        db,
        filters,
        completion_expression,
        [
            func.count(Ticket.id).label("completed_ticket_count"),
            func.avg(actual_days_expression).label("mttr_actual_days"),
            func.avg(business_days_expression)
            .filter(Ticket.business_duration_seconds >= 0)
            .label("mttr_business_days"),
        ],
        [
            Ticket.created_at.is_not(None),
            completion_expression.is_not(None),
            completion_expression >= Ticket.created_at,
        ],
    )

    return [
        {
            **period_row(period),
            "completed_ticket_count": int_count(
                rows_by_period.get(period.start, {}).get("completed_ticket_count")
            ),
            "mttr_actual_days": float_or_none(
                rows_by_period.get(period.start, {}).get("mttr_actual_days")
            ),
            "mttr_business_days": float_or_none(
                rows_by_period.get(period.start, {}).get("mttr_business_days")
            ),
        }
        for period in periods
    ]


def sla_trend(db: Session, filters: DashboardFilters) -> list[dict[str, Any]]:
    periods = build_periods_for_dates(db, filters, [Ticket.created_at])
    if not periods:
        return []

    rows_by_period = aggregate_by_period(
        db,
        filters,
        Ticket.created_at,
        [
            func.count(Ticket.id).filter(Ticket.sla_breached.is_not(None)).label("known_count"),
            func.count(Ticket.id).filter(Ticket.sla_breached.is_(False)).label("met_count"),
            func.count(Ticket.id).filter(Ticket.sla_breached.is_(True)).label("breached_count"),
            func.count(Ticket.id).filter(Ticket.sla_breached.is_(None)).label("unknown_count"),
        ],
    )

    rows: list[dict[str, Any]] = []
    for period in periods:
        period_values = rows_by_period.get(period.start, {})
        known_count = int_count(period_values.get("known_count"))
        met_count = int_count(period_values.get("met_count"))
        breached_count = int_count(period_values.get("breached_count"))
        rows.append(
            {
                **period_row(period),
                "total_tickets_with_sla": known_count,
                "sla_met_count": met_count,
                "sla_breached_count": breached_count,
                "sla_unknown_count": int_count(period_values.get("unknown_count")),
                "sla_met_percentage": (met_count / known_count * 100) if known_count else None,
                "sla_breached_percentage": (
                    breached_count / known_count * 100 if known_count else None
                ),
            }
        )
    return rows


def incident_sla_trend(db: Session, filters: DashboardFilters) -> list[dict[str, Any]]:
    filters = incident_only_filters(filters)
    periods = build_periods_for_dates(db, filters, [Ticket.created_at])
    if not periods:
        return []

    response_avg_seconds = func.avg(
        cast(Ticket.response_sla_business_elapsed_seconds, Float)
    ).filter(Ticket.response_sla_business_elapsed_seconds >= 0)
    resolution_avg_seconds = func.avg(
        cast(Ticket.resolution_sla_business_elapsed_seconds, Float)
    ).filter(Ticket.resolution_sla_business_elapsed_seconds >= 0)
    rows_by_period = aggregate_by_period(
        db,
        filters,
        Ticket.created_at,
        [
            func.count(Ticket.id).label("incident_count"),
            func.count(Ticket.id)
            .filter(Ticket.response_sla_breached.is_not(None))
            .label("response_applicable_count"),
            func.count(Ticket.id)
            .filter(Ticket.response_sla_breached.is_(False))
            .label("response_met_count"),
            func.count(Ticket.id)
            .filter(Ticket.response_sla_breached.is_(True))
            .label("response_breached_count"),
            response_avg_seconds.label("response_avg_seconds"),
            resolution_avg_seconds.label("resolution_avg_seconds"),
            func.count(Ticket.id)
            .filter(Ticket.resolution_sla_breached.is_not(None))
            .label("resolution_applicable_count"),
            func.count(Ticket.id)
            .filter(Ticket.resolution_sla_breached.is_(False))
            .label("resolution_met_count"),
            func.count(Ticket.id)
            .filter(Ticket.resolution_sla_breached.is_(True))
            .label("resolution_breached_count"),
        ],
    )

    rows: list[dict[str, Any]] = []
    for period in periods:
        period_values = rows_by_period.get(period.start, {})
        response_applicable = int_count(period_values.get("response_applicable_count"))
        response_met = int_count(period_values.get("response_met_count"))
        response_breached = int_count(period_values.get("response_breached_count"))
        response_seconds = float_or_none(period_values.get("response_avg_seconds"))
        resolution_applicable = int_count(period_values.get("resolution_applicable_count"))
        resolution_met = int_count(period_values.get("resolution_met_count"))
        resolution_breached = int_count(period_values.get("resolution_breached_count"))
        resolution_seconds = float_or_none(period_values.get("resolution_avg_seconds"))
        rows.append(
            {
                **period_row(period),
                "period": period.label,
                "incident_count": int_count(period_values.get("incident_count")),
                "response_sla_applicable_count": response_applicable,
                "response_sla_met_count": response_met,
                "response_sla_breached_count": response_breached,
                "response_sla_adherence_pct": percentage(response_met, response_applicable),
                "response_sla_breach_pct": percentage(response_breached, response_applicable),
                "response_sla_avg_business_elapsed_seconds": response_seconds,
                "response_sla_avg_business_elapsed_hours": (
                    response_seconds / SECONDS_PER_HOUR if response_seconds is not None else None
                ),
                "resolution_sla_applicable_count": resolution_applicable,
                "resolution_sla_met_count": resolution_met,
                "resolution_sla_breached_count": resolution_breached,
                "resolution_sla_adherence_pct": percentage(
                    resolution_met,
                    resolution_applicable,
                ),
                "resolution_sla_breach_pct": percentage(
                    resolution_breached,
                    resolution_applicable,
                ),
                "resolution_sla_avg_business_elapsed_seconds": resolution_seconds,
                "resolution_sla_avg_business_elapsed_hours": (
                    resolution_seconds / SECONDS_PER_HOUR
                    if resolution_seconds is not None
                    else None
                ),
            }
        )
    return rows


def incident_sla_summary(db: Session, filters: DashboardFilters) -> dict[str, Any]:
    filters = incident_only_filters(filters)
    response_avg_hours = (
        func.avg(cast(Ticket.response_sla_business_elapsed_seconds, Float))
        .filter(Ticket.response_sla_business_elapsed_seconds >= 0)
        / SECONDS_PER_HOUR
    )
    resolution_avg_hours = (
        func.avg(cast(Ticket.resolution_sla_business_elapsed_seconds, Float))
        .filter(Ticket.resolution_sla_business_elapsed_seconds >= 0)
        / SECONDS_PER_HOUR
    )
    response_name = func.lower(func.coalesce(Ticket.response_sla_name, ""))
    resolution_name = func.lower(func.coalesce(Ticket.resolution_sla_name, ""))
    statement = select(
        func.count(Ticket.id).label("incident_count"),
        func.count(Ticket.id)
        .filter(Ticket.response_sla_breached.is_not(None))
        .label("response_applicable_count"),
        func.count(Ticket.id)
        .filter(Ticket.response_sla_breached.is_(False))
        .label("response_met_count"),
        func.count(Ticket.id)
        .filter(Ticket.response_sla_breached.is_(True))
        .label("response_breached_count"),
        response_avg_hours.label("response_avg_hours"),
        func.count(Ticket.id)
        .filter(Ticket.resolution_sla_breached.is_not(None))
        .label("resolution_applicable_count"),
        func.count(Ticket.id)
        .filter(Ticket.resolution_sla_breached.is_(False))
        .label("resolution_met_count"),
        func.count(Ticket.id)
        .filter(Ticket.resolution_sla_breached.is_(True))
        .label("resolution_breached_count"),
        resolution_avg_hours.label("resolution_avg_hours"),
        func.count(Ticket.id)
        .filter(response_name.like("%accenture%"))
        .label("response_accenture_count"),
        func.count(Ticket.id).filter(response_name.like("%default%")).label("response_default_count"),
        func.count(Ticket.id)
        .filter(resolution_name.like("%accenture%"))
        .label("resolution_accenture_count"),
        func.count(Ticket.id)
        .filter(resolution_name.like("%default%"))
        .label("resolution_default_count"),
    )
    statement = dashboard_select(statement, filters)
    statement = apply_date_bounds(statement, filters, Ticket.created_at)
    row = db.execute(statement).mappings().one()
    response_applicable = int_count(row["response_applicable_count"])
    response_met = int_count(row["response_met_count"])
    response_breached = int_count(row["response_breached_count"])
    resolution_applicable = int_count(row["resolution_applicable_count"])
    resolution_met = int_count(row["resolution_met_count"])
    resolution_breached = int_count(row["resolution_breached_count"])

    return {
        "incident_count": int_count(row["incident_count"]),
        "response_sla_applicable_count": response_applicable,
        "response_sla_met_count": response_met,
        "response_sla_breached_count": response_breached,
        "response_sla_adherence_pct": percentage(response_met, response_applicable),
        "response_sla_breach_pct": percentage(response_breached, response_applicable),
        "response_sla_avg_business_elapsed_hours": float_or_none(row["response_avg_hours"]),
        "resolution_sla_applicable_count": resolution_applicable,
        "resolution_sla_met_count": resolution_met,
        "resolution_sla_breached_count": resolution_breached,
        "resolution_sla_adherence_pct": percentage(resolution_met, resolution_applicable),
        "resolution_sla_breach_pct": percentage(resolution_breached, resolution_applicable),
        "resolution_sla_avg_business_elapsed_hours": float_or_none(row["resolution_avg_hours"]),
        "response_accenture_count": int_count(row["response_accenture_count"]),
        "response_default_count": int_count(row["response_default_count"]),
        "resolution_accenture_count": int_count(row["resolution_accenture_count"]),
        "resolution_default_count": int_count(row["resolution_default_count"]),
    }


def sla_name_breakdown_rows(
    db: Session,
    filters: DashboardFilters,
    *,
    name_column: Any,
    breached_column: Any,
    elapsed_seconds_column: Any,
) -> list[dict[str, Any]]:
    filters = incident_only_filters(filters)
    avg_hours = (
        func.avg(cast(elapsed_seconds_column, Float)).filter(elapsed_seconds_column >= 0)
        / SECONDS_PER_HOUR
    )
    statement = select(
        name_column.label("sla_name"),
        func.count(Ticket.id).label("ticket_count"),
        func.count(Ticket.id).filter(breached_column.is_(False)).label("met_count"),
        func.count(Ticket.id).filter(breached_column.is_(True)).label("breached_count"),
        avg_hours.label("avg_business_elapsed_hours"),
    )
    statement = dashboard_select(statement, filters)
    statement = apply_date_bounds(statement, filters, Ticket.created_at)
    statement = statement.where(name_column.is_not(None), breached_column.is_not(None))
    statement = statement.group_by(name_column).order_by(func.count(Ticket.id).desc(), name_column)
    rows: list[dict[str, Any]] = []
    for row in db.execute(statement).mappings().all():
        ticket_count = int_count(row["ticket_count"])
        met_count = int_count(row["met_count"])
        breached_count = int_count(row["breached_count"])
        rows.append(
            {
                "sla_name": str(row["sla_name"]),
                "ticket_count": ticket_count,
                "met_count": met_count,
                "breached_count": breached_count,
                "adherence_pct": percentage(met_count, ticket_count),
                "breach_pct": percentage(breached_count, ticket_count),
                "avg_business_elapsed_hours": float_or_none(row["avg_business_elapsed_hours"]),
            }
        )
    return rows


def incident_sla_name_breakdown(
    db: Session,
    filters: DashboardFilters,
    name_type: str,
) -> dict[str, list[dict[str, Any]]]:
    normalized_name_type = name_type.strip().upper()
    include_response = normalized_name_type in {"RESPONSE", "BOTH"}
    include_resolution = normalized_name_type in {"RESOLUTION", "BOTH"}
    return {
        "response_sla_names": (
            sla_name_breakdown_rows(
                db,
                filters,
                name_column=Ticket.response_sla_name,
                breached_column=Ticket.response_sla_breached,
                elapsed_seconds_column=Ticket.response_sla_business_elapsed_seconds,
            )
            if include_response
            else []
        ),
        "resolution_sla_names": (
            sla_name_breakdown_rows(
                db,
                filters,
                name_column=Ticket.resolution_sla_name,
                breached_column=Ticket.resolution_sla_breached,
                elapsed_seconds_column=Ticket.resolution_sla_business_elapsed_seconds,
            )
            if include_resolution
            else []
        ),
    }


def reopen_trend(db: Session, filters: DashboardFilters) -> list[dict[str, Any]]:
    periods = build_periods_for_dates(db, filters, [Ticket.created_at])
    if not periods:
        return []

    reopen_value = func.coalesce(Ticket.reopen_count, 0)
    rows_by_period = aggregate_by_period(
        db,
        filters,
        Ticket.created_at,
        [
            func.count(Ticket.id).label("total_tickets"),
            func.count(Ticket.id).filter(Ticket.reopen_count > 0).label("reopened_ticket_count"),
            func.coalesce(func.sum(reopen_value), 0).label("total_reopen_count"),
            func.avg(cast(reopen_value, Float)).label("average_reopen_count"),
        ],
    )

    return [
        {
            **period_row(period),
            "total_tickets": int_count(rows_by_period.get(period.start, {}).get("total_tickets")),
            "reopened_ticket_count": int_count(
                rows_by_period.get(period.start, {}).get("reopened_ticket_count")
            ),
            "total_reopen_count": int_count(
                rows_by_period.get(period.start, {}).get("total_reopen_count")
            ),
            "average_reopen_count": float_or_none(
                rows_by_period.get(period.start, {}).get("average_reopen_count")
            ),
        }
        for period in periods
    ]


def reassignment_trend(db: Session, filters: DashboardFilters) -> list[dict[str, Any]]:
    periods = build_periods_for_dates(db, filters, [Ticket.created_at])
    if not periods:
        return []

    rows_by_period = aggregate_by_period(
        db,
        filters,
        Ticket.created_at,
        [
            func.count(Ticket.id).label("total_tickets"),
            func.count(Ticket.id)
            .filter(Ticket.reassignment_count > 2)
            .label("tickets_with_more_than_2_reassignments"),
            func.coalesce(func.sum(Ticket.reassignment_count), 0).label(
                "total_reassignment_count"
            ),
            func.avg(Ticket.reassignment_count).label("average_reassignment_count"),
        ],
    )

    return [
        {
            **period_row(period),
            "total_tickets": int_count(rows_by_period.get(period.start, {}).get("total_tickets")),
            "tickets_with_more_than_2_reassignments": int_count(
                rows_by_period.get(period.start, {}).get(
                    "tickets_with_more_than_2_reassignments"
                )
            ),
            "total_reassignment_count": int_count(
                rows_by_period.get(period.start, {}).get("total_reassignment_count")
            ),
            "average_reassignment_count": float_or_none(
                rows_by_period.get(period.start, {}).get("average_reassignment_count")
            ),
        }
        for period in periods
    ]


def creation_source_trend(db: Session, filters: DashboardFilters) -> list[dict[str, Any]]:
    periods = build_periods_for_dates(db, filters, [Ticket.created_at])
    if not periods:
        return []

    rows_by_period = aggregate_by_period(
        db,
        filters,
        Ticket.created_at,
        [
            func.count(Ticket.id)
            .filter(Ticket.is_system_created.is_(False))
            .label("user_created_count"),
            func.count(Ticket.id)
            .filter(Ticket.is_system_created.is_(True))
            .label("system_created_count"),
            func.count(Ticket.id)
            .filter(Ticket.is_system_created.is_(None))
            .label("unknown_count"),
        ],
    )

    return [
        {
            **period_row(period),
            "user_created_count": int_count(
                rows_by_period.get(period.start, {}).get("user_created_count")
            ),
            "system_created_count": int_count(
                rows_by_period.get(period.start, {}).get("system_created_count")
            ),
            "unknown_count": int_count(rows_by_period.get(period.start, {}).get("unknown_count")),
        }
        for period in periods
    ]


def technical_functional_breakdown(db: Session, filters: DashboardFilters) -> dict[str, int]:
    stored_type = func.upper(func.coalesce(Ticket.technical_functional_type, ""))
    incident_condition = Ticket.ticket_type == "INCIDENT"
    technical_condition = and_(
        incident_condition,
        or_(stored_type == "TECHNICAL", Ticket.is_technical.is_(True)),
    )
    functional_condition = and_(
        incident_condition,
        ~technical_condition,
        or_(stored_type == "FUNCTIONAL", Ticket.is_technical.is_(False)),
    )
    unknown_condition = and_(
        incident_condition,
        ~technical_condition,
        ~functional_condition,
    )

    statement = select(
        func.count(Ticket.id).filter(technical_condition).label("technical_count"),
        func.count(Ticket.id).filter(functional_condition).label("functional_count"),
        func.count(Ticket.id).filter(unknown_condition).label("unknown_count"),
        func.count(Ticket.id)
        .filter(Ticket.ticket_type != "INCIDENT")
        .label("not_applicable_count"),
    )
    statement = dashboard_select(statement, filters)
    statement = apply_date_bounds(statement, filters, date_filter_basis_expression(filters))
    row = db.execute(statement).mappings().one()
    return {
        "technical_count": int_count(row["technical_count"]),
        "functional_count": int_count(row["functional_count"]),
        "unknown_count": int_count(row["unknown_count"]),
        "not_applicable_count": int_count(row["not_applicable_count"]),
    }


def distinct_values_for_column(
    db: Session,
    filters: DashboardFilters,
    column: Any,
    *,
    join_dimensions: bool = False,
) -> list[str]:
    statement = select(column).distinct().where(column.is_not(None))
    statement = dashboard_select(statement, filters, join_dimensions=join_dimensions)
    statement = apply_date_bounds(statement, filters, date_filter_basis_expression(filters))
    statement = statement.order_by(column).limit(FILTER_VALUE_LIMIT)
    return [str(value) for value in db.scalars(statement).all() if value]


def filter_values(db: Session, filters: DashboardFilters) -> dict[str, list[str]]:
    return {
        "ticket_types": distinct_values_for_column(db, filters, Ticket.ticket_type),
        "priorities": distinct_values_for_column(db, filters, Ticket.priority),
        "states": distinct_values_for_column(db, filters, Ticket.state),
        "assignment_groups": distinct_values_for_column(db, filters, Ticket.assignment_group),
        "applications": distinct_values_for_column(db, filters, Ticket.application),
        "customers": distinct_values_for_column(
            db,
            filters,
            ApplicationDimension.customer_name,
            join_dimensions=True,
        ),
        "towers": distinct_values_for_column(
            db,
            filters,
            ApplicationDimension.tower_name,
            join_dimensions=True,
        ),
        "clusters": distinct_values_for_column(
            db,
            filters,
            ApplicationDimension.cluster_name,
            join_dimensions=True,
        ),
        "application_groups": distinct_values_for_column(
            db,
            filters,
            ApplicationDimension.application_group_name,
            join_dimensions=True,
        ),
        "application_names": distinct_values_for_column(
            db,
            filters,
            ApplicationDimension.application_name,
            join_dimensions=True,
        ),
        "month_keys": distinct_values_for_column(db, filters, Ticket.month_key),
        "response_sla_names": distinct_values_for_column(
            db,
            incident_only_filters(filters),
            Ticket.response_sla_name,
        ),
        "resolution_sla_names": distinct_values_for_column(
            db,
            incident_only_filters(filters),
            Ticket.resolution_sla_name,
        ),
    }
