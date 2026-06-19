from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models import Project, SourceColumnMapping, Ticket, TicketRawRow, UploadBatch, UploadedFile
from app.services.ingestion import INGESTION_BATCH_SIZE, normalize_source_column_name
from app.services.upload_lifecycle import (
    BATCH_STATUS_DELETED,
    mark_upload_batch_normalization_failed,
    mark_upload_batch_normalized,
    mark_upload_batch_normalizing,
)

MAX_ERROR_SAMPLES = 50
MAX_WARNING_SAMPLES = 50
MAPPING_SOURCE_SAVED_TEMPLATE = "SAVED_TEMPLATE"
MAPPING_SOURCE_BUILT_IN_SUGGESTION = "BUILT_IN_SUGGESTION"
MAPPING_SOURCE_REQUEST_BODY = "REQUEST_BODY"
APPLY_SCOPE_BATCH = "BATCH"
APPLY_SCOPE_TICKET_TYPE = "TICKET_TYPE"

NORMALIZED_FIELDS = (
    "ticket_id",
    "ticket_type",
    "title",
    "description",
    "status",
    "priority",
    "urgency",
    "impact",
    "category",
    "subcategory",
    "application",
    "business_service",
    "configuration_item",
    "assignment_group",
    "assigned_to",
    "requester",
    "created_by",
    "created_channel",
    "created_at",
    "resolved_at",
    "closed_at",
    "sla_due_at",
    "sla_breached",
    "business_duration_seconds",
    "reopen_count",
    "reassignment_count",
    "resolution_code",
    "resolution_notes",
    "source_system",
    "month_key",
)

FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "ticket_id": (
        "ticket_id",
        "number",
        "incident_number",
        "request_number",
        "task_number",
        "sc_task",
        "sctask",
        "sys_id",
    ),
    "ticket_type": ("ticket_type", "type", "task_type", "record_type"),
    "title": ("short_description", "title", "summary", "brief_description"),
    "description": ("description", "details", "detailed_description", "work_notes"),
    "status": ("status", "state", "incident_state", "request_state", "task_state"),
    "priority": ("priority", "pri"),
    "urgency": ("urgency",),
    "impact": ("impact",),
    "category": ("category", "sc_catalog"),
    "subcategory": ("subcategory", "sub_category"),
    "application": (
        "application",
        "cmdb_ci_business_app",
        "business_service",
        "cmdb_ci",
        "app",
        "business_application",
        "u_application",
        "app_name",
    ),
    "business_service": ("business_service",),
    "configuration_item": ("configuration_item", "cmdb_ci", "ci", "config_item"),
    "assignment_group": ("assignment_group", "group", "support_group"),
    "assigned_to": ("assigned_to", "assignee"),
    "requester": (
        "requester",
        "caller_id",
        "caller",
        "request.requested_for",
        "requested_for",
        "requested_by",
    ),
    "created_by": ("created_by", "opened_by", "sys_created_by"),
    "created_channel": ("created_channel", "channel", "contact_type", "opened_via"),
    "created_at": (
        "created_at",
        "opened_at",
        "opened",
        "created",
        "created_date",
        "opened_date",
        "sys_created_on",
    ),
    "resolved_at": ("resolved_at", "resolved", "resolved_date", "resolved_on"),
    "closed_at": ("closed_at", "closed", "closed_date", "closed_on"),
    "sla_due_at": ("sla_due_at", "sla_due", "due_date", "due_at", "planned_end_time"),
    "sla_breached": ("sla_breached", "has_breached", "breached", "breach", "made_sla"),
    "business_duration_seconds": (
        "business_duration_seconds",
        "business_stc",
        "business_duration",
    ),
    "reopen_count": ("reopen_count", "reopens", "reopen_count_int"),
    "reassignment_count": ("reassignment_count", "reassignments"),
    "resolution_code": ("resolution_code", "close_code", "closure_code"),
    "resolution_notes": ("resolution_notes", "close_notes", "close_note", "resolution"),
    "source_system": ("source_system", "source", "system"),
    "month_key": ("month_key", "month", "period"),
}

FIELD_DATA_TYPES: dict[str, str] = {
    "created_at": "datetime",
    "resolved_at": "datetime",
    "closed_at": "datetime",
    "sla_due_at": "datetime",
    "sla_breached": "boolean",
    "business_duration_seconds": "integer",
    "reopen_count": "integer",
    "reassignment_count": "integer",
}

