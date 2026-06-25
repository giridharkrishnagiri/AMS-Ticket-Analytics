from __future__ import annotations

import calendar
import math
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, time, timedelta
from enum import StrEnum
from typing import Any
from uuid import UUID

from sqlalchemy import Float, and_, case, cast, func, literal, or_, select, union_all
from sqlalchemy.orm import Session

from app.models import (
    ApplicationInventoryItem,
    AssessmentOutOfScopeTicket,
    Client,
    IncidentSlaRow,
    Project,
    Ticket,
    TicketRawRow,
)

SECONDS_PER_DAY = 86400
SECONDS_PER_HOUR = 3600
FILTER_VALUE_LIMIT = 2000
BLANK_LABEL = "(blank)"
FINAL_STATES = {"closed", "resolved", "complete", "completed", "cancelled", "canceled"}
DATE_TRUNC_GRAIN = {
    "DAILY": "day",
    "WEEKLY": "week",
    "MONTHLY": "month",
    "QUARTERLY": "quarter",
    "YEARLY": "year",
}

DIRECT_APPLICATION_FIELDS = {
    "business_service_ci_name": ApplicationInventoryItem.business_service_ci_name,
    "parent_application_name": ApplicationInventoryItem.parent_application_name,
    "assignment_group": ApplicationInventoryItem.assignment_group,
    "assignment_group_owner": ApplicationInventoryItem.assignment_group_owner,
    "application_owner": ApplicationInventoryItem.application_owner,
    "support_lead": ApplicationInventoryItem.support_lead,
    "functional_track": ApplicationInventoryItem.functional_track,
    "ams_owner": ApplicationInventoryItem.ams_owner,
    "supported_by_vendor": ApplicationInventoryItem.supported_by_vendor,
    "sap_non_sap": ApplicationInventoryItem.sap_non_sap,
    "active_users": ApplicationInventoryItem.active_users,
    "avg_monthly_ticket_volume_6m": ApplicationInventoryItem.avg_monthly_ticket_volume_6m,
    "tickets_per_user_per_month": ApplicationInventoryItem.tickets_per_user_per_month,
}

CMDB_APPLICATION_FIELDS = {
    "app_family": ("Application family", "App Family"),
    "biz_process": ("Business process", "Biz Process"),
    "app_category": ("Application category", "App Category"),
    "org_unit_level_1": ("Organization Unit Level 1", "Org Unit Level 1"),
    "org_unit_level_2": ("Organization Unit Level 2", "Org Unit Level 2"),
    "org_unit_level_3": ("Organization Unit Level 3", "Org Unit Level 3"),
    "app_type": ("Application type", "Application Type"),
    "architecture_type": ("Architecture type", "Architecture Type"),
    "biz_capabilities": ("Business Capabilities", "Biz Capabilities"),
    "business_reason_for_maintain_applications": (
        "Business Reason for Maintain Applications",
    ),
    "business_units": ("Business Units",),
    "biz_criticality": (
        "Business criticality",
        "Biz Criticality",
        "Business Criticality",
        "Business Critical",
    ),
    "biz_owner": ("Business owner", "Biz Owner"),
    "company": ("Company",),
    "install_status": ("Install Status",),
    "install_type": ("Install type", "Install Type"),
    "lifecycle_status": ("Life Cycle Stage", "Lifecycle Status"),
    "lifecycle_stage_status": ("Life Cycle Stage Status", "Lifecycle Stage Status"),
    "operating_system": ("Operating System",),
    "sox_audited": ("SOX Audited - ever", "SOX Audited"),
    "sox_scope": ("SOX Scope",),
    "strategic": ("Strategic",),
}

APPLICATION_LIST_FIELDS = (
    "business_service_ci_name",
    "parent_application_name",
    "assignment_group",
    "sap_non_sap",
    "assignment_group_owner",
    "application_owner",
    "support_lead",
    "functional_track",
    "ams_owner",
    "supported_by_vendor",
    "active_users",
    "avg_monthly_ticket_volume_6m",
    "tickets_per_user_per_month",
    "app_family",
    "biz_process",
    "app_category",
    "org_unit_level_1",
    "org_unit_level_2",
    "org_unit_level_3",
    "app_type",
    "architecture_type",
    "biz_capabilities",
    "business_reason_for_maintain_applications",
    "business_units",
    "biz_criticality",
    "biz_owner",
    "company",
    "install_status",
    "install_type",
    "lifecycle_status",
    "operating_system",
    "sox_audited",
    "sox_scope",
    "strategic",
)

SINGLE_APPLICATION_FILTER_FIELDS = {
    "parent_application_name": "parent_application_name",
    "application_owner": "application_owner",
    "supported_by_vendor": "supported_by_vendor",
    "sap_non_sap": "sap_non_sap",
    "architecture_type": "architecture_type",
    "application_type": "app_type",
    "business_critical": "biz_criticality",
    "install_status": "install_status",
    "install_type": "install_type",
}

COMBINED_APPLICATION_FILTER_FIELDS = {
    "functional_track_ams_owner": ("functional_track", "ams_owner"),
    "assignment_group_owner": ("assignment_group", "assignment_group_owner"),
    "lifecycle_status_stage": ("lifecycle_status", "lifecycle_stage_status"),
}

APPLICATION_FILTER_CUSTOM_SORTS = {
    "business_critical": (BLANK_LABEL, "Very Critical", "Critical", "High", "Medium", "Low"),
    "install_status": (
        BLANK_LABEL,
        "In production",
        "Retire in progress",
        "Archived",
        "Pilot",
    ),
    "lifecycle_status_stage": (BLANK_LABEL, "Operational", "End of Life", "Ideation"),
}

VOLUMETRICS_SCOPES = {"in_scope", "out_of_scope", "all"}
VOLUMETRICS_TICKET_TYPES = {"all", "incident", "sc_task"}
VOLUMETRICS_TIME_GRAINS = {"monthly", "weekly"}
VOLUMETRICS_MAX_WEEKLY_PERIODS = 15
VOLUMETRICS_CREATED_PATTERN_TYPES = {
    "day_of_month",
    "day_of_week",
    "hour_weekdays",
    "hour_weekends",
}
VOLUMETRICS_DAY_TYPES = {"weekdays", "weekends"}
VOLUMETRICS_SCOPE_LABELS = {
    "all": "All",
    "in_scope": "In-scope",
    "out_of_scope": "Out-of-scope",
}
VOLUMETRICS_TICKET_TYPE_LABELS = {
    "all": "All",
    "incident": "Incidents",
    "sc_task": "SC Tasks",
}
VOLUMETRICS_TICKET_TYPE_VALUES = {
    "incident": "INCIDENT",
    "sc_task": "SERVICE_CATALOG_TASK",
}
VOLUMETRICS_CANCELLED_STATES = {
    "cancelled",
    "canceled",
    "closed cancelled",
    "closed canceled",
    "closed incomplete",
}

SINGLE_VOLUMETRICS_FILTER_FIELDS = {
    "parent_application_name": "parent_application_name",
    "application_owner": "application_owner",
    "supported_by_vendor": "supported_by_vendor",
    "sap_non_sap": "sap_non_sap",
}

