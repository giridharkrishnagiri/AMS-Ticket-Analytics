from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import delete, func, select, text, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models import IncidentSlaRow, Project, Ticket
from app.services.ingestion import INGESTION_BATCH_SIZE, iter_csv_rows, normalize_source_column_name
from app.services.mapping import parse_bool_value, parse_business_duration_seconds, text_or_none

MAX_MESSAGE_SAMPLES = 50
INCIDENT_TICKET_TYPE = "INCIDENT"
SLA_TARGET_RESPONSE = "response"
SLA_TARGET_RESOLUTION = "resolution"


class IncidentSlaError(Exception):
    pass


@dataclass
class IncidentSlaUploadResult:
    project_id: UUID
    uploaded_file_name: str
    total_rows: int = 0
    inserted_rows: int = 0
    failed_rows: int = 0
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class IncidentSlaEnrichResult:
    project_id: UUID
    ticket_type: str
    replace_existing: bool
    matched_ticket_count: int
    response_sla_updated_count: int
    resolution_sla_updated_count: int
    warnings: list[str]


@dataclass(frozen=True)
class IncidentSlaSummary:
    project_id: UUID
    total_sla_rows: int
    unique_incident_numbers: int
    matched_tickets_count: int
    unmatched_sla_incident_numbers_count: int
    tickets_with_response_sla_selected: int
    tickets_with_resolution_sla_selected: int
    response_accenture_selected_count: int
    response_default_selected_count: int
    resolution_accenture_selected_count: int
    resolution_default_selected_count: int
    response_breached_count: int
    resolution_breached_count: int


@dataclass(frozen=True)
class UnmatchedIncidentSlaRow:
    inc_number: str
    row_count: int


def append_sample_message(messages: list[str], message: str) -> None:
    if len(messages) < MAX_MESSAGE_SAMPLES:
        messages.append(message)


def get_raw_value(raw_data: dict[str, Any], *aliases: str) -> Any:
    for alias in aliases:
        if alias in raw_data:
            return raw_data[alias]

    normalized_lookup = {
        normalize_source_column_name(column_name): value
        for column_name, value in raw_data.items()
    }
    for alias in aliases:
        normalized_alias = normalize_source_column_name(alias)
        if normalized_alias in normalized_lookup:
            return normalized_lookup[normalized_alias]

    return None


def parse_optional_duration_seconds(value: Any) -> int | None:
    return parse_business_duration_seconds(value)


def build_incident_sla_row(
    project_id: UUID,
    uploaded_file_name: str,
    source_row_number: int,
    raw_data: dict[str, Any],
    result: IncidentSlaUploadResult,
) -> IncidentSlaRow | None:
    inc_number = text_or_none(get_raw_value(raw_data, "inc_number", "number", "ticket_number"))
    if inc_number is None:
        result.failed_rows += 1
        append_sample_message(
            result.errors,
            f"Row {source_row_number}: inc_number is required.",
        )
        return None

    duration_value = get_raw_value(raw_data, "taskslatable_duration")
    business_duration_value = get_raw_value(raw_data, "taskslatable_business_duration")
    has_breached_value = get_raw_value(raw_data, "taskslatable_has_breached")

    duration_seconds = parse_optional_duration_seconds(duration_value)
    if text_or_none(duration_value) is not None and duration_seconds is None:
        append_sample_message(
            result.warnings,
            f"Row {source_row_number}: taskslatable_duration could not be parsed.",
        )

    business_duration_seconds = parse_optional_duration_seconds(business_duration_value)
    if text_or_none(business_duration_value) is not None and business_duration_seconds is None:
        append_sample_message(
            result.warnings,
            f"Row {source_row_number}: taskslatable_business_duration could not be parsed.",
        )

    has_breached = parse_bool_value(has_breached_value)
    if text_or_none(has_breached_value) is not None and has_breached is None:
        append_sample_message(
            result.warnings,
            f"Row {source_row_number}: taskslatable_has_breached could not be parsed.",
        )

    return IncidentSlaRow(
        project_id=project_id,
        uploaded_file_name=uploaded_file_name,
        source_row_number=source_row_number,
        inc_number=inc_number,
        inc_priority=text_or_none(get_raw_value(raw_data, "inc_priority", "priority")),
        taskslatable_stage=text_or_none(get_raw_value(raw_data, "taskslatable_stage")),
        assignment_group_name=text_or_none(
            get_raw_value(raw_data, "inc_assignment_group.name", "assignment_group_name")
        ),
        taskslatable_duration_seconds=duration_seconds,
        taskslatable_business_duration_seconds=business_duration_seconds,
        taskslatable_has_breached=has_breached,
        taskslatable_sla_sys_name=text_or_none(
            get_raw_value(raw_data, "taskslatable_sla.sys_name")
        ),
        taskslatable_sla_name=text_or_none(get_raw_value(raw_data, "taskslatable_sla.name")),
        taskslatable_sla_type=text_or_none(get_raw_value(raw_data, "taskslatable_sla.type")),
        taskslatable_sla_target=text_or_none(get_raw_value(raw_data, "taskslatable_sla.target")),
        raw_data=raw_data,
    )


