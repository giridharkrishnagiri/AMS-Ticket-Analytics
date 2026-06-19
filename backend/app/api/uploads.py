from __future__ import annotations

import re
import shutil
from datetime import UTC, date, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import IngestionJob, Project, TicketRawRow, UploadBatch, UploadedFile
from app.schemas.upload import (
    IngestionJobResponse,
    RawRowsPreviewResponse,
    UploadBatchResponse,
    UploadCreateResponse,
    UploadedFileResponse,
    ValidationSummaryResponse,
)
from app.services.ingestion import (
    IngestionError,
    IngestionJobAlreadyRunningError,
    UnsupportedIngestionFileTypeError,
    build_validation_summary,
    ingest_uploaded_file,
    recalculate_upload_batch_status,
)
from app.services.upload_lifecycle import (
    BATCH_STATUS_ARCHIVED,
    BATCH_STATUS_DELETED,
    BATCH_STATUS_NORMALIZED,
    BATCH_STATUS_UPLOADED,
    count_normalized_tickets,
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