COMBINED_VOLUMETRICS_FILTER_FIELDS = {
    "functional_track_ams_owner": ("functional_track", "ams_owner"),
    "assignment_group_support_lead": ("assignment_group", "support_lead"),
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
    functional_track: list[str]
    ams_owner: list[str]
    supported_by_vendor: list[str]
    support_lead: list[str]
    application_owner: list[str]
    business_service_ci_name: list[str]
    parent_application_name: list[str]
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


@dataclass(frozen=True)
class VolumetricsPeriod:
    start: datetime
    end: datetime
    label: str


def normalize_ticket_type(ticket_type: str | None) -> str:
    return (ticket_type or "").strip().upper()


def to_utc_datetime(value: date | datetime) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    return datetime.combine(value, time.min, tzinfo=UTC)


def first_day_of_month(value: datetime) -> datetime:
    normalized = to_utc_datetime(value)
    return datetime(normalized.year, normalized.month, 1, tzinfo=normalized.tzinfo)


def first_day_of_next_month(value: datetime) -> datetime:
    normalized = to_utc_datetime(value)
    if normalized.month == 12:
        return datetime(normalized.year + 1, 1, 1, tzinfo=normalized.tzinfo)
    return datetime(normalized.year, normalized.month + 1, 1, tzinfo=normalized.tzinfo)


def last_moment_of_month(value: datetime) -> datetime:
    normalized = to_utc_datetime(value)
    last_day = calendar.monthrange(normalized.year, normalized.month)[1]
    return datetime(
        normalized.year,
        normalized.month,
        last_day,
        23,
        59,
        59,
        999999,
        tzinfo=normalized.tzinfo,
    )


def last_moment_of_previous_month(value: datetime) -> datetime:
    return first_day_of_month(value) - timedelta(microseconds=1)


def complete_month_bounds(
    start_value: datetime | None,
    end_value: datetime | None,
    *,
    reference_datetime: datetime | None = None,
) -> tuple[datetime | None, datetime | None]:
    if start_value is None or end_value is None:
        return None, None

    normalized_start = to_utc_datetime(start_value)
    normalized_end = to_utc_datetime(end_value)
    start_datetime = (
        first_day_of_month(normalized_start)
        if normalized_start.day == 1
        else first_day_of_next_month(normalized_start)
    )
    end_month_last_day = calendar.monthrange(normalized_end.year, normalized_end.month)[1]
    data_end_datetime = (
        last_moment_of_month(normalized_end)
        if normalized_end.day == end_month_last_day
        else last_moment_of_previous_month(normalized_end)
    )
    latest_allowed_end = last_moment_of_previous_month(reference_datetime or datetime.now(UTC))
    end_datetime = min(data_end_datetime, latest_allowed_end)
    if start_datetime > end_datetime:
        return None, None
    return start_datetime, end_datetime


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
        conditions.append(Ticket.customer_name.in_(filters.customer_name))
    if filters.tower_name:
        conditions.append(Ticket.tower_name.in_(filters.tower_name))
    if filters.cluster_name:
        conditions.append(Ticket.cluster_name.in_(filters.cluster_name))
    if filters.application_group_name:
        conditions.append(Ticket.application_group_name.in_(filters.application_group_name))
    if filters.application_name:
        conditions.append(Ticket.application_name.in_(filters.application_name))
    if filters.response_sla_name:
        conditions.append(Ticket.response_sla_name.in_(filters.response_sla_name))
    if filters.resolution_sla_name:
        conditions.append(Ticket.resolution_sla_name.in_(filters.resolution_sla_name))
    if filters.functional_track:
        conditions.append(Ticket.functional_track.in_(filters.functional_track))
    if filters.ams_owner:
        conditions.append(Ticket.ams_owner.in_(filters.ams_owner))
    if filters.supported_by_vendor:
        conditions.append(Ticket.supported_by_vendor.in_(filters.supported_by_vendor))
    if filters.support_lead:
        conditions.append(Ticket.support_lead.in_(filters.support_lead))
    if filters.application_owner:
        conditions.append(Ticket.application_owner.in_(filters.application_owner))
    if filters.business_service_ci_name:
        conditions.append(Ticket.business_service_ci_name.in_(filters.business_service_ci_name))
    if filters.parent_application_name:
        conditions.append(Ticket.parent_application_name.in_(filters.parent_application_name))
    return conditions


def dashboard_select(
    statement: Any,
    filters: DashboardFilters,
    *,
    join_dimensions: bool = False,
) -> Any:
    statement = statement.select_from(Ticket)
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


def distinct_nonblank_count(column: Any) -> Any:
    return func.count(func.distinct(func.nullif(func.trim(column), "")))


def overview_ticket_volume_80pct_application_count(
    db: Session,
    project_id: UUID,
    completion_start: datetime | None,
    completion_end: datetime | None,
) -> int:
    if completion_start is None or completion_end is None:
        return 0

    completion_expression = effective_completion_expression()
    application_expression = func.nullif(func.trim(Ticket.business_service_ci_name), "")
    statement = (
        select(
            application_expression.label("application_name"),
            func.count(Ticket.id).label("ticket_count"),
        )
        .where(
            Ticket.project_id == project_id,
            application_expression.is_not(None),
            completion_expression.is_not(None),
            completion_expression >= completion_start,
            completion_expression <= completion_end,
        )
        .group_by(application_expression)
        .order_by(func.count(Ticket.id).desc(), application_expression.asc())
    )
    rows = db.execute(statement).mappings().all()
    total_tickets = sum(int(row["ticket_count"] or 0) for row in rows)
    if total_tickets <= 0:
        return 0

    threshold = total_tickets * 0.8
    cumulative = 0
    application_count = 0
    for row in rows:
        cumulative += int(row["ticket_count"] or 0)
        application_count += 1
        if cumulative >= threshold:
            break
    return application_count


def overview_summary(db: Session, project_id: UUID) -> dict[str, Any]:
    project_statement = (
        select(Project, Client)
        .join(Client, Project.client_id == Client.id)
        .where(Project.id == project_id)
    )
    project_row = db.execute(project_statement).one_or_none()
    if project_row is None:
        raise ValueError("Project not found")

    project, client = project_row

    criticality_expression = func.lower(
        func.trim(
            func.coalesce(
                cmdb_payload_text_expression(*CMDB_APPLICATION_FIELDS["biz_criticality"]),
                "",
            ),
        ),
    )
    active_application_expression = ApplicationInventoryItem.business_service_ci_name
    inventory_statement = select(
        distinct_nonblank_count(ApplicationInventoryItem.business_service_ci_name).label(
            "total_applications",
        ),
        distinct_nonblank_count(ApplicationInventoryItem.functional_track).label(
            "functional_track_count",
        ),
        distinct_nonblank_count(ApplicationInventoryItem.ams_owner).label("ams_owner_count"),
        distinct_nonblank_count(ApplicationInventoryItem.supported_by_vendor).label(
            "supported_vendor_count",
        ),
        distinct_nonblank_count(ApplicationInventoryItem.assignment_group).label(
            "assignment_group_count",
        ),
        distinct_nonblank_count(ApplicationInventoryItem.application_owner).label(
            "application_owner_count",
        ),
        distinct_nonblank_count(active_application_expression)
        .filter(criticality_expression == "very critical")
        .label("very_critical_application_count"),
        distinct_nonblank_count(active_application_expression)
        .filter(criticality_expression == "critical")
        .label("critical_application_count"),
    ).where(
        ApplicationInventoryItem.project_id == project_id,
        ApplicationInventoryItem.active.is_(True),
    )
    inventory_row = db.execute(inventory_statement).mappings().one()

    completion_expression = effective_completion_expression()
    range_statement = select(
        func.min(completion_expression).label("completion_date_min"),
        func.max(completion_expression).label("completion_date_max"),
    ).where(
        Ticket.project_id == project_id,
        completion_expression.is_not(None),
    )
    range_row = db.execute(range_statement).mappings().one()
    completion_start, completion_end = complete_month_bounds(
        range_row["completion_date_min"],
        range_row["completion_date_max"],
    )

    ticket_conditions = [Ticket.project_id == project_id]
    if completion_start is None or completion_end is None:
        ticket_conditions.append(literal(False))
    else:
        ticket_conditions.extend(
            [
                completion_expression.is_not(None),
                completion_expression >= completion_start,
                completion_expression <= completion_end,
            ],
        )

    ticket_statement = select(
        func.count(Ticket.id).label("total_in_scope_tickets"),
        func.sum(case((Ticket.ticket_type == "INCIDENT", 1), else_=0)).label("incident_count"),
        func.sum(case((Ticket.ticket_type == "SERVICE_CATALOG_TASK", 1), else_=0)).label(
            "sc_task_count",
        ),
        func.min(completion_expression).label("completion_date_min"),
        func.max(completion_expression).label("completion_date_max"),
    ).where(*ticket_conditions)
    ticket_row = db.execute(ticket_statement).mappings().one()
    applications_80pct_count = overview_ticket_volume_80pct_application_count(
        db,
        project_id,
        completion_start,
        completion_end,
    )

    raw_ticket_statement = select(
        func.count(TicketRawRow.id).label("total_ticket_rows"),
        func.sum(case((TicketRawRow.ticket_type == "INCIDENT", 1), else_=0)).label(
            "incident_rows",
        ),
        func.sum(case((TicketRawRow.ticket_type == "SERVICE_CATALOG_TASK", 1), else_=0)).label(
            "sc_task_rows",
        ),
    ).where(TicketRawRow.project_id == project_id)
    raw_ticket_row = db.execute(raw_ticket_statement).mappings().one()

    incident_sla_rows = db.scalar(
        select(func.count(IncidentSlaRow.id)).where(IncidentSlaRow.project_id == project_id),
    )

    raw_incident_rows = int(raw_ticket_row["incident_rows"] or 0)
    raw_sc_task_rows = int(raw_ticket_row["sc_task_rows"] or 0)
    raw_incident_sla_rows = int(incident_sla_rows or 0)

    return {
        "project_id": project.id,
        "customer_name": client.name,
        "project_name": project.name,
        "application_inventory": {
            "total_applications": int(inventory_row["total_applications"] or 0),
            "functional_track_count": int(inventory_row["functional_track_count"] or 0),
            "ams_owner_count": int(inventory_row["ams_owner_count"] or 0),
            "supported_vendor_count": int(inventory_row["supported_vendor_count"] or 0),
            "assignment_group_count": int(inventory_row["assignment_group_count"] or 0),
            "application_owner_count": int(inventory_row["application_owner_count"] or 0),
            "very_critical_application_count": int(
                inventory_row["very_critical_application_count"] or 0,
            ),
            "critical_application_count": int(inventory_row["critical_application_count"] or 0),
        },
        "ingested_volume": {
            "total_rows": raw_incident_rows + raw_sc_task_rows + raw_incident_sla_rows,
            "incident_rows": raw_incident_rows,
            "sc_task_rows": raw_sc_task_rows,
            "incident_sla_rows": raw_incident_sla_rows,
        },
        "tickets": {
            "total_in_scope_tickets": int(ticket_row["total_in_scope_tickets"] or 0),
            "incident_count": int(ticket_row["incident_count"] or 0),
            "sc_task_count": int(ticket_row["sc_task_count"] or 0),
            "completion_date_min": completion_start,
            "completion_date_max": completion_end,
            "applications_80pct_monthly_volume_count": applications_80pct_count,
        },
    }


def nonblank_text_expression(expression: Any) -> Any:
    return func.nullif(func.trim(expression), "")


def cmdb_payload_text_expression(*keys: str) -> Any:
    expressions = [
        nonblank_text_expression(ApplicationInventoryItem.cmdb_payload.op("->>")(key))
        for key in keys
    ]
    if len(expressions) == 1:
        return expressions[0]
    return func.coalesce(*expressions)


APPLICATION_NUMERIC_FIELDS = {
    "active_users",
    "avg_monthly_ticket_volume_6m",
    "tickets_per_user_per_month",
}


def application_field_expression(field_name: str) -> Any:
    if field_name in APPLICATION_NUMERIC_FIELDS:
        return DIRECT_APPLICATION_FIELDS[field_name]
    if field_name in DIRECT_APPLICATION_FIELDS:
        return nonblank_text_expression(DIRECT_APPLICATION_FIELDS[field_name])
    if field_name in CMDB_APPLICATION_FIELDS:
        return cmdb_payload_text_expression(*CMDB_APPLICATION_FIELDS[field_name])
    raise ValueError(f"Unsupported application field: {field_name}")


def application_display_expression(field_name: str) -> Any:
    if field_name in APPLICATION_NUMERIC_FIELDS:
        return DIRECT_APPLICATION_FIELDS[field_name]
    return func.coalesce(application_field_expression(field_name), literal(BLANK_LABEL))


def combined_application_display_expression(left_field: str, right_field: str) -> Any:
    return func.concat(
        application_display_expression(left_field),
        literal(" - "),
        application_display_expression(right_field),
    )


def applications_base_conditions(project_id: UUID) -> list[Any]:
    return [
        ApplicationInventoryItem.project_id == project_id,
        ApplicationInventoryItem.active.is_(True),
    ]


def selected_application_filter_values(filters: Any, filter_name: str) -> list[str]:
    values = getattr(filters, filter_name, []) or []
    return [value.strip() for value in values if value and value.strip()]


def applications_filter_conditions(
    project_id: UUID,
    filters: Any,
    *,
    excluded_filter_name: str | None = None,
) -> list[Any]:
    conditions = applications_base_conditions(project_id)

    for filter_name, field_name in SINGLE_APPLICATION_FILTER_FIELDS.items():
        if filter_name == excluded_filter_name:
            continue
        selected_values = selected_application_filter_values(filters, filter_name)
        if selected_values:
            conditions.append(application_display_expression(field_name).in_(selected_values))

    for filter_name, fields in COMBINED_APPLICATION_FILTER_FIELDS.items():
        if filter_name == excluded_filter_name:
            continue
        selected_values = selected_application_filter_values(filters, filter_name)
        if selected_values:
            conditions.append(combined_application_display_expression(*fields).in_(selected_values))

    return conditions


def distinct_application_filter_values(
    db: Session,
    project_id: UUID,
    field_name: str,
    *,
    filter_name: str | None = None,
) -> list[str]:
    expression = application_display_expression(field_name)
    statement = (
        select(expression.label("label"))
        .where(*applications_base_conditions(project_id))
        .group_by(expression)
        .order_by(expression.asc())
    )
    values = [row.label for row in db.execute(statement).all()]
    if filter_name is not None:
        values = sorted(values, key=lambda value: application_filter_sort_key(filter_name, value))
    return values


def distinct_combined_application_filter_values(
    db: Session,
    project_id: UUID,
    left_field: str,
    right_field: str,
    *,
    filter_name: str | None = None,
) -> list[dict[str, str]]:
    left_expression = application_display_expression(left_field)
    right_expression = application_display_expression(right_field)
    label_expression = combined_application_display_expression(left_field, right_field)
    statement = (
        select(
            label_expression.label("label"),
            left_expression.label("left_value"),
            right_expression.label("right_value"),
        )
        .where(*applications_base_conditions(project_id))
        .group_by(label_expression, left_expression, right_expression)
        .order_by(label_expression.asc())
    )
    rows = [dict(row._mapping) for row in db.execute(statement).all()]
    if filter_name is not None:
        rows = sort_filter_count_rows(rows, filter_name=filter_name)
    return rows


def applications_filter_values(db: Session, project_id: UUID) -> dict[str, Any]:
    return {
        "functional_track_ams_owner": distinct_combined_application_filter_values(
            db,
            project_id,
            "functional_track",
            "ams_owner",
        ),
        "assignment_group_owner": distinct_combined_application_filter_values(
            db,
            project_id,
            "assignment_group",
            "assignment_group_owner",
        ),
        "parent_application_name": distinct_application_filter_values(
            db,
            project_id,
            "parent_application_name",
        ),
        "application_owner": distinct_application_filter_values(
            db,
            project_id,
            "application_owner",
        ),
        "supported_by_vendor": distinct_application_filter_values(
            db,
            project_id,
            "supported_by_vendor",
        ),
        "sap_non_sap": distinct_application_filter_values(db, project_id, "sap_non_sap"),
        "architecture_type": distinct_application_filter_values(
            db,
            project_id,
            "architecture_type",
        ),
        "application_type": distinct_application_filter_values(db, project_id, "app_type"),
        "business_critical": distinct_application_filter_values(
            db,
            project_id,
            "biz_criticality",
            filter_name="business_critical",
        ),
        "install_status": distinct_application_filter_values(
            db,
            project_id,
            "install_status",
            filter_name="install_status",
        ),
        "install_type": distinct_application_filter_values(db, project_id, "install_type"),
        "lifecycle_status_stage": distinct_combined_application_filter_values(
            db,
            project_id,
            "lifecycle_status",
            "lifecycle_stage_status",
            filter_name="lifecycle_status_stage",
        ),
    }


def normalize_custom_sort_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split()).casefold()


def application_filter_sort_key(
    filter_name: str | None,
    value: Any,
    *,
    secondary_value: Any | None = None,
) -> tuple[int, str, str]:
    normalized_value = normalize_custom_sort_text(value)
    sort_order = APPLICATION_FILTER_CUSTOM_SORTS.get(filter_name or "")
    if not sort_order:
        return (0, normalized_value, normalize_custom_sort_text(secondary_value))

    normalized_order = {
        normalize_custom_sort_text(order_value): index
        for index, order_value in enumerate(sort_order)
    }
    rank = normalized_order.get(normalized_value, len(normalized_order))
    return (rank, normalized_value, normalize_custom_sort_text(secondary_value))


def sort_filter_count_rows(
    rows: list[dict[str, Any]],
    *,
    filter_name: str | None = None,
) -> list[dict[str, Any]]:
    return sorted(
        rows,
        key=lambda row: application_filter_sort_key(
            filter_name,
            row.get("left_value") if filter_name == "lifecycle_status_stage" else row["label"],
            secondary_value=row["label"],
        ),
    )


def add_missing_selected_single_filter_values(
    rows: list[dict[str, Any]],
    selected_values: list[str],
    *,
    filter_name: str,
) -> list[dict[str, Any]]:
    existing_labels = {str(row["label"]) for row in rows}
    for selected_value in selected_values:
        if selected_value not in existing_labels:
            rows.append({"label": selected_value, "value": selected_value, "count": 0})
            existing_labels.add(selected_value)
    return sort_filter_count_rows(rows, filter_name=filter_name)


def split_combined_filter_label(label: str) -> tuple[str, str]:
    left_value, separator, right_value = label.partition(" - ")
    if not separator:
        return label, BLANK_LABEL
    return left_value or BLANK_LABEL, right_value or BLANK_LABEL


def add_missing_selected_combined_filter_values(
    rows: list[dict[str, Any]],
    selected_values: list[str],
    *,
    filter_name: str,
) -> list[dict[str, Any]]:
    existing_labels = {str(row["label"]) for row in rows}
    for selected_value in selected_values:
        if selected_value not in existing_labels:
            left_value, right_value = split_combined_filter_label(selected_value)
            rows.append(
                {
                    "label": selected_value,
                    "left_value": left_value,
                    "right_value": right_value,
                    "count": 0,
                },
            )
            existing_labels.add(selected_value)
    return sort_filter_count_rows(rows, filter_name=filter_name)