BUILT_IN_DEFAULT_MAPPINGS: dict[str, dict[str, str]] = {
    "INCIDENT": {
        "ticket_id": "number",
        "title": "short_description",
        "description": "description",
        "status": "state",
        "priority": "priority",
        "created_at": "sys_created_on",
        "requester": "caller_id",
        "created_by": "opened_by",
        "assignment_group": "assignment_group",
        "assigned_to": "assigned_to",
        "category": "category",
        "subcategory": "subcategory",
        "application": "business_service",
        "configuration_item": "cmdb_ci",
        "impact": "impact",
        "urgency": "urgency",
        "closed_at": "closed_at",
        "resolved_at": "resolved_at",
        "sla_breached": "made_sla",
        "reopen_count": "reopen_count",
        "reassignment_count": "reassignment_count",
        "business_duration_seconds": "business_stc",
        "resolution_code": "close_code",
        "resolution_notes": "close_notes",
    },
    "SERVICE_CATALOG_TASK": {
        "ticket_id": "number",
        "title": "short_description",
        "description": "description",
        "status": "state",
        "priority": "priority",
        "created_at": "sys_created_on",
        "requester": "request.requested_for",
        "created_by": "sys_created_by",
        "assignment_group": "assignment_group",
        "assigned_to": "assigned_to",
        "application": "cmdb_ci_business_app",
        "configuration_item": "cmdb_ci",
        "category": "sc_catalog",
        "closed_at": "closed_at",
        "created_channel": "contact_type",
        "sla_breached": "made_sla",
        "resolution_notes": "close_notes",
        "business_duration_seconds": "business_duration",
        "reassignment_count": "reassignment_count",
    },
}

DATE_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d",
    "%m/%d/%Y %H:%M:%S",
    "%m/%d/%Y %H:%M",
    "%m/%d/%Y",
    "%m/%d/%y %H:%M:%S",
    "%m/%d/%y %H:%M",
    "%m/%d/%y",
    "%d/%m/%Y %H:%M:%S",
    "%d/%m/%Y %H:%M",
    "%d/%m/%Y",
    "%d-%m-%Y %H:%M:%S",
    "%d-%m-%Y %H:%M",
    "%d-%m-%Y",
    "%d-%b-%Y %H:%M:%S",
    "%d-%b-%Y %H:%M",
    "%d-%b-%Y",
)


class MappingError(Exception):
    pass


@dataclass(frozen=True)
class SourceColumnInfo:
    name: str
    normalized_name: str
    occurrence_count: int


@dataclass(frozen=True)
class NormalizationErrorSample:
    row_number: int
    raw_row_id: UUID
    message: str


@dataclass(frozen=True)
class ApplyMappingResult:
    upload_batch_id: UUID
    total_raw_rows: int
    normalized_ticket_count: int
    failed_row_count: int
    warnings: list[str]
    errors: list[NormalizationErrorSample]
    status: str


@dataclass(frozen=True)
class SuggestedMappingResult:
    project_id: UUID
    ticket_type: str
    source_columns: list[str]
    mapping: dict[str, str]
    mapping_source: str
    upload_batch_id: UUID | None = None


@dataclass(frozen=True)
class BatchApplyMappingResult:
    upload_batch_id: UUID
    batch_name: str
    status: str
    total_raw_rows: int
    normalized_ticket_count: int
    failed_row_count: int
    warnings: list[str]
    errors: list[NormalizationErrorSample]


@dataclass(frozen=True)
class ScopedApplyMappingResult:
    scope: str
    project_id: UUID
    ticket_type: str
    mapping_source: str
    saved_as_default_for_ticket_type: bool
    batch_results: list[BatchApplyMappingResult]
    total_raw_rows: int
    normalized_ticket_count: int
    failed_row_count: int
    warnings: list[str]
    errors: list[NormalizationErrorSample]


def normalize_ticket_type_value(ticket_type: str) -> str:
    return ticket_type.strip().upper()


def get_upload_batch_or_raise(db: Session, upload_batch_id: UUID) -> UploadBatch:
    upload_batch = db.get(UploadBatch, upload_batch_id)
    if upload_batch is None or upload_batch.status == BATCH_STATUS_DELETED:
        raise FileNotFoundError(f"Upload batch {upload_batch_id} was not found.")
    return upload_batch


