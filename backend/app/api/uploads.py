from __future__ import annotations

import re
import shutil
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import (
    AssessmentChangeRecord,
    AssessmentOutOfScopeTicket,
    AssessmentProblemRecord,
    IngestionJob,
    Project,
    Ticket,
    TicketRawRow,
    UploadBatch,
    UploadedFile,
)
from app.schemas.upload import (
    IngestionJobResponse,
    RawRowsPreviewResponse,
    UploadBatchActionRequest,
    UploadBatchApplyMappingFileResponse,
    UploadBatchApplyMappingMultipleResponse,
    UploadBatchApplyMappingRequest,
    UploadBatchApplyMappingTotalsResponse,
    UploadBatchIngestMultipleResponse,
    UploadBatchIngestResultResponse,
    UploadBatchIngestTotalsResponse,
    UploadBatchNormalizeMultipleResponse,
    UploadBatchNormalizeRequest,
    UploadBatchNormalizeResultResponse,
    UploadBatchNormalizeTotalsResponse,
    UploadBatchResponse,
    UploadCreateResponse,
    UploadedFileResponse,
    UploadMultipleFileResponse,
    UploadMultipleResponse,
    UploadMultipleTotalsResponse,
    ValidationSummaryResponse,
)
from app.services.dashboard_filter_cache import mark_filter_caches_stale
from app.services.dashboard_filter_facts import refresh_dashboard_filter_facts
from app.services.ingestion import (
    IngestionError,
    IngestionJobAlreadyRunningError,
    UnsupportedIngestionFileTypeError,
    build_validation_summary,
    ingest_uploaded_file,
    recalculate_upload_batch_status,
)
from app.services.mapping import (
    MappingError,
    apply_mapping_to_batch,
    resolve_mapping_for_project_ticket_type,
    save_mapping_template,
)
from app.services.upload_lifecycle import (
    BATCH_STATUS_ARCHIVED,
    BATCH_STATUS_DELETED,
    BATCH_STATUS_NORMALIZATION_FAILED,
    BATCH_STATUS_NORMALIZED,
    BATCH_STATUS_UPLOADED,
    count_normalized_tickets,
    mark_upload_batch_normalization_failed,
    sync_legacy_normalized_status,
    utc_now,
)
from app.services.upload_storage import is_allowed_upload_filename, save_upload_file

router = APIRouter(prefix="/uploads", tags=["uploads"])
DbSession = Annotated[Session, Depends(get_db)]
MONTH_KEY_PATTERN = re.compile(r"^\d{4}-\d{2}$")
PERIOD_TYPE_MONTHLY = "MONTHLY"
PERIOD_TYPE_SNAPSHOT = "SNAPSHOT"
BATCH_VIEW_ACTIVE = "active"
BATCH_VIEW_HISTORY = "history"
BATCH_VIEW_ALL = "all"
APPLY_STATUS_APPLIED = "APPLIED"
APPLY_STATUS_ALREADY_APPLIED = "SKIPPED_ALREADY_APPLIED"
APPLY_STATUS_PARTIAL_OUTPUT = "FAILED_PARTIAL_OUTPUT"
APPLY_STATUS_FAILED = "FAILED"
GENERIC_FILTER_FACT_TICKET_TYPES = {"INCIDENT", "SERVICE_CATALOG_TASK"}


def get_batch_ticket_type(db: Session, upload_batch_id: UUID) -> str | None:
    ticket_type = db.scalar(
        select(UploadedFile.ticket_type)
        .where(UploadedFile.upload_batch_id == upload_batch_id)
        .order_by(UploadedFile.created_at.asc())
        .limit(1)
    )
    return str(ticket_type) if ticket_type else None


def get_count(db: Session, statement) -> int:
    return int(db.scalar(statement) or 0)


def batch_output_counts(db: Session, upload_batch_id: UUID) -> dict[str, int]:
    upload_batch = db.get(UploadBatch, upload_batch_id)
    ticket_type = (get_batch_ticket_type(db, upload_batch_id) or "").strip().upper()
    raw_rows = get_count(
        db,
        select(func.count(TicketRawRow.id)).where(
            TicketRawRow.upload_batch_id == upload_batch_id
        ),
    )
    if ticket_type in {"PROBLEM", "CHANGE"}:
        model = AssessmentProblemRecord if ticket_type == "PROBLEM" else AssessmentChangeRecord
        normalized_rows = get_count(
            db,
            select(func.count(model.id)).where(model.upload_batch_id == upload_batch_id),
        )
        unmatched_rows = get_count(
            db,
            select(func.count(model.id)).where(
                model.upload_batch_id == upload_batch_id,
                model.application_inventory_match_status == "unmatched",
            ),
        )
        output_rows = normalized_rows
        effective_output_rows = (
            raw_rows
            if upload_batch is not None and upload_batch.status == BATCH_STATUS_NORMALIZED
            else output_rows
        )
        return {
            "raw_rows": raw_rows,
            "in_scope_rows": normalized_rows,
            "out_of_scope_rows": 0,
            "blank_assignment_group_rows": 0,
            "assignment_group_not_in_inventory_rows": unmatched_rows,
            "duplicate_skipped_rows": max(raw_rows - output_rows, 0)
            if upload_batch is not None and upload_batch.status == BATCH_STATUS_NORMALIZED
            else 0,
            "failed_rows": max(raw_rows - effective_output_rows, 0),
            "output_rows": effective_output_rows,
        }

    in_scope_rows = get_count(
        db,
        select(func.count(Ticket.id)).where(Ticket.upload_batch_id == upload_batch_id),
    )
    out_of_scope_rows = get_count(
        db,
        select(func.count(AssessmentOutOfScopeTicket.id)).where(
            AssessmentOutOfScopeTicket.upload_batch_id == upload_batch_id
        ),
    )
    blank_assignment_group_rows = get_count(
        db,
        select(func.count(AssessmentOutOfScopeTicket.id)).where(
            AssessmentOutOfScopeTicket.upload_batch_id == upload_batch_id,
            AssessmentOutOfScopeTicket.out_of_scope_reason == "blank_assignment_group",
        ),
    )
    assignment_group_not_in_inventory_rows = get_count(
        db,
        select(func.count(AssessmentOutOfScopeTicket.id)).where(
            AssessmentOutOfScopeTicket.upload_batch_id == upload_batch_id,
            AssessmentOutOfScopeTicket.out_of_scope_reason
            == "assignment_group_not_in_application_inventory",
        ),
    )
    output_rows = in_scope_rows + out_of_scope_rows
    return {
        "raw_rows": raw_rows,
        "in_scope_rows": in_scope_rows,
        "out_of_scope_rows": out_of_scope_rows,
        "blank_assignment_group_rows": blank_assignment_group_rows,
        "assignment_group_not_in_inventory_rows": assignment_group_not_in_inventory_rows,
        "duplicate_skipped_rows": 0,
        "failed_rows": max(raw_rows - output_rows, 0),
        "output_rows": output_rows,
    }


