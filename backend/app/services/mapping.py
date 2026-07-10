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

from app.models import (
    ApplicationInventoryItem,
    AssessmentChangeRecord,
    AssessmentOutOfScopeChangeRecord,
    AssessmentOutOfScopeProblemRecord,
    AssessmentOutOfScopeTicket,
    AssessmentProblemRecord,
    Project,
    SourceColumnMapping,
    Ticket,
    TicketRawRow,
    UploadBatch,
    UploadedFile,
)
from app.services.batch_classification import derive_is_batch_related
from app.services.ingestion import INGESTION_BATCH_SIZE, normalize_source_column_name
from app.services.sap_classification import derive_sap_non_sap
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
PROBLEM_TICKET_TYPE = "PROBLEM"
CHANGE_TICKET_TYPE = "CHANGE"
PROBLEM_CHANGE_TICKET_TYPES = {PROBLEM_TICKET_TYPE, CHANGE_TICKET_TYPE}
OUT_OF_SCOPE_SCOPE_REFERENCE_DESTINATION = "OUT_OF_SCOPE_ASSIGNMENT_GROUP_NOT_IN_SCOPE_REFERENCE"
INCIDENT_NUMBER_PATTERN = re.compile(r"\bINC[0-9][A-Z0-9-]*\b", flags=re.IGNORECASE)
CMDB_ARCHITECTURE_TYPE_KEYS = ("Architecture type", "Architecture Type")
CMDB_BUSINESS_CRITICAL_KEYS = (
    "Business criticality",
    "Biz Criticality",
    "Business Criticality",
    "Business Critical",
)
CMDB_INSTALL_TYPE_KEYS = ("Install type", "Install Type")

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
    "catalog_item_name",
    "catalog_knowledge_base",
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
    "vendor",
    "source_system",
    "month_key",
)

PROBLEM_CHANGE_NORMALIZED_FIELDS = (
    "number",
    "state",
    "problem_state",
    "problem_statement",
    "short_description_or_statement",
    "short_description",
    "type",
    "phase",
    "phase_state",
    "business_application",
    "application_name",
    "affected_ci_service",
    "active",
    "created_at_source",
    "opened_at",
    "actual_start_at",
    "actual_end_at",
    "planned_start_at",
    "planned_end_at",
    "duration_seconds",
    "made_sla",
    "major_incident",
    "major_problem",
    "known_error",
    "related_incidents",
    "linked_incident_count",
    "change_request",
    "caused_by_change",
    "duplicate_of",
    "parent",
    "close_notes",
    "cause_notes",
    "fix_notes",
    "workaround",
    "source",
    "contact_type",
    "company",
    "vendor_or_supplier_if_available",
    "risk",
    "risk_value",
    "unauthorized",
    "outside_maintenance_schedule",
    "cab_required",
    "cab_approval",
    "cab_date",
    "change_reason",
    "close_code",
    "close_code_sub_category",
    "incident",
    "problem",
    "service_outage_required",
    "implementation_plan",
    "backout_plan",
    "test_plan",
    "communication_plan",
)

NORMALIZED_FIELDS = tuple(dict.fromkeys((*NORMALIZED_FIELDS, *PROBLEM_CHANGE_NORMALIZED_FIELDS)))

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
    "catalog_item_name": (
        "cat_item.name",
        "item",
        "item_name",
        "item name",
        "catalog_item",
        "catalog item",
        "catalog_item_name",
        "catalog item name",
    ),
    "catalog_knowledge_base": (
        "cat_item.ref_sc_cat_item_content.kb_article.ref_u_kb_template_global_communication.u_kb_kb_knowledge_base",
        "knowledge_base",
        "knowledge base",
        "kb",
        "kb_article_knowledge_base",
        "kb article knowledge base",
        "catalog_knowledge_base",
        "catalog knowledge base",
    ),
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
    "vendor": ("vendor", "scr_vendor", "u_vendor"),
    "source_system": ("source_system", "source", "system"),
    "month_key": ("month_key", "month", "period"),
}

FIELD_ALIASES.update(
    {
        "number": ("number", "effective_number"),
        "state": ("state", "problem_state", "phase_state"),
        "problem_state": ("problem_state", "problem state"),
        "problem_statement": ("problem_statement", "problem statement"),
        "short_description_or_statement": (
            "problem_statement",
            "short_description",
            "description",
        ),
        "short_description": ("short_description", "short description"),
        "type": ("type", "change_type", "task_type"),
        "phase": ("phase",),
        "phase_state": ("phase_state", "phase state"),
        "business_application": ("business_application", "business application"),
        "application_name": ("application_name", "application name"),
        "affected_ci_service": (
            "affected_ci_service",
            "affected ci/service",
            "affected_ci",
        ),
        "active": ("active",),
        "created_at_source": ("created", "created_at", "sys_created_on"),
        "opened_at": ("opened", "opened_at", "opened_date"),
        "actual_start_at": ("actual_start", "actual start", "actual_start_date"),
        "actual_end_at": ("actual_end", "actual end", "actual_end_date"),
        "planned_start_at": ("planned_start_date", "planned start date"),
        "planned_end_at": ("planned_end_date", "planned end date"),
        "duration_seconds": ("duration", "duration_seconds"),
        "made_sla": ("made_sla", "made sla"),
        "major_incident": ("major_incident", "major incident"),
        "major_problem": ("major_problem", "major problem"),
        "known_error": ("known_error", "known error"),
        "related_incidents": (
            "related_incidents",
            "related incidents",
            "linked_incidents",
            "linked incidents",
            "incidents",
        ),
        "linked_incident_count": (
            "linked_incident_count",
            "linked incident count",
            "related_incident_count",
            "related incident count",
            "related_incidents_count",
            "related incidents count",
            "incident_count",
            "incident count",
            "number_of_incidents",
            "number of incidents",
            "related_incidents",
            "related incidents",
            "linked_incidents",
            "linked incidents",
            "incidents",
        ),
        "change_request": ("change_request", "change request"),
        "caused_by_change": ("caused_by_change", "caused by change"),
        "duplicate_of": ("duplicate_of", "duplicate of"),
        "parent": ("parent",),
        "close_notes": ("close_notes", "close notes"),
        "cause_notes": ("cause_notes", "cause notes"),
        "fix_notes": ("fix_notes", "fix notes"),
        "workaround": ("workaround",),
        "source": ("source",),
        "contact_type": ("contact_type", "contact type"),
        "company": ("company",),
        "vendor_or_supplier_if_available": (
            "vendor",
            "vendor_or_supplier_if_available",
            "supplier",
        ),
        "risk": ("risk",),
        "risk_value": ("risk_value", "risk value"),
        "unauthorized": ("unauthorized",),
        "outside_maintenance_schedule": (
            "outside_maintenance_schedule",
            "outside maintenance schedule",
        ),
        "cab_required": ("cab_required", "cab required"),
        "cab_approval": ("cab_approval", "cab approval"),
        "cab_date": ("cab_date", "cab date", "cab_date_time", "cab date/time"),
        "change_reason": ("change_reason", "change reason"),
        "close_code": ("close_code", "close code"),
        "close_code_sub_category": (
            "close_code_sub_category",
            "close code sub-category",
        ),
        "incident": ("incident",),
        "problem": ("problem",),
        "service_outage_required": (
            "service_outage_required",
            "service outage required?",
        ),
        "implementation_plan": ("implementation_plan", "implementation plan"),
        "backout_plan": ("backout_plan", "backout plan"),
        "test_plan": ("test_plan", "test plan"),
        "communication_plan": ("communication_plan", "communication plan"),
    }
)

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