def infer_source_columns(db: Session, upload_batch_id: UUID) -> list[SourceColumnInfo]:
    get_upload_batch_or_raise(db, upload_batch_id)
    column_counts: dict[str, int] = {}

    statement = select(TicketRawRow.raw_data).where(TicketRawRow.upload_batch_id == upload_batch_id)
    for (raw_data,) in db.execute(statement).yield_per(INGESTION_BATCH_SIZE):
        for column_name in raw_data:
            column_counts[column_name] = column_counts.get(column_name, 0) + 1

    return [
        SourceColumnInfo(
            name=column_name,
            normalized_name=normalize_source_column_name(column_name),
            occurrence_count=occurrence_count,
        )
        for column_name, occurrence_count in sorted(
            column_counts.items(),
            key=lambda item: normalize_source_column_name(item[0]),
        )
    ]


def source_column_counts_to_infos(column_counts: dict[str, int]) -> list[SourceColumnInfo]:
    return [
        SourceColumnInfo(
            name=column_name,
            normalized_name=normalize_source_column_name(column_name),
            occurrence_count=occurrence_count,
        )
        for column_name, occurrence_count in sorted(
            column_counts.items(),
            key=lambda item: normalize_source_column_name(item[0]),
        )
    ]


def infer_source_columns_for_ticket_type(
    db: Session,
    project_id: UUID,
    ticket_type: str,
) -> list[SourceColumnInfo]:
    project = db.get(Project, project_id)
    if project is None:
        raise FileNotFoundError(f"Project {project_id} was not found.")

    ticket_type = normalize_ticket_type_value(ticket_type)
    column_counts: dict[str, int] = {}

    statement = (
        select(TicketRawRow.raw_data)
        .join(UploadBatch, UploadBatch.id == TicketRawRow.upload_batch_id)
        .where(
            TicketRawRow.project_id == project_id,
            TicketRawRow.ticket_type == ticket_type,
            UploadBatch.status != BATCH_STATUS_DELETED,
            UploadBatch.deleted_at.is_(None),
        )
    )
    for (raw_data,) in db.execute(statement).yield_per(INGESTION_BATCH_SIZE):
        for column_name in raw_data:
            column_counts[column_name] = column_counts.get(column_name, 0) + 1

    return source_column_counts_to_infos(column_counts)


def get_batch_ticket_type(db: Session, upload_batch_id: UUID) -> str | None:
    ticket_type = db.scalar(
        select(TicketRawRow.ticket_type)
        .where(TicketRawRow.upload_batch_id == upload_batch_id)
        .order_by(TicketRawRow.created_at.asc())
        .limit(1)
    )
    if ticket_type:
        return normalize_ticket_type_value(ticket_type)

    ticket_type = db.scalar(
        select(UploadedFile.ticket_type)
        .where(UploadedFile.upload_batch_id == upload_batch_id)
        .order_by(UploadedFile.created_at.asc())
        .limit(1)
    )
    return normalize_ticket_type_value(ticket_type) if ticket_type else None


def get_upload_batches_for_ticket_type(
    db: Session,
    project_id: UUID,
    ticket_type: str,
) -> list[UploadBatch]:
    project = db.get(Project, project_id)
    if project is None:
        raise FileNotFoundError(f"Project {project_id} was not found.")

    statement = (
        select(UploadBatch)
        .join(UploadedFile, UploadedFile.upload_batch_id == UploadBatch.id)
        .where(
            UploadBatch.project_id == project_id,
            UploadedFile.ticket_type == normalize_ticket_type_value(ticket_type),
            UploadBatch.status != BATCH_STATUS_DELETED,
            UploadBatch.deleted_at.is_(None),
        )
        .distinct()
        .order_by(UploadBatch.created_at.asc())
    )
    return list(db.scalars(statement).all())


def field_aliases_for_ticket_type(ticket_type: str | None) -> dict[str, tuple[str, ...]]:
    aliases = dict(FIELD_ALIASES)
    normalized_ticket_type = normalize_ticket_type_value(ticket_type or "")
    if normalized_ticket_type == "INCIDENT":
        aliases["business_duration_seconds"] = (
            "business_stc",
            "business_duration_seconds",
        )
    elif normalized_ticket_type == "SERVICE_CATALOG_TASK":
        aliases["business_duration_seconds"] = (
            "business_duration",
            "business_duration_seconds",
        )
    return aliases


def suggest_mapping(source_columns: list[str], ticket_type: str | None = None) -> dict[str, str]:
    if not source_columns and ticket_type:
        default_mapping = BUILT_IN_DEFAULT_MAPPINGS.get(normalize_ticket_type_value(ticket_type))
        if default_mapping:
            return default_mapping.copy()

    normalized_to_source = {
        normalize_source_column_name(source_column): source_column
        for source_column in source_columns
    }
    suggested: dict[str, str] = {}

    for normalized_field, aliases in field_aliases_for_ticket_type(ticket_type).items():
        for alias in aliases:
            source_column = normalized_to_source.get(normalize_source_column_name(alias))
            if source_column:
                suggested[normalized_field] = source_column
                break

    return suggested


