# ruff: noqa: E501

from __future__ import annotations

import calendar
import html
import json
import re
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from uuid import UUID

from sqlalchemy import Integer, case, cast, func, literal, select, union_all
from sqlalchemy.orm import Session

from app.models import (
    ApplicationInventoryItem,
    AssessmentOutOfScopeTicket,
    Client,
    Project,
    Ticket,
)
from app.services.dashboard import (
    APPLICATION_LIST_FIELDS,
    BLANK_LABEL,
    VOLUMETRICS_SCOPE_LABELS,
    VOLUMETRICS_TICKET_TYPE_LABELS,
    application_display_expression,
    applications_charts,
    applications_summary,
    build_volumetrics_periods,
    combined_volumetrics_display_expression,
    date_counts_by_day_of_month,
    date_counts_by_weekday,
    day_count_for_week_part,
    normalize_dashboard_datetime,
    overview_summary,
    priority_sort_key,
    volumetrics_base_conditions,
    volumetrics_cancelled_expression,
    volumetrics_data_range,
    volumetrics_display_expression,
    volumetrics_period_start_expression,
    volumetrics_source_select,
)

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


def json_default(value: Any) -> str:
    if isinstance(value, datetime):
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
    return (
        f"{safe_filename_part(customer_name)}_"
        f"{safe_filename_part(project_name)}_Dashboard_{timestamp}.html"
    )


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
            functional_track_ams_owner=[],
            assignment_group_support_lead=[],
            parent_application_name=[],
            application_owner=[],
            supported_by_vendor=[],
            sap_non_sap=[],
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
            ApplicationInventoryItem.active.is_(True),
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
    }


def dimension_key(row: dict[str, Any]) -> tuple[str, str, str, str, str, str]:
    return (
        str(row["scope"]),
        str(row["ticket_type"]),
        str(row["functional_track"]),
        str(row["ams_owner"]),
        str(row["functional_track_ams_owner"]),
        str(row["sap_non_sap"]),
    )


def dimension_dict(key: tuple[str, str, str, str, str, str]) -> dict[str, str]:
    return {
        "scope": key[0],
        "ticket_type": key[1],
        "functional_track": key[2],
        "ams_owner": key[3],
        "functional_track_ams_owner": key[4],
        "sap_non_sap": key[5],
    }


