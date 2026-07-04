# ruff: noqa: E501

from __future__ import annotations

import base64
import calendar
import html
import json
import re
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import UUID

from sqlalchemy import Float, Integer, case, cast, func, literal, select, union_all
from sqlalchemy.orm import Session

from app.models import (
    ApplicationInventoryItem,
    AssessmentOutOfScopeProblemRecord,
    AssessmentOutOfScopeTicket,
    AssessmentProblemRecord,
    Client,
    Project,
    Ticket,
)
from app.services.dashboard import (
    APPLICATION_CRITICALITY_ORDER,
    APPLICATION_LIST_FIELDS,
    BLANK_LABEL,
    DURATION_BUCKETS,
    MTTR_PRIORITIES,
    VOLUMETRICS_SCOPE_LABELS,
    VOLUMETRICS_TICKET_TYPE_LABELS,
    application_display_expression,
    applications_assignment_group_mapping,
    applications_charts,
    applications_summary,
    build_volumetrics_periods,
    combined_volumetrics_display_expression,
    date_counts_by_day_of_month,
    date_counts_by_weekday,
    day_count_for_week_part,
    duration_bucket_expression,
    latest_complete_month_window,
    latest_complete_window_payload,
    non_negative_reassignment_expression,
    nonblank_text_expression,
    normalize_dashboard_datetime,
    overview_summary,
    priority_bucket_expression,
    priority_sort_key,
    ranking_window_payload,
    volumetrics_assignment_group_volumetrics,
    volumetrics_base_conditions,
    volumetrics_cancelled_expression,
    volumetrics_data_range,
    volumetrics_display_expression,
    volumetrics_period_start_expression,
    volumetrics_source_select,
)
from app.services.dashboard_commentary import export_project_commentaries

OFFLINE_APPLICATION_FIELDS = tuple(
    dict.fromkeys((*APPLICATION_LIST_FIELDS, "lifecycle_stage_status")),
)
OFFLINE_CREATED_PATTERN_TYPES = (
    "day_of_month",
    "day_of_week",
    "hour_weekdays",
    "hour_weekends",
)
OFFLINE_SCOPE_VALUES = ("in_scope", "out_of_scope")
OFFLINE_TICKET_TYPE_VALUES = ("incident", "sc_task")
MONDELEZ_LOGO_FILENAMES = ("MDLZlogo_smr.webp", "MDLZlogo.webp")


def json_default(value: Any) -> str:
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def json_script_payload(payload: dict[str, Any]) -> str:
    return json.dumps(payload, default=json_default, ensure_ascii=False).replace("</", "<\\/")


