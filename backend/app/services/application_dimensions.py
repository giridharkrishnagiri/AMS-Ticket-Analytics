from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import func, select, text, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models import ApplicationDimension, Project, Ticket
from app.services.ingestion import iter_csv_rows, normalize_source_column_name

MAX_MESSAGE_SAMPLES = 50
TOP_UNMATCHED_LIMIT = 10
MATCH_SOURCE_KEYS = (
    "application_alias",
    "application_name",
    "business_service_alias",
    "cmdb_ci_alias",
    "service_offering",
    "catalog_item",
)


class ApplicationDimensionError(Exception):
    pass


@dataclass
class BulkUploadResult:
    project_id: UUID
    total_rows: int = 0
    inserted_count: int = 0
    updated_count: int = 0
    skipped_count: int = 0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ValueCount:
    value: str
    count: int


@dataclass(frozen=True)
class EnrichmentSummary:
    project_id: UUID
    total_tickets: int
    matched_tickets: int
    unmatched_tickets: int
    updated_tickets: int
    match_rate_pct: float | None
    match_counts_by_source: dict[str, int]
    top_unmatched_applications: list[ValueCount]
    top_unmatched_business_services: list[ValueCount]
    top_unmatched_cmdb_ci: list[ValueCount]
    top_unmatched_service_offerings: list[ValueCount]
    top_unmatched_catalog_items: list[ValueCount]


def clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text_value = str(value).strip()
    return text_value or None


def clean_payload(payload: dict[str, Any]) -> dict[str, Any]:
    cleaned = {
        "customer_name": clean_text(payload.get("customer_name")),
        "tower_name": clean_text(payload.get("tower_name")),
        "cluster_name": clean_text(payload.get("cluster_name")),
        "application_group_name": clean_text(payload.get("application_group_name")),
        "application_name": clean_text(payload.get("application_name")),
        "application_alias": clean_text(payload.get("application_alias")),
        "business_service_alias": clean_text(payload.get("business_service_alias")),
        "cmdb_ci_alias": clean_text(payload.get("cmdb_ci_alias")),
        "notes": clean_text(payload.get("notes")),
        "is_active": bool(payload.get("is_active", True)),
    }
    if cleaned["application_name"] is None:
        raise ApplicationDimensionError("application_name is required.")
    return cleaned


def append_sample_message(messages: list[str], message: str) -> None:
    if len(messages) < MAX_MESSAGE_SAMPLES:
        messages.append(message)


def get_project_or_raise(db: Session, project_id: UUID) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise FileNotFoundError(f"Project {project_id} was not found.")
    return project


def list_application_dimensions(db: Session, project_id: UUID) -> list[ApplicationDimension]:
    get_project_or_raise(db, project_id)
    statement = (
        select(ApplicationDimension)
        .where(ApplicationDimension.project_id == project_id)
        .order_by(
            ApplicationDimension.is_active.desc(),
            ApplicationDimension.application_name.asc(),
            ApplicationDimension.application_alias.asc(),
        )
    )
    return list(db.scalars(statement).all())


def create_application_dimension(
    db: Session,
    payload: dict[str, Any],
) -> ApplicationDimension:
    project_id = payload["project_id"]
    get_project_or_raise(db, project_id)
    cleaned = clean_payload(payload)
    dimension = ApplicationDimension(project_id=project_id, **cleaned)
    db.add(dimension)
    db.commit()
    db.refresh(dimension)
    return dimension


def update_application_dimension(
    db: Session,
    dimension_id: UUID,
    payload: dict[str, Any],
) -> ApplicationDimension:
    dimension = db.get(ApplicationDimension, dimension_id)
    if dimension is None:
        raise FileNotFoundError(f"Application dimension {dimension_id} was not found.")

    for field_name in (
        "customer_name",
        "tower_name",
        "cluster_name",
        "application_group_name",
        "application_name",
        "application_alias",
        "business_service_alias",
        "cmdb_ci_alias",
        "notes",
    ):
        if field_name in payload:
            next_value = clean_text(payload.get(field_name))
            if field_name == "application_name" and next_value is None:
                raise ApplicationDimensionError("application_name is required.")
            setattr(dimension, field_name, next_value)

    if "is_active" in payload and payload["is_active"] is not None:
        dimension.is_active = bool(payload["is_active"])

    db.commit()
    db.refresh(dimension)
    return dimension


def deactivate_application_dimension(db: Session, dimension_id: UUID) -> ApplicationDimension:
    dimension = db.get(ApplicationDimension, dimension_id)
    if dimension is None:
        raise FileNotFoundError(f"Application dimension {dimension_id} was not found.")
    dimension.is_active = False
    db.commit()
    db.refresh(dimension)
    return dimension


