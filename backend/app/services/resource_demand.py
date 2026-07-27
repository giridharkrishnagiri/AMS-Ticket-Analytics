from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    AssessmentChangeRecord,
    AssessmentProblemRecord,
    ResourceDemandServiceLevelSplit,
    ResourceDemandUnitEffort,
    Ticket,
)
from app.schemas.resource_demand import (
    ResourceDemandInputRow,
    ResourceDemandResponse,
    ResourceDemandServiceLevelSplitRow,
    ResourceDemandServiceLevelValues,
    ResourceDemandTechnologyView,
    ResourceDemandUnitEffortRow,
)
from app.services.dashboard import valid_resolved_closed_state_condition

DEFAULT_FROM_MONTH = "2026-03"
DEFAULT_TO_MONTH = "2026-05"
TECHNOLOGY_TABS = ("Overall", "Generic", "SAP", "Data & Analytics")
MASTER_TECHNOLOGIES = ("Generic", "SAP", "Data & Analytics")
SERVICE_LEVELS = ("L1.5", "L2", "L3")

UNIT_EFFORT_DEFAULTS = (
    ("INCIDENT", "User-generated"),
    ("INCIDENT", "System-generated"),
    ("SERVICE_CATALOG_TASK", "Any"),
    ("PROBLEM", "Any"),
    ("CHANGE", "Any"),
)
SERVICE_LEVEL_SPLIT_DEFAULTS = UNIT_EFFORT_DEFAULTS


def parse_month_key(month_key: str) -> tuple[int, int]:
    try:
        year_text, month_text = month_key.split("-", 1)
        year = int(year_text)
        month = int(month_text)
    except ValueError as exc:
        raise ValueError(f"Month must use YYYY-MM format: {month_key}") from exc
    if month < 1 or month > 12:
        raise ValueError(f"Month must use YYYY-MM format: {month_key}")
    return year, month


def month_start(month_key: str) -> datetime:
    year, month = parse_month_key(month_key)
    return datetime(year, month, 1, tzinfo=UTC)


def add_months(value: datetime, months: int) -> datetime:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    return datetime(year, month, 1, tzinfo=UTC)


def inclusive_month_count(from_month: str, to_month: str) -> int:
    from_year, from_month_number = parse_month_key(from_month)
    to_year, to_month_number = parse_month_key(to_month)
    count = (to_year - from_year) * 12 + (to_month_number - from_month_number) + 1
    if count <= 0:
        raise ValueError("From month must be before or equal to To month.")
    return count


def decimal_to_float(value: Decimal | float | int | None) -> float | None:
    if value is None:
        return None
    return float(value)


def clean_text(value: str | None, fallback: str) -> str:
    cleaned = (value or "").strip()
    return cleaned or fallback