def upload_incident_sla_csv(
    db: Session,
    project_id: UUID,
    csv_path: Path,
    uploaded_file_name: str,
) -> IncidentSlaUploadResult:
    project = db.get(Project, project_id)
    if project is None:
        raise FileNotFoundError(f"Project {project_id} was not found.")

    result = IncidentSlaUploadResult(project_id=project_id, uploaded_file_name=uploaded_file_name)
    pending_rows: list[IncidentSlaRow] = []

    try:
        for parsed_row in iter_csv_rows(csv_path):
            result.total_rows += 1
            sla_row = build_incident_sla_row(
                project_id=project_id,
                uploaded_file_name=uploaded_file_name,
                source_row_number=parsed_row.row_number,
                raw_data=parsed_row.raw_data,
                result=result,
            )
            if sla_row is None:
                continue

            pending_rows.append(sla_row)
            result.inserted_rows += 1

            if len(pending_rows) >= INGESTION_BATCH_SIZE:
                db.add_all(pending_rows)
                db.commit()
                pending_rows.clear()

        if pending_rows:
            db.add_all(pending_rows)
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise IncidentSlaError(f"Incident SLA rows could not be saved: {exc}") from exc
    except Exception as exc:
        db.rollback()
        if isinstance(exc, IncidentSlaError):
            raise
        raise IncidentSlaError(f"Incident SLA file could not be parsed: {exc}") from exc

    return result


def reset_incident_sla_columns(db: Session, project_id: UUID) -> None:
    db.execute(
        update(Ticket)
        .where(Ticket.project_id == project_id, Ticket.ticket_type == INCIDENT_TICKET_TYPE)
        .values(
            response_sla_breached=None,
            resolution_sla_breached=None,
            response_sla_business_elapsed_seconds=None,
            resolution_sla_business_elapsed_seconds=None,
            response_sla_name=None,
            resolution_sla_name=None,
            response_sla_updated_at=None,
            resolution_sla_updated_at=None,
            sla_enriched_at=None,
        )
    )