def build_apply_mapping_totals(
    files: list[UploadBatchApplyMappingFileResponse],
) -> UploadBatchApplyMappingTotalsResponse:
    return UploadBatchApplyMappingTotalsResponse(
        total_files=len(files),
        applied=sum(1 for file in files if file.status == APPLY_STATUS_APPLIED),
        skipped=sum(1 for file in files if file.status == APPLY_STATUS_ALREADY_APPLIED),
        failed=sum(
            1
            for file in files
            if file.status in {APPLY_STATUS_FAILED, APPLY_STATUS_PARTIAL_OUTPUT}
        ),
        input_rows=sum(file.input_rows for file in files),
        in_scope_rows=sum(file.in_scope_rows for file in files),
        out_of_scope_rows=sum(file.out_of_scope_rows for file in files),
        blank_assignment_group_rows=sum(file.blank_assignment_group_rows for file in files),
        assignment_group_not_in_inventory_rows=sum(
            file.assignment_group_not_in_inventory_rows for file in files
        ),
        duplicate_skipped_rows=sum(file.duplicate_skipped_rows for file in files),
        failed_rows=sum(file.failed_rows for file in files),
    )


def build_upload_batch_response(db: Session, upload_batch: UploadBatch) -> UploadBatchResponse:
    normalized_ticket_count = sync_legacy_normalized_status(db, upload_batch)
    uploaded_file_count = get_count(
        db,
        select(func.count(UploadedFile.id)).where(
            UploadedFile.upload_batch_id == upload_batch.id
        ),
    )
    raw_row_count = get_count(
        db,
        select(func.count(TicketRawRow.id)).where(
            TicketRawRow.upload_batch_id == upload_batch.id
        ),
    )

    return UploadBatchResponse(
        id=upload_batch.id,
        project_id=upload_batch.project_id,
        month_key=upload_batch.month_key,
        period_type=upload_batch.period_type,
        snapshot_date=upload_batch.snapshot_date,
        batch_name=upload_batch.batch_name,
        source_system=upload_batch.source_system,
        status=upload_batch.status,
        uploaded_by=upload_batch.uploaded_by,
        file_count=upload_batch.file_count,
        total_size_bytes=upload_batch.total_size_bytes,
        description=upload_batch.description,
        ticket_type=get_batch_ticket_type(db, upload_batch.id),
        uploaded_file_count=uploaded_file_count,
        raw_row_count=raw_row_count,
        normalized_ticket_count=normalized_ticket_count,
        normalized_at=upload_batch.normalized_at,
        archived_at=upload_batch.archived_at,
        deleted_at=upload_batch.deleted_at,
        created_at=upload_batch.created_at,
        updated_at=upload_batch.updated_at,
    )


def batch_is_deleted(upload_batch: UploadBatch) -> bool:
    return upload_batch.status == BATCH_STATUS_DELETED or upload_batch.deleted_at is not None


def batch_matches_view(upload_batch: UploadBatch, view: str) -> bool:
    if batch_is_deleted(upload_batch):
        return False
    if view == BATCH_VIEW_HISTORY:
        return upload_batch.status in {BATCH_STATUS_NORMALIZED, BATCH_STATUS_ARCHIVED}
    if view == BATCH_VIEW_ACTIVE:
        return upload_batch.status not in {BATCH_STATUS_NORMALIZED, BATCH_STATUS_ARCHIVED}
    return True


def get_existing_batch_or_404(db: Session, upload_batch_id: UUID) -> UploadBatch:
    upload_batch = db.get(UploadBatch, upload_batch_id)
    if upload_batch is None or batch_is_deleted(upload_batch):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Upload batch {upload_batch_id} was not found.",
        )
    return upload_batch


def validate_period_metadata(
    period_type: str,
    month_key: str | None,
    snapshot_date: date | None,
) -> tuple[str, str | None, date | None]:
    normalized_period_type = period_type.strip().upper()
    if normalized_period_type not in {PERIOD_TYPE_MONTHLY, PERIOD_TYPE_SNAPSHOT}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Upload period type must be MONTHLY or SNAPSHOT.",
        )

    cleaned_month_key = (month_key or "").strip() or None
    resolved_snapshot_date: date | None = None
    if normalized_period_type == PERIOD_TYPE_MONTHLY:
        if not cleaned_month_key or not MONTH_KEY_PATTERN.fullmatch(cleaned_month_key):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Month-Year is required for monthly uploads.",
            )
    else:
        cleaned_month_key = None
        resolved_snapshot_date = snapshot_date or datetime.now(UTC).date()

    return normalized_period_type, cleaned_month_key, resolved_snapshot_date