def average_monthly(total: int, month_count: int) -> int:
    if month_count <= 0:
        return 0
    return int((2 * total + month_count) // (2 * month_count))


def round_half_up(value: float) -> int:
    return int(value + 0.5)


def service_level_volume(
    average_monthly_volume: float | int | None,
    percentage: float | int | None,
) -> int | None:
    if average_monthly_volume is None or percentage is None:
        return None
    return round_half_up(float(average_monthly_volume) * float(percentage) / 100.0)


def technology_for_view(label: str) -> str:
    return "Generic" if label == "Overall" else label


def count_ticket_volume(
    db: Session,
    project_id: UUID,
    ticket_type: str,
    completion_column: object,
    from_datetime: datetime,
    to_datetime_exclusive: datetime,
    *extra_conditions: object,
) -> int:
    statement = select(func.count(Ticket.id)).where(
        Ticket.project_id == project_id,
        Ticket.ticket_type == ticket_type,
        Ticket.is_in_scope.is_(True),
        valid_resolved_closed_state_condition(Ticket),
        completion_column.is_not(None),  # type: ignore[attr-defined]
        completion_column >= from_datetime,
        completion_column < to_datetime_exclusive,
        *extra_conditions,
    )
    return int(db.scalar(statement) or 0)


def count_problem_volume(
    db: Session,
    project_id: UUID,
    from_datetime: datetime,
    to_datetime_exclusive: datetime,
) -> int:
    statement = select(func.count(AssessmentProblemRecord.id)).where(
        AssessmentProblemRecord.project_id == project_id,
        AssessmentProblemRecord.closed_at.is_not(None),
        AssessmentProblemRecord.closed_at >= from_datetime,
        AssessmentProblemRecord.closed_at < to_datetime_exclusive,
    )
    return int(db.scalar(statement) or 0)


def count_change_volume(
    db: Session,
    project_id: UUID,
    from_datetime: datetime,
    to_datetime_exclusive: datetime,
) -> int:
    statement = select(func.count(AssessmentChangeRecord.id)).where(
        AssessmentChangeRecord.project_id == project_id,
        AssessmentChangeRecord.closed_at.is_not(None),
        AssessmentChangeRecord.closed_at >= from_datetime,
        AssessmentChangeRecord.closed_at < to_datetime_exclusive,
    )
    return int(db.scalar(statement) or 0)


def overall_demand_rows(
    db: Session,
    project_id: UUID,
    from_datetime: datetime,
    to_datetime_exclusive: datetime,
    month_count: int,
) -> list[ResourceDemandInputRow]:
    system_generated_condition = func.lower(func.coalesce(Ticket.requester, "")).like(
        "%integration%",
    )
    user_generated_condition = ~system_generated_condition

    incident_total = count_ticket_volume(
        db,
        project_id,
        "INCIDENT",
        Ticket.resolved_at,
        from_datetime,
        to_datetime_exclusive,
    )
    incident_user = count_ticket_volume(
        db,
        project_id,
        "INCIDENT",
        Ticket.resolved_at,
        from_datetime,
        to_datetime_exclusive,
        user_generated_condition,
    )
    incident_system = count_ticket_volume(
        db,
        project_id,
        "INCIDENT",
        Ticket.resolved_at,
        from_datetime,
        to_datetime_exclusive,
        system_generated_condition,
    )
    sc_tasks = count_ticket_volume(
        db,
        project_id,
        "SERVICE_CATALOG_TASK",
        Ticket.closed_at,
        from_datetime,
        to_datetime_exclusive,
    )
    problems = count_problem_volume(db, project_id, from_datetime, to_datetime_exclusive)
    changes = count_change_volume(db, project_id, from_datetime, to_datetime_exclusive)

    return [
        ResourceDemandInputRow(
            key="incident_total",
            label="Incidents",
            ticket_type="INCIDENT",
            average_monthly_volume=average_monthly(incident_total, month_count),
            service_level_split=ResourceDemandServiceLevelValues(),
        ),
        ResourceDemandInputRow(
            key="incident_user_generated",
            label="Incidents - User-generated",
            ticket_type="INCIDENT",
            incident_source="User-generated",
            average_monthly_volume=average_monthly(incident_user, month_count),
            service_level_split=ResourceDemandServiceLevelValues(),
        ),
        ResourceDemandInputRow(
            key="incident_system_generated",
            label="Incidents - System-generated",
            ticket_type="INCIDENT",
            incident_source="System-generated",
            average_monthly_volume=average_monthly(incident_system, month_count),
            service_level_split=ResourceDemandServiceLevelValues(),
            notes="System-generated when caller/requester contains integration.",
        ),
        ResourceDemandInputRow(
            key="sc_tasks",
            label="SC Tasks",
            ticket_type="SERVICE_CATALOG_TASK",
            average_monthly_volume=average_monthly(sc_tasks, month_count),
            service_level_split=ResourceDemandServiceLevelValues(),
        ),
        ResourceDemandInputRow(
            key="problems",
            label="Problems",
            ticket_type="PROBLEM",
            average_monthly_volume=average_monthly(problems, month_count),
            service_level_split=ResourceDemandServiceLevelValues(),
        ),
        ResourceDemandInputRow(
            key="changes",
            label="Changes",
            ticket_type="CHANGE",
            average_monthly_volume=average_monthly(changes, month_count),
            service_level_split=ResourceDemandServiceLevelValues(),
        ),
        ResourceDemandInputRow(
            key="non_ticketed_activities",
            label="Non-ticketed activities",
            ticket_type="NON_TICKETED",
            average_monthly_volume=None,
            service_level_split=ResourceDemandServiceLevelValues(),
            notes="Absolute service-level hours will be added once the non-ticketed activity source is defined.",
        ),
    ]


def blank_technology_rows(technology: str) -> list[ResourceDemandInputRow]:
    return [
        ResourceDemandInputRow(
            key=f"{technology.lower().replace(' ', '_').replace('&', 'and')}_{row_key}",
            label=label,
            ticket_type=ticket_type,
            incident_source=incident_source,
            average_monthly_volume=None,
            service_level_split=ResourceDemandServiceLevelValues(),
            notes="Technology-specific volume will be populated after technology derivation is finalized.",
        )
        for row_key, label, ticket_type, incident_source in (
            ("incident_total", "Incidents", "INCIDENT", None),
            ("incident_user_generated", "Incidents - User-generated", "INCIDENT", "User-generated"),
            (
                "incident_system_generated",
                "Incidents - System-generated",
                "INCIDENT",
                "System-generated",
            ),
            ("sc_tasks", "SC Tasks", "SERVICE_CATALOG_TASK", None),
            ("problems", "Problems", "PROBLEM", None),
            ("changes", "Changes", "CHANGE", None),
            ("non_ticketed_activities", "Non-ticketed activities", "NON_TICKETED", None),
        )
    ]


def ensure_default_unit_efforts(db: Session, project_id: UUID) -> None:
    existing_keys = {
        (row.ticket_type, row.incident_source, row.technology)
        for row in db.scalars(
            select(ResourceDemandUnitEffort).where(
                ResourceDemandUnitEffort.project_id == project_id,
            )
        )
    }

    sort_order = 0
    for ticket_type, incident_source in UNIT_EFFORT_DEFAULTS:
        for technology in MASTER_TECHNOLOGIES:
            sort_order += 10
            key = (ticket_type, incident_source, technology)
            if key in existing_keys:
                continue
            db.add(
                ResourceDemandUnitEffort(
                    project_id=project_id,
                    ticket_type=ticket_type,
                    incident_source=incident_source,
                    technology=technology,
                    sort_order=sort_order,
                )
            )
    db.flush()


def unit_effort_response_rows(db: Session, project_id: UUID) -> list[ResourceDemandUnitEffortRow]:
    ensure_default_unit_efforts(db, project_id)
    rows = db.scalars(
        select(ResourceDemandUnitEffort)
        .where(ResourceDemandUnitEffort.project_id == project_id)
        .order_by(
            ResourceDemandUnitEffort.sort_order,
            ResourceDemandUnitEffort.ticket_type,
            ResourceDemandUnitEffort.incident_source,
            ResourceDemandUnitEffort.technology,
        )
    ).all()
    return [
        ResourceDemandUnitEffortRow(
            id=row.id,
            ticket_type=row.ticket_type,
            incident_source=row.incident_source,
            technology=row.technology,
            l1_5_hours=decimal_to_float(row.l1_5_hours),
            l2_hours=decimal_to_float(row.l2_hours),
            l3_hours=decimal_to_float(row.l3_hours),
            sort_order=row.sort_order,
        )
        for row in rows
    ]


def ensure_default_service_level_splits(db: Session, project_id: UUID) -> None:
    existing_keys = {
        (row.ticket_type, row.incident_source, row.technology)
        for row in db.scalars(
            select(ResourceDemandServiceLevelSplit).where(
                ResourceDemandServiceLevelSplit.project_id == project_id,
            )
        )
    }

    sort_order = 0
    for ticket_type, incident_source in SERVICE_LEVEL_SPLIT_DEFAULTS:
        for technology in MASTER_TECHNOLOGIES:
            sort_order += 10
            key = (ticket_type, incident_source, technology)
            if key in existing_keys:
                continue
            db.add(
                ResourceDemandServiceLevelSplit(
                    project_id=project_id,
                    ticket_type=ticket_type,
                    incident_source=incident_source,
                    technology=technology,
                    sort_order=sort_order,
                )
            )
    db.flush()


def service_level_split_response_rows(
    db: Session,
    project_id: UUID,
) -> list[ResourceDemandServiceLevelSplitRow]:
    ensure_default_service_level_splits(db, project_id)
    rows = db.scalars(
        select(ResourceDemandServiceLevelSplit)
        .where(ResourceDemandServiceLevelSplit.project_id == project_id)
        .order_by(
            ResourceDemandServiceLevelSplit.sort_order,
            ResourceDemandServiceLevelSplit.ticket_type,
            ResourceDemandServiceLevelSplit.incident_source,
            ResourceDemandServiceLevelSplit.technology,
        )
    ).all()
    return [
        ResourceDemandServiceLevelSplitRow(
            id=row.id,
            ticket_type=row.ticket_type,
            incident_source=row.incident_source,
            technology=row.technology,
            l1_5_pct=decimal_to_float(row.l1_5_pct),
            l2_pct=decimal_to_float(row.l2_pct),
            l3_pct=decimal_to_float(row.l3_pct),
            sort_order=row.sort_order,
        )
        for row in rows
    ]


def apply_service_level_splits(
    demand_views: list[ResourceDemandTechnologyView],
    split_rows: list[ResourceDemandServiceLevelSplitRow],
) -> None:
    split_by_basis = {
        (row.ticket_type, row.incident_source or "Any", row.technology): row for row in split_rows
    }
    for view in demand_views:
        technology = technology_for_view(view.label)
        for row in view.rows:
            if row.ticket_type == "NON_TICKETED" or row.average_monthly_volume is None:
                continue
            split_row = split_by_basis.get(
                (row.ticket_type, row.incident_source or "Any", technology),
            )
            if split_row is None:
                continue
            row.service_level_split = ResourceDemandServiceLevelValues(
                l1_5=service_level_volume(
                    row.average_monthly_volume,
                    split_row.l1_5_pct,
                ),
                l2=service_level_volume(row.average_monthly_volume, split_row.l2_pct),
                l3=service_level_volume(row.average_monthly_volume, split_row.l3_pct),
            )


def get_resource_demand(
    db: Session,
    project_id: UUID,
    from_month: str = DEFAULT_FROM_MONTH,
    to_month: str = DEFAULT_TO_MONTH,
) -> ResourceDemandResponse:
    month_count = inclusive_month_count(from_month, to_month)
    from_datetime = month_start(from_month)
    to_datetime_exclusive = add_months(month_start(to_month), 1)

    overall_rows = overall_demand_rows(
        db,
        project_id,
        from_datetime,
        to_datetime_exclusive,
        month_count,
    )
    demand_views = [
        ResourceDemandTechnologyView(key="overall", label="Overall", rows=overall_rows),
        *[
            ResourceDemandTechnologyView(
                key=technology.lower().replace(" ", "_").replace("&", "and"),
                label=technology,
                rows=blank_technology_rows(technology),
            )
            for technology in MASTER_TECHNOLOGIES
        ],
    ]
    service_level_splits = service_level_split_response_rows(db, project_id)
    apply_service_level_splits(demand_views, service_level_splits)

    return ResourceDemandResponse(
        project_id=project_id,
        period_from_month=from_month,
        period_to_month=to_month,
        month_count=month_count,
        technologies=list(TECHNOLOGY_TABS),
        demand_views=demand_views,
        unit_efforts=unit_effort_response_rows(db, project_id),
        service_level_splits=service_level_splits,
        data_notes=[
            "Overall volumes use in-scope closed/resolved records from Mar 2026 to May 2026 by default.",
            "Incident source split uses caller/requester containing integration for system-generated incidents.",
            "Technology-specific volume is intentionally blank until the mapping rules are defined.",
        ],
        warnings=[],
    )


def upsert_resource_demand_unit_efforts(
    db: Session,
    project_id: UUID,
    rows: list[ResourceDemandUnitEffortRow],
) -> list[ResourceDemandUnitEffortRow]:
    ensure_default_unit_efforts(db, project_id)
    existing_by_id = {
        row.id: row
        for row in db.scalars(
            select(ResourceDemandUnitEffort).where(
                ResourceDemandUnitEffort.project_id == project_id,
            )
        )
    }
    existing_by_basis = {
        (row.ticket_type, row.incident_source, row.technology): row
        for row in existing_by_id.values()
    }

    for index, input_row in enumerate(rows):
        ticket_type = clean_text(input_row.ticket_type, "UNKNOWN").upper()
        incident_source = clean_text(input_row.incident_source, "Any")
        technology = clean_text(input_row.technology, "Generic")
        target = existing_by_id.get(input_row.id) if input_row.id else None
        if target is None:
            target = existing_by_basis.get((ticket_type, incident_source, technology))
        if target is None:
            target = ResourceDemandUnitEffort(
                project_id=project_id,
                ticket_type=ticket_type,
                incident_source=incident_source,
                technology=technology,
            )
            db.add(target)

        target.ticket_type = ticket_type
        target.incident_source = incident_source
        target.technology = technology
        target.l1_5_hours = input_row.l1_5_hours
        target.l2_hours = input_row.l2_hours
        target.l3_hours = input_row.l3_hours
        target.sort_order = input_row.sort_order or (index + 1) * 10

    db.flush()
    return unit_effort_response_rows(db, project_id)


def upsert_resource_demand_service_level_splits(
    db: Session,
    project_id: UUID,
    rows: list[ResourceDemandServiceLevelSplitRow],
) -> list[ResourceDemandServiceLevelSplitRow]:
    ensure_default_service_level_splits(db, project_id)
    existing_by_id = {
        row.id: row
        for row in db.scalars(
            select(ResourceDemandServiceLevelSplit).where(
                ResourceDemandServiceLevelSplit.project_id == project_id,
            )
        )
    }
    existing_by_basis = {
        (row.ticket_type, row.incident_source, row.technology): row
        for row in existing_by_id.values()
    }

    for index, input_row in enumerate(rows):
        ticket_type = clean_text(input_row.ticket_type, "UNKNOWN").upper()
        incident_source = clean_text(input_row.incident_source, "Any")
        technology = clean_text(input_row.technology, "Generic")
        target = existing_by_id.get(input_row.id) if input_row.id else None
        if target is None:
            target = existing_by_basis.get((ticket_type, incident_source, technology))
        if target is None:
            target = ResourceDemandServiceLevelSplit(
                project_id=project_id,
                ticket_type=ticket_type,
                incident_source=incident_source,
                technology=technology,
            )
            db.add(target)

        target.ticket_type = ticket_type
        target.incident_source = incident_source
        target.technology = technology
        target.l1_5_pct = input_row.l1_5_pct
        target.l2_pct = input_row.l2_pct
        target.l3_pct = input_row.l3_pct
        target.sort_order = input_row.sort_order or (index + 1) * 10

    db.flush()
    return service_level_split_response_rows(db, project_id)