def update_incident_sla_target(
    db: Session,
    project_id: UUID,
    *,
    sla_target: str,
    breached_column: str,
    business_elapsed_column: str,
    name_column: str,
    updated_at_column: str,
    replace_existing: bool,
) -> int:
    replace_filter = "" if replace_existing else f"AND t.{name_column} IS NULL"
    statement = text(
        f"""
        WITH ranked_sla AS (
            SELECT
                s.inc_number,
                s.taskslatable_has_breached,
                s.taskslatable_business_duration_seconds,
                s.taskslatable_sla_name,
                row_number() OVER (
                    PARTITION BY s.inc_number
                    ORDER BY
                        CASE
                            WHEN lower(coalesce(s.taskslatable_sla_name, '')) LIKE '%accenture%'
                                THEN 0
                            WHEN lower(coalesce(s.taskslatable_sla_name, '')) LIKE '%default%'
                                THEN 1
                            ELSE 2
                        END,
                        CASE
                            WHEN lower(coalesce(s.taskslatable_stage, '')) = 'completed'
                                THEN 0
                            ELSE 1
                        END,
                        s.source_row_number ASC,
                        s.id ASC
                ) AS row_rank
            FROM incident_sla_rows AS s
            WHERE s.project_id = CAST(:project_id AS uuid)
              AND lower(coalesce(s.taskslatable_sla_target, '')) = :sla_target
        )
        UPDATE tickets AS t
        SET
            {breached_column} = ranked_sla.taskslatable_has_breached,
            {business_elapsed_column} = ranked_sla.taskslatable_business_duration_seconds,
            {name_column} = ranked_sla.taskslatable_sla_name,
            {updated_at_column} = now(),
            sla_enriched_at = now()
        FROM ranked_sla
        WHERE ranked_sla.row_rank = 1
          AND t.project_id = CAST(:project_id AS uuid)
          AND t.ticket_type = 'INCIDENT'
          AND t.ticket_number = ranked_sla.inc_number
          {replace_filter}
        """
    )
    result = db.execute(
        statement,
        {"project_id": str(project_id), "sla_target": sla_target},
    )
    return int(result.rowcount or 0)


def count_matched_incident_tickets(db: Session, project_id: UUID) -> int:
    statement = (
        select(func.count(func.distinct(Ticket.id)))
        .join(
            IncidentSlaRow,
            (IncidentSlaRow.project_id == Ticket.project_id)
            & (IncidentSlaRow.inc_number == Ticket.ticket_number),
        )
        .where(Ticket.project_id == project_id, Ticket.ticket_type == INCIDENT_TICKET_TYPE)
    )
    return int(db.scalar(statement) or 0)


def enrich_incident_sla(
    db: Session,
    project_id: UUID,
    ticket_type: str,
    replace_existing: bool,
) -> IncidentSlaEnrichResult:
    if ticket_type.strip().upper() != INCIDENT_TICKET_TYPE:
        raise IncidentSlaError("Only INCIDENT tickets can be enriched with Incident SLA rows.")

    project = db.get(Project, project_id)
    if project is None:
        raise FileNotFoundError(f"Project {project_id} was not found.")

    if replace_existing:
        reset_incident_sla_columns(db, project_id)

    response_count = update_incident_sla_target(
        db,
        project_id,
        sla_target=SLA_TARGET_RESPONSE,
        breached_column="response_sla_breached",
        business_elapsed_column="response_sla_business_elapsed_seconds",
        name_column="response_sla_name",
        updated_at_column="response_sla_updated_at",
        replace_existing=replace_existing,
    )
    resolution_count = update_incident_sla_target(
        db,
        project_id,
        sla_target=SLA_TARGET_RESOLUTION,
        breached_column="resolution_sla_breached",
        business_elapsed_column="resolution_sla_business_elapsed_seconds",
        name_column="resolution_sla_name",
        updated_at_column="resolution_sla_updated_at",
        replace_existing=replace_existing,
    )
    matched_ticket_count = count_matched_incident_tickets(db, project_id)
    db.commit()

    warnings = [
        "Selection tie-breaker is Accenture first, then Default, then Completed stage, "
        "then lowest source row number."
    ]
    return IncidentSlaEnrichResult(
        project_id=project_id,
        ticket_type=INCIDENT_TICKET_TYPE,
        replace_existing=replace_existing,
        matched_ticket_count=matched_ticket_count,
        response_sla_updated_count=response_count,
        resolution_sla_updated_count=resolution_count,
        warnings=warnings,
    )


def count_ticket_condition(db: Session, project_id: UUID, condition) -> int:
    statement = select(func.count(Ticket.id)).where(
        Ticket.project_id == project_id,
        Ticket.ticket_type == INCIDENT_TICKET_TYPE,
        condition,
    )
    return int(db.scalar(statement) or 0)