def unique_upload_batch_name(
    db: Session,
    project_id: UUID,
    month_key: str | None,
    base_batch_name: str,
) -> str:
    candidate = base_batch_name[:255]
    suffix = 2
    while db.scalar(
        select(UploadBatch.id)
        .where(
            UploadBatch.project_id == project_id,
            UploadBatch.month_key == month_key,
            UploadBatch.batch_name == candidate,
            UploadBatch.deleted_at.is_(None),
            UploadBatch.status != BATCH_STATUS_DELETED,
        )
        .limit(1)
    ):
        suffix_text = f" ({suffix})"
        candidate = f"{base_batch_name[: 255 - len(suffix_text)]}{suffix_text}"
        suffix += 1
    return candidate


def build_per_file_batch_name(batch_name: str, filename: str, file_count: int) -> str:
    cleaned_batch_name = batch_name.strip()
    if file_count == 1:
        return cleaned_batch_name

    file_stem = Path(filename).stem.strip() or "file"
    return f"{cleaned_batch_name} - {file_stem}"


def duplicate_upload_warnings(
    db: Session,
    *,
    project_id: UUID,
    ticket_type: str,
    period_type: str,
    month_key: str | None,
    snapshot_date: date | None,
    filename: str,
    size_bytes: int,
) -> list[str]:
    month_filter = (
        UploadBatch.month_key.is_(None)
        if month_key is None
        else UploadBatch.month_key == month_key
    )
    snapshot_filter = (
        UploadBatch.snapshot_date.is_(None)
        if snapshot_date is None
        else UploadBatch.snapshot_date == snapshot_date
    )
    statement = (
        select(UploadedFile.id)
        .join(UploadBatch, UploadBatch.id == UploadedFile.upload_batch_id)
        .where(
            UploadedFile.project_id == project_id,
            UploadedFile.ticket_type == ticket_type,
            UploadedFile.original_filename == filename,
            UploadedFile.size_bytes == size_bytes,
            UploadBatch.period_type == period_type,
            month_filter,
            snapshot_filter,
            UploadBatch.deleted_at.is_(None),
            UploadBatch.status != BATCH_STATUS_DELETED,
        )
        .limit(1)
    )
    if db.scalar(statement):
        return [
            "A file with the same name and size already exists for this project, "
            "ticket type, and period. Upload was allowed, but verify that this is "
            "not an accidental duplicate."
        ]
    return []


async def create_single_file_upload_batch(
    *,
    db: Session,
    project: Project,
    ticket_type: str,
    period_type: str,
    month_key: str | None,
    snapshot_date: date | None,
    batch_name: str,
    upload_file: UploadFile,
    source_system: str | None,
    uploaded_by: str | None,
    description: str | None,
) -> tuple[UploadBatch, UploadedFile, IngestionJob, list[str]]:
    upload_batch = UploadBatch(
        project_id=project.id,
        month_key=month_key,
        period_type=period_type,
        snapshot_date=snapshot_date,
        batch_name=batch_name,
        source_system=source_system,
        status=BATCH_STATUS_UPLOADED,
        uploaded_by=uploaded_by,
        file_count=0,
        total_size_bytes=0,
        description=description,
    )
    db.add(upload_batch)
    db.flush()

    saved_file = await save_upload_file(upload_batch.id, upload_file)
    warnings = duplicate_upload_warnings(
        db,
        project_id=project.id,
        ticket_type=ticket_type,
        period_type=period_type,
        month_key=month_key,
        snapshot_date=snapshot_date,
        filename=saved_file.original_filename,
        size_bytes=saved_file.size_bytes,
    )

    uploaded_file = UploadedFile(
        upload_batch_id=upload_batch.id,
        project_id=project.id,
        ticket_type=ticket_type,
        original_filename=saved_file.original_filename,
        saved_filename=saved_file.saved_filename,
        storage_path=str(saved_file.storage_path),
        content_type=saved_file.content_type,
        size_bytes=saved_file.size_bytes,
        checksum_sha256=saved_file.checksum_sha256,
        status="STORED",
    )
    db.add(uploaded_file)
    db.flush()

    ingestion_job = IngestionJob(
        upload_batch_id=upload_batch.id,
        uploaded_file_id=uploaded_file.id,
        job_type="FILE_INGESTION",
        status="PENDING",
        rows_total=0,
        rows_processed=0,
    )
    db.add(ingestion_job)

    upload_batch.file_count = 1
    upload_batch.total_size_bytes = saved_file.size_bytes
    return upload_batch, uploaded_file, ingestion_job, warnings


def batch_file_label(db: Session, upload_batch_id: UUID) -> str | None:
    filenames = list(
        db.scalars(
            select(UploadedFile.original_filename)
            .where(UploadedFile.upload_batch_id == upload_batch_id)
            .order_by(UploadedFile.created_at.asc())
        )
    )
    return ", ".join(filenames) if filenames else None