def application_filter_value_count_rows(
    db: Session,
    request: Any,
    filter_name: str,
    field_name: str,
) -> list[dict[str, Any]]:
    expression = application_display_expression(field_name)
    statement = (
        select(
            expression.label("label"),
            expression.label("value"),
            func.count(ApplicationInventoryItem.id).label("count"),
        )
        .where(
            *applications_filter_conditions(
                request.project_id,
                request.filters,
                excluded_filter_name=filter_name,
            ),
        )
        .group_by(expression)
        .order_by(expression.asc())
    )
    rows = [
        {"label": row["label"], "value": row["value"], "count": int(row["count"] or 0)}
        for row in db.execute(statement).mappings().all()
    ]
    return add_missing_selected_single_filter_values(
        rows,
        selected_application_filter_values(request.filters, filter_name),
        filter_name=filter_name,
    )


def combined_application_filter_value_count_rows(
    db: Session,
    request: Any,
    filter_name: str,
    left_field: str,
    right_field: str,
) -> list[dict[str, Any]]:
    left_expression = application_display_expression(left_field)
    right_expression = application_display_expression(right_field)
    label_expression = combined_application_display_expression(left_field, right_field)
    statement = (
        select(
            label_expression.label("label"),
            left_expression.label("left_value"),
            right_expression.label("right_value"),
            func.count(ApplicationInventoryItem.id).label("count"),
        )
        .where(
            *applications_filter_conditions(
                request.project_id,
                request.filters,
                excluded_filter_name=filter_name,
            ),
        )
        .group_by(label_expression, left_expression, right_expression)
        .order_by(label_expression.asc())
    )
    rows = [
        {
            "label": row["label"],
            "left_value": row["left_value"],
            "right_value": row["right_value"],
            "count": int(row["count"] or 0),
        }
        for row in db.execute(statement).mappings().all()
    ]
    return add_missing_selected_combined_filter_values(
        rows,
        selected_application_filter_values(request.filters, filter_name),
        filter_name=filter_name,
    )


def applications_filter_value_counts(db: Session, request: Any) -> dict[str, Any]:
    return {
        "functional_track_ams_owner": combined_application_filter_value_count_rows(
            db,
            request,
            "functional_track_ams_owner",
            "functional_track",
            "ams_owner",
        ),
        "assignment_group_owner": combined_application_filter_value_count_rows(
            db,
            request,
            "assignment_group_owner",
            "assignment_group",
            "assignment_group_owner",
        ),
        "parent_application_name": application_filter_value_count_rows(
            db,
            request,
            "parent_application_name",
            "parent_application_name",
        ),
        "application_owner": application_filter_value_count_rows(
            db,
            request,
            "application_owner",
            "application_owner",
        ),
        "supported_by_vendor": application_filter_value_count_rows(
            db,
            request,
            "supported_by_vendor",
            "supported_by_vendor",
        ),
        "sap_non_sap": application_filter_value_count_rows(
            db,
            request,
            "sap_non_sap",
            "sap_non_sap",
        ),
        "architecture_type": application_filter_value_count_rows(
            db,
            request,
            "architecture_type",
            "architecture_type",
        ),
        "application_type": application_filter_value_count_rows(
            db,
            request,
            "application_type",
            "app_type",
        ),
        "business_critical": application_filter_value_count_rows(
            db,
            request,
            "business_critical",
            "biz_criticality",
        ),
        "install_status": application_filter_value_count_rows(
            db,
            request,
            "install_status",
            "install_status",
        ),
        "install_type": application_filter_value_count_rows(
            db,
            request,
            "install_type",
            "install_type",
        ),
        "lifecycle_status_stage": combined_application_filter_value_count_rows(
            db,
            request,
            "lifecycle_status_stage",
            "lifecycle_status",
            "lifecycle_stage_status",
        ),
    }


def applications_summary(db: Session, request: Any) -> dict[str, Any]:
    filters = request.filters
    conditions = applications_filter_conditions(request.project_id, filters)
    app_type_lower = func.lower(application_field_expression("app_type"))
    criticality_lower = func.lower(application_field_expression("biz_criticality"))
    statement = select(
        distinct_nonblank_count(ApplicationInventoryItem.business_service_ci_name).label(
            "applications",
        ),
        distinct_nonblank_count(ApplicationInventoryItem.functional_track).label(
            "functional_groups",
        ),
        distinct_nonblank_count(ApplicationInventoryItem.assignment_group).label(
            "assignment_groups",
        ),
        distinct_nonblank_count(ApplicationInventoryItem.parent_application_name).label(
            "parent_business_apps",
        ),
        func.sum(
            case((app_type_lower.in_(("business", "business application")), 1), else_=0),
        ).label("business_applications"),
        func.sum(
            case((app_type_lower.in_(("technical", "technical application")), 1), else_=0),
        ).label("technical_applications"),
        func.sum(case((criticality_lower == "very critical", 1), else_=0)).label(
            "very_critical_applications",
        ),
        func.sum(case((criticality_lower == "critical", 1), else_=0)).label(
            "critical_applications",
        ),
    ).where(*conditions)
    row = db.execute(statement).mappings().one()
    return {
        "applications": int(row["applications"] or 0),
        "functional_groups": int(row["functional_groups"] or 0),
        "assignment_groups": int(row["assignment_groups"] or 0),
        "parent_business_apps": int(row["parent_business_apps"] or 0),
        "business_applications": int(row["business_applications"] or 0),
        "technical_applications": int(row["technical_applications"] or 0),
        "very_critical_applications": int(row["very_critical_applications"] or 0),
        "critical_applications": int(row["critical_applications"] or 0),
        "show_functional_groups": not selected_application_filter_values(
            filters,
            "functional_track_ams_owner",
        ),
        "show_assignment_groups": not selected_application_filter_values(
            filters,
            "assignment_group_owner",
        ),
        "show_parent_business_apps": not selected_application_filter_values(
            filters,
            "parent_application_name",
        ),
    }


def applications_sort_expression(column_name: str) -> Any:
    if column_name not in APPLICATION_LIST_FIELDS:
        raise ValueError(f"Unsupported application sort column: {column_name}")
    return application_display_expression(column_name)


def applications_list(db: Session, request: Any) -> dict[str, Any]:
    conditions = applications_filter_conditions(request.project_id, request.filters)
    total_statement = select(func.count(ApplicationInventoryItem.id)).where(*conditions)
    total = int(db.scalar(total_statement) or 0)

    sort_expression = applications_sort_expression(request.sort.column)
    sort_direction = request.sort.direction.lower()
    if sort_direction not in {"asc", "desc"}:
        raise ValueError("Sort direction must be asc or desc")
    order_expression = sort_expression.desc() if sort_direction == "desc" else sort_expression.asc()

    columns = [
        application_display_expression(field_name).label(field_name)
        for field_name in APPLICATION_LIST_FIELDS
    ]
    statement = (
        select(*columns)
        .where(*conditions)
        .order_by(
            order_expression,
            application_display_expression("business_service_ci_name").asc(),
        )
        .limit(request.limit)
        .offset(request.offset)
    )
    rows = [dict(row._mapping) for row in db.execute(statement).all()]
    return {"total": total, "rows": rows}


def applications_chart_counts(
    db: Session,
    request: Any,
    field_name: str,
) -> list[dict[str, Any]]:
    expression = application_display_expression(field_name)
    statement = (
        select(
            expression.label("label"),
            func.count(ApplicationInventoryItem.id).label("count"),
        )
        .where(*applications_filter_conditions(request.project_id, request.filters))
        .group_by(expression)
        .order_by(func.count(ApplicationInventoryItem.id).desc(), expression.asc())
    )
    return [
        {"label": row.label, "count": int(row.count or 0)}
        for row in db.execute(statement).all()
    ]


def applications_charts(db: Session, request: Any) -> dict[str, list[dict[str, Any]]]:
    lifecycle_selected = bool(
        selected_application_filter_values(request.filters, "lifecycle_status_stage"),
    )
    return {
        "lifecycle_stage": []
        if lifecycle_selected
        else applications_chart_counts(db, request, "lifecycle_stage_status"),
        "architecture_type": applications_chart_counts(db, request, "architecture_type"),
        "install_type": applications_chart_counts(db, request, "install_type"),
        "strategic": applications_chart_counts(db, request, "strategic"),
    }


def applications_top_active_users(db: Session, request: Any) -> dict[str, Any]:
    top_n = normalized_top_n(getattr(request, "top_n", 10))
    name_expression = application_display_expression("business_service_ci_name")
    statement = (
        select(
            name_expression.label("application_name"),
            ApplicationInventoryItem.active_users.label("active_users"),
        )
        .where(
            *applications_filter_conditions(request.project_id, request.filters),
            ApplicationInventoryItem.active_users.is_not(None),
            ApplicationInventoryItem.active_users > 0,
        )
        .order_by(ApplicationInventoryItem.active_users.desc(), name_expression.asc())
        .limit(top_n)
    )
    points = [
        {
            "application_name": str(row["application_name"]),
            "active_users": int(row["active_users"] or 0),
        }
        for row in db.execute(statement).mappings().all()
    ]
    return {"top_n": top_n, "points": points}


def normalize_volumetrics_scope(value: str | None) -> str:
    normalized = (value or "in_scope").strip().lower()
    if normalized not in VOLUMETRICS_SCOPES:
        raise ValueError("Scope must be one of in_scope, out_of_scope, or all")
    return normalized


def normalize_volumetrics_ticket_type(value: str | None) -> str:
    normalized = (value or "all").strip().lower()
    if normalized not in VOLUMETRICS_TICKET_TYPES:
        raise ValueError("Ticket type must be one of all, incident, or sc_task")
    return normalized


def normalize_volumetrics_time_grain(value: str | None) -> str:
    normalized = (value or "monthly").strip().lower()
    if normalized not in VOLUMETRICS_TIME_GRAINS:
        raise ValueError("Time grain must be monthly or weekly")
    return normalized