FIELD_DATA_TYPES.update(
    {
        "active": "boolean",
        "created_at_source": "datetime",
        "opened_at": "datetime",
        "actual_start_at": "datetime",
        "actual_end_at": "datetime",
        "planned_start_at": "datetime",
        "planned_end_at": "datetime",
        "cab_date": "datetime",
        "duration_seconds": "integer",
        "linked_incident_count": "integer",
        "made_sla": "boolean",
        "major_incident": "boolean",
        "major_problem": "boolean",
        "known_error": "boolean",
        "unauthorized": "boolean",
        "outside_maintenance_schedule": "boolean",
        "cab_required": "boolean",
        "service_outage_required": "boolean",
    }
)

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
        "vendor": "scr_vendor",
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
        "catalog_item_name": "cat_item.name",
        "catalog_knowledge_base": (
            "cat_item.ref_sc_cat_item_content.kb_article."
            "ref_u_kb_template_global_communication.u_kb_kb_knowledge_base"
        ),
        "closed_at": "closed_at",
        "created_channel": "contact_type",
        "sla_breached": "made_sla",
        "resolution_notes": "close_notes",
        "business_duration_seconds": "business_duration",
        "reassignment_count": "reassignment_count",
        "vendor": "u_vendor",
    },
    PROBLEM_TICKET_TYPE: {
        "number": "number",
        "state": "state",
        "problem_statement": "problem_statement",
        "business_application": "business_application",
        "business_service": "business_service",
        "configuration_item": "configuration_item",
        "category": "category",
        "subcategory": "subcategory",
        "assignment_group": "assignment_group",
        "assigned_to": "assigned_to",
        "urgency": "urgency",
        "priority": "priority",
        "active": "active",
        "created_at_source": "created",
        "opened_at": "opened",
        "actual_start_at": "actual_start",
        "actual_end_at": "actual_end",
        "closed_at": "closed",
        "resolved_at": "resolved",
        "business_duration_seconds": "business_duration",
        "duration_seconds": "duration",
        "made_sla": "made_sla",
        "major_incident": "major_incident",
        "major_problem": "major_problem",
        "known_error": "known_error",
        "related_incidents": "related_incidents",
        "linked_incident_count": "related_incidents",
        "change_request": "change_request",
        "caused_by_change": "caused_by_change",
        "problem_state": "problem_state",
        "close_notes": "close_notes",
        "cause_notes": "cause_notes",
        "fix_notes": "fix_notes",
        "workaround": "workaround",
        "description": "description",
    },
    CHANGE_TICKET_TYPE: {
        "number": "number",
        "short_description": "short_description",
        "type": "type",
        "state": "state",
        "phase": "phase",
        "phase_state": "phase_state",
        "business_application": "business_application",
        "business_service": "business_service",
        "application_name": "application_name",
        "affected_ci_service": "affected_ci_service",
        "category": "category",
        "assignment_group": "assignment_group",
        "assigned_to": "assigned_to",
        "priority": "priority",
        "urgency": "urgency",
        "impact": "impact",
        "risk": "risk",
        "risk_value": "risk_value",
        "vendor": "vendor",
        "created_at_source": "created",
        "opened_at": "opened",
        "planned_start_at": "planned_start_date",
        "planned_end_at": "planned_end_date",
        "actual_start_at": "actual_start_date",
        "actual_end_at": "actual_end_date",
        "closed_at": "closed",
        "business_duration_seconds": "business_duration",
        "duration_seconds": "duration",
        "made_sla": "made_sla",
        "unauthorized": "unauthorized",
        "outside_maintenance_schedule": "outside_maintenance_schedule",
        "cab_required": "cab_required",
        "cab_approval": "cab_approval",
        "cab_date": "cab_date",
        "change_reason": "change_reason",
        "close_code": "close_code",
        "close_code_sub_category": "close_code_sub_category",
        "incident": "incident",
        "problem": "problem",
        "caused_by_change": "caused_by_change",
        "implementation_plan": "implementation_plan",
        "backout_plan": "backout_plan",
        "test_plan": "test_plan",
        "communication_plan": "communication_plan",
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
    out_of_scope_ticket_count: int
    blank_assignment_group_count: int
    assignment_group_not_in_inventory_count: int
    duplicate_skipped_count: int
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
    out_of_scope_ticket_count: int
    blank_assignment_group_count: int
    assignment_group_not_in_inventory_count: int
    duplicate_skipped_count: int
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
    out_of_scope_ticket_count: int
    blank_assignment_group_count: int
    assignment_group_not_in_inventory_count: int
    duplicate_skipped_count: int
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
    elif normalized_ticket_type in PROBLEM_CHANGE_TICKET_TYPES:
        aliases["business_duration_seconds"] = (
            "business_duration",
            "business duration",
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


def mapping_required_fields(ticket_type: str | None) -> set[str]:
    normalized_ticket_type = normalize_ticket_type_value(ticket_type or "")
    if normalized_ticket_type in PROBLEM_CHANGE_TICKET_TYPES:
        return {"number"}
    return {"ticket_id"}


def clean_mapping(mapping: Mapping[str, str], ticket_type: str | None = None) -> dict[str, str]:
    cleaned: dict[str, str] = {}

    for normalized_field, source_column in mapping.items():
        normalized_field = normalized_field.strip()
        source_column = source_column.strip()
        if not normalized_field or not source_column:
            continue
        if normalized_field not in NORMALIZED_FIELDS:
            raise MappingError(f"Unsupported normalized field: {normalized_field}")

        cleaned[normalized_field] = source_column

    required_fields = mapping_required_fields(ticket_type)
    if required_fields == {"number"} and "number" not in cleaned and "ticket_id" in cleaned:
        required_fields = {"ticket_id"}
    missing_required_fields = sorted(required_fields - set(cleaned))
    if missing_required_fields:
        joined = ", ".join(missing_required_fields)
        raise MappingError(f"Mapping must include {joined}.")

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
    cleaned_mapping = clean_mapping(mapping, ticket_type)
    required_fields = mapping_required_fields(ticket_type)
    if required_fields == {"number"} and "number" not in cleaned_mapping:
        required_fields = {"ticket_id"}

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
                is_required=normalized_field in required_fields,
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


def parse_linked_incident_count(value: Any, related_incidents: Any = None) -> int:
    parsed = parse_optional_int_value(value)
    if parsed is not None:
        return max(parsed, 0)

    related_text = text_or_none(related_incidents)
    if related_text is None:
        return 0

    parsed_related = parse_optional_int_value(related_text)
    if parsed_related is not None:
        return max(parsed_related, 0)

    return len(INCIDENT_NUMBER_PATTERN.findall(related_text))


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


def normalize_match_key(value: Any) -> str | None:
    text = text_or_none(value)
    if text is None:
        return None
    normalized = re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip().casefold()
    return normalized or None


def get_raw_vendor_value(
    raw_data: Mapping[str, Any],
    mapping: Mapping[str, str],
    ticket_type: str,
) -> str | None:
    mapped_vendor = text_or_none(get_mapped_value(raw_data, mapping, "vendor"))
    if mapped_vendor is not None:
        return mapped_vendor

    if normalize_ticket_type_value(ticket_type) == "INCIDENT":
        return text_or_none(get_raw_value(raw_data, "scr_vendor"))

    if normalize_ticket_type_value(ticket_type) == "SERVICE_CATALOG_TASK":
        return text_or_none(get_raw_value(raw_data, "u_vendor"))

    return text_or_none(get_raw_value(raw_data, "vendor"))


def load_active_inventory_items(
    db: Session,
    project_id: UUID,
) -> list[ApplicationInventoryItem]:
    statement = (
        select(ApplicationInventoryItem)
        .where(
            ApplicationInventoryItem.project_id == project_id,
            ApplicationInventoryItem.is_current.is_(True),
            ApplicationInventoryItem.active.is_not(False),
        )
        .order_by(
            ApplicationInventoryItem.source_row_number.asc().nullslast(),
            ApplicationInventoryItem.created_at.asc(),
            ApplicationInventoryItem.id.asc(),
        )
    )
    return list(db.scalars(statement).all())


def active_inventory_in_scope_assignment_group_keys(
    db: Session,
    project_id: UUID,
) -> set[str]:
    statement = select(ApplicationInventoryItem.assignment_group).where(
        ApplicationInventoryItem.project_id == project_id,
        ApplicationInventoryItem.is_current.is_(True),
        ApplicationInventoryItem.active.is_not(False),
        ApplicationInventoryItem.scope_status == "in_scope",
        ApplicationInventoryItem.assignment_group.is_not(None),
    )
    return {
        key
        for assignment_group in db.scalars(statement).all()
        if (key := normalize_match_key(assignment_group)) is not None
    }


def inventory_sort_key_for_values(
    inventory_item: ApplicationInventoryItem,
    *,
    assignment_group: str | None,
    business_service: str | None,
    application: str | None,
) -> tuple[int, int, int, datetime, str]:
    active_rank = 0 if inventory_item.active is True else 1
    business_service_rank = 0
    if normalize_match_key(inventory_item.business_service_ci_name) != normalize_match_key(
        business_service
    ):
        business_service_rank = 1

    assignment_group_rank = 0
    if normalize_match_key(inventory_item.assignment_group) != normalize_match_key(
        assignment_group
    ):
        assignment_group_rank = 1

    return (
        active_rank,
        business_service_rank,
        assignment_group_rank,
        inventory_item.source_row_number or 999_999_999,
        inventory_item.created_at,
        str(inventory_item.id),
    )


def inventory_sort_key(
    inventory_item: ApplicationInventoryItem,
    ticket: Ticket,
) -> tuple[int, int, int, datetime, str]:
    return inventory_sort_key_for_values(
        inventory_item,
        assignment_group=ticket.assignment_group,
        business_service=ticket.business_service,
        application=ticket.application,
    )


def select_inventory_item_for_values(
    inventory_items: list[ApplicationInventoryItem],
    *,
    assignment_group: str | None,
    business_service: str | None,
    application: str | None,
) -> ApplicationInventoryItem | None:
    assignment_group_key = normalize_match_key(assignment_group)
    business_service_key = normalize_match_key(business_service)
    application_key = normalize_match_key(application)

    assignment_group_matches = [
        item
        for item in inventory_items
        if normalize_match_key(item.assignment_group) == assignment_group_key
    ]
    if assignment_group_matches:
        return sorted(
            assignment_group_matches,
            key=lambda item: inventory_sort_key_for_values(
                item,
                assignment_group=assignment_group,
                business_service=business_service,
                application=application,
            ),
        )[0]

    service_keys = {business_service_key, application_key}
    service_keys.discard(None)
    service_matches = [
        item
        for item in inventory_items
        if normalize_match_key(item.business_service_ci_name) in service_keys
    ]
    if service_matches:
        return sorted(
            service_matches,
            key=lambda item: inventory_sort_key_for_values(
                item,
                assignment_group=assignment_group,
                business_service=business_service,
                application=application,
            ),
        )[0]

    return None


def select_inventory_item_for_ticket(
    ticket: Ticket,
    inventory_items: list[ApplicationInventoryItem],
) -> ApplicationInventoryItem | None:
    return select_inventory_item_for_values(
        inventory_items,
        assignment_group=ticket.assignment_group,
        business_service=ticket.business_service,
        application=ticket.application,
    )


def select_inventory_item_for_business_service_ci(
    inventory_items: list[ApplicationInventoryItem],
    business_service_ci_name: str | None,
) -> ApplicationInventoryItem | None:
    business_service_key = normalize_match_key(business_service_ci_name)
    if business_service_key is None:
        return None

    matches = [
        item
        for item in inventory_items
        if normalize_match_key(item.business_service_ci_name) == business_service_key
    ]
    if not matches:
        return None

    return sorted(
        matches,
        key=lambda item: (
            0 if item.active is True else 1,
            item.source_row_number or 999_999_999,
            item.created_at,
            str(item.id),
        ),
    )[0]


def inventory_items_for_assignment_group(
    inventory_items: list[ApplicationInventoryItem],
    assignment_group: str | None,
) -> list[ApplicationInventoryItem]:
    assignment_group_key = normalize_match_key(assignment_group)
    if assignment_group_key is None:
        return []
    return [
        item
        for item in inventory_items
        if normalize_match_key(item.assignment_group) == assignment_group_key
    ]


def collapse_inventory_values_for_support_group(
    inventory_items: list[ApplicationInventoryItem],
    field_name: str,
) -> str | None:
    values_by_key: dict[str, str] = {}
    for item in inventory_items:
        value = text_or_none(getattr(item, field_name))
        if value is None:
            continue
        values_by_key.setdefault(normalize_match_key(value) or value.casefold(), value)
    if not values_by_key:
        return None
    if len(values_by_key) == 1:
        return next(iter(values_by_key.values()))
    return "Multiple"


def apply_service_inventory_enrichment_to_ticket(
    ticket: Ticket,
    inventory_items: list[ApplicationInventoryItem],
) -> None:
    ticket.functional_track = collapse_inventory_values_for_support_group(
        inventory_items,
        "functional_track",
    )
    ticket.service_type = collapse_inventory_values_for_support_group(
        inventory_items,
        "service_type",
    )
    ticket.service_entitlement = collapse_inventory_values_for_support_group(
        inventory_items,
        "service_entitlement",
    )
    ticket.sap_non_sap = (
        collapse_inventory_values_for_support_group(inventory_items, "sap_non_sap")
        or ticket.sap_non_sap
    )


def apply_inventory_enrichment_to_ticket(
    ticket: Ticket,
    inventory_item: ApplicationInventoryItem | None,
) -> None:
    if inventory_item is None:
        return

    ticket.application_inventory_id = inventory_item.id
    ticket.parent_application_number = inventory_item.application_number_apm
    ticket.parent_application_name = inventory_item.parent_application_name
    ticket.business_service_ci_name = inventory_item.business_service_ci_name
    ticket.application_owner = inventory_item.application_owner
    ticket.support_lead = inventory_item.support_lead
    ticket.functional_track = inventory_item.functional_track
    ticket.ams_owner = inventory_item.ams_owner
    ticket.supported_by_vendor = inventory_item.supported_by_vendor
    ticket.service_type = text_or_none(inventory_item.service_type)
    ticket.service_entitlement = text_or_none(inventory_item.service_entitlement)
    ticket.assignment_group_owner = inventory_item.assignment_group_owner
    ticket.derived_vendor = inventory_item.supported_by_vendor
    ticket.hosting_env = inventory_item.hosting_env
    ticket.architecture_type = cmdb_payload_text(
        inventory_item.cmdb_payload,
        *CMDB_ARCHITECTURE_TYPE_KEYS,
    )
    ticket.business_critical = cmdb_payload_text(
        inventory_item.cmdb_payload,
        *CMDB_BUSINESS_CRITICAL_KEYS,
    )
    ticket.install_type = cmdb_payload_text(inventory_item.cmdb_payload, *CMDB_INSTALL_TYPE_KEYS)


OperationalRecord = (
    AssessmentProblemRecord
    | AssessmentOutOfScopeProblemRecord
    | AssessmentChangeRecord
    | AssessmentOutOfScopeChangeRecord
)


def apply_inventory_enrichment_to_operational_record(
    record: OperationalRecord,
    inventory_item: ApplicationInventoryItem | None,
) -> None:
    if inventory_item is None:
        record.application_inventory_match_status = "unmatched"
        return

    record.application_inventory_id = inventory_item.id
    record.functional_track = inventory_item.functional_track
    record.ams_owner = inventory_item.ams_owner
    record.parent_business_application = inventory_item.parent_application_name
    record.supported_by_vendor = inventory_item.supported_by_vendor
    record.sap_non_sap = inventory_item.sap_non_sap or record.sap_non_sap
    record.architecture_type = cmdb_payload_text(
        inventory_item.cmdb_payload,
        *CMDB_ARCHITECTURE_TYPE_KEYS,
    )
    record.install_type = cmdb_payload_text(inventory_item.cmdb_payload, *CMDB_INSTALL_TYPE_KEYS)
    record.application_inventory_match_status = "matched"


def operational_record_scope_reason(
    record: OperationalRecord,
    active_assignment_groups: set[str],
) -> str:
    assignment_group_key = normalize_match_key(record.assignment_group)
    if assignment_group_key is None:
        return "blank_assignment_group"
    if assignment_group_key not in active_assignment_groups:
        return "assignment_group_not_in_scope_reference"
    return ""


def build_out_of_scope_problem_record(
    record: AssessmentProblemRecord,
    reason: str,
) -> AssessmentOutOfScopeProblemRecord:
    return AssessmentOutOfScopeProblemRecord(
        project_id=record.project_id,
        upload_batch_id=record.upload_batch_id,
        uploaded_file_id=record.uploaded_file_id,
        raw_row_id=record.raw_row_id,
        application_inventory_id=record.application_inventory_id,
        source_row_number=record.source_row_number,
        row_fingerprint=record.row_fingerprint,
        number=record.number,
        state=record.state,
        problem_state=record.problem_state,
        problem_statement=record.problem_statement,
        short_description_or_statement=record.short_description_or_statement,
        description=record.description,
        business_application=record.business_application,
        business_service=record.business_service,
        configuration_item=record.configuration_item,
        category=record.category,
        subcategory=record.subcategory,
        assignment_group=record.assignment_group,
        assigned_to=record.assigned_to,
        urgency=record.urgency,
        priority=record.priority,
        active=record.active,
        created_at_source=record.created_at_source,
        opened_at=record.opened_at,
        actual_start_at=record.actual_start_at,
        actual_end_at=record.actual_end_at,
        closed_at=record.closed_at,
        resolved_at=record.resolved_at,
        business_duration_seconds=record.business_duration_seconds,
        duration_seconds=record.duration_seconds,
        made_sla=record.made_sla,
        major_incident=record.major_incident,
        major_problem=record.major_problem,
        known_error=record.known_error,
        related_incidents=record.related_incidents,
        linked_incident_count=record.linked_incident_count,
        change_request=record.change_request,
        caused_by_change=record.caused_by_change,
        duplicate_of=record.duplicate_of,
        parent=record.parent,
        reassignment_count=record.reassignment_count,
        reopen_count=record.reopen_count,
        resolution_code=record.resolution_code,
        close_notes=record.close_notes,
        cause_notes=record.cause_notes,
        fix_notes=record.fix_notes,
        workaround=record.workaround,
        source=record.source,
        contact_type=record.contact_type,
        company=record.company,
        vendor_or_supplier_if_available=record.vendor_or_supplier_if_available,
        functional_track=record.functional_track,
        ams_owner=record.ams_owner,
        parent_business_application=record.parent_business_application,
        supported_by_vendor=record.supported_by_vendor,
        sap_non_sap=record.sap_non_sap,
        architecture_type=record.architecture_type,
        install_type=record.install_type,
        application_inventory_match_status=record.application_inventory_match_status,
        out_of_scope_reason=reason,
        normalized_payload=record.normalized_payload,
    )


def build_out_of_scope_change_record(
    record: AssessmentChangeRecord,
    reason: str,
) -> AssessmentOutOfScopeChangeRecord:
    return AssessmentOutOfScopeChangeRecord(
        project_id=record.project_id,
        upload_batch_id=record.upload_batch_id,
        uploaded_file_id=record.uploaded_file_id,
        raw_row_id=record.raw_row_id,
        application_inventory_id=record.application_inventory_id,
        source_row_number=record.source_row_number,
        row_fingerprint=record.row_fingerprint,
        number=record.number,
        short_description=record.short_description,
        type=record.type,
        state=record.state,
        phase=record.phase,
        phase_state=record.phase_state,
        business_application=record.business_application,
        business_service=record.business_service,
        application_name=record.application_name,
        affected_ci_service=record.affected_ci_service,
        category=record.category,
        assignment_group=record.assignment_group,
        assigned_to=record.assigned_to,
        priority=record.priority,
        urgency=record.urgency,
        impact=record.impact,
        risk=record.risk,
        risk_value=record.risk_value,
        vendor=record.vendor,
        created_at_source=record.created_at_source,
        opened_at=record.opened_at,
        planned_start_at=record.planned_start_at,
        planned_end_at=record.planned_end_at,
        actual_start_at=record.actual_start_at,
        actual_end_at=record.actual_end_at,
        closed_at=record.closed_at,
        business_duration_seconds=record.business_duration_seconds,
        duration_seconds=record.duration_seconds,
        made_sla=record.made_sla,
        unauthorized=record.unauthorized,
        outside_maintenance_schedule=record.outside_maintenance_schedule,
        cab_required=record.cab_required,
        cab_approval=record.cab_approval,
        cab_date=record.cab_date,
        change_reason=record.change_reason,
        close_code=record.close_code,
        close_code_sub_category=record.close_code_sub_category,
        incident=record.incident,
        problem=record.problem,
        caused_by_change=record.caused_by_change,
        parent=record.parent,
        reassignment_count=record.reassignment_count,
        service_outage_required=record.service_outage_required,
        implementation_plan=record.implementation_plan,
        backout_plan=record.backout_plan,
        test_plan=record.test_plan,
        communication_plan=record.communication_plan,
        functional_track=record.functional_track,
        ams_owner=record.ams_owner,
        parent_business_application=record.parent_business_application,
        supported_by_vendor=record.supported_by_vendor,
        sap_non_sap=record.sap_non_sap,
        architecture_type=record.architecture_type,
        install_type=record.install_type,
        application_inventory_match_status=record.application_inventory_match_status,
        out_of_scope_reason=reason,
        normalized_payload=record.normalized_payload,
    )


def cmdb_payload_text(payload: Mapping[str, Any] | None, *keys: str) -> str | None:
    if not payload:
        return None
    for key in keys:
        value = text_or_none(payload.get(key))
        if value is not None:
            return value
    return None


def build_out_of_scope_ticket(
    ticket: Ticket,
    reason: str,
) -> AssessmentOutOfScopeTicket:
    return AssessmentOutOfScopeTicket(
        project_id=ticket.project_id,
        upload_batch_id=ticket.upload_batch_id,
        source_raw_row_id=ticket.raw_row_id,
        application_inventory_id=ticket.application_inventory_id,
        ticket_number=ticket.ticket_number,
        ticket_type=ticket.ticket_type,
        month_key=ticket.month_key,
        source_system=ticket.source_system,
        created_at=ticket.created_at,
        updated_at=ticket.updated_at,
        resolved_at=ticket.resolved_at,
        closed_at=ticket.closed_at,
        due_at=ticket.due_at,
        short_description=ticket.short_description,
        description=ticket.description,
        state=ticket.state,
        priority=ticket.priority,
        urgency=ticket.urgency,
        impact=ticket.impact,
        application=ticket.application,
        business_service=ticket.business_service,
        assignment_group=ticket.assignment_group,
        assigned_to=ticket.assigned_to,
        requester=ticket.requester,
        opened_by=ticket.opened_by,
        created_by=ticket.created_by,
        category=ticket.category,
        subcategory=ticket.subcategory,
        catalog_item=ticket.catalog_item,
        catalog_item_name=ticket.catalog_item_name,
        catalog_knowledge_base=ticket.catalog_knowledge_base,
        service_offering=ticket.service_offering,
        reopen_count=ticket.reopen_count,
        reassignment_count=ticket.reassignment_count,
        business_duration_seconds=ticket.business_duration_seconds,
        is_system_created=ticket.is_system_created,
        system_creation_source=ticket.system_creation_source,
        is_technical=ticket.is_technical,
        technical_functional_type=ticket.technical_functional_type,
        technical_functional_confidence=ticket.technical_functional_confidence,
        technical_functional_reason=ticket.technical_functional_reason,
        classification_level_1=ticket.classification_level_1,
        classification_level_2=ticket.classification_level_2,
        classification_level_3=ticket.classification_level_3,
        classification_level_4=ticket.classification_level_4,
        improvement_area=ticket.improvement_area,
        estimated_effort_hours=ticket.estimated_effort_hours,
        vendor=ticket.vendor,
        derived_vendor=ticket.derived_vendor,
        parent_application_number=ticket.parent_application_number,
        parent_application_name=ticket.parent_application_name,
        business_service_ci_name=ticket.business_service_ci_name,
        application_owner=ticket.application_owner,
        support_lead=ticket.support_lead,
        functional_track=ticket.functional_track,
        ams_owner=ticket.ams_owner,
        supported_by_vendor=ticket.supported_by_vendor,
        service_type=ticket.service_type,
        service_entitlement=ticket.service_entitlement,
        assignment_group_owner=ticket.assignment_group_owner,
        sap_non_sap=ticket.sap_non_sap,
        architecture_type=ticket.architecture_type,
        business_critical=ticket.business_critical,
        install_type=ticket.install_type,
        hosting_env=ticket.hosting_env,
        is_batch_related=ticket.is_batch_related,
        out_of_scope_reason=reason,
    )


def resolve_apply_mapping(
    db: Session,
    upload_batch: UploadBatch,
    mapping: Mapping[str, str] | None,
) -> dict[str, str]:
    ticket_type = get_batch_ticket_type(db, upload_batch.id)
    if not ticket_type:
        raise MappingError("No raw rows found. Ingest files before applying a mapping.")

    if mapping:
        return clean_mapping(mapping, ticket_type)

    template_rows = get_mapping_template(db, upload_batch.project_id, ticket_type)
    if not template_rows:
        raise MappingError(
            "No saved mapping template found. Pass a mapping in the request or save a template."
        )
    return clean_mapping(mapping_rows_to_field_mapping(template_rows), ticket_type)


def collect_normalized_values(
    raw_data: Mapping[str, Any],
    mapping: Mapping[str, str],
) -> dict[str, Any]:
    return {
        field: get_mapped_value(raw_data, mapping, field)
        for field in NORMALIZED_FIELDS
        if field in mapping
    }


def normalized_payload_for_raw_row(
    raw_row: TicketRawRow,
    mapping: Mapping[str, str],
    normalized_values: Mapping[str, Any],
) -> dict[str, Any]:
    mapped_source_keys = {
        normalize_source_column_name(source_column) for source_column in mapping.values()
    }
    unmapped_fields = {
        source_column: raw_value
        for source_column, raw_value in raw_row.raw_data.items()
        if normalize_source_column_name(source_column) not in mapped_source_keys
    }
    return {
        "raw_payload_json": raw_row.raw_data,
        "unmapped_fields": unmapped_fields,
        "mapped_fields": {
            field: text_or_none(value) for field, value in normalized_values.items()
        },
    }


def record_number_from_values(normalized_values: Mapping[str, Any]) -> str | None:
    return text_or_none(normalized_values.get("number")) or text_or_none(
        normalized_values.get("ticket_id")
    )


def first_text_value(*values: Any) -> str | None:
    for value in values:
        text = text_or_none(value)
        if text is not None:
            return text
    return None


def build_ticket_from_raw_row(
    raw_row: TicketRawRow,
    upload_batch: UploadBatch,
    mapping: Mapping[str, str],
) -> Ticket:
    ticket_number = text_or_none(get_mapped_value(raw_row.raw_data, mapping, "ticket_id"))
    if ticket_number is None:
        raise MappingError("Mapped ticket_id is empty.")

    normalized_values = collect_normalized_values(raw_row.raw_data, mapping)
    mapped_ticket_type = text_or_none(normalized_values.get("ticket_type"))
    ticket_type = mapped_ticket_type.upper() if mapped_ticket_type else raw_row.ticket_type
    source_system = (
        text_or_none(normalized_values.get("source_system")) or upload_batch.source_system
    )
    short_description = text_or_none(normalized_values.get("title"))

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
        short_description=short_description,
        description=text_or_none(normalized_values.get("description")),
        state=text_or_none(normalized_values.get("status")),
        priority=normalize_priority(normalized_values.get("priority")),
        urgency=text_or_none(normalized_values.get("urgency")),
        impact=text_or_none(normalized_values.get("impact")),
        application=text_or_none(normalized_values.get("application")),
        business_service=text_or_none(normalized_values.get("business_service")),
        cmdb_ci=text_or_none(normalized_values.get("configuration_item")),
        assignment_group=text_or_none(normalized_values.get("assignment_group")),
        sap_non_sap=derive_sap_non_sap(normalized_values.get("assignment_group")),
        is_batch_related=derive_is_batch_related(ticket_type, short_description),
        assigned_to=text_or_none(normalized_values.get("assigned_to")),
        requester=text_or_none(normalized_values.get("requester")),
        opened_by=text_or_none(normalized_values.get("created_by")),
        created_by=text_or_none(normalized_values.get("created_by")),
        category=text_or_none(normalized_values.get("category")),
        subcategory=text_or_none(normalized_values.get("subcategory")),
        catalog_item=text_or_none(normalized_values.get("catalog_item")),
        catalog_item_name=text_or_none(normalized_values.get("catalog_item_name")),
        catalog_knowledge_base=text_or_none(
            normalized_values.get("catalog_knowledge_base"),
        ),
        service_offering=text_or_none(normalized_values.get("service_offering")),
        vendor=get_raw_vendor_value(raw_row.raw_data, mapping, ticket_type),
        sla_breached=parse_sla_breached_value(
            normalized_values.get("sla_breached"),
            mapping.get("sla_breached"),
        ),
        business_duration_seconds=parse_business_duration_seconds(
            normalized_values.get("business_duration_seconds"),
        ),
        reopen_count=parse_int_value(normalized_values.get("reopen_count")),
        reassignment_count=parse_optional_int_value(normalized_values.get("reassignment_count")),
        normalized_payload=normalized_payload_for_raw_row(
            raw_row,
            mapping,
            normalized_values,
        ),
    )


def build_problem_record_from_raw_row(
    raw_row: TicketRawRow,
    upload_batch: UploadBatch,
    mapping: Mapping[str, str],
) -> AssessmentProblemRecord:
    normalized_values = collect_normalized_values(raw_row.raw_data, mapping)
    number = record_number_from_values(normalized_values)
    if number is None:
        raise MappingError("Mapped Problem Number is empty.")

    assignment_group = text_or_none(normalized_values.get("assignment_group"))
    problem_statement = text_or_none(normalized_values.get("problem_statement"))
    description = text_or_none(normalized_values.get("description"))
    related_incidents = text_or_none(normalized_values.get("related_incidents"))
    short_description_or_statement = first_text_value(
        normalized_values.get("short_description_or_statement"),
        problem_statement,
        description,
    )

    return AssessmentProblemRecord(
        project_id=raw_row.project_id,
        upload_batch_id=upload_batch.id,
        uploaded_file_id=raw_row.uploaded_file_id,
        raw_row_id=raw_row.id,
        source_row_number=raw_row.row_number,
        row_fingerprint=raw_row.row_hash or str(raw_row.id),
        number=number,
        state=text_or_none(normalized_values.get("state")),
        problem_state=text_or_none(normalized_values.get("problem_state")),
        problem_statement=problem_statement,
        short_description_or_statement=short_description_or_statement,
        description=description,
        business_application=text_or_none(normalized_values.get("business_application")),
        business_service=text_or_none(normalized_values.get("business_service")),
        configuration_item=text_or_none(normalized_values.get("configuration_item")),
        category=text_or_none(normalized_values.get("category")),
        subcategory=text_or_none(normalized_values.get("subcategory")),
        assignment_group=assignment_group,
        assigned_to=text_or_none(normalized_values.get("assigned_to")),
        urgency=text_or_none(normalized_values.get("urgency")),
        priority=normalize_priority(normalized_values.get("priority")),
        active=parse_bool_value(normalized_values.get("active")),
        created_at_source=parse_datetime_value(normalized_values.get("created_at_source")),
        opened_at=parse_datetime_value(normalized_values.get("opened_at")),
        actual_start_at=parse_datetime_value(normalized_values.get("actual_start_at")),
        actual_end_at=parse_datetime_value(normalized_values.get("actual_end_at")),
        closed_at=parse_datetime_value(normalized_values.get("closed_at")),
        resolved_at=parse_datetime_value(normalized_values.get("resolved_at")),
        business_duration_seconds=parse_business_duration_seconds(
            normalized_values.get("business_duration_seconds"),
        ),
        duration_seconds=parse_business_duration_seconds(
            normalized_values.get("duration_seconds"),
        ),
        made_sla=parse_bool_value(normalized_values.get("made_sla")),
        major_incident=parse_bool_value(normalized_values.get("major_incident")),
        major_problem=parse_bool_value(normalized_values.get("major_problem")),
        known_error=parse_bool_value(normalized_values.get("known_error")),
        related_incidents=related_incidents,
        linked_incident_count=parse_linked_incident_count(
            normalized_values.get("linked_incident_count"),
            related_incidents,
        ),
        change_request=text_or_none(normalized_values.get("change_request")),
        caused_by_change=text_or_none(normalized_values.get("caused_by_change")),
        duplicate_of=text_or_none(normalized_values.get("duplicate_of")),
        parent=text_or_none(normalized_values.get("parent")),
        reassignment_count=parse_optional_int_value(
            normalized_values.get("reassignment_count"),
        ),
        reopen_count=parse_optional_int_value(normalized_values.get("reopen_count")),
        resolution_code=text_or_none(normalized_values.get("resolution_code")),
        close_notes=text_or_none(normalized_values.get("close_notes")),
        cause_notes=text_or_none(normalized_values.get("cause_notes")),
        fix_notes=text_or_none(normalized_values.get("fix_notes")),
        workaround=text_or_none(normalized_values.get("workaround")),
        source=text_or_none(normalized_values.get("source")),
        contact_type=text_or_none(normalized_values.get("contact_type")),
        company=text_or_none(normalized_values.get("company")),
        vendor_or_supplier_if_available=text_or_none(
            normalized_values.get("vendor_or_supplier_if_available"),
        ),
        sap_non_sap=derive_sap_non_sap(assignment_group),
        normalized_payload=normalized_payload_for_raw_row(
            raw_row,
            mapping,
            normalized_values,
        ),
    )


def build_change_record_from_raw_row(
    raw_row: TicketRawRow,
    upload_batch: UploadBatch,
    mapping: Mapping[str, str],
) -> AssessmentChangeRecord:
    normalized_values = collect_normalized_values(raw_row.raw_data, mapping)
    number = record_number_from_values(normalized_values)
    if number is None:
        raise MappingError("Mapped Change Number is empty.")

    assignment_group = text_or_none(normalized_values.get("assignment_group"))

    return AssessmentChangeRecord(
        project_id=raw_row.project_id,
        upload_batch_id=upload_batch.id,
        uploaded_file_id=raw_row.uploaded_file_id,
        raw_row_id=raw_row.id,
        source_row_number=raw_row.row_number,
        row_fingerprint=raw_row.row_hash or str(raw_row.id),
        number=number,
        short_description=text_or_none(normalized_values.get("short_description")),
        type=text_or_none(normalized_values.get("type")),
        state=text_or_none(normalized_values.get("state")),
        phase=text_or_none(normalized_values.get("phase")),
        phase_state=text_or_none(normalized_values.get("phase_state")),
        business_application=text_or_none(normalized_values.get("business_application")),
        business_service=text_or_none(normalized_values.get("business_service")),
        application_name=text_or_none(normalized_values.get("application_name")),
        affected_ci_service=text_or_none(normalized_values.get("affected_ci_service")),
        category=text_or_none(normalized_values.get("category")),
        assignment_group=assignment_group,
        assigned_to=text_or_none(normalized_values.get("assigned_to")),
        priority=normalize_priority(normalized_values.get("priority")),
        urgency=text_or_none(normalized_values.get("urgency")),
        impact=text_or_none(normalized_values.get("impact")),
        risk=text_or_none(normalized_values.get("risk")),
        risk_value=text_or_none(normalized_values.get("risk_value")),
        vendor=text_or_none(normalized_values.get("vendor")),
        created_at_source=parse_datetime_value(normalized_values.get("created_at_source")),
        opened_at=parse_datetime_value(normalized_values.get("opened_at")),
        planned_start_at=parse_datetime_value(normalized_values.get("planned_start_at")),
        planned_end_at=parse_datetime_value(normalized_values.get("planned_end_at")),
        actual_start_at=parse_datetime_value(normalized_values.get("actual_start_at")),
        actual_end_at=parse_datetime_value(normalized_values.get("actual_end_at")),
        closed_at=parse_datetime_value(normalized_values.get("closed_at")),
        business_duration_seconds=parse_business_duration_seconds(
            normalized_values.get("business_duration_seconds"),
        ),
        duration_seconds=parse_business_duration_seconds(
            normalized_values.get("duration_seconds"),
        ),
        made_sla=parse_bool_value(normalized_values.get("made_sla")),
        unauthorized=parse_bool_value(normalized_values.get("unauthorized")),
        outside_maintenance_schedule=parse_bool_value(
            normalized_values.get("outside_maintenance_schedule"),
        ),
        cab_required=parse_bool_value(normalized_values.get("cab_required")),
        cab_approval=text_or_none(normalized_values.get("cab_approval")),
        cab_date=parse_datetime_value(normalized_values.get("cab_date")),
        change_reason=text_or_none(normalized_values.get("change_reason")),
        close_code=text_or_none(normalized_values.get("close_code")),
        close_code_sub_category=text_or_none(
            normalized_values.get("close_code_sub_category"),
        ),
        incident=text_or_none(normalized_values.get("incident")),
        problem=text_or_none(normalized_values.get("problem")),
        caused_by_change=text_or_none(normalized_values.get("caused_by_change")),
        parent=text_or_none(normalized_values.get("parent")),
        reassignment_count=parse_optional_int_value(
            normalized_values.get("reassignment_count"),
        ),
        service_outage_required=parse_bool_value(
            normalized_values.get("service_outage_required"),
        ),
        implementation_plan=text_or_none(normalized_values.get("implementation_plan")),
        backout_plan=text_or_none(normalized_values.get("backout_plan")),
        test_plan=text_or_none(normalized_values.get("test_plan")),
        communication_plan=text_or_none(normalized_values.get("communication_plan")),
        sap_non_sap=derive_sap_non_sap(assignment_group),
        normalized_payload=normalized_payload_for_raw_row(
            raw_row,
            mapping,
            normalized_values,
        ),
    )


def select_inventory_item_for_operational_record(
    record: OperationalRecord,
    inventory_items: list[ApplicationInventoryItem],
) -> ApplicationInventoryItem | None:
    application = first_text_value(
        getattr(record, "business_application", None),
        getattr(record, "business_service", None),
        getattr(record, "configuration_item", None),
        getattr(record, "application_name", None),
        getattr(record, "affected_ci_service", None),
    )
    return select_inventory_item_for_values(
        inventory_items,
        assignment_group=record.assignment_group,
        business_service=record.business_service,
        application=application,
    )


def apply_problem_or_change_mapping_to_batch(
    db: Session,
    upload_batch: UploadBatch,
    resolved_mapping: Mapping[str, str],
    ticket_type: str,
    delete_existing: bool,
) -> ApplyMappingResult:
    model: type[AssessmentProblemRecord] | type[AssessmentChangeRecord]
    out_model: type[AssessmentOutOfScopeProblemRecord] | type[AssessmentOutOfScopeChangeRecord]
    if ticket_type == PROBLEM_TICKET_TYPE:
        model = AssessmentProblemRecord
        out_model = AssessmentOutOfScopeProblemRecord
        builder = build_problem_record_from_raw_row
        out_builder = build_out_of_scope_problem_record
        record_label = "Problem"
    else:
        model = AssessmentChangeRecord
        out_model = AssessmentOutOfScopeChangeRecord
        builder = build_change_record_from_raw_row
        out_builder = build_out_of_scope_change_record
        record_label = "Change"

    total_raw_rows = 0
    normalized_record_count = 0
    out_of_scope_record_count = 0
    blank_assignment_group_count = 0
    assignment_group_not_in_inventory_count = 0
    unmatched_inventory_count = 0
    duplicate_skipped_count = 0
    failed_row_count = 0
    errors: list[NormalizationErrorSample] = []
    warnings: list[str] = []
    seen_fingerprints: set[str] = set()

    mark_upload_batch_normalizing(upload_batch)
    db.flush()

    if delete_existing:
        db.execute(delete(model).where(model.upload_batch_id == upload_batch.id))
        db.execute(delete(out_model).where(out_model.upload_batch_id == upload_batch.id))
        db.flush()

    inventory_items = load_active_inventory_items(db, upload_batch.project_id)
    active_assignment_groups = active_inventory_in_scope_assignment_group_keys(
        db,
        upload_batch.project_id,
    )
    if not active_assignment_groups:
        warnings.append(
            "No active CMDB/Application Inventory in-scope assignment groups were found for "
            "this project; records with non-blank assignment groups will be classified as "
            "out of scope.",
        )
    existing_fingerprint_statement = select(model.row_fingerprint).where(
        model.project_id == upload_batch.project_id,
        model.upload_batch_id != upload_batch.id,
    )
    existing_out_fingerprint_statement = select(out_model.row_fingerprint).where(
        out_model.project_id == upload_batch.project_id,
        out_model.upload_batch_id != upload_batch.id,
    )
    existing_fingerprints = set(db.scalars(existing_fingerprint_statement).all())
    existing_fingerprints.update(db.scalars(existing_out_fingerprint_statement).all())

    raw_row_statement = (
        select(TicketRawRow)
        .where(TicketRawRow.upload_batch_id == upload_batch.id)
        .order_by(TicketRawRow.uploaded_file_id.asc(), TicketRawRow.row_number.asc())
    )

    for raw_row in db.scalars(raw_row_statement).yield_per(INGESTION_BATCH_SIZE):
        total_raw_rows += 1
        try:
            record = builder(raw_row, upload_batch, resolved_mapping)
            if (
                record.row_fingerprint in existing_fingerprints
                or record.row_fingerprint in seen_fingerprints
            ):
                duplicate_skipped_count += 1
                continue
            seen_fingerprints.add(record.row_fingerprint)

            inventory_item = select_inventory_item_for_operational_record(
                record,
                inventory_items,
            )
            apply_inventory_enrichment_to_operational_record(record, inventory_item)
            support_group_items = inventory_items_for_assignment_group(
                inventory_items,
                record.assignment_group,
            )
            support_group_track = collapse_inventory_values_for_support_group(
                support_group_items,
                "functional_track",
            )
            if support_group_track is not None:
                record.functional_track = support_group_track
            if record.application_inventory_match_status == "unmatched":
                unmatched_inventory_count += 1

            out_of_scope_reason = operational_record_scope_reason(
                record,
                active_assignment_groups,
            )
            if out_of_scope_reason == "blank_assignment_group":
                blank_assignment_group_count += 1
            elif out_of_scope_reason:
                assignment_group_not_in_inventory_count += 1

            if out_of_scope_reason:
                db.add(out_builder(record, out_of_scope_reason))
                out_of_scope_record_count += 1
            else:
                db.add(record)
                normalized_record_count += 1
            processed_record_count = normalized_record_count + out_of_scope_record_count
            if processed_record_count % INGESTION_BATCH_SIZE == 0:
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
    if duplicate_skipped_count:
        warnings.append(
            f"{duplicate_skipped_count} duplicate {record_label} row(s) were skipped."
        )
    if unmatched_inventory_count:
        warnings.append(
            f"{unmatched_inventory_count} {record_label} row(s) did not match "
            "Application Inventory enrichment."
        )
    if out_of_scope_record_count:
        warnings.append(
            f"{out_of_scope_record_count} {record_label} row(s) were classified as "
            "out of scope by the CMDB/Application Inventory in-scope assignment group "
            "reference."
        )

    if total_raw_rows > 0 and failed_row_count == 0:
        mark_upload_batch_normalized(upload_batch)
    else:
        mark_upload_batch_normalization_failed(upload_batch)

    return ApplyMappingResult(
        upload_batch_id=upload_batch.id,
        total_raw_rows=total_raw_rows,
        normalized_ticket_count=normalized_record_count,
        out_of_scope_ticket_count=out_of_scope_record_count,
        blank_assignment_group_count=blank_assignment_group_count,
        assignment_group_not_in_inventory_count=assignment_group_not_in_inventory_count,
        duplicate_skipped_count=duplicate_skipped_count,
        failed_row_count=failed_row_count,
        warnings=warnings[:MAX_WARNING_SAMPLES],
        errors=errors,
        status=upload_batch.status,
    )


def apply_mapping_to_batch(
    db: Session,
    upload_batch_id: UUID,
    mapping: Mapping[str, str] | None = None,
    delete_existing: bool = True,
) -> ApplyMappingResult:
    upload_batch = get_upload_batch_or_raise(db, upload_batch_id)
    batch_ticket_type = get_batch_ticket_type(db, upload_batch_id)
    resolved_mapping = resolve_apply_mapping(db, upload_batch, mapping)

    if batch_ticket_type in PROBLEM_CHANGE_TICKET_TYPES:
        try:
            result = apply_problem_or_change_mapping_to_batch(
                db=db,
                upload_batch=upload_batch,
                resolved_mapping=resolved_mapping,
                ticket_type=batch_ticket_type,
                delete_existing=delete_existing,
            )
            db.commit()
        except SQLAlchemyError as exc:
            db.rollback()
            failed_batch = db.get(UploadBatch, upload_batch_id)
            if failed_batch is not None:
                mark_upload_batch_normalization_failed(failed_batch)
                db.commit()
            raise MappingError(f"Mapping apply failed: {exc}") from exc
        db.refresh(upload_batch)
        return result

    total_raw_rows = 0
    normalized_ticket_count = 0
    out_of_scope_ticket_count = 0
    blank_assignment_group_count = 0
    assignment_group_not_in_inventory_count = 0
    failed_row_count = 0
    errors: list[NormalizationErrorSample] = []
    warnings: list[str] = []
    seen_ticket_destinations: dict[str, str] = {}
    duplicate_ticket_replacement_count = 0

    try:
        mark_upload_batch_normalizing(upload_batch)
        db.flush()

        if delete_existing:
            db.execute(delete(Ticket).where(Ticket.upload_batch_id == upload_batch_id))
            db.execute(
                delete(AssessmentOutOfScopeTicket).where(
                    AssessmentOutOfScopeTicket.upload_batch_id == upload_batch_id
                )
            )
            db.flush()

        inventory_items = load_active_inventory_items(db, upload_batch.project_id)
        active_assignment_groups = active_inventory_in_scope_assignment_group_keys(
            db,
            upload_batch.project_id,
        )
        if not active_assignment_groups:
            warnings.append(
                "No active CMDB/Application Inventory in-scope assignment groups were found "
                "for this project; tickets with non-blank assignment groups will be "
                "classified as out of scope.",
            )

        raw_row_statement = (
            select(TicketRawRow)
            .where(TicketRawRow.upload_batch_id == upload_batch_id)
            .order_by(TicketRawRow.uploaded_file_id.asc(), TicketRawRow.row_number.asc())
        )

        for raw_row in db.scalars(raw_row_statement).yield_per(INGESTION_BATCH_SIZE):
            total_raw_rows += 1
            try:
                ticket = build_ticket_from_raw_row(raw_row, upload_batch, resolved_mapping)
                previous_destination = seen_ticket_destinations.get(ticket.ticket_number)
                if previous_destination is not None:
                    if not delete_existing:
                        raise MappingError(
                            f"Duplicate ticket_id in batch: {ticket.ticket_number}"
                        )
                    db.flush()
                    duplicate_ticket_replacement_count += 1
                    if previous_destination == "IN_SCOPE":
                        normalized_ticket_count -= 1
                    elif previous_destination == "OUT_OF_SCOPE_BLANK_ASSIGNMENT_GROUP":
                        out_of_scope_ticket_count -= 1
                        blank_assignment_group_count -= 1
                    elif previous_destination == OUT_OF_SCOPE_SCOPE_REFERENCE_DESTINATION:
                        out_of_scope_ticket_count -= 1
                        assignment_group_not_in_inventory_count -= 1

                if delete_existing:
                    db.execute(
                        delete(Ticket).where(
                            Ticket.project_id == ticket.project_id,
                            Ticket.ticket_number == ticket.ticket_number,
                        )
                    )
                    db.execute(
                        delete(AssessmentOutOfScopeTicket).where(
                            AssessmentOutOfScopeTicket.project_id == ticket.project_id,
                            AssessmentOutOfScopeTicket.ticket_number == ticket.ticket_number,
                        )
                    )

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
                existing_out_of_scope_ticket_id = db.scalar(
                    select(AssessmentOutOfScopeTicket.id)
                    .where(
                        AssessmentOutOfScopeTicket.project_id == ticket.project_id,
                        AssessmentOutOfScopeTicket.ticket_number == ticket.ticket_number,
                    )
                    .limit(1)
                )
                if existing_out_of_scope_ticket_id is not None:
                    raise MappingError(
                        f"Ticket {ticket.ticket_number} already exists as out of scope."
                    )

                inventory_item = select_inventory_item_for_ticket(ticket, inventory_items)
                apply_inventory_enrichment_to_ticket(ticket, inventory_item)
                service_inventory_items = inventory_items_for_assignment_group(
                    inventory_items,
                    ticket.assignment_group,
                )
                apply_service_inventory_enrichment_to_ticket(ticket, service_inventory_items)
                assignment_group_key = normalize_match_key(ticket.assignment_group)
                if assignment_group_key is None:
                    out_of_scope_reason = "blank_assignment_group"
                    blank_assignment_group_count += 1
                elif assignment_group_key not in active_assignment_groups:
                    out_of_scope_reason = "assignment_group_not_in_scope_reference"
                    assignment_group_not_in_inventory_count += 1
                else:
                    out_of_scope_reason = ""

                if out_of_scope_reason:
                    db.add(build_out_of_scope_ticket(ticket, out_of_scope_reason))
                    out_of_scope_ticket_count += 1
                    if out_of_scope_reason == "blank_assignment_group":
                        seen_ticket_destinations[
                            ticket.ticket_number
                        ] = "OUT_OF_SCOPE_BLANK_ASSIGNMENT_GROUP"
                    else:
                        seen_ticket_destinations[ticket.ticket_number] = (
                            OUT_OF_SCOPE_SCOPE_REFERENCE_DESTINATION
                        )
                else:
                    db.add(ticket)
                    normalized_ticket_count += 1
                    seen_ticket_destinations[ticket.ticket_number] = "IN_SCOPE"

                processed_ticket_count = normalized_ticket_count + out_of_scope_ticket_count
                if processed_ticket_count % INGESTION_BATCH_SIZE == 0:
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
        if duplicate_ticket_replacement_count > 0:
            warnings.append(
                f"{duplicate_ticket_replacement_count} duplicate ticket ID row(s) were "
                "replaced while normalizing this batch. The latest row in file order was kept."
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
        out_of_scope_ticket_count=out_of_scope_ticket_count,
        blank_assignment_group_count=blank_assignment_group_count,
        assignment_group_not_in_inventory_count=assignment_group_not_in_inventory_count,
        duplicate_skipped_count=0,
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
    ticket_type = normalize_ticket_type_value(ticket_type)
    if mapping:
        return clean_mapping(mapping, ticket_type), MAPPING_SOURCE_REQUEST_BODY

    template_rows = get_mapping_template(db, project_id, ticket_type)
    if template_rows:
        return (
            clean_mapping(mapping_rows_to_field_mapping(template_rows), ticket_type),
            MAPPING_SOURCE_SAVED_TEMPLATE,
        )

    source_columns = [
        source_column.name
        for source_column in infer_source_columns_for_ticket_type(db, project_id, ticket_type)
    ]
    return (
        clean_mapping(suggest_mapping(source_columns, ticket_type), ticket_type),
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
            out_of_scope_ticket_count=result.out_of_scope_ticket_count,
            blank_assignment_group_count=result.blank_assignment_group_count,
            assignment_group_not_in_inventory_count=(
                result.assignment_group_not_in_inventory_count
            ),
            duplicate_skipped_count=result.duplicate_skipped_count,
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
        out_of_scope_ticket_count=sum(
            result.out_of_scope_ticket_count for result in batch_results
        ),
        blank_assignment_group_count=sum(
            result.blank_assignment_group_count for result in batch_results
        ),
        assignment_group_not_in_inventory_count=sum(
            result.assignment_group_not_in_inventory_count for result in batch_results
        ),
        duplicate_skipped_count=sum(result.duplicate_skipped_count for result in batch_results),
        failed_row_count=sum(result.failed_row_count for result in batch_results),
        warnings=all_warnings[:MAX_WARNING_SAMPLES],
        errors=all_errors[:MAX_ERROR_SAMPLES],
    )