@router.post(
    "",
    response_model=UploadCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_ticket_files(
    project_id: Annotated[UUID, Form(...)],
    ticket_type: Annotated[str, Form(min_length=1, max_length=40)],
    files: Annotated[list[UploadFile], File(...)],
    db: DbSession,
    period_type: Annotated[str, Form(max_length=40)] = PERIOD_TYPE_MONTHLY,
    month_key: Annotated[str | None, Form(max_length=7)] = None,
    snapshot_date: Annotated[date | None, Form()] = None,
    batch_name: Annotated[str | None, Form(max_length=255)] = None,
    source_system: Annotated[str | None, Form(max_length=120)] = None,
    uploaded_by: Annotated[str | None, Form(max_length=255)] = None,
    description: Annotated[str | None, Form()] = None,
) -> UploadCreateResponse:
    if not files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one CSV or XLSX file is required.",
        )

    normalized_period_type = period_type.strip().upper()
    if normalized_period_type not in {PERIOD_TYPE_MONTHLY, PERIOD_TYPE_SNAPSHOT}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Upload period type must be MONTHLY or SNAPSHOT.",
        )

    cleaned_batch_name = (batch_name or "").strip()
    if not cleaned_batch_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Batch name is required.",
        )

    cleaned_month_key = (month_key or "").strip() or None
    resolved_snapshot_date: date | None = None
    if normalized_period_type == PERIOD_TYPE_MONTHLY:
        if not cleaned_month_key or not MONTH_KEY_PATTERN.fullmatch(cleaned_month_key):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Month-Year is required for monthly uploads.",
            )
    else:
        cleaned_month_key = None
        resolved_snapshot_date = snapshot_date or datetime.now(UTC).date()

    invalid_filenames = [
        upload_file.filename or "<unnamed>"
        for upload_file in files
        if not is_allowed_upload_filename(upload_file.filename)
    ]
    if invalid_filenames:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": "Only .csv and .xlsx files are supported.",
                "invalid_files": invalid_filenames,
            },
        )

    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project {project_id} was not found.",
        )

    upload_batch = UploadBatch(
        project_id=project.id,
        month_key=cleaned_month_key,
        period_type=normalized_period_type,
        snapshot_date=resolved_snapshot_date,
        batch_name=cleaned_batch_name,
        source_system=source_system,
        status=BATCH_STATUS_UPLOADED,
        uploaded_by=uploaded_by,
        file_count=0,
        total_size_bytes=0,
        description=description,
    )
    db.add(upload_batch)
    db.flush()

    saved_paths = []
    uploaded_files: list[UploadedFile] = []
    ingestion_jobs: list[IngestionJob] = []

    try:
        for upload_file in files:
            saved_file = await save_upload_file(upload_batch.id, upload_file)
            saved_paths.append(saved_file.storage_path)

            uploaded_file = UploadedFile(
                upload_batch_id=upload_batch.id,
                project_id=project.id,
                ticket_type=ticket_type.strip().upper(),
                original_filename=saved_file.original_filename,
                saved_filename=saved_file.saved_filename,
                storage_path=str(saved_file.storage_path),
                content_type=saved_file.content_type,
                size_bytes=saved_file.size_bytes,
                checksum_sha256=saved_file.checksum_sha256,
                status="STORED",
            )
            db.add(uploaded_file)
            db.flush()

            ingestion_job = IngestionJob(
                upload_batch_id=upload_batch.id,
                uploaded_file_id=uploaded_file.id,
                job_type="FILE_INGESTION",
                status="PENDING",
                rows_total=0,
                rows_processed=0,
            )
            db.add(ingestion_job)

            uploaded_files.append(uploaded_file)
            ingestion_jobs.append(ingestion_job)
            upload_batch.file_count += 1
            upload_batch.total_size_bytes += saved_file.size_bytes

        db.commit()
    except OSError as exc:
        db.rollback()
        for saved_path in saved_paths:
            saved_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"File storage failed: {exc}",
        ) from exc
    except SQLAlchemyError as exc:
        db.rollback()
        for saved_path in saved_paths:
            saved_path.unlink(missing_ok=True)
        batch_dir = saved_paths[0].parent if saved_paths else None
        if batch_dir and batch_dir.exists():
            shutil.rmtree(batch_dir, ignore_errors=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Upload metadata could not be saved.",
        ) from exc

    db.refresh(upload_batch)
    for uploaded_file in uploaded_files:
        db.refresh(uploaded_file)
    for ingestion_job in ingestion_jobs:
        db.refresh(ingestion_job)

    return UploadCreateResponse(
        batch=build_upload_batch_response(db, upload_batch),
        files=uploaded_files,
        ingestion_jobs=ingestion_jobs,
    )


@router.post(
    "/upload-multiple",
    response_model=UploadMultipleResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_ticket_files_as_separate_batches(
    project_id: Annotated[UUID, Form(...)],
    ticket_type: Annotated[str, Form(min_length=1, max_length=40)],
    files: Annotated[list[UploadFile], File(...)],
    db: DbSession,
    period_type: Annotated[str, Form(max_length=40)] = PERIOD_TYPE_MONTHLY,
    month_key: Annotated[str | None, Form(max_length=7)] = None,
    snapshot_date: Annotated[date | None, Form()] = None,
    batch_name: Annotated[str | None, Form(max_length=255)] = None,
    source_system: Annotated[str | None, Form(max_length=120)] = None,
    uploaded_by: Annotated[str | None, Form(max_length=255)] = None,
    description: Annotated[str | None, Form()] = None,
) -> UploadMultipleResponse:
    if not files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one CSV or XLSX file is required.",
        )

    normalized_period_type, cleaned_month_key, resolved_snapshot_date = validate_period_metadata(
        period_type,
        month_key,
        snapshot_date,
    )
    cleaned_batch_name = (batch_name or "").strip()
    if not cleaned_batch_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Batch name is required.",
        )

    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project {project_id} was not found.",
        )

    normalized_ticket_type = ticket_type.strip().upper()
    results: list[UploadMultipleFileResponse] = []

    for upload_index, upload_file in enumerate(files, start=1):
        original_filename = upload_file.filename or f"upload-{upload_index}"
        if not is_allowed_upload_filename(upload_file.filename):
            results.append(
                UploadMultipleFileResponse(
                    filename=original_filename,
                    status="FAILED_UPLOAD",
                    message="Only .csv and .xlsx files are supported.",
                )
            )
            await upload_file.close()
            continue

        file_batch_name = unique_upload_batch_name(
            db,
            project.id,
            cleaned_month_key,
            build_per_file_batch_name(cleaned_batch_name, original_filename, len(files)),
        )

        saved_path: Path | None = None
        try:
            upload_batch, uploaded_file, ingestion_job, warnings = (
                await create_single_file_upload_batch(
                    db=db,
                    project=project,
                    ticket_type=normalized_ticket_type,
                    period_type=normalized_period_type,
                    month_key=cleaned_month_key,
                    snapshot_date=resolved_snapshot_date,
                    batch_name=file_batch_name,
                    upload_file=upload_file,
                    source_system=source_system,
                    uploaded_by=uploaded_by,
                    description=description,
                )
            )
            saved_path = Path(uploaded_file.storage_path)
            db.commit()
            results.append(
                UploadMultipleFileResponse(
                    filename=uploaded_file.original_filename,
                    size_bytes=uploaded_file.size_bytes,
                    upload_batch_id=upload_batch.id,
                    uploaded_file_id=uploaded_file.id,
                    ingestion_job_id=ingestion_job.id,
                    status="UPLOADED",
                    warnings=warnings,
                )
            )
        except (OSError, SQLAlchemyError) as exc:
            db.rollback()
            if saved_path is not None:
                saved_path.unlink(missing_ok=True)
            results.append(
                UploadMultipleFileResponse(
                    filename=original_filename,
                    status="FAILED_UPLOAD",
                    message=f"Upload failed: {exc}",
                )
            )
        finally:
            await upload_file.close()

    files_uploaded = sum(1 for result in results if result.status == "UPLOADED")
    files_failed = len(results) - files_uploaded
    return UploadMultipleResponse(
        project_id=project.id,
        ticket_type=normalized_ticket_type,
        period_type=normalized_period_type,
        files=results,
        totals=UploadMultipleTotalsResponse(
            files_selected=len(files),
            files_uploaded=files_uploaded,
            files_failed=files_failed,
        ),
    )