def source_value(raw_data: dict[str, Any], column_name: str) -> Any:
    if column_name in raw_data:
        return raw_data[column_name]
    normalized_lookup = {
        normalize_source_column_name(key): value for key, value in raw_data.items()
    }
    return normalized_lookup.get(normalize_source_column_name(column_name))


def find_duplicate_dimension(
    db: Session,
    project_id: UUID,
    cleaned: dict[str, Any],
) -> ApplicationDimension | None:
    statement = select(ApplicationDimension).where(
        ApplicationDimension.project_id == project_id,
        ApplicationDimension.application_name == cleaned["application_name"],
        ApplicationDimension.application_alias.is_not_distinct_from(
            cleaned["application_alias"]
        ),
        ApplicationDimension.business_service_alias.is_not_distinct_from(
            cleaned["business_service_alias"]
        ),
        ApplicationDimension.cmdb_ci_alias.is_not_distinct_from(cleaned["cmdb_ci_alias"]),
    )
    return db.scalar(statement.limit(1))


def upload_application_dimensions_csv(
    db: Session,
    project_id: UUID,
    csv_path: Path,
) -> BulkUploadResult:
    get_project_or_raise(db, project_id)
    result = BulkUploadResult(project_id=project_id)

    try:
        for parsed_row in iter_csv_rows(csv_path):
            result.total_rows += 1
            raw_payload = {
                "customer_name": source_value(parsed_row.raw_data, "customer_name"),
                "tower_name": source_value(parsed_row.raw_data, "tower_name"),
                "cluster_name": source_value(parsed_row.raw_data, "cluster_name"),
                "application_group_name": source_value(
                    parsed_row.raw_data,
                    "application_group_name",
                ),
                "application_name": source_value(parsed_row.raw_data, "application_name"),
                "application_alias": source_value(parsed_row.raw_data, "application_alias"),
                "business_service_alias": source_value(
                    parsed_row.raw_data,
                    "business_service_alias",
                ),
                "cmdb_ci_alias": source_value(parsed_row.raw_data, "cmdb_ci_alias"),
                "notes": source_value(parsed_row.raw_data, "notes"),
                "is_active": True,
            }
            try:
                cleaned = clean_payload(raw_payload)
            except ApplicationDimensionError as exc:
                result.skipped_count += 1
                append_sample_message(result.errors, f"Row {parsed_row.row_number}: {exc}")
                continue

            existing = find_duplicate_dimension(db, project_id, cleaned)
            if existing is None:
                db.add(ApplicationDimension(project_id=project_id, **cleaned))
                db.flush()
                result.inserted_count += 1
            else:
                for field_name, value in cleaned.items():
                    setattr(existing, field_name, value)
                result.updated_count += 1

        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise ApplicationDimensionError(
            f"Application dimensions could not be saved: {exc}"
        ) from exc
    except Exception as exc:
        db.rollback()
        if isinstance(exc, ApplicationDimensionError):
            raise
        raise ApplicationDimensionError(
            f"Application dimension CSV could not be parsed: {exc}"
        ) from exc

    return result


def clear_ticket_dimension_values(db: Session, project_id: UUID) -> None:
    db.execute(
        update(Ticket)
        .where(Ticket.project_id == project_id)
        .values(
            application_dimension_id=None,
            customer_name=None,
            tower_name=None,
            cluster_name=None,
            application_group_name=None,
            application_name=None,
        )
    )


def update_tickets_for_match(
    db: Session,
    project_id: UUID,
    *,
    ticket_column: str,
    dimension_column: str,
) -> int:
    statement = text(
        f"""
        WITH candidates AS (
            SELECT
                t.id AS ticket_id,
                d.id AS dimension_id,
                d.customer_name,
                d.tower_name,
                d.cluster_name,
                d.application_group_name,
                d.application_name,
                row_number() OVER (
                    PARTITION BY t.id
                    ORDER BY d.updated_at DESC, d.id ASC
                ) AS row_rank
            FROM tickets AS t
            JOIN application_dimensions AS d
              ON d.project_id = t.project_id
             AND d.is_active = true
             AND nullif(btrim(t.{ticket_column}), '') IS NOT NULL
             AND nullif(btrim(d.{dimension_column}), '') IS NOT NULL
             AND lower(btrim(t.{ticket_column})) = lower(btrim(d.{dimension_column}))
            WHERE t.project_id = CAST(:project_id AS uuid)
              AND t.application_dimension_id IS NULL
        )
        UPDATE tickets AS t
        SET
            application_dimension_id = candidates.dimension_id,
            customer_name = candidates.customer_name,
            tower_name = candidates.tower_name,
            cluster_name = candidates.cluster_name,
            application_group_name = candidates.application_group_name,
            application_name = candidates.application_name
        FROM candidates
        WHERE candidates.row_rank = 1
          AND t.id = candidates.ticket_id
        """
    )
    result = db.execute(statement, {"project_id": str(project_id)})
    return int(result.rowcount or 0)