def get_suggested_mapping_for_batch(db: Session, upload_batch_id: UUID) -> dict[str, str]:
    return get_suggested_mapping_result_for_batch(db, upload_batch_id).mapping


def get_suggested_mapping_result(
    db: Session,
    project_id: UUID,
    ticket_type: str,
    upload_batch_id: UUID | None = None,
) -> SuggestedMappingResult:
    ticket_type = normalize_ticket_type_value(ticket_type)
    project = db.get(Project, project_id)
    if project is None:
        raise FileNotFoundError(f"Project {project_id} was not found.")

    if upload_batch_id is not None:
        upload_batch = get_upload_batch_or_raise(db, upload_batch_id)
        if upload_batch.project_id != project_id:
            raise MappingError("Selected batch does not belong to the selected project.")

        batch_ticket_type = get_batch_ticket_type(db, upload_batch_id)
        if batch_ticket_type and batch_ticket_type != ticket_type:
            raise MappingError(
                f"Selected batch is {batch_ticket_type}, not {ticket_type}."
            )
        source_column_infos = infer_source_columns(db, upload_batch_id)
    else:
        source_column_infos = infer_source_columns_for_ticket_type(db, project_id, ticket_type)

    source_columns = [column.name for column in source_column_infos]
    template_rows = get_mapping_template(db, project_id, ticket_type)
    if template_rows:
        return SuggestedMappingResult(
            project_id=project_id,
            ticket_type=ticket_type,
            upload_batch_id=upload_batch_id,
            source_columns=source_columns,
            mapping=mapping_rows_to_field_mapping(template_rows),
            mapping_source=MAPPING_SOURCE_SAVED_TEMPLATE,
        )

    return SuggestedMappingResult(
        project_id=project_id,
        ticket_type=ticket_type,
        upload_batch_id=upload_batch_id,
        source_columns=source_columns,
        mapping=suggest_mapping(source_columns, ticket_type),
        mapping_source=MAPPING_SOURCE_BUILT_IN_SUGGESTION,
    )


def get_suggested_mapping_result_for_batch(
    db: Session,
    upload_batch_id: UUID,
) -> SuggestedMappingResult:
    upload_batch = get_upload_batch_or_raise(db, upload_batch_id)
    ticket_type = get_batch_ticket_type(db, upload_batch_id)
    if not ticket_type:
        raise MappingError("Unable to determine ticket type for the selected batch.")

    return get_suggested_mapping_result(
        db=db,
        project_id=upload_batch.project_id,
        ticket_type=ticket_type,
        upload_batch_id=upload_batch_id,
    )


def clean_mapping(mapping: Mapping[str, str]) -> dict[str, str]:
    cleaned: dict[str, str] = {}

    for normalized_field, source_column in mapping.items():
        normalized_field = normalized_field.strip()
        source_column = source_column.strip()
        if not normalized_field or not source_column:
            continue
        if normalized_field not in NORMALIZED_FIELDS:
            raise MappingError(f"Unsupported normalized field: {normalized_field}")

        cleaned[normalized_field] = source_column

    if "ticket_id" not in cleaned:
        raise MappingError("Mapping must include ticket_id.")

    return cleaned


def save_mapping_template(
    db: Session,
    project_id: UUID,
    ticket_type: str,
    mapping: Mapping[str, str],
    notes: str | None = None,
) -> list[SourceColumnMapping]:
    project = db.get(Project, project_id)
    if project is None:
        raise FileNotFoundError(f"Project {project_id} was not found.")

    ticket_type = normalize_ticket_type_value(ticket_type)
    cleaned_mapping = clean_mapping(mapping)

    try:
        db.execute(
            delete(SourceColumnMapping).where(
                SourceColumnMapping.project_id == project_id,
                SourceColumnMapping.ticket_type == ticket_type,
            )
        )
        saved_rows = [
            SourceColumnMapping(
                project_id=project_id,
                ticket_type=ticket_type,
                source_column_name=source_column,
                normalized_field_name=normalized_field,
                data_type=FIELD_DATA_TYPES.get(normalized_field, "string"),
                is_required=normalized_field in {"ticket_id", "created_at"},
                notes=notes,
            )
            for normalized_field, source_column in cleaned_mapping.items()
        ]
        db.add_all(saved_rows)
        db.commit()
        for saved_row in saved_rows:
            db.refresh(saved_row)
    except SQLAlchemyError as exc:
        db.rollback()
        raise MappingError(f"Mapping template could not be saved: {exc}") from exc

    return saved_rows