@router.post(
    "/batches/ingest-multiple",
    response_model=UploadBatchIngestMultipleResponse,
)
def ingest_upload_batches(
    request: UploadBatchActionRequest,
    db: DbSession,
) -> UploadBatchIngestMultipleResponse:
    project = db.get(Project, request.project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project {request.project_id} was not found.",
        )

    results: list[UploadBatchIngestResultResponse] = []
    seen_batch_ids: set[UUID] = set()
    for upload_batch_id in request.upload_batch_ids:
        if upload_batch_id in seen_batch_ids:
            continue
        seen_batch_ids.add(upload_batch_id)

        upload_batch = db.get(UploadBatch, upload_batch_id)
        if (
            upload_batch is None
            or upload_batch.project_id != request.project_id
            or batch_is_deleted(upload_batch)
        ):
            results.append(
                UploadBatchIngestResultResponse(
                    upload_batch_id=upload_batch_id,
                    batch_name="Unknown batch",
                    status="FAILED",
                    raw_rows_inserted=0,
                    error="Upload batch was not found for the selected project.",
                )
            )
            continue

        uploaded_files = list(
            db.scalars(
                select(UploadedFile)
                .where(UploadedFile.upload_batch_id == upload_batch_id)
                .order_by(UploadedFile.created_at.asc())
            )
        )
        batch_errors: list[str] = []
        for uploaded_file in uploaded_files:
            if uploaded_file.status == "INGESTED":
                continue
            try:
                ingest_uploaded_file(db, uploaded_file.id)
            except Exception as exc:
                batch_errors.append(f"{uploaded_file.original_filename}: {exc}")

        recalculate_upload_batch_status(db, upload_batch_id)
        db.commit()
        db.refresh(upload_batch)
        raw_rows_inserted = get_count(
            db,
            select(func.count(TicketRawRow.id)).where(
                TicketRawRow.upload_batch_id == upload_batch_id
            ),
        )
        results.append(
            UploadBatchIngestResultResponse(
                upload_batch_id=upload_batch.id,
                batch_name=upload_batch.batch_name,
                filename=batch_file_label(db, upload_batch.id),
                status="FAILED" if batch_errors else upload_batch.status,
                raw_rows_inserted=raw_rows_inserted,
                error="; ".join(batch_errors[:5]) if batch_errors else None,
            )
        )

    batches_ingested = sum(
        1 for result in results if result.status in {"INGESTED", BATCH_STATUS_NORMALIZED}
    )
    batches_failed = sum(1 for result in results if result.status == "FAILED")
    return UploadBatchIngestMultipleResponse(
        project_id=request.project_id,
        batches=results,
        totals=UploadBatchIngestTotalsResponse(
            batches_requested=len(seen_batch_ids),
            batches_ingested=batches_ingested,
            batches_failed=batches_failed,
            raw_rows_inserted=sum(result.raw_rows_inserted for result in results),
        ),
    )


