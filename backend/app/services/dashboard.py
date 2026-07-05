from __future__ import annotations

import calendar
import math
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, time, timedelta
from enum import StrEnum
from time import perf_counter
from typing import Any
from uuid import UUID

from sqlalchemy import Float, and_, case, cast, func, literal, or_, select, union_all
from sqlalchemy.orm import Session

from app.models import (
    ApplicationInventoryItem,
    AssessmentOutOfScopeProblemRecord,
    AssessmentOutOfScopeTicket,
    AssessmentProblemRecord,
    Client,
    DashboardFilterFact,
    IncidentSlaRow,
    Project,
    Ticket,
    TicketRawRow,
)
from app.services.assignment_group_master_reference import (
    active_assignment_group_master_manager_map,
    assignment_group_master_reference_status,
)
from app.services.dashboard_assignment_groups import (
    basis_security_assignment_group_condition,
    is_basis_security_assignment_group,
    normalized_assignment_group_expression,
)
from app.services.dashboard_filter_facts import ensure_dashboard_filter_facts

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
    "hosting_env": ApplicationInventoryItem.hosting_env,
    "global_application": ApplicationInventoryItem.global_application,
    "scope_status": ApplicationInventoryItem.scope_status,
    "lifecycle_stage_status": ApplicationInventoryItem.lifecycle_stage_status,
    "lifecycle_current": ApplicationInventoryItem.lifecycle_current,
    "lifecycle_1_to_3_years": ApplicationInventoryItem.lifecycle_1_to_3_years,
    "lifecycle_3_to_5_years": ApplicationInventoryItem.lifecycle_3_to_5_years,
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
    "scope_status",
    "parent_application_name",
    "assignment_group",
    "sap_non_sap",
    "assignment_group_owner",
    "application_owner",
    "support_lead",
    "functional_track",
    "ams_owner",
    "supported_by_vendor",
    "hosting_env",
    "global_application",
    "lifecycle_stage_status",
    "lifecycle_current",
    "lifecycle_1_to_3_years",
    "lifecycle_3_to_5_years",
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
    "application_scope": "scope_status",
    "parent_application_name": "parent_application_name",
    "application_owner": "application_owner",
    "supported_by_vendor": "supported_by_vendor",
    "sap_non_sap": "sap_non_sap",
    "architecture_type": "architecture_type",
    "application_type": "app_type",
    "business_critical": "biz_criticality",
    "install_status": "install_status",
    "install_type": "install_type",
    "hosting_env": "hosting_env",
}

APPLICATION_CRITICALITY_ORDER = ("Very Critical", "Critical", "High", "Medium", "Low")
APPLICATION_SCOPE_ORDER = ("in_scope", "out_of_scope")
APPLICATION_GLOBAL_LOCAL_ORDER = ("Global", "Local")
APPLICATION_LIFECYCLE_PLAN_ORDER = ("Invest", "Disinvest", "Maintain", "Retired")
APPLICATION_LIFECYCLE_HORIZONS = (
    ("Current", "lifecycle_current"),
    ("1 to 3 years", "lifecycle_1_to_3_years"),
    ("3 to 5 years", "lifecycle_3_to_5_years"),
)

COMBINED_APPLICATION_FILTER_FIELDS = {
    "functional_track_ams_owner": ("functional_track", "ams_owner"),
    "assignment_group_owner": ("assignment_group", "assignment_group_owner"),
    "lifecycle_status_stage": ("lifecycle_status", "lifecycle_stage_status"),
}

APPLICATION_FILTER_CUSTOM_SORTS = {
    "application_scope": APPLICATION_SCOPE_ORDER,
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
VOLUMETRICS_AGREEMENT_MODES = {"sla", "ola"}
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
    "architecture_type": "architecture_type",
    "business_critical": "business_critical",
    "install_type": "install_type",
}

COMBINED_VOLUMETRICS_FILTER_FIELDS = {
    "functional_track_ams_owner": ("functional_track", "ams_owner"),
    "assignment_group_support_lead": ("assignment_group", "support_lead"),
}

FACT_SINGLE_VOLUMETRICS_FILTER_FIELDS = {
    "parent_application_name": "parent_business_application",
    "application_owner": "application_owner",
    "supported_by_vendor": "supported_by_vendor",
    "sap_non_sap": "sap_non_sap",
    "architecture_type": "architecture_type",
    "business_critical": "business_critical",
    "install_type": "install_type",
}

FACT_COMBINED_VOLUMETRICS_FILTER_FIELDS = {
    "functional_track_ams_owner": (
        "functional_track",
        "ams_owner",
        "functional_track_ams_owner",
    ),
    "assignment_group_support_lead": (
        "assignment_group",
        "support_group_owner",
        "assignment_group_support_owner",
    ),
}

FACT_TICKET_TYPE_VALUES = {
    "incident": "incident",
    "sc_task": "sc_task",
}

VOLUMETRICS_FILTER_CUSTOM_SORTS = {
    "business_critical": APPLICATION_CRITICALITY_ORDER,
}

SC_TASK_CATALOG_PERIODS = (
    (
        "H1_2025",
        "H1 2025",
        datetime(2025, 1, 1, tzinfo=UTC),
        datetime(2025, 7, 1, tzinfo=UTC),
    ),
    (
        "H2_2025",
        "H2 2025",
        datetime(2025, 7, 1, tzinfo=UTC),
        datetime(2026, 1, 1, tzinfo=UTC),
    ),
    (
        "H1_2026",
        "H1 2026",
        datetime(2026, 1, 1, tzinfo=UTC),
        datetime(2026, 7, 1, tzinfo=UTC),
    ),
)

ASSIGNMENT_GROUP_VOLUMETRICS_DEFAULT_MONTHS = ("2025-12", "2026-05")
ASSIGNMENT_GROUP_MAPPING_SOURCES = {"application_inventory", "tickets"}
ASSIGNMENT_GROUP_MAPPING_SCOPES = {"in_scope", "out_of_scope", "all"}
UNMAPPED_ASSIGNMENT_GROUP_LABEL = "Unmapped Assignment Group"
UNMAPPED_FUNCTIONAL_TRACK_LABEL = "Unmapped Functional Track"
UNMAPPED_PARENT_APPLICATION_LABEL = "Unmapped Parent Business Application"
UNMAPPED_BUSINESS_SERVICE_CI_LABEL = "Unmapped Business Service CI"
REFERENCE_MISSING_LABEL = "-"
MULTIPLE_REFERENCE_LABEL = "Multiple"


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


def normalized_state_expression(model: Any) -> Any:
    return func.lower(func.trim(func.coalesce(model.state, "")))


def cancelled_or_canceled_state_condition(model: Any) -> Any:
    return normalized_state_expression(model).like("%cancel%")


def sc_task_closed_incomplete_state_condition(model: Any) -> Any:
    return and_(
        func.upper(model.ticket_type) == "SERVICE_CATALOG_TASK",
        normalized_state_expression(model) == "closed incomplete",
    )