def normalize_dashboard_datetime(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def volumetrics_completion_expression(model: Any) -> Any:
    cancelled_state = volumetrics_cancelled_state_expression(model)
    return case(
        (cancelled_state, func.coalesce(model.resolved_at, model.closed_at)),
        (model.ticket_type == "INCIDENT", model.resolved_at),
        (model.ticket_type == "SERVICE_CATALOG_TASK", model.closed_at),
        else_=func.coalesce(model.resolved_at, model.closed_at),
    )


def volumetrics_availability_completion_expression(model: Any) -> Any:
    return case(
        (model.ticket_type == "INCIDENT", model.resolved_at),
        (model.ticket_type == "SERVICE_CATALOG_TASK", model.closed_at),
        else_=func.coalesce(model.resolved_at, model.closed_at),
    )


def volumetrics_cancelled_state_expression(model: Any) -> Any:
    return func.lower(func.trim(func.coalesce(model.state, ""))).in_(VOLUMETRICS_CANCELLED_STATES)


def volumetrics_exit_expression(model: Any) -> Any:
    completion_expression = volumetrics_completion_expression(model)
    # Cancelled rows with no resolved/closed timestamp should not remain backlog forever.
    return case(
        (
            and_(
                volumetrics_cancelled_state_expression(model),
                completion_expression.is_(None),
            ),
            model.created_at,
        ),
        else_=completion_expression,
    )


def volumetrics_supported_vendor_expression(model: Any) -> Any:
    return func.coalesce(
        nonblank_text_expression(model.supported_by_vendor),
        nonblank_text_expression(model.derived_vendor),
    )


def volumetrics_source_select(model: Any, scope_label: str, project_id: UUID) -> Any:
    return select(
        literal(scope_label).label("scope"),
        model.id.label("id"),
        model.ticket_type.label("ticket_type"),
        model.created_at.label("created_at"),
        model.resolved_at.label("resolved_at"),
        model.closed_at.label("closed_at"),
        volumetrics_completion_expression(model).label("completion_at"),
        volumetrics_exit_expression(model).label("exit_at"),
        model.state.label("state"),
        model.priority.label("priority"),
        model.assignment_group.label("assignment_group"),
        model.support_lead.label("support_lead"),
        model.functional_track.label("functional_track"),
        model.ams_owner.label("ams_owner"),
        model.parent_application_name.label("parent_application_name"),
        model.business_service_ci_name.label("business_service_ci_name"),
        model.application_owner.label("application_owner"),
        volumetrics_supported_vendor_expression(model).label("supported_by_vendor"),
        model.sap_non_sap.label("sap_non_sap"),
        model.architecture_type.label("architecture_type"),
        model.install_type.label("install_type"),
        model.is_batch_related.label("is_batch_related"),
        model.business_duration_seconds.label("business_duration_seconds"),
        model.response_sla_breached.label("response_sla_breached"),
        model.resolution_sla_breached.label("resolution_sla_breached"),
    ).where(model.project_id == project_id)


def volumetrics_source_subquery(request: Any, *, scope_override: str | None = None) -> Any:
    scope = normalize_volumetrics_scope(scope_override or request.scope)
    in_scope_select = volumetrics_source_select(Ticket, "in_scope", request.project_id)
    out_of_scope_select = volumetrics_source_select(
        AssessmentOutOfScopeTicket,
        "out_of_scope",
        request.project_id,
    )
    if scope == "in_scope":
        return in_scope_select.subquery("volumetrics_source")
    if scope == "out_of_scope":
        return out_of_scope_select.subquery("volumetrics_source")
    return union_all(in_scope_select, out_of_scope_select).subquery("volumetrics_source")


def volumetrics_display_expression(expression: Any) -> Any:
    return func.coalesce(nonblank_text_expression(expression), literal(BLANK_LABEL))


def combined_volumetrics_display_expression(source: Any, left_field: str, right_field: str) -> Any:
    return func.concat(
        volumetrics_display_expression(getattr(source.c, left_field)),
        literal(" - "),
        volumetrics_display_expression(getattr(source.c, right_field)),
    )


def selected_volumetrics_filter_values(filters: Any, filter_name: str) -> list[str]:
    values = getattr(filters, filter_name, []) or []
    return [value.strip() for value in values if value and value.strip()]


def volumetrics_ticket_type_condition(source: Any, ticket_type: str) -> Any | None:
    normalized = normalize_volumetrics_ticket_type(ticket_type)
    mapped_value = VOLUMETRICS_TICKET_TYPE_VALUES.get(normalized)
    if mapped_value is None:
        return None
    return source.c.ticket_type == mapped_value


def volumetrics_created_date_conditions(source: Any, request: Any) -> list[Any]:
    start_datetime = normalize_dashboard_datetime(request.start_datetime)
    end_datetime = normalize_dashboard_datetime(request.end_datetime)
    return [
        source.c.created_at.is_not(None),
        source.c.created_at >= start_datetime,
        source.c.created_at <= end_datetime,
    ]


def volumetrics_filter_conditions(
    source: Any,
    filters: Any,
    *,
    excluded_filter_name: str | None = None,
) -> list[Any]:
    conditions: list[Any] = []
    for filter_name, field_name in SINGLE_VOLUMETRICS_FILTER_FIELDS.items():
        if filter_name == excluded_filter_name:
            continue
        selected_values = selected_volumetrics_filter_values(filters, filter_name)
        if selected_values:
            conditions.append(
                volumetrics_display_expression(getattr(source.c, field_name)).in_(
                    selected_values,
                ),
            )

    for filter_name, fields in COMBINED_VOLUMETRICS_FILTER_FIELDS.items():
        if filter_name == excluded_filter_name:
            continue
        selected_values = selected_volumetrics_filter_values(filters, filter_name)
        if selected_values:
            conditions.append(
                combined_volumetrics_display_expression(source, *fields).in_(selected_values),
            )
    return conditions


def volumetrics_base_conditions(
    source: Any,
    request: Any,
    *,
    excluded_filter_name: str | None = None,
    exclude_ticket_type: bool = False,
    include_date_bounds: bool = True,
) -> list[Any]:
    conditions: list[Any] = []
    ticket_condition = (
        None
        if exclude_ticket_type
        else volumetrics_ticket_type_condition(source, request.ticket_type)
    )
    if ticket_condition is not None:
        conditions.append(ticket_condition)
    if include_date_bounds:
        conditions.extend(volumetrics_created_date_conditions(source, request))
    conditions.extend(
        volumetrics_filter_conditions(
            source,
            request.filters,
            excluded_filter_name=excluded_filter_name,
        ),
    )
    return conditions


def add_missing_selected_volumetrics_single_values(
    rows: list[dict[str, Any]],
    selected_values: list[str],
) -> list[dict[str, Any]]:
    existing = {str(row["label"]) for row in rows}
    for selected_value in selected_values:
        if selected_value not in existing:
            rows.append({"label": selected_value, "value": selected_value, "count": 0})
            existing.add(selected_value)
    return sorted(rows, key=lambda row: str(row["label"]).casefold())


def add_missing_selected_volumetrics_combined_values(
    rows: list[dict[str, Any]],
    selected_values: list[str],
) -> list[dict[str, Any]]:
    existing = {str(row["label"]) for row in rows}
    for selected_value in selected_values:
        if selected_value not in existing:
            left_value, right_value = split_combined_filter_label(selected_value)
            rows.append(
                {
                    "label": selected_value,
                    "left_value": left_value,
                    "right_value": right_value,
                    "count": 0,
                },
            )
            existing.add(selected_value)
    return sorted(rows, key=lambda row: str(row["label"]).casefold())


def volumetrics_filter_value_count_rows(
    db: Session,
    request: Any,
    filter_name: str,
    field_name: str,
) -> list[dict[str, Any]]:
    source = volumetrics_source_subquery(request)
    expression = volumetrics_display_expression(getattr(source.c, field_name))
    statement = (
        select(
            expression.label("label"),
            expression.label("value"),
            func.count(source.c.id).label("count"),
        )
        .select_from(source)
        .where(
            *volumetrics_base_conditions(
                source,
                request,
                excluded_filter_name=filter_name,
            ),
        )
        .group_by(expression)
        .order_by(expression.asc())
    )
    rows = [
        {"label": row["label"], "value": row["value"], "count": int(row["count"] or 0)}
        for row in db.execute(statement).mappings().all()
    ]
    return add_missing_selected_volumetrics_single_values(
        rows,
        selected_volumetrics_filter_values(request.filters, filter_name),
    )


def combined_volumetrics_filter_value_count_rows(
    db: Session,
    request: Any,
    filter_name: str,
    left_field: str,
    right_field: str,
) -> list[dict[str, Any]]:
    source = volumetrics_source_subquery(request)
    left_expression = volumetrics_display_expression(getattr(source.c, left_field))
    right_expression = volumetrics_display_expression(getattr(source.c, right_field))
    label_expression = combined_volumetrics_display_expression(source, left_field, right_field)
    statement = (
        select(
            label_expression.label("label"),
            left_expression.label("left_value"),
            right_expression.label("right_value"),
            func.count(source.c.id).label("count"),
        )
        .select_from(source)
        .where(
            *volumetrics_base_conditions(
                source,
                request,
                excluded_filter_name=filter_name,
            ),
        )
        .group_by(label_expression, left_expression, right_expression)
        .order_by(label_expression.asc())
    )
    rows = [
        {
            "label": row["label"],
            "left_value": row["left_value"],
            "right_value": row["right_value"],
            "count": int(row["count"] or 0),
        }
        for row in db.execute(statement).mappings().all()
    ]
    return add_missing_selected_volumetrics_combined_values(
        rows,
        selected_volumetrics_filter_values(request.filters, filter_name),
    )


def count_volumetrics_rows(
    db: Session,
    request: Any,
    *,
    scope_override: str | None = None,
    ticket_type_override: str | None = None,
    exclude_ticket_type: bool = False,
) -> int:
    source = volumetrics_source_subquery(request, scope_override=scope_override)
    effective_request = request
    if ticket_type_override is not None:
        effective_request = replace_request_value(request, "ticket_type", ticket_type_override)
    statement = (
        select(func.count(source.c.id))
        .select_from(source)
        .where(
            *volumetrics_base_conditions(
                source,
                effective_request,
                exclude_ticket_type=exclude_ticket_type,
            ),
        )
    )
    return int(db.scalar(statement) or 0)


def replace_request_value(request: Any, field_name: str, value: Any) -> Any:
    # Pydantic v1/v2 compatibility keeps tests and runtime aligned across local installs.
    if hasattr(request, "model_copy"):
        return request.model_copy(update={field_name: value})
    return request.copy(update={field_name: value})


def volumetrics_filter_value_counts(db: Session, request: Any) -> dict[str, Any]:
    normalize_volumetrics_scope(request.scope)
    normalize_volumetrics_ticket_type(request.ticket_type)
    normalize_volumetrics_time_grain(request.time_grain)
    scope_rows = []
    for scope_key in ("all", "in_scope", "out_of_scope"):
        scope_rows.append(
            {
                "label": VOLUMETRICS_SCOPE_LABELS[scope_key],
                "value": scope_key,
                "count": count_volumetrics_rows(db, request, scope_override=scope_key),
            },
        )

    ticket_type_rows = []
    for ticket_type_key in ("all", "incident", "sc_task"):
        ticket_type_rows.append(
            {
                "label": VOLUMETRICS_TICKET_TYPE_LABELS[ticket_type_key],
                "value": ticket_type_key,
                "count": count_volumetrics_rows(
                    db,
                    request,
                    ticket_type_override=ticket_type_key,
                    exclude_ticket_type=ticket_type_key == "all",
                ),
            },
        )

    return {
        "scope": scope_rows,
        "ticket_type": ticket_type_rows,
        "functional_track_ams_owner": combined_volumetrics_filter_value_count_rows(
            db,
            request,
            "functional_track_ams_owner",
            "functional_track",
            "ams_owner",
        ),
        "assignment_group_support_lead": combined_volumetrics_filter_value_count_rows(
            db,
            request,
            "assignment_group_support_lead",
            "assignment_group",
            "support_lead",
        ),
        "parent_application_name": volumetrics_filter_value_count_rows(
            db,
            request,
            "parent_application_name",
            "parent_application_name",
        ),
        "application_owner": volumetrics_filter_value_count_rows(
            db,
            request,
            "application_owner",
            "application_owner",
        ),
        "supported_by_vendor": volumetrics_filter_value_count_rows(
            db,
            request,
            "supported_by_vendor",
            "supported_by_vendor",
        ),
        "sap_non_sap": volumetrics_filter_value_count_rows(
            db,
            request,
            "sap_non_sap",
            "sap_non_sap",
        ),
    }


def volumetrics_data_range(db: Session, project_id: UUID) -> dict[str, Any]:
    in_scope_select = select(
        volumetrics_availability_completion_expression(Ticket).label("completion_at"),
    ).where(Ticket.project_id == project_id)
    out_of_scope_select = select(
        volumetrics_availability_completion_expression(AssessmentOutOfScopeTicket).label(
            "completion_at",
        ),
    ).where(
        AssessmentOutOfScopeTicket.project_id == project_id,
    )
    source = union_all(in_scope_select, out_of_scope_select).subquery("volumetrics_source")
    row = db.execute(
        select(
            func.min(source.c.completion_at).label("completion_date_min"),
            func.max(source.c.completion_at).label("completion_date_max"),
        ).where(source.c.completion_at.is_not(None)),
    ).mappings().one()
    completion_start, completion_end = complete_month_bounds(
        row["completion_date_min"],
        row["completion_date_max"],
    )
    return {
        "completion_date_min": completion_start,
        "completion_date_max": completion_end,
    }


def add_month(value: datetime) -> datetime:
    if value.month == 12:
        return datetime(value.year + 1, 1, 1, tzinfo=value.tzinfo)
    return datetime(value.year, value.month + 1, 1, tzinfo=value.tzinfo)


def build_volumetrics_periods(request: Any) -> list[VolumetricsPeriod]:
    grain = normalize_volumetrics_time_grain(request.time_grain)
    start_datetime = normalize_dashboard_datetime(request.start_datetime)
    end_datetime = normalize_dashboard_datetime(request.end_datetime)
    if start_datetime > end_datetime:
        raise ValueError("Start datetime must be before end datetime")

    periods: list[VolumetricsPeriod] = []
    if grain == "monthly":
        current = datetime(
            start_datetime.year,
            start_datetime.month,
            1,
            tzinfo=start_datetime.tzinfo,
        )
        while current <= end_datetime:
            next_start = add_month(current)
            period_end = min(next_start - timedelta(microseconds=1), end_datetime)
            periods.append(
                VolumetricsPeriod(
                    start=current,
                    end=period_end,
                    label=f"{current:%b-%y}",
                ),
            )
            current = next_start
        return periods

    current_date = start_datetime.date() - timedelta(days=start_datetime.weekday())
    current = datetime.combine(current_date, time.min, tzinfo=start_datetime.tzinfo)
    while current <= end_datetime:
        next_start = current + timedelta(days=7)
        period_end = min(next_start - timedelta(microseconds=1), end_datetime)
        periods.append(
            VolumetricsPeriod(
                start=current,
                end=period_end,
                label=f"{current:%d-%b-%y}",
            ),
        )
        current = next_start
    if len(periods) > VOLUMETRICS_MAX_WEEKLY_PERIODS:
        raise ValueError("Weekly view is limited to 15 weeks. Select a range of 3 months or less.")
    return periods


def volumetrics_cancelled_expression(source: Any) -> Any:
    state_expression = func.lower(func.trim(func.coalesce(source.c.state, "")))
    return state_expression.in_(VOLUMETRICS_CANCELLED_STATES)


def scalar_count(db: Session, source: Any, conditions: list[Any]) -> int:
    statement = select(func.count(source.c.id)).select_from(source).where(*conditions)
    return int(db.scalar(statement) or 0)


def volumetrics_period_start_expression(date_expression: Any, grain: str) -> Any:
    return func.date_trunc("month" if grain == "monthly" else "week", date_expression)


def normalize_volumetrics_period_key(value: datetime | None, grain: str) -> datetime | None:
    if value is None:
        return None
    value = normalize_dashboard_datetime(value)
    if grain == "monthly":
        return datetime(value.year, value.month, 1, tzinfo=value.tzinfo)
    week_date = value.date() - timedelta(days=value.weekday())
    return datetime.combine(week_date, time.min, tzinfo=value.tzinfo)


def volumetrics_period_lookup_key(value: datetime, grain: str) -> str:
    normalized = normalize_volumetrics_period_key(value, grain)
    if normalized is None:
        return ""
    if grain == "monthly":
        return f"{normalized.year:04d}-{normalized.month:02d}"
    return f"{normalized.year:04d}-{normalized.month:02d}-{normalized.day:02d}"


def volumetrics_aggregate_by_period(
    db: Session,
    request: Any,
    source: Any,
    date_expression: Any,
    columns: list[Any],
    extra_conditions: list[Any] | None = None,
    *,
    override_request: Any | None = None,
) -> dict[str, dict[str, Any]]:
    effective_request = override_request or request
    grain = normalize_volumetrics_time_grain(effective_request.time_grain)
    period_expression = volumetrics_period_start_expression(date_expression, grain).label(
        "period_start",
    )
    conditions = [
        *volumetrics_base_conditions(
            source,
            effective_request,
            include_date_bounds=False,
        ),
        date_expression.is_not(None),
        date_expression >= normalize_dashboard_datetime(effective_request.start_datetime),
        date_expression <= normalize_dashboard_datetime(effective_request.end_datetime),
    ]
    if extra_conditions:
        conditions.extend(extra_conditions)

    statement = (
        select(period_expression, *columns)
        .select_from(source)
        .where(*conditions)
        .group_by(period_expression)
        .order_by(period_expression)
    )
    rows_by_period: dict[str, dict[str, Any]] = {}
    for row in db.execute(statement).mappings().all():
        key = normalize_volumetrics_period_key(row["period_start"], grain)
        if key is not None:
            rows_by_period[volumetrics_period_lookup_key(key, grain)] = dict(row)
    return rows_by_period


def average(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def period_adherence_percentages(rows: list[dict[str, Any]], prefix: str) -> list[float]:
    values: list[float] = []
    for row in rows:
        applicable = int(row[f"{prefix}_applicable_count"])
        met = int(row[f"{prefix}_met_count"])
        percentage_value = percentage(met, applicable)
        if percentage_value is not None:
            values.append(percentage_value)
    return values


def volumetrics_period_metrics(
    db: Session,
    request: Any,
    *,
    include_backlog: bool = True,
    include_cancelled: bool = True,
    include_sla: bool = True,
) -> list[dict[str, Any]]:
    normalize_volumetrics_scope(request.scope)
    normalize_volumetrics_ticket_type(request.ticket_type)
    periods = build_volumetrics_periods(request)
    source = volumetrics_source_subquery(request)
    base_conditions = volumetrics_base_conditions(
        source,
        request,
        include_date_bounds=False,
    )
    cancelled_condition = volumetrics_cancelled_expression(source)

    created_rows = volumetrics_aggregate_by_period(
        db,
        request,
        source,
        source.c.created_at,
        [func.count(source.c.id).label("created_count")],
    )
    completed_rows = volumetrics_aggregate_by_period(
        db,
        request,
        source,
        source.c.completion_at,
        [func.count(source.c.id).label("resolved_closed_count")],
        [~cancelled_condition],
    )
    cancelled_rows = (
        volumetrics_aggregate_by_period(
            db,
            request,
            source,
            source.c.completion_at,
            [func.count(source.c.id).label("cancelled_count")],
            [cancelled_condition],
        )
        if include_cancelled
        else {}
    )
    exit_rows = (
        volumetrics_aggregate_by_period(
            db,
            request,
            source,
            source.c.exit_at,
            [func.count(source.c.id).label("exit_count")],
        )
        if include_backlog
        else {}
    )
    incident_request = replace_request_value(request, "ticket_type", "incident")
    sla_rows = (
        volumetrics_aggregate_by_period(
            db,
            request,
            source,
            source.c.created_at,
            [
                func.count(source.c.id)
                .filter(source.c.response_sla_breached.is_not(None))
                .label("response_applicable_count"),
                func.count(source.c.id)
                .filter(source.c.response_sla_breached.is_(False))
                .label("response_met_count"),
                func.count(source.c.id)
                .filter(source.c.resolution_sla_breached.is_not(None))
                .label("resolution_applicable_count"),
                func.count(source.c.id)
                .filter(source.c.resolution_sla_breached.is_(False))
                .label("resolution_met_count"),
            ],
            override_request=incident_request,
        )
        if include_sla
        else {}
    )

    first_period_start = periods[0].start if periods else None
    running_created = 0
    running_exits = 0
    if include_backlog and first_period_start is not None:
        running_created = scalar_count(
            db,
            source,
            [
                *base_conditions,
                source.c.created_at.is_not(None),
                source.c.created_at < first_period_start,
            ],
        )
        running_exits = scalar_count(
            db,
            source,
            [
                *base_conditions,
                source.c.exit_at.is_not(None),
                source.c.exit_at < first_period_start,
            ],
        )

    rows: list[dict[str, Any]] = []
    for period in periods:
        period_key = volumetrics_period_lookup_key(
            period.start,
            normalize_volumetrics_time_grain(request.time_grain),
        )
        created_values = created_rows.get(period_key, {})
        completed_values = completed_rows.get(period_key, {})
        cancelled_values = cancelled_rows.get(period_key, {})
        exit_values = exit_rows.get(period_key, {})
        sla_values = sla_rows.get(period_key, {})
        created_count = int_count(created_values.get("created_count"))
        exit_count = int_count(exit_values.get("exit_count"))
        if include_backlog:
            running_created += created_count
            running_exits += exit_count

        rows.append(
            {
                "period_start": period.start,
                "period_end": period.end,
                "period_label": period.label,
                "created_count": created_count,
                "resolved_closed_count": int_count(
                    completed_values.get("resolved_closed_count"),
                ),
                "cancelled_count": int_count(cancelled_values.get("cancelled_count")),
                "backlog_open_count": (
                    max(running_created - running_exits, 0) if include_backlog else 0
                ),
                "response_applicable_count": int_count(
                    sla_values.get("response_applicable_count"),
                ),
                "response_met_count": int_count(sla_values.get("response_met_count")),
                "resolution_applicable_count": int_count(
                    sla_values.get("resolution_applicable_count"),
                ),
                "resolution_met_count": int_count(sla_values.get("resolution_met_count")),
            },
        )
    return rows


def volumetrics_summary(db: Session, request: Any) -> dict[str, Any]:
    rows = volumetrics_period_metrics(db, request, include_backlog=False)
    period_count = len(rows)
    total_created = sum(row["created_count"] for row in rows)
    total_resolved_closed = sum(row["resolved_closed_count"] for row in rows)
    total_cancelled = sum(row["cancelled_count"] for row in rows)
    response_applicable = sum(row["response_applicable_count"] for row in rows)
    response_met = sum(row["response_met_count"] for row in rows)
    resolution_applicable = sum(row["resolution_applicable_count"] for row in rows)
    resolution_met = sum(row["resolution_met_count"] for row in rows)
    sla_not_applicable = normalize_volumetrics_ticket_type(request.ticket_type) == "sc_task"

    return {
        "period_count": period_count,
        "created": {
            "total": total_created,
            "average_per_period": total_created / period_count if period_count else None,
        },
        "resolved_closed": {
            "total": total_resolved_closed,
            "average_per_period": total_resolved_closed / period_count if period_count else None,
        },
        "cancelled": {
            "total": total_cancelled,
            "average_per_period": total_cancelled / period_count if period_count else None,
            "cancelled_pct_of_resolved_cancelled": percentage(
                total_cancelled,
                total_resolved_closed + total_cancelled,
            ),
        },
        "response_sla": {
            "average_adherence_pct": None
            if sla_not_applicable
            else average(period_adherence_percentages(rows, "response")),
            "applicable_count": 0 if sla_not_applicable else response_applicable,
            "met_count": 0 if sla_not_applicable else response_met,
        },
        "resolution_sla": {
            "average_adherence_pct": None
            if sla_not_applicable
            else average(period_adherence_percentages(rows, "resolution")),
            "applicable_count": 0 if sla_not_applicable else resolution_applicable,
            "met_count": 0 if sla_not_applicable else resolution_met,
        },
    }


def volumetrics_created_resolved_backlog(db: Session, request: Any) -> dict[str, Any]:
    rows = volumetrics_period_metrics(
        db,
        request,
        include_cancelled=False,
        include_sla=False,
    )
    backlog_values = [float(row["backlog_open_count"]) for row in rows]
    average_backlog = average(backlog_values)
    chart_rows = [
        {
            "period_start": row["period_start"],
            "period_end": row["period_end"],
            "period_label": row["period_label"],
            "created_count": row["created_count"],
            "resolved_closed_count": row["resolved_closed_count"],
            "backlog_open_count": row["backlog_open_count"],
            "average_backlog_open": average_backlog,
        }
        for row in rows
    ]
    return {"average_backlog_open": average_backlog, "rows": chart_rows}


def volumetrics_created_resolved_cancelled(db: Session, request: Any) -> dict[str, Any]:
    rows = volumetrics_period_metrics(db, request, include_backlog=False, include_sla=False)
    return {
        "time_grain": normalize_volumetrics_time_grain(request.time_grain),
        "points": [
            {
                "period_start": row["period_start"],
                "period_end": row["period_end"],
                "period_label": row["period_label"],
                "created_count": row["created_count"],
                "resolved_closed_count": row["resolved_closed_count"],
                "canceled_closed_incomplete_count": row["cancelled_count"],
            }
            for row in rows
        ],
    }


def volumetrics_backlog(db: Session, request: Any) -> dict[str, Any]:
    rows = volumetrics_period_metrics(
        db,
        request,
        include_cancelled=False,
        include_sla=False,
    )
    backlog_values = [float(row["backlog_open_count"]) for row in rows]
    return {
        "time_grain": normalize_volumetrics_time_grain(request.time_grain),
        "average_backlog": average(backlog_values),
        "points": [
            {
                "period_start": row["period_start"],
                "period_end": row["period_end"],
                "period_label": row["period_label"],
                "backlog_open": row["backlog_open_count"],
            }
            for row in rows
        ],
    }


def normalize_volumetrics_created_pattern_type(value: str | None) -> str:
    normalized = (value or "day_of_month").strip().lower()
    if normalized not in VOLUMETRICS_CREATED_PATTERN_TYPES:
        raise ValueError(
            "Created pattern type must be day_of_month, day_of_week, "
            "hour_weekdays, or hour_weekends"
        )
    return normalized


def date_counts_by_day_of_month(start_date: date, end_date: date) -> dict[int, int]:
    counts = {day: 0 for day in range(1, 31)}
    current = start_date
    while current <= end_date:
        if current.day <= 30:
            counts[current.day] += 1
        current += timedelta(days=1)
    return counts


def date_counts_by_weekday(start_date: date, end_date: date) -> dict[int, int]:
    counts = {weekday: 0 for weekday in range(7)}
    current = start_date
    while current <= end_date:
        counts[current.weekday()] += 1
        current += timedelta(days=1)
    return counts


def day_count_for_week_part(start_date: date, end_date: date, *, weekdays: bool) -> int:
    allowed_weekdays = {0, 1, 2, 3, 4} if weekdays else {5, 6}
    current = start_date
    count = 0
    while current <= end_date:
        if current.weekday() in allowed_weekdays:
            count += 1
        current += timedelta(days=1)
    return count


def volumetrics_created_counts_by_bucket(
    db: Session,
    request: Any,
    source: Any,
    bucket_expression: Any,
    extra_conditions: list[Any] | None = None,
) -> dict[int, int]:
    conditions = volumetrics_base_conditions(source, request)
    if extra_conditions:
        conditions.extend(extra_conditions)

    statement = (
        select(
            bucket_expression.label("bucket"),
            func.count(source.c.id).label("created_count"),
        )
        .select_from(source)
        .where(*conditions)
        .group_by(bucket_expression)
        .order_by(bucket_expression)
    )
    return {
        int(row["bucket"]): int(row["created_count"] or 0)
        for row in db.execute(statement).mappings().all()
        if row["bucket"] is not None
    }


def volumetrics_created_pattern(db: Session, request: Any) -> dict[str, Any]:
    pattern_type = normalize_volumetrics_created_pattern_type(request.pattern_type)
    start_date = normalize_dashboard_datetime(request.start_datetime).date()
    end_date = normalize_dashboard_datetime(request.end_datetime).date()
    source = volumetrics_source_subquery(request)

    if pattern_type == "day_of_month":
        day_expression = cast(func.extract("day", source.c.created_at), Float)
        counts = volumetrics_created_counts_by_bucket(
            db,
            request,
            source,
            day_expression,
            [day_expression <= 30],
        )
        denominators = date_counts_by_day_of_month(start_date, end_date)
        points = []
        for day in range(1, 31):
            total_created = counts.get(day, 0)
            denominator = denominators.get(day, 0)
            points.append(
                {
                    "label": str(day),
                    "average_created": total_created / denominator if denominator else 0,
                    "total_created": total_created,
                    "denominator": denominator,
                },
            )
        return {"pattern_type": pattern_type, "points": points}

    if pattern_type == "day_of_week":
        # PostgreSQL EXTRACT(DOW) returns Sunday as 0. Convert to Monday-first labels.
        dow_expression = cast(func.extract("dow", source.c.created_at), Float)
        counts = volumetrics_created_counts_by_bucket(db, request, source, dow_expression)
        denominators = date_counts_by_weekday(start_date, end_date)
        labels = (
            ("Mon", 1, 0),
            ("Tue", 2, 1),
            ("Wed", 3, 2),
            ("Thu", 4, 3),
            ("Fri", 5, 4),
            ("Sat", 6, 5),
            ("Sun", 0, 6),
        )
        return {
            "pattern_type": pattern_type,
            "points": [
                {
                    "label": label,
                    "average_created": (
                        counts.get(postgres_dow, 0) / denominators.get(python_weekday, 0)
                        if denominators.get(python_weekday, 0)
                        else 0
                    ),
                    "total_created": counts.get(postgres_dow, 0),
                    "denominator": denominators.get(python_weekday, 0),
                }
                for label, postgres_dow, python_weekday in labels
            ],
        }

    hour_expression = cast(func.extract("hour", source.c.created_at), Float)
    dow_expression = cast(func.extract("dow", source.c.created_at), Float)
    include_weekdays = pattern_type == "hour_weekdays"
    day_denominator = day_count_for_week_part(
        start_date,
        end_date,
        weekdays=include_weekdays,
    )
    dow_condition = (
        dow_expression.between(1, 5)
        if include_weekdays
        else dow_expression.in_((0, 6))
    )
    counts = volumetrics_created_counts_by_bucket(
        db,
        request,
        source,
        hour_expression,
        [dow_condition],
    )
    return {
        "pattern_type": pattern_type,
        "points": [
            {
                "label": f"{hour:02d}",
                "average_created": counts.get(hour, 0) / day_denominator
                if day_denominator
                else 0,
                "total_created": counts.get(hour, 0),
                "denominator": day_denominator,
            }
            for hour in range(24)
        ],
    }


def normalize_volumetrics_day_type(value: str | None) -> str:
    normalized = (value or "weekdays").strip().lower()
    if normalized not in VOLUMETRICS_DAY_TYPES:
        raise ValueError("Day type must be weekdays or weekends")
    return normalized


def volumetrics_day_type_condition(date_expression: Any, day_type: str) -> Any:
    dow_expression = cast(func.extract("dow", date_expression), Float)
    if normalize_volumetrics_day_type(day_type) == "weekdays":
        return dow_expression.between(1, 5)
    return dow_expression.in_((0, 6))


def volumetrics_counts_by_hour(
    db: Session,
    request: Any,
    source: Any,
    date_expression: Any,
    day_type: str,
    value_label: str,
    extra_conditions: list[Any] | None = None,
) -> dict[int, int]:
    hour_expression = cast(func.extract("hour", date_expression), Float)
    conditions = [
        *volumetrics_base_conditions(source, request, include_date_bounds=False),
        date_expression.is_not(None),
        date_expression >= normalize_dashboard_datetime(request.start_datetime),
        date_expression <= normalize_dashboard_datetime(request.end_datetime),
        volumetrics_day_type_condition(date_expression, day_type),
    ]
    if extra_conditions:
        conditions.extend(extra_conditions)

    statement = (
        select(
            hour_expression.label("hour"),
            func.count(source.c.id).label(value_label),
        )
        .select_from(source)
        .where(*conditions)
        .group_by(hour_expression)
        .order_by(hour_expression)
    )
    return {
        int(row["hour"]): int(row[value_label] or 0)
        for row in db.execute(statement).mappings().all()
        if row["hour"] is not None
    }


def volumetrics_hourly_created_resolved(db: Session, request: Any) -> dict[str, Any]:
    day_type = normalize_volumetrics_day_type(request.day_type)
    start_date = normalize_dashboard_datetime(request.start_datetime).date()
    end_date = normalize_dashboard_datetime(request.end_datetime).date()
    denominator = day_count_for_week_part(
        start_date,
        end_date,
        weekdays=day_type == "weekdays",
    )
    source = volumetrics_source_subquery(request)
    cancelled_condition = volumetrics_cancelled_expression(source)

    created_counts = volumetrics_counts_by_hour(
        db,
        request,
        source,
        source.c.created_at,
        day_type,
        "created_count",
    )
    resolved_counts = volumetrics_counts_by_hour(
        db,
        request,
        source,
        source.c.completion_at,
        day_type,
        "resolved_closed_count",
        [~cancelled_condition],
    )

    points = []
    for hour in range(24):
        created_total = created_counts.get(hour, 0)
        resolved_total = resolved_counts.get(hour, 0)
        average_created = created_total / denominator if denominator else 0
        average_resolved = resolved_total / denominator if denominator else 0
        points.append(
            {
                "hour": f"{hour:02d}",
                "average_created": average_created,
                "average_resolved_closed": average_resolved,
                "created_label": math.ceil(average_created),
                "resolved_closed_label": math.ceil(average_resolved),
            },
        )

    return {
        "day_type": day_type,
        "denominator_days": denominator,
        "points": points,
    }


def priority_display_expression(expression: Any) -> Any:
    return volumetrics_display_expression(expression)


def priority_sort_key(label: str) -> tuple[int, str]:
    normalized = label.casefold()
    if label == BLANK_LABEL:
        return (99, normalized)
    first_digit = next((int(character) for character in label if character.isdigit()), None)
    if first_digit is not None:
        return (first_digit, normalized)
    priority_words = (
        ("critical", 1),
        ("high", 2),
        ("moderate", 3),
        ("medium", 3),
        ("low", 4),
        ("planning", 5),
    )
    for word, sort_value in priority_words:
        if word in normalized:
            return (sort_value, normalized)
    return (50, normalized)


def volumetrics_priority_distribution(db: Session, request: Any) -> dict[str, Any]:
    grain = normalize_volumetrics_time_grain(request.time_grain)
    periods = build_volumetrics_periods(request)
    source = volumetrics_source_subquery(request)
    period_expression = volumetrics_period_start_expression(source.c.created_at, grain)
    priority_expression = priority_display_expression(source.c.priority)
    statement = (
        select(
            period_expression.label("period_start"),
            priority_expression.label("priority"),
            func.count(source.c.id).label("ticket_count"),
        )
        .select_from(source)
        .where(*volumetrics_base_conditions(source, request))
        .group_by(period_expression, priority_expression)
        .order_by(period_expression, priority_expression)
    )

    rows_by_period: dict[str, dict[str, int]] = {}
    priorities: set[str] = set()
    for row in db.execute(statement).mappings().all():
        period_start = normalize_volumetrics_period_key(row["period_start"], grain)
        if period_start is None:
            continue
        period_key = volumetrics_period_lookup_key(period_start, grain)
        priority = str(row["priority"])
        priorities.add(priority)
        rows_by_period.setdefault(period_key, {})[priority] = int(row["ticket_count"] or 0)

    ordered_priorities = sorted(priorities, key=priority_sort_key)
    points = []
    for period in periods:
        period_key = volumetrics_period_lookup_key(period.start, grain)
        values = rows_by_period.get(period_key, {})
        points.append(
            {
                "period_key": period_key,
                "period_label": period.label,
                "values": {priority: values.get(priority, 0) for priority in ordered_priorities},
                "total": sum(values.get(priority, 0) for priority in ordered_priorities),
            },
        )

    return {
        "time_grain": grain,
        "priorities": ordered_priorities,
        "points": points,
    }


def empty_sla_trend_response(request: Any, *, not_applicable: bool) -> dict[str, Any]:
    return {
        "time_grain": normalize_volumetrics_time_grain(request.time_grain),
        "not_applicable": not_applicable,
        "response": [],
        "resolution": [],
        "logic": {
            "response_adherence_formula": (
                "response_sla_adhered_count / response_sla_captured_count * 100"
            ),
            "resolution_adherence_formula": (
                "resolution_sla_adhered_count / resolution_sla_captured_count * 100"
            ),
            "captured_definition": "sla_breached IS NOT NULL",
        },
    }


def volumetrics_sla_trend_rows(
    db: Session,
    request: Any,
    source: Any,
) -> dict[str, dict[str, Any]]:
    grain = normalize_volumetrics_time_grain(request.time_grain)
    period_expression = volumetrics_period_start_expression(source.c.resolved_at, grain)
    incident_request = replace_request_value(request, "ticket_type", "incident")
    statement = (
        select(
            period_expression.label("period_start"),
            func.count(source.c.id).label("total_closed_ticket_count"),
            func.count(source.c.id)
            .filter(source.c.response_sla_breached.is_not(None))
            .label("response_sla_captured_count"),
            func.count(source.c.id)
            .filter(source.c.response_sla_breached.is_(False))
            .label("response_sla_adhered_count"),
            func.count(source.c.id)
            .filter(source.c.resolution_sla_breached.is_not(None))
            .label("resolution_sla_captured_count"),
            func.count(source.c.id)
            .filter(source.c.resolution_sla_breached.is_(False))
            .label("resolution_sla_adhered_count"),
        )
        .select_from(source)
        .where(
            *volumetrics_base_conditions(
                source,
                incident_request,
                include_date_bounds=False,
            ),
            source.c.resolved_at.is_not(None),
            source.c.resolved_at >= normalize_dashboard_datetime(request.start_datetime),
            source.c.resolved_at <= normalize_dashboard_datetime(request.end_datetime),
        )
        .group_by(period_expression)
        .order_by(period_expression)
    )
    rows: dict[str, dict[str, Any]] = {}
    for row in db.execute(statement).mappings().all():
        period_start = normalize_volumetrics_period_key(row["period_start"], grain)
        if period_start is None:
            continue
        rows[volumetrics_period_lookup_key(period_start, grain)] = dict(row)
    return rows


def volumetrics_sla_trends(db: Session, request: Any) -> dict[str, Any]:
    if normalize_volumetrics_ticket_type(request.ticket_type) == "sc_task":
        return empty_sla_trend_response(request, not_applicable=True)

    periods = build_volumetrics_periods(request)
    source = volumetrics_source_subquery(request)
    rows_by_period = volumetrics_sla_trend_rows(db, request, source)
    response_rows = []
    resolution_rows = []
    grain = normalize_volumetrics_time_grain(request.time_grain)

    for period in periods:
        period_key = volumetrics_period_lookup_key(period.start, grain)
        values = rows_by_period.get(period_key, {})
        total_closed = int_count(values.get("total_closed_ticket_count"))
        response_captured = int_count(values.get("response_sla_captured_count"))
        response_adhered = int_count(values.get("response_sla_adhered_count"))
        resolution_captured = int_count(values.get("resolution_sla_captured_count"))
        resolution_adhered = int_count(values.get("resolution_sla_adhered_count"))
        response_rows.append(
            {
                "period_key": period_key,
                "period_label": period.label,
                "total_closed_ticket_count": total_closed,
                "sla_captured_count": response_captured,
                "sla_adhered_count": response_adhered,
                "sla_adherence_pct": percentage(response_adhered, response_captured),
            },
        )
        resolution_rows.append(
            {
                "period_key": period_key,
                "period_label": period.label,
                "total_closed_ticket_count": total_closed,
                "sla_captured_count": resolution_captured,
                "sla_adhered_count": resolution_adhered,
                "sla_adherence_pct": percentage(resolution_adhered, resolution_captured),
            },
        )

    response = empty_sla_trend_response(request, not_applicable=False)
    response["response"] = response_rows
    response["resolution"] = resolution_rows
    return response


TOP_APPLICATIONS_WINDOW_DESCRIPTION = "Last 6 complete months excluding current month"
LATEST_COMPLETE_6_MONTHS_DESCRIPTION = "Latest complete 6 months"
BATCH_RULE_DESCRIPTION = (
    "Incident is batch-related when short_description contains Automic, case-insensitive."
)
BATCH_APPLICABLE_MESSAGE = (
    "Batch-related charts are Incident-only and use Incident tickets within the selected filters."
)
BATCH_NOT_APPLICABLE_MESSAGE = (
    "Batch-related ticket charts are applicable only for Incidents. "
    "SC Task catalog item charts will be added separately."
)
MTTR_PRIORITIES = ("P1", "P2", "P3", "P4")
MTTR_LABEL_START_INDEX = {"P1": 0, "P2": 1, "P3": 2, "P4": 3}
DURATION_BUCKETS = ("0-1 day", "1-3 days", "3-10 days", ">10 days")


def subtract_months(value: datetime, month_count: int) -> datetime:
    month_index = value.year * 12 + (value.month - 1) - month_count
    return datetime(month_index // 12, month_index % 12 + 1, 1, tzinfo=value.tzinfo)


def rolling_six_complete_month_window(
    reference_datetime: datetime | None = None,
) -> tuple[datetime, datetime]:
    reference = normalize_dashboard_datetime(reference_datetime or datetime.now(UTC))
    current_month_start = datetime(reference.year, reference.month, 1, tzinfo=reference.tzinfo)
    previous_month_end = current_month_start - timedelta(microseconds=1)
    previous_month_start = datetime(
        previous_month_end.year,
        previous_month_end.month,
        1,
        tzinfo=previous_month_end.tzinfo,
    )
    return subtract_months(previous_month_start, 5), previous_month_end


def latest_complete_month_window(
    db: Session,
    project_id: UUID,
    month_count: int,
) -> tuple[datetime, datetime]:
    data_range = volumetrics_data_range(db, project_id)
    data_end = data_range["completion_date_max"]
    if data_end is None:
        fallback_start, fallback_end = rolling_six_complete_month_window()
        fallback_end_month = first_day_of_month(fallback_end)
        return subtract_months(fallback_end_month, month_count - 1), fallback_end

    end_month = first_day_of_month(normalize_dashboard_datetime(data_end))
    end_datetime = last_moment_of_month(end_month)
    return subtract_months(end_month, month_count - 1), end_datetime


def ranking_window_payload(start_datetime: datetime, end_datetime: datetime) -> dict[str, str]:
    return {
        "start_month": f"{start_datetime.year:04d}-{start_datetime.month:02d}",
        "end_month": f"{end_datetime.year:04d}-{end_datetime.month:02d}",
        "description": TOP_APPLICATIONS_WINDOW_DESCRIPTION,
    }


def latest_complete_window_payload(
    start_datetime: datetime,
    end_datetime: datetime,
) -> dict[str, str]:
    return {
        "start_month": f"{start_datetime.year:04d}-{start_datetime.month:02d}",
        "end_month": f"{end_datetime.year:04d}-{end_datetime.month:02d}",
        "description": LATEST_COMPLETE_6_MONTHS_DESCRIPTION,
    }


def normalized_top_n(value: int | None) -> int:
    top_n = int(value or 10)
    if top_n not in {10, 20}:
        raise ValueError("top_n must be either 10 or 20")
    return top_n


def batch_rule_payload() -> dict[str, str]:
    return {
        "field": "short_description",
        "rule_description": BATCH_RULE_DESCRIPTION,
    }


def is_batch_chart_not_applicable(request: Any) -> bool:
    return normalize_volumetrics_ticket_type(request.ticket_type) == "sc_task"


def application_name_expression(source: Any) -> Any:
    return volumetrics_display_expression(source.c.business_service_ci_name)


def pareto_top_application_points(
    rows: list[dict[str, Any]],
    *,
    created_key: str,
    canceled_key: str,
    created_label_key: str,
    canceled_label_key: str,
    output_created_key: str,
    output_canceled_key: str,
) -> list[dict[str, Any]]:
    total_created = sum(float(row[created_key] or 0) for row in rows)
    running_created = 0.0
    points: list[dict[str, Any]] = []
    for row in rows:
        created_value = float(row[created_key] or 0)
        canceled_value = float(row[canceled_key] or 0)
        running_created += created_value
        points.append(
            {
                "application_name": str(row["application_name"]),
                output_created_key: created_value,
                output_canceled_key: canceled_value,
                created_label_key: math.ceil(created_value),
                canceled_label_key: math.ceil(canceled_value),
                "pareto_cumulative_pct": percentage(
                    int(round(running_created * 1000)),
                    int(round(total_created * 1000)),
                ),
            },
        )
    return points


def volumetrics_top_application_rows(
    db: Session,
    request: Any,
    *,
    top_n: int,
    incident_batch_only: bool = False,
) -> list[dict[str, Any]]:
    window_start, window_end = latest_complete_month_window(db, request.project_id, 6)
    effective_request = (
        replace_request_value(request, "ticket_type", "incident")
        if incident_batch_only
        else request
    )
    source = volumetrics_source_subquery(request)
    application_expression = application_name_expression(source)
    cancelled_condition = volumetrics_cancelled_expression(source)
    created_count_expression = (func.count(source.c.id) / 6.0).label("average_created")
    canceled_count_expression = (
        func.count(source.c.id).filter(cancelled_condition) / 6.0
    ).label("average_canceled")
    conditions = [
        *volumetrics_base_conditions(
            source,
            effective_request,
            include_date_bounds=False,
        ),
        source.c.created_at.is_not(None),
        source.c.created_at >= window_start,
        source.c.created_at <= window_end,
    ]
    if incident_batch_only:
        conditions.append(source.c.is_batch_related.is_(True))

    statement = (
        select(
            application_expression.label("application_name"),
            created_count_expression,
            canceled_count_expression,
        )
        .select_from(source)
        .where(*conditions)
        .group_by(application_expression)
        .order_by(created_count_expression.desc(), application_expression.asc())
        .limit(top_n)
    )
    return [dict(row) for row in db.execute(statement).mappings().all()]


def volumetrics_overall_average_created_volume(
    db: Session,
    request: Any,
    *,
    incident_batch_only: bool = False,
) -> float:
    window_start, window_end = latest_complete_month_window(db, request.project_id, 6)
    effective_request = (
        replace_request_value(request, "ticket_type", "incident")
        if incident_batch_only
        else request
    )
    source = volumetrics_source_subquery(request)
    conditions = [
        *volumetrics_base_conditions(
            source,
            effective_request,
            include_date_bounds=False,
        ),
        source.c.created_at.is_not(None),
        source.c.created_at >= window_start,
        source.c.created_at <= window_end,
    ]
    if incident_batch_only:
        conditions.append(source.c.is_batch_related.is_(True))
    value = db.scalar(
        select((func.count(source.c.id) / 6.0).label("overall_average"))
        .select_from(source)
        .where(*conditions),
    )
    return float(value or 0)


def top_application_volume_points(
    rows: list[dict[str, Any]],
    *,
    overall_average_monthly_volume: float,
) -> list[dict[str, Any]]:
    points: list[dict[str, Any]] = []
    for row in rows:
        created_value = float(row["average_created"] or 0)
        canceled_value = float(row["average_canceled"] or 0)
        volume_pct = (
            created_value / overall_average_monthly_volume * 100
            if overall_average_monthly_volume
            else None
        )
        created_label = math.ceil(created_value)
        pct_text = f"{volume_pct:.1f}%" if volume_pct is not None else "N/A"
        points.append(
            {
                "application_name": str(row["application_name"]),
                "average_created": created_value,
                "average_canceled_closed_incomplete": canceled_value,
                "created_label": created_label,
                "canceled_label": math.ceil(canceled_value),
                "volume_pct": volume_pct,
                "display_label": f"{created_label:,} ({pct_text})",
            },
        )
    return points


def volumetrics_top_applications(db: Session, request: Any) -> dict[str, Any]:
    top_n = normalized_top_n(getattr(request, "top_n", 10))
    window_start, window_end = latest_complete_month_window(db, request.project_id, 6)
    rows = volumetrics_top_application_rows(db, request, top_n=top_n)
    overall_average = volumetrics_overall_average_created_volume(db, request)
    points = top_application_volume_points(
        rows,
        overall_average_monthly_volume=overall_average,
    )
    return {
        "ranking_window": ranking_window_payload(window_start, window_end),
        "top_n": top_n,
        "overall_average_monthly_volume": overall_average,
        "points": points,
    }


def monthly_batch_request(request: Any) -> Any:
    return replace_request_value(
        replace_request_value(request, "ticket_type", "incident"),
        "time_grain",
        "monthly",
    )


def volumetrics_incident_batch_trend(db: Session, request: Any) -> dict[str, Any]:
    if is_batch_chart_not_applicable(request):
        return {
            "applicable": False,
            "message": BATCH_NOT_APPLICABLE_MESSAGE,
            "batch_rule": batch_rule_payload(),
            "points": [],
        }

    effective_request = monthly_batch_request(request)
    periods = build_volumetrics_periods(effective_request)
    source = volumetrics_source_subquery(request)
    period_expression = volumetrics_period_start_expression(source.c.created_at, "monthly")
    statement = (
        select(
            period_expression.label("period_start"),
            func.count(source.c.id).label("batch_created_count"),
        )
        .select_from(source)
        .where(
            *volumetrics_base_conditions(
                source,
                effective_request,
                include_date_bounds=True,
            ),
            source.c.is_batch_related.is_(True),
        )
        .group_by(period_expression)
        .order_by(period_expression)
    )
    rows_by_period = {}
    for row in db.execute(statement).mappings().all():
        period_start = normalize_volumetrics_period_key(row["period_start"], "monthly")
        if period_start is None:
            continue
        rows_by_period[volumetrics_period_lookup_key(period_start, "monthly")] = int_count(
            row["batch_created_count"],
        )

    return {
        "applicable": True,
        "message": BATCH_APPLICABLE_MESSAGE,
        "batch_rule": batch_rule_payload(),
        "points": [
            {
                "period_key": volumetrics_period_lookup_key(period.start, "monthly"),
                "period_label": period.label,
                "batch_created_count": rows_by_period.get(
                    volumetrics_period_lookup_key(period.start, "monthly"),
                    0,
                ),
            }
            for period in periods
        ],
    }


def volumetrics_top_incident_batch_applications(db: Session, request: Any) -> dict[str, Any]:
    top_n = normalized_top_n(getattr(request, "top_n", 10))
    window_start, window_end = latest_complete_month_window(db, request.project_id, 6)
    if is_batch_chart_not_applicable(request):
        return {
            "applicable": False,
            "message": BATCH_NOT_APPLICABLE_MESSAGE,
            "ranking_window": ranking_window_payload(window_start, window_end),
            "top_n": top_n,
            "points": [],
        }

    rows = volumetrics_top_application_rows(
        db,
        request,
        top_n=top_n,
        incident_batch_only=True,
    )
    points = pareto_top_application_points(
        rows,
        created_key="average_created",
        canceled_key="average_canceled",
        created_label_key="batch_created_label",
        canceled_label_key="batch_canceled_label",
        output_created_key="average_batch_created",
        output_canceled_key="average_batch_canceled",
    )
    return {
        "applicable": True,
        "message": BATCH_APPLICABLE_MESSAGE,
        "ranking_window": ranking_window_payload(window_start, window_end),
        "top_n": top_n,
        "points": points,
    }


def volumetrics_split_rows(
    db: Session,
    request: Any,
    *,
    field_name: str,
    ticket_type: str,
    window_start: datetime,
    window_end: datetime,
) -> list[dict[str, Any]]:
    source = volumetrics_source_subquery(request)
    effective_request = replace_request_value(request, "ticket_type", ticket_type)
    split_expression = volumetrics_display_expression(getattr(source.c, field_name))
    statement = (
        select(
            split_expression.label("label"),
            (func.count(source.c.id) / 6.0).label("average_monthly_count"),
        )
        .select_from(source)
        .where(
            *volumetrics_base_conditions(
                source,
                effective_request,
                include_date_bounds=False,
            ),
            source.c.created_at.is_not(None),
            source.c.created_at >= window_start,
            source.c.created_at <= window_end,
        )
        .group_by(split_expression)
        .order_by(func.count(source.c.id).desc(), split_expression.asc())
    )
    rows = [dict(row) for row in db.execute(statement).mappings().all()]
    total_average = sum(float(row["average_monthly_count"] or 0) for row in rows)
    return [
        {
            "label": str(row["label"]),
            "average_monthly_count": float(row["average_monthly_count"] or 0),
            "display_count": math.ceil(float(row["average_monthly_count"] or 0)),
            "percentage": (
                float(row["average_monthly_count"] or 0) / total_average * 100
                if total_average
                else None
            ),
        }
        for row in rows
    ]


def volumetrics_detailed_architecture_install_splits(
    db: Session,
    request: Any,
) -> dict[str, Any]:
    window_start, window_end = latest_complete_month_window(db, request.project_id, 6)
    return {
        "rolling_window": latest_complete_window_payload(window_start, window_end),
        "architecture_type": {
            "incidents": volumetrics_split_rows(
                db,
                request,
                field_name="architecture_type",
                ticket_type="incident",
                window_start=window_start,
                window_end=window_end,
            ),
            "sc_tasks": volumetrics_split_rows(
                db,
                request,
                field_name="architecture_type",
                ticket_type="sc_task",
                window_start=window_start,
                window_end=window_end,
            ),
        },
        "install_type": {
            "incidents": volumetrics_split_rows(
                db,
                request,
                field_name="install_type",
                ticket_type="incident",
                window_start=window_start,
                window_end=window_end,
            ),
            "sc_tasks": volumetrics_split_rows(
                db,
                request,
                field_name="install_type",
                ticket_type="sc_task",
                window_start=window_start,
                window_end=window_end,
            ),
        },
    }


def format_tickets_per_user(value: float) -> str:
    if value < 10:
        return f"{value:.2f}"
    if value < 100:
        return f"{value:.1f}"
    return f"{round(value):,}"


def inventory_active_users_subquery(project_id: UUID) -> Any:
    application_key = func.lower(func.btrim(ApplicationInventoryItem.business_service_ci_name))
    return (
        select(
            application_key.label("application_key"),
            func.max(ApplicationInventoryItem.business_service_ci_name).label("application_name"),
            func.max(ApplicationInventoryItem.active_users).label("active_users"),
        )
        .where(
            ApplicationInventoryItem.project_id == project_id,
            ApplicationInventoryItem.active.is_(True),
            ApplicationInventoryItem.active_users.is_not(None),
            ApplicationInventoryItem.active_users > 0,
            ApplicationInventoryItem.business_service_ci_name.is_not(None),
            func.btrim(ApplicationInventoryItem.business_service_ci_name) != "",
        )
        .group_by(application_key)
        .subquery("inventory_active_users")
    )


def volumetrics_tickets_per_user(db: Session, request: Any) -> dict[str, Any]:
    top_n = normalized_top_n(getattr(request, "top_n", 10))
    window_start, window_end = latest_complete_month_window(db, request.project_id, 6)
    source = volumetrics_source_subquery(request)
    inventory = inventory_active_users_subquery(request.project_id)
    source_application_key = func.lower(func.btrim(source.c.business_service_ci_name))
    average_volume_expression = (func.count(source.c.id) / 6.0).label(
        "average_monthly_ticket_volume",
    )
    ratio_expression = (
        (func.count(source.c.id) / 6.0) / cast(inventory.c.active_users, Float)
    ).label("tickets_per_user_per_month")
    statement = (
        select(
            inventory.c.application_name,
            inventory.c.active_users,
            average_volume_expression,
            ratio_expression,
        )
        .select_from(source)
        .join(inventory, inventory.c.application_key == source_application_key)
        .where(
            *volumetrics_base_conditions(
                source,
                request,
                include_date_bounds=False,
            ),
            source.c.created_at.is_not(None),
            source.c.created_at >= window_start,
            source.c.created_at <= window_end,
        )
        .group_by(inventory.c.application_name, inventory.c.active_users)
        .order_by(ratio_expression.desc(), inventory.c.application_name.asc())
        .limit(top_n)
    )
    points = []
    for row in db.execute(statement).mappings().all():
        ratio = float(row["tickets_per_user_per_month"] or 0)
        points.append(
            {
                "application_name": str(row["application_name"]),
                "active_users": int(row["active_users"] or 0),
                "average_monthly_ticket_volume": float(
                    row["average_monthly_ticket_volume"] or 0,
                ),
                "tickets_per_user_per_month": ratio,
                "display_label": format_tickets_per_user(ratio),
            },
        )
    return {
        "ranking_window": latest_complete_window_payload(window_start, window_end),
        "top_n": top_n,
        "points": points,
    }


def volumetrics_distribution_split_rows(
    db: Session,
    request: Any,
    *,
    field_name: str,
    ticket_type: str,
    window_start: datetime,
    window_end: datetime,
) -> list[dict[str, Any]]:
    source = volumetrics_source_subquery(request)
    effective_request = (
        replace_request_value(request, "ticket_type", ticket_type)
        if ticket_type != "all"
        else replace_request_value(request, "ticket_type", "all")
    )
    split_expression = volumetrics_display_expression(getattr(source.c, field_name))
    statement = (
        select(
            split_expression.label("label"),
            (func.count(source.c.id) / 6.0).label("average_monthly_count"),
        )
        .select_from(source)
        .where(
            *volumetrics_base_conditions(
                source,
                effective_request,
                include_date_bounds=False,
            ),
            source.c.created_at.is_not(None),
            source.c.created_at >= window_start,
            source.c.created_at <= window_end,
        )
        .group_by(split_expression)
        .order_by(func.count(source.c.id).desc(), split_expression.asc())
    )
    rows = [dict(row) for row in db.execute(statement).mappings().all()]
    total_average = sum(float(row["average_monthly_count"] or 0) for row in rows)
    return [
        {
            "label": str(row["label"]),
            "average_monthly_count": float(row["average_monthly_count"] or 0),
            "display_count": math.ceil(float(row["average_monthly_count"] or 0)),
            "percentage": (
                float(row["average_monthly_count"] or 0) / total_average * 100
                if total_average
                else None
            ),
        }
        for row in rows
    ]


def volumetrics_distribution_splits(db: Session, request: Any) -> dict[str, Any]:
    window_start, window_end = latest_complete_month_window(db, request.project_id, 6)

    def group(field_name: str) -> dict[str, list[dict[str, Any]]]:
        return {
            "all": volumetrics_distribution_split_rows(
                db,
                request,
                field_name=field_name,
                ticket_type="all",
                window_start=window_start,
                window_end=window_end,
            ),
            "incidents": volumetrics_distribution_split_rows(
                db,
                request,
                field_name=field_name,
                ticket_type="incident",
                window_start=window_start,
                window_end=window_end,
            ),
            "sc_tasks": volumetrics_distribution_split_rows(
                db,
                request,
                field_name=field_name,
                ticket_type="sc_task",
                window_start=window_start,
                window_end=window_end,
            ),
        }

    return {
        "ranking_window": latest_complete_window_payload(window_start, window_end),
        "sap_non_sap": group("sap_non_sap"),
        "architecture_type": group("architecture_type"),
        "install_type": group("install_type"),
    }


def priority_bucket_expression(source: Any) -> Any:
    normalized = func.lower(func.trim(func.coalesce(source.c.priority, "")))
    # ServiceNow priority values can arrive as P1/P2 labels or as numbered labels.
    return case(
        (
            or_(
                normalized.like("p1%"),
                normalized.like("1%"),
                normalized.like("%critical%"),
            ),
            literal("P1"),
        ),
        (
            or_(
                normalized.like("p2%"),
                normalized.like("2%"),
                normalized.like("%high%"),
            ),
            literal("P2"),
        ),
        (
            or_(
                normalized.like("p3%"),
                normalized.like("3%"),
                normalized.like("%moderate%"),
                normalized.like("%medium%"),
            ),
            literal("P3"),
        ),
        (
            or_(
                normalized.like("p4%"),
                normalized.like("4%"),
                normalized.like("%low%"),
            ),
            literal("P4"),
        ),
        else_=None,
    )


def empty_mttr_priority_set() -> dict[str, list[dict[str, Any]]]:
    return {priority: [] for priority in MTTR_PRIORITIES}


def mttr_show_label(priority: str, period_index: int) -> bool:
    start_index = MTTR_LABEL_START_INDEX[priority]
    return period_index >= start_index and (period_index - start_index) % 3 == 0


def mttr_label_text(average_mttr_days: float | None, ticket_count: int) -> str | None:
    if average_mttr_days is None or ticket_count <= 0:
        return None
    return f"{average_mttr_days:.1f}d\nn={ticket_count:,}"


def complete_month_clamped_request(db: Session, request: Any) -> Any:
    completion_end = volumetrics_data_range(db, request.project_id)["completion_date_max"]
    if completion_end is None:
        return request
    request_end = normalize_dashboard_datetime(request.end_datetime)
    clamped_end = min(request_end, normalize_dashboard_datetime(completion_end))
    if clamped_end == request_end:
        return request
    return replace_request_value(request, "end_datetime", clamped_end)


def mttr_rows_for_ticket_type(
    db: Session,
    request: Any,
    *,
    ticket_type: str,
    completion_field: str,
) -> dict[str, list[dict[str, Any]]]:
    complete_request = complete_month_clamped_request(db, request)
    grain = normalize_volumetrics_time_grain(complete_request.time_grain)
    periods = build_volumetrics_periods(complete_request)
    source = volumetrics_source_subquery(complete_request)
    completion_expression = getattr(source.c, completion_field)
    period_expression = volumetrics_period_start_expression(completion_expression, grain)
    priority_expression = priority_bucket_expression(source)
    business_days_expression = cast(source.c.business_duration_seconds, Float) / SECONDS_PER_DAY
    effective_request = replace_request_value(complete_request, "ticket_type", ticket_type)
    statement = (
        select(
            period_expression.label("period_start"),
            priority_expression.label("priority_bucket"),
            func.avg(business_days_expression).label("average_mttr_days"),
            func.count(source.c.id).label("ticket_count"),
        )
        .select_from(source)
        .where(
            *volumetrics_base_conditions(
                source,
                effective_request,
                include_date_bounds=False,
            ),
            completion_expression.is_not(None),
            completion_expression >= normalize_dashboard_datetime(complete_request.start_datetime),
            completion_expression <= normalize_dashboard_datetime(complete_request.end_datetime),
            source.c.business_duration_seconds.is_not(None),
            source.c.business_duration_seconds >= 0,
            priority_expression.in_(MTTR_PRIORITIES),
        )
        .group_by(period_expression, priority_expression)
    )
    rows_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for row in db.execute(statement).mappings().all():
        period_start = normalize_volumetrics_period_key(row["period_start"], grain)
        priority = row["priority_bucket"]
        if period_start is None or priority is None:
            continue
        rows_by_key[(volumetrics_period_lookup_key(period_start, grain), priority)] = {
            "average_mttr_days": float(row["average_mttr_days"] or 0),
            "ticket_count": int_count(row["ticket_count"]),
        }

    rows = empty_mttr_priority_set()
    for priority in MTTR_PRIORITIES:
        for period_index, period in enumerate(periods):
            period_key = volumetrics_period_lookup_key(period.start, grain)
            values = rows_by_key.get((period_key, priority))
            average_mttr_days = (
                float(values["average_mttr_days"]) if values is not None else None
            )
            ticket_count = int_count(values.get("ticket_count") if values else None)
            show_label = mttr_show_label(priority, period_index) and average_mttr_days is not None
            rows[priority].append(
                {
                    "period_key": period_key,
                    "period_label": period.label,
                    "average_mttr_days": average_mttr_days,
                    "ticket_count": ticket_count,
                    "show_label": show_label,
                    "label_text": mttr_label_text(average_mttr_days, ticket_count)
                    if show_label
                    else None,
                },
            )
    return rows


def volumetrics_kpi_mttr_trends(db: Session, request: Any) -> dict[str, Any]:
    grain = normalize_volumetrics_time_grain(request.time_grain)
    return {
        "time_grain": grain,
        "incident": mttr_rows_for_ticket_type(
            db,
            request,
            ticket_type="incident",
            completion_field="resolved_at",
        ),
        "sc_task": mttr_rows_for_ticket_type(
            db,
            request,
            ticket_type="sc_task",
            completion_field="closed_at",
        ),
    }


def latest_complete_month_periods(
    db: Session,
    project_id: UUID,
    month_count: int,
) -> list[VolumetricsPeriod]:
    start_datetime, end_datetime = latest_complete_month_window(db, project_id, month_count)
    request = type(
        "MonthlyPeriodRequest",
        (),
        {
            "time_grain": "monthly",
            "start_datetime": start_datetime,
            "end_datetime": end_datetime,
        },
    )()
    return build_volumetrics_periods(request)


def duration_bucket_expression(duration_seconds: Any) -> Any:
    # Four bars are implemented because the requirements provided four explicit buckets.
    return case(
        (duration_seconds <= SECONDS_PER_DAY, literal("0-1 day")),
        (
            and_(duration_seconds > SECONDS_PER_DAY, duration_seconds <= SECONDS_PER_DAY * 3),
            literal("1-3 days"),
        ),
        (
            and_(duration_seconds > SECONDS_PER_DAY * 3, duration_seconds <= SECONDS_PER_DAY * 10),
            literal("3-10 days"),
        ),
        (duration_seconds > SECONDS_PER_DAY * 10, literal(">10 days")),
        else_=None,
    )


def duration_bucket_rows_for_ticket_type(
    db: Session,
    request: Any,
    *,
    ticket_type: str,
    completion_field: str,
) -> list[dict[str, Any]]:
    periods = latest_complete_month_periods(db, request.project_id, 3)
    if not periods:
        return []

    source = volumetrics_source_subquery(request)
    completion_expression = getattr(source.c, completion_field)
    period_expression = volumetrics_period_start_expression(completion_expression, "monthly")
    duration_seconds = func.extract("epoch", completion_expression - source.c.created_at)
    bucket_expression = duration_bucket_expression(duration_seconds)
    effective_request = replace_request_value(request, "ticket_type", ticket_type)
    statement = (
        select(
            period_expression.label("period_start"),
            bucket_expression.label("bucket"),
            func.count(source.c.id).label("ticket_count"),
        )
        .select_from(source)
        .where(
            *volumetrics_base_conditions(
                source,
                effective_request,
                include_date_bounds=False,
            ),
            source.c.created_at.is_not(None),
            completion_expression.is_not(None),
            completion_expression >= periods[0].start,
            completion_expression <= periods[-1].end,
            completion_expression >= source.c.created_at,
            bucket_expression.is_not(None),
        )
        .group_by(period_expression, bucket_expression)
    )
    counts: dict[tuple[str, str], int] = {}
    for row in db.execute(statement).mappings().all():
        period_start = normalize_volumetrics_period_key(row["period_start"], "monthly")
        bucket = row["bucket"]
        if period_start is None or bucket is None:
            continue
        counts[(volumetrics_period_lookup_key(period_start, "monthly"), str(bucket))] = int_count(
            row["ticket_count"],
        )

    return [
        {
            "period_key": volumetrics_period_lookup_key(period.start, "monthly"),
            "period_label": period.label,
            "buckets": {
                bucket: counts.get(
                    (volumetrics_period_lookup_key(period.start, "monthly"), bucket),
                    0,
                )
                for bucket in DURATION_BUCKETS
            },
        }
        for period in periods
    ]


def volumetrics_kpi_duration_buckets(db: Session, request: Any) -> dict[str, Any]:
    periods = latest_complete_month_periods(db, request.project_id, 3)
    months = [volumetrics_period_lookup_key(period.start, "monthly") for period in periods]
    return {
        "months": months,
        "incident": duration_bucket_rows_for_ticket_type(
            db,
            request,
            ticket_type="incident",
            completion_field="resolved_at",
        ),
        "sc_task": duration_bucket_rows_for_ticket_type(
            db,
            request,
            ticket_type="sc_task",
            completion_field="closed_at",
        ),
    }


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
            Ticket.customer_name,
        ),
        "towers": distinct_values_for_column(
            db,
            filters,
            Ticket.tower_name,
        ),
        "clusters": distinct_values_for_column(
            db,
            filters,
            Ticket.cluster_name,
        ),
        "application_groups": distinct_values_for_column(
            db,
            filters,
            Ticket.application_group_name,
        ),
        "application_names": distinct_values_for_column(
            db,
            filters,
            Ticket.application_name,
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
        "functional_tracks": distinct_values_for_column(db, filters, Ticket.functional_track),
        "ams_owners": distinct_values_for_column(db, filters, Ticket.ams_owner),
        "supported_by_vendors": distinct_values_for_column(
            db,
            filters,
            Ticket.supported_by_vendor,
        ),
        "support_leads": distinct_values_for_column(db, filters, Ticket.support_lead),
        "application_owners": distinct_values_for_column(db, filters, Ticket.application_owner),
        "business_service_ci_names": distinct_values_for_column(
            db,
            filters,
            Ticket.business_service_ci_name,
        ),
        "parent_application_names": distinct_values_for_column(
            db,
            filters,
            Ticket.parent_application_name,
        ),
    }