@router.post(
    "/batches/normalize-multiple",
    response_model=UploadBatchNormalizeMultipleResponse,
)
def normalize_upload_batches(
    request: UploadBatchNormalizeRequest,
    db: DbSession,
) -> UploadBatchNormalizeMultipleResponse:
    project = db.get(Project, request.project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project {request.project_id} was not found.",
        )

    normalized_ticket_type = request.ticket_type.strip().upper()
    results: list[UploadBatchNormalizeResultResponse] = []
    seen_batch_ids: set[UUID] = set()

    for upload_batch_id in request.upload_batch_ids:
        if upload_batch_id in seen_batch_ids:
            continue
        seen_batch_ids.add(upload_batch_id)

        upload_batch = db.get(UploadBatch, upload_batch_id)
        if (
            upload_batch is None
            or upload_batch.project_id != request.project_id
            or batch_is_deleted(upload_batch)
        ):
            results.append(
                UploadBatchNormalizeResultResponse(
                    upload_batch_id=upload_batch_id,
                    batch_name="Unknown batch",
                    status=BATCH_STATUS_NORMALIZATION_FAILED,
                    raw_rows=0,
                    in_scope_inserted=0,
                    out_of_scope_inserted=0,
                    failed_rows=0,
                    errors=["Upload batch was not found for the selected project."],
                )
            )
            continue

        batch_ticket_type = get_batch_ticket_type(db, upload_batch_id)
        if batch_ticket_type and batch_ticket_type != normalized_ticket_type:
            results.append(
                UploadBatchNormalizeResultResponse(
                    upload_batch_id=upload_batch.id,
                    batch_name=upload_batch.batch_name,
                    filename=batch_file_label(db, upload_batch.id),
                    status=BATCH_STATUS_NORMALIZATION_FAILED,
                    raw_rows=0,
                    in_scope_inserted=0,
                    out_of_scope_inserted=0,
                    failed_rows=0,
                    errors=[
                        f"Batch ticket type is {batch_ticket_type}, not {normalized_ticket_type}."
                    ],
                )
            )
            continue

        try:
            result = apply_mapping_to_batch(
                db=db,
                upload_batch_id=upload_batch.id,
                mapping=None,
                delete_existing=request.delete_existing,
            )
            results.append(
                UploadBatchNormalizeResultResponse(
                    upload_batch_id=upload_batch.id,
                    batch_name=upload_batch.batch_name,
                    filename=batch_file_label(db, upload_batch.id),
                    status=result.status,
                    raw_rows=result.total_raw_rows,
                    in_scope_inserted=result.normalized_ticket_count,
                    out_of_scope_inserted=result.out_of_scope_ticket_count,
                    assignment_group_not_in_inventory_rows=(
                        result.assignment_group_not_in_inventory_count
                    ),
                    duplicate_skipped_rows=result.duplicate_skipped_count,
                    failed_rows=result.failed_row_count,
                    warnings=result.warnings,
                    errors=[
                        f"Row {error.row_number}: {error.message}"
                        for error in result.errors[:10]
                    ],
                )
            )
        except (FileNotFoundError, MappingError, SQLAlchemyError) as exc:
            failed_batch = db.get(UploadBatch, upload_batch.id)
            if failed_batch is not None:
                mark_upload_batch_normalization_failed(failed_batch)
                db.commit()
            results.append(
                UploadBatchNormalizeResultResponse(
                    upload_batch_id=upload_batch.id,
                    batch_name=upload_batch.batch_name,
                    filename=batch_file_label(db, upload_batch.id),
                    status=BATCH_STATUS_NORMALIZATION_FAILED,
                    raw_rows=get_count(
                        db,
                        select(func.count(TicketRawRow.id)).where(
                            TicketRawRow.upload_batch_id == upload_batch.id
                        ),
                    ),
                    in_scope_inserted=0,
                    out_of_scope_inserted=0,
                    failed_rows=0,
                    errors=[str(exc)],
                )
            )

    if normalized_ticket_type in GENERIC_FILTER_FACT_TICKET_TYPES and any(
        result.status == BATCH_STATUS_NORMALIZED for result in results
    ):
        refresh_dashboard_filter_facts(db, request.project_id)
        mark_filter_caches_stale(db, request.project_id)
        db.commit()

    return UploadBatchNormalizeMultipleResponse(
        project_id=request.project_id,
        ticket_type=normalized_ticket_type,
        batches=results,
        totals=UploadBatchNormalizeTotalsResponse(
            raw_rows=sum(result.raw_rows for result in results),
            in_scope_inserted=sum(result.in_scope_inserted for result in results),
            out_of_scope_inserted=sum(result.out_of_scope_inserted for result in results),
            assignment_group_not_in_inventory_rows=sum(
                result.assignment_group_not_in_inventory_rows for result in results
            ),
            duplicate_skipped_rows=sum(result.duplicate_skipped_rows for result in results),
            failed_batches=sum(
                1
                for result in results
                if result.status == BATCH_STATUS_NORMALIZATION_FAILED or result.failed_rows > 0
            ),
        ),
    )