def get_mapping_template(
    db: Session,
    project_id: UUID,
    ticket_type: str,
) -> list[SourceColumnMapping]:
    statement = (
        select(SourceColumnMapping)
        .where(
            SourceColumnMapping.project_id == project_id,
            SourceColumnMapping.ticket_type == normalize_ticket_type_value(ticket_type),
        )
        .order_by(SourceColumnMapping.normalized_field_name.asc())
    )
    return list(db.scalars(statement).all())


def mapping_rows_to_field_mapping(rows: list[SourceColumnMapping]) -> dict[str, str]:
    return {
        row.normalized_field_name: row.source_column_name
        for row in rows
        if row.normalized_field_name
    }


def get_raw_value(raw_data: Mapping[str, Any], source_column: str | None) -> Any:
    if not source_column:
        return None
    if source_column in raw_data:
        return raw_data[source_column]

    source_column_key = normalize_source_column_name(source_column)
    for raw_column_name, raw_value in raw_data.items():
        if normalize_source_column_name(raw_column_name) == source_column_key:
            return raw_value

    return None


def get_mapped_value(raw_data: Mapping[str, Any], mapping: Mapping[str, str], field: str) -> Any:
    return get_raw_value(raw_data, mapping.get(field))


def text_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def parse_datetime_value(value: Any) -> datetime | None:
    if value is None:
        return None

    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)

    if isinstance(value, date):
        return datetime.combine(value, time.min, tzinfo=UTC)

    if isinstance(value, int | float) and value > 0:
        return datetime(1899, 12, 30, tzinfo=UTC) + timedelta(days=float(value))

    text = str(value).strip()
    if not text:
        return None

    if re.fullmatch(r"\d+(\.\d+)?", text):
        return parse_datetime_value(float(text))

    iso_text = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(iso_text)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    except ValueError:
        pass

    for date_format in DATE_FORMATS:
        try:
            parsed = datetime.strptime(text, date_format).replace(tzinfo=UTC)
            return parsed
        except ValueError:
            continue

    return None


def normalize_priority(value: Any) -> str | None:
    text = text_or_none(value)
    if text is None:
        return None

    normalized = text.strip().upper()
    if normalized in {"P1", "1", "1 - CRITICAL", "CRITICAL"} or "CRITICAL" in normalized:
        return "P1"
    if normalized in {"P2", "2", "2 - HIGH", "HIGH"} or "HIGH" in normalized:
        return "P2"
    if normalized in {"P3", "3", "3 - MEDIUM", "MEDIUM", "MODERATE"} or any(
        word in normalized for word in ("MEDIUM", "MODERATE")
    ):
        return "P3"
    if normalized in {
        "P5",
        "5",
        "5 - PLANNING",
        "PLANNING",
        "VERY LOW",
    } or any(word in normalized for word in ("PLANNING", "VERY LOW")):
        return "P5"
    if normalized in {"P4", "4", "4 - LOW", "LOW"} or "LOW" in normalized:
        return "P4"

    digit_match = re.search(r"\b([1-5])\b", normalized)
    if digit_match:
        return f"P{digit_match.group(1)}"

    return text