def incident_sla_summary(db: Session, project_id: UUID) -> IncidentSlaSummary:
    project = db.get(Project, project_id)
    if project is None:
        raise FileNotFoundError(f"Project {project_id} was not found.")

    total_sla_rows = int(
        db.scalar(
            select(func.count(IncidentSlaRow.id)).where(IncidentSlaRow.project_id == project_id)
        )
        or 0
    )
    unique_incident_numbers = int(
        db.scalar(
            select(func.count(func.distinct(IncidentSlaRow.inc_number))).where(
                IncidentSlaRow.project_id == project_id
            )
        )
        or 0
    )
    matched_tickets_count = count_matched_incident_tickets(db, project_id)
    unmatched_count = int(
        db.scalar(
            text(
                """
                SELECT count(*)
                FROM (
                    SELECT s.inc_number
                    FROM incident_sla_rows AS s
                    WHERE s.project_id = CAST(:project_id AS uuid)
                    GROUP BY s.inc_number
                    HAVING NOT EXISTS (
                        SELECT 1
                        FROM tickets AS t
                        WHERE t.project_id = CAST(:project_id AS uuid)
                          AND t.ticket_type = 'INCIDENT'
                          AND t.ticket_number = s.inc_number
                    )
                ) AS unmatched
                """
            ),
            {"project_id": str(project_id)},
        )
        or 0
    )

    return IncidentSlaSummary(
        project_id=project_id,
        total_sla_rows=total_sla_rows,
        unique_incident_numbers=unique_incident_numbers,
        matched_tickets_count=matched_tickets_count,
        unmatched_sla_incident_numbers_count=unmatched_count,
        tickets_with_response_sla_selected=count_ticket_condition(
            db,
            project_id,
            Ticket.response_sla_name.is_not(None),
        ),
        tickets_with_resolution_sla_selected=count_ticket_condition(
            db,
            project_id,
            Ticket.resolution_sla_name.is_not(None),
        ),
        response_accenture_selected_count=count_ticket_condition(
            db,
            project_id,
            func.lower(func.coalesce(Ticket.response_sla_name, "")).like("%accenture%"),
        ),
        response_default_selected_count=count_ticket_condition(
            db,
            project_id,
            func.lower(func.coalesce(Ticket.response_sla_name, "")).like("%default%"),
        ),
        resolution_accenture_selected_count=count_ticket_condition(
            db,
            project_id,
            func.lower(func.coalesce(Ticket.resolution_sla_name, "")).like("%accenture%"),
        ),
        resolution_default_selected_count=count_ticket_condition(
            db,
            project_id,
            func.lower(func.coalesce(Ticket.resolution_sla_name, "")).like("%default%"),
        ),
        response_breached_count=count_ticket_condition(
            db,
            project_id,
            Ticket.response_sla_breached.is_(True),
        ),
        resolution_breached_count=count_ticket_condition(
            db,
            project_id,
            Ticket.resolution_sla_breached.is_(True),
        ),
    )


def unmatched_incident_sla_numbers(
    db: Session,
    project_id: UUID,
    limit: int,
    offset: int,
) -> list[UnmatchedIncidentSlaRow]:
    project = db.get(Project, project_id)
    if project is None:
        raise FileNotFoundError(f"Project {project_id} was not found.")

    rows = db.execute(
        text(
            """
            SELECT s.inc_number, count(*) AS row_count
            FROM incident_sla_rows AS s
            WHERE s.project_id = CAST(:project_id AS uuid)
            GROUP BY s.inc_number
            HAVING NOT EXISTS (
                SELECT 1
                FROM tickets AS t
                WHERE t.project_id = CAST(:project_id AS uuid)
                  AND t.ticket_type = 'INCIDENT'
                  AND t.ticket_number = s.inc_number
            )
            ORDER BY s.inc_number
            LIMIT :limit
            OFFSET :offset
            """
        ),
        {"project_id": str(project_id), "limit": limit, "offset": offset},
    )
    return [
        UnmatchedIncidentSlaRow(inc_number=str(inc_number), row_count=int(row_count))
        for inc_number, row_count in rows
    ]


def delete_incident_sla_rows_for_project(db: Session, project_id: UUID) -> None:
    db.execute(delete(IncidentSlaRow).where(IncidentSlaRow.project_id == project_id))