@router.post(
    "/batches/apply-mapping-multiple",
    response_model=UploadBatchApplyMappingMultipleResponse,
)
def apply_mapping_to_upload_batches(
    request: UploadBatchApplyMappingRequest,
    db: DbSession,
) -> UploadBatchApplyMappingMultipleResponse:
    project = db.get(Project, request.project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project {request.project_id} was not found.",
        )

    if not request.upload_batch_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Select at least one upload batch before applying mapping.",
        )

    normalized_ticket_type = request.ticket_type.strip().upper()
    try:
        resolved_mapping, _mapping_source = resolve_mapping_for_project_ticket_type(
            db=db,
            project_id=request.project_id,
            ticket_type=normalized_ticket_type,
            mapping=request.mapping,
        )
        if request.save_as_default_for_ticket_type:
            save_mapping_template(
                db=db,
                project_id=request.project_id,
                ticket_type=normalized_ticket_type,
                mapping=resolved_mapping,
            )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except MappingError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    files: list[UploadBatchApplyMappingFileResponse] = []
    seen_batch_ids: set[UUID] = set()
    for upload_batch_id in request.upload_batch_ids:
        if upload_batch_id in seen_batch_ids:
            continue
        seen_batch_ids.add(upload_batch_id)

        upload_batch = db.get(UploadBatch, upload_batch_id)
        if (
            upload_batch is None
            or upload_batch.project_id != request.project_id
            or batch_is_deleted(upload_batch)
        ):
            files.append(
                UploadBatchApplyMappingFileResponse(
                    upload_batch_id=upload_batch_id,
                    batch_name="Unknown batch",
                    status=APPLY_STATUS_FAILED,
                    input_rows=0,
                    in_scope_rows=0,
                    out_of_scope_rows=0,
                    error="Upload batch was not found for the selected project.",
                )
            )
            continue

        filename = batch_file_label(db, upload_batch.id)
        batch_ticket_type = get_batch_ticket_type(db, upload_batch.id)
        if batch_ticket_type and batch_ticket_type != normalized_ticket_type:
            counts = batch_output_counts(db, upload_batch.id)
            files.append(
                UploadBatchApplyMappingFileResponse(
                    upload_batch_id=upload_batch.id,
                    batch_name=upload_batch.batch_name,
                    filename=filename,
                    status=APPLY_STATUS_FAILED,
                    input_rows=counts["raw_rows"],
                    in_scope_rows=counts["in_scope_rows"],
                    out_of_scope_rows=counts["out_of_scope_rows"],
                    blank_assignment_group_rows=counts["blank_assignment_group_rows"],
                    assignment_group_not_in_inventory_rows=counts[
                        "assignment_group_not_in_inventory_rows"
                    ],
                    duplicate_skipped_rows=counts["duplicate_skipped_rows"],
                    failed_rows=counts["failed_rows"],
                    error=(
                        f"Batch ticket type is {batch_ticket_type}, not "
                        f"{normalized_ticket_type}."
                    ),
                )
            )
            continue

        counts = batch_output_counts(db, upload_batch.id)
        if request.skip_already_applied and counts["output_rows"] > 0:
            if counts["raw_rows"] == counts["output_rows"]:
                files.append(
                    UploadBatchApplyMappingFileResponse(
                        upload_batch_id=upload_batch.id,
                        batch_name=upload_batch.batch_name,
                        filename=filename,
                        status=APPLY_STATUS_ALREADY_APPLIED,
                        input_rows=counts["raw_rows"],
                        in_scope_rows=counts["in_scope_rows"],
                        out_of_scope_rows=counts["out_of_scope_rows"],
                        blank_assignment_group_rows=counts["blank_assignment_group_rows"],
                        assignment_group_not_in_inventory_rows=counts[
                            "assignment_group_not_in_inventory_rows"
                        ],
                        duplicate_skipped_rows=counts["duplicate_skipped_rows"],
                        failed_rows=0,
                        warnings=["Batch already has complete mapped output and was skipped."],
                    )
                )
            else:
                files.append(
                    UploadBatchApplyMappingFileResponse(
                        upload_batch_id=upload_batch.id,
                        batch_name=upload_batch.batch_name,
                        filename=filename,
                        status=APPLY_STATUS_PARTIAL_OUTPUT,
                        input_rows=counts["raw_rows"],
                        in_scope_rows=counts["in_scope_rows"],
                        out_of_scope_rows=counts["out_of_scope_rows"],
                        blank_assignment_group_rows=counts["blank_assignment_group_rows"],
                        assignment_group_not_in_inventory_rows=counts[
                            "assignment_group_not_in_inventory_rows"
                        ],
                        duplicate_skipped_rows=counts["duplicate_skipped_rows"],
                        failed_rows=counts["failed_rows"],
                        error=(
                            "Batch has partial mapped output. It was not reprocessed "
                            "automatically to avoid hiding a data repair issue."
                        ),
                    )
                )
            continue

        try:
            result = apply_mapping_to_batch(
                db=db,
                upload_batch_id=upload_batch.id,
                mapping=resolved_mapping,
                delete_existing=request.delete_existing,
            )
            files.append(
                UploadBatchApplyMappingFileResponse(
                    upload_batch_id=upload_batch.id,
                    batch_name=upload_batch.batch_name,
                    filename=filename,
                    status=APPLY_STATUS_APPLIED,
                    input_rows=result.total_raw_rows,
                    in_scope_rows=result.normalized_ticket_count,
                    out_of_scope_rows=result.out_of_scope_ticket_count,
                    blank_assignment_group_rows=result.blank_assignment_group_count,
                    assignment_group_not_in_inventory_rows=(
                        result.assignment_group_not_in_inventory_count
                    ),
                    duplicate_skipped_rows=result.duplicate_skipped_count,
                    failed_rows=result.failed_row_count,
                    warnings=result.warnings,
                    errors=[
                        f"Row {error.row_number}: {error.message}"
                        for error in result.errors[:10]
                    ],
                )
            )
        except (FileNotFoundError, MappingError, SQLAlchemyError) as exc:
            failed_counts = batch_output_counts(db, upload_batch.id)
            files.append(
                UploadBatchApplyMappingFileResponse(
                    upload_batch_id=upload_batch.id,
                    batch_name=upload_batch.batch_name,
                    filename=filename,
                    status=APPLY_STATUS_FAILED,
                    input_rows=failed_counts["raw_rows"],
                    in_scope_rows=failed_counts["in_scope_rows"],
                    out_of_scope_rows=failed_counts["out_of_scope_rows"],
                    blank_assignment_group_rows=failed_counts["blank_assignment_group_rows"],
                    assignment_group_not_in_inventory_rows=failed_counts[
                        "assignment_group_not_in_inventory_rows"
                    ],
                    duplicate_skipped_rows=failed_counts["duplicate_skipped_rows"],
                    failed_rows=failed_counts["failed_rows"],
                    error=str(exc),
                )
            )

    if normalized_ticket_type in GENERIC_FILTER_FACT_TICKET_TYPES and any(
        file.status == APPLY_STATUS_APPLIED for file in files
    ):
        refresh_dashboard_filter_facts(db, request.project_id)
        mark_filter_caches_stale(db, request.project_id)
        db.commit()

    return UploadBatchApplyMappingMultipleResponse(
        project_id=request.project_id,
        ticket_type=normalized_ticket_type,
        files=files,
        totals=build_apply_mapping_totals(files),
    )