def parse_bool_value(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value

    normalized = str(value).strip().lower()
    if normalized in {"true", "t", "yes", "y", "1"}:
        return True
    if normalized in {"false", "f", "no", "n", "0"}:
        return False
    return None


def parse_int_value(value: Any) -> int:
    if value is None or str(value).strip() == "":
        return 0
    try:
        return int(float(str(value).strip().replace(",", "")))
    except ValueError:
        return 0


def parse_optional_int_value(value: Any) -> int | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        return int(float(str(value).strip().replace(",", "")))
    except ValueError:
        return None


def parse_business_duration_seconds(value: Any) -> int | None:
    if value is None:
        return None

    if isinstance(value, int | float):
        return int(value)

    text = str(value).strip()
    if not text:
        return None

    numeric_text = text.replace(",", "")
    if re.fullmatch(r"\d+(\.\d+)?", numeric_text):
        return int(float(numeric_text))

    day_match = re.search(r"(\d+(?:\.\d+)?)\s*(day|days|d)\b", text, flags=re.IGNORECASE)
    hour_match = re.search(r"(\d+(?:\.\d+)?)\s*(hour|hours|hr|hrs|h)\b", text, flags=re.IGNORECASE)
    minute_match = re.search(
        r"(\d+(?:\.\d+)?)\s*(minute|minutes|min|mins|m)\b",
        text,
        flags=re.IGNORECASE,
    )
    second_match = re.search(
        r"(\d+(?:\.\d+)?)\s*(second|seconds|sec|secs|s)\b",
        text,
        flags=re.IGNORECASE,
    )
    if any((day_match, hour_match, minute_match, second_match)):
        total_seconds = 0.0
        if day_match:
            total_seconds += float(day_match.group(1)) * 86400
        if hour_match:
            total_seconds += float(hour_match.group(1)) * 3600
        if minute_match:
            total_seconds += float(minute_match.group(1)) * 60
        if second_match:
            total_seconds += float(second_match.group(1))
        return int(total_seconds)

    colon_match = re.fullmatch(r"(?:(\d+)\s+)?(\d{1,2}):(\d{2})(?::(\d{2}))?", text)
    if colon_match:
        days = int(colon_match.group(1) or 0)
        hours = int(colon_match.group(2))
        minutes = int(colon_match.group(3))
        seconds = int(colon_match.group(4) or 0)
        return days * 86400 + hours * 3600 + minutes * 60 + seconds

    return None


def parse_sla_breached_value(
    value: Any,
    source_column: str | None,
) -> bool | None:
    parsed_value = parse_bool_value(value)
    if parsed_value is None:
        return None

    if source_column and normalize_source_column_name(source_column) == "made_sla":
        return not parsed_value

    return parsed_value


def resolve_apply_mapping(
    db: Session,
    upload_batch: UploadBatch,
    mapping: Mapping[str, str] | None,
) -> dict[str, str]:
    if mapping:
        return clean_mapping(mapping)

    ticket_type_statement = (
        select(TicketRawRow.ticket_type)
        .where(TicketRawRow.upload_batch_id == upload_batch.id)
        .order_by(TicketRawRow.created_at.asc())
        .limit(1)
    )
    ticket_type = db.scalar(ticket_type_statement)
    if not ticket_type:
        raise MappingError("No raw rows found. Ingest files before applying a mapping.")

    template_rows = get_mapping_template(db, upload_batch.project_id, ticket_type)
    if not template_rows:
        raise MappingError(
            "No saved mapping template found. Pass a mapping in the request or save a template."
        )
    return clean_mapping(mapping_rows_to_field_mapping(template_rows))


def build_ticket_from_raw_row(
    raw_row: TicketRawRow,
    upload_batch: UploadBatch,
    mapping: Mapping[str, str],
) -> Ticket:
    ticket_number = text_or_none(get_mapped_value(raw_row.raw_data, mapping, "ticket_id"))
    if ticket_number is None:
        raise MappingError("Mapped ticket_id is empty.")

    normalized_values = {
        field: get_mapped_value(raw_row.raw_data, mapping, field)
        for field in NORMALIZED_FIELDS
        if field in mapping
    }
    mapped_source_keys = {
        normalize_source_column_name(source_column) for source_column in mapping.values()
    }
    unmapped_fields = {
        source_column: raw_value
        for source_column, raw_value in raw_row.raw_data.items()
        if normalize_source_column_name(source_column) not in mapped_source_keys
    }
    mapped_ticket_type = text_or_none(normalized_values.get("ticket_type"))
    ticket_type = mapped_ticket_type.upper() if mapped_ticket_type else raw_row.ticket_type
    source_system = (
        text_or_none(normalized_values.get("source_system")) or upload_batch.source_system
    )

    return Ticket(
        project_id=raw_row.project_id,
        upload_batch_id=upload_batch.id,
        uploaded_file_id=raw_row.uploaded_file_id,
        raw_row_id=raw_row.id,
        ticket_number=ticket_number,
        ticket_type=ticket_type,
        month_key=upload_batch.month_key,
        source_system=source_system,
        created_at=parse_datetime_value(normalized_values.get("created_at")),
        resolved_at=parse_datetime_value(normalized_values.get("resolved_at")),
        closed_at=parse_datetime_value(normalized_values.get("closed_at")),
        due_at=parse_datetime_value(normalized_values.get("sla_due_at")),
        sla_due_at=parse_datetime_value(normalized_values.get("sla_due_at")),
        short_description=text_or_none(normalized_values.get("title")),
        description=text_or_none(normalized_values.get("description")),
        state=text_or_none(normalized_values.get("status")),
        priority=normalize_priority(normalized_values.get("priority")),
        urgency=text_or_none(normalized_values.get("urgency")),
        impact=text_or_none(normalized_values.get("impact")),
        application=text_or_none(normalized_values.get("application")),
        business_service=text_or_none(normalized_values.get("business_service")),
        assignment_group=text_or_none(normalized_values.get("assignment_group")),
        assigned_to=text_or_none(normalized_values.get("assigned_to")),
        requester=text_or_none(normalized_values.get("requester")),
        opened_by=text_or_none(normalized_values.get("created_by")),
        created_by=text_or_none(normalized_values.get("created_by")),
        category=text_or_none(normalized_values.get("category")),
        subcategory=text_or_none(normalized_values.get("subcategory")),
        sla_breached=parse_sla_breached_value(
            normalized_values.get("sla_breached"),
            mapping.get("sla_breached"),
        ),
        business_duration_seconds=parse_business_duration_seconds(
            normalized_values.get("business_duration_seconds"),
        ),
        reopen_count=parse_int_value(normalized_values.get("reopen_count")),
        reassignment_count=parse_optional_int_value(normalized_values.get("reassignment_count")),
        normalized_payload={
            "raw_payload_json": raw_row.raw_data,
            "unmapped_fields": unmapped_fields,
            "mapped_fields": {
                field: text_or_none(value) for field, value in normalized_values.items()
            },
        },
    )


def apply_mapping_to_batch(
    db: Session,
    upload_batch_id: UUID,
    mapping: Mapping[str, str] | None = None,
    delete_existing: bool = True,
) -> ApplyMappingResult:
    upload_batch = get_upload_batch_or_raise(db, upload_batch_id)
    resolved_mapping = resolve_apply_mapping(db, upload_batch, mapping)

    total_raw_rows = 0
    normalized_ticket_count = 0
    failed_row_count = 0
    errors: list[NormalizationErrorSample] = []
    warnings: list[str] = []
    seen_ticket_numbers: set[str] = set()

    try:
        mark_upload_batch_normalizing(upload_batch)
        db.flush()

        if delete_existing:
            db.execute(delete(Ticket).where(Ticket.upload_batch_id == upload_batch_id))
            db.flush()

        raw_row_statement = (
            select(TicketRawRow)
            .where(TicketRawRow.upload_batch_id == upload_batch_id)
            .order_by(TicketRawRow.uploaded_file_id.asc(), TicketRawRow.row_number.asc())
        )

        for raw_row in db.scalars(raw_row_statement).yield_per(INGESTION_BATCH_SIZE):
            total_raw_rows += 1
            try:
                ticket = build_ticket_from_raw_row(raw_row, upload_batch, resolved_mapping)
                if ticket.ticket_number in seen_ticket_numbers:
                    raise MappingError(f"Duplicate ticket_id in batch: {ticket.ticket_number}")

                existing_ticket_id = db.scalar(
                    select(Ticket.id)
                    .where(
                        Ticket.project_id == ticket.project_id,
                        Ticket.ticket_number == ticket.ticket_number,
                    )
                    .limit(1)
                )
                if existing_ticket_id is not None:
                    raise MappingError(
                        f"Ticket {ticket.ticket_number} already exists for this project."
                    )

                seen_ticket_numbers.add(ticket.ticket_number)
                db.add(ticket)
                normalized_ticket_count += 1
                if normalized_ticket_count % INGESTION_BATCH_SIZE == 0:
                    db.flush()
            except MappingError as exc:
                failed_row_count += 1
                if len(errors) < MAX_ERROR_SAMPLES:
                    errors.append(
                        NormalizationErrorSample(
                            row_number=raw_row.row_number,
                            raw_row_id=raw_row.id,
                            message=str(exc),
                        )
                    )

        if total_raw_rows == 0:
            warnings.append("No raw rows found. Ingest files before applying a mapping.")
        elif failed_row_count > MAX_ERROR_SAMPLES:
            warnings.append(
                f"{failed_row_count - MAX_ERROR_SAMPLES} additional row errors were omitted."
            )

        if total_raw_rows > 0 and failed_row_count == 0:
            mark_upload_batch_normalized(upload_batch)
        else:
            mark_upload_batch_normalization_failed(upload_batch)

        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        failed_batch = db.get(UploadBatch, upload_batch_id)
        if failed_batch is not None:
            mark_upload_batch_normalization_failed(failed_batch)
            db.commit()
        raise MappingError(f"Mapping apply failed: {exc}") from exc
    db.refresh(upload_batch)

    return ApplyMappingResult(
        upload_batch_id=upload_batch_id,
        total_raw_rows=total_raw_rows,
        normalized_ticket_count=normalized_ticket_count,
        failed_row_count=failed_row_count,
        warnings=warnings[:MAX_WARNING_SAMPLES],
        errors=errors,
        status=upload_batch.status,
    )


def resolve_mapping_for_project_ticket_type(
    db: Session,
    project_id: UUID,
    ticket_type: str,
    mapping: Mapping[str, str] | None,
) -> tuple[dict[str, str], str]:
    if mapping:
        return clean_mapping(mapping), MAPPING_SOURCE_REQUEST_BODY

    template_rows = get_mapping_template(db, project_id, ticket_type)
    if template_rows:
        return (
            clean_mapping(mapping_rows_to_field_mapping(template_rows)),
            MAPPING_SOURCE_SAVED_TEMPLATE,
        )

    source_columns = [
        source_column.name
        for source_column in infer_source_columns_for_ticket_type(db, project_id, ticket_type)
    ]
    return (
        clean_mapping(suggest_mapping(source_columns, ticket_type)),
        MAPPING_SOURCE_BUILT_IN_SUGGESTION,
    )


def apply_mapping_with_scope(
    db: Session,
    project_id: UUID,
    ticket_type: str,
    scope: str,
    mapping: Mapping[str, str] | None = None,
    upload_batch_id: UUID | None = None,
    delete_existing: bool = True,
    save_as_default_for_ticket_type: bool = False,
) -> ScopedApplyMappingResult:
    project = db.get(Project, project_id)
    if project is None:
        raise FileNotFoundError(f"Project {project_id} was not found.")

    ticket_type = normalize_ticket_type_value(ticket_type)
    scope = scope.strip().upper()
    if scope not in {APPLY_SCOPE_BATCH, APPLY_SCOPE_TICKET_TYPE}:
        raise MappingError("Apply scope must be BATCH or TICKET_TYPE.")

    resolved_mapping, mapping_source = resolve_mapping_for_project_ticket_type(
        db=db,
        project_id=project_id,
        ticket_type=ticket_type,
        mapping=mapping,
    )
    should_save_default = save_as_default_for_ticket_type or scope == APPLY_SCOPE_TICKET_TYPE

    if scope == APPLY_SCOPE_BATCH:
        if upload_batch_id is None:
            raise MappingError("upload_batch_id is required when scope is BATCH.")
        upload_batch = get_upload_batch_or_raise(db, upload_batch_id)
        if upload_batch.project_id != project_id:
            raise MappingError("Selected batch does not belong to the selected project.")

        batch_ticket_type = get_batch_ticket_type(db, upload_batch_id)
        if batch_ticket_type != ticket_type:
            raise MappingError(f"Selected batch is {batch_ticket_type}, not {ticket_type}.")
        upload_batches = [upload_batch]
    else:
        upload_batches = get_upload_batches_for_ticket_type(db, project_id, ticket_type)
        if not upload_batches:
            raise MappingError(f"No upload batches found for {ticket_type}.")

    if should_save_default:
        save_mapping_template(
            db=db,
            project_id=project_id,
            ticket_type=ticket_type,
            mapping=resolved_mapping,
        )

    batch_results: list[BatchApplyMappingResult] = []
    all_warnings: list[str] = []
    all_errors: list[NormalizationErrorSample] = []

    for upload_batch in upload_batches:
        result = apply_mapping_to_batch(
            db=db,
            upload_batch_id=upload_batch.id,
            mapping=resolved_mapping,
            delete_existing=delete_existing,
        )
        batch_result = BatchApplyMappingResult(
            upload_batch_id=upload_batch.id,
            batch_name=upload_batch.batch_name,
            status=result.status,
            total_raw_rows=result.total_raw_rows,
            normalized_ticket_count=result.normalized_ticket_count,
            failed_row_count=result.failed_row_count,
            warnings=result.warnings,
            errors=result.errors,
        )
        batch_results.append(batch_result)
        all_warnings.extend(result.warnings)
        all_errors.extend(result.errors)

    return ScopedApplyMappingResult(
        scope=scope,
        project_id=project_id,
        ticket_type=ticket_type,
        mapping_source=mapping_source,
        saved_as_default_for_ticket_type=should_save_default,
        batch_results=batch_results,
        total_raw_rows=sum(result.total_raw_rows for result in batch_results),
        normalized_ticket_count=sum(result.normalized_ticket_count for result in batch_results),
        failed_row_count=sum(result.failed_row_count for result in batch_results),
        warnings=all_warnings[:MAX_WARNING_SAMPLES],
        errors=all_errors[:MAX_ERROR_SAMPLES],
    )