def offline_period_rows(
    db: Session,
    request: Any,
    source: Any,
    date_expression: Any,
    value_label: str,
    extra_conditions: list[Any] | None = None,
) -> dict[tuple[tuple[str, str, str, str, str, str], str], int]:
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
    results: dict[tuple[tuple[str, str, str, str, str, str], str], int] = {}
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
) -> dict[tuple[str, str, str, str, str, str], int]:
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
) -> dict[tuple[tuple[str, str, str, str, str, str], str], dict[str, int]]:
    dimensions = volumetrics_dimension_expressions(source)
    period_expression = volumetrics_period_start_expression(source.c.created_at, "monthly")
    statement = (
        select(
            *[expression.label(name) for name, expression in dimensions.items()],
            period_expression.label("period_start"),
            func.count(source.c.id)
            .filter(source.c.response_sla_breached.is_not(None))
            .label("response_total"),
            func.count(source.c.id)
            .filter(source.c.response_sla_breached.is_(False))
            .label("response_met"),
            func.count(source.c.id)
            .filter(source.c.resolution_sla_breached.is_not(None))
            .label("resolution_total"),
            func.count(source.c.id)
            .filter(source.c.resolution_sla_breached.is_(False))
            .label("resolution_met"),
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
    results: dict[tuple[tuple[str, str, str, str, str, str], str], dict[str, int]] = {}
    for row in db.execute(statement).mappings().all():
        period_start = row["period_start"]
        if period_start is None:
            continue
        results[(dimension_key(row), month_key(period_start))] = {
            "response_sla_total_count": int(row["response_total"] or 0),
            "response_sla_met_count": int(row["response_met"] or 0),
            "resolution_sla_total_count": int(row["resolution_total"] or 0),
            "resolution_sla_met_count": int(row["resolution_met"] or 0),
        }
    return results


def distinct_dimension_keys(db: Session, request: Any, source: Any) -> set[tuple[str, str, str, str, str, str]]:
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
    initial_created = offline_initial_counts(db, request, source, source.c.created_at)
    initial_exits = offline_initial_counts(db, request, source, source.c.exit_at)

    dimension_keys = distinct_dimension_keys(db, request, source)
    for row_key, _period_key in [
        *created_rows.keys(),
        *completed_rows.keys(),
        *cancelled_rows.keys(),
        *exit_rows.keys(),
        *sla_rows.keys(),
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
            rows.append(
                {
                    **dimension_dict(key),
                    "period_key": period_key,
                    "period_label": period.label,
                    "created_count": created_count,
                    "resolved_closed_count": completed_rows.get((key, period_key), 0),
                    "canceled_closed_incomplete_count": cancelled_rows.get((key, period_key), 0),
                    "backlog_open": max(running_created - running_exits, 0),
                    "response_sla_met_count": sla_values.get("response_sla_met_count", 0),
                    "response_sla_total_count": sla_values.get("response_sla_total_count", 0),
                    "resolution_sla_met_count": sla_values.get("resolution_sla_met_count", 0),
                    "resolution_sla_total_count": sla_values.get("resolution_sla_total_count", 0),
                },
            )
    return rows


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
) -> dict[tuple[tuple[str, str, str, str, str, str], int], int]:
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
    rows: dict[tuple[tuple[str, str, str, str, str, str], int], int] = {}
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
        },
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
            ],
            "overall_volume_trends": {
                "created_resolved_by_hour": {"rows": [], "denominators": {}},
                "priority_distribution": {"priorities": [], "rows": []},
            },
            "overall_sla_trends": {"rows": [], "logic": {}},
            "placeholders": {
                "detailed_volume_trends": "Detailed requirements for this section will be added in the next prompts.",
                "kpi_trends": "Detailed requirements for this section will be added in the next prompts.",
                "category_wise_trends": "Detailed requirements for this section will be added in the next prompts.",
            },
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
            ],
            "overall_volume_trends": {
                "created_resolved_by_hour": {"rows": [], "denominators": {}},
                "priority_distribution": {"priorities": [], "rows": []},
            },
            "overall_sla_trends": {"rows": [], "logic": {}},
            "placeholders": {
                "detailed_volume_trends": "Detailed requirements for this section will be added in the next prompts.",
                "kpi_trends": "Detailed requirements for this section will be added in the next prompts.",
                "category_wise_trends": "Detailed requirements for this section will be added in the next prompts.",
            },
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
        "placeholders": {
            "detailed_volume_trends": "Detailed requirements for this section will be added in the next prompts.",
            "kpi_trends": "Detailed requirements for this section will be added in the next prompts.",
            "category_wise_trends": "Detailed requirements for this section will be added in the next prompts.",
        },
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
            ],
        },
        "overview": overview,
        "applications": build_applications_payload(db, project_id),
        "volumetrics": volumetrics,
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
  <meta name="viewport" content="width=device-width, initial-scale=1" />
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
    * { box-sizing: border-box; }
    html,
    body {
      width: 100%;
      height: 100%;
      max-width: 100%;
      margin: 0;
      overflow: hidden;
      background: var(--bg);
      color: var(--text);
    }
    .shell {
      display: grid;
      grid-template-rows: auto auto minmax(0, 1fr);
      gap: 12px;
      width: 100%;
      max-width: 100vw;
      height: 100vh;
      min-width: 0;
      overflow: hidden;
      padding: 10px;
    }
    .topbar, .panel {
      border: 1px solid var(--border);
      border-radius: 8px;
      background: var(--panel);
      box-shadow: 0 1px 3px rgba(15, 23, 42, 0.05);
    }
    .topbar {
      display: flex;
      justify-content: space-between;
      gap: 16px;
      align-items: flex-start;
      min-width: 0;
      padding: 14px 16px;
    }
    h1, h2, h3 { margin: 0; }
    h1 { font-size: 1.25rem; }
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
    .tabs { display: flex; flex-wrap: wrap; gap: 8px; }
    .tab {
      min-height: 36px;
      padding: 0 15px;
      border: 1px solid var(--border);
      border-radius: 8px;
      background: #fff;
      color: #334155;
      cursor: pointer;
      font-weight: 900;
    }
    .tab.active { border-color: var(--teal); color: #fff; background: var(--teal); }
    .view {
      display: none;
      min-width: 0;
      min-height: 0;
      overflow: hidden;
    }
    .view.active {
      display: grid;
      gap: 12px;
      min-height: 0;
    }
    #overview.view.active {
      overflow-x: hidden;
      overflow-y: auto;
      padding-right: 4px;
    }
    .summary-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
      gap: 10px;
      min-width: 0;
    }
    .tile {
      min-height: 84px;
      padding: 10px 12px;
      border: 1px solid var(--border);
      border-radius: 8px;
      background: #f8fafc;
    }
    .tile strong { display: block; margin-top: 6px; font-size: 1.08rem; }
    .tile .muted { margin: 7px 0 0; font-size: 0.78rem; }
    .layout {
      display: grid;
      grid-template-columns: minmax(240px, 280px) minmax(0, 1fr);
      gap: 12px;
      height: 100%;
      min-height: 0;
      min-width: 0;
      overflow: hidden;
    }
    .filters {
      position: sticky;
      top: 0;
      display: grid;
      align-content: start;
      gap: 12px;
      max-height: 100%;
      min-width: 0;
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
      height: 100%;
      min-width: 0;
      min-height: 0;
      overflow-x: hidden;
      overflow-y: auto;
      padding-right: 4px;
    }
    .chart-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px;
      min-width: 0;
    }
    .chart-card {
      min-width: 0;
      overflow: hidden;
      padding: 10px;
    }
    .chart-card.full { grid-column: 1 / -1; }
    .chart-frame {
      width: 100%;
      min-width: 0;
      min-height: 250px;
      margin-top: 8px;
      overflow: hidden;
      border: 1px solid #cbd5e1;
      border-radius: 8px;
      background: #fff;
    }
    svg {
      display: block;
      width: 100%;
      max-width: 100%;
      height: auto;
    }
    .table-frame {
      max-height: 360px;
      overflow: auto;
      border: 1px solid var(--border);
      border-radius: 8px;
      background: #fff;
    }
    table { width: 100%; border-collapse: collapse; min-width: 900px; font-size: 0.78rem; }
    th, td {
      padding: 8px 10px;
      border-bottom: 1px solid #e2e8f0;
      text-align: left;
      white-space: nowrap;
    }
    th { position: sticky; top: 0; background: #f8fafc; z-index: 1; }
    .pattern-buttons { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 10px; }
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
    .legend span { display: inline-flex; align-items: center; gap: 5px; font-weight: 800; }
    .swatch { width: 12px; height: 12px; border-radius: 2px; display: inline-block; }
    @media (max-width: 980px) {
      .topbar, .layout { grid-template-columns: 1fr; display: grid; }
      .summary-grid, .chart-grid { grid-template-columns: 1fr; }
      .filters { position: static; max-height: none; }
      .main { overflow-y: visible; }
      body { overflow-y: auto; }
    }
  </style>
</head>
<body>
  <script type="application/json" id="dashboard-data">__DASHBOARD_DATA_JSON__</script>
  <main class="shell">
    <section class="topbar">
      <div>
        <p class="label">Offline Dashboard</p>
        <h1 id="page-title"></h1>
        <p class="muted" id="page-subtitle"></p>
      </div>
      <div class="muted" id="export-meta"></div>
    </section>
    <nav class="tabs" aria-label="Dashboard tabs">
      <button class="tab active" data-tab="overview" type="button">Overview</button>
      <button class="tab" data-tab="applications" type="button">Applications</button>
      <button class="tab" data-tab="volumetrics" type="button">Volumetrics &amp; SLA</button>
    </nav>
    <section class="view active" id="overview"></section>
    <section class="view" id="applications"></section>
    <section class="view" id="volumetrics"></section>
  </main>
  <script>
    const DASHBOARD = JSON.parse(document.getElementById("dashboard-data").textContent);
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
      appFunctional: "all",
      appSap: "all",
      volScope: "in_scope",
      volTicketType: "all",
      volFunctional: "all",
      volSap: "all",
      pattern: "day_of_month",
      volSubTab: "overall_volume_trends",
      hourlyDayType: "weekdays",
      priorityView: "graph"
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
    function tile(label, value, helper = "") {
      return `<div class="tile"><p class="label">${esc(label)}</p><strong>${esc(value)}</strong><p class="muted">${esc(helper)}</p></div>`;
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
      const width = Math.max(options.width || 880, data.length * (series.length + 1) * 18);
      const height = options.height || 310;
      const margin = { top: 38, right: 30, bottom: 76, left: 34 };
      const plotWidth = width - margin.left - margin.right;
      const plotHeight = height - margin.top - margin.bottom;
      const maxValue = Math.max(1, ...data.flatMap((row) => series.map((item) => Number(row[item.key] || 0))));
      const groupWidth = plotWidth / Math.max(1, data.length);
      const barWidth = Math.max(5, Math.min(18, (groupWidth - 8) / series.length));
      const bars = [];
      data.forEach((row, index) => {
        series.forEach((item, seriesIndex) => {
          const value = Number(row[item.key] || 0);
          const barHeight = (value / maxValue) * plotHeight;
          const x = margin.left + index * groupWidth + (groupWidth - barWidth * series.length) / 2 + seriesIndex * barWidth;
          const y = margin.top + plotHeight - barHeight;
          bars.push(`<rect x="${x}" y="${y}" width="${barWidth}" height="${barHeight}" fill="${item.color}" rx="3"></rect>`);
          if (value > 0) {
            bars.push(`<text x="${x + barWidth / 2}" y="${y - 5}" text-anchor="middle" font-size="10" fill="#475569">${options.roundLabels ? rounded(value) : fmt(value)}</text>`);
          }
        });
      });
      const labels = data.map((row, index) => {
        const x = margin.left + index * groupWidth + groupWidth / 2;
        return `<text x="${x}" y="${height - 42}" text-anchor="end" transform="rotate(-35 ${x} ${height - 42})" font-size="11" font-weight="700" fill="#475569">${esc(row.label)}</text>`;
      });
      return `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${options.title || "Bar chart"}">
        <line x1="${margin.left}" y1="${margin.top + plotHeight}" x2="${width - margin.right}" y2="${margin.top + plotHeight}" stroke="#64748b"></line>
        ${bars.join("")}${labels.join("")}
      </svg>${legend(series)}`;
    }
    function lineChart(data, key, averageKey) {
      const width = Math.max(880, data.length * 56);
      const height = 310;
      const margin = { top: 44, right: 36, bottom: 72, left: 36 };
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
      return `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Backlog chart">
        <line x1="${margin.left}" y1="${margin.top + plotHeight}" x2="${width - margin.right}" y2="${margin.top + plotHeight}" stroke="#64748b"></line>
        <line x1="${margin.left}" y1="${avgY}" x2="${width - margin.right}" y2="${avgY}" stroke="${COLORS.purple}" stroke-dasharray="6 5"></line>
        <text x="${width - margin.right - 8}" y="${avgY - 10}" text-anchor="end" fill="${COLORS.purple}" font-size="12" font-weight="900">Avg backlog: ${fmt(average)}</text>
        <path d="${path}" fill="none" stroke="${COLORS.orange}" stroke-width="3"></path>
        ${points.map(([x, y], index) => `<circle cx="${x}" cy="${y}" r="4" fill="#fff" stroke="${COLORS.orange}" stroke-width="2"></circle><text x="${x}" y="${y - 9}" text-anchor="middle" font-size="10" fill="#475569">${fmt(data[index][key])}</text>`).join("")}
        ${data.map((row, index) => {
          const x = margin.left + (plotWidth * index) / Math.max(1, data.length - 1);
          return `<text x="${x}" y="${height - 38}" text-anchor="end" transform="rotate(-35 ${x} ${height - 38})" font-size="11" font-weight="700" fill="#475569">${esc(row.label)}</text>`;
        }).join("")}
      </svg>${legend([{ name: "Backlog(Open)", color: COLORS.orange }, { name: "Average", color: COLORS.purple }])}`;
    }
    function pieChart(items) {
      const total = items.reduce((sum, item) => sum + item.count, 0);
      if (!total) return `<p class="muted">No chart data available.</p>`;
      let startAngle = -90;
      const radius = 96;
      const cx = 170;
      const cy = 125;
      const colors = [COLORS.blue, COLORS.green, COLORS.orange, COLORS.red, COLORS.purple, COLORS.slate];
      const slices = items.map((item, index) => {
        const angle = (item.count / total) * 360;
        const endAngle = startAngle + angle;
        const start = polar(cx, cy, radius, endAngle);
        const end = polar(cx, cy, radius, startAngle);
        const large = angle > 180 ? 1 : 0;
        const path = `M ${cx} ${cy} L ${start.x} ${start.y} A ${radius} ${radius} 0 ${large} 0 ${end.x} ${end.y} Z`;
        startAngle = endAngle;
        return `<path d="${path}" fill="${colors[index % colors.length]}"><title>${esc(item.label)}: ${fmt(item.count)}</title></path>`;
      });
      return `<svg viewBox="0 0 360 260" role="img" aria-label="Pie chart">${slices.join("")}</svg>${legend(items.map((item, index) => ({ name: `${item.label} (${fmt(item.count)})`, color: colors[index % colors.length] })))}`;
    }
    function polar(cx, cy, radius, angle) {
      const radians = (angle * Math.PI) / 180;
      return { x: cx + radius * Math.cos(radians), y: cy + radius * Math.sin(radians) };
    }
    function legend(items) {
      return `<div class="legend">${items.map((item) => `<span><i class="swatch" style="background:${item.color}"></i>${esc(item.name)}</span>`).join("")}</div>`;
    }
    function countBy(rows, field) {
      const map = new Map();
      rows.forEach((row) => map.set(row[field] || "(blank)", (map.get(row[field] || "(blank)") || 0) + 1));
      return [...map.entries()]
        .map(([label, count]) => ({ label, count }))
        .sort((left, right) => right.count - left.count || left.label.localeCompare(right.label));
    }
    function aggregateByPeriod(rows) {
      return DASHBOARD.volumetrics.periods.map((period) => {
        const matching = rows.filter((row) => row.period_key === period.period_key);
        return {
          label: period.period_label,
          created: sum(matching, "created_count"),
          resolved: sum(matching, "resolved_closed_count"),
          canceled: sum(matching, "canceled_closed_incomplete_count"),
          backlog: sum(matching, "backlog_open"),
          responseMet: sum(matching, "response_sla_met_count"),
          responseTotal: sum(matching, "response_sla_total_count"),
          resolutionMet: sum(matching, "resolution_sla_met_count"),
          resolutionTotal: sum(matching, "resolution_sla_total_count")
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
        <div class="summary-grid" style="margin-top:12px">
          ${tile("Customer", DASHBOARD.metadata.customer_name)}
          ${tile("Project", DASHBOARD.metadata.project_name)}
          ${tile("Total Applications", fmt(overview.application_inventory.total_applications))}
          ${tile("Functional Tracks", fmt(overview.application_inventory.functional_track_count))}
          ${tile("AMS Owners", fmt(overview.application_inventory.ams_owner_count))}
          ${tile("Supported Vendors", fmt(overview.application_inventory.supported_vendor_count))}
          ${tile("Assignment Groups", fmt(overview.application_inventory.assignment_group_count))}
          ${tile("Application Owners", fmt(overview.application_inventory.application_owner_count))}
          ${tile("In-Scope Tickets", fmt(overview.tickets.total_in_scope_tickets), `Incidents: ${fmt(overview.tickets.incident_count)} | SC Tasks: ${fmt(overview.tickets.sc_task_count)}`)}
          ${tile("Completion Range", `${dateText(overview.tickets.completion_date_min)} to ${dateText(overview.tickets.completion_date_max)}`)}
        </div></section>`;
    }
    function filteredApplications() {
      return DASHBOARD.applications.rows.filter((row) =>
        (state.appFunctional === "all" || row.functional_track_ams_owner === state.appFunctional) &&
        (state.appSap === "all" || row.sap_non_sap === state.appSap)
      );
    }
    function renderApplications() {
      const rows = filteredApplications();
      const functionalValues = uniqueSorted(DASHBOARD.applications.rows, "functional_track_ams_owner");
      const sapValues = uniqueSorted(DASHBOARD.applications.rows, "sap_non_sap");
      const businessCount = rows.filter((row) => ["business", "business application"].includes(String(row.app_type).toLowerCase())).length;
      const technicalCount = rows.filter((row) => ["technical", "technical application"].includes(String(row.app_type).toLowerCase())).length;
      const criticalCount = rows.filter((row) => String(row.biz_criticality).toLowerCase() === "critical").length;
      const veryCriticalCount = rows.filter((row) => String(row.biz_criticality).toLowerCase() === "very critical").length;
      document.getElementById("applications").innerHTML = `<div class="layout">
        <aside class="filters panel">
          <p class="label">Filters</p><h2>Applications</h2>
          ${renderSelect("app-functional", "Functional Track / AMS Owner", [{ value: "all", label: "All" }, ...functionalValues.map((value) => ({ value, label: value }))], state.appFunctional)}
          ${renderSelect("app-sap", "SAP / Non-SAP", [{ value: "all", label: "All" }, ...sapValues.map((value) => ({ value, label: value }))], state.appSap)}
        </aside>
        <section class="main">
          <div class="summary-grid">
            ${tile("Applications", fmt(new Set(rows.map((row) => row.business_service_ci_name)).size))}
            ${tile("Functional Groups", fmt(new Set(rows.map((row) => row.functional_track)).size))}
            ${tile("Assignment Groups", fmt(new Set(rows.map((row) => row.assignment_group)).size))}
            ${tile("Parent Business Apps", fmt(new Set(rows.map((row) => row.parent_application_name)).size))}
            ${tile("Application Type", `Business: ${fmt(businessCount)}`, `Technical: ${fmt(technicalCount)}`)}
            ${tile("Criticality", `Very Critical: ${fmt(veryCriticalCount)}`, `Critical: ${fmt(criticalCount)}`)}
          </div>
          <div class="chart-grid">
            <section class="chart-card panel"><h3>Strategic</h3><div class="chart-frame">${pieChart(countBy(rows, "strategic"))}</div></section>
            <section class="chart-card panel"><h3>Lifecycle Stage</h3><div class="chart-frame">${barChart(countBy(rows, "lifecycle_stage_status").map((row) => ({ label: row.label, count: row.count })), [{ key: "count", name: "Applications", color: COLORS.blue }], { width: 760 })}</div></section>
            <section class="chart-card panel"><h3>Operating System</h3><div class="chart-frame">${barChart(countBy(rows, "operating_system").map((row) => ({ label: row.label, count: row.count })), [{ key: "count", name: "Applications", color: COLORS.teal }], { width: 760 })}</div></section>
            <section class="chart-card panel"><h3>SOX Scope</h3><div class="chart-frame">${barChart(countBy(rows, "sox_scope").map((row) => ({ label: row.label, count: row.count })), [{ key: "count", name: "Applications", color: COLORS.purple }], { width: 760 })}</div></section>
          </div>
          <section class="panel" style="padding:14px"><h3>Application List</h3><div class="table-frame">${applicationTable(rows)}</div></section>
        </section>
      </div>`;
      document.getElementById("app-functional").addEventListener("change", (event) => { state.appFunctional = event.target.value; renderApplications(); });
      document.getElementById("app-sap").addEventListener("change", (event) => { state.appSap = event.target.value; renderApplications(); });
    }
    function applicationTable(rows) {
      const columns = ["business_service_ci_name", "parent_application_name", "assignment_group", "sap_non_sap", "application_owner", "support_lead", "functional_track", "ams_owner", "supported_by_vendor", "app_type", "architecture_type", "biz_criticality", "install_status", "lifecycle_status", "operating_system", "sox_scope", "strategic"];
      return `<table><thead><tr>${columns.map((column) => `<th>${esc(column.replaceAll("_", " "))}</th>`).join("")}</tr></thead><tbody>${rows.map((row) => `<tr>${columns.map((column) => `<td>${esc(row[column] || "")}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
    }
    function filteredVolumetricsRows() {
      return DASHBOARD.volumetrics.monthly_rows.filter((row) =>
        (state.volScope === "all" || row.scope === state.volScope) &&
        (state.volTicketType === "all" || row.ticket_type === state.volTicketType) &&
        (state.volFunctional === "all" || row.functional_track_ams_owner === state.volFunctional) &&
        (state.volSap === "all" || row.sap_non_sap === state.volSap)
      );
    }
    function filteredPatternRows() {
      return DASHBOARD.volumetrics.created_patterns.rows.filter((row) =>
        row.pattern_type === state.pattern &&
        (state.volScope === "all" || row.scope === state.volScope) &&
        (state.volTicketType === "all" || row.ticket_type === state.volTicketType) &&
        (state.volFunctional === "all" || row.functional_track_ams_owner === state.volFunctional) &&
        (state.volSap === "all" || row.sap_non_sap === state.volSap)
      );
    }
    function offlineFilterMatch(row) {
      return (
        (state.volScope === "all" || row.scope === state.volScope) &&
        (state.volTicketType === "all" || row.ticket_type === state.volTicketType) &&
        (state.volFunctional === "all" || row.functional_track_ams_owner === state.volFunctional) &&
        (state.volSap === "all" || row.sap_non_sap === state.volSap)
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
        (state.volSap === "all" || row.sap_non_sap === state.volSap)
      );
    }
    function renderVolumetrics() {
      const rows = filteredVolumetricsRows();
      const periods = aggregateByPeriod(rows);
      document.getElementById("volumetrics").innerHTML = `<div class="layout">
        <aside class="filters panel">
          <p class="label">Filters</p><h2>Volumetrics &amp; SLA</h2>
          ${renderSelect("vol-scope", "Scope", DASHBOARD.volumetrics.filter_values.scope, state.volScope)}
          ${renderSelect("vol-ticket", "Ticket Type", DASHBOARD.volumetrics.filter_values.ticket_type, state.volTicketType)}
          ${renderSelect("vol-functional", "Functional Track / AMS Owner", [{ value: "all", label: "All" }, ...DASHBOARD.volumetrics.filter_values.functional_track_ams_owner.map((value) => ({ value, label: value }))], state.volFunctional)}
          ${renderSelect("vol-sap", "SAP / Non-SAP", [{ value: "all", label: "All" }, ...DASHBOARD.volumetrics.filter_values.sap_non_sap.map((value) => ({ value, label: value }))], state.volSap)}
        </aside>
        <section class="main">
          <section class="panel" style="padding:14px"><p class="muted"><strong>Monthly dashboard based on complete uploaded months.</strong> Charts use ${dateText(DASHBOARD.metadata.complete_month_from)} to ${dateText(DASHBOARD.metadata.complete_month_to)}. Data available from ${dateText(DASHBOARD.metadata.data_available_from)} to ${dateText(DASHBOARD.metadata.data_available_to)}.</p><div class="subtabs">${volSubTabs()}</div></section>
          ${renderVolumetricsSubTab(periods)}
        </section>
      </div>`;
      ["vol-scope", "vol-ticket", "vol-functional", "vol-sap"].forEach((id) => {
        document.getElementById(id).addEventListener("change", (event) => {
          const map = { "vol-scope": "volScope", "vol-ticket": "volTicketType", "vol-functional": "volFunctional", "vol-sap": "volSap" };
          state[map[id]] = event.target.value;
          renderVolumetrics();
        });
      });
      document.querySelectorAll("[data-vol-subtab]").forEach((button) => {
        button.addEventListener("click", () => { state.volSubTab = button.dataset.volSubtab; renderVolumetrics(); });
      });
      document.querySelectorAll("[data-pattern]").forEach((button) => {
        button.addEventListener("click", () => { state.pattern = button.dataset.pattern; renderVolumetrics(); });
      });
      document.querySelectorAll("[data-hourly-day]").forEach((button) => {
        button.addEventListener("click", () => { state.hourlyDayType = button.dataset.hourlyDay; renderVolumetrics(); });
      });
      document.querySelectorAll("[data-priority-view]").forEach((button) => {
        button.addEventListener("click", () => { state.priorityView = button.dataset.priorityView; renderVolumetrics(); });
      });
    }
    function volSubTabs() {
      const labels = {
        overall_volume_trends: "Overall Volume Trends",
        overall_sla_trends: "Overall SLA Trends",
        detailed_volume_trends: "Detailed Volume Trends",
        kpi_trends: "KPI Trends",
        category_wise_trends: "Category-wise Trends"
      };
      return Object.entries(labels).map(([value, label]) => `<button type="button" data-vol-subtab="${esc(value)}" class="${state.volSubTab === value ? "active" : ""}">${esc(label)}</button>`).join("");
    }
    function renderVolumetricsSubTab(periods) {
      if (state.volSubTab === "overall_sla_trends") return renderSlaTrends();
      if (state.volSubTab === "detailed_volume_trends") return placeholder("Detailed Volume Trends");
      if (state.volSubTab === "kpi_trends") return placeholder("KPI Trends");
      if (state.volSubTab === "category_wise_trends") return placeholder("Category-wise Trends");
      return renderOverallVolume(periods);
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
        <div class="summary-grid">
          ${tile("Created", `Total: ${fmt(totalCreated)}`, `Avg monthly: ${fmt(totalCreated / Math.max(1, periods.length))}`)}
          ${tile("Resolved / Closed", `Total: ${fmt(totalResolved)}`, `Avg monthly: ${fmt(totalResolved / Math.max(1, periods.length))}`)}
          ${tile("Canceled / Closed Incomplete", `Total: ${fmt(totalCanceled)}`, `% of Resolved+Canceled: ${pct(totalCanceled, totalResolved + totalCanceled)}`)}
          ${tile("Response SLA", responseAverage === null ? "N/A" : `${responseAverage.toFixed(1)}%`, "Avg monthly adherence")}
          ${tile("Resolution SLA", resolutionAverage === null ? "N/A" : `${resolutionAverage.toFixed(1)}%`, "Avg monthly adherence")}
        </div>
        <section class="chart-card panel full"><h3>Created vs Resolved/Closed vs Canceled / Closed Incomplete</h3><div class="chart-frame">${barChart(periods, [{ key: "created", name: "Created", color: COLORS.teal }, { key: "resolved", name: "Resolved/Closed", color: COLORS.blue }, { key: "canceled", name: "Canceled", color: COLORS.red }], { width: 980 })}</div></section>
        <section class="chart-card panel full"><h3>Backlog(Open)</h3><div class="chart-frame">${lineChart(periods, "backlog", "average")}</div></section>
        <section class="chart-card panel full"><h3>Created Pattern</h3><p class="muted">Average created/opened tickets across the available monthly range.</p><div class="pattern-buttons">${patternButtons()}</div><div class="chart-frame">${createdPatternChart()}</div></section>
        <section class="chart-card panel full"><h3>Created vs Resolved by hour of the day</h3><div class="pattern-buttons">${hourlyButtons()}</div><div class="chart-frame">${hourlyCreatedResolvedChart()}</div></section>
        <section class="chart-card panel full"><div class="chart-title-row"><h3>Priority-wise ticket distribution</h3><div class="pattern-buttons">${priorityToggle()}</div></div><div class="chart-frame">${priorityDistributionContent()}</div></section>
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
    function priorityDistributionContent() {
      const priorities = DASHBOARD.volumetrics.overall_volume_trends?.priority_distribution?.priorities || [];
      const rows = filteredPriorityRows();
      const periodRows = DASHBOARD.volumetrics.periods.map((period) => {
        const values = {};
        priorities.forEach((priority) => { values[priority] = 0; });
        rows.filter((row) => row.period_key === period.period_key).forEach((row) => {
          values[row.priority] = (values[row.priority] || 0) + Number(row.ticket_count || 0);
        });
        return {
          label: period.period_label,
          values,
          total: priorities.reduce((sumValue, priority) => sumValue + (values[priority] || 0), 0)
        };
      });
      if (state.priorityView === "table") {
        return priorityDistributionTable(periodRows, priorities);
      }
      const series = priorities.map((priority, index) => ({ key: priority, name: priority, color: [COLORS.teal, COLORS.blue, COLORS.orange, COLORS.purple, COLORS.red, COLORS.slate][index % 6] }));
      return stackedBarChart(periodRows, series);
    }
    function priorityDistributionTable(points, priorities) {
      return `<div class="table-frame"><table><thead><tr><th>Period</th>${priorities.map((priority) => `<th>${esc(priority)}</th>`).join("")}<th>Total</th></tr></thead><tbody>${points.map((point) => `<tr><td>${esc(point.label)}</td>${priorities.map((priority) => `<td>${fmt(point.values[priority] || 0)}</td>`).join("")}<td>${fmt(point.total)}</td></tr>`).join("")}</tbody></table></div>`;
    }
    function stackedBarChart(data, series) {
      const width = Math.max(880, data.length * 54);
      const height = 330;
      const margin = { top: 34, right: 30, bottom: 76, left: 34 };
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
          if (value > 0) {
            bars.push(`<rect x="${x}" y="${y}" width="${barWidth}" height="${barHeight}" fill="${item.color}"><title>${esc(item.name)}: ${fmt(value)}</title></rect>`);
          }
          stackTop = y;
        });
      });
      const labels = data.map((row, index) => {
        const x = margin.left + index * groupWidth + groupWidth / 2;
        return `<text x="${x}" y="${height - 42}" text-anchor="end" transform="rotate(-35 ${x} ${height - 42})" font-size="11" font-weight="700" fill="#475569">${esc(row.label)}</text>`;
      });
      return `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Priority distribution">
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
      return `
        <section class="chart-card panel full"><h3>Response SLA adherence trend</h3><p class="muted">Adherence = captured SLA adhered count / captured SLA count.</p><div class="chart-frame">${slaLineChart(response, COLORS.teal, "Response SLA adherence %")}</div>${slaTrendTable(response, "Response SLA")}</section>
        <section class="chart-card panel full"><h3>Resolution SLA adherence trend</h3><p class="muted">Adherence = captured SLA adhered count / captured SLA count.</p><div class="chart-frame">${slaLineChart(resolution, COLORS.blue, "Resolution SLA adherence %")}</div>${slaTrendTable(resolution, "Resolution SLA")}</section>
      `;
    }
    function slaTrendPoints(rows, kind) {
      return DASHBOARD.volumetrics.periods.map((period) => {
        const matching = rows.filter((row) => row.period_key === period.period_key);
        const totalClosed = sum(matching, "total_closed_ticket_count");
        const captured = sum(matching, `${kind}_sla_captured_count`);
        const adhered = sum(matching, `${kind}_sla_adhered_count`);
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
      const width = Math.max(880, data.length * 56);
      const height = 310;
      const margin = { top: 42, right: 34, bottom: 76, left: 44 };
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
      return `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${esc(label)}">
        <line x1="${margin.left}" y1="${margin.top + plotHeight}" x2="${width - margin.right}" y2="${margin.top + plotHeight}" stroke="#64748b"></line>
        <path d="${path}" fill="none" stroke="${color}" stroke-width="3"></path>
        ${points.map((point) => point.y === null ? "" : `<circle cx="${point.x}" cy="${point.y}" r="4" fill="#fff" stroke="${color}" stroke-width="2"></circle><text x="${point.x}" y="${point.y - 9}" text-anchor="middle" font-size="10" fill="#475569">${point.row.pct.toFixed(1)}%</text>`).join("")}
        ${data.map((row, index) => {
          const x = margin.left + (plotWidth * index) / Math.max(1, data.length - 1);
          return `<text x="${x}" y="${height - 40}" text-anchor="end" transform="rotate(-35 ${x} ${height - 40})" font-size="11" font-weight="700" fill="#475569">${esc(row.label)}</text>`;
        }).join("")}
      </svg>${legend([{ name: label, color }])}`;
    }
    function slaTrendTable(rows, label) {
      return `<div class="table-frame" style="margin-top:10px"><table><thead><tr><th>Duration</th><th>Total closed tickets</th><th>${esc(label)} captured</th><th>${esc(label)} adhered</th><th>${esc(label)} adherence %</th></tr></thead><tbody>${rows.map((row) => `<tr><td>${esc(row.label)}</td><td>${fmt(row.totalClosed)}</td><td>${fmt(row.captured)}</td><td>${fmt(row.adhered)}</td><td>${row.pct === null ? "N/A" : `${row.pct.toFixed(1)}%`}</td></tr>`).join("")}</tbody></table></div>`;
    }
    function activateTab(tab) {
      state.tab = tab;
      document.querySelectorAll(".tab").forEach((button) => button.classList.toggle("active", button.dataset.tab === tab));
      document.querySelectorAll(".view").forEach((view) => view.classList.toggle("active", view.id === tab));
    }
    function initialize() {
      document.getElementById("page-title").textContent = "AMS Ticket Intelligence";
      document.getElementById("page-subtitle").textContent = `${DASHBOARD.metadata.customer_name} / ${DASHBOARD.metadata.project_name}`;
      document.getElementById("export-meta").innerHTML = `Exported: ${dateTimeText(DASHBOARD.metadata.exported_at)}<br>Monthly offline dashboard`;
      document.querySelectorAll(".tab").forEach((button) => button.addEventListener("click", () => activateTab(button.dataset.tab)));
      renderOverview();
      renderApplications();
      renderVolumetrics();
    }
    initialize();
  </script>
</body>
</html>
"""
