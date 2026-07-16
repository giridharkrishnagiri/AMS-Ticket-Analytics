from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any
from uuid import uuid4

from sqlalchemy import delete, insert, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import (
    ApplicationInventoryItem,
    AssessmentOutOfScopeTicket,
    Ticket,
    TicketRawRow,
    UploadBatch,
)
from app.services.in_scope_assignment_groups import (
    AssignmentGroupScope,
    assignment_group_scope_map,
)
from app.services.ingestion import INGESTION_BATCH_SIZE
from app.services.mapping import (
    CMDB_ARCHITECTURE_TYPE_KEYS,
    CMDB_BUSINESS_CRITICAL_KEYS,
    CMDB_INSTALL_TYPE_KEYS,
    MAX_ERROR_SAMPLES,
    MAX_WARNING_SAMPLES,
    OUT_OF_SCOPE_SCOPE_REFERENCE_DESTINATION,
    ApplyMappingResult,
    MappingError,
    NormalizationErrorSample,
    build_ticket_from_raw_row,
    cmdb_payload_text,
    load_active_inventory_items,
    normalize_match_key,
    text_or_none,
)
from app.services.upload_lifecycle import (
    mark_upload_batch_normalization_failed,
    mark_upload_batch_normalized,
    mark_upload_batch_normalizing,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class InventoryReferenceIndex:
    inventory_by_business_service: dict[str, ApplicationInventoryItem]


@dataclass
class StageTimer:
    timings: dict[str, float] = field(default_factory=dict)

    def measure(self, stage: str):
        return _StageMeasurement(self.timings, stage)


class _StageMeasurement:
    def __init__(self, timings: dict[str, float], stage: str) -> None:
        self.timings = timings
        self.stage = stage
        self.started_at = 0.0

    def __enter__(self) -> None:
        self.started_at = perf_counter()

    def __exit__(self, *_exc: object) -> None:
        self.timings[self.stage] = self.timings.get(self.stage, 0.0) + (
            perf_counter() - self.started_at
        )


def chunked[T](values: list[T], chunk_size: int) -> list[list[T]]:
    return [values[index : index + chunk_size] for index in range(0, len(values), chunk_size)]


def inventory_item_sort_key(item: ApplicationInventoryItem) -> tuple[int, int, object, str]:
    return (
        0 if item.active is True else 1,
        item.source_row_number or 999_999_999,
        item.created_at,
        str(item.id),
    )


def build_inventory_reference_index(
    inventory_items: list[ApplicationInventoryItem],
) -> InventoryReferenceIndex:
    business_service_candidates: dict[str, list[ApplicationInventoryItem]] = {}
    for item in inventory_items:
        business_service_key = normalize_match_key(item.business_service_ci_name)
        if business_service_key is not None:
            business_service_candidates.setdefault(business_service_key, []).append(item)

    return InventoryReferenceIndex(
        inventory_by_business_service={
            key: sorted(candidates, key=inventory_item_sort_key)[0]
            for key, candidates in business_service_candidates.items()
        },
    )


def first_text_value(*values: Any) -> str | None:
    for value in values:
        text = text_or_none(value)
        if text is not None:
            return text
    return None


def ticket_cmdb_match_value(ticket: Ticket) -> str | None:
    return first_text_value(
        ticket.business_service_ci_name,
        ticket.business_service,
        ticket.application,
        ticket.cmdb_ci,
    )


def apply_assignment_group_scope(
    ticket: Ticket,
    scope_by_assignment_group: dict[str, AssignmentGroupScope],
) -> str:
    assignment_group_key = normalize_match_key(ticket.assignment_group)
    if assignment_group_key is None:
        ticket.is_in_scope = False
        return "OUT_OF_SCOPE_BLANK_ASSIGNMENT_GROUP"

    scope = scope_by_assignment_group.get(assignment_group_key)
    if scope is None:
        ticket.is_in_scope = False
        return OUT_OF_SCOPE_SCOPE_REFERENCE_DESTINATION

    ticket.is_in_scope = scope.is_in_scope
    ticket.functional_track = scope.functional_track
    return "IN_SCOPE" if scope.is_in_scope else OUT_OF_SCOPE_SCOPE_REFERENCE_DESTINATION


def enrich_ticket_from_inventory_index(
    ticket: Ticket,
    reference_index: InventoryReferenceIndex,
) -> None:
    match_value = ticket_cmdb_match_value(ticket)
    if ticket.business_service_ci_name is None:
        ticket.business_service_ci_name = match_value

    business_service_key = normalize_match_key(match_value)
    inventory_item = (
        reference_index.inventory_by_business_service.get(business_service_key)
        if business_service_key is not None
        else None
    )
    if inventory_item is None:
        ticket.sap_non_sap = None
        return

    ticket.application_inventory_id = inventory_item.id
    ticket.parent_application_number = inventory_item.application_number_apm
    ticket.parent_application_name = inventory_item.parent_application_name
    ticket.application_owner = inventory_item.application_owner
    ticket.support_lead = inventory_item.support_lead
    ticket.supported_by_vendor = inventory_item.supported_by_vendor
    ticket.service_type = text_or_none(inventory_item.service_type)
    ticket.service_entitlement = text_or_none(inventory_item.service_entitlement)
    ticket.assignment_group_owner = inventory_item.assignment_group_owner
    ticket.sap_non_sap = text_or_none(inventory_item.sap_non_sap)
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
    ticket.install_type = cmdb_payload_text(
        inventory_item.cmdb_payload,
        *CMDB_INSTALL_TYPE_KEYS,
    )


def model_insert_dict(ticket: Ticket) -> dict[str, Any]:
    skip_columns = {"ingested_at", "record_updated_at"}
    row: dict[str, Any] = {"id": uuid4()}
    for column in Ticket.__table__.columns:
        if column.name in skip_columns or column.name == "id":
            continue
        row[column.name] = getattr(ticket, column.name)
    return row


def bulk_delete_destinations(
    db: Session,
    *,
    project_id: object,
    upload_batch_id: object,
    ticket_numbers: list[str],
    chunk_size: int,
) -> None:
    db.execute(delete(Ticket).where(Ticket.upload_batch_id == upload_batch_id))
    db.execute(
        delete(AssessmentOutOfScopeTicket).where(
            AssessmentOutOfScopeTicket.upload_batch_id == upload_batch_id
        )
    )
    for number_chunk in chunked(ticket_numbers, chunk_size):
        db.execute(
            delete(Ticket).where(
                Ticket.project_id == project_id,
                Ticket.ticket_number.in_(number_chunk),
            )
        )
        db.execute(
            delete(AssessmentOutOfScopeTicket).where(
                AssessmentOutOfScopeTicket.project_id == project_id,
                AssessmentOutOfScopeTicket.ticket_number.in_(number_chunk),
            )
        )


def bulk_insert_ticket_rows(
    db: Session,
    *,
    ticket_rows: list[dict[str, Any]],
    chunk_size: int,
) -> None:
    for row_chunk in chunked(ticket_rows, chunk_size):
        db.execute(insert(Ticket), row_chunk)


def apply_mapping_to_batch_single_table(
    db: Session,
    *,
    upload_batch: UploadBatch,
    upload_batch_id: object,
    resolved_mapping: Mapping[str, str],
    delete_existing: bool,
) -> ApplyMappingResult:
    settings = get_settings()
    chunk_size = max(1, settings.ams_processing_bulk_chunk_size)
    timer = StageTimer()
    started_at = perf_counter()
    warnings: list[str] = ["Using processing pipeline version: single-table-v2."]
    errors: list[NormalizationErrorSample] = []
    failed_row_count = 0
    duplicate_ticket_replacement_count = 0
    deduped: dict[str, tuple[Ticket, str]] = {}

    logger.info(
        "Using single-table ticket mapping upload_batch_id=%s project_id=%s",
        upload_batch_id,
        upload_batch.project_id,
    )

    mark_upload_batch_normalizing(upload_batch)
    db.flush()

    with timer.measure("load_reference_data"):
        inventory_items = load_active_inventory_items(db, upload_batch.project_id)
        scope_by_assignment_group = assignment_group_scope_map(db, upload_batch.project_id)
    with timer.measure("build_reference_indexes"):
        reference_index = build_inventory_reference_index(inventory_items)
    if not scope_by_assignment_group:
        warnings.append(
            "No assignment group scope reference rows were found for this project; tickets "
            "will be classified as out of scope until the scope file is imported.",
        )

    raw_row_statement = (
        select(TicketRawRow)
        .where(TicketRawRow.upload_batch_id == upload_batch_id)
        .order_by(TicketRawRow.uploaded_file_id.asc(), TicketRawRow.row_number.asc())
    )

    total_raw_rows = 0
    with timer.measure("normalize_scope_and_enrich_rows"):
        for raw_row in db.scalars(raw_row_statement).yield_per(INGESTION_BATCH_SIZE):
            total_raw_rows += 1
            try:
                ticket = build_ticket_from_raw_row(raw_row, upload_batch, resolved_mapping)
                destination = apply_assignment_group_scope(ticket, scope_by_assignment_group)
                enrich_ticket_from_inventory_index(ticket, reference_index)

                if ticket.ticket_number in deduped:
                    duplicate_ticket_replacement_count += 1
                deduped[ticket.ticket_number] = (ticket, destination)
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

    ticket_numbers = list(deduped)
    ticket_rows: list[dict[str, Any]] = []
    blank_assignment_group_count = 0
    assignment_group_not_in_inventory_count = 0
    in_scope_count = 0
    out_of_scope_count = 0

    for ticket, destination in deduped.values():
        if ticket.is_in_scope:
            in_scope_count += 1
        else:
            out_of_scope_count += 1
            if destination == "OUT_OF_SCOPE_BLANK_ASSIGNMENT_GROUP":
                blank_assignment_group_count += 1
            else:
                assignment_group_not_in_inventory_count += 1
        ticket_rows.append(model_insert_dict(ticket))

    try:
        if delete_existing:
            with timer.measure("bulk_delete_destinations"):
                bulk_delete_destinations(
                    db,
                    project_id=upload_batch.project_id,
                    upload_batch_id=upload_batch_id,
                    ticket_numbers=ticket_numbers,
                    chunk_size=chunk_size,
                )
        with timer.measure("bulk_insert_destinations"):
            bulk_insert_ticket_rows(
                db,
                ticket_rows=ticket_rows,
                chunk_size=chunk_size,
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
    except Exception:
        db.rollback()
        failed_batch = db.get(UploadBatch, upload_batch_id)
        if failed_batch is not None:
            mark_upload_batch_normalization_failed(failed_batch)
            db.commit()
        raise

    duration_seconds = perf_counter() - started_at
    rows_per_second = len(deduped) / duration_seconds if duration_seconds else 0.0
    logger.info(
        "Single-table mapping complete upload_batch_id=%s input_rows=%s deduped_rows=%s "
        "in_scope_rows=%s out_of_scope_rows=%s duration_seconds=%.3f rows_per_second=%.2f "
        "stage_timings=%s",
        upload_batch_id,
        total_raw_rows,
        len(deduped),
        in_scope_count,
        out_of_scope_count,
        duration_seconds,
        rows_per_second,
        {key: round(value, 3) for key, value in timer.timings.items()},
    )
    warnings.append(
        "Single-table stage timings: "
        + ", ".join(f"{key}={value:.2f}s" for key, value in timer.timings.items())
    )
    warnings.append(f"Single-table rows/sec: {rows_per_second:.2f}")
    db.refresh(upload_batch)

    return ApplyMappingResult(
        upload_batch_id=upload_batch.id,
        total_raw_rows=total_raw_rows,
        normalized_ticket_count=in_scope_count,
        out_of_scope_ticket_count=out_of_scope_count,
        blank_assignment_group_count=blank_assignment_group_count,
        assignment_group_not_in_inventory_count=assignment_group_not_in_inventory_count,
        duplicate_skipped_count=0,
        failed_row_count=failed_row_count,
        warnings=warnings[:MAX_WARNING_SAMPLES],
        errors=errors,
        status=upload_batch.status,
    )
