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
from app.models import AssessmentOutOfScopeTicket, Ticket, TicketRawRow, UploadBatch
from app.services.ingestion import INGESTION_BATCH_SIZE
from app.services.mapping import (
    MAX_ERROR_SAMPLES,
    MAX_WARNING_SAMPLES,
    OUT_OF_SCOPE_SCOPE_REFERENCE_DESTINATION,
    ApplyMappingResult,
    MappingError,
    NormalizationErrorSample,
    active_inventory_in_scope_assignment_group_keys,
    apply_inventory_enrichment_to_ticket,
    apply_service_inventory_enrichment_to_ticket,
    build_out_of_scope_ticket,
    build_ticket_from_raw_row,
    inventory_items_for_assignment_group,
    load_active_inventory_items,
    normalize_match_key,
    select_inventory_item_for_ticket,
)
from app.services.upload_lifecycle import (
    mark_upload_batch_normalization_failed,
    mark_upload_batch_normalized,
    mark_upload_batch_normalizing,
)

logger = logging.getLogger(__name__)


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


def model_insert_dict(model: Any, *, out_of_scope: bool = False) -> dict[str, Any]:
    table = AssessmentOutOfScopeTicket.__table__ if out_of_scope else Ticket.__table__
    skip_columns = {"ingested_at", "record_updated_at"}
    row: dict[str, Any] = {"id": uuid4()}
    for column in table.columns:
        if column.name in skip_columns or column.name == "id":
            continue
        row[column.name] = getattr(model, column.name)
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


def bulk_insert_rows(
    db: Session,
    *,
    in_scope_rows: list[dict[str, Any]],
    out_of_scope_rows: list[dict[str, Any]],
    chunk_size: int,
) -> None:
    for row_chunk in chunked(in_scope_rows, chunk_size):
        db.execute(insert(Ticket), row_chunk)
    for row_chunk in chunked(out_of_scope_rows, chunk_size):
        db.execute(insert(AssessmentOutOfScopeTicket), row_chunk)


def apply_mapping_to_batch_v2(
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
    warnings: list[str] = ["Using processing pipeline version: v2."]
    errors: list[NormalizationErrorSample] = []
    failed_row_count = 0
    duplicate_ticket_replacement_count = 0
    deduped: dict[str, tuple[Ticket, str]] = {}

    logger.info(
        "Using processing pipeline version: v2 upload_batch_id=%s project_id=%s",
        upload_batch_id,
        upload_batch.project_id,
    )

    mark_upload_batch_normalizing(upload_batch)
    db.flush()

    with timer.measure("load_reference_data"):
        inventory_items = load_active_inventory_items(db, upload_batch.project_id)
        active_assignment_groups = active_inventory_in_scope_assignment_group_keys(
            db,
            upload_batch.project_id,
        )
    if not active_assignment_groups:
        warnings.append(
            "No active CMDB/Application Inventory in-scope assignment groups were found "
            "for this project; tickets with non-blank assignment groups will be classified "
            "as out of scope.",
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
                inventory_item = select_inventory_item_for_ticket(ticket, inventory_items)
                apply_inventory_enrichment_to_ticket(ticket, inventory_item)
                if inventory_item is None:
                    ticket.sap_non_sap = None
                apply_service_inventory_enrichment_to_ticket(
                    ticket,
                    inventory_items_for_assignment_group(inventory_items, ticket.assignment_group),
                )

                assignment_group_key = normalize_match_key(ticket.assignment_group)
                if assignment_group_key is None:
                    destination = "OUT_OF_SCOPE_BLANK_ASSIGNMENT_GROUP"
                elif assignment_group_key not in active_assignment_groups:
                    destination = OUT_OF_SCOPE_SCOPE_REFERENCE_DESTINATION
                else:
                    destination = "IN_SCOPE"

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
    in_scope_rows: list[dict[str, Any]] = []
    out_of_scope_rows: list[dict[str, Any]] = []
    blank_assignment_group_count = 0
    assignment_group_not_in_inventory_count = 0
    for ticket, destination in deduped.values():
        if destination == "IN_SCOPE":
            in_scope_rows.append(model_insert_dict(ticket))
        else:
            if destination == "OUT_OF_SCOPE_BLANK_ASSIGNMENT_GROUP":
                reason = "blank_assignment_group"
                blank_assignment_group_count += 1
            else:
                reason = "assignment_group_not_in_scope_reference"
                assignment_group_not_in_inventory_count += 1
            out_of_scope_rows.append(
                model_insert_dict(build_out_of_scope_ticket(ticket, reason), out_of_scope=True)
            )

    try:
        if delete_existing and ticket_numbers:
            with timer.measure("bulk_delete_destinations"):
                bulk_delete_destinations(
                    db,
                    project_id=upload_batch.project_id,
                    upload_batch_id=upload_batch_id,
                    ticket_numbers=ticket_numbers,
                    chunk_size=chunk_size,
                )
        with timer.measure("bulk_insert_destinations"):
            bulk_insert_rows(
                db,
                in_scope_rows=in_scope_rows,
                out_of_scope_rows=out_of_scope_rows,
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
        "V2 apply mapping complete upload_batch_id=%s input_rows=%s deduped_rows=%s "
        "in_scope_rows=%s out_of_scope_rows=%s duration_seconds=%.3f rows_per_second=%.2f "
        "stage_timings=%s",
        upload_batch_id,
        total_raw_rows,
        len(deduped),
        len(in_scope_rows),
        len(out_of_scope_rows),
        duration_seconds,
        rows_per_second,
        {key: round(value, 3) for key, value in timer.timings.items()},
    )
    warnings.append(
        "V2 stage timings: "
        + ", ".join(f"{key}={value:.2f}s" for key, value in timer.timings.items())
    )
    warnings.append(f"V2 rows/sec: {rows_per_second:.2f}")
    db.refresh(upload_batch)

    return ApplyMappingResult(
        upload_batch_id=upload_batch.id,
        total_raw_rows=total_raw_rows,
        normalized_ticket_count=len(in_scope_rows),
        out_of_scope_ticket_count=len(out_of_scope_rows),
        blank_assignment_group_count=blank_assignment_group_count,
        assignment_group_not_in_inventory_count=assignment_group_not_in_inventory_count,
        duplicate_skipped_count=0,
        failed_row_count=failed_row_count,
        warnings=warnings[:MAX_WARNING_SAMPLES],
        errors=errors,
        status=upload_batch.status,
    )
