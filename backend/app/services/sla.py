from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import delete, func, select, text, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models import (
    AssessmentOutOfScopeTicket,
    IncidentSlaRow,
    IncidentSlaUpload,
    Project,
    Ticket,
)
from app.services.ingestion import (
    INGESTION_BATCH_SIZE,
    iter_ticket_file_rows,
    normalize_source_column_name,
)
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
    upload_id: UUID | None = None
    status: str = "UPLOADED"
    total_rows: int = 0
    inserted_rows: int = 0
    duplicate_rows_skipped: int = 0
    failed_rows: int = 0
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class IncidentSlaUploadTotals:
    total_files: int
    total_rows_read: int
    inserted_rows: int
    duplicate_rows_skipped: int
    error_rows: int


@dataclass(frozen=True)
class IncidentSlaMultiUploadResult:
    project_id: UUID
    files: list[IncidentSlaUploadResult]
    totals: IncidentSlaUploadTotals


@dataclass(frozen=True)
class IncidentSlaUploadHistoryRow:
    upload_id: UUID
    filename: str
    uploaded_at: datetime
    total_rows_read: int
    inserted_rows: int
    duplicate_rows_skipped: int
    error_rows: int
    status: str


@dataclass(frozen=True)
class IncidentSlaScopeStats:
    incident_tickets_considered: int
    incident_tickets_matched_to_sla_rows: int
    incident_tickets_enriched: int
    response_sla_enriched: int
    resolution_sla_enriched: int
    response_vendor_specific: int
    response_default: int
    response_fallback_default: int
    response_not_found: int
    resolution_vendor_specific: int
    resolution_default: int
    resolution_fallback_default: int
    resolution_not_found: int


@dataclass(frozen=True)
class IncidentSlaRowsStats:
    total_rows: int
    distinct_ticket_numbers_in_sla_rows: int
    duplicate_rows_skipped_on_upload: int


@dataclass(frozen=True)
class IncidentSlaUnmatchedStats:
    sla_ticket_numbers_not_found_in_scope_or_out_of_scope: int
    in_scope_incidents_without_sla_rows: int
    out_of_scope_incidents_without_sla_rows: int


@dataclass(frozen=True)
class IncidentSlaEnrichResult:
    project_id: UUID
    ticket_type: str
    replace_existing: bool
    matched_ticket_count: int
    response_sla_updated_count: int
    resolution_sla_updated_count: int
    in_scope_incidents_considered: int
    in_scope_incidents_enriched: int
    out_of_scope_incidents_considered: int
    out_of_scope_incidents_enriched: int
    response_vendor_specific_count: int
    response_default_count: int
    resolution_vendor_specific_count: int
    resolution_default_count: int
    missing_response_sla_count: int
    missing_resolution_sla_count: int
    sla_rows: IncidentSlaRowsStats
    in_scope: IncidentSlaScopeStats
    out_of_scope: IncidentSlaScopeStats
    unmatched: IncidentSlaUnmatchedStats
    warnings: list[str]


@dataclass(frozen=True)
class IncidentSlaDeduplicateResult:
    project_id: UUID
    duplicate_groups_found: int
    duplicate_rows_deleted: int
    remaining_sla_rows: int


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


@dataclass(frozen=True)
class IncidentSlaCandidate:
    row_id: UUID
    inc_number: str
    stage: str | None
    business_duration_seconds: int | None
    has_breached: bool | None
    sla_name: str | None
    sla_type: str | None
    sla_target: str | None
    source_row_number: int


@dataclass(frozen=True)
class SelectedIncidentSlaCandidate:
    candidate: IncidentSlaCandidate
    selection_source: str
    effective_vendor: str | None


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


def normalize_fingerprint_key(key: Any) -> str:
    return str(key).strip()


def normalize_fingerprint_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip()
    return value


def canonicalize_raw_row(raw_data: dict[str, Any]) -> dict[str, Any]:
    canonical: dict[str, Any] = {}
    for key, value in raw_data.items():
        canonical[normalize_fingerprint_key(key)] = normalize_fingerprint_value(value)
    return canonical