@router.get("/batches", response_model=list[UploadBatchResponse])
def list_upload_batches(
    db: DbSession,
    project_id: UUID | None = None,
    view: Annotated[str, Query(pattern="^(active|history|all)$")] = BATCH_VIEW_ALL,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[UploadBatchResponse]:
    statement = select(UploadBatch).order_by(UploadBatch.created_at.desc())
    if project_id is not None:
        statement = statement.where(UploadBatch.project_id == project_id)

    upload_batches = list(db.scalars(statement).all())
    filtered_batches: list[UploadBatch] = []
    for upload_batch in upload_batches:
        if upload_batch.status not in {BATCH_STATUS_NORMALIZED, BATCH_STATUS_ARCHIVED}:
            recalculate_upload_batch_status(db, upload_batch.id)
        sync_legacy_normalized_status(db, upload_batch)
        if batch_matches_view(upload_batch, view):
            filtered_batches.append(upload_batch)
    db.commit()

    paged_batches = filtered_batches[offset : offset + limit]
    return [build_upload_batch_response(db, upload_batch) for upload_batch in paged_batches]


@router.delete("/batches/{upload_batch_id}", response_model=UploadBatchResponse)
def delete_staging_upload_batch(
    upload_batch_id: UUID,
    db: DbSession,
) -> UploadBatchResponse:
    upload_batch = get_existing_batch_or_404(db, upload_batch_id)
    normalized_ticket_count = count_normalized_tickets(db, upload_batch_id)
    if normalized_ticket_count > 0 or upload_batch.status in {
        BATCH_STATUS_NORMALIZED,
        BATCH_STATUS_ARCHIVED,
    }:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "This batch has already been normalized. Delete normalized ticket data first "
                "or archive it instead."
            ),
        )

    upload_batch.status = BATCH_STATUS_DELETED
    upload_batch.deleted_at = utc_now()
    db.commit()
    db.refresh(upload_batch)
    return build_upload_batch_response(db, upload_batch)


@router.post("/batches/{upload_batch_id}/archive", response_model=UploadBatchResponse)
def archive_upload_batch(
    upload_batch_id: UUID,
    db: DbSession,
) -> UploadBatchResponse:
    upload_batch = get_existing_batch_or_404(db, upload_batch_id)
    normalized_ticket_count = count_normalized_tickets(db, upload_batch_id)
    if normalized_ticket_count == 0 and upload_batch.status != BATCH_STATUS_NORMALIZED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only normalized batches can be archived.",
        )

    now = utc_now()
    upload_batch.status = BATCH_STATUS_ARCHIVED
    upload_batch.archived_at = now
    upload_batch.normalized_at = upload_batch.normalized_at or now
    upload_batch.completed_at = upload_batch.completed_at or now
    db.commit()
    db.refresh(upload_batch)
    return build_upload_batch_response(db, upload_batch)


@router.get("/batches/{upload_batch_id}/files", response_model=list[UploadedFileResponse])
def list_uploaded_files_for_batch(
    upload_batch_id: UUID,
    db: DbSession,
) -> list[UploadedFile]:
    get_existing_batch_or_404(db, upload_batch_id)

    recalculate_upload_batch_status(db, upload_batch_id)
    db.commit()

    statement = (
        select(UploadedFile)
        .where(UploadedFile.upload_batch_id == upload_batch_id)
        .order_by(UploadedFile.created_at.asc())
    )
    return list(db.scalars(statement).all())


@router.post("/files/{uploaded_file_id}/ingest", response_model=IngestionJobResponse)
def trigger_file_ingestion(
    uploaded_file_id: UUID,
    db: DbSession,
) -> IngestionJob:
    try:
        return ingest_uploaded_file(db, uploaded_file_id)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except IngestionJobAlreadyRunningError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except UnsupportedIngestionFileTypeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except IngestionError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"File ingestion failed: {exc}",
        ) from exc


@router.get("/ingestion-jobs/{ingestion_job_id}", response_model=IngestionJobResponse)
def get_ingestion_job_status(
    ingestion_job_id: UUID,
    db: DbSession,
) -> IngestionJob:
    ingestion_job = db.get(IngestionJob, ingestion_job_id)
    if ingestion_job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Ingestion job {ingestion_job_id} was not found.",
        )
    return ingestion_job


@router.get(
    "/batches/{upload_batch_id}/raw-rows/preview",
    response_model=RawRowsPreviewResponse,
)
def preview_raw_rows(
    upload_batch_id: UUID,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=100)] = 5,
) -> RawRowsPreviewResponse:
    get_existing_batch_or_404(db, upload_batch_id)

    statement = (
        select(TicketRawRow)
        .where(TicketRawRow.upload_batch_id == upload_batch_id)
        .order_by(TicketRawRow.uploaded_file_id.asc(), TicketRawRow.row_number.asc())
        .limit(limit)
    )
    rows = list(db.scalars(statement).all())
    return RawRowsPreviewResponse(
        upload_batch_id=upload_batch_id,
        limit=limit,
        rows=rows,
        message="No raw rows found. Ingest the uploaded file first." if not rows else None,
    )


@router.get(
    "/batches/{upload_batch_id}/validation-summary",
    response_model=ValidationSummaryResponse,
)
def get_validation_summary(
    upload_batch_id: UUID,
    db: DbSession,
) -> ValidationSummaryResponse:
    get_existing_batch_or_404(db, upload_batch_id)
    try:
        summary = build_validation_summary(db, upload_batch_id)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    return ValidationSummaryResponse(
        upload_batch_id=summary.upload_batch_id,
        total_raw_rows=summary.total_raw_rows,
        missing_ticket_id_count=summary.missing_ticket_id_count,
        missing_created_date_count=summary.missing_created_date_count,
        duplicate_ticket_id_count=summary.duplicate_ticket_id_count,
        duplicate_ticket_ids=summary.duplicate_ticket_ids,
        detected_source_columns=summary.detected_source_columns,
        rows_by_uploaded_file=[
            {
                "uploaded_file_id": file_count.uploaded_file_id,
                "original_filename": file_count.original_filename,
                "saved_filename": file_count.saved_filename,
                "row_count": file_count.row_count,
            }
            for file_count in summary.rows_by_uploaded_file
        ],
        message=summary.message,
    )