def safe_filename_part(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", value.strip()).strip("_")
    return cleaned or "Dashboard"


def dashboard_filename(customer_name: str, project_name: str, exported_at: datetime) -> str:
    timestamp = exported_at.strftime("%Y%m%d_%H%M")
    return f"AMS_Apps_Volumetrics_Dashboard_{timestamp}.html"


def project_root_path() -> Path:
    return Path(__file__).resolve().parents[3]


def customer_logo_data_url(customer_name: str) -> str | None:
    if "mondelez" not in customer_name.casefold():
        return None

    root = project_root_path()
    for filename in MONDELEZ_LOGO_FILENAMES:
        logo_path = root / filename
        if logo_path.is_file():
            encoded_logo = base64.b64encode(logo_path.read_bytes()).decode("ascii")
            return f"data:image/webp;base64,{encoded_logo}"
    return None


def display_value(value: Any) -> str:
    if value is None:
        return BLANK_LABEL
    text = str(value).strip()
    return text or BLANK_LABEL


def ticket_type_key_expression(source: Any) -> Any:
    return case(
        (source.c.ticket_type == "INCIDENT", literal("incident")),
        (source.c.ticket_type == "SERVICE_CATALOG_TASK", literal("sc_task")),
        else_=func.lower(source.c.ticket_type),
    )


def month_label(value: datetime) -> str:
    return f"{value:%b-%y}"


def month_key(value: datetime) -> str:
    return f"{value.year:04d}-{value.month:02d}"


def first_day_of_month(value: datetime) -> datetime:
    return datetime(value.year, value.month, 1, tzinfo=value.tzinfo)


def last_moment_of_month(value: datetime) -> datetime:
    last_day = calendar.monthrange(value.year, value.month)[1]
    return datetime(value.year, value.month, last_day, 23, 59, 59, 999999, tzinfo=value.tzinfo)


def first_day_of_next_month(value: datetime) -> datetime:
    if value.month == 12:
        return datetime(value.year + 1, 1, 1, tzinfo=value.tzinfo)
    return datetime(value.year, value.month + 1, 1, tzinfo=value.tzinfo)


def last_moment_of_previous_month(value: datetime) -> datetime:
    return first_day_of_month(value) - timedelta(microseconds=1)


def complete_month_bounds(
    start_value: datetime,
    end_value: datetime,
) -> tuple[datetime | None, datetime | None]:
    start_datetime = (
        first_day_of_month(start_value)
        if start_value.day == 1
        else first_day_of_next_month(start_value)
    )
    end_month_last_day = calendar.monthrange(end_value.year, end_value.month)[1]
    end_datetime = (
        last_moment_of_month(end_value)
        if end_value.day == end_month_last_day
        else last_moment_of_previous_month(end_value)
    )
    if start_datetime > end_datetime:
        return None, None
    return start_datetime, end_datetime


def monthly_request(project_id: UUID, start_datetime: datetime, end_datetime: datetime) -> Any:
    return SimpleNamespace(
        project_id=project_id,
        scope="all",
        ticket_type="all",
        time_grain="monthly",
        start_datetime=start_datetime,
        end_datetime=end_datetime,
        filters=SimpleNamespace(
            application_scope=[],
            functional_track_ams_owner=[],
            assignment_group_support_lead=[],
            parent_application_name=[],
            application_owner=[],
            supported_by_vendor=[],
            sap_non_sap=[],
            business_critical=[],
        ),
    )


def empty_application_request(project_id: UUID, *, limit: int = 10000) -> Any:
    return SimpleNamespace(
        project_id=project_id,
        filters=SimpleNamespace(
            functional_track_ams_owner=[],
            assignment_group_owner=[],
            parent_application_name=[],
            application_owner=[],
            supported_by_vendor=[],
            sap_non_sap=[],
            architecture_type=[],
            application_type=[],
            business_critical=[],
            install_status=[],
            install_type=[],
            hosting_env=[],
            lifecycle_status_stage=[],
        ),
        sort=SimpleNamespace(column="business_service_ci_name", direction="asc"),
        limit=limit,
        offset=0,
    )


def get_project_metadata(db: Session, project_id: UUID) -> tuple[Project, Client]:
    row = (
        db.execute(
            select(Project, Client)
            .join(Client, Project.client_id == Client.id)
            .where(Project.id == project_id),
        )
        .tuples()
        .one_or_none()
    )
    if row is None:
        raise ValueError("Project not found")
    return row


def application_export_rows(db: Session, project_id: UUID) -> list[dict[str, Any]]:
    columns = [
        application_display_expression(field_name).label(field_name)
        for field_name in OFFLINE_APPLICATION_FIELDS
    ]
    statement = (
        select(*columns)
        .where(
            ApplicationInventoryItem.project_id == project_id,
            ApplicationInventoryItem.is_current.is_(True),
            ApplicationInventoryItem.active.is_(True),
            nonblank_text_expression(ApplicationInventoryItem.business_service_ci_name).is_not(
                None
            ),
        )
        .order_by(application_display_expression("business_service_ci_name").asc())
    )
    rows = []
    for row in db.execute(statement).mappings().all():
        next_row = dict(row)
        next_row["functional_track_ams_owner"] = (
            f"{display_value(next_row.get('functional_track'))} - "
            f"{display_value(next_row.get('ams_owner'))}"
        )
        rows.append(next_row)
    return rows


def build_applications_payload(db: Session, project_id: UUID) -> dict[str, Any]:
    request = empty_application_request(project_id)
    return {
        "rows": application_export_rows(db, project_id),
        "summary": applications_summary(db, request),
        "charts": applications_charts(db, request),
        "assignment_group_mapping": build_assignment_group_mapping_payload(db, project_id),
    }


def assignment_group_mapping_request(
    project_id: UUID,
    *,
    source: str,
    scope: str = "all",
    functional_track: str = "all",
) -> Any:
    return SimpleNamespace(
        project_id=project_id,
        source=source,
        scope=scope,
        functional_track=functional_track,
        search=None,
    )


def build_assignment_group_mapping_payload(db: Session, project_id: UUID) -> dict[str, Any]:
    return {
        "application_inventory": applications_assignment_group_mapping(
            db,
            assignment_group_mapping_request(project_id, source="application_inventory"),
        ),
        "tickets": applications_assignment_group_mapping(
            db,
            assignment_group_mapping_request(project_id, source="tickets"),
        ),
    }


def build_assignment_group_volumetrics_payload(db: Session, project_id: UUID) -> dict[str, Any]:
    return {
        scope: volumetrics_assignment_group_volumetrics(
            db,
            SimpleNamespace(
                project_id=project_id,
                scope=scope,
                functional_track="all",
                from_month="2025-12",
                to_month="2026-05",
            ),
        )
        for scope in ("in_scope", "out_of_scope", "all")
    }


def build_volumetrics_source(project_id: UUID) -> Any:
    return union_all(
        volumetrics_source_select(Ticket, "in_scope", project_id),
        volumetrics_source_select(AssessmentOutOfScopeTicket, "out_of_scope", project_id),
    ).subquery("offline_volumetrics_source")


def volumetrics_dimension_expressions(source: Any) -> dict[str, Any]:
    return {
        "scope": source.c.scope,
        "ticket_type": ticket_type_key_expression(source),
        "functional_track": volumetrics_display_expression(source.c.functional_track),
        "ams_owner": volumetrics_display_expression(source.c.ams_owner),
        "functional_track_ams_owner": combined_volumetrics_display_expression(
            source,
            "functional_track",
            "ams_owner",
        ),
        "sap_non_sap": volumetrics_display_expression(source.c.sap_non_sap),
        "business_critical": volumetrics_display_expression(source.c.business_critical),
    }


def dimension_key(row: dict[str, Any]) -> tuple[str, str, str, str, str, str, str]:
    return (
        str(row["scope"]),
        str(row["ticket_type"]),
        str(row["functional_track"]),
        str(row["ams_owner"]),
        str(row["functional_track_ams_owner"]),
        str(row["sap_non_sap"]),
        str(row["business_critical"]),
    )


def dimension_dict(key: tuple[str, str, str, str, str, str, str]) -> dict[str, str]:
    return {
        "scope": key[0],
        "ticket_type": key[1],
        "functional_track": key[2],
        "ams_owner": key[3],
        "functional_track_ams_owner": key[4],
        "sap_non_sap": key[5],
        "business_critical": key[6],
    }


def offline_period_rows(
    db: Session,
    request: Any,
    source: Any,
    date_expression: Any,
    value_label: str,
    extra_conditions: list[Any] | None = None,
) -> dict[tuple[tuple[str, str, str, str, str, str, str], str], int]:
    dimensions = volumetrics_dimension_expressions(source)
    period_expression = volumetrics_period_start_expression(date_expression, "monthly")
    conditions = [
        *volumetrics_base_conditions(source, request, include_date_bounds=False),
        date_expression.is_not(None),
        date_expression >= normalize_dashboard_datetime(request.start_datetime),
        date_expression <= normalize_dashboard_datetime(request.end_datetime),
    ]
    if extra_conditions:
        conditions.extend(extra_conditions)
    statement = (
        select(
            *[expression.label(name) for name, expression in dimensions.items()],
            period_expression.label("period_start"),
            func.count(source.c.id).label(value_label),
        )
        .select_from(source)
        .where(*conditions)
        .group_by(*dimensions.values(), period_expression)
    )
    results: dict[tuple[tuple[str, str, str, str, str, str, str], str], int] = {}
    for row in db.execute(statement).mappings().all():
        key = dimension_key(row)
        period_start = row["period_start"]
        if period_start is not None:
            results[(key, month_key(period_start))] = int(row[value_label] or 0)
    return results


def offline_initial_counts(
    db: Session,
    request: Any,
    source: Any,
    date_expression: Any,
) -> dict[tuple[str, str, str, str, str, str, str], int]:
    dimensions = volumetrics_dimension_expressions(source)
    statement = (
        select(
            *[expression.label(name) for name, expression in dimensions.items()],
            func.count(source.c.id).label("row_count"),
        )
        .select_from(source)
        .where(
            *volumetrics_base_conditions(source, request, include_date_bounds=False),
            date_expression.is_not(None),
            date_expression < normalize_dashboard_datetime(request.start_datetime),
        )
        .group_by(*dimensions.values())
    )
    return {
        dimension_key(row): int(row["row_count"] or 0)
        for row in db.execute(statement).mappings().all()
    }


def offline_sla_rows(
    db: Session,
    request: Any,
    source: Any,
) -> dict[tuple[tuple[str, str, str, str, str, str, str], str], dict[str, int]]:
    dimensions = volumetrics_dimension_expressions(source)
    period_expression = volumetrics_period_start_expression(source.c.created_at, "monthly")
    statement = (
        select(
            *[expression.label(name) for name, expression in dimensions.items()],
            period_expression.label("period_start"),
            func.count(source.c.id)
            .filter(source.c.sla_response_sla_breached.is_not(None))
            .label("sla_response_total"),
            func.count(source.c.id)
            .filter(source.c.sla_response_sla_breached.is_(False))
            .label("sla_response_met"),
            func.count(source.c.id)
            .filter(source.c.sla_resolution_sla_breached.is_not(None))
            .label("sla_resolution_total"),
            func.count(source.c.id)
            .filter(source.c.sla_resolution_sla_breached.is_(False))
            .label("sla_resolution_met"),
            func.count(source.c.id)
            .filter(source.c.ola_response_sla_breached.is_not(None))
            .label("ola_response_total"),
            func.count(source.c.id)
            .filter(source.c.ola_response_sla_breached.is_(False))
            .label("ola_response_met"),
            func.count(source.c.id)
            .filter(source.c.ola_resolution_sla_breached.is_not(None))
            .label("ola_resolution_total"),
            func.count(source.c.id)
            .filter(source.c.ola_resolution_sla_breached.is_(False))
            .label("ola_resolution_met"),
        )
        .select_from(source)
        .where(
            *volumetrics_base_conditions(
                source,
                SimpleNamespace(**{**request.__dict__, "ticket_type": "incident"}),
            ),
            source.c.created_at.is_not(None),
        )
        .group_by(*dimensions.values(), period_expression)
    )
    results: dict[tuple[tuple[str, str, str, str, str, str, str], str], dict[str, int]] = {}
    for row in db.execute(statement).mappings().all():
        period_start = row["period_start"]
        if period_start is None:
            continue
        sla_response_total = int(row["sla_response_total"] or 0)
        sla_response_met = int(row["sla_response_met"] or 0)
        sla_resolution_total = int(row["sla_resolution_total"] or 0)
        sla_resolution_met = int(row["sla_resolution_met"] or 0)
        results[(dimension_key(row), month_key(period_start))] = {
            "response_sla_total_count": sla_response_total,
            "response_sla_met_count": sla_response_met,
            "resolution_sla_total_count": sla_resolution_total,
            "resolution_sla_met_count": sla_resolution_met,
            "sla_response_sla_total_count": sla_response_total,
            "sla_response_sla_met_count": sla_response_met,
            "sla_resolution_sla_total_count": sla_resolution_total,
            "sla_resolution_sla_met_count": sla_resolution_met,
            "ola_response_sla_total_count": int(row["ola_response_total"] or 0),
            "ola_response_sla_met_count": int(row["ola_response_met"] or 0),
            "ola_resolution_sla_total_count": int(row["ola_resolution_total"] or 0),
            "ola_resolution_sla_met_count": int(row["ola_resolution_met"] or 0),
        }
    return results


def offline_reassignment_hops_rows(
    db: Session,
    request: Any,
    source: Any,
) -> dict[tuple[tuple[str, str, str, str, str, str, str], str], dict[str, int]]:
    dimensions = volumetrics_dimension_expressions(source)
    period_expression = volumetrics_period_start_expression(source.c.created_at, "monthly")
    reassignment_count = non_negative_reassignment_expression(source)
    high_reassignment_condition = reassignment_count >= 2
    statement = (
        select(
            *[expression.label(name) for name, expression in dimensions.items()],
            period_expression.label("period_start"),
            func.count(source.c.id).label("total_created_tickets"),
            func.count(source.c.id)
            .filter(high_reassignment_condition)
            .label("tickets_with_2_plus_reassignments"),
            func.sum(case((high_reassignment_condition, reassignment_count), else_=0)).label(
                "total_reassignment_hops_ge_2",
            ),
        )
        .select_from(source)
        .where(
            *volumetrics_base_conditions(source, request, include_date_bounds=False),
            source.c.created_at.is_not(None),
            source.c.created_at >= normalize_dashboard_datetime(request.start_datetime),
            source.c.created_at <= normalize_dashboard_datetime(request.end_datetime),
        )
        .group_by(*dimensions.values(), period_expression)
    )
    results: dict[tuple[tuple[str, str, str, str, str, str, str], str], dict[str, int]] = {}
    for row in db.execute(statement).mappings().all():
        period_start = row["period_start"]
        if period_start is None:
            continue
        results[(dimension_key(row), month_key(period_start))] = {
            "total_created_tickets": int(row["total_created_tickets"] or 0),
            "tickets_with_2_plus_reassignments": int(
                row["tickets_with_2_plus_reassignments"] or 0,
            ),
            "total_reassignment_hops_ge_2": int(row["total_reassignment_hops_ge_2"] or 0),
        }
    return results


def problem_management_source_select(model: Any, scope_label: str, project_id: UUID) -> Any:
    return select(
        literal(scope_label).label("scope"),
        model.id.label("id"),
        model.created_at_source.label("created_at_source"),
        model.closed_at.label("closed_at"),
        model.linked_incident_count.label("linked_incident_count"),
        model.functional_track.label("functional_track"),
        model.ams_owner.label("ams_owner"),
        model.sap_non_sap.label("sap_non_sap"),
    ).where(model.project_id == project_id)


def problem_management_source_subquery(project_id: UUID) -> Any:
    return union_all(
        problem_management_source_select(AssessmentProblemRecord, "in_scope", project_id),
        problem_management_source_select(
            AssessmentOutOfScopeProblemRecord,
            "out_of_scope",
            project_id,
        ),
    ).subquery("offline_problem_management_source")


def problem_dimension_expressions(source: Any) -> dict[str, Any]:
    return {
        "scope": source.c.scope,
        "functional_track": volumetrics_display_expression(source.c.functional_track),
        "ams_owner": volumetrics_display_expression(source.c.ams_owner),
        "functional_track_ams_owner": func.concat(
            volumetrics_display_expression(source.c.functional_track),
            literal(" - "),
            volumetrics_display_expression(source.c.ams_owner),
        ),
        "sap_non_sap": volumetrics_display_expression(source.c.sap_non_sap),
    }


def problem_dimension_key(row: dict[str, Any]) -> tuple[str, str, str, str, str]:
    return (
        str(row["scope"]),
        str(row["functional_track"]),
        str(row["ams_owner"]),
        str(row["functional_track_ams_owner"]),
        str(row["sap_non_sap"]),
    )


def problem_dimension_dict(key: tuple[str, str, str, str, str]) -> dict[str, str]:
    return {
        "scope": key[0],
        "functional_track": key[1],
        "ams_owner": key[2],
        "functional_track_ams_owner": key[3],
        "sap_non_sap": key[4],
    }


def non_negative_problem_linked_incident_expression(source: Any) -> Any:
    linked_incident_count = func.coalesce(source.c.linked_incident_count, 0)
    return case((linked_incident_count < 0, 0), else_=linked_incident_count)


def build_problem_management_payload(
    db: Session,
    project_id: UUID,
    start_datetime: datetime,
    end_datetime: datetime,
) -> dict[str, Any]:
    request = monthly_request(project_id, start_datetime, end_datetime)
    periods = build_volumetrics_periods(request)
    source = problem_management_source_subquery(project_id)
    dimensions = problem_dimension_expressions(source)
    created_period = volumetrics_period_start_expression(
        source.c.created_at_source,
        "monthly",
    )
    created_statement = (
        select(
            *[expression.label(name) for name, expression in dimensions.items()],
            created_period.label("period_start"),
            func.count(source.c.id).label("problem_tickets_created"),
        )
        .select_from(source)
        .where(
            source.c.created_at_source.is_not(None),
            source.c.created_at_source >= normalize_dashboard_datetime(start_datetime),
            source.c.created_at_source <= normalize_dashboard_datetime(end_datetime),
        )
        .group_by(*dimensions.values(), created_period)
    )

    closed_period = volumetrics_period_start_expression(
        source.c.closed_at,
        "monthly",
    )
    linked_incident_count = non_negative_problem_linked_incident_expression(source)
    closed_statement = (
        select(
            *[expression.label(name) for name, expression in dimensions.items()],
            closed_period.label("period_start"),
            func.count(source.c.id).label("problem_tickets_closed"),
            func.sum(linked_incident_count).label("linked_incidents_resolved_permanently"),
        )
        .select_from(source)
        .where(
            source.c.closed_at.is_not(None),
            source.c.closed_at >= normalize_dashboard_datetime(start_datetime),
            source.c.closed_at <= normalize_dashboard_datetime(end_datetime),
        )
        .group_by(*dimensions.values(), closed_period)
    )

    created_rows: dict[tuple[tuple[str, str, str, str, str], str], int] = {}
    dimension_keys: set[tuple[str, str, str, str, str]] = set()
    for row in db.execute(created_statement).mappings().all():
        period_start = row["period_start"]
        if period_start is None:
            continue
        key = problem_dimension_key(row)
        dimension_keys.add(key)
        created_rows[(key, month_key(period_start))] = int(row["problem_tickets_created"] or 0)

    closed_rows: dict[tuple[tuple[str, str, str, str, str], str], dict[str, int]] = {}
    for row in db.execute(closed_statement).mappings().all():
        period_start = row["period_start"]
        if period_start is None:
            continue
        key = problem_dimension_key(row)
        dimension_keys.add(key)
        closed_rows[(key, month_key(period_start))] = {
            "problem_tickets_closed": int(row["problem_tickets_closed"] or 0),
            "linked_incidents_resolved_permanently": int(
                row["linked_incidents_resolved_permanently"] or 0,
            ),
        }

    rows: list[dict[str, Any]] = []
    for key in sorted(dimension_keys):
        for period in periods:
            period_key = month_key(period.start)
            closed_values = closed_rows.get((key, period_key), {})
            rows.append(
                {
                    **problem_dimension_dict(key),
                    "period_key": period_key,
                    "period_label": period.label,
                    "problem_tickets_created": created_rows.get((key, period_key), 0),
                    "problem_tickets_closed": closed_values.get("problem_tickets_closed", 0),
                    "linked_incidents_resolved_permanently": closed_values.get(
                        "linked_incidents_resolved_permanently",
                        0,
                    ),
                },
            )

    return {
        "rows": rows,
        "data_notes": [
            "Problem records are analyzed separately from generic tickets.",
            "Problem scope is classified using active Application Inventory assignment groups.",
            "Linked incidents are summed for Problems closed in each month.",
            "Complete-month cutoff applied.",
        ],
    }


def distinct_dimension_keys(
    db: Session,
    request: Any,
    source: Any,
) -> set[tuple[str, str, str, str, str, str, str]]:
    dimensions = volumetrics_dimension_expressions(source)
    statement = (
        select(*[expression.label(name) for name, expression in dimensions.items()])
        .select_from(source)
        .where(*volumetrics_base_conditions(source, request, include_date_bounds=False))
        .group_by(*dimensions.values())
    )
    return {dimension_key(row) for row in db.execute(statement).mappings().all()}


def build_monthly_volumetrics_rows(
    db: Session,
    project_id: UUID,
    start_datetime: datetime,
    end_datetime: datetime,
) -> list[dict[str, Any]]:
    request = monthly_request(project_id, start_datetime, end_datetime)
    periods = build_volumetrics_periods(request)
    source = build_volumetrics_source(project_id)
    cancelled_condition = volumetrics_cancelled_expression(source)

    created_rows = offline_period_rows(db, request, source, source.c.created_at, "created_count")
    completed_rows = offline_period_rows(
        db,
        request,
        source,
        source.c.completion_at,
        "resolved_closed_count",
        [~cancelled_condition],
    )
    cancelled_rows = offline_period_rows(
        db,
        request,
        source,
        source.c.completion_at,
        "cancelled_count",
        [cancelled_condition],
    )
    exit_rows = offline_period_rows(db, request, source, source.c.exit_at, "exit_count")
    sla_rows = offline_sla_rows(db, request, source)
    reassignment_hops_rows = offline_reassignment_hops_rows(db, request, source)
    initial_created = offline_initial_counts(db, request, source, source.c.created_at)
    initial_exits = offline_initial_counts(db, request, source, source.c.exit_at)

    dimension_keys = distinct_dimension_keys(db, request, source)
    for row_key, _period_key in [
        *created_rows.keys(),
        *completed_rows.keys(),
        *cancelled_rows.keys(),
        *exit_rows.keys(),
        *sla_rows.keys(),
        *reassignment_hops_rows.keys(),
    ]:
        dimension_keys.add(row_key)

    rows: list[dict[str, Any]] = []
    for key in sorted(dimension_keys):
        running_created = initial_created.get(key, 0)
        running_exits = initial_exits.get(key, 0)
        for period in periods:
            period_key = month_key(period.start)
            created_count = created_rows.get((key, period_key), 0)
            running_created += created_count
            running_exits += exit_rows.get((key, period_key), 0)
            sla_values = sla_rows.get((key, period_key), {})
            reassignment_values = reassignment_hops_rows.get((key, period_key), {})
            rows.append(
                {
                    **dimension_dict(key),
                    "period_key": period_key,
                    "period_label": period.label,
                    "created_count": created_count,
                    "tickets_with_2_plus_reassignments": reassignment_values.get(
                        "tickets_with_2_plus_reassignments",
                        0,
                    ),
                    "total_reassignment_hops_ge_2": reassignment_values.get(
                        "total_reassignment_hops_ge_2",
                        0,
                    ),
                    "resolved_closed_count": completed_rows.get((key, period_key), 0),
                    "canceled_closed_incomplete_count": cancelled_rows.get((key, period_key), 0),
                    "backlog_open": max(running_created - running_exits, 0),
                    "response_sla_met_count": sla_values.get("response_sla_met_count", 0),
                    "response_sla_total_count": sla_values.get("response_sla_total_count", 0),
                    "resolution_sla_met_count": sla_values.get("resolution_sla_met_count", 0),
                    "resolution_sla_total_count": sla_values.get("resolution_sla_total_count", 0),
                    "sla_response_sla_met_count": sla_values.get("sla_response_sla_met_count", 0),
                    "sla_response_sla_total_count": sla_values.get(
                        "sla_response_sla_total_count",
                        0,
                    ),
                    "sla_resolution_sla_met_count": sla_values.get(
                        "sla_resolution_sla_met_count",
                        0,
                    ),
                    "sla_resolution_sla_total_count": sla_values.get(
                        "sla_resolution_sla_total_count",
                        0,
                    ),
                    "ola_response_sla_met_count": sla_values.get("ola_response_sla_met_count", 0),
                    "ola_response_sla_total_count": sla_values.get(
                        "ola_response_sla_total_count",
                        0,
                    ),
                    "ola_resolution_sla_met_count": sla_values.get(
                        "ola_resolution_sla_met_count",
                        0,
                    ),
                    "ola_resolution_sla_total_count": sla_values.get(
                        "ola_resolution_sla_total_count",
                        0,
                    ),
                },
            )
    return rows


def build_reassignment_hops_payload(monthly_rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "rows": [
            {
                **dimension_dict(
                    (
                        str(row["scope"]),
                        str(row["ticket_type"]),
                        str(row["functional_track"]),
                        str(row["ams_owner"]),
                        str(row["functional_track_ams_owner"]),
                        str(row["sap_non_sap"]),
                        str(row["business_critical"]),
                    ),
                ),
                "period_key": row["period_key"],
                "period_label": row["period_label"],
                "total_created_tickets": int(row.get("created_count") or 0),
                "tickets_with_2_plus_reassignments": int(
                    row.get("tickets_with_2_plus_reassignments") or 0,
                ),
                "total_reassignment_hops_ge_2": int(
                    row.get("total_reassignment_hops_ge_2") or 0,
                ),
            }
            for row in monthly_rows
        ],
    }


def pattern_bucket_metadata(start_date: datetime, end_date: datetime) -> dict[str, list[dict[str, Any]]]:
    start = start_date.date()
    end = end_date.date()
    day_of_month_counts = date_counts_by_day_of_month(start, end)
    weekday_counts = date_counts_by_weekday(start, end)
    weekday_labels = (
        ("Mon", 1, 0),
        ("Tue", 2, 1),
        ("Wed", 3, 2),
        ("Thu", 4, 3),
        ("Fri", 5, 4),
        ("Sat", 6, 5),
        ("Sun", 0, 6),
    )
    return {
        "day_of_month": [
            {"label": str(day), "bucket_sort": day, "bucket_value": day, "denominator": count}
            for day, count in day_of_month_counts.items()
        ],
        "day_of_week": [
            {
                "label": label,
                "bucket_sort": sort_value,
                "bucket_value": postgres_value,
                "denominator": weekday_counts[python_value],
            }
            for sort_value, (label, postgres_value, python_value) in enumerate(weekday_labels, 1)
        ],
        "hour_weekdays": [
            {
                "label": f"{hour:02d}",
                "bucket_sort": hour,
                "bucket_value": hour,
                "denominator": day_count_for_week_part(start, end, weekdays=True),
            }
            for hour in range(24)
        ],
        "hour_weekends": [
            {
                "label": f"{hour:02d}",
                "bucket_sort": hour,
                "bucket_value": hour,
                "denominator": day_count_for_week_part(start, end, weekdays=False),
            }
            for hour in range(24)
        ],
    }


def offline_created_pattern_rows(
    db: Session,
    request: Any,
    source: Any,
    pattern_type: str,
    bucket_expression: Any,
    bucket_map: dict[int, dict[str, Any]],
    extra_conditions: list[Any] | None = None,
) -> list[dict[str, Any]]:
    dimensions = volumetrics_dimension_expressions(source)
    conditions = volumetrics_base_conditions(source, request)
    if extra_conditions:
        conditions.extend(extra_conditions)
    statement = (
        select(
            *[expression.label(name) for name, expression in dimensions.items()],
            bucket_expression.label("bucket"),
            func.count(source.c.id).label("total_created"),
        )
        .select_from(source)
        .where(*conditions)
        .group_by(*dimensions.values(), bucket_expression)
    )
    rows = []
    for row in db.execute(statement).mappings().all():
        bucket = int(row["bucket"]) if row["bucket"] is not None else None
        if bucket is None or bucket not in bucket_map:
            continue
        metadata = bucket_map[bucket]
        denominator = int(metadata["denominator"] or 0)
        total_created = int(row["total_created"] or 0)
        rows.append(
            {
                **dimension_dict(dimension_key(row)),
                "pattern_type": pattern_type,
                "bucket_label": metadata["label"],
                "bucket_sort": metadata["bucket_sort"],
                "total_created": total_created,
                "denominator": denominator,
                "average_created": total_created / denominator if denominator else 0,
            },
        )
    return rows


def build_created_pattern_payload(
    db: Session,
    project_id: UUID,
    start_datetime: datetime,
    end_datetime: datetime,
) -> dict[str, Any]:
    request = monthly_request(project_id, start_datetime, end_datetime)
    source = build_volumetrics_source(project_id)
    buckets = pattern_bucket_metadata(start_datetime, end_datetime)
    day_expression = cast(func.extract("day", source.c.created_at), Integer)
    dow_expression = cast(func.extract("dow", source.c.created_at), Integer)
    hour_expression = cast(func.extract("hour", source.c.created_at), Integer)

    rows: list[dict[str, Any]] = []
    rows.extend(
        offline_created_pattern_rows(
            db,
            request,
            source,
            "day_of_month",
            day_expression,
            {bucket["bucket_value"]: bucket for bucket in buckets["day_of_month"]},
            [day_expression <= 30],
        ),
    )
    rows.extend(
        offline_created_pattern_rows(
            db,
            request,
            source,
            "day_of_week",
            dow_expression,
            {bucket["bucket_value"]: bucket for bucket in buckets["day_of_week"]},
        ),
    )
    rows.extend(
        offline_created_pattern_rows(
            db,
            request,
            source,
            "hour_weekdays",
            hour_expression,
            {bucket["bucket_value"]: bucket for bucket in buckets["hour_weekdays"]},
            [dow_expression.between(1, 5)],
        ),
    )
    rows.extend(
        offline_created_pattern_rows(
            db,
            request,
            source,
            "hour_weekends",
            hour_expression,
            {bucket["bucket_value"]: bucket for bucket in buckets["hour_weekends"]},
            [dow_expression.in_((0, 6))],
        ),
    )
    return {"buckets": buckets, "rows": rows}


def offline_hourly_count_rows(
    db: Session,
    request: Any,
    source: Any,
    date_expression: Any,
    *,
    day_type: str,
    value_label: str,
    extra_conditions: list[Any] | None = None,
) -> dict[tuple[tuple[str, str, str, str, str, str, str], int], int]:
    dimensions = volumetrics_dimension_expressions(source)
    hour_expression = cast(func.extract("hour", date_expression), Integer)
    dow_expression = cast(func.extract("dow", date_expression), Integer)
    conditions = [
        *volumetrics_base_conditions(source, request, include_date_bounds=False),
        date_expression.is_not(None),
        date_expression >= normalize_dashboard_datetime(request.start_datetime),
        date_expression <= normalize_dashboard_datetime(request.end_datetime),
        dow_expression.between(1, 5) if day_type == "weekdays" else dow_expression.in_((0, 6)),
    ]
    if extra_conditions:
        conditions.extend(extra_conditions)

    statement = (
        select(
            *[expression.label(name) for name, expression in dimensions.items()],
            hour_expression.label("hour"),
            func.count(source.c.id).label(value_label),
        )
        .select_from(source)
        .where(*conditions)
        .group_by(*dimensions.values(), hour_expression)
    )
    rows: dict[tuple[tuple[str, str, str, str, str, str, str], int], int] = {}
    for row in db.execute(statement).mappings().all():
        if row["hour"] is None:
            continue
        rows[(dimension_key(row), int(row["hour"]))] = int(row[value_label] or 0)
    return rows


def build_hourly_created_resolved_payload(
    db: Session,
    project_id: UUID,
    start_datetime: datetime,
    end_datetime: datetime,
) -> dict[str, Any]:
    request = monthly_request(project_id, start_datetime, end_datetime)
    source = build_volumetrics_source(project_id)
    cancelled_condition = volumetrics_cancelled_expression(source)
    denominators = {
        "weekdays": day_count_for_week_part(
            start_datetime.date(),
            end_datetime.date(),
            weekdays=True,
        ),
        "weekends": day_count_for_week_part(
            start_datetime.date(),
            end_datetime.date(),
            weekdays=False,
        ),
    }
    rows: list[dict[str, Any]] = []
    for day_type in ("weekdays", "weekends"):
        created_rows = offline_hourly_count_rows(
            db,
            request,
            source,
            source.c.created_at,
            day_type=day_type,
            value_label="created_count",
        )
        resolved_rows = offline_hourly_count_rows(
            db,
            request,
            source,
            source.c.completion_at,
            day_type=day_type,
            value_label="resolved_closed_count",
            extra_conditions=[~cancelled_condition],
        )
        keys = {key for key, _hour in [*created_rows.keys(), *resolved_rows.keys()]}
        denominator = denominators[day_type]
        for key in sorted(keys):
            for hour in range(24):
                created_count = created_rows.get((key, hour), 0)
                resolved_count = resolved_rows.get((key, hour), 0)
                rows.append(
                    {
                        **dimension_dict(key),
                        "day_type": day_type,
                        "hour": f"{hour:02d}",
                        "total_created": created_count,
                        "total_resolved_closed": resolved_count,
                        "denominator_days": denominator,
                        "average_created": created_count / denominator if denominator else 0,
                        "average_resolved_closed": (
                            resolved_count / denominator if denominator else 0
                        ),
                    },
                )
    return {"rows": rows, "denominators": denominators}


def build_priority_distribution_payload(
    db: Session,
    project_id: UUID,
    start_datetime: datetime,
    end_datetime: datetime,
) -> dict[str, Any]:
    request = monthly_request(project_id, start_datetime, end_datetime)
    source = build_volumetrics_source(project_id)
    dimensions = volumetrics_dimension_expressions(source)
    period_expression = volumetrics_period_start_expression(source.c.created_at, "monthly")
    priority_expression = volumetrics_display_expression(source.c.priority)
    statement = (
        select(
            *[expression.label(name) for name, expression in dimensions.items()],
            period_expression.label("period_start"),
            priority_expression.label("priority"),
            func.count(source.c.id).label("ticket_count"),
        )
        .select_from(source)
        .where(*volumetrics_base_conditions(source, request))
        .group_by(*dimensions.values(), period_expression, priority_expression)
    )
    rows = []
    priorities: set[str] = set()
    for row in db.execute(statement).mappings().all():
        period_start = row["period_start"]
        if period_start is None:
            continue
        priority = str(row["priority"])
        priorities.add(priority)
        rows.append(
            {
                **dimension_dict(dimension_key(row)),
                "period_key": month_key(period_start),
                "period_label": f"{period_start:%b-%y}",
                "priority": priority,
                "ticket_count": int(row["ticket_count"] or 0),
            },
        )
    return {
        "priorities": sorted(priorities, key=priority_sort_key),
        "rows": rows,
    }


def build_sla_trends_payload(
    db: Session,
    project_id: UUID,
    start_datetime: datetime,
    end_datetime: datetime,
) -> dict[str, Any]:
    request = SimpleNamespace(
        project_id=project_id,
        scope="all",
        ticket_type="incident",
        time_grain="monthly",
        start_datetime=start_datetime,
        end_datetime=end_datetime,
        filters=SimpleNamespace(
            functional_track_ams_owner=[],
            assignment_group_support_lead=[],
            parent_application_name=[],
            application_owner=[],
            supported_by_vendor=[],
            sap_non_sap=[],
        ),
    )
    source = build_volumetrics_source(project_id)
    dimensions = volumetrics_dimension_expressions(source)
    period_expression = volumetrics_period_start_expression(source.c.resolved_at, "monthly")
    statement = (
        select(
            *[expression.label(name) for name, expression in dimensions.items()],
            period_expression.label("period_start"),
            func.count(source.c.id).label("total_closed_ticket_count"),
            func.count(source.c.id)
            .filter(source.c.sla_response_sla_breached.is_not(None))
            .label("response_sla_captured_count"),
            func.count(source.c.id)
            .filter(source.c.sla_response_sla_breached.is_(False))
            .label("response_sla_adhered_count"),
            func.count(source.c.id)
            .filter(source.c.sla_resolution_sla_breached.is_not(None))
            .label("resolution_sla_captured_count"),
            func.count(source.c.id)
            .filter(source.c.sla_resolution_sla_breached.is_(False))
            .label("resolution_sla_adhered_count"),
            func.count(source.c.id)
            .filter(source.c.ola_response_sla_breached.is_not(None))
            .label("response_ola_captured_count"),
            func.count(source.c.id)
            .filter(source.c.ola_response_sla_breached.is_(False))
            .label("response_ola_adhered_count"),
            func.count(source.c.id)
            .filter(source.c.ola_resolution_sla_breached.is_not(None))
            .label("resolution_ola_captured_count"),
            func.count(source.c.id)
            .filter(source.c.ola_resolution_sla_breached.is_(False))
            .label("resolution_ola_adhered_count"),
        )
        .select_from(source)
        .where(
            *volumetrics_base_conditions(source, request, include_date_bounds=False),
            source.c.resolved_at.is_not(None),
            source.c.resolved_at >= normalize_dashboard_datetime(start_datetime),
            source.c.resolved_at <= normalize_dashboard_datetime(end_datetime),
        )
        .group_by(*dimensions.values(), period_expression)
    )
    rows = []
    for row in db.execute(statement).mappings().all():
        period_start = row["period_start"]
        if period_start is None:
            continue
        rows.append(
            {
                **dimension_dict(dimension_key(row)),
                "period_key": month_key(period_start),
                "period_label": f"{period_start:%b-%y}",
                "total_closed_ticket_count": int(row["total_closed_ticket_count"] or 0),
                "response_sla_captured_count": int(row["response_sla_captured_count"] or 0),
                "response_sla_adhered_count": int(row["response_sla_adhered_count"] or 0),
                "resolution_sla_captured_count": int(row["resolution_sla_captured_count"] or 0),
                "resolution_sla_adhered_count": int(row["resolution_sla_adhered_count"] or 0),
                "response_ola_captured_count": int(row["response_ola_captured_count"] or 0),
                "response_ola_adhered_count": int(row["response_ola_adhered_count"] or 0),
                "resolution_ola_captured_count": int(row["resolution_ola_captured_count"] or 0),
                "resolution_ola_adhered_count": int(row["resolution_ola_adhered_count"] or 0),
            },
        )
    return {
        "rows": rows,
        "logic": {
            "response_adherence_formula": (
                "response_sla_adhered_count / response_sla_captured_count * 100"
            ),
            "resolution_adherence_formula": (
                "resolution_sla_adhered_count / resolution_sla_captured_count * 100"
            ),
            "captured_definition": "sla_breached IS NOT NULL",
            "supported_modes": ["sla", "ola"],
        },
    }


def build_detailed_volume_payload(
    db: Session,
    project_id: UUID,
    start_datetime: datetime,
    end_datetime: datetime,
) -> dict[str, Any]:
    request = monthly_request(project_id, start_datetime, end_datetime)
    source = build_volumetrics_source(project_id)
    dimensions = volumetrics_dimension_expressions(source)
    period_expression = volumetrics_period_start_expression(source.c.created_at, "monthly")
    application_expression = volumetrics_display_expression(source.c.business_service_ci_name)
    architecture_expression = volumetrics_display_expression(source.c.architecture_type)
    install_expression = volumetrics_display_expression(source.c.install_type)
    hosting_env_expression = volumetrics_display_expression(source.c.hosting_env)
    catalog_item_expression = func.coalesce(
        nonblank_text_expression(source.c.catalog_item_name),
        literal("Unmapped Catalog Item"),
    )
    cancelled_condition = volumetrics_cancelled_expression(source)
    incident_batch_condition = (
        (source.c.ticket_type == "INCIDENT") & source.c.is_batch_related.is_(True)
    )
    statement = (
        select(
            *[expression.label(name) for name, expression in dimensions.items()],
            application_expression.label("application_name"),
            architecture_expression.label("architecture_type"),
            install_expression.label("install_type"),
            hosting_env_expression.label("hosting_env"),
            catalog_item_expression.label("catalog_item_name"),
            period_expression.label("period_start"),
            func.count(source.c.id).label("created_count"),
            func.count(source.c.id)
            .filter(cancelled_condition)
            .label("canceled_closed_incomplete_count"),
            func.count(source.c.id)
            .filter(incident_batch_condition)
            .label("incident_batch_created_count"),
            func.count(source.c.id)
            .filter(incident_batch_condition & cancelled_condition)
            .label("incident_batch_canceled_count"),
        )
        .select_from(source)
        .where(*volumetrics_base_conditions(source, request))
        .group_by(
            *dimensions.values(),
            application_expression,
            architecture_expression,
            install_expression,
            hosting_env_expression,
            catalog_item_expression,
            period_expression,
        )
    )
    rows = []
    for row in db.execute(statement).mappings().all():
        period_start = row["period_start"]
        if period_start is None:
            continue
        rows.append(
            {
                **dimension_dict(dimension_key(row)),
                "application_name": str(row["application_name"]),
                "architecture_type": str(row["architecture_type"]),
                "install_type": str(row["install_type"]),
                "hosting_env": str(row["hosting_env"]),
                "catalog_item_name": str(row["catalog_item_name"]),
                "period_key": month_key(period_start),
                "period_label": f"{period_start:%b-%y}",
                "created_count": int(row["created_count"] or 0),
                "canceled_closed_incomplete_count": int(
                    row["canceled_closed_incomplete_count"] or 0,
                ),
                "incident_batch_created_count": int(row["incident_batch_created_count"] or 0),
                "incident_batch_canceled_count": int(row["incident_batch_canceled_count"] or 0),
            },
        )

    window_start, window_end = latest_complete_month_window(db, project_id, 6)
    split_window_start, split_window_end = latest_complete_month_window(db, project_id, 6)
    return {
        "ranking_window": ranking_window_payload(window_start, window_end),
        "split_window": latest_complete_window_payload(split_window_start, split_window_end),
        "application_rows": rows,
        "split_rows": build_detailed_split_rows(db, project_id),
        "batch_rule": {
            "field": "short_description",
            "rule_description": (
                "Incident is batch-related when short_description contains Automic, "
                "case-insensitive."
            ),
        },
    }


def build_detailed_split_rows(db: Session, project_id: UUID) -> list[dict[str, Any]]:
    window_start, window_end = latest_complete_month_window(db, project_id, 6)
    request = monthly_request(project_id, window_start, window_end)
    source = build_volumetrics_source(project_id)
    dimensions = volumetrics_dimension_expressions(source)
    rows: list[dict[str, Any]] = []

    for split_type in ("architecture_type", "install_type", "hosting_env"):
        split_expression = volumetrics_display_expression(getattr(source.c, split_type))
        statement = (
            select(
                *[expression.label(name) for name, expression in dimensions.items()],
                literal(split_type).label("split_type"),
                split_expression.label("split_label"),
                func.count(source.c.id).label("created_count"),
            )
            .select_from(source)
            .where(*volumetrics_base_conditions(source, request))
            .group_by(*dimensions.values(), split_expression)
        )
        for row in db.execute(statement).mappings().all():
            rows.append(
                {
                    **dimension_dict(dimension_key(row)),
                    "split_type": str(row["split_type"]),
                    "split_label": str(row["split_label"]),
                    "created_count": int(row["created_count"] or 0),
                },
            )
    return rows


def build_kpi_mttr_payload(
    db: Session,
    project_id: UUID,
    start_datetime: datetime,
    end_datetime: datetime,
) -> dict[str, Any]:
    request = monthly_request(project_id, start_datetime, end_datetime)
    source = build_volumetrics_source(project_id)
    dimensions = volumetrics_dimension_expressions(source)
    rows: list[dict[str, Any]] = []

    for ticket_type, completion_field in (
        ("incident", "resolved_at"),
        ("sc_task", "closed_at"),
    ):
        completion_expression = getattr(source.c, completion_field)
        period_expression = volumetrics_period_start_expression(completion_expression, "monthly")
        priority_expression = priority_bucket_expression(source)
        effective_request = SimpleNamespace(**{**request.__dict__, "ticket_type": ticket_type})
        statement = (
            select(
                *[expression.label(name) for name, expression in dimensions.items()],
                period_expression.label("period_start"),
                priority_expression.label("priority_bucket"),
                func.sum(cast(source.c.business_duration_seconds, Float)).label(
                    "business_duration_seconds_sum",
                ),
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
                completion_expression >= normalize_dashboard_datetime(start_datetime),
                completion_expression <= normalize_dashboard_datetime(end_datetime),
                source.c.business_duration_seconds.is_not(None),
                source.c.business_duration_seconds >= 0,
                priority_expression.in_(MTTR_PRIORITIES),
            )
            .group_by(*dimensions.values(), period_expression, priority_expression)
        )
        for row in db.execute(statement).mappings().all():
            period_start = row["period_start"]
            if period_start is None or row["priority_bucket"] is None:
                continue
            rows.append(
                {
                    **dimension_dict(dimension_key(row)),
                    "period_key": month_key(period_start),
                    "period_label": f"{period_start:%b-%y}",
                    "priority": str(row["priority_bucket"]),
                    "business_duration_seconds_sum": float(
                        row["business_duration_seconds_sum"] or 0,
                    ),
                    "ticket_count": int(row["ticket_count"] or 0),
                },
            )
    return {"rows": rows}


def build_duration_bucket_payload(db: Session, project_id: UUID) -> dict[str, Any]:
    window_start, window_end = latest_complete_month_window(db, project_id, 3)
    request = monthly_request(project_id, window_start, window_end)
    source = build_volumetrics_source(project_id)
    dimensions = volumetrics_dimension_expressions(source)
    periods = [
        {
            "period_key": month_key(period.start),
            "period_label": period.label,
        }
        for period in build_volumetrics_periods(request)
    ]
    rows: list[dict[str, Any]] = []

    for ticket_type, completion_field in (
        ("incident", "resolved_at"),
        ("sc_task", "closed_at"),
    ):
        completion_expression = getattr(source.c, completion_field)
        period_expression = volumetrics_period_start_expression(completion_expression, "monthly")
        duration_seconds = func.extract("epoch", completion_expression - source.c.created_at)
        bucket_expression = duration_bucket_expression(duration_seconds)
        effective_request = SimpleNamespace(**{**request.__dict__, "ticket_type": ticket_type})
        statement = (
            select(
                *[expression.label(name) for name, expression in dimensions.items()],
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
                completion_expression >= normalize_dashboard_datetime(window_start),
                completion_expression <= normalize_dashboard_datetime(window_end),
                completion_expression >= source.c.created_at,
                bucket_expression.is_not(None),
            )
            .group_by(*dimensions.values(), period_expression, bucket_expression)
        )
        for row in db.execute(statement).mappings().all():
            period_start = row["period_start"]
            if period_start is None or row["bucket"] is None:
                continue
            rows.append(
                {
                    **dimension_dict(dimension_key(row)),
                    "period_key": month_key(period_start),
                    "period_label": f"{period_start:%b-%y}",
                    "bucket": str(row["bucket"]),
                    "ticket_count": int(row["ticket_count"] or 0),
                },
            )

    return {
        "periods": periods,
        "buckets": list(DURATION_BUCKETS),
        "rows": rows,
    }


def build_filter_values(monthly_rows: list[dict[str, Any]]) -> dict[str, Any]:
    functional_values = sorted(
        {row["functional_track_ams_owner"] for row in monthly_rows},
        key=str.casefold,
    )
    sap_values = sorted(
        {row["sap_non_sap"] for row in monthly_rows},
        key=lambda value: {"SAP": 0, "Non-SAP": 1, BLANK_LABEL: 2}.get(value, 3),
    )
    criticality_rank = {
        label.casefold(): index for index, label in enumerate(APPLICATION_CRITICALITY_ORDER)
    }
    business_critical_values = sorted(
        {
            row["business_critical"]
            for row in monthly_rows
            if row["business_critical"] != BLANK_LABEL
        },
        key=lambda value: (
            criticality_rank.get(value.casefold(), len(APPLICATION_CRITICALITY_ORDER)),
            str(value).casefold(),
        ),
    )
    return {
        "scope": [
            {"label": "All", "value": "all"},
            *[
                {"label": VOLUMETRICS_SCOPE_LABELS[value], "value": value}
                for value in OFFLINE_SCOPE_VALUES
            ],
        ],
        "ticket_type": [
            {"label": "All", "value": "all"},
            *[
                {"label": VOLUMETRICS_TICKET_TYPE_LABELS[value], "value": value}
                for value in OFFLINE_TICKET_TYPE_VALUES
            ],
        ],
        "functional_track_ams_owner": functional_values,
        "sap_non_sap": sap_values,
        "business_critical": business_critical_values,
    }


def build_volumetrics_payload(
    db: Session,
    project_id: UUID,
    data_range: dict[str, Any],
) -> dict[str, Any]:
    start_value = data_range["completion_date_min"]
    end_value = data_range["completion_date_max"]
    if start_value is None or end_value is None:
        return {
            "filter_values": build_filter_values([]),
            "periods": [],
            "monthly_rows": [],
            "created_patterns": {"buckets": {}, "rows": []},
            "sub_tabs": [
                "overall_volume_trends",
                "overall_sla_trends",
                "detailed_volume_trends",
                "kpi_trends",
                "category_wise_trends",
                "assignment_group_volumetrics",
            ],
            "overall_volume_trends": {
                "created_resolved_by_hour": {"rows": [], "denominators": {}},
                "priority_distribution": {"priorities": [], "rows": []},
            },
            "overall_sla_trends": {"rows": [], "logic": {}},
            "detailed_volume_trends": {
                "ranking_window": {},
                "split_window": {},
                "application_rows": [],
                "split_rows": [],
                "batch_rule": {},
            },
            "kpi_trends": {
                "mttr": {"rows": []},
                "duration_buckets": {"periods": [], "buckets": [], "rows": []},
                "reassignment_hops": {"rows": []},
                "problem_management": {"rows": [], "data_notes": []},
            },
            "placeholders": {
                "category_wise_trends": "Detailed requirements for this section will be added in the next prompts.",
            },
            "assignment_group_volumetrics": {},
            "complete_month_from": None,
            "complete_month_to": None,
        }

    start_datetime, end_datetime = complete_month_bounds(start_value, end_value)
    if start_datetime is None or end_datetime is None:
        return {
            "filter_values": build_filter_values([]),
            "periods": [],
            "monthly_rows": [],
            "created_patterns": {"buckets": {}, "rows": []},
            "sub_tabs": [
                "overall_volume_trends",
                "overall_sla_trends",
                "detailed_volume_trends",
                "kpi_trends",
                "category_wise_trends",
                "assignment_group_volumetrics",
            ],
            "overall_volume_trends": {
                "created_resolved_by_hour": {"rows": [], "denominators": {}},
                "priority_distribution": {"priorities": [], "rows": []},
            },
            "overall_sla_trends": {"rows": [], "logic": {}},
            "detailed_volume_trends": {
                "ranking_window": {},
                "split_window": {},
                "application_rows": [],
                "split_rows": [],
                "batch_rule": {},
            },
            "kpi_trends": {
                "mttr": {"rows": []},
                "duration_buckets": {"periods": [], "buckets": [], "rows": []},
                "reassignment_hops": {"rows": []},
                "problem_management": {"rows": [], "data_notes": []},
            },
            "placeholders": {
                "category_wise_trends": "Detailed requirements for this section will be added in the next prompts.",
            },
            "assignment_group_volumetrics": {},
            "complete_month_from": None,
            "complete_month_to": None,
        }

    request = monthly_request(project_id, start_datetime, end_datetime)
    periods = [
        {
            "period_key": month_key(period.start),
            "period_label": period.label,
            "period_start": period.start,
            "period_end": period.end,
        }
        for period in build_volumetrics_periods(request)
    ]
    monthly_rows = build_monthly_volumetrics_rows(db, project_id, start_datetime, end_datetime)
    return {
        "filter_values": build_filter_values(monthly_rows),
        "periods": periods,
        "monthly_rows": monthly_rows,
        "created_patterns": build_created_pattern_payload(
            db,
            project_id,
            start_datetime,
            end_datetime,
        ),
        "sub_tabs": [
            "overall_volume_trends",
            "overall_sla_trends",
            "detailed_volume_trends",
            "kpi_trends",
            "category_wise_trends",
            "assignment_group_volumetrics",
        ],
        "overall_volume_trends": {
            "created_resolved_by_hour": build_hourly_created_resolved_payload(
                db,
                project_id,
                start_datetime,
                end_datetime,
            ),
            "priority_distribution": build_priority_distribution_payload(
                db,
                project_id,
                start_datetime,
                end_datetime,
            ),
        },
        "overall_sla_trends": build_sla_trends_payload(
            db,
            project_id,
            start_datetime,
            end_datetime,
        ),
        "detailed_volume_trends": build_detailed_volume_payload(
            db,
            project_id,
            start_datetime,
            end_datetime,
        ),
        "kpi_trends": {
            "mttr": build_kpi_mttr_payload(db, project_id, start_datetime, end_datetime),
            "duration_buckets": build_duration_bucket_payload(db, project_id),
            "reassignment_hops": build_reassignment_hops_payload(monthly_rows),
            "problem_management": build_problem_management_payload(
                db,
                project_id,
                start_datetime,
                end_datetime,
            ),
        },
        "placeholders": {
            "category_wise_trends": "Detailed requirements for this section will be added in the next prompts.",
        },
        "assignment_group_volumetrics": build_assignment_group_volumetrics_payload(
            db,
            project_id,
        ),
        "complete_month_from": start_datetime,
        "complete_month_to": end_datetime,
    }


def build_offline_dashboard_payload(db: Session, project_id: UUID) -> dict[str, Any]:
    project, client = get_project_metadata(db, project_id)
    exported_at = datetime.now(UTC)
    data_range = volumetrics_data_range(db, project_id)
    overview = overview_summary(db, project_id)
    volumetrics = build_volumetrics_payload(db, project_id, data_range)
    return {
        "metadata": {
            "version": "1.0",
            "exported_at": exported_at,
            "customer_name": client.name,
            "customer_logo_data_url": customer_logo_data_url(client.name),
            "project_name": project.name,
            "project_id": str(project.id),
            "data_available_from": data_range["completion_date_min"],
            "data_available_to": data_range["completion_date_max"],
            "complete_month_from": volumetrics["complete_month_from"],
            "complete_month_to": volumetrics["complete_month_to"],
            "time_grain": "monthly",
            "offline_filters": [
                "scope",
                "ticket_type",
                "functional_track_ams_owner",
                "sap_non_sap",
                "business_critical",
            ],
        },
        "overview": overview,
        "applications": build_applications_payload(db, project_id),
        "volumetrics": volumetrics,
        "commentaries": export_project_commentaries(db, project_id),
    }


def render_offline_dashboard_html(payload: dict[str, Any]) -> str:
    title = (
        f"{payload['metadata']['customer_name']} - "
        f"{payload['metadata']['project_name']} Dashboard"
    )
    escaped_title = html.escape(title)
    payload_json = json_script_payload(payload)
    return OFFLINE_DASHBOARD_TEMPLATE.replace("__PAGE_TITLE__", escaped_title).replace(
        "__DASHBOARD_DATA_JSON__",
        payload_json,
    )


def build_offline_dashboard_export(db: Session, project_id: UUID) -> tuple[str, str]:
    payload = build_offline_dashboard_payload(db, project_id)
    exported_at = payload["metadata"]["exported_at"]
    filename = dashboard_filename(
        str(payload["metadata"]["customer_name"]),
        str(payload["metadata"]["project_name"]),
        exported_at,
    )
    return render_offline_dashboard_html(payload), filename


OFFLINE_DASHBOARD_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>__PAGE_TITLE__</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f3f6fa;
      --panel: #ffffff;
      --border: #d9e2ec;
      --text: #111827;
      --muted: #52627a;
      --teal: #0f766e;
      --blue: #2563eb;
      --red: #dc2626;
      --orange: #d97706;
      --purple: #7c3aed;
      font-family: Inter, "Segoe UI", Arial, sans-serif;
    }
    *,
    *::before,
    *::after {
      box-sizing: border-box;
    }
    html,
    body {
      width: 100%;
      inline-size: 100%;
      min-height: 100%;
      height: auto;
      max-width: 100%;
      max-inline-size: 100%;
      margin: 0;
      overflow-x: hidden;
      overflow-y: auto;
      background: var(--bg);
      color: var(--text);
    }
    .shell {
      display: grid;
      grid-template-rows: auto auto auto;
      gap: 8px;
      width: 100%;
      inline-size: 100%;
      max-width: 100vw;
      max-inline-size: 100vw;
      min-height: 100vh;
      height: auto;
      min-width: 0;
      min-inline-size: 0;
      overflow-x: hidden;
      overflow-y: visible;
      padding: 8px 10px;
    }
    .topbar, .panel {
      border: 1px solid var(--border);
      border-radius: 8px;
      background: var(--panel);
      box-shadow: 0 1px 3px rgba(15, 23, 42, 0.05);
    }
    .topbar {
      display: grid;
      grid-template-columns: minmax(120px, 220px) minmax(0, 1fr) minmax(160px, 240px);
      gap: 14px;
      align-items: center;
      min-width: 0;
      min-height: 72px;
      max-height: 92px;
      overflow: hidden;
      padding: 8px 14px;
    }
    .customer-logo {
      display: flex;
      align-items: center;
      min-height: 0;
      min-width: 0;
    }
    .customer-logo img {
      display: block;
      max-width: 165px;
      max-height: 36px;
      object-fit: contain;
    }
    .dashboard-title {
      min-width: 0;
      text-align: center;
    }
    #export-meta {
      line-height: 1.25;
      text-align: right;
    }
    h1, h2, h3 { margin: 0; }
    h1 { font-size: 1.16rem; }
    h2 { font-size: 1.08rem; }
    h3 { font-size: 1rem; }
    .label {
      margin: 0 0 5px;
      color: #536783;
      font-size: 0.76rem;
      font-weight: 900;
      letter-spacing: 0;
      text-transform: uppercase;
    }
    .muted { color: var(--muted); font-size: 0.88rem; }
    .tabs {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 8px;
      min-height: 0;
    }
    .tab {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      height: 34px;
      min-height: 34px;
      max-height: 34px;
      padding: 0 14px;
      border: 1px solid var(--border);
      border-radius: 8px;
      background: #fff;
      color: #334155;
      cursor: pointer;
      font-weight: 900;
      line-height: 1;
    }
    .tab.active { border-color: var(--teal); color: #fff; background: var(--teal); }
    .view {
      display: none;
      width: 100%;
      inline-size: 100%;
      max-width: 100%;
      max-inline-size: 100%;
      min-width: 0;
      min-inline-size: 0;
      min-height: 0;
      overflow-x: hidden;
      overflow-y: visible;
    }
    .view.active {
      display: grid;
      gap: 12px;
      width: 100%;
      inline-size: 100%;
      max-width: 100%;
      max-inline-size: 100%;
      height: auto;
      min-height: 0;
      overflow-x: hidden;
      overflow-y: visible;
    }
    #overview.view.active {
      overflow-x: hidden;
      overflow-y: visible;
      padding-right: 0;
    }
    .summary-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(min(180px, 100%), 1fr));
      gap: 10px;
      width: 100%;
      inline-size: 100%;
      max-width: 100%;
      max-inline-size: 100%;
      min-width: 0;
      min-inline-size: 0;
    }
    .overview-summary-grid {
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 14px;
    }
    .tile {
      min-height: 84px;
      padding: 10px 12px;
      border: 1px solid var(--border);
      border-radius: 8px;
      background: #f8fafc;
    }
    .tile.tile-dark {
      border-color: #0f766e;
      background: #0f766e;
      color: #f8fafc;
    }
    .tile.tile-dark .label,
    .tile.tile-dark .muted {
      color: #d9f99d;
    }
    .tile.tile-light {
      border-color: #bdd6e6;
      background: #f8fbff;
      color: #111827;
    }
    .tile.tile-light .label {
      color: #0f766e;
    }
    .tile strong { display: block; margin-top: 6px; font-size: 1.08rem; }
    .tile .muted { margin: 7px 0 0; font-size: 0.78rem; }
    .overview-summary-grid .tile {
      min-height: 124px;
      padding: 16px;
    }
    .overview-summary-grid .tile strong {
      margin-top: 12px;
      font-size: 1.35rem;
      line-height: 1.2;
    }
    .overview-summary-grid .tile .muted {
      margin-top: 10px;
      font-size: 0.86rem;
      white-space: pre-line;
    }
    .overview-date-note {
      margin: 12px 0 0;
      color: #64748b;
      font-size: 0.86rem;
      font-style: italic;
      font-weight: 800;
      text-align: right;
    }
    .layout {
      display: grid;
      grid-template-columns: minmax(220px, 260px) minmax(0, 1fr);
      gap: 12px;
      width: 100%;
      inline-size: 100%;
      max-width: 100%;
      max-inline-size: 100%;
      height: auto;
      min-height: 0;
      min-width: 0;
      min-inline-size: 0;
      overflow-x: hidden;
      overflow-y: visible;
      align-items: start;
    }
    .filters {
      position: sticky;
      top: 10px;
      display: grid;
      align-content: start;
      gap: 12px;
      max-height: 90vh;
      max-width: 100%;
      max-inline-size: 100%;
      min-width: 0;
      min-inline-size: 0;
      overflow-x: hidden;
      overflow-y: auto;
      padding: 12px;
    }
    .filter { display: grid; gap: 6px; }
    .filter span { color: #334155; font-size: 0.8rem; font-weight: 900; }
    select {
      width: 100%;
      min-height: 34px;
      border: 1px solid #cbd5e1;
      border-radius: 7px;
      color: #111827;
      background: #fff;
      font-weight: 700;
    }
    .main {
      display: grid;
      gap: 12px;
      align-content: start;
      height: auto;
      max-height: none;
      width: 100%;
      inline-size: 100%;
      max-width: 100%;
      max-inline-size: 100%;
      min-width: 0;
      min-inline-size: 0;
      min-height: 0;
      overflow-x: hidden;
      overflow-y: visible;
      padding-right: 0;
    }
    .chart-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
      width: 100%;
      inline-size: 100%;
      max-width: 100%;
      max-inline-size: 100%;
      min-width: 0;
      min-inline-size: 0;
      overflow-x: hidden;
    }
    .chart-grid-three {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 12px;
      width: 100%;
      max-width: 100%;
      min-width: 0;
      overflow-x: hidden;
    }
    .kpi-stack {
      display: grid;
      grid-template-columns: minmax(0, 1fr);
      gap: 12px;
      min-width: 0;
    }
    .duration-grid {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 12px;
      min-width: 0;
    }
    .chart-card {
      width: 100%;
      inline-size: 100%;
      min-width: 0;
      min-inline-size: 0;
      max-width: 100%;
      max-inline-size: 100%;
      min-height: 420px;
      overflow-x: hidden;
      overflow-y: visible;
      padding: 10px;
    }
    .chart-card.full { grid-column: 1 / -1; }
    .chart-copy-toolbar {
      display: flex;
      justify-content: flex-end;
      align-items: center;
      gap: 10px;
      min-height: 30px;
      margin-top: 8px;
    }
    .copy-chart-button {
      min-height: 28px;
      padding: 0 10px;
      border: 1px solid #0f766e;
      border-radius: 7px;
      background: #ffffff;
      color: #0f766e;
      font-size: 0.75rem;
      font-weight: 900;
      cursor: pointer;
    }
    .copy-chart-button:hover,
    .copy-chart-button:focus-visible {
      background: #ecfdf5;
      outline: none;
    }
    .copy-chart-button:disabled {
      cursor: wait;
      opacity: 0.7;
    }
    .copy-chart-status {
      color: #475569;
      font-size: 0.74rem;
      font-weight: 800;
      min-width: 92px;
      text-align: right;
    }
    .chart-frame {
      display: flex;
      flex-direction: column;
      justify-content: center;
      width: 100%;
      inline-size: 100%;
      max-width: 100%;
      max-inline-size: 100%;
      min-width: 0;
      min-inline-size: 0;
      min-height: 340px;
      margin-top: 8px;
      overflow-x: hidden;
      overflow-y: visible;
      border: 1px solid #cbd5e1;
      border-radius: 8px;
      background: #fff;
      padding: 8px;
    }
    .chart-stage {
      width: 100%;
      inline-size: 100%;
      max-width: 100%;
      max-inline-size: 100%;
      min-width: 0;
      min-inline-size: 0;
      min-height: 340px;
      overflow-x: hidden;
      overflow-y: visible;
    }
    .chart-stage.scroll-x {
      overflow-x: auto;
    }
    svg,
    .chart-svg {
      display: block;
      width: 100%;
      inline-size: 100%;
      max-width: 100%;
      max-inline-size: 100%;
      height: auto;
    }
    .pie-svg {
      max-height: 320px;
    }
    .chart-frame .legend { margin-top: 8px; }
    #applications .chart-card {
      min-height: 430px;
    }
    #applications .chart-stage {
      min-height: 360px;
    }
    #volumetrics .chart-card {
      min-height: 440px;
    }
    #volumetrics .chart-stage {
      min-height: 360px;
    }
    #volumetrics .summary-grid { grid-template-columns: repeat(5, minmax(0, 1fr)); }
    .table-frame {
      display: block;
      width: 100%;
      inline-size: 100%;
      max-width: 100%;
      max-inline-size: 100%;
      min-height: 300px;
      max-height: 360px;
      overflow-x: auto;
      overflow-y: auto;
      border: 1px solid var(--border);
      border-radius: 8px;
      background: #fff;
      -webkit-overflow-scrolling: touch;
    }
    table { width: 100%; border-collapse: collapse; min-width: 760px; font-size: 0.78rem; }
    .table-card {
      width: 100%;
      inline-size: 100%;
      max-width: 100%;
      max-inline-size: 100%;
      min-width: 0;
      min-inline-size: 0;
      min-height: 420px;
      overflow: hidden;
    }
    .applications-table {
      width: max-content;
      min-width: 2600px;
      max-width: none;
      border-collapse: collapse;
    }
    .validation-toolbar {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 10px;
      margin: 10px 0;
    }
    .validation-actions {
      display: inline-flex;
      flex-wrap: wrap;
      gap: 8px;
      margin: 8px 0;
    }
    .validation-actions button,
    .validation-toolbar button {
      min-height: 30px;
      padding: 0 10px;
      border: 1px solid var(--border);
      border-radius: 7px;
      background: #fff;
      color: #334155;
      cursor: pointer;
      font-weight: 900;
    }
    .validation-toolbar button.active {
      border-color: var(--teal);
      background: var(--teal);
      color: #fff;
    }
    .validation-table-frame {
      max-height: 560px;
    }
    .validation-table-card {
      width: 100%;
      max-width: 100%;
      min-width: 0;
      overflow: hidden;
      border: 1px solid var(--border);
      border-radius: 8px;
      background: #fff;
    }
    .validation-table-scroll {
      display: block;
      position: relative;
      width: 100%;
      max-width: 100%;
      min-width: 0;
      max-height: 560px;
      overflow-x: scroll;
      overflow-y: scroll;
      scrollbar-gutter: stable both-edges;
      overscroll-behavior-x: contain;
      overscroll-behavior-y: contain;
      -webkit-overflow-scrolling: touch;
      touch-action: pan-x pan-y;
    }
    .validation-table-scroll:focus {
      outline: 3px solid rgba(15, 118, 110, 0.24);
      outline-offset: -3px;
    }
    .validation-table-scroll::-webkit-scrollbar {
      width: 14px;
      height: 14px;
    }
    .validation-table-scroll::-webkit-scrollbar-thumb {
      border: 3px solid #fff;
      border-radius: 999px;
      background: #94a3b8;
    }
    .validation-table-scroll::-webkit-scrollbar-track {
      background: #f1f5f9;
    }
    .offline-mapping-scroll {
      max-height: 560px;
    }
    .offline-validation-scroll {
      display: block;
      width: 100%;
      inline-size: min(100%, calc(100vw - 320px));
      max-width: 100%;
      max-inline-size: min(100%, calc(100vw - 320px));
      min-width: 0;
      min-inline-size: 0;
      min-height: 300px;
      max-height: 560px;
      overflow-x: scroll;
      overflow-y: scroll;
      scrollbar-gutter: stable both-edges;
      overscroll-behavior: contain;
      touch-action: pan-x pan-y;
      scrollbar-width: auto;
      scrollbar-color: #94a3b8 #f1f5f9;
    }
    .offline-validation-scroll::-webkit-scrollbar {
      width: 14px;
      height: 14px;
    }
    .offline-validation-scroll::-webkit-scrollbar-thumb {
      border: 3px solid #fff;
      border-radius: 999px;
      background: #94a3b8;
    }
    .offline-validation-scroll::-webkit-scrollbar-track {
      background: #f1f5f9;
    }
    .assignment-volumetrics-frame {
      display: block;
      width: 100%;
      inline-size: min(100%, calc(100vw - 320px));
      max-width: 100%;
      max-inline-size: min(100%, calc(100vw - 320px));
      min-width: 0;
      min-inline-size: 0;
      height: 560px;
      max-height: 62vh;
      overflow-x: scroll !important;
      overflow-y: scroll !important;
      scrollbar-gutter: stable both-edges;
      overscroll-behavior: contain;
      touch-action: pan-x pan-y;
    }
    .assignment-volumetrics-scroll {
      width: 100%;
      max-width: 100%;
      min-width: 0;
      max-height: 560px;
    }
    .validation-table th,
    .validation-table td {
      border-right: 1px solid var(--border);
      border-bottom: 1px solid var(--border);
      vertical-align: top;
    }
    .assignment-volumetrics-table {
      width: max-content;
      min-width: 2920px;
      max-width: none;
      table-layout: auto;
      border-collapse: separate;
      border-spacing: 0;
    }
    .assignment-volumetrics-table th,
    .assignment-volumetrics-table td {
      padding: 7px 9px;
    }
    .assignment-volumetrics-table thead th {
      position: sticky;
      top: 0;
      z-index: 2;
    }
    .assignment-volumetrics-table thead tr:first-child th {
      top: 0;
    }
    .assignment-volumetrics-table thead tr:nth-child(2) th {
      top: 34px;
    }
    .assignment-volumetrics-table .numeric-cell,
    .assignment-volumetrics-table .month-subheader,
    .assignment-volumetrics-table .month-group-header {
      min-width: 92px;
      white-space: nowrap;
    }
    .assignment-volumetrics-table .assignment-group-column {
      position: sticky;
      left: 0;
      z-index: 3;
      min-width: 250px;
      max-width: 340px;
      white-space: normal;
      overflow-wrap: anywhere;
      border-right: 2px solid #94a3b8;
      background: #fff;
      text-align: left;
    }
    .assignment-volumetrics-table thead .assignment-group-column {
      z-index: 5;
      background: var(--panel);
    }
    .assignment-volumetrics-table .reference-column {
      min-width: 140px;
      max-width: 220px;
      white-space: normal;
      overflow-wrap: anywhere;
      background: #fff;
      text-align: left;
    }
    .assignment-volumetrics-table thead .reference-column {
      background: var(--panel);
    }
    .validation-subsection {
      margin-top: 16px;
      padding-top: 14px;
      border-top: 1px solid var(--border);
    }
    .month-group-a { background: #f8fafc; }
    .month-group-b { background: #eef6ff; }
    .metric-created { background-color: #f3f8f6; }
    .metric-resolved { background-color: #f4f7fb; }
    .metric-cancelled { background-color: #fff7ed; }
    .month-boundary-left { border-left: 2px solid #94a3b8 !important; }
    .month-boundary-right { border-right: 2px solid #94a3b8 !important; }
    .assignment-volumetrics-table .total-cell {
      background-color: #f1f5f9;
      font-weight: 900;
    }
    .assignment-volumetrics-table .assignment-volumetrics-total-row th,
    .assignment-volumetrics-table .assignment-volumetrics-total-row td {
      position: sticky;
      top: 68px;
      z-index: 4;
      background-color: #f1f5f9;
    }
    .assignment-volumetrics-table .assignment-volumetrics-total-row .assignment-group-column {
      z-index: 6;
    }
    .assignment-volumetrics-table .assignment-volumetrics-total-row .reference-column {
      background-color: #f1f5f9;
    }
    .lifecycle-detail-table {
      min-width: 2500px;
    }
    .applications-pivot-table {
      width: 100%;
      min-width: 760px;
      border-collapse: collapse;
      font-size: 0.82rem;
    }
    .lifecycle-matrix-table {
      min-width: 700px;
    }
    .lifecycle-matrix-note {
      margin: 10px 12px 12px;
      color: #0f172a;
      font-size: 0.86rem;
      font-weight: 900;
      text-align: right;
    }
    .applications-pivot-table .numeric-cell {
      text-align: right;
      font-variant-numeric: tabular-nums;
    }
    .applications-pivot-table .total-cell {
      color: #0f172a;
      background: #f8fafc;
      font-weight: 900;
    }
    .applications-pivot-table th:last-child,
    .applications-pivot-table td:last-child {
      position: sticky;
      right: 0;
      z-index: 1;
      box-shadow: -1px 0 0 #e2e8f0;
    }
    .applications-pivot-table thead th:last-child {
      z-index: 3;
    }
    .applications-pivot-table .pivot-total-row th,
    .applications-pivot-table .pivot-total-row td {
      background: #eef6ff;
      font-weight: 900;
    }
    .applications-pivot-table .grand-total-cell {
      color: #0f172a;
      background: #eef6ff;
      font-weight: 900;
    }
    .applications-pivot-table .grand-total-label {
      display: block;
      color: #475569;
      font-size: 0.68rem;
      line-height: 1.1;
      text-transform: uppercase;
    }
    .applications-pivot-table .grand-total-cell strong {
      display: block;
      color: #0f172a;
      font-size: 0.98rem;
      line-height: 1.2;
    }
    th, td {
      padding: 8px 10px;
      border-bottom: 1px solid #e2e8f0;
      text-align: left;
      white-space: nowrap;
    }
    th { position: sticky; top: 0; background: #f8fafc; z-index: 1; }
    .pattern-buttons { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 10px; }
    .application-subtabs {
      width: fit-content;
      max-width: 100%;
      padding: 4px;
      border: 1px solid #cbd5e1;
      border-radius: 8px;
      background: #fff;
    }
    .segmented-control { display: inline-flex; flex-wrap: wrap; gap: 6px; padding: 4px; border: 1px solid #cbd5e1; border-radius: 8px; background: #f8fafc; }
    .segmented-control button {
      min-height: 32px;
      padding: 0 14px;
      border: 0;
      border-radius: 6px;
      background: transparent;
      cursor: pointer;
      font-weight: 900;
      color: #475569;
    }
    .segmented-control button.active { color: #fff; background: var(--teal); }
    .pattern-buttons button {
      min-height: 34px;
      padding: 0 14px;
      border: 1px solid #cbd5e1;
      border-radius: 7px;
      background: #fff;
      cursor: pointer;
      font-weight: 900;
    }
    .pattern-buttons button.active { border-color: var(--teal); color: #fff; background: var(--teal); }
    .subtabs {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 10px;
    }
    .subtabs button {
      min-height: 34px;
      padding: 0 12px;
      border: 1px solid #cbd5e1;
      border-radius: 8px;
      background: #fff;
      color: #334155;
      cursor: pointer;
      font-weight: 900;
    }
    .subtabs button.active { border-color: var(--teal); color: #fff; background: var(--teal); }
    .chart-title-row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
    }
    .legend { display: flex; flex-wrap: wrap; justify-content: center; gap: 12px; font-size: 0.78rem; }
    #applications .legend {
      gap: 14px;
      font-size: 0.82rem;
    }
    .legend span { display: inline-flex; align-items: center; gap: 5px; font-weight: 800; }
    .swatch { width: 12px; height: 12px; border-radius: 2px; display: inline-block; }
    #applications .swatch { width: 12px; height: 12px; }
    .offline-actions {
      display: flex;
      justify-content: flex-end;
      margin: 0 0 10px;
    }
    .commentary-box {
      margin-top: 12px;
      padding-top: 12px;
      border-top: 1px solid #dbe3ef;
    }
    .commentary-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
    }
    .commentary-icon-actions {
      display: inline-flex;
      align-items: center;
      gap: 8px;
    }
    .commentary-icon-button {
      display: inline-grid;
      place-items: center;
      width: 32px;
      height: 32px;
      min-height: 32px;
      padding: 0;
      border: 1px solid #cbd5e1;
      border-radius: 8px;
      color: #1e293b;
      background: #fff;
      cursor: pointer;
      font-size: 0.95rem;
      font-weight: 900;
      line-height: 1;
    }
    .commentary-icon-button.primary {
      border-color: var(--teal);
      color: #fff;
      background: var(--teal);
    }
    .commentary-box:not(.editing) .commentary-save-button,
    .commentary-box:not(.editing) .commentary-clear-button {
      display: none;
    }
    .commentary-box.editing .commentary-edit-button {
      display: none;
    }
    .commentary-preview {
      margin-top: 8px;
      padding: 10px 12px;
      border: 1px solid #dbeafe;
      border-radius: 8px;
      background: #f8fafc;
      color: #1e293b;
      line-height: 1.45;
    }
    .commentary-preview p,
    .commentary-editor p { margin: 0 0 8px; }
    .commentary-preview ul,
    .commentary-preview ol,
    .commentary-editor ul,
    .commentary-editor ol { margin: 6px 0 6px 22px; }
    .commentary-editor-panel {
      display: none;
      gap: 10px;
      margin-top: 10px;
    }
    .commentary-box.editing .commentary-editor-panel { display: grid; }
    .commentary-box.editing .commentary-preview { display: none; }
    .commentary-toolbar {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
    }
    .commentary-toolbar button {
      min-height: 28px;
      padding: 4px 8px;
      font-size: 0.74rem;
      font-weight: 800;
    }
    .commentary-editor {
      min-height: 96px;
      padding: 10px 12px;
      border: 1px solid #cbd5e1;
      border-radius: 8px;
      background: #fff;
      color: #0f172a;
      line-height: 1.45;
      outline: none;
    }
    .commentary-editor:focus {
      border-color: #2563eb;
      box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.12);
    }
    .commentary-footer {
      display: flex;
      justify-content: flex-end;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
    }
    .commentary-status {
      font-size: 0.8rem;
      color: #475569;
    }
    .offline-dashboard,
    .dashboard-layout,
    .filter-pane,
    .main-content,
    .cards-grid,
    .chart-grid,
    .chart-grid-three,
    .chart-card,
    .chart-stage,
    .table-card,
    .table-scroll {
      min-width: 0;
      min-inline-size: 0;
      max-width: 100%;
      max-inline-size: 100%;
    }
    .sc-task-catalog-grid {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 12px;
      min-width: 0;
    }
    .sc-task-catalog-card {
      display: grid;
      align-content: start;
      gap: 8px;
      min-width: 0;
      padding: 12px;
      border: 1px solid #dbe3ef;
      border-radius: 8px;
      background: #fff;
    }
    .sc-task-catalog-card h4 {
      margin: 0;
      color: #111827;
      font-size: 0.95rem;
    }
    @media (max-width: 1100px) {
      .chart-grid { grid-template-columns: 1fr; }
      .chart-grid-three { grid-template-columns: 1fr; }
      .sc-task-catalog-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .duration-grid { grid-template-columns: 1fr; }
      #volumetrics .summary-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .offline-validation-scroll {
        inline-size: 100%;
        max-inline-size: 100%;
      }
      .assignment-volumetrics-frame {
        inline-size: 100%;
        max-inline-size: 100%;
      }
    }
    @media (max-width: 980px) {
      .topbar, .layout { grid-template-columns: 1fr; display: grid; }
      .topbar { max-height: none; min-height: 0; }
      .dashboard-title, #export-meta { text-align: left; }
      .summary-grid, .chart-grid, .chart-grid-three, .sc-task-catalog-grid, .duration-grid, #volumetrics .summary-grid { grid-template-columns: 1fr; }
      .overview-summary-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .filters { position: static; max-height: none; }
      .main { overflow-y: visible; }
      .shell {
        height: auto;
        min-height: 100vh;
        overflow-y: visible;
      }
      body { overflow-y: auto; }
    }
    @media (max-width: 640px) {
      .overview-summary-grid { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <script type="application/json" id="dashboard-data">__DASHBOARD_DATA_JSON__</script>
  <main class="shell offline-dashboard">
    <section class="topbar">
      <div class="customer-logo" id="customer-logo"></div>
      <h1 class="dashboard-title" id="page-title"></h1>
      <div class="muted" id="export-meta"></div>
    </section>
    <nav class="tabs" aria-label="Dashboard tabs">
      <button class="tab active" data-tab="overview" type="button">Overview</button>
      <button class="tab" data-tab="applications" type="button">Applications</button>
      <button class="tab" data-tab="volumetrics" type="button">Volumetrics &amp; SLA</button>
    </nav>
    <div class="offline-actions">
      <button class="secondary-button" id="download-edited-dashboard" type="button">
        Download Updated Offline Dashboard
      </button>
    </div>
    <section class="view active" id="overview"></section>
    <section class="view" id="applications"></section>
    <section class="view" id="volumetrics"></section>
  </main>
  <script>
    function parseDashboardPayload() {
      const payloadElement = document.getElementById("dashboard-data");
      if (!payloadElement) {
        console.error("Offline dashboard payload script tag is missing.");
        return null;
      }
      try {
        return JSON.parse(payloadElement.textContent || "{}");
      } catch (error) {
        console.error("Offline dashboard payload could not be parsed.", error);
        return null;
      }
    }
    const DASHBOARD = parseDashboardPayload();
    const COLORS = {
      teal: "#0f766e",
      blue: "#2563eb",
      red: "#dc2626",
      orange: "#d97706",
      purple: "#7c3aed",
      green: "#16a34a",
      slate: "#64748b"
    };
    const state = {
      tab: "overview",
      appSubTab: "overview",
      appMappingSource: "application_inventory",
      appMappingScope: "in_scope",
      appMappingTrack: "all",
      appFunctional: "all",
      appScope: "all",
      appSap: "all",
      appBusinessCritical: "all",
      lifecyclePlan: "Invest",
      volScope: "in_scope",
      volTicketType: "all",
      volFunctional: "all",
      volSap: "all",
      volBusinessCritical: "all",
      volAssignmentTrack: "all",
      pattern: "day_of_month",
      volSubTab: "overall_volume_trends",
      hourlyDayType: "weekdays",
      priorityView: "graph",
      slaMode: "sla",
      topVolumeN: "10",
      topBatchN: "10",
      topActiveUsersN: "10",
      ticketsPerUserN: "10"
    };
    function fmt(value, digits = 0) {
      if (value === null || value === undefined || Number.isNaN(Number(value))) return "N/A";
      return Number(value).toLocaleString(undefined, { maximumFractionDigits: digits });
    }
    function pct(met, total) {
      return total > 0 ? `${((met / total) * 100).toFixed(1)}%` : "N/A";
    }
    function dateText(value) {
      if (!value) return "Not available";
      const date = new Date(value);
      if (Number.isNaN(date.getTime())) return "Not available";
      return date.toLocaleDateString("en-GB", {
        day: "2-digit",
        month: "short",
        year: "numeric"
      }).replace(/ /g, "-");
    }
    function dateTimeText(value) {
      if (!value) return "Not available";
      const date = new Date(value);
      if (Number.isNaN(date.getTime())) return "Not available";
      const time = date.toLocaleTimeString("en-GB", {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
        timeZoneName: "short"
      });
      return `${dateText(value)} ${time}`;
    }
    function rounded(value) {
      return Math.ceil(Number(value || 0)).toLocaleString();
    }
    function esc(value) {
      return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#39;");
    }
    const COMMENTARY_STORAGE_KEY = `ams-dashboard-commentary:${DASHBOARD?.metadata?.project_id || "project"}:${DASHBOARD?.metadata?.exported_at || "export"}`;
    function normalizeCommentaryValue(value, fallback = "") {
      const text = String(value ?? "").trim();
      return text || fallback;
    }
    function normalizeCommentaryKeyPart(value, fallback = "") {
      return normalizeCommentaryValue(value, fallback).toLowerCase();
    }
    function normalizeChartKey(value) {
      return normalizeCommentaryKeyPart(value, "general")
        .replace(/[^a-z0-9]+/g, "_")
        .replace(/^_+|_+$/g, "");
    }
    function commentaryKey(context) {
      return [
        DASHBOARD?.metadata?.project_id || "",
        normalizeCommentaryKeyPart(context.dashboard_area),
        normalizeCommentaryKeyPart(context.tab_name),
        normalizeCommentaryKeyPart(context.sub_tab_name),
        normalizeCommentaryKeyPart(context.section_key),
        normalizeCommentaryKeyPart(context.chart_key),
        normalizeCommentaryKeyPart(context.scope_filter, "all"),
        normalizeCommentaryKeyPart(context.ticket_type_filter, "all"),
        normalizeCommentaryValue(context.functional_track_ams_owner, "all")
      ].join("|");
    }
    function loadCommentaryEdits() {
      try {
        return JSON.parse(localStorage.getItem(COMMENTARY_STORAGE_KEY) || "{}");
      } catch (error) {
        console.warn("Offline commentary edits could not be loaded.", error);
        return {};
      }
    }
    let commentaryEdits = loadCommentaryEdits();
    function baseCommentaryMap() {
      const rows = new Map();
      (DASHBOARD.commentaries || []).forEach((row) => {
        rows.set(commentaryKey(row), row);
      });
      Object.values(commentaryEdits || {}).forEach((row) => {
        rows.set(commentaryKey(row), row);
      });
      return rows;
    }
    function getCommentary(context) {
      return baseCommentaryMap().get(commentaryKey(context)) || null;
    }
    function saveLocalCommentary(context, htmlValue, textValue) {
      const record = {
        project_id: DASHBOARD.metadata.project_id,
        dashboard_area: normalizeCommentaryKeyPart(context.dashboard_area),
        tab_name: normalizeCommentaryKeyPart(context.tab_name),
        sub_tab_name: normalizeCommentaryKeyPart(context.sub_tab_name) || null,
        section_key: normalizeCommentaryKeyPart(context.section_key),
        chart_key: normalizeCommentaryKeyPart(context.chart_key) || null,
        scope_filter: normalizeCommentaryKeyPart(context.scope_filter, "all"),
        ticket_type_filter: normalizeCommentaryKeyPart(context.ticket_type_filter, "all"),
        functional_track_ams_owner: normalizeCommentaryValue(context.functional_track_ams_owner, "all"),
        commentary_html: htmlValue || null,
        commentary_text: textValue || null
      };
      commentaryEdits[commentaryKey(record)] = record;
      localStorage.setItem(COMMENTARY_STORAGE_KEY, JSON.stringify(commentaryEdits));
      return record;
    }
    function sanitizeOfflineCommentary(htmlValue) {
      const template = document.createElement("template");
      template.innerHTML = htmlValue || "";
      const allowed = new Set(["P", "BR", "STRONG", "B", "EM", "I", "U", "UL", "OL", "LI", "SPAN"]);
      const drop = new Set(["SCRIPT", "STYLE", "IFRAME", "OBJECT", "EMBED"]);
      function clean(node) {
        [...node.childNodes].forEach((child) => {
          if (child.nodeType === Node.ELEMENT_NODE) {
            const element = child;
            if (drop.has(element.tagName)) {
              element.remove();
              return;
            }
            if (!allowed.has(element.tagName)) {
              const fragment = document.createDocumentFragment();
              while (element.firstChild) fragment.appendChild(element.firstChild);
              element.replaceWith(fragment);
              clean(node);
              return;
            }
            [...element.attributes].forEach((attribute) => element.removeAttribute(attribute.name));
            clean(element);
          }
        });
      }
      clean(template.content);
      return template.innerHTML.trim();
    }
    function commentaryContextAttributes(context) {
      return Object.entries(context)
        .map(([key, value]) => `data-${key.replaceAll("_", "-")}="${esc(value || "")}"`)
        .join(" ");
    }
    function commentaryMarkup(context) {
      const row = getCommentary(context);
      const htmlValue = row?.commentary_html || "";
      const hasCommentary = Boolean(String(htmlValue).replace(/<[^>]*>/g, "").trim());
      return `<section class="commentary-box" ${commentaryContextAttributes(context)}>
        <div class="commentary-header">
          <div><p class="label">Commentary / Inferences</p></div>
          <div class="commentary-icon-actions">
            <button class="commentary-icon-button commentary-clear-button" type="button" aria-label="Clear commentary">x</button>
            <button class="commentary-icon-button primary commentary-save-button" type="button" aria-label="Save commentary">✓</button>
            <button class="commentary-icon-button commentary-edit-button" type="button" aria-label="Edit commentary">✎</button>
          </div>
        </div>
        <div class="commentary-preview">${hasCommentary ? htmlValue : `<p class="muted">No commentary added yet.</p>`}</div>
        <div class="commentary-editor-panel">
          <div class="commentary-toolbar">
            <button type="button" data-command="bold">B</button>
            <button type="button" data-command="italic">I</button>
            <button type="button" data-command="underline">U</button>
            <button type="button" data-command="insertUnorderedList">Bullets</button>
            <button type="button" data-command="insertOrderedList">Numbered</button>
            <button type="button" data-command="removeFormat">Remove format</button>
          </div>
          <div class="commentary-editor" contenteditable="true" role="textbox">${htmlValue}</div>
          <div class="commentary-footer">
            <span class="commentary-status">Offline edits are saved in this browser until you download an updated HTML file.</span>
          </div>
        </div>
      </section>`;
    }
    function contextFromCommentaryElement(node) {
      return {
        dashboard_area: node.dataset.dashboardArea || "dashboard",
        tab_name: node.dataset.tabName || "overview",
        sub_tab_name: node.dataset.subTabName || "",
        section_key: node.dataset.sectionKey || "section",
        chart_key: node.dataset.chartKey || "",
        scope_filter: node.dataset.scopeFilter || "all",
        ticket_type_filter: node.dataset.ticketTypeFilter || "all",
        functional_track_ams_owner: node.dataset.functionalTrackAmsOwner || "all"
      };
    }
    function installCommentaryEditors(root) {
      if (!root) return;
      root.querySelectorAll(".commentary-box").forEach((box) => {
        const editButton = box.querySelector(".commentary-edit-button");
        const clearButton = box.querySelector(".commentary-clear-button");
        const saveButton = box.querySelector(".commentary-save-button");
        const editor = box.querySelector(".commentary-editor");
        const preview = box.querySelector(".commentary-preview");
        const status = box.querySelector(".commentary-status");
        function saveBox() {
          const sanitized = sanitizeOfflineCommentary(editor?.innerHTML || "");
          const text = (editor?.innerText || "").trim();
          const context = contextFromCommentaryElement(box);
          saveLocalCommentary(context, sanitized, text);
          if (editor) editor.innerHTML = sanitized;
          if (preview) preview.innerHTML = sanitized || `<p class="muted">No commentary added yet.</p>`;
          if (status) status.textContent = "Saved locally.";
          box.classList.remove("editing");
          return true;
        }
        editButton?.addEventListener("click", () => {
          if (window.activeOfflineCommentaryBox && window.activeOfflineCommentaryBox !== box) {
            window.activeOfflineCommentaryBox.__saveCommentary?.();
          }
          window.activeOfflineCommentaryBox = box;
          box.__saveCommentary = saveBox;
          box.classList.add("editing");
          editor?.focus();
        });
        clearButton?.addEventListener("click", () => {
          if (editor) editor.innerHTML = "";
          saveBox();
          if (window.activeOfflineCommentaryBox === box) window.activeOfflineCommentaryBox = null;
        });
        box.querySelectorAll("[data-command]").forEach((button) => {
          button.addEventListener("mousedown", (event) => event.preventDefault());
          button.addEventListener("click", () => {
            editor?.focus();
            document.execCommand(button.dataset.command, false);
          });
        });
        saveButton?.addEventListener("click", () => {
          saveBox();
          if (window.activeOfflineCommentaryBox === box) window.activeOfflineCommentaryBox = null;
        });
      });
    }
    function attachDefaultCommentaries(root, context) {
      if (!root) return;
      root.querySelectorAll(".chart-card, .table-card").forEach((card) => {
        if (card.querySelector(".commentary-box")) return;
        if (card.dataset.commentarySkip === "true") return;
        const title = card.querySelector("h3")?.textContent || card.getAttribute("aria-label") || "section";
        const chartKey = card.dataset.commentaryKey || normalizeChartKey(title);
        const sectionKey = card.dataset.commentarySection || context.section_key;
        card.insertAdjacentHTML(
          "beforeend",
          commentaryMarkup({
            ...context,
            section_key: sectionKey,
            chart_key: chartKey
          })
        );
      });
      installCommentaryEditors(root);
    }
    function currentVolumetricsCommentaryContext() {
      return {
        dashboard_area: "volumetrics",
        tab_name: "volumetrics_sla",
        sub_tab_name: state.volSubTab,
        section_key: state.volSubTab,
        scope_filter: state.volScope,
        ticket_type_filter: state.volTicketType,
        functional_track_ams_owner: state.volFunctional
      };
    }
    function allMergedCommentaries() {
      return [...baseCommentaryMap().values()];
    }
    function safeJsonForScript(payload) {
      return JSON.stringify(payload).replace(/<\//g, "<\\/");
    }
    function editedDashboardFilename() {
      const now = new Date();
      const stamp = `${now.getFullYear()}${String(now.getMonth() + 1).padStart(2, "0")}${String(now.getDate()).padStart(2, "0")}_${String(now.getHours()).padStart(2, "0")}${String(now.getMinutes()).padStart(2, "0")}`;
      return `AMS_Apps_Volumetrics_Dashboard_Edited_${stamp}.html`;
    }
    function downloadUpdatedOfflineDashboard() {
      const updatedPayload = JSON.parse(JSON.stringify(DASHBOARD));
      updatedPayload.commentaries = allMergedCommentaries();
      const clonedDocument = document.documentElement.cloneNode(true);
      const payloadElement = clonedDocument.querySelector("#dashboard-data");
      if (payloadElement) {
        payloadElement.textContent = safeJsonForScript(updatedPayload);
      }
      const blob = new Blob([`<!doctype html>\n${clonedDocument.outerHTML}`], { type: "text/html;charset=utf-8" });
      const link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.download = editedDashboardFilename();
      document.body.appendChild(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(link.href), 500);
    }
    function renderSectionError(sectionId, title, error) {
      const node = document.getElementById(sectionId);
      if (!node) return;
      const message = error instanceof Error ? error.message : String(error || "Unknown error");
      console.error(`Offline dashboard render failed for ${title}.`, error);
      node.innerHTML = `<section class="panel" style="padding:18px"><p class="label">${esc(title)}</p><h3>Unable to render this dashboard section.</h3><p class="muted">${esc(message)}</p></section>`;
    }
    function safeRenderSection(sectionId, title, renderFn) {
      try {
        renderFn();
      } catch (error) {
        renderSectionError(sectionId, title, error);
      }
    }
    function renderFatalDashboardError(message) {
      ["overview", "applications", "volumetrics"].forEach((sectionId) => {
        const node = document.getElementById(sectionId);
        if (!node) return;
        node.innerHTML = `<section class="panel" style="padding:18px"><p class="label">Dashboard Error</p><h3>${esc(message)}</h3><p class="muted">Open the browser console for details, then download a fresh dashboard export.</p></section>`;
      });
    }
    function tile(label, value, helper = "", index = null, columns = null) {
      let tone = "";
      if (index !== null) {
        const columnCount = columns || 2;
        const row = Math.floor(index / columnCount);
        const column = index % columnCount;
        tone = (row + column) % 2 === 0 ? "tile-dark" : "tile-light";
      }
      return `<div class="tile ${tone}"><p class="label">${esc(label)}</p><strong>${esc(value)}</strong><p class="muted">${esc(helper)}</p></div>`;
    }
    function option(value, label, selected) {
      return `<option value="${esc(value)}" ${selected === value ? "selected" : ""}>${esc(label)}</option>`;
    }
    function renderSelect(id, label, values, selected) {
      return `<label class="filter"><span>${label}</span><select id="${id}">${values
        .map((item) => option(item.value, item.label, selected))
        .join("")}</select></label>`;
    }
    function uniqueSorted(rows, field) {
      return [...new Set(rows.map((row) => row[field]).filter(Boolean))]
        .sort((left, right) => String(left).localeCompare(String(right)));
    }
    function barChart(data, series, options = {}) {
      const width = Math.max(640, Math.min(options.width || 960, 1120));
      const isApplicationChart = Boolean(options.applicationChart);
      const isDurationBucketChart = Boolean(options.durationBucketChart);
      const height = options.height || (isApplicationChart ? 380 : isDurationBucketChart ? 340 : 360);
      const margin = isApplicationChart
        ? { top: 46, right: 28, bottom: 96, left: 42 }
        : isDurationBucketChart
          ? { top: 52, right: 30, bottom: 92, left: 40 }
        : { top: 42, right: 28, bottom: 86, left: 36 };
      const plotWidth = width - margin.left - margin.right;
      const plotHeight = height - margin.top - margin.bottom;
      const maxValue = Math.max(1, ...data.flatMap((row) => series.map((item) => Number(row[item.key] || 0))));
      const categoryCount = Math.max(1, data.length);
      const activePlotWidth = isApplicationChart && categoryCount <= 5
        ? Math.min(plotWidth, categoryCount * 140)
        : plotWidth;
      const plotOffsetX = isApplicationChart ? (plotWidth - activePlotWidth) / 2 : 0;
      const groupWidth = activePlotWidth / categoryCount;
      let barWidth;
      if (isApplicationChart && categoryCount <= 5) {
        const totalBarWidth = Math.max(34, Math.min(64, groupWidth * 0.38));
        barWidth = Math.max(22, totalBarWidth / Math.max(1, series.length));
      } else if (isApplicationChart) {
        const totalBarWidth = Math.max(24, Math.min(52, groupWidth * 0.36));
        barWidth = Math.max(22, totalBarWidth / Math.max(1, series.length));
      } else if (isDurationBucketChart) {
        barWidth = Math.max(28, Math.min(58, (groupWidth - 16) / series.length));
      } else {
        barWidth = Math.max(5, Math.min(18, (groupWidth - 8) / series.length));
      }
      const dataLabelFontSize = isApplicationChart ? 14 : isDurationBucketChart ? 14 : 10;
      const axisLabelFontSize = isApplicationChart ? 13 : isDurationBucketChart ? 13 : 10;
      const labelFontWeight = isApplicationChart || isDurationBucketChart ? 800 : 700;
      const bars = [];
      data.forEach((row, index) => {
        series.forEach((item, seriesIndex) => {
          const value = Number(row[item.key] || 0);
          const barHeight = (value / maxValue) * plotHeight;
          const x = margin.left + plotOffsetX + index * groupWidth + (groupWidth - barWidth * series.length) / 2 + seriesIndex * barWidth;
          const y = margin.top + plotHeight - barHeight;
          bars.push(`<rect x="${x}" y="${y}" width="${barWidth}" height="${barHeight}" fill="${item.color}" rx="3"></rect>`);
          if (value > 0) {
            const labelY = Math.max(margin.top + dataLabelFontSize, y - 7);
            bars.push(`<text x="${x + barWidth / 2}" y="${labelY}" text-anchor="middle" font-size="${dataLabelFontSize}" font-weight="${labelFontWeight}" fill="#334155">${options.roundLabels ? rounded(value) : fmt(value)}</text>`);
          }
        });
      });
      const labels = data.map((row, index) => {
        const x = margin.left + plotOffsetX + index * groupWidth + groupWidth / 2;
        return `<text x="${x}" y="${height - 42}" text-anchor="end" transform="rotate(-38 ${x} ${height - 42})" font-size="${axisLabelFontSize}" font-weight="${labelFontWeight}" fill="#334155">${esc(row.label)}</text>`;
      });
      return `<svg class="chart-svg" viewBox="0 0 ${width} ${height}" preserveAspectRatio="xMidYMid meet" role="img" aria-label="${options.title || "Bar chart"}">
        <line x1="${margin.left}" y1="${margin.top + plotHeight}" x2="${width - margin.right}" y2="${margin.top + plotHeight}" stroke="#64748b"></line>
        ${bars.join("")}${labels.join("")}
      </svg>${legend(series)}`;
    }
    function horizontalBarChart(data, options = {}) {
      if (!data.length) return `<p class="muted" style="padding:12px">${esc(options.emptyMessage || "No chart data available.")}</p>`;
      const width = Math.max(760, Math.min(options.width || 1040, 1120));
      const height = options.height || Math.max(420, data.length * 34 + 110);
      const margin = { top: 32, right: options.right || 132, bottom: 42, left: options.left || 280 };
      const plotWidth = width - margin.left - margin.right;
      const plotHeight = height - margin.top - margin.bottom;
      const valueKey = options.valueKey || "value";
      const maxValue = Math.max(1, ...data.map((row) => Number(row[valueKey] || 0)));
      const bandHeight = plotHeight / Math.max(1, data.length);
      const barHeight = Math.max(14, Math.min(28, bandHeight * 0.58));
      const bars = data.map((row, index) => {
        const value = Number(row[valueKey] || 0);
        const barWidth = (value / maxValue) * plotWidth;
        const y = margin.top + index * bandHeight + (bandHeight - barHeight) / 2;
        const labelY = y + barHeight / 2 + 4;
        const display = row.displayLabel || fmt(value, options.digits || 0);
        return `
          <text x="${margin.left - 12}" y="${labelY}" text-anchor="end" font-size="12" font-weight="800" fill="#334155"><title>${esc(row.label)}</title>${esc(truncateLabel(row.label, 36))}</text>
          <rect x="${margin.left}" y="${y}" width="${barWidth}" height="${barHeight}" rx="5" fill="${options.color || COLORS.teal}"></rect>
          <text x="${Math.min(width - margin.right + 8, margin.left + barWidth + 8)}" y="${labelY}" font-size="12" font-weight="900" fill="#334155">${esc(display)}</text>
        `;
      });
      return `<svg class="chart-svg" viewBox="0 0 ${width} ${height}" preserveAspectRatio="xMidYMid meet" role="img" aria-label="${esc(options.title || "Horizontal bar chart")}">
        <line x1="${margin.left}" y1="${height - margin.bottom}" x2="${width - margin.right}" y2="${height - margin.bottom}" stroke="#64748b"></line>
        ${bars.join("")}
      </svg>${legend([{ name: options.legend || "Value", color: options.color || COLORS.teal }])}`;
    }
    function lineChart(data, key, averageKey) {
      const width = 1040;
      const height = 360;
      const margin = { top: 52, right: 36, bottom: 78, left: 36 };
      const plotWidth = width - margin.left - margin.right;
      const plotHeight = height - margin.top - margin.bottom;
      const values = data.map((row) => Number(row[key] || 0));
      const average = values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : 0;
      const maxValue = Math.max(1, average, ...values);
      const point = (row, index) => {
        const x = margin.left + (plotWidth * index) / Math.max(1, data.length - 1);
        const y = margin.top + plotHeight - (Number(row[key] || 0) / maxValue) * plotHeight;
        return [x, y];
      };
      const points = data.map(point);
      const path = points.map(([x, y], index) => `${index ? "L" : "M"}${x},${y}`).join(" ");
      const avgY = margin.top + plotHeight - (average / maxValue) * plotHeight;
      return `<svg class="chart-svg" viewBox="0 0 ${width} ${height}" preserveAspectRatio="xMidYMid meet" role="img" aria-label="Backlog chart">
        <line x1="${margin.left}" y1="${margin.top + plotHeight}" x2="${width - margin.right}" y2="${margin.top + plotHeight}" stroke="#64748b"></line>
        <line x1="${margin.left}" y1="${avgY}" x2="${width - margin.right}" y2="${avgY}" stroke="${COLORS.purple}" stroke-dasharray="6 5"></line>
        <text x="${width - margin.right - 8}" y="${avgY - 10}" text-anchor="end" fill="${COLORS.purple}" font-size="12" font-weight="900">Avg backlog: ${fmt(average)}</text>
        <path d="${path}" fill="none" stroke="${COLORS.orange}" stroke-width="3"></path>
        ${points.map(([x, y], index) => `<circle cx="${x}" cy="${y}" r="4" fill="#fff" stroke="${COLORS.orange}" stroke-width="2"></circle><text x="${x}" y="${y - 9}" text-anchor="middle" font-size="10" fill="#475569">${fmt(data[index][key])}</text>`).join("")}
        ${data.map((row, index) => {
          const x = margin.left + (plotWidth * index) / Math.max(1, data.length - 1);
          return `<text x="${x}" y="${height - 38}" text-anchor="end" transform="rotate(-35 ${x} ${height - 38})" font-size="10" font-weight="700" fill="#475569">${esc(row.label)}</text>`;
        }).join("")}
      </svg>${legend([{ name: "Backlog(Open)", color: COLORS.orange }, { name: "Average", color: COLORS.purple }])}`;
    }
    function lifecyclePlanLineChart(data, plan) {
      if (!data.some((row) => Number(row.count || 0) > 0)) {
        return `<p class="muted" style="padding:12px">No applications found for the selected lifecycle plan.</p>`;
      }
      const color = lifecyclePlanColor(plan);
      const width = 760;
      const height = 340;
      const margin = { top: 54, right: 52, bottom: 82, left: 54 };
      const plotWidth = width - margin.left - margin.right;
      const plotHeight = height - margin.top - margin.bottom;
      const edgePadding = 58;
      const activePlotWidth = Math.max(1, plotWidth - edgePadding * 2);
      const maxValue = Math.max(1, ...data.map((row) => Number(row.count || 0)));
      const point = (row, index) => {
        const x = margin.left + edgePadding + (activePlotWidth * index) / Math.max(1, data.length - 1);
        const y = margin.top + plotHeight - (Number(row.count || 0) / maxValue) * plotHeight;
        return [x, y];
      };
      const points = data.map(point);
      const path = points.map(([x, y], index) => `${index ? "L" : "M"}${x},${y}`).join(" ");
      const pointLabels = data.map((row, index) => {
        const [x, y] = points[index];
        return `<circle cx="${x}" cy="${y}" r="5" fill="#ffffff" stroke="${color}" stroke-width="3"></circle><text x="${x}" y="${Math.max(margin.top - 14, y - 12)}" text-anchor="middle" font-size="13" font-weight="900" fill="#334155">${fmt(row.count)}</text>`;
      }).join("");
      const xLabels = data.map((row, index) => {
        const [x] = points[index];
        return `<text x="${x}" y="${height - 38}" text-anchor="middle" font-size="12" font-weight="800" fill="#334155">${esc(row.label)}</text>`;
      }).join("");
      return `<svg class="chart-svg" viewBox="0 0 ${width} ${height}" preserveAspectRatio="xMidYMid meet" role="img" aria-label="${esc(lifecyclePlanTitle(plan))}">
        <line x1="${margin.left}" y1="${margin.top + plotHeight}" x2="${width - margin.right}" y2="${margin.top + plotHeight}" stroke="#64748b"></line>
        <path d="${path}" fill="none" stroke="${color}" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"></path>
        ${pointLabels}${xLabels}
      </svg>${legend([{ name: `${plan} applications`, color }])}`;
    }
    function pieChart(items) {
      const visibleItems = items.filter((item) => Number(item.count || 0) > 0);
      const total = visibleItems.reduce((sum, item) => sum + item.count, 0);
      if (!total) return `<p class="muted">No chart data available.</p>`;
      let startAngle = -90;
      const radius = 106;
      const cx = 260;
      const cy = 146;
      const colors = [COLORS.blue, COLORS.green, COLORS.orange, COLORS.red, COLORS.purple, COLORS.slate];
      const labels = [];
      const slices = visibleItems.map((item, index) => {
        const angle = (item.count / total) * 360;
        const endAngle = startAngle + angle;
        const start = polar(cx, cy, radius, endAngle);
        const end = polar(cx, cy, radius, startAngle);
        const labelPoint = polar(cx, cy, radius + 34, startAngle + angle / 2);
        if (angle >= 10) {
          labels.push(`<text x="${labelPoint.x}" y="${labelPoint.y}" text-anchor="middle" dominant-baseline="middle" font-size="11" font-weight="900" fill="#0f172a">${fmt(item.count)} (${Math.round((item.count / total) * 100)}%)</text>`);
        }
        const large = angle > 180 ? 1 : 0;
        const path = `M ${cx} ${cy} L ${start.x} ${start.y} A ${radius} ${radius} 0 ${large} 0 ${end.x} ${end.y} Z`;
        startAngle = endAngle;
        return `<path d="${path}" fill="${colors[index % colors.length]}"><title>${esc(item.label)}: ${fmt(item.count)}</title></path>`;
      });
      return `<svg class="chart-svg pie-svg" viewBox="0 0 520 320" preserveAspectRatio="xMidYMid meet" role="img" aria-label="Pie chart">${slices.join("")}${labels.join("")}</svg>${legend(visibleItems.map((item, index) => ({ name: `${item.label} (${fmt(item.count)})`, color: colors[index % colors.length] })))}`;
    }
    function polar(cx, cy, radius, angle) {
      const radians = (angle * Math.PI) / 180;
      return { x: cx + radius * Math.cos(radians), y: cy + radius * Math.sin(radians) };
    }
    function legend(items) {
      return `<div class="legend">${items.map((item) => `<span><i class="swatch" style="background:${item.color}"></i>${esc(item.name)}</span>`).join("")}</div>`;
    }
    const SVG_COPY_STYLE_PROPERTIES = [
      "display",
      "visibility",
      "fill",
      "fill-opacity",
      "stroke",
      "stroke-width",
      "stroke-opacity",
      "stroke-dasharray",
      "stroke-linecap",
      "stroke-linejoin",
      "opacity",
      "font-family",
      "font-size",
      "font-weight",
      "text-anchor",
      "dominant-baseline",
      "paint-order"
    ];
    function inlineSvgComputedStyles(source, clone) {
      const sourceElements = [source, ...Array.from(source.querySelectorAll("*"))];
      const cloneElements = [clone, ...Array.from(clone.querySelectorAll("*"))];
      sourceElements.forEach((sourceElement, index) => {
        const cloneElement = cloneElements[index];
        if (!(cloneElement instanceof SVGElement)) return;
        const computed = getComputedStyle(sourceElement);
        SVG_COPY_STYLE_PROPERTIES.forEach((property) => {
          const value = computed.getPropertyValue(property);
          if (value) cloneElement.style.setProperty(property, value);
        });
      });
    }
    function chartSvgSize(svg) {
      const viewBoxText = svg.getAttribute("viewBox") || "";
      const viewBox = viewBoxText.trim().split(/\s+/).map(Number);
      const rect = svg.getBoundingClientRect();
      const attrWidth = Number(svg.getAttribute("width"));
      const attrHeight = Number(svg.getAttribute("height"));
      const viewBoxWidth = viewBox.length === 4 && Number.isFinite(viewBox[2]) ? viewBox[2] : 0;
      const viewBoxHeight = viewBox.length === 4 && Number.isFinite(viewBox[3]) ? viewBox[3] : 0;
      const width = Math.max(600, Math.ceil(rect.width || attrWidth || viewBoxWidth || 960));
      const height = Math.max(300, Math.ceil(rect.height || attrHeight || viewBoxHeight || 360));
      return {
        width,
        height,
        viewBoxText: viewBoxText || `0 0 ${Math.max(1, viewBoxWidth || attrWidth || width)} ${Math.max(1, viewBoxHeight || attrHeight || height)}`
      };
    }
    function serializedChartSvg(svg, width, height, viewBoxText) {
      const clone = svg.cloneNode(true);
      inlineSvgComputedStyles(svg, clone);
      clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");
      clone.setAttribute("x", "0");
      clone.setAttribute("y", "0");
      clone.setAttribute("width", String(width));
      clone.setAttribute("height", String(height));
      clone.setAttribute("viewBox", viewBoxText);
      const innerSvg = new XMLSerializer().serializeToString(clone);
      return `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}"><rect x="0" y="0" width="${width}" height="${height}" fill="#ffffff"></rect>${innerSvg}</svg>`;
    }
    function loadImageFromBlob(blob) {
      return new Promise((resolve, reject) => {
        const url = URL.createObjectURL(blob);
        const image = new Image();
        image.onload = () => {
          URL.revokeObjectURL(url);
          resolve(image);
        };
        image.onerror = () => {
          URL.revokeObjectURL(url);
          reject(new Error("Chart image could not be prepared."));
        };
        image.src = url;
      });
    }
    function canvasToPngBlob(canvas) {
      return new Promise((resolve, reject) => {
        canvas.toBlob((blob) => {
          if (blob) resolve(blob);
          else reject(new Error("Chart image could not be encoded."));
        }, "image/png");
      });
    }
    function chartLegendItems(frame) {
      return Array.from(frame.querySelectorAll(".legend span")).map((item) => {
        const swatch = item.querySelector(".swatch");
        return {
          name: item.textContent.trim(),
          color: swatch ? getComputedStyle(swatch).backgroundColor : COLORS.slate
        };
      }).filter((item) => item.name);
    }
    function wrapExportText(value, maxLength = 128) {
      const words = String(value || "").trim().split(/\s+/).filter(Boolean);
      const lines = [];
      let current = "";
      words.forEach((word) => {
        const next = current ? `${current} ${word}` : word;
        if (next.length > maxLength && current) {
          lines.push(current);
          current = word;
          return;
        }
        current = next;
      });
      if (current) lines.push(current);
      return lines.length ? lines : [String(value || "").trim()];
    }
    function chartExportText(card, frame) {
      const title = card?.querySelector("h3")?.textContent?.trim() || "chart";
      const subtitles = card
        ? Array.from(card.querySelectorAll(".muted, .muted-text"))
            .filter((element) => {
              const text = element.textContent?.trim();
              return text && !element.classList.contains("copy-chart-status") && !element.closest(".commentary-box") && !frame.contains(element);
            })
            .flatMap((element) => wrapExportText(element.textContent?.trim() || ""))
            .slice(0, 3)
        : [];
      return { title, subtitles };
    }
    async function chartFramePngBlob(frame, card) {
      const svg = frame.querySelector("svg");
      if (!svg) throw new Error("No chart image is available to copy.");
      const { width, height, viewBoxText } = chartSvgSize(svg);
      const svgMarkup = serializedChartSvg(svg, width, height, viewBoxText);
      const image = await loadImageFromBlob(new Blob([svgMarkup], { type: "image/svg+xml;charset=utf-8" }));
      const legendItems = chartLegendItems(frame);
      const exportText = chartExportText(card, frame);
      const headerHeight = Math.max(54, 42 + exportText.subtitles.length * 17);
      const scale = Math.max(1, Math.min(window.devicePixelRatio || 1, 2));
      const measureCanvas = document.createElement("canvas");
      const measureContext = measureCanvas.getContext("2d");
      if (!measureContext) throw new Error("Canvas copy is not available in this browser.");
      measureContext.font = "700 13px Arial, sans-serif";
      const legendRows = [];
      let currentRow = [];
      let currentWidth = 12;
      legendItems.forEach((item) => {
        const itemWidth = 24 + measureContext.measureText(item.name).width + 18;
        if (currentRow.length && currentWidth + itemWidth > width - 12) {
          legendRows.push(currentRow);
          currentRow = [];
          currentWidth = 12;
        }
        currentRow.push({ ...item, width: itemWidth });
        currentWidth += itemWidth;
      });
      if (currentRow.length) legendRows.push(currentRow);
      const legendHeight = legendRows.length ? 18 + legendRows.length * 24 : 0;
      const canvas = document.createElement("canvas");
      canvas.width = Math.ceil(width * scale);
      canvas.height = Math.ceil((headerHeight + height + legendHeight) * scale);
      const context = canvas.getContext("2d");
      if (!context) throw new Error("Canvas copy is not available in this browser.");
      context.scale(scale, scale);
      context.fillStyle = "#ffffff";
      context.fillRect(0, 0, width, headerHeight + height + legendHeight);
      context.fillStyle = "#111827";
      context.font = "700 17px Arial, sans-serif";
      context.textBaseline = "alphabetic";
      context.fillText(exportText.title, 14, 28);
      context.fillStyle = "#475569";
      context.font = "500 13px Arial, sans-serif";
      exportText.subtitles.forEach((line, index) => {
        context.fillText(line, 14, 48 + index * 17);
      });
      context.drawImage(image, 0, headerHeight, width, height);
      context.font = "700 13px Arial, sans-serif";
      context.textBaseline = "middle";
      legendRows.forEach((row, rowIndex) => {
        let x = 12;
        const y = headerHeight + height + 18 + rowIndex * 24;
        row.forEach((item) => {
          context.fillStyle = item.color;
          context.fillRect(x, y - 5, 10, 10);
          context.fillStyle = "#334155";
          context.fillText(item.name, x + 16, y);
          x += item.width;
        });
      });
      return { blob: await canvasToPngBlob(canvas), svgMarkup, title: exportText.title };
    }
    function safeChartFilename(title) {
      const cleaned = String(title || "chart").replace(/[^A-Za-z0-9]+/g, "_").replace(/^_+|_+$/g, "");
      return `${cleaned || "chart"}.png`;
    }
    function downloadOfflineChartPng(blob, title) {
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = safeChartFilename(title);
      document.body.append(link);
      link.click();
      link.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    }
    function setCopyStatus(button, message, isError = false) {
      const status = button.closest(".chart-copy-toolbar")?.querySelector(".copy-chart-status");
      if (!status) return;
      status.textContent = message;
      status.style.color = isError ? "#b91c1c" : "#0f766e";
      window.clearTimeout(status._resetTimer);
      status._resetTimer = window.setTimeout(() => {
        status.textContent = "";
        status.style.color = "#475569";
      }, 3200);
    }
    async function copyOfflineChart(button) {
      const card = button.closest(".chart-card");
      const frame = card?.querySelector(".chart-frame");
      if (!frame) {
        setCopyStatus(button, "No chart found", true);
        return;
      }
      button.disabled = true;
      let blob = null;
      let title = card?.querySelector("h3")?.textContent?.trim() || "chart";
      try {
        const result = await chartFramePngBlob(frame, card);
        blob = result.blob;
        title = result.title;
        if (!navigator.clipboard?.write || typeof ClipboardItem === "undefined") {
          throw new Error("Clipboard image copy is not supported in this browser.");
        }
        await navigator.clipboard.write([new ClipboardItem({ "image/png": blob })]);
        setCopyStatus(button, "Chart copied");
      } catch (error) {
        if (blob) {
          downloadOfflineChartPng(blob, title);
          const message = error instanceof Error ? error.message : "Copy blocked by browser.";
          setCopyStatus(button, `Copy blocked. PNG downloaded instead. ${message}`);
        } else {
          setCopyStatus(button, error instanceof Error ? error.message : "Copy failed", true);
        }
      } finally {
        button.disabled = false;
      }
    }
    function installChartCopyButtons(root = document) {
      // Future offline charts only need the standard .chart-card + .chart-frame SVG pattern.
      root.querySelectorAll(".chart-card").forEach((card) => {
        if (card.dataset.copyReady === "true") return;
        const frame = card.querySelector(".chart-frame");
        if (!frame || !frame.querySelector("svg")) return;
        const toolbar = document.createElement("div");
        toolbar.className = "chart-copy-toolbar";
        const status = document.createElement("span");
        status.className = "copy-chart-status";
        status.setAttribute("aria-live", "polite");
        const button = document.createElement("button");
        button.type = "button";
        button.className = "copy-chart-button";
        button.textContent = "Copy Chart";
        button.addEventListener("click", () => copyOfflineChart(button));
        toolbar.append(status, button);
        card.insertBefore(toolbar, frame);
        card.dataset.copyReady = "true";
      });
    }
    function countBy(rows, field) {
      const map = new Map();
      rows.forEach((row) => map.set(row[field] || "(blank)", (map.get(row[field] || "(blank)") || 0) + 1));
      return [...map.entries()]
        .map(([label, count]) => ({ label, count }))
        .sort((left, right) => right.count - left.count || left.label.localeCompare(right.label));
    }
    function aggregateByPeriod(rows) {
      const agreementMode = state.slaMode === "ola" ? "ola" : "sla";
      return DASHBOARD.volumetrics.periods.map((period) => {
        const matching = rows.filter((row) => row.period_key === period.period_key);
        return {
          label: period.period_label,
          created: sum(matching, "created_count"),
          resolved: sum(matching, "resolved_closed_count"),
          canceled: sum(matching, "canceled_closed_incomplete_count"),
          backlog: sum(matching, "backlog_open"),
          responseMet: sum(matching, `${agreementMode}_response_sla_met_count`),
          responseTotal: sum(matching, `${agreementMode}_response_sla_total_count`),
          resolutionMet: sum(matching, `${agreementMode}_resolution_sla_met_count`),
          resolutionTotal: sum(matching, `${agreementMode}_resolution_sla_total_count`)
        };
      });
    }
    function sum(rows, field) {
      return rows.reduce((total, row) => total + Number(row[field] || 0), 0);
    }
    function renderOverview() {
      const overview = DASHBOARD.overview;
      document.getElementById("overview").innerHTML = `<section class="panel" style="padding:14px">
        <p class="label">Overview</p><h2>Executive Summary</h2>
        <div class="summary-grid cards-grid overview-summary-grid" style="margin-top:12px">
          ${tile("Total Applications", fmt(overview.application_inventory.total_applications), `Very Critical: ${fmt(overview.application_inventory.very_critical_application_count)}\nCritical: ${fmt(overview.application_inventory.critical_application_count)}`, 0, 4)}
          ${tile("Functional Tracks / AMS Owners", fmt(overview.application_inventory.functional_track_count), `AMS Owners: ${fmt(overview.application_inventory.ams_owner_count)}`, 1, 4)}
          ${tile("Assignment Groups", fmt(overview.application_inventory.assignment_group_count), "", 2, 4)}
          ${tile("Supported Vendors", fmt(overview.application_inventory.supported_vendor_count), "", 3, 4)}
          ${tile("In-Scope Tickets", fmt(overview.tickets.total_in_scope_tickets), "", 4, 4)}
          ${tile("Incidents", fmt(overview.tickets.incident_count), `${pct(overview.tickets.incident_count, overview.tickets.total_in_scope_tickets)} of in-scope tickets`, 5, 4)}
          ${tile("SC Tasks", fmt(overview.tickets.sc_task_count), `${pct(overview.tickets.sc_task_count, overview.tickets.total_in_scope_tickets)} of in-scope tickets`, 6, 4)}
          ${tile("Apps Driving 80% Volume", fmt(overview.tickets.applications_80pct_monthly_volume_count), "Based on avg monthly ticket volume", 7, 4)}
        </div>
        <p class="overview-date-note">Tickets data range: ${dateText(overview.tickets.completion_date_min)} to ${dateText(overview.tickets.completion_date_max)}</p>
        ${commentaryMarkup({ dashboard_area: "dashboard", tab_name: "overview", sub_tab_name: "", section_key: "overview_summary", chart_key: "", scope_filter: "all", ticket_type_filter: "all", functional_track_ams_owner: "all" })}
      </section>`;
      installCommentaryEditors(document.getElementById("overview"));
    }
    function filteredApplications() {
      return DASHBOARD.applications.rows.filter((row) =>
        (state.appScope === "all" || row.scope_status === state.appScope) &&
        (state.appFunctional === "all" || row.functional_track_ams_owner === state.appFunctional) &&
        (state.appSap === "all" || row.sap_non_sap === state.appSap) &&
        (state.appBusinessCritical === "all" || row.biz_criticality === state.appBusinessCritical)
      );
    }
    function topActiveUsersPoints(rows) {
      const byParentApplication = new Map();
      rows.forEach((row) => {
        const parentName = String(row.parent_application_name || "").trim();
        const activeUsers = Number(row.active_users || 0);
        if (!parentName || activeUsers <= 0) return;
        const current = byParentApplication.get(parentName);
        if (!current || activeUsers > current.value) {
          byParentApplication.set(parentName, {
            label: parentName,
            value: activeUsers,
            displayLabel: fmt(activeUsers)
          });
        }
      });
      return [...byParentApplication.values()]
        .sort((left, right) => right.value - left.value || left.label.localeCompare(right.label))
        .slice(0, Number(state.topActiveUsersN || 10));
    }
    function topActiveUsersToggle() {
      return ["10", "20"].map((value) => `<button type="button" data-top-active-users="${value}" class="${state.topActiveUsersN === value ? "active" : ""}">Top ${value}</button>`).join("");
    }
    const APPLICATION_CRITICALITY_ORDER = ["Very Critical", "Critical", "High", "Medium", "Low"];
    function sortCriticalityValues(values) {
      const criticalityRank = new Map(APPLICATION_CRITICALITY_ORDER.map((label, index) => [label.toLowerCase(), index]));
      return [...values].sort((left, right) => {
        const leftLabel = normalizeApplicationDimension(left);
        const rightLabel = normalizeApplicationDimension(right);
        const leftRank = criticalityRank.has(leftLabel.toLowerCase()) ? criticalityRank.get(leftLabel.toLowerCase()) : APPLICATION_CRITICALITY_ORDER.length;
        const rightRank = criticalityRank.has(rightLabel.toLowerCase()) ? criticalityRank.get(rightLabel.toLowerCase()) : APPLICATION_CRITICALITY_ORDER.length;
        return leftRank - rightRank || leftLabel.localeCompare(rightLabel);
      });
    }
    function normalizeApplicationDimension(value) {
      return String(value ?? "").trim().replace(/\s+/g, " ");
    }
    function applicationServiceKey(row) {
      return normalizeApplicationDimension(row.business_service_ci_name).toLowerCase();
    }
    function globalLocalApplications(rows) {
      const buckets = {
        Global: new Set(),
        Local: new Set()
      };
      rows.forEach((row) => {
        const serviceKey = applicationServiceKey(row);
        if (!serviceKey) return;
        const value = normalizeApplicationDimension(row.global_application).toLowerCase();
        if (value === "yes") {
          buckets.Global.add(serviceKey);
        } else if (value === "no") {
          buckets.Local.add(serviceKey);
        }
      });
      return ["Global", "Local"].map((label) => ({ label, count: buckets[label].size }));
    }
    function criticalityHostingPivot(rows) {
      const cellSets = new Map();
      const criticalityLabels = new Map();
      const hostingLabels = new Map();
      rows.forEach((row) => {
        const serviceKey = applicationServiceKey(row);
        if (!serviceKey) return;
        const lifecycleStageStatus = normalizeApplicationDimension(row.lifecycle_stage_status).toLowerCase();
        if (lifecycleStageStatus !== "in use") return;
        const criticality = normalizeApplicationDimension(row.biz_criticality);
        const hostingEnv = normalizeApplicationDimension(row.hosting_env);
        if (!criticality || !hostingEnv) return;
        const criticalityKey = criticality.toLowerCase();
        const hostingKey = hostingEnv.toLowerCase();
        criticalityLabels.set(criticalityKey, criticality);
        hostingLabels.set(hostingKey, hostingEnv);
        const cellKey = `${criticalityKey}|${hostingKey}`;
        if (!cellSets.has(cellKey)) cellSets.set(cellKey, new Set());
        cellSets.get(cellKey).add(serviceKey);
      });
      const rowTotals = new Map();
      const columnTotalsByKey = new Map();
      cellSets.forEach((services, cellKey) => {
        const [criticalityKey, hostingKey] = cellKey.split("|");
        const count = services.size;
        rowTotals.set(criticalityKey, (rowTotals.get(criticalityKey) || 0) + count);
        columnTotalsByKey.set(hostingKey, (columnTotalsByKey.get(hostingKey) || 0) + count);
      });
      const criticalityRank = new Map(APPLICATION_CRITICALITY_ORDER.map((label, index) => [label.toLowerCase(), index]));
      const criticalityKeys = [...criticalityLabels.keys()].sort((left, right) => {
        const leftRank = criticalityRank.has(left) ? criticalityRank.get(left) : APPLICATION_CRITICALITY_ORDER.length;
        const rightRank = criticalityRank.has(right) ? criticalityRank.get(right) : APPLICATION_CRITICALITY_ORDER.length;
        return leftRank - rightRank || (rowTotals.get(right) || 0) - (rowTotals.get(left) || 0) || criticalityLabels.get(left).localeCompare(criticalityLabels.get(right));
      });
      const hostingKeys = [...hostingLabels.keys()].sort((left, right) =>
        (columnTotalsByKey.get(right) || 0) - (columnTotalsByKey.get(left) || 0) || hostingLabels.get(left).localeCompare(hostingLabels.get(right))
      );
      const values = criticalityKeys.map((criticalityKey) => {
        const criticality = criticalityLabels.get(criticalityKey);
        const counts = {};
        let total = 0;
        hostingKeys.forEach((hostingKey) => {
          const hostingEnv = hostingLabels.get(hostingKey);
          const count = cellSets.get(`${criticalityKey}|${hostingKey}`)?.size || 0;
          counts[hostingEnv] = count;
          total += count;
        });
        return { business_criticality: criticality, counts, total };
      });
      const columnTotals = {};
      hostingKeys.forEach((hostingKey) => {
        const hostingEnv = hostingLabels.get(hostingKey);
        columnTotals[hostingEnv] = columnTotalsByKey.get(hostingKey) || 0;
      });
      return {
        rows: criticalityKeys.map((criticalityKey) => criticalityLabels.get(criticalityKey)),
        columns: hostingKeys.map((hostingKey) => hostingLabels.get(hostingKey)),
        values,
        column_totals: columnTotals,
        grand_total: values.reduce((sumValue, row) => sumValue + row.total, 0)
      };
    }
    function criticalityHostingPivotTable(pivot) {
      if (!pivot.grand_total) return `<p class="muted">No in-use applications match the selected filters.</p>`;
      return `<table class="applications-pivot-table">
        <thead><tr><th>Business Criticality</th>${pivot.columns.map((column) => `<th class="numeric-cell">${esc(column)}</th>`).join("")}<th class="numeric-cell total-cell">Total</th></tr></thead>
        <tbody>
          ${pivot.rows.map((criticality) => {
            const row = pivot.values.find((item) => item.business_criticality === criticality) || { counts: {}, total: 0 };
            return `<tr><th>${esc(criticality)}</th>${pivot.columns.map((column) => `<td class="numeric-cell">${fmt(row.counts[column] || 0)}</td>`).join("")}<td class="numeric-cell total-cell">${fmt(row.total || 0)}</td></tr>`;
          }).join("")}
          <tr class="pivot-total-row"><th>Total</th>${pivot.columns.map((column) => `<td class="numeric-cell total-cell">${fmt(pivot.column_totals[column] || 0)}</td>`).join("")}<td class="numeric-cell total-cell grand-total-cell" aria-label="Grand total ${fmt(pivot.grand_total)}" title="Grand total"><span class="grand-total-label">Grand Total</span><strong>${fmt(pivot.grand_total)}</strong></td></tr>
        </tbody>
      </table>`;
    }
    const LIFECYCLE_PLANS = ["Invest", "Disinvest", "Maintain", "Retired"];
    const LIFECYCLE_PLAN_COLORS = {
      Invest: COLORS.teal,
      Disinvest: "#991b1b",
      Maintain: COLORS.blue,
      Retired: "#581c87"
    };
    const LIFECYCLE_HORIZONS = [
      { label: "Current", field: "lifecycle_current" },
      { label: "1 to 3 years", field: "lifecycle_1_to_3_years" },
      { label: "3 to 5 years", field: "lifecycle_3_to_5_years" }
    ];
    function canonicalLifecyclePlan(value) {
      const normalized = normalizeApplicationDimension(value).toLowerCase();
      return LIFECYCLE_PLANS.find((plan) => plan.toLowerCase() === normalized) || null;
    }
    function lifecyclePlanTitle(plan) {
      return plan === "Retired" ? "Applications Planned to Retire" : `Applications Planned to ${plan}`;
    }
    function lifecyclePlanColor(plan) {
      return LIFECYCLE_PLAN_COLORS[plan] || COLORS.slate;
    }
    function lifecyclePlanCommentaryKey(plan) {
      return `applications_lifecycle_plan_${String(plan || "Invest").toLowerCase()}`;
    }
    function inUseLifecycleApplication(row) {
      return normalizeApplicationDimension(row.lifecycle_stage_status).toLowerCase() === "in use" && !!applicationServiceKey(row);
    }
    function lifecyclePlanningData(rows, selectedPlan) {
      const cellSets = new Map();
      const selectedRows = new Map();
      rows.filter(inUseLifecycleApplication).forEach((row) => {
        const serviceKey = applicationServiceKey(row);
        LIFECYCLE_HORIZONS.forEach((horizon) => {
          const plan = canonicalLifecyclePlan(row[horizon.field]);
          if (!plan) return;
          const cellKey = `${plan}|${horizon.label}`;
          if (!cellSets.has(cellKey)) cellSets.set(cellKey, new Set());
          cellSets.get(cellKey).add(serviceKey);
        });
        const selectedHorizons = LIFECYCLE_HORIZONS
          .filter((horizon) => canonicalLifecyclePlan(row[horizon.field]) === selectedPlan)
          .map((horizon) => horizon.label);
        if (!selectedHorizons.length) return;
        if (!selectedRows.has(serviceKey)) {
          selectedRows.set(serviceKey, { ...row, selected_plan_horizons: selectedHorizons });
          return;
        }
        const existing = selectedRows.get(serviceKey);
        selectedHorizons.forEach((horizon) => {
          if (!existing.selected_plan_horizons.includes(horizon)) existing.selected_plan_horizons.push(horizon);
        });
      });
      const horizonLabels = LIFECYCLE_HORIZONS.map((horizon) => horizon.label);
      const inUseApplicationKeys = new Set(rows.filter(inUseLifecycleApplication).map(applicationServiceKey));
      const matrixRows = LIFECYCLE_PLANS.map((plan) => {
        const counts = {};
        horizonLabels.forEach((horizon) => {
          const count = cellSets.get(`${plan}|${horizon}`)?.size || 0;
          counts[horizon] = count;
        });
        return { plan, counts };
      });
      const criticalityRank = new Map(APPLICATION_CRITICALITY_ORDER.map((label, index) => [label.toLowerCase(), index]));
      const criticalitySort = (value) => criticalityRank.has(normalizeApplicationDimension(value).toLowerCase())
        ? criticalityRank.get(normalizeApplicationDimension(value).toLowerCase())
        : APPLICATION_CRITICALITY_ORDER.length;
      const applications = [...selectedRows.values()].sort((left, right) =>
        criticalitySort(left.biz_criticality) - criticalitySort(right.biz_criticality) ||
        normalizeApplicationDimension(left.functional_track).localeCompare(normalizeApplicationDimension(right.functional_track)) ||
        normalizeApplicationDimension(left.parent_application_name).localeCompare(normalizeApplicationDimension(right.parent_application_name)) ||
        normalizeApplicationDimension(left.business_service_ci_name).localeCompare(normalizeApplicationDimension(right.business_service_ci_name))
      );
      return {
        matrix: {
          plans: LIFECYCLE_PLANS,
          horizons: horizonLabels,
          rows: matrixRows,
          in_use_application_count: inUseApplicationKeys.size
        },
        selected_plan: {
          plan: selectedPlan,
          chart: horizonLabels.map((horizon) => ({ label: horizon, count: cellSets.get(`${selectedPlan}|${horizon}`)?.size || 0 })),
          applications,
          application_count: applications.length
        }
      };
    }
    function lifecyclePlanningMatrixTable(data) {
      const matrix = data.matrix;
      if (!matrix.in_use_application_count) return `<p class="muted">No In Use applications match the current filters for lifecycle planning.</p>`;
      return `<table class="applications-pivot-table lifecycle-matrix-table">
        <thead><tr><th>Lifecycle Plan</th>${matrix.horizons.map((horizon) => `<th class="numeric-cell">${esc(horizon)}</th>`).join("")}</tr></thead>
        <tbody>
          ${matrix.rows.map((row) => `<tr><th>${esc(row.plan)}</th>${matrix.horizons.map((horizon) => `<td class="numeric-cell">${fmt(row.counts[horizon] || 0)}</td>`).join("")}</tr>`).join("")}
        </tbody>
      </table><p class="lifecycle-matrix-note">Matrix is based on ${fmt(matrix.in_use_application_count)} In Use applications.</p>`;
    }
    function lifecyclePlanToggle() {
      return LIFECYCLE_PLANS.map((plan) => `<button type="button" data-lifecycle-plan="${plan}" class="${state.lifecyclePlan === plan ? "active" : ""}">${plan}</button>`).join("");
    }
    function lifecycleDetailTable(rows) {
      if (!rows.length) return `<p class="muted">No applications found for the selected lifecycle plan.</p>`;
      const columns = [
        ["Business Service CI Name", "business_service_ci_name"],
        ["Parent Business Application", "parent_application_name"],
        ["Functional Track", "functional_track"],
        ["AMS Owner", "ams_owner"],
        ["Application Owner", "application_owner"],
        ["Supported By Vendor", "supported_by_vendor"],
        ["Install Type", "install_type"],
        ["Business Criticality", "biz_criticality"],
        ["Architecture Type", "architecture_type"],
        ["Application Type", "app_type"],
        ["Hosting Env", "hosting_env"],
        ["Global", "global_application"],
        ["Active Users", "active_users"],
        ["Lifecycle - Current", "lifecycle_current"],
        ["Lifecycle - 1 to 3 years", "lifecycle_1_to_3_years"],
        ["Lifecycle - 3 to 5 years", "lifecycle_3_to_5_years"],
        ["Selected Plan Horizons", "selected_plan_horizons"]
      ];
      return `<table class="applications-table lifecycle-detail-table"><thead><tr>${columns.map(([label]) => `<th>${esc(label)}</th>`).join("")}</tr></thead><tbody>${rows.map((row) => `<tr>${columns.map(([, field]) => {
        const value = Array.isArray(row[field]) ? row[field].join(", ") : row[field];
        return `<td>${esc(field === "active_users" && value !== null && value !== undefined ? fmt(value) : (value ?? ""))}</td>`;
      }).join("")}</tr>`).join("")}</tbody></table>`;
    }
    function tableToTsv(table) {
      return [...table.querySelectorAll("tr")].map((tr) =>
        [...tr.children].map((cell) => String(cell.textContent || "").trim()).join("\\t")
      ).join("\\n");
    }
    function installTableCopyButtons(root) {
      root.querySelectorAll("[data-copy-table]").forEach((button) => {
        button.addEventListener("click", async () => {
          const table = document.getElementById(button.dataset.copyTable);
          const status = button.closest(".validation-actions")?.querySelector(".copy-chart-status");
          if (!table) return;
          try {
            await navigator.clipboard.writeText(tableToTsv(table));
            if (status) status.textContent = "Copied table.";
          } catch (error) {
            if (status) status.textContent = "Copy failed. Select the table and copy manually.";
          }
        });
      });
    }
    function installScrollableTableKeyboard(root) {
      root.querySelectorAll(".validation-table-scroll, .offline-validation-scroll").forEach((frame) => {
        if (frame.dataset.keyboardScrollReady === "true") return;
        frame.dataset.keyboardScrollReady = "true";
        frame.addEventListener("keydown", (event) => {
          const scrollStep = event.shiftKey ? 240 : 80;
          if (event.key === "ArrowRight") {
            frame.scrollLeft += scrollStep;
            event.preventDefault();
          } else if (event.key === "ArrowLeft") {
            frame.scrollLeft -= scrollStep;
            event.preventDefault();
          } else if (event.key === "PageDown") {
            frame.scrollLeft += 480;
            event.preventDefault();
          } else if (event.key === "PageUp") {
            frame.scrollLeft -= 480;
            event.preventDefault();
          } else if (event.key === "Home") {
            frame.scrollLeft = 0;
            event.preventDefault();
          } else if (event.key === "End") {
            frame.scrollLeft = frame.scrollWidth;
            event.preventDefault();
          }
        });
        frame.addEventListener("wheel", (event) => {
          if (!event.shiftKey || Math.abs(event.deltaY) <= Math.abs(event.deltaX)) return;
          frame.scrollLeft += event.deltaY;
          event.preventDefault();
        }, { passive: false });
      });
    }
    function renderAssignmentGroupMapping() {
      const payload = DASHBOARD.applications.assignment_group_mapping?.[state.appMappingSource] || { rows: [], basis_security_rows: [], summary: {}, available_functional_tracks: [] };
      const rows = (payload.rows || []).filter((row) =>
        (state.appMappingScope === "all" || row.scope === state.appMappingScope) &&
        (state.appMappingTrack === "all" || row.functional_track === state.appMappingTrack)
      );
      const basisRows = (payload.basis_security_rows || []).filter((row) =>
        (state.appMappingScope === "all" || row.scope === state.appMappingScope) &&
        (state.appMappingTrack === "all" || row.functional_track === state.appMappingTrack)
      );
      const allMappingRows = [...(payload.rows || []), ...(payload.basis_security_rows || [])];
      const tracks = [...new Set(allMappingRows
        .filter((row) => state.appMappingScope === "all" || row.scope === state.appMappingScope)
        .map((row) => row.functional_track || "Unmapped Functional Track"))].sort((a, b) => a.localeCompare(b));
      const sourceButtons = [
        ["application_inventory", "Application Inventory"],
        ["tickets", "Tickets Data"]
      ].map(([value, label]) => `<button type="button" data-app-mapping-source="${value}" class="${state.appMappingSource === value ? "active" : ""}">${label}</button>`).join("");
      const scopeButtons = [
        ["in_scope", "In-Scope"],
        ["out_of_scope", "Out-of-Scope"],
        ["all", "All"]
      ].map(([value, label]) => `<button type="button" data-app-mapping-scope="${value}" class="${state.appMappingScope === value ? "active" : ""}">${label}</button>`).join("");
      const trackButtons = [`<button type="button" data-app-mapping-track="all" class="${state.appMappingTrack === "all" ? "active" : ""}">All Tracks</button>`, ...tracks.map((track) => `<button type="button" data-app-mapping-track="${esc(track)}" class="${state.appMappingTrack === track ? "active" : ""}">${esc(track)}</button>`)].join("");
      const inventoryHeaders = state.appMappingSource === "application_inventory" ? "<th>Application Number</th><th>Application Owner</th><th>Supported By Vendor</th>" : "";
      const inventoryCells = (row) => state.appMappingSource === "application_inventory" ? `<td>${esc(row.application_number || "-")}</td><td>${esc(row.application_owner || "-")}</td><td>${esc(row.supported_by_vendor || "-")}</td>` : "";
      const countHeaders = state.appMappingSource === "tickets" ? "<th>Incident Count</th><th>SC Task Count</th><th>Total Ticket Count</th><th>Avg Monthly Incidents</th><th>Avg Monthly SC Tasks</th><th>Avg Monthly Total Tickets</th>" : "";
      const countCells = (row) => state.appMappingSource === "tickets" ? `<td class="numeric-cell">${fmt(row.incident_count || 0)}</td><td class="numeric-cell">${fmt(row.sc_task_count || 0)}</td><td class="numeric-cell">${fmt(row.total_ticket_count || 0)}</td><td class="numeric-cell">${fmt(row.avg_monthly_incidents || 0)}</td><td class="numeric-cell">${fmt(row.avg_monthly_sc_tasks || 0)}</td><td class="numeric-cell">${fmt(row.avg_monthly_total_tickets || 0)}</td>` : "";
      const extraColumnCount = state.appMappingSource === "tickets" ? 6 : 3;
      const mappingTable = (tableRows, tableId, emptyMessage) => `<div class="table-frame table-scroll validation-table-frame offline-validation-scroll offline-mapping-scroll" role="region" tabindex="0" aria-label="Scrollable Assignment Group Mapping table"><table id="${tableId}" class="applications-table validation-table"><thead><tr><th>Assignment Group</th><th>Functional Track</th><th>AMS Owner</th><th>Support Lead</th><th>Parent Business Application</th><th>Business Service CI Name</th>${inventoryHeaders}<th>Scope</th>${countHeaders}</tr></thead><tbody>${tableRows.length ? tableRows.map((row) => `<tr><td>${esc(row.assignment_group)}</td><td>${esc(row.functional_track)}</td><td>${esc(row.ams_owner)}</td><td>${esc(row.support_lead)}</td><td>${esc(row.parent_business_application)}</td><td>${esc(row.business_service_ci_name)}</td>${inventoryCells(row)}<td>${esc(row.scope)}</td>${countCells(row)}</tr>`).join("") : `<tr><td colspan="${7 + extraColumnCount}">${esc(emptyMessage)}</td></tr>`}</tbody></table></div>`;
      const basisSection = basisRows.length ? `<section class="validation-subsection"><div class="chart-title-row"><div><p class="label">Confirmed Out-of-Scope</p><h3>BASIS and SECURITY Assignment Group Mapping</h3><p class="muted">Confirmed out-of-scope assignment groups containing "Basis" or "Security".</p></div><div class="validation-actions"><button type="button" data-copy-table="offline-app-assignment-basis-security">Copy Table</button><span class="copy-chart-status"></span></div></div>${mappingTable(basisRows, "offline-app-assignment-basis-security", "No BASIS or SECURITY assignment groups found for the selected scope and filters.")}</section>` : "";
      return `<section class="panel full"><p class="label">Applications</p><h2>Assignment Group ↔ Application Mapping</h2><p class="muted">Static validation table for Assignment Group mappings from Application Inventory or normalized Incident and SC Task data.</p>
        <div class="validation-toolbar">${sourceButtons}</div>
        <div class="validation-toolbar">${scopeButtons}</div>
        <div class="validation-toolbar">${trackButtons}</div>
        <p class="muted">Showing ${fmt(rows.length)} Assignment Group mappings.${state.appMappingSource === "tickets" && payload.volume_period ? ` Average monthly volumes are based on ${esc(payload.volume_period.label)}.` : ""}</p>
        <div class="validation-actions"><button type="button" data-copy-table="offline-app-assignment-mapping">Copy Table</button><span class="copy-chart-status"></span></div>
        ${mappingTable(rows, "offline-app-assignment-mapping", "No mappings match the selected controls.")}
        ${basisSection}
        ${commentaryMarkup({ dashboard_area: "applications", tab_name: "applications", sub_tab_name: "assignment_group_mapping", section_key: "applications_assignment_group_mapping", chart_key: "assignment_group_mapping", scope_filter: "all", ticket_type_filter: "all", functional_track_ams_owner: "all" })}
      </section>`;
    }
    function renderApplications() {
      const rows = filteredApplications();
      const topActiveUsers = topActiveUsersPoints(rows);
      const globalLocalData = globalLocalApplications(rows);
      const criticalityPivot = criticalityHostingPivot(rows);
      const lifecycleData = lifecyclePlanningData(rows, state.lifecyclePlan);
      const functionalValues = uniqueSorted(DASHBOARD.applications.rows, "functional_track_ams_owner");
      const appScopeValues = [
        { value: "in_scope", label: "In Scope" },
        { value: "out_of_scope", label: "Out of Scope" }
      ].filter((item) => DASHBOARD.applications.rows.some((row) => row.scope_status === item.value));
      const sapValues = uniqueSorted(DASHBOARD.applications.rows, "sap_non_sap");
      const businessCriticalValues = sortCriticalityValues(uniqueSorted(DASHBOARD.applications.rows, "biz_criticality"));
      const businessCount = rows.filter((row) => ["business", "business application"].includes(String(row.app_type).toLowerCase())).length;
      const technicalCount = rows.filter((row) => ["technical", "technical application"].includes(String(row.app_type).toLowerCase())).length;
      const criticalCount = rows.filter((row) => String(row.biz_criticality).toLowerCase() === "critical").length;
      const veryCriticalCount = rows.filter((row) => String(row.biz_criticality).toLowerCase() === "very critical").length;
      const applicationsSubtabs = ["overview", "lifecycle_planning", "assignment_group_mapping"].map((tab) => {
        const label = tab === "overview"
          ? "Overview"
          : tab === "lifecycle_planning"
            ? "Lifecycle Planning"
            : "Assignment Group Mapping";
        return `<button type="button" data-app-subtab="${tab}" class="${state.appSubTab === tab ? "active" : ""}">${label}</button>`;
      }).join("");
      const overviewMarkup = `
        <div class="summary-grid cards-grid">
          ${tile("Applications", fmt(new Set(rows.map((row) => row.business_service_ci_name)).size), "", 0, 6)}
          ${tile("Functional Groups", fmt(new Set(rows.map((row) => row.functional_track)).size), "", 1, 6)}
          ${tile("Assignment Groups", fmt(new Set(rows.map((row) => row.assignment_group)).size), "", 2, 6)}
          ${tile("Parent Business Apps", fmt(new Set(rows.map((row) => row.parent_application_name)).size), "", 3, 6)}
          ${tile("Application Type", `Business: ${fmt(businessCount)}`, `Technical: ${fmt(technicalCount)}`, 4, 6)}
          ${tile("Criticality", `Very Critical: ${fmt(veryCriticalCount)}`, `Critical: ${fmt(criticalCount)}`, 5, 6)}
        </div>
        ${commentaryMarkup({ dashboard_area: "applications", tab_name: "applications", sub_tab_name: "", section_key: "applications_summary", chart_key: "", scope_filter: "all", ticket_type_filter: "all", functional_track_ams_owner: state.appFunctional })}
        <div class="chart-grid">
          <section class="chart-card panel" data-commentary-key="strategic"><h3>Strategic</h3><div class="chart-frame chart-stage">${pieChart(countBy(rows, "strategic"))}</div></section>
          <section class="chart-card panel" data-commentary-key="lifecycle_stage"><h3>Lifecycle Stage</h3><div class="chart-frame chart-stage">${barChart(countBy(rows, "lifecycle_stage_status").map((row) => ({ label: row.label, count: row.count })), [{ key: "count", name: "Applications", color: COLORS.blue }], { width: 820, applicationChart: true })}</div></section>
          <section class="chart-card panel" data-commentary-key="architecture_type"><h3>Architecture Type</h3><div class="chart-frame chart-stage">${barChart(countBy(rows, "architecture_type").map((row) => ({ label: row.label, count: row.count })), [{ key: "count", name: "Applications", color: COLORS.teal }], { width: 820, applicationChart: true })}</div></section>
          <section class="chart-card panel" data-commentary-key="install_type"><h3>Install Type</h3><div class="chart-frame chart-stage">${barChart(countBy(rows, "install_type").map((row) => ({ label: row.label, count: row.count })), [{ key: "count", name: "Applications", color: COLORS.purple }], { width: 820, applicationChart: true })}</div></section>
          <section class="chart-card panel" data-commentary-key="hosting_env"><h3>Hosting Env</h3><div class="chart-frame chart-stage">${barChart(countBy(rows, "hosting_env").map((row) => ({ label: row.label, count: row.count })), [{ key: "count", name: "Applications", color: COLORS.orange }], { width: 820, applicationChart: true })}</div></section>
          <section class="chart-card panel" data-commentary-key="applications_global_local"><h3>Global vs Local Applications</h3><div class="chart-frame chart-stage">${pieChart(globalLocalData)}</div></section>
        </div>
        <section class="chart-card panel full" data-commentary-key="applications_criticality_hosting_pivot"><h3>Application Criticality by Hosting Environment</h3><p class="muted">Count of unique Business Service CI Names with Life Cycle Stage Status = In Use.</p><div class="table-frame table-scroll">${criticalityHostingPivotTable(criticalityPivot)}</div></section>
        <section class="chart-card panel full" data-commentary-key="top_active_users"><div class="chart-title-row"><div><h3>Top Parent Business Applications by Active Users</h3><p class="muted">Application Inventory only. One row per Parent Business Application, using the highest Active Users value when duplicates exist.</p></div><div class="pattern-buttons">${topActiveUsersToggle()}</div></div><div class="chart-frame chart-stage">${horizontalBarChart(topActiveUsers, { title: "Top Parent Business Applications by Active Users", legend: "Active Users", color: COLORS.teal, height: state.topActiveUsersN === "20" ? 720 : 470, emptyMessage: "Active Users data is not available yet." })}</div></section>
        <section class="panel table-card" data-commentary-key="application_list" style="padding:14px"><h3>Application List</h3><div class="table-frame table-scroll">${applicationTable(rows)}</div></section>`;
      const lifecycleMarkup = `
        <section class="panel lifecycle-planning-intro"><p class="label">Applications</p><h2>Lifecycle Planning</h2><p class="muted">Lifecycle planning shows In Use applications across Current, 1 to 3 years, and 3 to 5 years planning horizons.</p></section>
        <section class="panel lifecycle-matrix-panel"><p class="label">Lifecycle Planning Matrix</p><h2>Application Lifecycle Planning Matrix</h2><p class="muted">Counts represent distinct Business Service CI Names per planning horizon. The same application can appear in multiple horizons.</p><div class="table-frame table-scroll">${lifecyclePlanningMatrixTable(lifecycleData)}</div></section>
        <section class="panel lifecycle-plan-panel"><div class="chart-title-row"><div><p class="label">Plan Focus</p><h2>${esc(lifecyclePlanTitle(state.lifecyclePlan))}</h2></div><div class="pattern-buttons">${lifecyclePlanToggle()}</div></div>${commentaryMarkup({ dashboard_area: "applications", tab_name: "applications", sub_tab_name: "lifecycle_planning", section_key: "lifecycle_planning_selected_plan", chart_key: lifecyclePlanCommentaryKey(state.lifecyclePlan), scope_filter: "all", ticket_type_filter: "all", functional_track_ams_owner: state.appFunctional })}</section>
        <section class="chart-card panel full"><h3>${esc(lifecyclePlanTitle(state.lifecyclePlan))}</h3><p class="muted">Count of unique Business Service CI Names by planning horizon.</p><div class="chart-frame chart-stage">${lifecyclePlanLineChart(lifecycleData.selected_plan.chart, state.lifecyclePlan)}</div></section>
        <section class="panel table-card" style="padding:14px"><h3>${esc(lifecyclePlanTitle(state.lifecyclePlan))} - Details</h3><p class="muted">Showing ${fmt(lifecycleData.selected_plan.application_count)} applications with ${esc(state.lifecyclePlan)} plan across one or more lifecycle horizons.</p><div class="table-frame table-scroll">${lifecycleDetailTable(lifecycleData.selected_plan.applications)}</div></section>`;
      document.getElementById("applications").innerHTML = `<div class="layout dashboard-layout">
        <aside class="filters filter-pane panel">
          <p class="label">Filters</p><h2>Applications</h2>
          ${renderSelect("app-scope", "Application Scope", [{ value: "all", label: "All" }, ...appScopeValues], state.appScope)}
          ${renderSelect("app-functional", "Functional Track / AMS Owner", [{ value: "all", label: "All" }, ...functionalValues.map((value) => ({ value, label: value }))], state.appFunctional)}
          ${renderSelect("app-sap", "SAP / Non-SAP", [{ value: "all", label: "All" }, ...sapValues.map((value) => ({ value, label: value }))], state.appSap)}
          ${renderSelect("app-business-critical", "Business Criticality", [{ value: "all", label: "All" }, ...businessCriticalValues.map((value) => ({ value, label: value }))], state.appBusinessCritical)}
        </aside>
        <section class="main main-content">
          <div class="pattern-buttons application-subtabs">${applicationsSubtabs}</div>
          ${state.appSubTab === "overview" ? overviewMarkup : state.appSubTab === "lifecycle_planning" ? lifecycleMarkup : renderAssignmentGroupMapping()}
        </section>
      </div>`;
      document.getElementById("app-scope").addEventListener("change", (event) => { state.appScope = event.target.value; safeRenderSection("applications", "Applications", renderApplications); });
      document.getElementById("app-functional").addEventListener("change", (event) => { state.appFunctional = event.target.value; safeRenderSection("applications", "Applications", renderApplications); });
      document.getElementById("app-sap").addEventListener("change", (event) => { state.appSap = event.target.value; safeRenderSection("applications", "Applications", renderApplications); });
      document.getElementById("app-business-critical").addEventListener("change", (event) => { state.appBusinessCritical = event.target.value; safeRenderSection("applications", "Applications", renderApplications); });
      document.querySelectorAll("[data-app-subtab]").forEach((button) => {
        button.addEventListener("click", () => { state.appSubTab = button.dataset.appSubtab; safeRenderSection("applications", "Applications", renderApplications); });
      });
      document.querySelectorAll("[data-top-active-users]").forEach((button) => {
        button.addEventListener("click", () => { state.topActiveUsersN = button.dataset.topActiveUsers; safeRenderSection("applications", "Applications", renderApplications); });
      });
      document.querySelectorAll("[data-lifecycle-plan]").forEach((button) => {
        button.addEventListener("click", () => { state.lifecyclePlan = button.dataset.lifecyclePlan; safeRenderSection("applications", "Applications", renderApplications); });
      });
      document.querySelectorAll("[data-app-mapping-source]").forEach((button) => {
        button.addEventListener("click", () => { state.appMappingSource = button.dataset.appMappingSource; state.appMappingTrack = "all"; safeRenderSection("applications", "Applications", renderApplications); });
      });
      document.querySelectorAll("[data-app-mapping-scope]").forEach((button) => {
        button.addEventListener("click", () => { state.appMappingScope = button.dataset.appMappingScope; state.appMappingTrack = "all"; safeRenderSection("applications", "Applications", renderApplications); });
      });
      document.querySelectorAll("[data-app-mapping-track]").forEach((button) => {
        button.addEventListener("click", () => { state.appMappingTrack = button.dataset.appMappingTrack; safeRenderSection("applications", "Applications", renderApplications); });
      });
      attachDefaultCommentaries(document.getElementById("applications"), { dashboard_area: "applications", tab_name: "applications", sub_tab_name: "", section_key: "applications_charts", scope_filter: "all", ticket_type_filter: "all", functional_track_ams_owner: state.appFunctional });
      installCommentaryEditors(document.getElementById("applications"));
      installChartCopyButtons(document.getElementById("applications"));
      installTableCopyButtons(document.getElementById("applications"));
      installScrollableTableKeyboard(document.getElementById("applications"));
    }
    function applicationTable(rows) {
      const columns = ["business_service_ci_name", "scope_status", "parent_application_name", "assignment_group", "sap_non_sap", "application_owner", "support_lead", "functional_track", "ams_owner", "supported_by_vendor", "hosting_env", "global_application", "lifecycle_stage_status", "lifecycle_current", "lifecycle_1_to_3_years", "lifecycle_3_to_5_years", "active_users", "app_type", "architecture_type", "biz_criticality", "install_status", "install_type", "lifecycle_status", "operating_system", "sox_scope", "strategic"];
      return `<table class="applications-table"><thead><tr>${columns.map((column) => `<th>${esc(column.replaceAll("_", " "))}</th>`).join("")}</tr></thead><tbody>${rows.map((row) => `<tr>${columns.map((column) => `<td>${esc(column === "active_users" && row[column] !== null && row[column] !== undefined ? fmt(row[column]) : (row[column] ?? ""))}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
    }
    function filteredVolumetricsRows() {
      return DASHBOARD.volumetrics.monthly_rows.filter(offlineFilterMatch);
    }
    function filteredPatternRows() {
      return DASHBOARD.volumetrics.created_patterns.rows.filter((row) =>
        row.pattern_type === state.pattern && offlineFilterMatch(row)
      );
    }
    function offlineFilterMatch(row) {
      return (
        (state.volScope === "all" || row.scope === state.volScope) &&
        (state.volTicketType === "all" || row.ticket_type === state.volTicketType) &&
        (state.volFunctional === "all" || row.functional_track_ams_owner === state.volFunctional) &&
        (state.volSap === "all" || row.sap_non_sap === state.volSap) &&
        (state.volBusinessCritical === "all" || row.business_critical === state.volBusinessCritical)
      );
    }
    function filteredHourlyRows() {
      return (DASHBOARD.volumetrics.overall_volume_trends?.created_resolved_by_hour?.rows || [])
        .filter((row) => row.day_type === state.hourlyDayType && offlineFilterMatch(row));
    }
    function filteredPriorityRows() {
      return (DASHBOARD.volumetrics.overall_volume_trends?.priority_distribution?.rows || [])
        .filter(offlineFilterMatch);
    }
    function filteredSlaRows() {
      return (DASHBOARD.volumetrics.overall_sla_trends?.rows || []).filter((row) =>
        (state.volScope === "all" || row.scope === state.volScope) &&
        (state.volFunctional === "all" || row.functional_track_ams_owner === state.volFunctional) &&
        (state.volSap === "all" || row.sap_non_sap === state.volSap) &&
        (state.volBusinessCritical === "all" || row.business_critical === state.volBusinessCritical)
      );
    }
    function renderVolumetrics() {
      const rows = filteredVolumetricsRows();
      const periods = aggregateByPeriod(rows);
      document.getElementById("volumetrics").innerHTML = `<div class="layout dashboard-layout">
        <aside class="filters filter-pane panel">
          <p class="label">Filters</p><h2>Volumetrics &amp; SLA</h2>
          ${renderSelect("vol-scope", "Scope", DASHBOARD.volumetrics.filter_values.scope, state.volScope)}
          ${renderSelect("vol-ticket", "Ticket Type", DASHBOARD.volumetrics.filter_values.ticket_type, state.volTicketType)}
          ${renderSelect("vol-functional", "Functional Track / AMS Owner", [{ value: "all", label: "All" }, ...DASHBOARD.volumetrics.filter_values.functional_track_ams_owner.map((value) => ({ value, label: value }))], state.volFunctional)}
          ${renderSelect("vol-sap", "SAP / Non-SAP", [{ value: "all", label: "All" }, ...DASHBOARD.volumetrics.filter_values.sap_non_sap.map((value) => ({ value, label: value }))], state.volSap)}
          ${renderSelect("vol-business-critical", "Business Criticality", [{ value: "all", label: "All" }, ...DASHBOARD.volumetrics.filter_values.business_critical.map((value) => ({ value, label: value }))], state.volBusinessCritical)}
        </aside>
        <section class="main main-content">
          <section class="panel" style="padding:14px"><p class="muted"><strong>Monthly dashboard based on complete uploaded months.</strong> Charts use ${dateText(DASHBOARD.metadata.complete_month_from)} to ${dateText(DASHBOARD.metadata.complete_month_to)}. Data available from ${dateText(DASHBOARD.metadata.data_available_from)} to ${dateText(DASHBOARD.metadata.data_available_to)}.</p><div class="subtabs">${volSubTabs()}</div></section>
          ${renderVolumetricsSubTab(periods)}
        </section>
      </div>`;
      ["vol-scope", "vol-ticket", "vol-functional", "vol-sap", "vol-business-critical"].forEach((id) => {
        document.getElementById(id).addEventListener("change", (event) => {
          const map = { "vol-scope": "volScope", "vol-ticket": "volTicketType", "vol-functional": "volFunctional", "vol-sap": "volSap", "vol-business-critical": "volBusinessCritical" };
          state[map[id]] = event.target.value;
          safeRenderSection("volumetrics", "Volumetrics & SLA", renderVolumetrics);
        });
      });
      document.querySelectorAll("[data-vol-subtab]").forEach((button) => {
        button.addEventListener("click", () => { state.volSubTab = button.dataset.volSubtab; safeRenderSection("volumetrics", "Volumetrics & SLA", renderVolumetrics); });
      });
      document.querySelectorAll("[data-pattern]").forEach((button) => {
        button.addEventListener("click", () => { state.pattern = button.dataset.pattern; safeRenderSection("volumetrics", "Volumetrics & SLA", renderVolumetrics); });
      });
      document.querySelectorAll("[data-hourly-day]").forEach((button) => {
        button.addEventListener("click", () => { state.hourlyDayType = button.dataset.hourlyDay; safeRenderSection("volumetrics", "Volumetrics & SLA", renderVolumetrics); });
      });
      document.querySelectorAll("[data-priority-view]").forEach((button) => {
        button.addEventListener("click", () => { state.priorityView = button.dataset.priorityView; safeRenderSection("volumetrics", "Volumetrics & SLA", renderVolumetrics); });
      });
      document.querySelectorAll("[data-sla-mode]").forEach((button) => {
        button.addEventListener("click", () => { state.slaMode = button.dataset.slaMode; safeRenderSection("volumetrics", "Volumetrics & SLA", renderVolumetrics); });
      });
      document.querySelectorAll("[data-top-volume]").forEach((button) => {
        button.addEventListener("click", () => { state.topVolumeN = button.dataset.topVolume; safeRenderSection("volumetrics", "Volumetrics & SLA", renderVolumetrics); });
      });
      document.querySelectorAll("[data-top-batch]").forEach((button) => {
        button.addEventListener("click", () => { state.topBatchN = button.dataset.topBatch; safeRenderSection("volumetrics", "Volumetrics & SLA", renderVolumetrics); });
      });
      document.querySelectorAll("[data-top-tickets-user]").forEach((button) => {
        button.addEventListener("click", () => { state.ticketsPerUserN = button.dataset.topTicketsUser; safeRenderSection("volumetrics", "Volumetrics & SLA", renderVolumetrics); });
      });
      document.querySelectorAll("[data-vol-assignment-track]").forEach((button) => {
        button.addEventListener("click", () => { state.volAssignmentTrack = button.dataset.volAssignmentTrack; safeRenderSection("volumetrics", "Volumetrics & SLA", renderVolumetrics); });
      });
      attachDefaultCommentaries(document.getElementById("volumetrics"), currentVolumetricsCommentaryContext());
      installChartCopyButtons(document.getElementById("volumetrics"));
      installTableCopyButtons(document.getElementById("volumetrics"));
      installScrollableTableKeyboard(document.getElementById("volumetrics"));
    }
    function volSubTabs() {
      const labels = {
        overall_volume_trends: "Overall Volume Trends",
        overall_sla_trends: "Overall SLA Trends",
        detailed_volume_trends: "Detailed Volume Trends",
        kpi_trends: "KPI Trends",
        category_wise_trends: "Category-wise Trends",
        assignment_group_volumetrics: "Assignment Group Volumetrics"
      };
      return Object.entries(labels).map(([value, label]) => `<button type="button" data-vol-subtab="${esc(value)}" class="${state.volSubTab === value ? "active" : ""}">${esc(label)}</button>`).join("");
    }
    function assignmentVolumetricsPayload() {
      return DASHBOARD.volumetrics.assignment_group_volumetrics?.[state.volScope] ||
        DASHBOARD.volumetrics.assignment_group_volumetrics?.in_scope ||
        { months: [], tables: { incidents: { rows: [] }, sc_tasks: { rows: [] }, overall: { rows: [] } }, available_functional_tracks: [] };
    }
    function assignmentVolumetricsRows(table) {
      const rows = table?.rows || [];
      return state.volAssignmentTrack === "all"
        ? rows
        : rows.filter((row) => row.functional_track === state.volAssignmentTrack);
    }
    const ASSIGNMENT_METRICS = [
      ["created", "Created"],
      ["resolved", "Resolved"],
      ["cancelled", "Cancelled"]
    ];
    function assignmentMetric(row, month, key) {
      return Number(row.months?.[month.month_key]?.[key] || 0);
    }
    function assignmentMonthTotals(rows, month, key) {
      return rows.reduce((total, row) => total + assignmentMetric(row, month, key), 0);
    }
    function assignmentVolumetricsTable(table, months, tableKey) {
      const rows = assignmentVolumetricsRows(table);
      const tableId = `offline-assignment-vol-${tableKey}`;
      const header1 = `<tr><th class="assignment-group-column" rowspan="2">Assignment Group</th><th class="reference-column" rowspan="2">Functional Track</th><th class="reference-column" rowspan="2">AMS Owner</th><th class="reference-column" rowspan="2">Support Lead</th>${months.map((month, index) => `<th class="month-group-${index % 2 === 0 ? "a" : "b"} month-boundary-left month-boundary-right" colspan="3">${esc(month.month_label)}</th>`).join("")}</tr>`;
      const header2 = `<tr>${months.flatMap((month, index) => ASSIGNMENT_METRICS.map(([key, label], metricIndex) => `<th class="month-group-${index % 2 === 0 ? "a" : "b"} metric-${key} ${metricIndex === 0 ? "month-boundary-left" : ""} ${metricIndex === 2 ? "month-boundary-right" : ""}">${label}</th>`)).join("")}</tr>`;
      const bodyRows = rows.map((row) => `<tr><th class="assignment-group-column">${esc(row.assignment_group)}</th><td class="reference-column">${esc(row.functional_track)}</td><td class="reference-column">${esc(row.ams_owner)}</td><td class="reference-column">${esc(row.support_lead)}</td>${months.flatMap((month, index) => ASSIGNMENT_METRICS.map(([key], metricIndex) => `<td class="numeric-cell month-group-${index % 2 === 0 ? "a" : "b"} metric-${key} ${metricIndex === 0 ? "month-boundary-left" : ""} ${metricIndex === 2 ? "month-boundary-right" : ""}">${fmt(assignmentMetric(row, month, key))}</td>`)).join("")}</tr>`).join("");
      const totalRow = `<tr class="pivot-total-row assignment-volumetrics-total-row"><th class="assignment-group-column">Grand Total</th><td class="reference-column"></td><td class="reference-column"></td><td class="reference-column"></td>${months.flatMap((month, index) => ASSIGNMENT_METRICS.map(([key], metricIndex) => `<td class="numeric-cell total-cell month-group-${index % 2 === 0 ? "a" : "b"} metric-${key} ${metricIndex === 0 ? "month-boundary-left" : ""} ${metricIndex === 2 ? "month-boundary-right" : ""}">${fmt(assignmentMonthTotals(rows, month, key))}</td>`)).join("")}</tr>`;
      return `<section class="panel full"><div class="chart-title-row"><div><p class="label">Assignment Group Volumetrics</p><h3>${esc(table?.title || tableKey)}</h3><p class="muted">Showing ${fmt(rows.length)} Assignment Groups.</p></div><div class="validation-actions"><button type="button" data-copy-table="${tableId}">Copy Table</button><span class="copy-chart-status"></span></div></div><div class="table-frame table-scroll validation-table-frame offline-validation-scroll assignment-volumetrics-frame" role="region" tabindex="0" aria-label="${esc(table?.title || tableKey)} scrollable Assignment Group Volumetrics table"><table id="${tableId}" class="validation-table assignment-volumetrics-table"><thead>${header1}${header2}</thead><tbody>${rows.length ? totalRow + bodyRows : `<tr><td colspan="${4 + months.length * 3}">No Assignment Groups match the selected controls.</td></tr>`}</tbody></table></div></section>`;
    }
    function renderAssignmentGroupVolumetrics() {
      const payload = assignmentVolumetricsPayload();
      const tracks = payload.available_functional_tracks || [];
      const trackButtons = [`<button type="button" data-vol-assignment-track="all" class="${state.volAssignmentTrack === "all" ? "active" : ""}">All Tracks</button>`, ...tracks.map((track) => `<button type="button" data-vol-assignment-track="${esc(track)}" class="${state.volAssignmentTrack === track ? "active" : ""}">${esc(track)}</button>`)].join("");
      const basisTables = [
        ["basis-security-incidents", payload.tables?.basis_security_incidents],
        ["basis-security-sc-tasks", payload.tables?.basis_security_sc_tasks],
        ["basis-security-overall", payload.tables?.basis_security_overall]
      ].filter(([, table]) => (table?.rows || []).length > 0);
      const basisSection = basisTables.length ? `<section class="panel full"><p class="label">Confirmed Out-of-Scope</p><h2>BASIS and SECURITY Assignment Group Volumetrics</h2><p class="muted">Confirmed out-of-scope BASIS/SECURITY assignment groups shown separately for validation.</p></section>${basisTables.map(([key, table]) => assignmentVolumetricsTable(table, payload.months || [], key)).join("")}` : "";
      return `<section class="panel full"><p class="label">Volumetrics &amp; SLA</p><h2>Assignment Group-wise Volumetrics</h2><p class="muted">Monthly created, resolved, and cancelled generic ticket volumes by Assignment Group for Dec-25 through May-26. Problems and Changes are excluded.</p><div class="validation-toolbar">${trackButtons}</div>${commentaryMarkup({ ...currentVolumetricsCommentaryContext(), chart_key: "assignment_group_volumetrics" })}</section>${assignmentVolumetricsTable(payload.tables?.incidents, payload.months || [], "incidents")}${assignmentVolumetricsTable(payload.tables?.sc_tasks, payload.months || [], "sc-tasks")}${assignmentVolumetricsTable(payload.tables?.overall, payload.months || [], "overall")}${basisSection}`;
    }
    function renderVolumetricsSubTab(periods) {
      if (state.volSubTab === "overall_sla_trends") return renderSlaTrends();
      if (state.volSubTab === "detailed_volume_trends") return renderDetailedVolumeTrends();
      if (state.volSubTab === "kpi_trends") return renderKpiTrends();
      if (state.volSubTab === "assignment_group_volumetrics") return renderAssignmentGroupVolumetrics();
      if (state.volSubTab === "category_wise_trends") return placeholder("Category-wise Trends");
      return renderOverallVolume(periods);
    }
    function rankingWindowText() {
      const window = DASHBOARD.volumetrics.detailed_volume_trends?.ranking_window || {};
      if (!window.start_month || !window.end_month) return "Ranking uses the last 6 complete months, excluding the current month.";
      return `Ranking uses average monthly created tickets for ${esc(window.start_month)} to ${esc(window.end_month)}, excluding the current month.`;
    }
    function topToggle(kind, selected) {
      const attribute = kind === "batch"
        ? "data-top-batch"
        : kind === "tickets-user"
          ? "data-top-tickets-user"
          : "data-top-volume";
      return ["10", "20"].map((value) => `<button type="button" ${attribute}="${value}" class="${selected === value ? "active" : ""}">Top ${value}</button>`).join("");
    }
    function detailedVolumeRows() {
      return DASHBOARD.volumetrics.detailed_volume_trends?.application_rows || [];
    }
    function detailedSplitRows() {
      return DASHBOARD.volumetrics.detailed_volume_trends?.split_rows || [];
    }
    function incidentBatchFilterMatch(row) {
      return (
        row.ticket_type === "incident" &&
        (state.volScope === "all" || row.scope === state.volScope) &&
        (state.volFunctional === "all" || row.functional_track_ams_owner === state.volFunctional) &&
        (state.volSap === "all" || row.sap_non_sap === state.volSap) &&
        (state.volBusinessCritical === "all" || row.business_critical === state.volBusinessCritical)
      );
    }
    function inRankingWindow(row) {
      const window = DASHBOARD.volumetrics.detailed_volume_trends?.ranking_window || {};
      return !window.start_month || !window.end_month || (row.period_key >= window.start_month && row.period_key <= window.end_month);
    }
    function topApplicationPoints(options) {
      const topN = Number(options.topN || 10);
      const rows = detailedVolumeRows()
        .filter(options.batch ? incidentBatchFilterMatch : offlineFilterMatch)
        .filter(inRankingWindow);
      const createdKey = options.batch ? "incident_batch_created_count" : "created_count";
      const canceledKey = options.batch ? "incident_batch_canceled_count" : "canceled_closed_incomplete_count";
      const byApp = new Map();
      rows.forEach((row) => {
        const appName = row.application_name || "(blank)";
        const current = byApp.get(appName) || { label: appName, createdSum: 0, canceledSum: 0 };
        current.createdSum += Number(row[createdKey] || 0);
        current.canceledSum += Number(row[canceledKey] || 0);
        byApp.set(appName, current);
      });
      const allPoints = [...byApp.values()]
        .map((row) => ({
          label: row.label,
          created: row.createdSum / 6,
          canceled: row.canceledSum / 6
        }))
        .filter((row) => row.created > 0 || row.canceled > 0)
        .sort((left, right) => right.created - left.created || left.label.localeCompare(right.label));
      const overallCreated = allPoints.reduce((total, row) => total + row.created, 0);
      const points = allPoints.slice(0, topN);
      if (!options.batch) {
        return points.map((row) => {
          const volumePct = overallCreated > 0 ? (row.created / overallCreated) * 100 : null;
          return {
            ...row,
            volumePct,
            displayLabel: `${rounded(row.created)} (${volumePct === null ? "N/A" : `${volumePct.toFixed(1)}%`})`
          };
        });
      }
      const totalCreated = points.reduce((total, row) => total + row.created, 0);
      let runningCreated = 0;
      return points.map((row) => {
        runningCreated += row.created;
        return {
          ...row,
          pareto: totalCreated > 0 ? (runningCreated / totalCreated) * 100 : null
        };
      });
    }
    function ticketsPerUserPoints() {
      const activeUsersByApp = new Map();
      filteredApplications().forEach((row) => {
        const users = Number(row.active_users || 0);
        if (users > 0) activeUsersByApp.set(row.business_service_ci_name || "(blank)", users);
      });
      const rows = detailedVolumeRows().filter(offlineFilterMatch).filter(inRankingWindow);
      const byApp = new Map();
      rows.forEach((row) => {
        const appName = row.application_name || "(blank)";
        if (!activeUsersByApp.has(appName)) return;
        byApp.set(appName, (byApp.get(appName) || 0) + Number(row.created_count || 0));
      });
      return [...byApp.entries()]
        .map(([label, createdSum]) => {
          const activeUsers = activeUsersByApp.get(label);
          const avgMonthly = createdSum / 6;
          const ratio = activeUsers > 0 ? avgMonthly / activeUsers : 0;
          return {
            label,
            value: ratio,
            displayLabel: ratio < 10 ? ratio.toFixed(2) : ratio < 100 ? ratio.toFixed(1) : fmt(Math.round(ratio)),
            activeUsers,
            avgMonthly
          };
        })
        .filter((row) => row.value > 0)
        .sort((left, right) => right.value - left.value || left.label.localeCompare(right.label))
        .slice(0, Number(state.ticketsPerUserN || 10));
    }
    function distributionTicketMatch(row, ticketType) {
      return (
        (ticketType === "all" || row.ticket_type === ticketType) &&
        (state.volScope === "all" || row.scope === state.volScope) &&
        (state.volFunctional === "all" || row.functional_track_ams_owner === state.volFunctional) &&
        (state.volSap === "all" || row.sap_non_sap === state.volSap) &&
        (state.volBusinessCritical === "all" || row.business_critical === state.volBusinessCritical)
      );
    }
    function distributionItems(field, ticketType) {
      const totals = new Map();
      detailedVolumeRows()
        .filter(inRankingWindow)
        .filter((row) => distributionTicketMatch(row, ticketType))
        .forEach((row) => {
          const label = row[field] || "(blank)";
          totals.set(label, (totals.get(label) || 0) + Number(row.created_count || 0));
        });
      return [...totals.entries()]
        .map(([label, count]) => ({ label, count: count / 6 }))
        .filter((row) => row.count > 0)
        .sort((left, right) => right.count - left.count || left.label.localeCompare(right.label));
    }
    function distributionNotApplicable(ticketType) {
      if (state.volTicketType === "all") return false;
      if (state.volTicketType === "incident") return ticketType !== "incident";
      return ticketType !== "sc_task";
    }
    function distributionPieSection(title, field, ticketType) {
      const notApplicable = distributionNotApplicable(ticketType);
      const items = distributionItems(field, ticketType);
      return `<section class="chart-card panel" data-commentary-skip="true"><h3>${esc(title)}</h3><p class="muted">${splitWindowText()}</p><div class="chart-frame chart-stage">${notApplicable ? `<p class="muted" style="padding:12px">This distribution chart is not applicable for the selected ticket type.</p>` : pieChart(items)}</div></section>`;
    }
    function scTaskCatalogPeriodDefinitions() {
      return [
        { key: "H1_2025", label: "H1 2025", title: "H1 2025 Catalog Item Proportion", start: "2025-01", end: "2025-06", from: "2025-01-01", to: "2025-06-30" },
        { key: "H2_2025", label: "H2 2025", title: "H2 2025 Catalog Item Proportion", start: "2025-07", end: "2025-12", from: "2025-07-01", to: "2025-12-31" },
        { key: "H1_2026", label: "H1 2026", title: "H1 2026 Catalog Item Proportion", start: "2026-01", end: "2026-06", from: "2026-01-01", to: "2026-06-30" }
      ];
    }
    function scTaskCatalogPeriodData(period) {
      const rows = detailedVolumeRows().filter((row) =>
        row.ticket_type === "sc_task" &&
        offlineFilterMatch(row) &&
        row.period_key >= period.start &&
        row.period_key <= period.end
      );
      const totals = new Map();
      rows.forEach((row) => {
        const label = row.catalog_item_name || "Unmapped Catalog Item";
        totals.set(label, (totals.get(label) || 0) + Number(row.created_count || 0));
      });
      const allRows = [...totals.entries()]
        .map(([label, count]) => ({ label, count }))
        .filter((row) => row.count > 0)
        .sort((left, right) => right.count - left.count || left.label.localeCompare(right.label));
      const total = allRows.reduce((sum, row) => sum + row.count, 0);
      const topRows = allRows.slice(0, 10).map((row, index) => ({
        ...row,
        rank: index + 1,
        avg: row.count / 6,
        pct: total > 0 ? (row.count / total) * 100 : null
      }));
      const visiblePieRows = [];
      let otherCount = 0;
      allRows.forEach((row) => {
        const pct = total > 0 ? (row.count / total) * 100 : null;
        if (pct !== null && pct < 2) {
          otherCount += row.count;
        } else {
          visiblePieRows.push({ label: row.label, count: row.count });
        }
      });
      if (otherCount > 0) {
        visiblePieRows.push({ label: "Others", count: otherCount });
      }
      const pieRows = visiblePieRows.sort((left, right) =>
        right.count - left.count || left.label.localeCompare(right.label)
      );
      return { period, total, pieRows, topRows };
    }
    function scTaskCatalogTable(periodData) {
      if (!periodData.topRows.length) {
        return `<p class="muted" style="padding:12px">No data available for ${esc(periodData.period.label)}.</p>`;
      }
      return `<div class="table-scroll"><table class="applications-table"><thead><tr><th>Rank</th><th>Catalog Item</th><th>Average Monthly Volume</th></tr></thead><tbody>${periodData.topRows.map((row) => `<tr><td>${fmt(row.rank)}</td><td>${esc(row.label)}</td><td>${Math.round(row.avg)} (${row.pct === null ? "N/A" : `${row.pct.toFixed(1)}%`})</td></tr>`).join("")}</tbody></table></div>`;
    }
    function scTaskCatalogSection() {
      if (state.volTicketType === "incident") {
        return `<section class="chart-card panel full" data-commentary-key="volumetrics_sc_task_catalog_item_proportion"><h3>SC Task Catalog Item Proportion</h3><p class="muted">SC Task Catalog Item Proportion is available for SC Tasks only. Change Ticket Type to All or SC Tasks.</p>${commentaryMarkup({ ...currentVolumetricsCommentaryContext(), chart_key: "volumetrics_sc_task_catalog_item_proportion" })}</section>`;
      }
      const periods = scTaskCatalogPeriodDefinitions().map(scTaskCatalogPeriodData);
      return `<section class="chart-card panel full" data-commentary-key="volumetrics_sc_task_catalog_item_proportion"><h3>SC Task Catalog Item Proportion</h3><p class="muted">Shows the proportion of SC Tasks by catalog item across selected half-year periods. Values are based on created SC Task volume.</p><div class="sc-task-catalog-grid">${periods.map((periodData) => `<section class="sc-task-catalog-card"><h4>${esc(periodData.period.title)}</h4><p class="muted">${esc(periodData.period.from)} to ${esc(periodData.period.to)} · ${fmt(periodData.total)} SC Tasks</p><div class="chart-frame chart-stage">${pieChart(periodData.pieRows)}</div></section>`).join("")}</div><div class="sc-task-catalog-grid">${periods.map((periodData) => `<section class="sc-task-catalog-card"><h4>${esc(periodData.period.label)} Top Catalog Items</h4>${scTaskCatalogTable(periodData)}</section>`).join("")}</div><p class="muted">SC Task Catalog Item Proportion uses SC Tasks only. Incidents, Problems, and Changes are excluded. Catalog items below 2% are grouped into Others. Average monthly volume is calculated over six months.</p>${commentaryMarkup({ ...currentVolumetricsCommentaryContext(), chart_key: "volumetrics_sc_task_catalog_item_proportion" })}</section>`;
    }
    function incidentBatchTrendPoints() {
      const rows = detailedVolumeRows().filter(incidentBatchFilterMatch);
      return DASHBOARD.volumetrics.periods.map((period) => ({
        label: period.period_label,
        batch_created: sum(rows.filter((row) => row.period_key === period.period_key), "incident_batch_created_count")
      }));
    }
    function splitWindowText() {
      const window = DASHBOARD.volumetrics.detailed_volume_trends?.split_window || {};
      if (!window.start_month || !window.end_month) return "Uses the latest complete 6 months and excludes the current partial month.";
      return `Uses average monthly created volume for ${esc(window.start_month)} to ${esc(window.end_month)}.`;
    }
    function renderDetailedVolumeTrends() {
      const topVolume = topApplicationPoints({ topN: state.topVolumeN, batch: false });
      const topBatch = state.volTicketType === "sc_task"
        ? []
        : topApplicationPoints({ topN: state.topBatchN, batch: true });
      const batchTrend = state.volTicketType === "sc_task" ? [] : incidentBatchTrendPoints();
      const ticketUserPoints = ticketsPerUserPoints();
      const batchMessage = state.volTicketType === "sc_task"
        ? "Batch-related ticket charts are applicable only for Incidents. SC Task catalog item charts will be added separately."
        : "Batch-related charts are Incident-only and use Incident tickets within the selected filters.";
      return `
        <section class="chart-card panel full" data-commentary-key="top_high_volume_applications"><div class="chart-title-row"><div><h3>Top High-Volume Applications</h3><p class="muted">${rankingWindowText()}</p></div><div class="pattern-buttons">${topToggle("volume", state.topVolumeN)}</div></div><div class="chart-frame chart-stage">${horizontalBarChart(topVolume.map((row) => ({ label: row.label, value: row.created, displayLabel: row.displayLabel })), { title: "Top High-Volume Applications", legend: "Average monthly tickets", color: COLORS.teal, height: state.topVolumeN === "20" ? 820 : 520 })}</div></section>
        <section class="chart-card panel full" data-commentary-key="batch_related_incidents_created"><h3>Batch-related Incidents Created</h3><p class="muted">${esc(batchMessage)}</p><div class="chart-frame chart-stage">${state.volTicketType === "sc_task" ? `<p class="muted" style="padding:12px">${esc(batchMessage)}</p>` : barChart(batchTrend, [{ key: "batch_created", name: "Batch Created", color: COLORS.orange }], { width: 1040 })}</div></section>
        <section class="chart-card panel full" data-commentary-key="top_incident_batch_applications"><div class="chart-title-row"><div><h3>Top Applications with Incident Batch-Related Tickets</h3><p class="muted">${rankingWindowText()}</p></div><div class="pattern-buttons">${topToggle("batch", state.topBatchN)}</div></div><div class="chart-frame chart-stage">${state.volTicketType === "sc_task" ? `<p class="muted" style="padding:12px">${esc(batchMessage)}</p>` : paretoBarLineChart(topBatch, "Average Batch Created Count", "Average Batch Canceled Count")}</div></section>
        <section class="chart-card panel full" data-commentary-key="tickets_per_user_application"><div class="chart-title-row"><div><h3>Tickets per User per Month by Application</h3><p class="muted">Calculated as latest complete 6-month average monthly ticket volume divided by Active Users.</p></div><div class="pattern-buttons">${topToggle("tickets-user", state.ticketsPerUserN)}</div></div><div class="chart-frame chart-stage">${horizontalBarChart(ticketUserPoints, { title: "Tickets per User per Month by Application", legend: "Tickets per user per month", color: COLORS.purple, digits: 2, height: state.ticketsPerUserN === "20" ? 780 : 500, emptyMessage: "No applications with non-zero Active Users are available." })}</div></section>
        ${scTaskCatalogSection()}
        <div class="chart-grid-three">
          ${distributionPieSection("Average Monthly Tickets by SAP / Non-SAP", "sap_non_sap", "all")}
          ${distributionPieSection("Average Monthly Incidents by SAP / Non-SAP", "sap_non_sap", "incident")}
          ${distributionPieSection("Average Monthly SC Tasks by SAP / Non-SAP", "sap_non_sap", "sc_task")}
        </div>
        ${commentaryMarkup({ ...currentVolumetricsCommentaryContext(), chart_key: "sap_non_sap_distribution_row" })}
        <div class="chart-grid-three">
          ${distributionPieSection("Average Monthly Tickets by Architecture Type", "architecture_type", "all")}
          ${distributionPieSection("Average Monthly Incidents by Architecture Type", "architecture_type", "incident")}
          ${distributionPieSection("Average Monthly SC Tasks by Architecture Type", "architecture_type", "sc_task")}
        </div>
        ${commentaryMarkup({ ...currentVolumetricsCommentaryContext(), chart_key: "architecture_type_distribution_row" })}
        <div class="chart-grid-three">
          ${distributionPieSection("Average Monthly Tickets by Install Type", "install_type", "all")}
          ${distributionPieSection("Average Monthly Incidents by Install Type", "install_type", "incident")}
          ${distributionPieSection("Average Monthly SC Tasks by Install Type", "install_type", "sc_task")}
        </div>
        ${commentaryMarkup({ ...currentVolumetricsCommentaryContext(), chart_key: "install_type_distribution_row" })}
        <div class="chart-grid-three">
          ${distributionPieSection("Average Monthly Tickets by Hosting Env", "hosting_env", "all")}
          ${distributionPieSection("Average Monthly Incidents by Hosting Env", "hosting_env", "incident")}
          ${distributionPieSection("Average Monthly SC Tasks by Hosting Env", "hosting_env", "sc_task")}
        </div>
        ${commentaryMarkup({ ...currentVolumetricsCommentaryContext(), chart_key: "hosting_env_distribution_row" })}
      `;
    }
    function truncateLabel(value, maxLength = 28) {
      const text = String(value || "");
      return text.length > maxLength ? `${text.slice(0, maxLength - 1)}…` : text;
    }
    function paretoBarLineChart(data, createdName, canceledName) {
      if (!data.length) return `<p class="muted" style="padding:12px">No chart data available.</p>`;
      const width = 1100;
      const height = 430;
      const margin = { top: 58, right: 72, bottom: 132, left: 44 };
      const plotWidth = width - margin.left - margin.right;
      const plotHeight = height - margin.top - margin.bottom;
      const maxValue = Math.max(1, ...data.flatMap((row) => [Number(row.created || 0), Number(row.canceled || 0)]));
      const groupWidth = plotWidth / Math.max(1, data.length);
      const barWidth = Math.max(8, Math.min(26, (groupWidth - 12) / 2));
      const bars = [];
      const linePoints = [];
      data.forEach((row, index) => {
        const groupCenter = margin.left + index * groupWidth + groupWidth / 2;
        const createdHeight = (Number(row.created || 0) / maxValue) * plotHeight;
        const canceledHeight = (Number(row.canceled || 0) / maxValue) * plotHeight;
        const createdX = groupCenter - barWidth - 2;
        const canceledX = groupCenter + 2;
        const createdY = margin.top + plotHeight - createdHeight;
        const canceledY = margin.top + plotHeight - canceledHeight;
        bars.push(`<rect x="${createdX}" y="${createdY}" width="${barWidth}" height="${createdHeight}" fill="${COLORS.teal}" rx="3"></rect>`);
        bars.push(`<rect x="${canceledX}" y="${canceledY}" width="${barWidth}" height="${canceledHeight}" fill="${COLORS.red}" rx="3"></rect>`);
        if (row.created > 0) bars.push(`<text x="${createdX + barWidth / 2}" y="${Math.max(margin.top + 12, createdY - 7)}" text-anchor="middle" font-size="10" font-weight="800" fill="#334155">${rounded(row.created)}</text>`);
        if (row.canceled > 0) bars.push(`<text x="${canceledX + barWidth / 2}" y="${Math.max(margin.top + 12, canceledY - 7)}" text-anchor="middle" font-size="10" font-weight="800" fill="#334155">${rounded(row.canceled)}</text>`);
        const paretoY = row.pareto === null ? null : margin.top + plotHeight - (Number(row.pareto) / 100) * plotHeight;
        if (paretoY !== null) linePoints.push({ x: groupCenter, y: paretoY, pct: row.pareto });
      });
      const linePath = linePoints.map((point, index) => `${index ? "L" : "M"}${point.x},${point.y}`).join(" ");
      const labels = data.map((row, index) => {
        const x = margin.left + index * groupWidth + groupWidth / 2;
        return `<text x="${x}" y="${height - 50}" text-anchor="end" transform="rotate(-38 ${x} ${height - 50})" font-size="10" font-weight="800" fill="#334155"><title>${esc(row.label)}</title>${esc(truncateLabel(row.label))}</text>`;
      });
      return `<svg class="chart-svg" viewBox="0 0 ${width} ${height}" preserveAspectRatio="xMidYMid meet" role="img" aria-label="Top applications Pareto chart">
        <line x1="${margin.left}" y1="${margin.top + plotHeight}" x2="${width - margin.right}" y2="${margin.top + plotHeight}" stroke="#64748b"></line>
        <text x="${width - margin.right + 20}" y="${margin.top}" text-anchor="middle" font-size="10" font-weight="900" fill="${COLORS.purple}">100%</text>
        ${bars.join("")}
        <path d="${linePath}" fill="none" stroke="${COLORS.purple}" stroke-width="3"></path>
        ${linePoints.map((point) => `<circle cx="${point.x}" cy="${point.y}" r="4" fill="#fff" stroke="${COLORS.purple}" stroke-width="2"></circle><text x="${point.x}" y="${Math.max(margin.top + 12, point.y - 10)}" text-anchor="middle" font-size="11" font-weight="900" fill="${COLORS.purple}" stroke="#fff" stroke-width="3" paint-order="stroke">${point.pct.toFixed(0)}%</text>`).join("")}
        ${labels.join("")}
      </svg>${legend([{ name: createdName, color: COLORS.teal }, { name: canceledName, color: COLORS.red }, { name: "Pareto cumulative %", color: COLORS.purple }])}`;
    }
    const MTTR_LABEL_START_INDEX = { P1: 0, P2: 1, P3: 2, P4: 3 };
    const MTTR_PRIORITY_COLORS = { P1: COLORS.blue, P2: COLORS.orange, P3: COLORS.teal, P4: COLORS.purple };
    function kpiFilterMatch(row, ticketType) {
      return (
        row.ticket_type === ticketType &&
        (state.volScope === "all" || row.scope === state.volScope) &&
        (state.volFunctional === "all" || row.functional_track_ams_owner === state.volFunctional) &&
        (state.volSap === "all" || row.sap_non_sap === state.volSap) &&
        (state.volBusinessCritical === "all" || row.business_critical === state.volBusinessCritical)
      );
    }
    function mttrShowLabel(priority, index) {
      const startIndex = MTTR_LABEL_START_INDEX[priority] || 0;
      return index >= startIndex && (index - startIndex) % 3 === 0;
    }
    function mttrPoints(ticketType, priority) {
      const rows = (DASHBOARD.volumetrics.kpi_trends?.mttr?.rows || [])
        .filter((row) => kpiFilterMatch(row, ticketType) && row.priority === priority);
      const totals = new Map();
      rows.forEach((row) => {
        const current = totals.get(row.period_key) || { seconds: 0, count: 0 };
        current.seconds += Number(row.business_duration_seconds_sum || 0);
        current.count += Number(row.ticket_count || 0);
        totals.set(row.period_key, current);
      });
      return DASHBOARD.volumetrics.periods.map((period, index) => {
        const values = totals.get(period.period_key) || { seconds: 0, count: 0 };
        const point = {
          label: period.period_label,
          period_key: period.period_key,
          mttr: values.count ? values.seconds / values.count / 86400 : null,
          ticket_count: values.count,
          show_label: values.count > 0 && mttrShowLabel(priority, index),
        };
        point.label_text = point.show_label ? `${fmt(point.mttr, 1)}d\\nn=${fmt(point.ticket_count)}` : "";
        return point;
      });
    }
    function mttrCombinedLineChart(ticketType, priorities, title) {
      const width = 1040;
      const height = 340;
      const margin = { top: 46, right: 52, bottom: 76, left: 58 };
      const plotWidth = width - margin.left - margin.right;
      const plotHeight = height - margin.top - margin.bottom;
      const series = priorities.map((priority) => ({ priority, data: mttrPoints(ticketType, priority) }));
      const values = series.flatMap((item) => item.data.map((row) => row.mttr)).filter((value) => value !== null);
      if (!values.length) return `<p class="muted" style="padding:12px">No MTTR data available.</p>`;
      const maxValue = Math.max(1, ...values);
      const dataLength = Math.max(...series.map((item) => item.data.length), 1);
      const xAt = (index) => margin.left + (plotWidth * index) / Math.max(1, dataLength - 1);
      const yAt = (value) => margin.top + plotHeight - (Number(value || 0) / maxValue) * plotHeight;
      const gridLines = Array.from({ length: 4 }, (_, index) => {
        const y = margin.top + (plotHeight * index) / 3;
        return `<line x1="${margin.left}" y1="${y}" x2="${width - margin.right}" y2="${y}" stroke="#e2e8f0"></line>`;
      }).join("");
      const labels = series.flatMap((item, seriesIndex) => {
        const offset = seriesIndex === 0 ? -18 : 20;
        return item.data.map((row, index) => ({ x: xAt(index), y: row.mttr === null ? null : yAt(row.mttr), row, offset }))
          .filter((point) => point.row.show_label && point.y !== null)
          .map((point) => {
            const y = Math.max(margin.top + 12, point.y + point.offset);
            const parts = String(point.row.label_text || "").split("\\n");
            return `<text x="${point.x}" y="${y}" text-anchor="middle" font-size="10" font-weight="900" fill="#334155" stroke="#fff" stroke-width="3" paint-order="stroke">${parts.map((part, index) => `<tspan x="${point.x}" dy="${index === 0 ? 0 : 12}">${esc(part)}</tspan>`).join("")}</text>`;
          });
      }).join("");
      const seriesMarkup = series.map((item) => {
        const points = item.data.map((row, index) => ({ x: xAt(index), y: row.mttr === null ? null : yAt(row.mttr), row }));
        const linePath = points.filter((point) => point.y !== null).map((point, index) => `${index ? "L" : "M"}${point.x},${point.y}`).join(" ");
        const color = MTTR_PRIORITY_COLORS[item.priority] || COLORS.blue;
        return `<path d="${linePath}" fill="none" stroke="${color}" stroke-width="3"></path>
          ${points.filter((point) => point.y !== null).map((point) => `<circle cx="${point.x}" cy="${point.y}" r="4" fill="#fff" stroke="${color}" stroke-width="2"><title>${esc(item.priority)} MTTR ${fmt(point.row.mttr, 2)} days, n=${fmt(point.row.ticket_count)}</title></circle>`).join("")}`;
      }).join("");
      const axisLabels = (series[0]?.data || []).map((row, index) => {
        const x = xAt(index);
        return `<text x="${x}" y="${height - 36}" text-anchor="end" transform="rotate(-35 ${x} ${height - 36})" font-size="10" font-weight="700" fill="#475569">${esc(row.label)}</text>`;
      }).join("");
      return `<svg class="chart-svg" viewBox="0 0 ${width} ${height}" preserveAspectRatio="xMidYMid meet" role="img" aria-label="${esc(title)}">
        ${gridLines}
        <line x1="${margin.left}" y1="${margin.top}" x2="${margin.left}" y2="${margin.top + plotHeight}" stroke="#94a3b8"></line>
        <line x1="${margin.left}" y1="${margin.top + plotHeight}" x2="${width - margin.right}" y2="${margin.top + plotHeight}" stroke="#64748b"></line>
        <text x="18" y="${margin.top + plotHeight / 2}" transform="rotate(-90 18 ${margin.top + plotHeight / 2})" font-size="11" font-weight="800" fill="#334155">MTTR days</text>
        ${seriesMarkup}
        ${labels}
        ${axisLabels}
      </svg>${legend(priorities.map((priority) => ({ name: `${priority} MTTR`, color: MTTR_PRIORITY_COLORS[priority] || COLORS.blue })))}`;
    }
    function mttrGroup(title, ticketType) {
      const notApplicable = state.volTicketType !== "all" && state.volTicketType !== ticketType;
      if (notApplicable) {
        return `<section class="panel full"><h3>${esc(title)}</h3><p class="muted">This MTTR group is not applicable for the selected ticket type.</p></section>`;
      }
      const prefix = ticketType === "incident" ? "Incident" : "SC Task";
      return `<section class="panel full"><p class="label">KPI Trends</p><h3>${esc(title)}</h3><div class="kpi-stack">
        <section class="chart-card panel full"><h3>${esc(prefix)} P1 / P2 MTTR</h3><p class="muted">Average business duration in days. Labels show MTTR days and ticket count.</p><div class="chart-frame chart-stage">${mttrCombinedLineChart(ticketType, ["P1", "P2"], `${prefix} P1 / P2 MTTR`)}</div></section>
        <section class="chart-card panel full"><h3>${esc(prefix)} P3 / P4 MTTR</h3><p class="muted">Average business duration in days. Labels show MTTR days and ticket count.</p><div class="chart-frame chart-stage">${mttrCombinedLineChart(ticketType, ["P3", "P4"], `${prefix} P3 / P4 MTTR`)}</div></section>
      </div></section>`;
    }
    function durationRows(ticketType) {
      const source = DASHBOARD.volumetrics.kpi_trends?.duration_buckets || {};
      const buckets = source.buckets || ["0-1 day", "1-3 days", "3-10 days", ">10 days"];
      return (source.periods || []).map((period) => {
        const matching = (source.rows || []).filter((row) => kpiFilterMatch(row, ticketType) && row.period_key === period.period_key);
        return {
          label: period.period_label,
          period_key: period.period_key,
          buckets: buckets.map((bucket) => ({
            label: bucket,
            count: sum(matching.filter((row) => row.bucket === bucket), "ticket_count")
          }))
        };
      });
    }
    function durationBucketChart(row) {
      return `<section class="chart-card panel" data-commentary-skip="true"><h3>${esc(row.label)}</h3><div class="chart-frame chart-stage">${barChart(row.buckets, [{ key: "count", name: "Tickets", color: COLORS.purple }], { width: 520, height: 340, durationBucketChart: true })}</div></section>`;
    }
    function durationGroup(title, ticketType) {
      const notApplicable = state.volTicketType !== "all" && state.volTicketType !== ticketType;
      if (notApplicable) {
        return `<section class="panel full"><h3>${esc(title)}</h3><p class="muted">This duration group is not applicable for the selected ticket type.</p></section>`;
      }
      const commentaryKey = ticketType === "incident" ? "incident_duration_buckets_row" : "sc_task_duration_buckets_row";
      return `<section class="panel full"><p class="label">Duration Buckets</p><h3>${esc(title)}</h3><div class="duration-grid">${durationRows(ticketType).map(durationBucketChart).join("")}</div>${commentaryMarkup({ ...currentVolumetricsCommentaryContext(), chart_key: commentaryKey })}</section>`;
    }
    function reassignmentHopsPoints() {
      const rows = (DASHBOARD.volumetrics.kpi_trends?.reassignment_hops?.rows || []).filter(offlineFilterMatch);
      const totals = new Map();
      rows.forEach((row) => {
        const current = totals.get(row.period_key) || { created: 0, tickets: 0, hops: 0 };
        current.created += Number(row.total_created_tickets || 0);
        current.tickets += Number(row.tickets_with_2_plus_reassignments || 0);
        current.hops += Number(row.total_reassignment_hops_ge_2 || 0);
        totals.set(row.period_key, current);
      });
      return DASHBOARD.volumetrics.periods.map((period) => {
        const values = totals.get(period.period_key) || { created: 0, tickets: 0, hops: 0 };
        return {
          label: period.period_label,
          period_key: period.period_key,
          created: values.created,
          tickets: values.tickets,
          hops: values.hops,
          ticketPct: values.created ? (values.tickets / values.created) * 100 : null,
          hopsPct: values.created ? (values.hops / values.created) * 100 : null
        };
      });
    }
    function reassignmentHopsLineChart(data) {
      if (!data.length) return `<p class="muted" style="padding:12px">No reassignment data available.</p>`;
      const width = 1040;
      const height = 380;
      const margin = { top: 58, right: 76, bottom: 82, left: 64 };
      const plotWidth = width - margin.left - margin.right;
      const plotHeight = height - margin.top - margin.bottom;
      const ticketMax = Math.max(1, ...data.map((row) => Number(row.tickets || 0)));
      const pctMax = Math.max(1, ...data.map((row) => Number(row.hopsPct || 0)));
      const xAt = (index) => margin.left + (plotWidth * index) / Math.max(1, data.length - 1);
      const ticketY = (value) => margin.top + plotHeight - (Number(value || 0) / ticketMax) * plotHeight;
      const pctY = (value) => margin.top + plotHeight - (Number(value || 0) / pctMax) * plotHeight;
      const ticketPoints = data.map((row, index) => ({ x: xAt(index), y: ticketY(row.tickets), value: row.tickets }));
      const pctPoints = data.map((row, index) => ({ x: xAt(index), y: row.hopsPct === null ? null : pctY(row.hopsPct), value: row.hopsPct }));
      const ticketPath = ticketPoints.map((point, index) => `${index ? "L" : "M"}${point.x},${point.y}`).join(" ");
      const pctPath = pctPoints.filter((point) => point.y !== null).map((point, index) => `${index ? "L" : "M"}${point.x},${point.y}`).join(" ");
      const gridLines = Array.from({ length: 4 }, (_, index) => {
        const y = margin.top + (plotHeight * index) / 3;
        return `<line x1="${margin.left}" y1="${y}" x2="${width - margin.right}" y2="${y}" stroke="#e2e8f0"></line>`;
      }).join("");
      const axisLabels = data.map((row, index) => {
        const x = xAt(index);
        return `<text x="${x}" y="${height - 38}" text-anchor="end" transform="rotate(-35 ${x} ${height - 38})" font-size="10" font-weight="700" fill="#475569">${esc(row.label)}</text>`;
      }).join("");
      return `<svg class="chart-svg" viewBox="0 0 ${width} ${height}" preserveAspectRatio="xMidYMid meet" role="img" aria-label="Reassignment hops trend">
        ${gridLines}
        <line x1="${margin.left}" y1="${margin.top}" x2="${margin.left}" y2="${margin.top + plotHeight}" stroke="#94a3b8"></line>
        <line x1="${width - margin.right}" y1="${margin.top}" x2="${width - margin.right}" y2="${margin.top + plotHeight}" stroke="#94a3b8"></line>
        <line x1="${margin.left}" y1="${margin.top + plotHeight}" x2="${width - margin.right}" y2="${margin.top + plotHeight}" stroke="#64748b"></line>
        <text x="18" y="${margin.top + plotHeight / 2}" transform="rotate(-90 18 ${margin.top + plotHeight / 2})" font-size="11" font-weight="800" fill="#334155">Tickets with 2+ reassignments</text>
        <text x="${width - 18}" y="${margin.top + plotHeight / 2}" transform="rotate(90 ${width - 18} ${margin.top + plotHeight / 2})" font-size="11" font-weight="800" fill="#334155">Hops % of created</text>
        <path d="${ticketPath}" fill="none" stroke="${COLORS.teal}" stroke-width="3"></path>
        <path d="${pctPath}" fill="none" stroke="${COLORS.purple}" stroke-width="3"></path>
        ${ticketPoints.map((point) => `<circle cx="${point.x}" cy="${point.y}" r="4" fill="#fff" stroke="${COLORS.teal}" stroke-width="2"></circle><text x="${point.x}" y="${Math.max(margin.top + 12, point.y - 12)}" text-anchor="middle" font-size="10" font-weight="900" fill="#334155" stroke="#fff" stroke-width="3" paint-order="stroke">${fmt(point.value)}</text>`).join("")}
        ${pctPoints.filter((point) => point.y !== null).map((point) => `<circle cx="${point.x}" cy="${point.y}" r="4" fill="#fff" stroke="${COLORS.purple}" stroke-width="2"></circle><text x="${point.x}" y="${Math.min(margin.top + plotHeight + 28, point.y + 22)}" text-anchor="middle" font-size="10" font-weight="900" fill="${COLORS.purple}" stroke="#fff" stroke-width="3" paint-order="stroke">${Number(point.value || 0).toFixed(1)}%</text>`).join("")}
        ${axisLabels}
      </svg>${legend([{ name: "Tickets with 2+ reassignments", color: COLORS.teal }, { name: "Hops % of created", color: COLORS.purple }])}`;
    }
    function reassignmentHopsTable(data) {
      return `<div class="table-card"><div class="table-scroll"><table class="applications-table"><thead><tr><th>Month</th><th>Total Created Tickets</th><th>Tickets with 2+ Reassignments</th><th>Total Reassignment Hops for 2+ Reassignment Tickets</th><th>% Tickets with 2+ Reassignments</th><th>% Reassignment Hops to Created Volume</th></tr></thead><tbody>${data.map((row) => `<tr><td>${esc(row.label)}</td><td>${fmt(row.created)}</td><td>${fmt(row.tickets)}</td><td>${fmt(row.hops)}</td><td>${row.ticketPct === null ? "N/A" : `${row.ticketPct.toFixed(1)}%`}</td><td>${row.hopsPct === null ? "N/A" : `${row.hopsPct.toFixed(1)}%`}</td></tr>`).join("")}</tbody></table></div></div>`;
    }
    function reassignmentHopsGroup() {
      const points = reassignmentHopsPoints();
      return `<section class="panel full" data-commentary-key="reassignment_hops_trend"><p class="label">KPI Trends</p><h3>Reassignment / Hops Trend</h3><p class="muted">Tickets with 2+ reassignments indicate handoffs between support teams. The percentage shows reassignment hops as a share of monthly created ticket volume.</p><section class="chart-card panel full"><h3>Monthly Reassignment / Hops Trend</h3><p class="muted">Generic Tickets includes Incidents and SC Tasks only. Problems and Changes are excluded.</p><div class="chart-frame chart-stage">${reassignmentHopsLineChart(points)}</div>${reassignmentHopsTable(points)}</section>${commentaryMarkup({ ...currentVolumetricsCommentaryContext(), chart_key: "reassignment_hops_trend" })}</section>`;
    }
    function problemFilterMatch(row) {
      return (
        (state.volScope === "all" || row.scope === state.volScope) &&
        (state.volFunctional === "all" || row.functional_track_ams_owner === state.volFunctional) &&
        (state.volSap === "all" || row.sap_non_sap === state.volSap)
      );
    }
    function problemManagementPoints() {
      const rows = (DASHBOARD.volumetrics.kpi_trends?.problem_management?.rows || []).filter(problemFilterMatch);
      const totals = new Map();
      rows.forEach((row) => {
        const current = totals.get(row.period_key) || { created: 0, closed: 0, linked: 0 };
        current.created += Number(row.problem_tickets_created || 0);
        current.closed += Number(row.problem_tickets_closed || 0);
        current.linked += Number(row.linked_incidents_resolved_permanently || 0);
        totals.set(row.period_key, current);
      });
      return DASHBOARD.volumetrics.periods.map((period) => {
        const values = totals.get(period.period_key) || { created: 0, closed: 0, linked: 0 };
        return {
          label: period.period_label,
          period_key: period.period_key,
          created: values.created,
          closed: values.closed,
          linked: values.linked,
          avgLinked: values.closed ? values.linked / values.closed : null
        };
      });
    }
    function problemManagementChart(data) {
      if (!data.length) return `<p class="muted" style="padding:12px">No Problem Management data available.</p>`;
      const width = 1040;
      const height = 420;
      const margin = { top: 58, right: 84, bottom: 82, left: 64 };
      const plotWidth = width - margin.left - margin.right;
      const plotHeight = height - margin.top - margin.bottom;
      const problemMax = Math.max(1, ...data.map((row) => Math.max(Number(row.created || 0), Number(row.closed || 0))));
      const linkedMax = Math.max(1, ...data.map((row) => Number(row.linked || 0)));
      const useSecondary = linkedMax > 0 && (problemMax === 0 || linkedMax >= problemMax * 3);
      const linkedScaleMax = useSecondary ? linkedMax : Math.max(problemMax, linkedMax);
      const problemScaleMax = useSecondary ? problemMax : Math.max(problemMax, linkedMax);
      const step = plotWidth / Math.max(1, data.length);
      const barWidth = Math.min(24, Math.max(8, step / 5));
      const xAt = (index) => margin.left + step * index + step / 2;
      const problemY = (value) => margin.top + plotHeight - (Number(value || 0) / problemScaleMax) * plotHeight;
      const linkedY = (value) => margin.top + plotHeight - (Number(value || 0) / linkedScaleMax) * plotHeight;
      const linePoints = data.map((row, index) => ({ x: xAt(index), y: linkedY(row.linked), value: row.linked }));
      const linePath = linePoints.map((point, index) => `${index ? "L" : "M"}${point.x},${point.y}`).join(" ");
      const gridLines = Array.from({ length: 4 }, (_, index) => {
        const y = margin.top + (plotHeight * index) / 3;
        return `<line x1="${margin.left}" y1="${y}" x2="${width - margin.right}" y2="${y}" stroke="#e2e8f0"></line>`;
      }).join("");
      const bars = data.map((row, index) => {
        const x = xAt(index);
        const createdY = problemY(row.created);
        const closedY = problemY(row.closed);
        const createdHeight = margin.top + plotHeight - createdY;
        const closedHeight = margin.top + plotHeight - closedY;
        return `<rect x="${x - barWidth - 2}" y="${createdY}" width="${barWidth}" height="${createdHeight}" rx="4" fill="${COLORS.teal}"></rect><text x="${x - barWidth / 2 - 2}" y="${Math.max(margin.top + 12, createdY - 8)}" text-anchor="middle" font-size="10" font-weight="900" fill="#334155" stroke="#fff" stroke-width="3" paint-order="stroke">${fmt(row.created)}</text><rect x="${x + 2}" y="${closedY}" width="${barWidth}" height="${closedHeight}" rx="4" fill="${COLORS.blue}"></rect><text x="${x + barWidth / 2 + 2}" y="${Math.max(margin.top + 12, closedY - 8)}" text-anchor="middle" font-size="10" font-weight="900" fill="#334155" stroke="#fff" stroke-width="3" paint-order="stroke">${fmt(row.closed)}</text>`;
      }).join("");
      const axisLabels = data.map((row, index) => {
        const x = xAt(index);
        return `<text x="${x}" y="${height - 38}" text-anchor="end" transform="rotate(-35 ${x} ${height - 38})" font-size="10" font-weight="700" fill="#475569">${esc(row.label)}</text>`;
      }).join("");
      return `<svg class="chart-svg" viewBox="0 0 ${width} ${height}" preserveAspectRatio="xMidYMid meet" role="img" aria-label="Problem Management trend">
        ${gridLines}
        <line x1="${margin.left}" y1="${margin.top}" x2="${margin.left}" y2="${margin.top + plotHeight}" stroke="#94a3b8"></line>
        ${useSecondary ? `<line x1="${width - margin.right}" y1="${margin.top}" x2="${width - margin.right}" y2="${margin.top + plotHeight}" stroke="#94a3b8"></line>` : ""}
        <line x1="${margin.left}" y1="${margin.top + plotHeight}" x2="${width - margin.right}" y2="${margin.top + plotHeight}" stroke="#64748b"></line>
        <text x="18" y="${margin.top + plotHeight / 2}" transform="rotate(-90 18 ${margin.top + plotHeight / 2})" font-size="11" font-weight="800" fill="#334155">Problem ticket count</text>
        ${useSecondary ? `<text x="${width - 18}" y="${margin.top + plotHeight / 2}" transform="rotate(90 ${width - 18} ${margin.top + plotHeight / 2})" font-size="11" font-weight="800" fill="#334155">Linked incident count</text>` : ""}
        ${bars}
        <path d="${linePath}" fill="none" stroke="${COLORS.orange}" stroke-width="3"></path>
        ${linePoints.map((point) => `<circle cx="${point.x}" cy="${point.y}" r="4" fill="#fff" stroke="${COLORS.orange}" stroke-width="2"></circle><text x="${point.x}" y="${Math.max(margin.top + 12, point.y - 14)}" text-anchor="middle" font-size="10" font-weight="900" fill="#334155" stroke="#fff" stroke-width="3" paint-order="stroke">${fmt(point.value)}</text>`).join("")}
        ${axisLabels}
      </svg>${legend([{ name: "Problem Tickets Created", color: COLORS.teal }, { name: "Problem Tickets Closed", color: COLORS.blue }, { name: "Linked Incidents Resolved Permanently", color: COLORS.orange }])}`;
    }
    function problemManagementTable(data) {
      return `<div class="table-card"><div class="table-scroll"><table class="applications-table"><thead><tr><th>Month</th><th>Problem Tickets Created</th><th>Problem Tickets Closed</th><th>Linked Incidents Resolved Permanently</th><th>Avg Linked Incidents per Closed Problem</th></tr></thead><tbody>${data.map((row) => `<tr><td>${esc(row.label)}</td><td>${fmt(row.created)}</td><td>${fmt(row.closed)}</td><td>${fmt(row.linked)}</td><td>${row.avgLinked === null ? "N/A" : fmt(row.avgLinked, 2)}</td></tr>`).join("")}</tbody></table></div></div>`;
    }
    function problemManagementGroup() {
      const points = problemManagementPoints();
      return `<section class="panel full" data-commentary-key="problem_management_trend"><p class="label">KPI Trends</p><h3>Problem Management Trend</h3><p class="muted">Shows Problem tickets created and closed by month, plus linked Incidents expected to be permanently resolved through closed Problems.</p><section class="chart-card panel full"><h3>Monthly Problem Management Trend</h3><p class="muted">Problem records are analyzed separately. The selected scope is applied to Problem records by Application Inventory assignment group.</p><div class="chart-frame chart-stage">${problemManagementChart(points)}</div>${problemManagementTable(points)}</section>${commentaryMarkup({ ...currentVolumetricsCommentaryContext(), chart_key: "problem_management_trend" })}</section>`;
    }
    function renderKpiTrends() {
      return `
        ${mttrGroup("Incident MTTR by Priority", "incident")}
        ${mttrGroup("SC Task MTTR by Priority", "sc_task")}
        ${reassignmentHopsGroup()}
        ${problemManagementGroup()}
        ${durationGroup("Incident Resolved Volume by Resolution Duration", "incident")}
        ${durationGroup("SC Task Closed Volume by Closed Duration", "sc_task")}
      `;
    }
    function placeholder(title) {
      return `<section class="panel" style="padding:18px"><p class="label">${esc(title)}</p><h3>Detailed requirements for this section will be added in the next prompts.</h3></section>`;
    }
    function renderOverallVolume(periods) {
      const totalCreated = sum(periods, "created");
      const totalResolved = sum(periods, "resolved");
      const totalCanceled = sum(periods, "canceled");
      const responsePercentages = periods.filter((row) => row.responseTotal > 0).map((row) => (row.responseMet / row.responseTotal) * 100);
      const resolutionPercentages = periods.filter((row) => row.resolutionTotal > 0).map((row) => (row.resolutionMet / row.resolutionTotal) * 100);
      const responseAverage = state.volTicketType === "sc_task" ? null : average(responsePercentages);
      const resolutionAverage = state.volTicketType === "sc_task" ? null : average(resolutionPercentages);
      return `
        <div class="summary-grid cards-grid">
          ${tile("Created", `Total: ${fmt(totalCreated)}`, `Avg monthly: ${fmt(totalCreated / Math.max(1, periods.length))}`, 0, 5)}
          ${tile("Resolved / Closed", `Total: ${fmt(totalResolved)}`, `Avg monthly: ${fmt(totalResolved / Math.max(1, periods.length))}`, 1, 5)}
          ${tile("Canceled / Closed Incomplete", `Total: ${fmt(totalCanceled)}`, `% of Resolved+Canceled: ${pct(totalCanceled, totalResolved + totalCanceled)}`, 2, 5)}
          ${tile("Response SLA", responseAverage === null ? "N/A" : `${responseAverage.toFixed(1)}%`, "Avg monthly adherence", 3, 5)}
          ${tile("Resolution SLA", resolutionAverage === null ? "N/A" : `${resolutionAverage.toFixed(1)}%`, "Avg monthly adherence", 4, 5)}
        </div>
        <section class="chart-card panel full" data-commentary-key="created_resolved_canceled"><h3>Created vs Resolved/Closed vs Canceled / Closed Incomplete</h3><div class="chart-frame chart-stage">${barChart(periods, [{ key: "created", name: "Created", color: COLORS.teal }, { key: "resolved", name: "Resolved/Closed", color: COLORS.blue }, { key: "canceled", name: "Canceled", color: COLORS.red }], { width: 1040 })}</div></section>
        <section class="chart-card panel full" data-commentary-key="backlog"><h3>Backlog(Open)</h3><div class="chart-frame chart-stage">${lineChart(periods, "backlog", "average")}</div></section>
        <section class="chart-card panel full" data-commentary-key="created_pattern"><h3>Created Pattern</h3><p class="muted">Average created/opened tickets across the available monthly range.</p><div class="pattern-buttons">${patternButtons()}</div><div class="chart-frame chart-stage">${createdPatternChart()}</div></section>
        <section class="chart-card panel full" data-commentary-key="hourly_created_resolved"><h3>Created vs Resolved by hour of the day</h3><div class="pattern-buttons">${hourlyButtons()}</div><div class="chart-frame chart-stage">${hourlyCreatedResolvedChart()}</div></section>
        <section class="chart-card panel full" data-commentary-key="priority_distribution"><div class="chart-title-row"><h3>Priority-wise ticket distribution</h3><div class="pattern-buttons">${priorityToggle()}</div></div><div class="chart-frame chart-stage">${priorityDistributionContent()}</div></section>
      `;
    }
    function average(values) {
      return values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : null;
    }
    function patternButtons() {
      const labels = {
        day_of_month: "Created by day of month",
        day_of_week: "Created by day of week",
        hour_weekdays: "Created by hour - weekdays",
        hour_weekends: "Created by hour - weekends"
      };
      return Object.entries(labels).map(([value, label]) => `<button type="button" data-pattern="${esc(value)}" class="${state.pattern === value ? "active" : ""}">${esc(label)}</button>`).join("");
    }
    function createdPatternChart() {
      const buckets = DASHBOARD.volumetrics.created_patterns.buckets[state.pattern] || [];
      const rows = filteredPatternRows();
      const totals = new Map();
      rows.forEach((row) => totals.set(row.bucket_label, (totals.get(row.bucket_label) || 0) + row.total_created));
      const points = buckets.map((bucket) => ({
        label: bucket.label,
        average: bucket.denominator ? (totals.get(bucket.label) || 0) / bucket.denominator : 0
      }));
      return barChart(points, [{ key: "average", name: "Average Created", color: state.pattern.includes("hour") ? COLORS.purple : COLORS.teal }], { width: state.pattern === "day_of_month" ? 980 : 860, roundLabels: true });
    }
    function hourlyButtons() {
      const labels = { weekdays: "Weekdays", weekends: "Weekends" };
      return Object.entries(labels).map(([value, label]) => `<button type="button" data-hourly-day="${esc(value)}" class="${state.hourlyDayType === value ? "active" : ""}">${esc(label)}</button>`).join("");
    }
    function hourlyCreatedResolvedChart() {
      const rows = filteredHourlyRows();
      const totals = new Map();
      rows.forEach((row) => {
        const current = totals.get(row.hour) || { created: 0, resolved: 0 };
        current.created += Number(row.total_created || 0);
        current.resolved += Number(row.total_resolved_closed || 0);
        totals.set(row.hour, current);
      });
      const denominator = DASHBOARD.volumetrics.overall_volume_trends?.created_resolved_by_hour?.denominators?.[state.hourlyDayType] || 0;
      const points = Array.from({ length: 24 }, (_, hour) => {
        const label = String(hour).padStart(2, "0");
        const values = totals.get(label) || { created: 0, resolved: 0 };
        return {
          label,
          created: denominator ? values.created / denominator : 0,
          resolved: denominator ? values.resolved / denominator : 0
        };
      });
      return barChart(points, [{ key: "created", name: "Created", color: COLORS.teal }, { key: "resolved", name: "Resolved/Closed", color: COLORS.blue }], { width: 980, roundLabels: true });
    }
    function priorityToggle() {
      return ["graph", "table"].map((value) => `<button type="button" data-priority-view="${esc(value)}" class="${state.priorityView === value ? "active" : ""}">${value === "graph" ? "Graph" : "Data table"}</button>`).join("");
    }
    function priorityRank(label) {
      const normalized = String(label || "").toLowerCase();
      const pMatch = normalized.match(/\bp\s*([1-4])\b/);
      if (pMatch) return Number(pMatch[1]);
      const digitMatch = normalized.match(/\b([1-4])\b/);
      if (digitMatch) return Number(digitMatch[1]);
      if (normalized.includes("moderate") || normalized.includes("medium")) return 3;
      if (normalized.includes("low")) return 4;
      if (normalized.includes("critical")) return 1;
      if (normalized.includes("high")) return 2;
      return null;
    }
    function priorityLabelRequired(label) {
      const rank = priorityRank(label);
      return rank === 3 || rank === 4;
    }
    function priorityCellText(point, priority) {
      const count = Number(point.values[priority] || 0);
      const percentage = point.percentages?.[priority] ?? (point.total > 0 ? (count / point.total) * 100 : 0);
      return `${fmt(count)} (${Number(percentage || 0).toFixed(1)}%)`;
    }
    function priorityChartLabelParts(count, percentage) {
      return {
        count: fmt(count),
        percentage: `${Math.round(Number(percentage || 0))}%`
      };
    }
    function priorityDistributionContent() {
      const priorities = DASHBOARD.volumetrics.overall_volume_trends?.priority_distribution?.priorities || [];
      const rows = filteredPriorityRows();
      const periodRows = DASHBOARD.volumetrics.periods.map((period) => {
        const values = {};
        priorities.forEach((priority) => { values[priority] = 0; });
        rows.filter((row) => row.period_key === period.period_key).forEach((row) => {
          values[row.priority] = (values[row.priority] || 0) + Number(row.ticket_count || 0);
        });
        const total = priorities.reduce((sumValue, priority) => sumValue + (values[priority] || 0), 0);
        const percentages = {};
        priorities.forEach((priority) => {
          percentages[priority] = total > 0 ? (values[priority] / total) * 100 : 0;
        });
        return {
          label: period.period_label,
          values,
          percentages,
          total
        };
      });
      if (state.priorityView === "table") {
        return priorityDistributionTable(periodRows, priorities);
      }
      const series = priorities.map((priority, index) => ({ key: priority, name: priority, color: [COLORS.teal, COLORS.blue, COLORS.orange, COLORS.purple, COLORS.red, COLORS.slate][index % 6] }));
      return stackedBarChart(periodRows, series);
    }
    function priorityDistributionTable(points, priorities) {
      return `<div class="table-frame table-scroll"><table><thead><tr><th>Period</th>${priorities.map((priority) => `<th>${esc(priority)}</th>`).join("")}<th>Total</th></tr></thead><tbody>${points.map((point) => `<tr><td>${esc(point.label)}</td>${priorities.map((priority) => `<td>${priorityCellText(point, priority)}</td>`).join("")}<td>${fmt(point.total)}</td></tr>`).join("")}</tbody></table></div>`;
    }
    function stackedBarChart(data, series) {
      const width = 1040;
      const height = 360;
      const margin = { top: 42, right: 30, bottom: 86, left: 36 };
      const plotWidth = width - margin.left - margin.right;
      const plotHeight = height - margin.top - margin.bottom;
      const maxValue = Math.max(1, ...data.map((row) => Number(row.total || 0)));
      const groupWidth = plotWidth / Math.max(1, data.length);
      const barWidth = Math.max(12, Math.min(28, groupWidth * 0.52));
      const bars = [];
      data.forEach((row, index) => {
        let stackTop = margin.top + plotHeight;
        series.forEach((item) => {
          const value = Number(row.values[item.key] || 0);
          const barHeight = (value / maxValue) * plotHeight;
          const x = margin.left + index * groupWidth + (groupWidth - barWidth) / 2;
          const y = stackTop - barHeight;
          const segmentPct = row.percentages?.[item.key] ?? (row.total > 0 ? (value / row.total) * 100 : 0);
          if (value > 0) {
            bars.push(`<rect x="${x}" y="${y}" width="${barWidth}" height="${barHeight}" fill="${item.color}"><title>${esc(item.name)}: ${fmt(value)} (${segmentPct.toFixed(1)}%)</title></rect>`);
            if (priorityLabelRequired(item.name)) {
              const label = priorityChartLabelParts(value, segmentPct);
              const inside = barHeight >= 28 && barWidth >= 20;
              const labelY = inside ? y + barHeight / 2 - 5 : Math.max(margin.top + 14, y - 16);
              bars.push(`<text x="${x + barWidth / 2}" y="${labelY}" text-anchor="middle" font-size="9" font-weight="900" fill="${inside ? "#ffffff" : "#334155"}" stroke="${inside ? "none" : "#ffffff"}" stroke-width="${inside ? 0 : 3}" paint-order="stroke"><tspan x="${x + barWidth / 2}" dy="0">${esc(label.count)}</tspan><tspan x="${x + barWidth / 2}" dy="10">${esc(label.percentage)}</tspan></text>`);
            }
          }
          stackTop = y;
        });
      });
      const labels = data.map((row, index) => {
        const x = margin.left + index * groupWidth + groupWidth / 2;
        return `<text x="${x}" y="${height - 38}" text-anchor="end" transform="rotate(-35 ${x} ${height - 38})" font-size="10" font-weight="700" fill="#475569">${esc(row.label)}</text>`;
      });
      return `<svg class="chart-svg" viewBox="0 0 ${width} ${height}" preserveAspectRatio="xMidYMid meet" role="img" aria-label="Priority distribution">
        <line x1="${margin.left}" y1="${margin.top + plotHeight}" x2="${width - margin.right}" y2="${margin.top + plotHeight}" stroke="#64748b"></line>
        ${bars.join("")}${labels.join("")}
      </svg>${legend(series)}`;
    }
    function renderSlaTrends() {
      if (state.volTicketType === "sc_task") {
        return `<section class="panel" style="padding:18px"><p class="label">Overall SLA Trends</p><h3>SLA trends are not applicable for SC Tasks.</h3></section>`;
      }
      const rows = filteredSlaRows();
      const response = slaTrendPoints(rows, "response");
      const resolution = slaTrendPoints(rows, "resolution");
      const modeLabel = state.slaMode === "ola" ? "OLA" : "SLA";
      return `
        <section class="panel" style="padding:12px"><div class="segmented-control" role="group" aria-label="SLA mode">
          ${["sla", "ola"].map((mode) => `<button type="button" data-sla-mode="${mode}" class="${state.slaMode === mode ? "active" : ""}">${mode.toUpperCase()}</button>`).join("")}
        </div></section>
        <section class="chart-card panel full" data-commentary-key="response_sla_adherence"><h3>Response ${modeLabel} adherence trend</h3><p class="muted">Adherence = captured ${modeLabel} adhered count / captured ${modeLabel} count.</p><div class="chart-frame chart-stage">${slaLineChart(response, COLORS.teal, `Response ${modeLabel} adherence %`)}</div>${slaTrendTable(response, `Response ${modeLabel}`)}</section>
        <section class="chart-card panel full" data-commentary-key="resolution_sla_adherence"><h3>Resolution ${modeLabel} adherence trend</h3><p class="muted">Adherence = captured ${modeLabel} adhered count / captured ${modeLabel} count.</p><div class="chart-frame chart-stage">${slaLineChart(resolution, COLORS.blue, `Resolution ${modeLabel} adherence %`)}</div>${slaTrendTable(resolution, `Resolution ${modeLabel}`)}</section>
      `;
    }
    function slaTrendPoints(rows, kind) {
      return DASHBOARD.volumetrics.periods.map((period) => {
        const matching = rows.filter((row) => row.period_key === period.period_key);
        const totalClosed = sum(matching, "total_closed_ticket_count");
        const mode = state.slaMode === "ola" ? "ola" : "sla";
        const captured = sum(matching, `${kind}_${mode}_captured_count`);
        const adhered = sum(matching, `${kind}_${mode}_adhered_count`);
        return {
          label: period.period_label,
          totalClosed,
          captured,
          adhered,
          pct: captured > 0 ? (adhered / captured) * 100 : null
        };
      });
    }
    function slaLineChart(data, color, label) {
      const width = 1040;
      const height = 360;
      const margin = { top: 52, right: 34, bottom: 78, left: 44 };
      const plotWidth = width - margin.left - margin.right;
      const plotHeight = height - margin.top - margin.bottom;
      const values = data.map((row) => row.pct).filter((value) => value !== null);
      if (!values.length) return `<p class="muted" style="padding:12px">No SLA trend data available.</p>`;
      const points = data.map((row, index) => {
        const x = margin.left + (plotWidth * index) / Math.max(1, data.length - 1);
        const y = row.pct === null ? null : margin.top + plotHeight - (row.pct / 100) * plotHeight;
        return { x, y, row };
      });
      const path = points.filter((point) => point.y !== null).map((point, index) => `${index ? "L" : "M"}${point.x},${point.y}`).join(" ");
      return `<svg class="chart-svg" viewBox="0 0 ${width} ${height}" preserveAspectRatio="xMidYMid meet" role="img" aria-label="${esc(label)}">
        <line x1="${margin.left}" y1="${margin.top + plotHeight}" x2="${width - margin.right}" y2="${margin.top + plotHeight}" stroke="#64748b"></line>
        <path d="${path}" fill="none" stroke="${color}" stroke-width="3"></path>
        ${points.map((point) => point.y === null ? "" : `<circle cx="${point.x}" cy="${point.y}" r="4" fill="#fff" stroke="${color}" stroke-width="2"></circle><text x="${point.x}" y="${point.y - 9}" text-anchor="middle" font-size="10" fill="#475569">${point.row.pct.toFixed(1)}%</text>`).join("")}
        ${data.map((row, index) => {
          const x = margin.left + (plotWidth * index) / Math.max(1, data.length - 1);
          return `<text x="${x}" y="${height - 38}" text-anchor="end" transform="rotate(-35 ${x} ${height - 38})" font-size="10" font-weight="700" fill="#475569">${esc(row.label)}</text>`;
        }).join("")}
      </svg>${legend([{ name: label, color }])}`;
    }
    function slaTrendTable(rows, label) {
      return `<div class="table-frame table-scroll" style="margin-top:10px"><table><thead><tr><th>Duration</th><th>Total closed tickets</th><th>${esc(label)} captured</th><th>${esc(label)} adhered</th><th>${esc(label)} adherence %</th></tr></thead><tbody>${rows.map((row) => `<tr><td>${esc(row.label)}</td><td>${fmt(row.totalClosed)}</td><td>${fmt(row.captured)}</td><td>${fmt(row.adhered)}</td><td>${row.pct === null ? "N/A" : `${row.pct.toFixed(1)}%`}</td></tr>`).join("")}</tbody></table></div>`;
    }
    function renderCustomerLogo() {
      const logoUrl = DASHBOARD.metadata.customer_logo_data_url;
      document.getElementById("customer-logo").innerHTML = logoUrl
        ? `<img src="${esc(logoUrl)}" alt="${esc(DASHBOARD.metadata.customer_name)} logo">`
        : "";
    }
    function activateTab(tab) {
      state.tab = tab;
      document.querySelectorAll(".tab").forEach((button) => button.classList.toggle("active", button.dataset.tab === tab));
      document.querySelectorAll(".view").forEach((view) => view.classList.toggle("active", view.id === tab));
    }
    function initialize() {
      if (!DASHBOARD) {
        renderFatalDashboardError("The offline dashboard data could not be loaded.");
        return;
      }
      document.getElementById("page-title").textContent = "AMS Applications & Volumetric Analysis";
      document.getElementById("export-meta").innerHTML = `Exported: ${dateTimeText(DASHBOARD.metadata.exported_at)}<br>Monthly offline dashboard`;
      renderCustomerLogo();
      document.querySelectorAll(".tab").forEach((button) => button.addEventListener("click", () => activateTab(button.dataset.tab)));
      document.getElementById("download-edited-dashboard")?.addEventListener("click", downloadUpdatedOfflineDashboard);
      safeRenderSection("overview", "Overview", renderOverview);
      safeRenderSection("applications", "Applications", renderApplications);
      safeRenderSection("volumetrics", "Volumetrics & SLA", renderVolumetrics);
    }
    initialize();
  </script>
</body>
</html>
"""