def build_row_fingerprint(raw_data: dict[str, Any]) -> str:
    canonical_json = json.dumps(
        canonicalize_raw_row(raw_data),
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


def existing_row_fingerprints(db: Session, project_id: UUID) -> set[str]:
    return {
        str(fingerprint)
        for fingerprint in db.scalars(
            select(IncidentSlaRow.row_fingerprint).where(
                IncidentSlaRow.project_id == project_id,
                IncidentSlaRow.row_fingerprint.is_not(None),
            )
        )
        if fingerprint
    }


def parse_optional_duration_seconds(value: Any) -> int | None:
    return parse_business_duration_seconds(value)


def build_incident_sla_row(
    project_id: UUID,
    uploaded_file_name: str,
    source_row_number: int,
    raw_data: dict[str, Any],
    row_fingerprint: str,
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
        row_fingerprint=row_fingerprint,
        raw_data=raw_data,
    )


def record_incident_sla_upload(
    db: Session,
    project_id: UUID,
    result: IncidentSlaUploadResult,
) -> None:
    upload = IncidentSlaUpload(
        project_id=project_id,
        filename=result.uploaded_file_name,
        total_rows_read=result.total_rows,
        inserted_rows=result.inserted_rows,
        duplicate_rows_skipped=result.duplicate_rows_skipped,
        error_rows=result.failed_rows,
        status=result.status,
    )
    db.add(upload)
    db.flush()
    result.upload_id = upload.id


def upload_incident_sla_file(
    db: Session,
    project_id: UUID,
    file_path: Path,
    uploaded_file_name: str,
) -> IncidentSlaUploadResult:
    project = db.get(Project, project_id)
    if project is None:
        raise FileNotFoundError(f"Project {project_id} was not found.")

    result = IncidentSlaUploadResult(project_id=project_id, uploaded_file_name=uploaded_file_name)
    pending_rows: list[IncidentSlaRow] = []
    backfill_missing_sla_fingerprints(db, project_id)
    known_fingerprints = existing_row_fingerprints(db, project_id)
    upload_fingerprints: set[str] = set()

    try:
        for parsed_row in iter_ticket_file_rows(file_path):
            result.total_rows += 1
            row_fingerprint = build_row_fingerprint(parsed_row.raw_data)
            if row_fingerprint in known_fingerprints or row_fingerprint in upload_fingerprints:
                result.duplicate_rows_skipped += 1
                continue

            sla_row = build_incident_sla_row(
                project_id=project_id,
                uploaded_file_name=uploaded_file_name,
                source_row_number=parsed_row.row_number,
                raw_data=parsed_row.raw_data,
                row_fingerprint=row_fingerprint,
                result=result,
            )
            if sla_row is None:
                continue

            pending_rows.append(sla_row)
            upload_fingerprints.add(row_fingerprint)
            result.inserted_rows += 1

            if len(pending_rows) >= INGESTION_BATCH_SIZE:
                db.add_all(pending_rows)
                db.flush()
                known_fingerprints.update(upload_fingerprints)
                upload_fingerprints.clear()
                pending_rows.clear()

        if pending_rows:
            db.add_all(pending_rows)
        record_incident_sla_upload(db, project_id, result)
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


def upload_incident_sla_csv(
    db: Session,
    project_id: UUID,
    csv_path: Path,
    uploaded_file_name: str,
) -> IncidentSlaUploadResult:
    return upload_incident_sla_file(db, project_id, csv_path, uploaded_file_name)


def build_multi_upload_totals(
    project_id: UUID,
    files: list[IncidentSlaUploadResult],
) -> IncidentSlaMultiUploadResult:
    return IncidentSlaMultiUploadResult(
        project_id=project_id,
        files=files,
        totals=IncidentSlaUploadTotals(
            total_files=len(files),
            total_rows_read=sum(file.total_rows for file in files),
            inserted_rows=sum(file.inserted_rows for file in files),
            duplicate_rows_skipped=sum(file.duplicate_rows_skipped for file in files),
            error_rows=sum(file.failed_rows for file in files),
        ),
    )


def list_incident_sla_uploads(
    db: Session,
    project_id: UUID,
) -> list[IncidentSlaUploadHistoryRow]:
    project = db.get(Project, project_id)
    if project is None:
        raise FileNotFoundError(f"Project {project_id} was not found.")

    statement = (
        select(IncidentSlaUpload)
        .where(IncidentSlaUpload.project_id == project_id)
        .order_by(IncidentSlaUpload.uploaded_at.desc(), IncidentSlaUpload.id.desc())
    )
    return [
        IncidentSlaUploadHistoryRow(
            upload_id=upload.id,
            filename=upload.filename,
            uploaded_at=upload.uploaded_at,
            total_rows_read=upload.total_rows_read,
            inserted_rows=upload.inserted_rows,
            duplicate_rows_skipped=upload.duplicate_rows_skipped,
            error_rows=upload.error_rows,
            status=upload.status,
        )
        for upload in db.scalars(statement).all()
    ]


def backfill_missing_sla_fingerprints(db: Session, project_id: UUID) -> int:
    updated_rows = 0
    statement = (
        select(IncidentSlaRow)
        .where(
            IncidentSlaRow.project_id == project_id,
            IncidentSlaRow.row_fingerprint.is_(None),
            IncidentSlaRow.raw_data.is_not(None),
        )
        .order_by(IncidentSlaRow.ingested_at.asc(), IncidentSlaRow.id.asc())
    )
    for row in db.scalars(statement).yield_per(INGESTION_BATCH_SIZE):
        if row.raw_data:
            row.row_fingerprint = build_row_fingerprint(row.raw_data)
            updated_rows += 1
        if updated_rows and updated_rows % INGESTION_BATCH_SIZE == 0:
            db.flush()
    if updated_rows:
        db.flush()
    return updated_rows


def deduplicate_incident_sla_rows(
    db: Session,
    project_id: UUID,
) -> IncidentSlaDeduplicateResult:
    project = db.get(Project, project_id)
    if project is None:
        raise FileNotFoundError(f"Project {project_id} was not found.")

    try:
        backfill_missing_sla_fingerprints(db, project_id)
        duplicate_groups_found = int(
            db.execute(
                text(
                    """
                    SELECT count(*)
                    FROM (
                        SELECT row_fingerprint
                        FROM incident_sla_rows
                        WHERE project_id = CAST(:project_id AS uuid)
                          AND row_fingerprint IS NOT NULL
                        GROUP BY row_fingerprint
                        HAVING count(*) > 1
                    ) AS duplicate_groups
                    """
                ),
                {"project_id": str(project_id)},
            ).scalar_one()
            or 0
        )
        duplicate_rows_deleted = int(
            db.execute(
                text(
                    """
                    WITH ranked AS (
                        SELECT
                            id,
                            row_number() OVER (
                                PARTITION BY project_id, row_fingerprint
                                ORDER BY ingested_at ASC, source_row_number ASC, id ASC
                            ) AS row_rank
                        FROM incident_sla_rows
                        WHERE project_id = CAST(:project_id AS uuid)
                          AND row_fingerprint IS NOT NULL
                    ),
                    deleted AS (
                        DELETE FROM incident_sla_rows AS s
                        USING ranked
                        WHERE s.id = ranked.id
                          AND ranked.row_rank > 1
                        RETURNING s.id
                    )
                    SELECT count(*) FROM deleted
                    """
                ),
                {"project_id": str(project_id)},
            ).scalar_one()
            or 0
        )
        remaining_sla_rows = int(
            db.scalar(
                select(func.count(IncidentSlaRow.id)).where(
                    IncidentSlaRow.project_id == project_id
                )
            )
            or 0
        )
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise IncidentSlaError(f"Incident SLA deduplication failed: {exc}") from exc

    return IncidentSlaDeduplicateResult(
        project_id=project_id,
        duplicate_groups_found=duplicate_groups_found,
        duplicate_rows_deleted=duplicate_rows_deleted,
        remaining_sla_rows=remaining_sla_rows,
    )


def reset_incident_sla_columns(db: Session, project_id: UUID) -> None:
    reset_values = {
        "response_sla_breached": None,
        "resolution_sla_breached": None,
        "response_sla_business_elapsed_seconds": None,
        "resolution_sla_business_elapsed_seconds": None,
        "response_sla_name": None,
        "resolution_sla_name": None,
        "response_sla_definition_name_used": None,
        "resolution_sla_definition_name_used": None,
        "response_sla_selection_source": None,
        "resolution_sla_selection_source": None,
        "response_sla_vendor_used": None,
        "resolution_sla_vendor_used": None,
        "response_sla_updated_at": None,
        "resolution_sla_updated_at": None,
        "sla_enriched_at": None,
    }
    for model in (Ticket, AssessmentOutOfScopeTicket):
        db.execute(
            update(model)
            .where(model.project_id == project_id, model.ticket_type == INCIDENT_TICKET_TYPE)
            .values(**reset_values)
        )


def normalized_text(value: str | None) -> str:
    return (value or "").strip().lower()


def normalized_optional_text(value: str | None) -> str | None:
    cleaned = (value or "").strip()
    return cleaned or None


def sla_candidate_matches_target(candidate: IncidentSlaCandidate, sla_target: str) -> bool:
    target = sla_target.lower()
    return (
        target in normalized_text(candidate.sla_target)
        or target in normalized_text(candidate.sla_type)
        or target in normalized_text(candidate.sla_name)
    )


def load_incident_sla_candidates(
    db: Session,
    project_id: UUID,
) -> dict[str, dict[str, list[IncidentSlaCandidate]]]:
    candidates_by_target: dict[str, dict[str, list[IncidentSlaCandidate]]] = {
        SLA_TARGET_RESPONSE: defaultdict(list),
        SLA_TARGET_RESOLUTION: defaultdict(list),
    }
    statement = (
        select(
            IncidentSlaRow.id,
            IncidentSlaRow.inc_number,
            IncidentSlaRow.taskslatable_stage,
            IncidentSlaRow.taskslatable_business_duration_seconds,
            IncidentSlaRow.taskslatable_has_breached,
            IncidentSlaRow.taskslatable_sla_name,
            IncidentSlaRow.taskslatable_sla_type,
            IncidentSlaRow.taskslatable_sla_target,
            IncidentSlaRow.source_row_number,
        )
        .where(IncidentSlaRow.project_id == project_id)
        .order_by(IncidentSlaRow.inc_number.asc(), IncidentSlaRow.source_row_number.asc())
    )
    for row in db.execute(statement).yield_per(INGESTION_BATCH_SIZE):
        candidate = IncidentSlaCandidate(
            row_id=row.id,
            inc_number=row.inc_number,
            stage=row.taskslatable_stage,
            business_duration_seconds=row.taskslatable_business_duration_seconds,
            has_breached=row.taskslatable_has_breached,
            sla_name=row.taskslatable_sla_name,
            sla_type=row.taskslatable_sla_type,
            sla_target=row.taskslatable_sla_target,
            source_row_number=row.source_row_number,
        )
        if sla_candidate_matches_target(candidate, SLA_TARGET_RESPONSE):
            candidates_by_target[SLA_TARGET_RESPONSE][candidate.inc_number].append(candidate)
        if sla_candidate_matches_target(candidate, SLA_TARGET_RESOLUTION):
            candidates_by_target[SLA_TARGET_RESOLUTION][candidate.inc_number].append(candidate)

    return candidates_by_target


def select_incident_sla_candidate(
    candidates: list[IncidentSlaCandidate],
    *,
    ticket_vendor: str | None,
    derived_vendor: str | None,
) -> SelectedIncidentSlaCandidate | None:
    effective_vendor = normalized_optional_text(ticket_vendor) or normalized_optional_text(
        derived_vendor
    )
    vendor_source = "ticket_vendor" if normalized_optional_text(ticket_vendor) else "derived_vendor"

    def preference(candidate: IncidentSlaCandidate) -> tuple[int, int, int, str]:
        sla_name = normalized_text(candidate.sla_name)
        if effective_vendor and effective_vendor.lower() in sla_name:
            preference_rank = 0
        elif "default" in sla_name:
            preference_rank = 1
        else:
            preference_rank = 2

        stage_rank = 0 if normalized_text(candidate.stage) == "completed" else 1
        return (
            preference_rank,
            stage_rank,
            candidate.source_row_number,
            str(candidate.row_id),
        )

    if not candidates:
        return None

    selected = sorted(candidates, key=preference)[0]
    preference_rank = preference(selected)[0]
    if preference_rank not in {0, 1}:
        return None

    if preference_rank == 0:
        selection_source = vendor_source
    elif effective_vendor is None:
        selection_source = "default"
    else:
        selection_source = "fallback_default"

    return SelectedIncidentSlaCandidate(
        candidate=selected,
        selection_source=selection_source,
        effective_vendor=effective_vendor,
    )


def bulk_update_incident_sla_target(
    db: Session,
    project_id: UUID,
    model,
    *,
    candidates_by_incident: dict[str, list[IncidentSlaCandidate]],
    breached_column: str,
    business_elapsed_column: str,
    name_column: str,
    definition_column: str,
    selection_source_column: str,
    vendor_used_column: str,
    updated_at_column: str,
    replace_existing: bool,
) -> int:
    statement = select(
        model.id,
        model.ticket_number,
        model.vendor,
        model.derived_vendor,
    ).where(
        model.project_id == project_id,
        model.ticket_type == INCIDENT_TICKET_TYPE,
    )
    if not replace_existing:
        statement = statement.where(getattr(model, name_column).is_(None))

    now = datetime.now(UTC)
    updated_count = 0
    pending_updates: list[dict[str, object]] = []
    for row in db.execute(statement).yield_per(INGESTION_BATCH_SIZE):
        selected = select_incident_sla_candidate(
            candidates_by_incident.get(row.ticket_number, []),
            ticket_vendor=row.vendor,
            derived_vendor=row.derived_vendor,
        )
        if selected is None:
            continue

        candidate = selected.candidate
        pending_updates.append(
            {
                "id": row.id,
                breached_column: candidate.has_breached,
                business_elapsed_column: candidate.business_duration_seconds,
                name_column: candidate.sla_name,
                definition_column: candidate.sla_name,
                selection_source_column: selected.selection_source,
                vendor_used_column: selected.effective_vendor,
                updated_at_column: now,
                "sla_enriched_at": now,
            }
        )
        if len(pending_updates) >= INGESTION_BATCH_SIZE:
            db.bulk_update_mappings(model, pending_updates)
            updated_count += len(pending_updates)
            pending_updates.clear()

    if pending_updates:
        db.bulk_update_mappings(model, pending_updates)
        updated_count += len(pending_updates)

    return updated_count


def update_incident_sla_target(
    db: Session,
    project_id: UUID,
    *,
    sla_target: str,
    breached_column: str,
    business_elapsed_column: str,
    name_column: str,
    definition_column: str,
    selection_source_column: str,
    vendor_used_column: str,
    updated_at_column: str,
    replace_existing: bool,
    table_name: str = "tickets",
) -> int:
    if table_name not in {"tickets", "assessment_out_of_scope_tickets"}:
        raise IncidentSlaError(f"Unsupported SLA enrichment table: {table_name}")

    replace_filter = "" if replace_existing else f"AND t.{name_column} IS NULL"
    statement = text(
        f"""
        WITH target_tickets AS (
            SELECT
                t.id,
                t.ticket_number,
                nullif(btrim(t.vendor), '') AS ticket_vendor,
                nullif(btrim(t.derived_vendor), '') AS derived_vendor,
                coalesce(nullif(btrim(t.vendor), ''), nullif(btrim(t.derived_vendor), ''))
                    AS effective_vendor,
                CASE
                    WHEN nullif(btrim(t.vendor), '') IS NOT NULL THEN 'ticket_vendor'
                    WHEN nullif(btrim(t.derived_vendor), '') IS NOT NULL THEN 'derived_vendor'
                    ELSE 'default'
                END AS vendor_source
            FROM {table_name} AS t
            WHERE t.project_id = CAST(:project_id AS uuid)
              AND t.ticket_type = 'INCIDENT'
              {replace_filter}
        ),
        candidate_sla AS (
            SELECT
                t.id AS ticket_id,
                s.taskslatable_has_breached,
                s.taskslatable_business_duration_seconds,
                s.taskslatable_sla_name,
                t.effective_vendor,
                t.vendor_source,
                CASE
                    WHEN t.effective_vendor IS NOT NULL
                     AND lower(coalesce(s.taskslatable_sla_name, ''))
                         LIKE '%' || lower(t.effective_vendor) || '%'
                        THEN 0
                    WHEN lower(coalesce(s.taskslatable_sla_name, '')) LIKE '%default%'
                        THEN 1
                    ELSE 2
                END AS preference_rank,
                row_number() OVER (
                    PARTITION BY t.id
                    ORDER BY
                        CASE
                            WHEN t.effective_vendor IS NOT NULL
                             AND lower(coalesce(s.taskslatable_sla_name, ''))
                                 LIKE '%' || lower(t.effective_vendor) || '%'
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
            FROM target_tickets AS t
            JOIN incident_sla_rows AS s
              ON s.project_id = CAST(:project_id AS uuid)
             AND s.inc_number = t.ticket_number
            WHERE (
                lower(coalesce(s.taskslatable_sla_target, '')) = :sla_target
                OR lower(coalesce(s.taskslatable_sla_type, '')) = :sla_target
                OR lower(coalesce(s.taskslatable_sla_name, '')) LIKE '%' || :sla_target || '%'
              )
        )
        UPDATE {table_name} AS t
        SET
            {breached_column} = candidate_sla.taskslatable_has_breached,
            {business_elapsed_column} = candidate_sla.taskslatable_business_duration_seconds,
            {name_column} = candidate_sla.taskslatable_sla_name,
            {definition_column} = candidate_sla.taskslatable_sla_name,
            {selection_source_column} = CASE
                WHEN candidate_sla.preference_rank = 0 THEN candidate_sla.vendor_source
                WHEN candidate_sla.preference_rank = 1
                 AND candidate_sla.effective_vendor IS NULL THEN 'default'
                WHEN candidate_sla.preference_rank = 1 THEN 'fallback_default'
                ELSE 'not_found'
            END,
            {vendor_used_column} = candidate_sla.effective_vendor,
            {updated_at_column} = now(),
            sla_enriched_at = now()
        FROM candidate_sla
        WHERE candidate_sla.row_rank = 1
          AND candidate_sla.preference_rank IN (0, 1)
          AND t.project_id = CAST(:project_id AS uuid)
          AND t.ticket_type = 'INCIDENT'
          AND t.id = candidate_sla.ticket_id
        """
    )
    result = db.execute(
        statement,
        {"project_id": str(project_id), "sla_target": sla_target},
    )
    return int(result.rowcount or 0)


def mark_missing_incident_sla_target(
    db: Session,
    project_id: UUID,
    *,
    name_column: str,
    selection_source_column: str,
    updated_at_column: str,
    replace_existing: bool,
    table_name: str = "tickets",
) -> int:
    if table_name not in {"tickets", "assessment_out_of_scope_tickets"}:
        raise IncidentSlaError(f"Unsupported SLA enrichment table: {table_name}")

    replace_filter = "" if replace_existing else f"AND {selection_source_column} IS NULL"
    statement = text(
        f"""
        UPDATE {table_name}
        SET
            {selection_source_column} = 'not_found',
            {updated_at_column} = now(),
            sla_enriched_at = now()
        WHERE project_id = CAST(:project_id AS uuid)
          AND ticket_type = 'INCIDENT'
          AND {name_column} IS NULL
          {replace_filter}
        """
    )
    result = db.execute(statement, {"project_id": str(project_id)})
    return int(result.rowcount or 0)


def count_matched_incident_tickets(db: Session, project_id: UUID) -> int:
    return count_matched_incident_tickets_for_model(
        db,
        project_id,
        Ticket,
    ) + count_matched_incident_tickets_for_model(
        db,
        project_id,
        AssessmentOutOfScopeTicket,
    )


def count_matched_incident_tickets_for_model(db: Session, project_id: UUID, model) -> int:
    statement = (
        select(func.count(func.distinct(model.id)))
        .join(
            IncidentSlaRow,
            (IncidentSlaRow.project_id == model.project_id)
            & (IncidentSlaRow.inc_number == model.ticket_number),
        )
        .where(model.project_id == project_id, model.ticket_type == INCIDENT_TICKET_TYPE)
    )
    return int(db.scalar(statement) or 0)


def count_incidents(db: Session, project_id: UUID, model) -> int:
    return int(
        db.scalar(
            select(func.count(model.id)).where(
                model.project_id == project_id,
                model.ticket_type == INCIDENT_TICKET_TYPE,
            )
        )
        or 0
    )


def count_enriched_incidents(db: Session, project_id: UUID, model) -> int:
    return int(
        db.scalar(
            select(func.count(model.id)).where(
                model.project_id == project_id,
                model.ticket_type == INCIDENT_TICKET_TYPE,
                (model.response_sla_name.is_not(None))
                | (model.resolution_sla_name.is_not(None)),
            )
        )
        or 0
    )


def count_named_sla(db: Session, project_id: UUID, model, column) -> int:
    return int(
        db.scalar(
            select(func.count(model.id)).where(
                model.project_id == project_id,
                model.ticket_type == INCIDENT_TICKET_TYPE,
                column.is_not(None),
            )
        )
        or 0
    )


def count_sla_selection_source(
    db: Session,
    project_id: UUID,
    model,
    column,
    sources: tuple[str, ...],
) -> int:
    return int(
        db.scalar(
            select(func.count(model.id)).where(
                model.project_id == project_id,
                model.ticket_type == INCIDENT_TICKET_TYPE,
                column.in_(sources),
            )
        )
        or 0
    )


def build_scope_stats(db: Session, project_id: UUID, model) -> IncidentSlaScopeStats:
    return IncidentSlaScopeStats(
        incident_tickets_considered=count_incidents(db, project_id, model),
        incident_tickets_matched_to_sla_rows=count_matched_incident_tickets_for_model(
            db,
            project_id,
            model,
        ),
        incident_tickets_enriched=count_enriched_incidents(db, project_id, model),
        response_sla_enriched=count_named_sla(
            db,
            project_id,
            model,
            model.response_sla_name,
        ),
        resolution_sla_enriched=count_named_sla(
            db,
            project_id,
            model,
            model.resolution_sla_name,
        ),
        response_vendor_specific=count_sla_selection_source(
            db,
            project_id,
            model,
            model.response_sla_selection_source,
            ("ticket_vendor", "derived_vendor"),
        ),
        response_default=count_sla_selection_source(
            db,
            project_id,
            model,
            model.response_sla_selection_source,
            ("default",),
        ),
        response_fallback_default=count_sla_selection_source(
            db,
            project_id,
            model,
            model.response_sla_selection_source,
            ("fallback_default",),
        ),
        response_not_found=count_sla_selection_source(
            db,
            project_id,
            model,
            model.response_sla_selection_source,
            ("not_found",),
        ),
        resolution_vendor_specific=count_sla_selection_source(
            db,
            project_id,
            model,
            model.resolution_sla_selection_source,
            ("ticket_vendor", "derived_vendor"),
        ),
        resolution_default=count_sla_selection_source(
            db,
            project_id,
            model,
            model.resolution_sla_selection_source,
            ("default",),
        ),
        resolution_fallback_default=count_sla_selection_source(
            db,
            project_id,
            model,
            model.resolution_sla_selection_source,
            ("fallback_default",),
        ),
        resolution_not_found=count_sla_selection_source(
            db,
            project_id,
            model,
            model.resolution_sla_selection_source,
            ("not_found",),
        ),
    )


def build_sla_rows_stats(db: Session, project_id: UUID) -> IncidentSlaRowsStats:
    total_rows = int(
        db.scalar(
            select(func.count(IncidentSlaRow.id)).where(IncidentSlaRow.project_id == project_id)
        )
        or 0
    )
    distinct_numbers = int(
        db.scalar(
            select(func.count(func.distinct(IncidentSlaRow.inc_number))).where(
                IncidentSlaRow.project_id == project_id
            )
        )
        or 0
    )
    duplicate_skipped = int(
        db.scalar(
            select(func.coalesce(func.sum(IncidentSlaUpload.duplicate_rows_skipped), 0)).where(
                IncidentSlaUpload.project_id == project_id
            )
        )
        or 0
    )
    return IncidentSlaRowsStats(
        total_rows=total_rows,
        distinct_ticket_numbers_in_sla_rows=distinct_numbers,
        duplicate_rows_skipped_on_upload=duplicate_skipped,
    )


def count_incidents_without_sla_rows(db: Session, project_id: UUID, table_name: str) -> int:
    statement = text(
        f"""
        SELECT count(*)
        FROM {table_name} AS t
        WHERE t.project_id = CAST(:project_id AS uuid)
          AND t.ticket_type = 'INCIDENT'
          AND NOT EXISTS (
              SELECT 1
              FROM incident_sla_rows AS s
              WHERE s.project_id = CAST(:project_id AS uuid)
                AND s.inc_number = t.ticket_number
          )
        """
    )
    return int(db.execute(statement, {"project_id": str(project_id)}).scalar_one() or 0)


def count_unmatched_sla_ticket_numbers(db: Session, project_id: UUID) -> int:
    statement = text(
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
            AND NOT EXISTS (
                SELECT 1
                FROM assessment_out_of_scope_tickets AS oos
                WHERE oos.project_id = CAST(:project_id AS uuid)
                  AND oos.ticket_type = 'INCIDENT'
                  AND oos.ticket_number = s.inc_number
            )
        ) AS unmatched
        """
    )
    return int(db.execute(statement, {"project_id": str(project_id)}).scalar_one() or 0)


def build_unmatched_stats(db: Session, project_id: UUID) -> IncidentSlaUnmatchedStats:
    return IncidentSlaUnmatchedStats(
        sla_ticket_numbers_not_found_in_scope_or_out_of_scope=count_unmatched_sla_ticket_numbers(
            db,
            project_id,
        ),
        in_scope_incidents_without_sla_rows=count_incidents_without_sla_rows(
            db,
            project_id,
            "tickets",
        ),
        out_of_scope_incidents_without_sla_rows=count_incidents_without_sla_rows(
            db,
            project_id,
            "assessment_out_of_scope_tickets",
        ),
    )


def count_combined_sla_selection_source(
    db: Session,
    project_id: UUID,
    column_name: str,
    sources: tuple[str, ...],
) -> int:
    return count_sla_selection_source(
        db,
        project_id,
        Ticket,
        getattr(Ticket, column_name),
        sources,
    ) + count_sla_selection_source(
        db,
        project_id,
        AssessmentOutOfScopeTicket,
        getattr(AssessmentOutOfScopeTicket, column_name),
        sources,
    )


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

    sla_candidates = load_incident_sla_candidates(db, project_id)
    response_count = 0
    resolution_count = 0
    for model, table_name in (
        (Ticket, "tickets"),
        (AssessmentOutOfScopeTicket, "assessment_out_of_scope_tickets"),
    ):
        response_count += bulk_update_incident_sla_target(
            db,
            project_id,
            model,
            candidates_by_incident=sla_candidates[SLA_TARGET_RESPONSE],
            breached_column="response_sla_breached",
            business_elapsed_column="response_sla_business_elapsed_seconds",
            name_column="response_sla_name",
            definition_column="response_sla_definition_name_used",
            selection_source_column="response_sla_selection_source",
            vendor_used_column="response_sla_vendor_used",
            updated_at_column="response_sla_updated_at",
            replace_existing=replace_existing,
        )
        resolution_count += bulk_update_incident_sla_target(
            db,
            project_id,
            model,
            candidates_by_incident=sla_candidates[SLA_TARGET_RESOLUTION],
            breached_column="resolution_sla_breached",
            business_elapsed_column="resolution_sla_business_elapsed_seconds",
            name_column="resolution_sla_name",
            definition_column="resolution_sla_definition_name_used",
            selection_source_column="resolution_sla_selection_source",
            vendor_used_column="resolution_sla_vendor_used",
            updated_at_column="resolution_sla_updated_at",
            replace_existing=replace_existing,
        )
        mark_missing_incident_sla_target(
            db,
            project_id,
            name_column="response_sla_name",
            selection_source_column="response_sla_selection_source",
            updated_at_column="response_sla_updated_at",
            replace_existing=replace_existing,
            table_name=table_name,
        )
        mark_missing_incident_sla_target(
            db,
            project_id,
            name_column="resolution_sla_name",
            selection_source_column="resolution_sla_selection_source",
            updated_at_column="resolution_sla_updated_at",
            replace_existing=replace_existing,
            table_name=table_name,
        )

    matched_ticket_count = count_matched_incident_tickets(db, project_id)
    db.commit()

    warnings = [
        "Selection uses ticket vendor first, then derived vendor, then Default. "
        "Response and Resolution SLA selection are independent."
    ]
    in_scope_stats = build_scope_stats(db, project_id, Ticket)
    out_of_scope_stats = build_scope_stats(db, project_id, AssessmentOutOfScopeTicket)
    return IncidentSlaEnrichResult(
        project_id=project_id,
        ticket_type=INCIDENT_TICKET_TYPE,
        replace_existing=replace_existing,
        matched_ticket_count=matched_ticket_count,
        response_sla_updated_count=response_count,
        resolution_sla_updated_count=resolution_count,
        in_scope_incidents_considered=in_scope_stats.incident_tickets_considered,
        in_scope_incidents_enriched=in_scope_stats.incident_tickets_enriched,
        out_of_scope_incidents_considered=out_of_scope_stats.incident_tickets_considered,
        out_of_scope_incidents_enriched=out_of_scope_stats.incident_tickets_enriched,
        response_vendor_specific_count=count_combined_sla_selection_source(
            db,
            project_id,
            "response_sla_selection_source",
            ("ticket_vendor", "derived_vendor"),
        ),
        response_default_count=count_combined_sla_selection_source(
            db,
            project_id,
            "response_sla_selection_source",
            ("default", "fallback_default"),
        ),
        resolution_vendor_specific_count=count_combined_sla_selection_source(
            db,
            project_id,
            "resolution_sla_selection_source",
            ("ticket_vendor", "derived_vendor"),
        ),
        resolution_default_count=count_combined_sla_selection_source(
            db,
            project_id,
            "resolution_sla_selection_source",
            ("default", "fallback_default"),
        ),
        missing_response_sla_count=count_combined_sla_selection_source(
            db,
            project_id,
            "response_sla_selection_source",
            ("not_found",),
        ),
        missing_resolution_sla_count=count_combined_sla_selection_source(
            db,
            project_id,
            "resolution_sla_selection_source",
            ("not_found",),
        ),
        sla_rows=build_sla_rows_stats(db, project_id),
        in_scope=in_scope_stats,
        out_of_scope=out_of_scope_stats,
        unmatched=build_unmatched_stats(db, project_id),
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
    unmatched_count = count_unmatched_sla_ticket_numbers(db, project_id)

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
            AND NOT EXISTS (
                SELECT 1
                FROM assessment_out_of_scope_tickets AS oos
                WHERE oos.project_id = CAST(:project_id AS uuid)
                  AND oos.ticket_type = 'INCIDENT'
                  AND oos.ticket_number = s.inc_number
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
    db.execute(delete(IncidentSlaUpload).where(IncidentSlaUpload.project_id == project_id))