def valid_resolved_closed_state_condition(model: Any) -> Any:
    return and_(
        ~cancelled_or_canceled_state_condition(model),
        ~sc_task_closed_incomplete_state_condition(model),
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
            valid_resolved_closed_state_condition(Ticket),
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
        ApplicationInventoryItem.is_current.is_(True),
        ApplicationInventoryItem.active.is_(True),
    )
    inventory_row = db.execute(inventory_statement).mappings().one()

    completion_expression = effective_completion_expression()
    range_statement = select(
        func.min(completion_expression).label("completion_date_min"),
        func.max(completion_expression).label("completion_date_max"),
    ).where(
        Ticket.project_id == project_id,
        valid_resolved_closed_state_condition(Ticket),
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
                valid_resolved_closed_state_condition(Ticket),
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


def normalized_text_expression(expression: Any) -> Any:
    return func.lower(func.trim(func.coalesce(expression, literal(""))))


def application_lifecycle_stage_status_in_use_condition() -> Any:
    lifecycle_stage_status = application_field_expression("lifecycle_stage_status")
    return normalized_text_expression(lifecycle_stage_status) == "in use"


def canonical_lifecycle_plan_expression(expression: Any) -> Any:
    normalized_expression = normalized_text_expression(expression)
    return case(
        (normalized_expression == "invest", literal("Invest")),
        (normalized_expression == "disinvest", literal("Disinvest")),
        (normalized_expression == "maintain", literal("Maintain")),
        (normalized_expression == "retired", literal("Retired")),
        else_=None,
    )


def normalize_lifecycle_plan(value: Any) -> str:
    normalized_value = normalize_custom_sort_text(value)
    for plan in APPLICATION_LIFECYCLE_PLAN_ORDER:
        if normalized_value == normalize_custom_sort_text(plan):
            return plan
    return APPLICATION_LIFECYCLE_PLAN_ORDER[0]


def canonical_lifecycle_plan_value(value: Any) -> str | None:
    normalized_value = normalize_custom_sort_text(value)
    for plan in APPLICATION_LIFECYCLE_PLAN_ORDER:
        if normalized_value == normalize_custom_sort_text(plan):
            return plan
    return None


def applications_base_conditions(project_id: UUID) -> list[Any]:
    return [
        ApplicationInventoryItem.project_id == project_id,
        ApplicationInventoryItem.is_current.is_(True),
        ApplicationInventoryItem.active.is_(True),
    ]


def applications_business_service_detail_conditions(
    project_id: UUID,
    filters: Any,
    *,
    excluded_filter_name: str | None = None,
) -> list[Any]:
    service_expression = nonblank_text_expression(ApplicationInventoryItem.business_service_ci_name)
    return [
        *applications_filter_conditions(
            project_id,
            filters,
            excluded_filter_name=excluded_filter_name,
        ),
        service_expression.is_not(None),
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
        "application_scope": distinct_application_filter_values(
            db,
            project_id,
            "scope_status",
            filter_name="application_scope",
        ),
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
        "hosting_env": distinct_application_filter_values(db, project_id, "hosting_env"),
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
        "application_scope": application_filter_value_count_rows(
            db,
            request,
            "application_scope",
            "scope_status",
        ),
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
        "hosting_env": application_filter_value_count_rows(
            db,
            request,
            "hosting_env",
            "hosting_env",
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
    conditions = applications_business_service_detail_conditions(request.project_id, filters)
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
    conditions = applications_business_service_detail_conditions(
        request.project_id,
        request.filters,
    )
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
        .where(
            *applications_business_service_detail_conditions(
                request.project_id,
                request.filters,
            )
        )
        .group_by(expression)
        .order_by(func.count(ApplicationInventoryItem.id).desc(), expression.asc())
    )
    return [
        {"label": row.label, "count": int(row.count or 0)}
        for row in db.execute(statement).all()
    ]


def applications_criticality_hosting_pivot(db: Session, request: Any) -> dict[str, Any]:
    service_expression = nonblank_text_expression(ApplicationInventoryItem.business_service_ci_name)
    criticality_label = nonblank_text_expression(application_field_expression("biz_criticality"))
    hosting_label = nonblank_text_expression(application_field_expression("hosting_env"))
    statement = (
        select(
            criticality_label.label("business_criticality"),
            hosting_label.label("hosting_env"),
            func.count(func.distinct(service_expression)).label("application_count"),
        )
        .where(
            *applications_filter_conditions(request.project_id, request.filters),
            application_lifecycle_stage_status_in_use_condition(),
            criticality_label.is_not(None),
            hosting_label.is_not(None),
            service_expression.is_not(None),
        )
        .group_by(criticality_label, hosting_label)
    )
    result_rows = db.execute(statement).mappings().all()
    values_by_key: dict[tuple[str, str], int] = {}
    row_totals: dict[str, int] = {}
    column_totals: dict[str, int] = {}
    for row in result_rows:
        criticality = str(row["business_criticality"])
        hosting_env = str(row["hosting_env"])
        count = int(row["application_count"] or 0)
        values_by_key[(criticality, hosting_env)] = count
        row_totals[criticality] = row_totals.get(criticality, 0) + count
        column_totals[hosting_env] = column_totals.get(hosting_env, 0) + count

    criticality_rank = {
        label.casefold(): index for index, label in enumerate(APPLICATION_CRITICALITY_ORDER)
    }
    criticality_rows = sorted(
        row_totals,
        key=lambda label: (
            criticality_rank.get(label.casefold(), len(APPLICATION_CRITICALITY_ORDER)),
            -row_totals[label],
            label.casefold(),
        ),
    )
    hosting_columns = sorted(
        column_totals,
        key=lambda label: (-column_totals[label], label.casefold()),
    )
    rows: list[dict[str, Any]] = []
    for criticality in criticality_rows:
        counts = {
            hosting_env: values_by_key.get((criticality, hosting_env), 0)
            for hosting_env in hosting_columns
        }
        row_total = sum(counts.values())
        rows.append(
            {
                "business_criticality": criticality,
                "counts": counts,
                "total": row_total,
            },
        )

    return {
        "rows": criticality_rows,
        "columns": hosting_columns,
        "values": rows,
        "column_totals": {
            hosting_env: column_totals[hosting_env] for hosting_env in hosting_columns
        },
        "grand_total": sum(column_totals.values()),
    }


def applications_global_local(db: Session, request: Any) -> list[dict[str, Any]]:
    service_expression = nonblank_text_expression(ApplicationInventoryItem.business_service_ci_name)
    global_expression = application_field_expression("global_application")
    normalized_global = func.lower(func.trim(func.coalesce(global_expression, literal(""))))
    global_label = case(
        (normalized_global == "yes", literal("Global")),
        (normalized_global == "no", literal("Local")),
        else_=None,
    )
    statement = (
        select(
            global_label.label("label"),
            func.count(func.distinct(service_expression)).label("count"),
        )
        .where(
            *applications_filter_conditions(request.project_id, request.filters),
            global_label.is_not(None),
            service_expression.is_not(None),
        )
        .group_by(global_label)
    )
    counts = {
        str(row["label"]): int(row["count"] or 0)
        for row in db.execute(statement).mappings().all()
    }
    return [
        {"label": label, "count": counts.get(label, 0)}
        for label in APPLICATION_GLOBAL_LOCAL_ORDER
    ]


def applications_charts(db: Session, request: Any) -> dict[str, Any]:
    lifecycle_selected = bool(
        selected_application_filter_values(request.filters, "lifecycle_status_stage"),
    )
    return {
        "lifecycle_stage": []
        if lifecycle_selected
        else applications_chart_counts(db, request, "lifecycle_stage_status"),
        "architecture_type": applications_chart_counts(db, request, "architecture_type"),
        "install_type": applications_chart_counts(db, request, "install_type"),
        "hosting_env": applications_chart_counts(db, request, "hosting_env"),
        "strategic": applications_chart_counts(db, request, "strategic"),
        "criticality_hosting_pivot": applications_criticality_hosting_pivot(db, request),
        "global_local_applications": applications_global_local(db, request),
    }


def applications_top_active_users(db: Session, request: Any) -> dict[str, Any]:
    top_n = normalized_top_n(getattr(request, "top_n", 10))
    parent_expression = nonblank_text_expression(ApplicationInventoryItem.parent_application_name)
    distinct_pairs = (
        select(
            parent_expression.label("parent_application_name"),
            ApplicationInventoryItem.active_users.label("active_users"),
        )
        .where(
            *applications_filter_conditions(request.project_id, request.filters),
            parent_expression.is_not(None),
            ApplicationInventoryItem.active_users.is_not(None),
            ApplicationInventoryItem.active_users > 0,
        )
        .distinct()
        .subquery("distinct_parent_active_users")
    )
    statement = (
        select(
            distinct_pairs.c.parent_application_name.label("parent_application_name"),
            func.max(distinct_pairs.c.active_users).label("active_users"),
            func.count(distinct_pairs.c.active_users).label("active_user_value_count"),
        )
        .group_by(distinct_pairs.c.parent_application_name)
        .order_by(
            func.max(distinct_pairs.c.active_users).desc(),
            distinct_pairs.c.parent_application_name.asc(),
        )
    )
    rows = db.execute(statement).mappings().all()
    duplicate_parent_count = sum(
        1 for row in rows if int(row["active_user_value_count"] or 0) > 1
    )
    points = [
        {
            "application_name": str(row["parent_application_name"]),
            "parent_application_name": str(row["parent_application_name"]),
            "active_users": int(row["active_users"] or 0),
        }
        for row in rows[:top_n]
    ]
    return {
        "top_n": top_n,
        "duplicate_parent_active_user_count": duplicate_parent_count,
        "points": points,
    }


def applications_lifecycle_matrix_counts(db: Session, request: Any) -> dict[tuple[str, str], int]:
    service_expression = nonblank_text_expression(ApplicationInventoryItem.business_service_ci_name)
    selects = []
    for horizon_label, field_name in APPLICATION_LIFECYCLE_HORIZONS:
        field_expression = application_field_expression(field_name)
        plan_expression = canonical_lifecycle_plan_expression(field_expression)
        selects.append(
            select(
                service_expression.label("business_service_ci_name"),
                literal(horizon_label).label("horizon"),
                plan_expression.label("plan"),
            ).where(
                *applications_filter_conditions(request.project_id, request.filters),
                application_lifecycle_stage_status_in_use_condition(),
                service_expression.is_not(None),
                plan_expression.is_not(None),
            ),
        )
    lifecycle_rows = union_all(*selects).subquery("application_lifecycle_planning_rows")
    statement = (
        select(
            lifecycle_rows.c.plan.label("plan"),
            lifecycle_rows.c.horizon.label("horizon"),
            func.count(func.distinct(lifecycle_rows.c.business_service_ci_name)).label(
                "application_count",
            ),
        )
        .group_by(lifecycle_rows.c.plan, lifecycle_rows.c.horizon)
        .order_by(lifecycle_rows.c.plan, lifecycle_rows.c.horizon)
    )
    return {
        (str(row["plan"]), str(row["horizon"])): int(row["application_count"] or 0)
        for row in db.execute(statement).mappings().all()
    }


def lifecycle_planning_matrix_from_counts(
    counts_by_plan_horizon: dict[tuple[str, str], int],
    *,
    in_use_application_count: int,
) -> dict[str, Any]:
    horizon_labels = [label for label, _field_name in APPLICATION_LIFECYCLE_HORIZONS]
    rows: list[dict[str, Any]] = []
    for plan in APPLICATION_LIFECYCLE_PLAN_ORDER:
        counts = {
            horizon: counts_by_plan_horizon.get((plan, horizon), 0)
            for horizon in horizon_labels
        }
        rows.append(
            {
                "plan": plan,
                "counts": counts,
            },
        )
    return {
        "plans": list(APPLICATION_LIFECYCLE_PLAN_ORDER),
        "horizons": horizon_labels,
        "rows": rows,
        "in_use_application_count": in_use_application_count,
    }


def applications_lifecycle_in_use_count(db: Session, request: Any) -> int:
    service_expression = nonblank_text_expression(ApplicationInventoryItem.business_service_ci_name)
    statement = select(func.count(func.distinct(service_expression))).where(
        *applications_filter_conditions(request.project_id, request.filters),
        application_lifecycle_stage_status_in_use_condition(),
        service_expression.is_not(None),
    )
    return int(db.scalar(statement) or 0)


def lifecycle_selected_plan_conditions(selected_plan: str) -> list[Any]:
    return [
        canonical_lifecycle_plan_expression(application_field_expression(field_name))
        == selected_plan
        for _horizon_label, field_name in APPLICATION_LIFECYCLE_HORIZONS
    ]


def lifecycle_planning_selected_applications(
    db: Session,
    request: Any,
    selected_plan: str,
) -> list[dict[str, Any]]:
    service_expression = nonblank_text_expression(ApplicationInventoryItem.business_service_ci_name)
    columns = [
        application_display_expression("business_service_ci_name").label("business_service_ci_name"),
        application_display_expression("parent_application_name").label(
            "parent_business_application",
        ),
        application_display_expression("functional_track").label("functional_track"),
        application_display_expression("ams_owner").label("ams_owner"),
        application_display_expression("application_owner").label("application_owner"),
        application_display_expression("supported_by_vendor").label("supported_by_vendor"),
        application_display_expression("install_type").label("install_type"),
        application_display_expression("biz_criticality").label("business_criticality"),
        application_display_expression("architecture_type").label("architecture_type"),
        application_display_expression("app_type").label("application_type"),
        application_display_expression("hosting_env").label("hosting_env"),
        application_display_expression("global_application").label("global_application"),
        application_display_expression("active_users").label("active_users"),
        application_display_expression("lifecycle_current").label("lifecycle_current"),
        application_display_expression("lifecycle_1_to_3_years").label("lifecycle_1_to_3_years"),
        application_display_expression("lifecycle_3_to_5_years").label("lifecycle_3_to_5_years"),
    ]
    statement = (
        select(*columns)
        .where(
            *applications_filter_conditions(request.project_id, request.filters),
            application_lifecycle_stage_status_in_use_condition(),
            service_expression.is_not(None),
            or_(*lifecycle_selected_plan_conditions(selected_plan)),
        )
        .order_by(
            application_display_expression("business_service_ci_name").asc(),
            application_display_expression("parent_application_name").asc(),
        )
    )
    unique_rows: dict[str, dict[str, Any]] = {}
    for row in db.execute(statement).mappings().all():
        row_dict = dict(row)
        service_name = str(row_dict["business_service_ci_name"])
        service_key = normalize_custom_sort_text(service_name)
        selected_horizons = [
            horizon_label
            for horizon_label, field_name in APPLICATION_LIFECYCLE_HORIZONS
            if canonical_lifecycle_plan_value(row_dict.get(field_name)) == selected_plan
        ]
        if service_key not in unique_rows:
            row_dict["selected_plan_horizons"] = selected_horizons
            unique_rows[service_key] = row_dict
            continue
        existing_horizons = unique_rows[service_key]["selected_plan_horizons"]
        for horizon in selected_horizons:
            if horizon not in existing_horizons:
                existing_horizons.append(horizon)

    criticality_rank = {
        label.casefold(): index for index, label in enumerate(APPLICATION_CRITICALITY_ORDER)
    }
    return sorted(
        unique_rows.values(),
        key=lambda row: (
            criticality_rank.get(
                str(row.get("business_criticality", "")).casefold(),
                len(APPLICATION_CRITICALITY_ORDER),
            ),
            normalize_custom_sort_text(row.get("functional_track")),
            normalize_custom_sort_text(row.get("parent_business_application")),
            normalize_custom_sort_text(row.get("business_service_ci_name")),
        ),
    )


def applications_lifecycle_planning(db: Session, request: Any) -> dict[str, Any]:
    selected_plan = normalize_lifecycle_plan(getattr(request, "selected_plan", "Invest"))
    counts_by_plan_horizon = applications_lifecycle_matrix_counts(db, request)
    matrix = lifecycle_planning_matrix_from_counts(
        counts_by_plan_horizon,
        in_use_application_count=applications_lifecycle_in_use_count(db, request),
    )
    chart = [
        {
            "horizon": horizon,
            "count": counts_by_plan_horizon.get((selected_plan, horizon), 0),
        }
        for horizon, _field_name in APPLICATION_LIFECYCLE_HORIZONS
    ]
    applications = lifecycle_planning_selected_applications(db, request, selected_plan)
    return {
        "matrix": matrix,
        "selected_plan": {
            "plan": selected_plan,
            "chart": chart,
            "applications": applications,
            "application_count": len(applications),
        },
    }


def validation_display_expression(expression: Any, label: str) -> Any:
    return func.coalesce(nonblank_text_expression(expression), literal(label))


def reference_display_expression(expression: Any) -> Any:
    return validation_display_expression(expression, REFERENCE_MISSING_LABEL)


def display_reference_value(values: set[str], fallback: str | None = None) -> str:
    clean_values = {
        str(value).strip()
        for value in values
        if value and str(value).strip() and str(value).strip() != REFERENCE_MISSING_LABEL
    }
    if len(clean_values) == 1:
        return next(iter(clean_values))
    if len(clean_values) > 1:
        return MULTIPLE_REFERENCE_LABEL
    return fallback or REFERENCE_MISSING_LABEL


def display_assignment_group_value(values: set[str], fallback: str) -> str:
    clean_values = {str(value).strip() for value in values if value and str(value).strip()}
    if clean_values:
        return sorted(clean_values, key=lambda value: (value.casefold(), value))[0]
    return fallback


def display_reference_value_without_multiple(values: set[str], fallback: str | None = None) -> str:
    value = display_reference_value(values, fallback)
    return REFERENCE_MISSING_LABEL if value == MULTIPLE_REFERENCE_LABEL else value


def inventory_assignment_group_reference_map(
    db: Session,
    project_id: UUID,
) -> dict[tuple[str, str], dict[str, str]]:
    assignment_key_expression = normalized_assignment_group_expression(
        ApplicationInventoryItem.assignment_group,
    )
    scope_expression = application_inventory_scope_expression()
    statement = (
        select(
            assignment_key_expression.label("assignment_group_key"),
            scope_expression.label("scope"),
            reference_display_expression(ApplicationInventoryItem.functional_track).label(
                "functional_track",
            ),
            reference_display_expression(ApplicationInventoryItem.ams_owner).label("ams_owner"),
            reference_display_expression(ApplicationInventoryItem.support_lead).label(
                "support_lead",
            ),
        )
        .where(
            ApplicationInventoryItem.project_id == project_id,
            ApplicationInventoryItem.is_current.is_(True),
            assignment_key_expression != "",
        )
        .group_by(
            assignment_key_expression,
            scope_expression,
            ApplicationInventoryItem.functional_track,
            ApplicationInventoryItem.ams_owner,
            ApplicationInventoryItem.support_lead,
        )
    )
    grouped: dict[tuple[str, str], dict[str, set[str]]] = {}
    for row in db.execute(statement).mappings().all():
        key = (str(row["scope"]), str(row["assignment_group_key"]))
        entry = grouped.setdefault(
            key,
            {"functional_track": set(), "ams_owner": set(), "support_lead": set()},
        )
        entry["functional_track"].add(str(row["functional_track"] or ""))
        entry["ams_owner"].add(str(row["ams_owner"] or ""))
        entry["support_lead"].add(str(row["support_lead"] or ""))

    return {
        key: {
            "functional_track": display_reference_value(values["functional_track"]),
            "ams_owner": display_reference_value(values["ams_owner"]),
            "support_lead": display_reference_value(values["support_lead"]),
        }
        for key, values in grouped.items()
    }


def assignment_group_reference_for_row(
    row: dict[str, Any],
    reference_map: dict[tuple[str, str], dict[str, str]],
    master_manager_map: dict[str, str] | None = None,
    *,
    allow_multiple: bool = True,
) -> dict[str, str]:
    scope = str(row.get("scope") or "in_scope")
    assignment_key = str(row.get("assignment_group_key") or "")
    fallback = reference_map.get((scope, assignment_key), {})
    app_inventory_support_lead = fallback.get("support_lead")
    support_lead_fallback = (
        app_inventory_support_lead
        if app_inventory_support_lead and app_inventory_support_lead != REFERENCE_MISSING_LABEL
        else (master_manager_map or {}).get(assignment_key)
    )
    display = (
        display_reference_value
        if allow_multiple
        else display_reference_value_without_multiple
    )
    return {
        "functional_track": display(
            {str(row.get("functional_track") or "")},
            fallback.get("functional_track"),
        ),
        "ams_owner": display(
            {str(row.get("ams_owner") or "")},
            fallback.get("ams_owner"),
        ),
        "support_lead": display(
            {str(row.get("support_lead") or "")},
            support_lead_fallback,
        ),
    }


def assignment_group_mapping_with_basis_split(
    rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    regular_rows: list[dict[str, Any]] = []
    basis_security_rows: list[dict[str, Any]] = []
    for row in rows:
        if row.get("scope") == "out_of_scope" and is_basis_security_assignment_group(
            row.get("assignment_group")
        ):
            basis_security_rows.append(row)
        else:
            regular_rows.append(row)
    return regular_rows, basis_security_rows


def normalize_assignment_mapping_source(value: str | None) -> str:
    normalized = (value or "application_inventory").strip().lower()
    if normalized not in ASSIGNMENT_GROUP_MAPPING_SOURCES:
        raise ValueError("Mapping source must be application_inventory or tickets")
    return normalized


def normalize_assignment_mapping_scope(value: str | None) -> str:
    normalized = (value or "in_scope").strip().lower()
    if normalized not in ASSIGNMENT_GROUP_MAPPING_SCOPES:
        raise ValueError("Scope must be in_scope, out_of_scope, or all")
    return normalized


def normalize_assignment_mapping_track(value: str | None) -> str:
    normalized = (value or "all").strip()
    return normalized if normalized else "all"


def assignment_mapping_search_condition(search: str | None, expressions: list[Any]) -> Any | None:
    search_value = (search or "").strip()
    if not search_value:
        return None
    pattern = f"%{search_value.lower()}%"
    return or_(*[func.lower(expression).like(pattern) for expression in expressions])


def application_inventory_scope_expression() -> Any:
    scope = normalized_text_expression(ApplicationInventoryItem.scope_status)
    return case(
        (scope == "in_scope", literal("in_scope")),
        else_=literal("out_of_scope"),
    )


def application_inventory_mapping_conditions(request: Any, scope_expression: Any) -> list[Any]:
    scope = normalize_assignment_mapping_scope(request.scope)
    conditions: list[Any] = [
        ApplicationInventoryItem.project_id == request.project_id,
        ApplicationInventoryItem.is_current.is_(True),
    ]
    if scope != "all":
        conditions.append(scope_expression == scope)
    return conditions


def application_assignment_mapping_tracks(db: Session, request: Any) -> list[str]:
    source = normalize_assignment_mapping_source(request.source)
    scope = normalize_assignment_mapping_scope(request.scope)
    if source == "application_inventory":
        scope_expression = application_inventory_scope_expression()
        track_expression = validation_display_expression(
            ApplicationInventoryItem.functional_track,
            UNMAPPED_FUNCTIONAL_TRACK_LABEL,
        )
        statement = (
            select(track_expression.label("functional_track"))
            .where(*application_inventory_mapping_conditions(request, scope_expression))
            .group_by(track_expression)
            .order_by(track_expression.asc())
        )
    else:
        ticket_source = volumetrics_source_subquery(request, scope_override=scope)
        track_expression = validation_display_expression(
            ticket_source.c.functional_track,
            UNMAPPED_FUNCTIONAL_TRACK_LABEL,
        )
        statement = (
            select(track_expression.label("functional_track"))
            .select_from(ticket_source)
            .where(ticket_source.c.ticket_type.in_(VOLUMETRICS_TICKET_TYPE_VALUES.values()))
            .group_by(track_expression)
            .order_by(track_expression.asc())
        )
    return [str(row["functional_track"]) for row in db.execute(statement).mappings().all()]


def applications_assignment_group_mapping(db: Session, request: Any) -> dict[str, Any]:
    source = normalize_assignment_mapping_source(request.source)
    scope = normalize_assignment_mapping_scope(request.scope)
    functional_track = normalize_assignment_mapping_track(request.functional_track)
    if source == "application_inventory":
        return applications_assignment_group_mapping_from_inventory(
            db,
            request,
            scope,
            functional_track,
        )
    return applications_assignment_group_mapping_from_tickets(
        db,
        request,
        scope,
        functional_track,
    )


def applications_assignment_group_mapping_from_inventory(
    db: Session,
    request: Any,
    scope: str,
    functional_track: str,
) -> dict[str, Any]:
    scope_expression = application_inventory_scope_expression()
    assignment_expression = validation_display_expression(
        ApplicationInventoryItem.assignment_group,
        UNMAPPED_ASSIGNMENT_GROUP_LABEL,
    )
    assignment_key_expression = normalized_assignment_group_expression(
        ApplicationInventoryItem.assignment_group,
    )
    filter_track_expression = validation_display_expression(
        ApplicationInventoryItem.functional_track,
        UNMAPPED_FUNCTIONAL_TRACK_LABEL,
    )
    track_expression = reference_display_expression(ApplicationInventoryItem.functional_track)
    ams_owner_expression = reference_display_expression(ApplicationInventoryItem.ams_owner)
    support_lead_expression = reference_display_expression(ApplicationInventoryItem.support_lead)
    parent_expression = reference_display_expression(
        ApplicationInventoryItem.parent_application_name
    )
    business_service_expression = reference_display_expression(
        ApplicationInventoryItem.business_service_ci_name
    )
    application_number_expression = reference_display_expression(
        ApplicationInventoryItem.application_number_apm
    )
    application_owner_expression = reference_display_expression(
        ApplicationInventoryItem.application_owner
    )
    supported_vendor_expression = reference_display_expression(
        ApplicationInventoryItem.supported_by_vendor
    )
    conditions = application_inventory_mapping_conditions(request, scope_expression)
    if functional_track != "all":
        conditions.append(filter_track_expression == functional_track)
    search_condition = assignment_mapping_search_condition(
        request.search,
        [
            assignment_expression,
            track_expression,
            parent_expression,
            business_service_expression,
            application_number_expression,
            application_owner_expression,
            supported_vendor_expression,
            scope_expression,
        ],
    )
    if search_condition is not None:
        conditions.append(search_condition)

    statement = (
        select(
            assignment_expression.label("assignment_group"),
            assignment_key_expression.label("assignment_group_key"),
            track_expression.label("functional_track"),
            ams_owner_expression.label("ams_owner"),
            support_lead_expression.label("support_lead"),
            parent_expression.label("parent_business_application"),
            business_service_expression.label("business_service_ci_name"),
            application_number_expression.label("application_number"),
            application_owner_expression.label("application_owner"),
            supported_vendor_expression.label("supported_by_vendor"),
            scope_expression.label("scope"),
            func.count(ApplicationInventoryItem.id).label("row_count"),
        )
        .where(*conditions)
        .group_by(
            assignment_expression,
            assignment_key_expression,
            track_expression,
            ams_owner_expression,
            support_lead_expression,
            parent_expression,
            business_service_expression,
            application_number_expression,
            application_owner_expression,
            supported_vendor_expression,
            scope_expression,
        )
        .order_by(
            assignment_expression.asc(),
            parent_expression.asc(),
            business_service_expression.asc(),
        )
    )
    rows = [
        {
            "assignment_group": row["assignment_group"],
            "assignment_group_key": row["assignment_group_key"],
            "functional_track": row["functional_track"],
            "ams_owner": row["ams_owner"],
            "support_lead": row["support_lead"],
            "parent_business_application": row["parent_business_application"],
            "business_service_ci_name": row["business_service_ci_name"],
            "application_number": row["application_number"],
            "application_owner": row["application_owner"],
            "supported_by_vendor": row["supported_by_vendor"],
            "scope": row["scope"],
            "incident_count": None,
            "sc_task_count": None,
            "total_ticket_count": None,
            "avg_monthly_incidents": None,
            "avg_monthly_sc_tasks": None,
            "avg_monthly_total_tickets": None,
        }
        for row in db.execute(statement).mappings().all()
    ]
    rows, basis_security_rows = assignment_group_mapping_with_basis_split(rows)
    summary = assignment_group_mapping_summary(rows)
    summary["basis_security_mapping_count"] = len(basis_security_rows)
    return {
        "source": "application_inventory",
        "scope": scope,
        "functional_track": functional_track,
        "available_functional_tracks": application_assignment_mapping_tracks(db, request),
        "summary": summary,
        "rows": rows,
        "basis_security_rows": basis_security_rows,
        "volume_period": None,
        "data_notes": [
            "Application Inventory source shows configured assignment group to application "
            "mapping.",
            "Application Inventory remains the source for application attributes.",
            "BASIS and SECURITY assignment groups are confirmed out-of-scope and shown "
            "separately when present.",
            "BASIS/SECURITY classification uses a case-insensitive contains match on "
            "assignment group name.",
        ],
        "warnings": [],
    }


def applications_assignment_group_mapping_from_tickets(
    db: Session,
    request: Any,
    scope: str,
    functional_track: str,
) -> dict[str, Any]:
    source = volumetrics_source_subquery(request, scope_override=scope)
    assignment_expression = validation_display_expression(
        source.c.assignment_group,
        UNMAPPED_ASSIGNMENT_GROUP_LABEL,
    )
    assignment_key_expression = normalized_assignment_group_expression(source.c.assignment_group)
    filter_track_expression = validation_display_expression(
        source.c.functional_track,
        UNMAPPED_FUNCTIONAL_TRACK_LABEL,
    )
    track_expression = reference_display_expression(source.c.functional_track)
    ams_owner_expression = reference_display_expression(source.c.ams_owner)
    support_lead_expression = reference_display_expression(source.c.support_lead)
    parent_expression = validation_display_expression(
        source.c.parent_application_name,
        UNMAPPED_PARENT_APPLICATION_LABEL,
    )
    business_service_expression = validation_display_expression(
        source.c.business_service_ci_name,
        UNMAPPED_BUSINESS_SERVICE_CI_LABEL,
    )
    volume_period = assignment_group_mapping_volume_period()
    volume_period_conditions = (
        source.c.created_at.is_not(None),
        source.c.created_at >= volume_period["start_datetime"],
        source.c.created_at < volume_period["end_datetime"],
    )
    conditions: list[Any] = [
        source.c.ticket_type.in_(VOLUMETRICS_TICKET_TYPE_VALUES.values()),
        *volume_period_conditions,
    ]
    if functional_track != "all":
        conditions.append(filter_track_expression == functional_track)
    search_condition = assignment_mapping_search_condition(
        request.search,
        [
            assignment_expression,
            track_expression,
            parent_expression,
            business_service_expression,
            source.c.scope,
        ],
    )
    if search_condition is not None:
        conditions.append(search_condition)

    incident_count = func.count(source.c.id).filter(source.c.ticket_type == "INCIDENT")
    sc_task_count = func.count(source.c.id).filter(
        source.c.ticket_type == "SERVICE_CATALOG_TASK",
    )
    period_incident_count = func.count(source.c.id).filter(
        source.c.ticket_type == "INCIDENT",
        *volume_period_conditions,
    )
    period_sc_task_count = func.count(source.c.id).filter(
        source.c.ticket_type == "SERVICE_CATALOG_TASK",
        *volume_period_conditions,
    )
    statement = (
        select(
            assignment_expression.label("assignment_group"),
            assignment_key_expression.label("assignment_group_key"),
            track_expression.label("functional_track"),
            ams_owner_expression.label("ams_owner"),
            support_lead_expression.label("support_lead"),
            parent_expression.label("parent_business_application"),
            business_service_expression.label("business_service_ci_name"),
            source.c.scope.label("scope"),
            incident_count.label("incident_count"),
            sc_task_count.label("sc_task_count"),
            func.count(source.c.id).label("total_ticket_count"),
            period_incident_count.label("period_incident_count"),
            period_sc_task_count.label("period_sc_task_count"),
        )
        .select_from(source)
        .where(*conditions)
        .group_by(
            assignment_expression,
            assignment_key_expression,
            track_expression,
            ams_owner_expression,
            support_lead_expression,
            parent_expression,
            business_service_expression,
            source.c.scope,
        )
        .order_by(func.count(source.c.id).desc(), assignment_expression.asc())
    )
    reference_map = inventory_assignment_group_reference_map(db, request.project_id)
    master_manager_map = active_assignment_group_master_manager_map(db, request.project_id)
    rows = [
        {
            "assignment_group": row["assignment_group"],
            "assignment_group_key": row["assignment_group_key"],
            **assignment_group_reference_for_row(
                row,
                reference_map,
                master_manager_map,
                allow_multiple=False,
            ),
            "parent_business_application": row["parent_business_application"],
            "business_service_ci_name": row["business_service_ci_name"],
            "application_number": None,
            "application_owner": None,
            "supported_by_vendor": None,
            "scope": row["scope"],
            "incident_count": int_count(row["incident_count"]),
            "sc_task_count": int_count(row["sc_task_count"]),
            "total_ticket_count": int_count(row["total_ticket_count"]),
            "avg_monthly_incidents": rounded_average_monthly_count(
                int_count(row["period_incident_count"]),
                int(volume_period["months"]),
            ),
            "avg_monthly_sc_tasks": rounded_average_monthly_count(
                int_count(row["period_sc_task_count"]),
                int(volume_period["months"]),
            ),
            "avg_monthly_total_tickets": rounded_average_monthly_count(
                int_count(row["period_incident_count"]) + int_count(row["period_sc_task_count"]),
                int(volume_period["months"]),
            ),
        }
        for row in db.execute(statement).mappings().all()
    ]
    rows, basis_security_rows = assignment_group_mapping_with_basis_split(rows)
    summary = assignment_group_mapping_summary(rows)
    summary["basis_security_mapping_count"] = len(basis_security_rows)
    return {
        "source": "tickets",
        "scope": scope,
        "functional_track": functional_track,
        "available_functional_tracks": application_assignment_mapping_tracks(db, request),
        "summary": summary,
        "rows": rows,
        "basis_security_rows": basis_security_rows,
        "volume_period": {
            "from_month": volume_period["from_month"],
            "to_month": volume_period["to_month"],
            "months": volume_period["months"],
            "label": volume_period["label"],
        },
        "data_notes": [
            "Tickets Data source shows distinct mappings found in normalized Incident and "
            f"SC Task records created during {volume_period['label']}.",
            "Generic Tickets includes Incidents and SC Tasks only.",
            "Problems and Changes are excluded.",
            f"Ticket counts and average monthly volumes use {volume_period['label']}.",
            "BASIS and SECURITY assignment groups are confirmed out-of-scope and shown "
            "separately when present.",
            "BASIS/SECURITY classification uses a case-insensitive contains match on "
            "assignment group name.",
        ],
        "warnings": [],
    }


def assignment_group_mapping_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    incident_counts = [row.get("incident_count") for row in rows]
    has_ticket_counts = any(value is not None for value in incident_counts)
    incident_total = (
        sum(int_count(row.get("incident_count")) for row in rows) if has_ticket_counts else None
    )
    sc_task_total = (
        sum(int_count(row.get("sc_task_count")) for row in rows) if has_ticket_counts else None
    )
    return {
        "mapping_count": len(rows),
        "assignment_group_count": len({row["assignment_group"] for row in rows}),
        "business_service_ci_count": len({row["business_service_ci_name"] for row in rows}),
        "parent_business_application_count": len(
            {row["parent_business_application"] for row in rows},
        ),
        "incident_count": incident_total,
        "sc_task_count": sc_task_total,
        "total_ticket_count": (
            incident_total + sc_task_total
            if incident_total is not None and sc_task_total is not None
            else None
        ),
        "basis_security_mapping_count": 0,
    }


def parse_month_key(value: str, *, field_name: str) -> date:
    try:
        year_text, month_text = value.split("-", 1)
        year = int(year_text)
        month = int(month_text)
        if month < 1 or month > 12:
            raise ValueError
        return date(year, month, 1)
    except ValueError as exc:
        raise ValueError(f"{field_name} must use YYYY-MM format") from exc


def month_key_date_range(from_month: str, to_month: str) -> list[date]:
    start = parse_month_key(from_month, field_name="from_month")
    end = parse_month_key(to_month, field_name="to_month")
    if end < start:
        raise ValueError("to_month must be greater than or equal to from_month")
    months: list[date] = []
    current = start
    while current <= end:
        months.append(current)
        if len(months) > 24:
            raise ValueError("Month range cannot exceed 24 months")
        current = (
            date(current.year + 1, 1, 1)
            if current.month == 12
            else date(current.year, current.month + 1, 1)
        )
    return months


def month_label(month_start: date) -> str:
    return f"{month_start:%b}-{month_start:%y}"


def assignment_group_mapping_volume_period() -> dict[str, Any]:
    months = month_key_date_range(*ASSIGNMENT_GROUP_VOLUMETRICS_DEFAULT_MONTHS)
    return {
        "from_month": month_key(months[0]),
        "to_month": month_key(months[-1]),
        "months": len(months),
        "label": f"{month_label(months[0])} through {month_label(months[-1])}",
        "start_datetime": datetime.combine(months[0], time.min, tzinfo=UTC),
        "end_datetime": datetime.combine(next_month_start(months[-1]), time.min, tzinfo=UTC),
    }


def rounded_average_monthly_count(count: int, months: int) -> int:
    if months <= 0:
        return 0
    return int(math.floor((count / months) + 0.5))


def month_key(month_start: date) -> str:
    return f"{month_start:%Y-%m}"


def next_month_start(month_start: date) -> date:
    return (
        date(month_start.year + 1, 1, 1)
        if month_start.month == 12
        else date(month_start.year, month_start.month + 1, 1)
    )


def volumetrics_assignment_group_available_tracks(db: Session, request: Any) -> list[str]:
    source = volumetrics_source_subquery(request, scope_override=request.scope)
    track_expression = validation_display_expression(
        source.c.functional_track,
        UNMAPPED_FUNCTIONAL_TRACK_LABEL,
    )
    statement = (
        select(track_expression.label("functional_track"))
        .select_from(source)
        .where(source.c.ticket_type.in_(VOLUMETRICS_TICKET_TYPE_VALUES.values()))
        .group_by(track_expression)
        .order_by(track_expression.asc())
    )
    return [str(row["functional_track"]) for row in db.execute(statement).mappings().all()]


def assignment_group_volumetrics_category_expression(source: Any) -> Any:
    return case(
        (source.c.ticket_type == "INCIDENT", literal("incidents")),
        (source.c.ticket_type == "SERVICE_CATALOG_TASK", literal("sc_tasks")),
        else_=literal("other"),
    )


def assignment_group_volumetrics_event_rows(
    db: Session,
    source: Any,
    *,
    date_expression: Any,
    event_name: str,
    start_datetime: datetime,
    end_datetime: datetime,
    functional_track: str,
    extra_conditions: list[Any] | None = None,
) -> list[dict[str, Any]]:
    assignment_expression = validation_display_expression(
        source.c.assignment_group,
        UNMAPPED_ASSIGNMENT_GROUP_LABEL,
    )
    assignment_key_expression = normalized_assignment_group_expression(source.c.assignment_group)
    filter_track_expression = validation_display_expression(
        source.c.functional_track,
        UNMAPPED_FUNCTIONAL_TRACK_LABEL,
    )
    track_expression = reference_display_expression(source.c.functional_track)
    ams_owner_expression = reference_display_expression(source.c.ams_owner)
    support_lead_expression = reference_display_expression(source.c.support_lead)
    category_expression = assignment_group_volumetrics_category_expression(source)
    month_expression = func.to_char(func.date_trunc("month", date_expression), "YYYY-MM")
    basis_security_expression = case(
        (
            and_(
                source.c.scope == "out_of_scope",
                basis_security_assignment_group_condition(source.c.assignment_group),
            ),
            literal(True),
        ),
        else_=literal(False),
    )
    conditions: list[Any] = [
        source.c.ticket_type.in_(VOLUMETRICS_TICKET_TYPE_VALUES.values()),
        date_expression.is_not(None),
        date_expression >= start_datetime,
        date_expression < end_datetime,
    ]
    if functional_track != "all":
        conditions.append(filter_track_expression == functional_track)
    if extra_conditions:
        conditions.extend(extra_conditions)

    statement = (
        select(
            category_expression.label("ticket_category"),
            source.c.scope.label("scope"),
            assignment_expression.label("assignment_group"),
            assignment_key_expression.label("assignment_group_key"),
            track_expression.label("functional_track"),
            ams_owner_expression.label("ams_owner"),
            support_lead_expression.label("support_lead"),
            basis_security_expression.label("basis_security"),
            month_expression.label("month_key"),
            func.count(source.c.id).label("ticket_count"),
        )
        .select_from(source)
        .where(*conditions)
        .group_by(
            category_expression,
            source.c.scope,
            assignment_expression,
            assignment_key_expression,
            track_expression,
            ams_owner_expression,
            support_lead_expression,
            basis_security_expression,
            month_expression,
        )
    )
    return [
        {
            "ticket_category": row["ticket_category"],
            "scope": row["scope"],
            "assignment_group": row["assignment_group"],
            "assignment_group_key": row["assignment_group_key"],
            "functional_track": row["functional_track"],
            "ams_owner": row["ams_owner"],
            "support_lead": row["support_lead"],
            "basis_security": bool(row["basis_security"]),
            "month_key": row["month_key"],
            event_name: int_count(row["ticket_count"]),
        }
        for row in db.execute(statement).mappings().all()
    ]


def blank_month_metrics(months: list[date]) -> dict[str, dict[str, int]]:
    return {
        month_key(month): {"created": 0, "resolved": 0, "cancelled": 0}
        for month in months
    }


def add_assignment_group_volumetrics_event(
    store: dict[tuple[str, bool, str], dict[str, Any]],
    row: dict[str, Any],
    months: list[date],
    event_name: str,
) -> None:
    key = (
        row["ticket_category"],
        row["basis_security"],
        row["assignment_group_key"],
    )
    entry = store.setdefault(
        key,
        {
            "assignment_group": row["assignment_group"],
            "assignment_group_values": set(),
            "assignment_group_key": row["assignment_group_key"],
            "scopes": set(),
            "functional_track_values": set(),
            "ams_owner_values": set(),
            "support_lead_values": set(),
            "basis_security": row["basis_security"],
            "months": blank_month_metrics(months),
        },
    )
    entry["assignment_group_values"].add(row["assignment_group"])
    entry["scopes"].add(row["scope"])
    entry["functional_track_values"].add(row["functional_track"])
    entry["ams_owner_values"].add(row["ams_owner"])
    entry["support_lead_values"].add(row["support_lead"])
    if row["month_key"] in entry["months"]:
        entry["months"][row["month_key"]][event_name] += int_count(row[event_name])


def merge_assignment_group_volumetrics_rows(
    rows: list[dict[str, Any]],
    months: list[date],
) -> list[dict[str, Any]]:
    merged: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for row in rows:
        key = (
            str(row["assignment_group"]),
            str(row["functional_track"]),
            str(row["ams_owner"]),
            str(row["support_lead"]),
        )
        entry = merged.setdefault(
            key,
            {
                "assignment_group": row["assignment_group"],
                "functional_track": row["functional_track"],
                "ams_owner": row["ams_owner"],
                "support_lead": row["support_lead"],
                "months": blank_month_metrics(months),
                "totals": {"created": 0, "resolved": 0, "cancelled": 0},
            },
        )
        for current_month in months:
            current_key = month_key(current_month)
            for metric in ("created", "resolved", "cancelled"):
                entry["months"][current_key][metric] += int_count(
                    row["months"][current_key][metric],
                )
        for metric in ("created", "resolved", "cancelled"):
            entry["totals"][metric] += int_count(row["totals"][metric])
    return list(merged.values())


def build_assignment_group_volumetrics_table(
    title: str,
    rows: list[dict[str, Any]],
    months: list[date],
    reference_map: dict[tuple[str, str], dict[str, str]],
    master_manager_map: dict[str, str] | None = None,
) -> dict[str, Any]:
    output_rows: list[dict[str, Any]] = []
    for row in rows:
        assignment_group = display_assignment_group_value(
            row.get("assignment_group_values", set()),
            str(row["assignment_group"]),
        )
        scopes = row.get("scopes") or set()
        fallback_scope = next(iter(scopes)) if len(scopes) == 1 else ""
        fallback = reference_map.get((fallback_scope, row.get("assignment_group_key", "")), {})
        assignment_key = str(row.get("assignment_group_key", ""))
        app_inventory_support_lead = fallback.get("support_lead")
        support_lead_fallback = (
            app_inventory_support_lead
            if app_inventory_support_lead and app_inventory_support_lead != REFERENCE_MISSING_LABEL
            else (master_manager_map or {}).get(assignment_key)
        )
        totals = {
            "created": sum(row["months"][month_key(month)]["created"] for month in months),
            "resolved": sum(row["months"][month_key(month)]["resolved"] for month in months),
            "cancelled": sum(row["months"][month_key(month)]["cancelled"] for month in months),
        }
        output_rows.append(
            {
                "assignment_group": assignment_group,
                "functional_track": display_reference_value(
                    row.get("functional_track_values", set()),
                    fallback.get("functional_track"),
                ),
                "ams_owner": display_reference_value(
                    row.get("ams_owner_values", set()),
                    fallback.get("ams_owner"),
                ),
                "support_lead": display_reference_value(
                    row.get("support_lead_values", set()),
                    support_lead_fallback,
                ),
                "months": row["months"],
                "totals": totals,
            },
        )
    output_rows = merge_assignment_group_volumetrics_rows(output_rows, months)
    output_rows.sort(
        key=lambda item: (
            -int_count(item["totals"]["created"]),
            str(item["assignment_group"]).casefold(),
            str(item["functional_track"]).casefold(),
            str(item["ams_owner"]).casefold(),
            str(item["support_lead"]).casefold(),
        ),
    )
    return {
        "title": title,
        "rows": output_rows,
        "grand_totals": {
            "created": sum(int_count(row["totals"]["created"]) for row in output_rows),
            "resolved": sum(int_count(row["totals"]["resolved"]) for row in output_rows),
            "cancelled": sum(int_count(row["totals"]["cancelled"]) for row in output_rows),
        },
    }


def volumetrics_assignment_group_volumetrics(db: Session, request: Any) -> dict[str, Any]:
    scope = normalize_volumetrics_scope(request.scope)
    functional_track = normalize_assignment_mapping_track(request.functional_track)
    months = month_key_date_range(request.from_month, request.to_month)
    start_datetime = datetime.combine(months[0], time.min, tzinfo=UTC)
    end_datetime = datetime.combine(next_month_start(months[-1]), time.min, tzinfo=UTC)
    source = volumetrics_source_subquery(request, scope_override=scope)
    cancelled_condition = volumetrics_cancelled_state_expression(source.c)
    resolved_closed_condition = volumetrics_resolved_closed_state_expression(source.c)
    resolved_date_expression = source.c.completion_at
    cancelled_date_expression = volumetrics_cancelled_count_date_expression(source.c)

    reference_map = inventory_assignment_group_reference_map(db, request.project_id)
    master_reference_status = assignment_group_master_reference_status(db, request.project_id)
    master_manager_map = active_assignment_group_master_manager_map(db, request.project_id)
    store: dict[tuple[str, bool, str], dict[str, Any]] = {}
    for row in assignment_group_volumetrics_event_rows(
        db,
        source,
        date_expression=source.c.created_at,
        event_name="created",
        start_datetime=start_datetime,
        end_datetime=end_datetime,
        functional_track=functional_track,
    ):
        add_assignment_group_volumetrics_event(store, row, months, "created")
    for row in assignment_group_volumetrics_event_rows(
        db,
        source,
        date_expression=resolved_date_expression,
        event_name="resolved",
        start_datetime=start_datetime,
        end_datetime=end_datetime,
        functional_track=functional_track,
        extra_conditions=[resolved_closed_condition],
    ):
        add_assignment_group_volumetrics_event(store, row, months, "resolved")
    for row in assignment_group_volumetrics_event_rows(
        db,
        source,
        date_expression=cancelled_date_expression,
        event_name="cancelled",
        start_datetime=start_datetime,
        end_datetime=end_datetime,
        functional_track=functional_track,
        extra_conditions=[cancelled_condition],
    ):
        add_assignment_group_volumetrics_event(store, row, months, "cancelled")

    incident_rows = [row for key, row in store.items() if key[0] == "incidents" and not key[1]]
    sc_task_rows = [row for key, row in store.items() if key[0] == "sc_tasks" and not key[1]]
    basis_incident_rows = [
        row for key, row in store.items() if key[0] == "incidents" and key[1]
    ]
    basis_sc_task_rows = [
        row for key, row in store.items() if key[0] == "sc_tasks" and key[1]
    ]
    overall_by_assignment: dict[tuple[bool, str], dict[str, Any]] = {}
    for row in incident_rows + sc_task_rows:
        key = (False, row["assignment_group_key"])
        overall_row = overall_by_assignment.setdefault(
            key,
            {
                "assignment_group": row["assignment_group"],
                "assignment_group_values": set(),
                "assignment_group_key": row["assignment_group_key"],
                "scopes": set(),
                "functional_track_values": set(),
                "ams_owner_values": set(),
                "support_lead_values": set(),
                "basis_security": False,
                "months": blank_month_metrics(months),
            },
        )
        overall_row["assignment_group_values"].update(row.get("assignment_group_values", set()))
        overall_row["scopes"].update(row.get("scopes", set()))
        overall_row["functional_track_values"].update(row.get("functional_track_values", set()))
        overall_row["ams_owner_values"].update(row.get("ams_owner_values", set()))
        overall_row["support_lead_values"].update(row.get("support_lead_values", set()))
        for current_month in months:
            current_key = month_key(current_month)
            for metric in ("created", "resolved", "cancelled"):
                overall_row["months"][current_key][metric] += row["months"][current_key][metric]

    basis_overall_by_assignment: dict[tuple[bool, str], dict[str, Any]] = {}
    for row in basis_incident_rows + basis_sc_task_rows:
        key = (True, row["assignment_group_key"])
        overall_row = basis_overall_by_assignment.setdefault(
            key,
            {
                "assignment_group": row["assignment_group"],
                "assignment_group_values": set(),
                "assignment_group_key": row["assignment_group_key"],
                "scopes": set(),
                "functional_track_values": set(),
                "ams_owner_values": set(),
                "support_lead_values": set(),
                "basis_security": True,
                "months": blank_month_metrics(months),
            },
        )
        overall_row["assignment_group_values"].update(row.get("assignment_group_values", set()))
        overall_row["scopes"].update(row.get("scopes", set()))
        overall_row["functional_track_values"].update(row.get("functional_track_values", set()))
        overall_row["ams_owner_values"].update(row.get("ams_owner_values", set()))
        overall_row["support_lead_values"].update(row.get("support_lead_values", set()))
        for current_month in months:
            current_key = month_key(current_month)
            for metric in ("created", "resolved", "cancelled"):
                overall_row["months"][current_key][metric] += row["months"][current_key][metric]

    data_notes = [
        "Assignment Group-wise Volumetrics includes Incidents and SC Tasks only.",
        "Problems and Changes are excluded.",
        "Created counts use created_at month.",
        "Resolved counts use normalized completion date and exclude cancelled states.",
        "Cancelled counts use cancelled/closed-incomplete state with closed/resolved date.",
        "BASIS and SECURITY assignment groups are confirmed out-of-scope and shown "
        "separately when present.",
    ]
    warnings: list[str] = []
    if master_reference_status.active_count > 0:
        data_notes.append(
            "Support Lead may be populated from the ServiceNow master assignment group "
            "reference Manager field when not available in Application Inventory.",
        )
    else:
        warnings.append(
            "Assignment Group master reference has not been imported; Support Lead fallback "
            "is unavailable.",
        )

    return {
        "scope": scope,
        "functional_track": functional_track,
        "months": [
            {
                "month": current_month,
                "month_key": month_key(current_month),
                "month_label": month_label(current_month),
            }
            for current_month in months
        ],
        "tables": {
            "incidents": build_assignment_group_volumetrics_table(
                "Incidents",
                incident_rows,
                months,
                reference_map,
                master_manager_map,
            ),
            "sc_tasks": build_assignment_group_volumetrics_table(
                "SC Tasks",
                sc_task_rows,
                months,
                reference_map,
                master_manager_map,
            ),
            "overall": build_assignment_group_volumetrics_table(
                "Overall",
                list(overall_by_assignment.values()),
                months,
                reference_map,
                master_manager_map,
            ),
            "basis_security_incidents": build_assignment_group_volumetrics_table(
                "BASIS/SECURITY Incidents",
                basis_incident_rows,
                months,
                reference_map,
                master_manager_map,
            ),
            "basis_security_sc_tasks": build_assignment_group_volumetrics_table(
                "BASIS/SECURITY SC Tasks",
                basis_sc_task_rows,
                months,
                reference_map,
                master_manager_map,
            ),
            "basis_security_overall": build_assignment_group_volumetrics_table(
                "BASIS/SECURITY Overall",
                list(basis_overall_by_assignment.values()),
                months,
                reference_map,
                master_manager_map,
            ),
        },
        "available_functional_tracks": volumetrics_assignment_group_available_tracks(db, request),
        "data_notes": data_notes,
        "warnings": warnings,
    }


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


def normalize_volumetrics_agreement_mode(value: str | None) -> str:
    normalized = (value or "sla").strip().lower()
    if normalized not in VOLUMETRICS_AGREEMENT_MODES:
        raise ValueError("Agreement mode must be sla or ola")
    return normalized


def volumetrics_agreement_breach_columns(source: Any, request: Any) -> tuple[Any, Any]:
    mode = normalize_volumetrics_agreement_mode(getattr(request, "agreement_mode", "sla"))
    if mode == "ola":
        return source.c.ola_response_sla_breached, source.c.ola_resolution_sla_breached
    return source.c.sla_response_sla_breached, source.c.sla_resolution_sla_breached


def normalize_dashboard_datetime(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def volumetrics_completion_expression(model: Any) -> Any:
    return case(
        (model.ticket_type == "INCIDENT", model.resolved_at),
        (model.ticket_type == "SERVICE_CATALOG_TASK", model.closed_at),
        else_=func.coalesce(model.resolved_at, model.closed_at),
    )


def volumetrics_availability_completion_expression(model: Any) -> Any:
    completion_expression = volumetrics_completion_expression(model)
    return case(
        (valid_resolved_closed_state_condition(model), completion_expression),
        else_=None,
    )


def volumetrics_cancelled_state_expression(model: Any) -> Any:
    return or_(
        cancelled_or_canceled_state_condition(model),
        sc_task_closed_incomplete_state_condition(model),
    )


def volumetrics_resolved_closed_state_expression(model: Any) -> Any:
    return valid_resolved_closed_state_condition(model)


def volumetrics_cancelled_count_date_expression(model: Any) -> Any:
    return case(
        (func.upper(model.ticket_type) == "SERVICE_CATALOG_TASK", model.closed_at),
        else_=func.coalesce(model.closed_at, model.resolved_at),
    )


def volumetrics_exit_expression(model: Any) -> Any:
    completion_expression = volumetrics_completion_expression(model)
    cancelled_date_expression = volumetrics_cancelled_count_date_expression(model)
    # Cancelled rows with no resolved/closed timestamp should not remain backlog forever.
    return case(
        (
            and_(
                volumetrics_cancelled_state_expression(model),
                cancelled_date_expression.is_(None),
            ),
            model.created_at,
        ),
        (volumetrics_cancelled_state_expression(model), cancelled_date_expression),
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
        model.business_critical.label("business_critical"),
        model.install_type.label("install_type"),
        model.hosting_env.label("hosting_env"),
        model.catalog_item_name.label("catalog_item_name"),
        model.is_batch_related.label("is_batch_related"),
        model.reassignment_count.label("reassignment_count"),
        model.business_duration_seconds.label("business_duration_seconds"),
        model.response_sla_breached.label("response_sla_breached"),
        model.resolution_sla_breached.label("resolution_sla_breached"),
        model.sla_response_sla_breached.label("sla_response_sla_breached"),
        model.sla_resolution_sla_breached.label("sla_resolution_sla_breached"),
        func.coalesce(model.ola_response_sla_breached, model.response_sla_breached).label(
            "ola_response_sla_breached",
        ),
        func.coalesce(model.ola_resolution_sla_breached, model.resolution_sla_breached).label(
            "ola_resolution_sla_breached",
        ),
    ).where(
        model.project_id == project_id,
        model.ticket_type.in_(tuple(VOLUMETRICS_TICKET_TYPE_VALUES.values())),
    )


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
    *,
    filter_name: str | None = None,
) -> list[dict[str, Any]]:
    existing = {str(row["label"]) for row in rows}
    for selected_value in selected_values:
        if selected_value not in existing:
            rows.append({"label": selected_value, "value": selected_value, "count": 0})
            existing.add(selected_value)
    sort_order = VOLUMETRICS_FILTER_CUSTOM_SORTS.get(filter_name or "")
    if sort_order:
        sort_rank = {label.casefold(): index for index, label in enumerate(sort_order)}
        return sorted(
            rows,
            key=lambda row: (
                sort_rank.get(str(row["label"]).casefold(), len(sort_order)),
                str(row["label"]).casefold(),
            ),
        )
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
        filter_name=filter_name,
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


def volumetrics_filter_fact_ticket_type_condition(
    ticket_type: str,
) -> Any | None:
    normalized = normalize_volumetrics_ticket_type(ticket_type)
    mapped_value = FACT_TICKET_TYPE_VALUES.get(normalized)
    if mapped_value is None:
        return None
    return DashboardFilterFact.record_type == mapped_value


def volumetrics_filter_fact_date_conditions(request: Any) -> list[Any]:
    start_datetime = normalize_dashboard_datetime(request.start_datetime)
    end_datetime = normalize_dashboard_datetime(request.end_datetime)
    return [
        DashboardFilterFact.created_at_source.is_not(None),
        DashboardFilterFact.created_at_source >= start_datetime,
        DashboardFilterFact.created_at_source <= end_datetime,
    ]


def volumetrics_filter_fact_filter_conditions(
    filters: Any,
    *,
    excluded_filter_name: str | None = None,
) -> list[Any]:
    conditions: list[Any] = []
    for filter_name, field_name in FACT_SINGLE_VOLUMETRICS_FILTER_FIELDS.items():
        if filter_name == excluded_filter_name:
            continue
        selected_values = selected_volumetrics_filter_values(filters, filter_name)
        if selected_values:
            conditions.append(
                volumetrics_display_expression(getattr(DashboardFilterFact, field_name)).in_(
                    selected_values,
                ),
            )

    for filter_name, fields in FACT_COMBINED_VOLUMETRICS_FILTER_FIELDS.items():
        if filter_name == excluded_filter_name:
            continue
        selected_values = selected_volumetrics_filter_values(filters, filter_name)
        if selected_values:
            conditions.append(
                volumetrics_display_expression(getattr(DashboardFilterFact, fields[2])).in_(
                    selected_values,
                ),
            )
    return conditions


def volumetrics_filter_fact_base_conditions(
    request: Any,
    *,
    scope_override: str | None = None,
    ticket_type_override: str | None = None,
    excluded_filter_name: str | None = None,
    exclude_ticket_type: bool = False,
    include_date_bounds: bool = True,
) -> list[Any]:
    scope = normalize_volumetrics_scope(scope_override or request.scope)
    conditions: list[Any] = [
        DashboardFilterFact.project_id == request.project_id,
        DashboardFilterFact.dashboard_area == "volumetrics",
        DashboardFilterFact.record_domain == "ticket",
    ]
    if scope != "all":
        conditions.append(DashboardFilterFact.scope == scope)

    ticket_type = ticket_type_override or request.ticket_type
    ticket_condition = (
        None
        if exclude_ticket_type
        else volumetrics_filter_fact_ticket_type_condition(ticket_type)
    )
    if ticket_condition is not None:
        conditions.append(ticket_condition)
    if include_date_bounds:
        conditions.extend(volumetrics_filter_fact_date_conditions(request))
    conditions.extend(
        volumetrics_filter_fact_filter_conditions(
            request.filters,
            excluded_filter_name=excluded_filter_name,
        ),
    )
    return conditions


def volumetrics_filter_fact_value_count_rows(
    db: Session,
    request: Any,
    filter_name: str,
    field_name: str,
) -> list[dict[str, Any]]:
    expression = volumetrics_display_expression(getattr(DashboardFilterFact, field_name))
    statement = (
        select(
            expression.label("label"),
            expression.label("value"),
            func.count(DashboardFilterFact.id).label("count"),
        )
        .select_from(DashboardFilterFact)
        .where(
            *volumetrics_filter_fact_base_conditions(
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
        filter_name=filter_name,
    )


def combined_volumetrics_filter_fact_value_count_rows(
    db: Session,
    request: Any,
    filter_name: str,
    left_field: str,
    right_field: str,
    label_field: str,
) -> list[dict[str, Any]]:
    label_expression = volumetrics_display_expression(getattr(DashboardFilterFact, label_field))
    left_expression = volumetrics_display_expression(getattr(DashboardFilterFact, left_field))
    right_expression = volumetrics_display_expression(getattr(DashboardFilterFact, right_field))
    statement = (
        select(
            label_expression.label("label"),
            left_expression.label("left_value"),
            right_expression.label("right_value"),
            func.count(DashboardFilterFact.id).label("count"),
        )
        .select_from(DashboardFilterFact)
        .where(
            *volumetrics_filter_fact_base_conditions(
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


def count_volumetrics_filter_fact_rows(
    db: Session,
    request: Any,
    *,
    scope_override: str | None = None,
    ticket_type_override: str | None = None,
    exclude_ticket_type: bool = False,
) -> int:
    statement = (
        select(func.count(DashboardFilterFact.id))
        .select_from(DashboardFilterFact)
        .where(
            *volumetrics_filter_fact_base_conditions(
                request,
                scope_override=scope_override,
                ticket_type_override=ticket_type_override,
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
    refreshed = ensure_dashboard_filter_facts(db, request.project_id)
    if refreshed is not None:
        db.commit()

    started = perf_counter()
    scope_rows = []
    for scope_key in ("all", "in_scope", "out_of_scope"):
        scope_rows.append(
            {
                "label": VOLUMETRICS_SCOPE_LABELS[scope_key],
                "value": scope_key,
                "count": count_volumetrics_filter_fact_rows(
                    db,
                    request,
                    scope_override=scope_key,
                ),
            },
        )

    ticket_type_rows = []
    for ticket_type_key in ("all", "incident", "sc_task"):
        ticket_type_rows.append(
            {
                "label": VOLUMETRICS_TICKET_TYPE_LABELS[ticket_type_key],
                "value": ticket_type_key,
                "count": count_volumetrics_filter_fact_rows(
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
        "functional_track_ams_owner": combined_volumetrics_filter_fact_value_count_rows(
            db,
            request,
            "functional_track_ams_owner",
            "functional_track",
            "ams_owner",
            "functional_track_ams_owner",
        ),
        "assignment_group_support_lead": combined_volumetrics_filter_fact_value_count_rows(
            db,
            request,
            "assignment_group_support_lead",
            "assignment_group",
            "support_group_owner",
            "assignment_group_support_owner",
        ),
        "parent_application_name": volumetrics_filter_fact_value_count_rows(
            db,
            request,
            "parent_application_name",
            "parent_business_application",
        ),
        "application_owner": volumetrics_filter_fact_value_count_rows(
            db,
            request,
            "application_owner",
            "application_owner",
        ),
        "supported_by_vendor": volumetrics_filter_fact_value_count_rows(
            db,
            request,
            "supported_by_vendor",
            "supported_by_vendor",
        ),
        "sap_non_sap": volumetrics_filter_fact_value_count_rows(
            db,
            request,
            "sap_non_sap",
            "sap_non_sap",
        ),
        "architecture_type": volumetrics_filter_fact_value_count_rows(
            db,
            request,
            "architecture_type",
            "architecture_type",
        ),
        "business_critical": volumetrics_filter_fact_value_count_rows(
            db,
            request,
            "business_critical",
            "business_critical",
        ),
        "install_type": volumetrics_filter_fact_value_count_rows(
            db,
            request,
            "install_type",
            "install_type",
        ),
        "source": "dashboard_filter_facts",
        "duration_ms": int((perf_counter() - started) * 1000),
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
    return volumetrics_cancelled_state_expression(source.c)


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
    resolved_closed_condition = volumetrics_resolved_closed_state_expression(source.c)
    cancelled_date_expression = volumetrics_cancelled_count_date_expression(source.c)

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
        [resolved_closed_condition],
    )
    cancelled_rows = (
        volumetrics_aggregate_by_period(
            db,
            request,
            source,
            cancelled_date_expression,
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
    response_breached_column, resolution_breached_column = volumetrics_agreement_breach_columns(
        source,
        request,
    )
    sla_rows = (
        volumetrics_aggregate_by_period(
            db,
            request,
            source,
            source.c.created_at,
            [
                func.count(source.c.id)
                .filter(response_breached_column.is_not(None))
                .label("response_applicable_count"),
                func.count(source.c.id)
                .filter(response_breached_column.is_(False))
                .label("response_met_count"),
                func.count(source.c.id)
                .filter(resolution_breached_column.is_not(None))
                .label("resolution_applicable_count"),
                func.count(source.c.id)
                .filter(resolution_breached_column.is_(False))
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
    resolved_closed_condition = volumetrics_resolved_closed_state_expression(source.c)

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
        [resolved_closed_condition],
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
        period_values = {priority: values.get(priority, 0) for priority in ordered_priorities}
        period_total = sum(period_values.values())
        points.append(
            {
                "period_key": period_key,
                "period_label": period.label,
                "values": period_values,
                "percentages": {
                    priority: (
                        round((count / period_total) * 100, 1) if period_total > 0 else 0.0
                    )
                    for priority, count in period_values.items()
                },
                "total": period_total,
            },
        )

    return {
        "time_grain": grain,
        "priorities": ordered_priorities,
        "points": points,
    }


def empty_sla_trend_response(request: Any, *, not_applicable: bool) -> dict[str, Any]:
    agreement_mode = normalize_volumetrics_agreement_mode(
        getattr(request, "agreement_mode", "sla"),
    )
    agreement_label = agreement_mode.upper()
    return {
        "time_grain": normalize_volumetrics_time_grain(request.time_grain),
        "agreement_mode": agreement_mode,
        "not_applicable": not_applicable,
        "response": [],
        "resolution": [],
        "logic": {
            "response_adherence_formula": (
                f"response_{agreement_mode}_adhered_count / "
                f"response_{agreement_mode}_captured_count * 100"
            ),
            "resolution_adherence_formula": (
                f"resolution_{agreement_mode}_adhered_count / "
                f"resolution_{agreement_mode}_captured_count * 100"
            ),
            "captured_definition": f"{agreement_label} breached flag IS NOT NULL",
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
    response_breached_column, resolution_breached_column = volumetrics_agreement_breach_columns(
        source,
        request,
    )
    statement = (
        select(
            period_expression.label("period_start"),
            func.count(source.c.id).label("total_closed_ticket_count"),
            func.count(source.c.id)
            .filter(response_breached_column.is_not(None))
            .label("response_sla_captured_count"),
            func.count(source.c.id)
            .filter(response_breached_column.is_(False))
            .label("response_sla_adhered_count"),
            func.count(source.c.id)
            .filter(resolution_breached_column.is_not(None))
            .label("resolution_sla_captured_count"),
            func.count(source.c.id)
            .filter(resolution_breached_column.is_(False))
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
            volumetrics_resolved_closed_state_expression(source.c),
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
    cancelled_date_expression = volumetrics_cancelled_count_date_expression(source.c)
    created_window_condition = and_(
        source.c.created_at.is_not(None),
        source.c.created_at >= window_start,
        source.c.created_at <= window_end,
    )
    cancelled_window_condition = and_(
        cancelled_condition,
        cancelled_date_expression.is_not(None),
        cancelled_date_expression >= window_start,
        cancelled_date_expression <= window_end,
    )
    created_count_expression = (
        func.count(source.c.id).filter(created_window_condition) / 6.0
    ).label("average_created")
    canceled_count_expression = (
        func.count(source.c.id).filter(cancelled_window_condition) / 6.0
    ).label("average_canceled")
    conditions = [
        *volumetrics_base_conditions(
            source,
            effective_request,
            include_date_bounds=False,
        ),
        or_(created_window_condition, cancelled_window_condition),
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
            ApplicationInventoryItem.is_current.is_(True),
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
        "hosting_env": group("hosting_env"),
    }


def sc_task_catalog_period_expression(source: Any) -> Any:
    return case(
        *(
            (
                and_(
                    source.c.created_at >= start_datetime,
                    source.c.created_at < end_exclusive_datetime,
                ),
                literal(period_key),
            )
            for period_key, _label, start_datetime, end_exclusive_datetime in (
                SC_TASK_CATALOG_PERIODS
            )
        ),
        else_=None,
    )


def sc_task_catalog_period_shells() -> list[dict[str, Any]]:
    shells = []
    for period_key, period_label, start_datetime, end_exclusive_datetime in SC_TASK_CATALOG_PERIODS:
        shells.append(
            {
                "period_key": period_key,
                "period_label": period_label,
                "from_date": start_datetime.date(),
                "to_date": (end_exclusive_datetime - timedelta(days=1)).date(),
                "total_sc_tasks": 0,
                "months_in_period": 6,
                "pie_rows": [],
                "top_10_rows": [],
                "warnings": [],
            },
        )
    return shells


def sc_task_catalog_metric_row(
    catalog_item_name: str,
    sc_task_count: int,
    total_sc_tasks: int,
) -> dict[str, Any]:
    avg_monthly_volume = sc_task_count / 6.0
    proportion_pct = percentage(sc_task_count, total_sc_tasks)
    return {
        "catalog_item_name": catalog_item_name,
        "sc_task_count": sc_task_count,
        "avg_monthly_volume": round(avg_monthly_volume, 1),
        "proportion_pct": round(proportion_pct, 1) if proportion_pct is not None else None,
    }


def sc_task_catalog_pie_rows(
    raw_rows: list[dict[str, Any]],
    total_sc_tasks: int,
) -> list[dict[str, Any]]:
    visible_rows: list[dict[str, Any]] = []
    other_count = 0
    for row in raw_rows:
        sc_task_count = int(row["sc_task_count"])
        proportion_pct = percentage(sc_task_count, total_sc_tasks)
        if proportion_pct is not None and proportion_pct < 2:
            other_count += sc_task_count
        else:
            visible_rows.append(row)

    pie_rows = [
        sc_task_catalog_metric_row(
            str(row["catalog_item_name"]),
            int(row["sc_task_count"]),
            total_sc_tasks,
        )
        for row in visible_rows
    ]
    if other_count > 0:
        pie_rows.append(sc_task_catalog_metric_row("Others", other_count, total_sc_tasks))
    return sorted(
        pie_rows,
        key=lambda item: (
            -int(item["sc_task_count"]),
            str(item["catalog_item_name"]).casefold(),
        ),
    )


def volumetrics_sc_task_catalog_item_proportion(
    db: Session,
    request: Any,
) -> dict[str, Any]:
    normalize_volumetrics_scope(request.scope)
    selected_ticket_type = normalize_volumetrics_ticket_type(request.ticket_type)
    periods = sc_task_catalog_period_shells()
    data_notes = [
        "SC Task Catalog Item Proportion uses SC Tasks only.",
        "Incidents, Problems, and Changes are excluded.",
        "Pie charts group catalog items below 2% into Others.",
        "Average monthly volume is calculated over six months for each half-year period.",
        "Date controls do not override the fixed H1/H2 periods for this chart.",
    ]
    warnings: list[str] = []
    if selected_ticket_type == "incident":
        warnings.append(
            "SC Task Catalog Item Proportion is available for SC Tasks only. "
            "Change Ticket Type to All or SC Tasks.",
        )
        for period in periods:
            period["warnings"].append(warnings[0])
        return {"periods": periods, "data_notes": data_notes, "warnings": warnings}

    source = volumetrics_source_subquery(request)
    sc_task_request = replace_request_value(request, "ticket_type", "sc_task")
    period_expression = sc_task_catalog_period_expression(source)
    catalog_expression = func.coalesce(
        nonblank_text_expression(source.c.catalog_item_name),
        literal("Unmapped Catalog Item"),
    )
    period_start = SC_TASK_CATALOG_PERIODS[0][2]
    period_end_exclusive = SC_TASK_CATALOG_PERIODS[-1][3]
    statement = (
        select(
            period_expression.label("period_key"),
            catalog_expression.label("catalog_item_name"),
            func.count(source.c.id).label("sc_task_count"),
        )
        .select_from(source)
        .where(
            *volumetrics_base_conditions(
                source,
                sc_task_request,
                include_date_bounds=False,
            ),
            source.c.created_at.is_not(None),
            source.c.created_at >= period_start,
            source.c.created_at < period_end_exclusive,
            period_expression.is_not(None),
        )
        .group_by(period_expression, catalog_expression)
        .order_by(period_expression.asc(), func.count(source.c.id).desc(), catalog_expression.asc())
    )

    rows_by_period: dict[str, list[dict[str, Any]]] = {
        period_key: [] for period_key, _label, _start, _end in SC_TASK_CATALOG_PERIODS
    }
    for row in db.execute(statement).mappings().all():
        period_key = str(row["period_key"])
        if period_key in rows_by_period:
            rows_by_period[period_key].append(
                {
                    "catalog_item_name": str(row["catalog_item_name"]),
                    "sc_task_count": int(row["sc_task_count"] or 0),
                },
            )

    for period in periods:
        raw_rows = sorted(
            rows_by_period.get(period["period_key"], []),
            key=lambda item: (-item["sc_task_count"], item["catalog_item_name"].casefold()),
        )
        total_sc_tasks = sum(row["sc_task_count"] for row in raw_rows)
        period["total_sc_tasks"] = total_sc_tasks
        if total_sc_tasks == 0:
            period["warnings"].append(
                f"No SC Task catalog item data available for {period['period_label']}.",
            )
            continue

        top_rows = raw_rows[:10]
        period["top_10_rows"] = [
            {
                **sc_task_catalog_metric_row(
                    str(row["catalog_item_name"]),
                    int(row["sc_task_count"]),
                    total_sc_tasks,
                ),
                "rank": index + 1,
                "avg_monthly_with_pct_label": (
                    f"{int((row['sc_task_count'] / 6.0) + 0.5)} "
                    f"({(row['sc_task_count'] / total_sc_tasks * 100):.1f}%)"
                ),
            }
            for index, row in enumerate(top_rows)
        ]
        period["pie_rows"] = sc_task_catalog_pie_rows(raw_rows, total_sc_tasks)

    return {"periods": periods, "data_notes": data_notes, "warnings": warnings}


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
            volumetrics_resolved_closed_state_expression(source.c),
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
            volumetrics_resolved_closed_state_expression(source.c),
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


def non_negative_reassignment_expression(source: Any) -> Any:
    reassignment_count = func.coalesce(source.c.reassignment_count, 0)
    return case((reassignment_count < 0, 0), else_=reassignment_count)


def rounded_percentage(numerator: int, denominator: int) -> float | None:
    percentage_value = percentage(numerator, denominator)
    return round(percentage_value, 2) if percentage_value is not None else None


PROBLEM_SINGLE_FILTER_FIELDS = {
    "parent_application_name": "parent_business_application",
    "supported_by_vendor": "supported_by_vendor",
    "sap_non_sap": "sap_non_sap",
}

PROBLEM_COMBINED_FILTER_FIELDS = {
    "functional_track_ams_owner": ("functional_track", "ams_owner"),
}

PROBLEM_UNSUPPORTED_FILTERS = {
    "assignment_group_support_lead": (
        "Assignment Group - Support Lead is not normalized on Problem records."
    ),
    "application_owner": "Application Owner is not normalized on Problem records.",
    "business_critical": "Business Criticality is not normalized on Problem records.",
}


def problem_management_source_select(model: Any, scope_label: str, project_id: UUID) -> Any:
    return select(
        literal(scope_label).label("scope"),
        model.id.label("id"),
        model.created_at_source.label("created_at_source"),
        model.closed_at.label("closed_at"),
        model.linked_incident_count.label("linked_incident_count"),
        model.functional_track.label("functional_track"),
        model.ams_owner.label("ams_owner"),
        model.parent_business_application.label("parent_business_application"),
        model.supported_by_vendor.label("supported_by_vendor"),
        model.sap_non_sap.label("sap_non_sap"),
    ).where(model.project_id == project_id)


def problem_management_source_subquery(request: Any) -> Any:
    scope = normalize_volumetrics_scope(request.scope)
    in_scope_select = problem_management_source_select(
        AssessmentProblemRecord,
        "in_scope",
        request.project_id,
    )
    out_of_scope_select = problem_management_source_select(
        AssessmentOutOfScopeProblemRecord,
        "out_of_scope",
        request.project_id,
    )
    if scope == "in_scope":
        return in_scope_select.subquery("problem_management_source")
    if scope == "out_of_scope":
        return out_of_scope_select.subquery("problem_management_source")
    return union_all(in_scope_select, out_of_scope_select).subquery("problem_management_source")


def problem_management_filter_conditions(
    source: Any,
    filters: Any,
) -> tuple[list[Any], list[str]]:
    conditions: list[Any] = []
    warnings: list[str] = []
    for filter_name, field_name in PROBLEM_SINGLE_FILTER_FIELDS.items():
        selected_values = selected_volumetrics_filter_values(filters, filter_name)
        if selected_values:
            conditions.append(
                volumetrics_display_expression(
                    getattr(source.c, field_name),
                ).in_(selected_values),
            )

    for filter_name, fields in PROBLEM_COMBINED_FILTER_FIELDS.items():
        selected_values = selected_volumetrics_filter_values(filters, filter_name)
        if selected_values:
            conditions.append(
                func.concat(
                    volumetrics_display_expression(
                        getattr(source.c, fields[0]),
                    ),
                    literal(" - "),
                    volumetrics_display_expression(
                        getattr(source.c, fields[1]),
                    ),
                ).in_(selected_values),
            )

    for filter_name, message in PROBLEM_UNSUPPORTED_FILTERS.items():
        if selected_volumetrics_filter_values(filters, filter_name):
            warnings.append(message)

    return conditions, warnings


def non_negative_linked_incident_count_expression(source: Any) -> Any:
    linked_incident_count = func.coalesce(source.c.linked_incident_count, 0)
    return case((linked_incident_count < 0, 0), else_=linked_incident_count)


def empty_problem_management_trend_response(request: Any) -> dict[str, Any]:
    return {
        "time_grain": "monthly",
        "scope": normalize_volumetrics_scope(request.scope),
        "date_range": {
            "from_date": normalize_dashboard_datetime(request.start_datetime),
            "to_date": normalize_dashboard_datetime(request.end_datetime),
            "complete_month_cutoff_applied": True,
        },
        "points": [],
        "axis": {
            "use_secondary_axis_for_linked_incidents": False,
            "reason": "No complete months are available for the selected range.",
        },
        "data_notes": [
            "Problem records are analyzed separately from generic tickets.",
            "Problem scope is classified using active Application Inventory assignment groups.",
            "Generic ticket counts still include only Incidents and SC Tasks.",
            "Linked incidents are summed for Problems closed in each month.",
            "Complete-month cutoff applied.",
        ],
        "warnings": [],
    }


def problem_management_secondary_axis(points: list[dict[str, Any]]) -> dict[str, Any]:
    max_problem_volume = max(
        (
            max(
                int_count(point.get("problem_tickets_created")),
                int_count(point.get("problem_tickets_closed")),
            )
            for point in points
        ),
        default=0,
    )
    max_linked_incidents = max(
        (int_count(point.get("linked_incidents_resolved_permanently")) for point in points),
        default=0,
    )
    use_secondary_axis = (
        max_linked_incidents > 0
        and (max_problem_volume == 0 or max_linked_incidents >= max_problem_volume * 3)
    )
    return {
        "use_secondary_axis_for_linked_incidents": use_secondary_axis,
        "reason": (
            "Linked incident count is at least 3x higher than Problem ticket volume."
            if use_secondary_axis
            else "Linked incident count is comparable with Problem ticket volume."
        ),
    }


def volumetrics_kpi_problem_management_trend(db: Session, request: Any) -> dict[str, Any]:
    scope = normalize_volumetrics_scope(request.scope)
    start_datetime, end_datetime = complete_month_bounds(
        request.start_datetime,
        request.end_datetime,
    )
    if start_datetime is None or end_datetime is None:
        return empty_problem_management_trend_response(request)

    monthly_request = replace_request_value(
        replace_request_value(request, "start_datetime", start_datetime),
        "end_datetime",
        end_datetime,
    )
    monthly_request = replace_request_value(monthly_request, "time_grain", "monthly")
    periods = build_volumetrics_periods(monthly_request)
    source = problem_management_source_subquery(monthly_request)
    filter_conditions, warnings = problem_management_filter_conditions(
        source,
        monthly_request.filters,
    )

    created_period = volumetrics_period_start_expression(
        source.c.created_at_source,
        "monthly",
    )
    created_statement = (
        select(
            created_period.label("period_start"),
            func.count(source.c.id).label("problem_tickets_created"),
        )
        .select_from(source)
        .where(
            *filter_conditions,
            source.c.created_at_source.is_not(None),
            source.c.created_at_source
            >= normalize_dashboard_datetime(monthly_request.start_datetime),
            source.c.created_at_source
            <= normalize_dashboard_datetime(monthly_request.end_datetime),
        )
        .group_by(created_period)
    )

    linked_incident_count = non_negative_linked_incident_count_expression(source)
    closed_period = volumetrics_period_start_expression(
        source.c.closed_at,
        "monthly",
    )
    closed_statement = (
        select(
            closed_period.label("period_start"),
            func.count(source.c.id).label("problem_tickets_closed"),
            func.sum(linked_incident_count).label("linked_incidents_resolved_permanently"),
        )
        .select_from(source)
        .where(
            *filter_conditions,
            source.c.closed_at.is_not(None),
            source.c.closed_at
            >= normalize_dashboard_datetime(monthly_request.start_datetime),
            source.c.closed_at
            <= normalize_dashboard_datetime(monthly_request.end_datetime),
        )
        .group_by(closed_period)
    )

    created_by_period: dict[str, int] = {}
    for row in db.execute(created_statement).mappings().all():
        period_start = normalize_volumetrics_period_key(row["period_start"], "monthly")
        if period_start is None:
            continue
        created_by_period[volumetrics_period_lookup_key(period_start, "monthly")] = int_count(
            row["problem_tickets_created"],
        )

    closed_by_period: dict[str, dict[str, int]] = {}
    for row in db.execute(closed_statement).mappings().all():
        period_start = normalize_volumetrics_period_key(row["period_start"], "monthly")
        if period_start is None:
            continue
        closed_by_period[volumetrics_period_lookup_key(period_start, "monthly")] = {
            "problem_tickets_closed": int_count(row["problem_tickets_closed"]),
            "linked_incidents_resolved_permanently": int_count(
                row["linked_incidents_resolved_permanently"],
            ),
        }

    points: list[dict[str, Any]] = []
    for period in periods:
        period_key = volumetrics_period_lookup_key(period.start, "monthly")
        closed_values = closed_by_period.get(period_key, {})
        problem_tickets_closed = int_count(closed_values.get("problem_tickets_closed"))
        linked_incidents = int_count(
            closed_values.get("linked_incidents_resolved_permanently"),
        )
        points.append(
            {
                "period_key": period_key,
                "period_label": period.label,
                "period_start": period.start,
                "period_end": period.end,
                "problem_tickets_created": created_by_period.get(period_key, 0),
                "problem_tickets_closed": problem_tickets_closed,
                "linked_incidents_resolved_permanently": linked_incidents,
                "avg_linked_incidents_per_closed_problem": (
                    round(linked_incidents / problem_tickets_closed, 2)
                    if problem_tickets_closed
                    else None
                ),
            },
        )

    return {
        "time_grain": "monthly",
        "scope": scope,
        "date_range": {
            "from_date": monthly_request.start_datetime,
            "to_date": monthly_request.end_datetime,
            "complete_month_cutoff_applied": True,
        },
        "points": points,
        "axis": problem_management_secondary_axis(points),
        "data_notes": [
            "Problem records are analyzed separately from generic tickets.",
            "Problem scope is classified using active Application Inventory assignment groups.",
            "Out-of-scope Problems are excluded unless scope is set to out_of_scope or all.",
            "Generic ticket counts still include only Incidents and SC Tasks.",
            "Linked incidents are summed for Problems closed in each month.",
            "Created volume uses Problem created date; closed volume and linked incident counts "
            "use Problem closed date.",
            "Complete-month cutoff applied.",
        ],
        "warnings": warnings,
    }


def volumetrics_kpi_reassignment_hops_trend(db: Session, request: Any) -> dict[str, Any]:
    complete_request = complete_month_clamped_request(db, request)
    monthly_request = replace_request_value(complete_request, "time_grain", "monthly")
    periods = build_volumetrics_periods(monthly_request)
    source = volumetrics_source_subquery(monthly_request)
    period_expression = volumetrics_period_start_expression(source.c.created_at, "monthly")
    reassignment_count = non_negative_reassignment_expression(source)
    high_reassignment_condition = reassignment_count >= 2

    statement = (
        select(
            period_expression.label("period_start"),
            func.count(source.c.id).label("total_created_tickets"),
            func.count(source.c.id)
            .filter(high_reassignment_condition)
            .label("tickets_with_2_plus_reassignments"),
            func.sum(
                case(
                    (high_reassignment_condition, reassignment_count),
                    else_=0,
                ),
            ).label("total_reassignment_hops_ge_2"),
        )
        .select_from(source)
        .where(
            *volumetrics_base_conditions(
                source,
                monthly_request,
                include_date_bounds=False,
            ),
            source.c.created_at.is_not(None),
            source.c.created_at >= normalize_dashboard_datetime(monthly_request.start_datetime),
            source.c.created_at <= normalize_dashboard_datetime(monthly_request.end_datetime),
        )
        .group_by(period_expression)
        .order_by(period_expression)
    )
    rows_by_period: dict[str, dict[str, Any]] = {}
    for row in db.execute(statement).mappings().all():
        period_start = normalize_volumetrics_period_key(row["period_start"], "monthly")
        if period_start is None:
            continue
        rows_by_period[volumetrics_period_lookup_key(period_start, "monthly")] = dict(row)

    points: list[dict[str, Any]] = []
    for period in periods:
        period_key = volumetrics_period_lookup_key(period.start, "monthly")
        values = rows_by_period.get(period_key, {})
        total_created = int_count(values.get("total_created_tickets"))
        high_reassignment_tickets = int_count(
            values.get("tickets_with_2_plus_reassignments"),
        )
        total_hops = int_count(values.get("total_reassignment_hops_ge_2"))
        points.append(
            {
                "period_key": period_key,
                "period_label": period.label,
                "period_start": period.start,
                "period_end": period.end,
                "total_created_tickets": total_created,
                "tickets_with_2_plus_reassignments": high_reassignment_tickets,
                "total_reassignment_hops_ge_2": total_hops,
                "pct_tickets_with_2_plus_reassignments": rounded_percentage(
                    high_reassignment_tickets,
                    total_created,
                ),
                "reassignment_hops_pct_of_created": rounded_percentage(
                    total_hops,
                    total_created,
                ),
            },
        )

    return {
        "time_grain": "monthly",
        "date_range": {
            "from_date": monthly_request.start_datetime,
            "to_date": monthly_request.end_datetime,
            "complete_month_cutoff_applied": True,
        },
        "points": points,
        "data_notes": [
            "Generic Tickets includes Incidents and SC Tasks only.",
            "Problems and Changes are excluded.",
            "Reassignment threshold is >= 2.",
            "Monthly grouping uses created date.",
            "Complete-month cutoff applied.",
        ],
        "warnings": [],
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
        [valid_resolved_closed_state_condition(Ticket)],
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
            valid_resolved_closed_state_condition(Ticket),
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