def count_tickets(db: Session, project_id: UUID, *, matched: bool | None = None) -> int:
    statement = select(func.count(Ticket.id)).where(Ticket.project_id == project_id)
    if matched is True:
        statement = statement.where(Ticket.application_dimension_id.is_not(None))
    elif matched is False:
        statement = statement.where(Ticket.application_dimension_id.is_(None))
    return int(db.scalar(statement) or 0)


def top_unmatched_values(db: Session, project_id: UUID, column: Any) -> list[ValueCount]:
    statement = (
        select(column, func.count(Ticket.id))
        .where(
            Ticket.project_id == project_id,
            Ticket.application_dimension_id.is_(None),
            column.is_not(None),
            func.btrim(column) != "",
        )
        .group_by(column)
        .order_by(func.count(Ticket.id).desc(), column.asc())
        .limit(TOP_UNMATCHED_LIMIT)
    )
    return [
        ValueCount(value=str(value), count=int(count))
        for value, count in db.execute(statement)
    ]


def build_enrichment_summary(
    db: Session,
    project_id: UUID,
    *,
    updated_tickets: int = 0,
    match_counts_by_source: dict[str, int] | None = None,
) -> EnrichmentSummary:
    get_project_or_raise(db, project_id)
    total_tickets = count_tickets(db, project_id)
    matched_tickets = count_tickets(db, project_id, matched=True)
    unmatched_tickets = max(total_tickets - matched_tickets, 0)
    match_rate_pct = matched_tickets / total_tickets * 100 if total_tickets else None
    return EnrichmentSummary(
        project_id=project_id,
        total_tickets=total_tickets,
        matched_tickets=matched_tickets,
        unmatched_tickets=unmatched_tickets,
        updated_tickets=updated_tickets,
        match_rate_pct=match_rate_pct,
        match_counts_by_source={
            key: int((match_counts_by_source or {}).get(key, 0)) for key in MATCH_SOURCE_KEYS
        },
        top_unmatched_applications=top_unmatched_values(db, project_id, Ticket.application),
        top_unmatched_business_services=top_unmatched_values(
            db,
            project_id,
            Ticket.business_service,
        ),
        top_unmatched_cmdb_ci=top_unmatched_values(db, project_id, Ticket.cmdb_ci),
        top_unmatched_service_offerings=top_unmatched_values(
            db,
            project_id,
            Ticket.service_offering,
        ),
        top_unmatched_catalog_items=top_unmatched_values(db, project_id, Ticket.catalog_item),
    )


def enrich_tickets_with_application_dimensions(
    db: Session,
    project_id: UUID,
    replace_existing: bool,
) -> EnrichmentSummary:
    get_project_or_raise(db, project_id)
    match_counts: dict[str, int] = {key: 0 for key in MATCH_SOURCE_KEYS}

    try:
        if replace_existing:
            clear_ticket_dimension_values(db, project_id)
            db.flush()

        match_counts["application_alias"] = update_tickets_for_match(
            db,
            project_id,
            ticket_column="application",
            dimension_column="application_alias",
        )
        match_counts["application_name"] = update_tickets_for_match(
            db,
            project_id,
            ticket_column="application",
            dimension_column="application_name",
        )
        match_counts["business_service_alias"] = update_tickets_for_match(
            db,
            project_id,
            ticket_column="business_service",
            dimension_column="business_service_alias",
        )
        match_counts["cmdb_ci_alias"] = update_tickets_for_match(
            db,
            project_id,
            ticket_column="cmdb_ci",
            dimension_column="cmdb_ci_alias",
        )
        match_counts["service_offering"] = update_tickets_for_match(
            db,
            project_id,
            ticket_column="service_offering",
            dimension_column="business_service_alias",
        )
        match_counts["catalog_item"] = update_tickets_for_match(
            db,
            project_id,
            ticket_column="catalog_item",
            dimension_column="application_alias",
        )
        updated_tickets = sum(match_counts.values())
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise ApplicationDimensionError(f"Ticket enrichment failed: {exc}") from exc

    return build_enrichment_summary(
        db,
        project_id,
        updated_tickets=updated_tickets,
        match_counts_by_source=match_counts,
    )
