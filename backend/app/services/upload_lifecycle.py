from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Ticket, UploadBatch

BATCH_STATUS_UPLOADED = "UPLOADED"
BATCH_STATUS_INGESTING = "INGESTING"
BATCH_STATUS_INGESTED = "INGESTED"
BATCH_STATUS_INGESTION_FAILED = "INGESTION_FAILED"
BATCH_STATUS_NORMALIZING = "NORMALIZING"
BATCH_STATUS_NORMALIZED = "NORMALIZED"
BATCH_STATUS_NORMALIZATION_FAILED = "NORMALIZATION_FAILED"
BATCH_STATUS_ARCHIVED = "ARCHIVED"
BATCH_STATUS_DELETED = "DELETED"

LEGACY_ACTIVE_STATUSES = {"PENDING", "RUNNING", "PARTIAL", "FAILED", "COMPLETED", "created"}
NORMALIZATION_TERMINAL_STATUSES = {
    BATCH_STATUS_NORMALIZING,
    BATCH_STATUS_NORMALIZED,
    BATCH_STATUS_NORMALIZATION_FAILED,
    BATCH_STATUS_ARCHIVED,
    BATCH_STATUS_DELETED,
}


def utc_now() -> datetime:
    return datetime.now(UTC)


def count_normalized_tickets(db: Session, upload_batch_id: UUID) -> int:
    return int(
        db.scalar(select(func.count(Ticket.id)).where(Ticket.upload_batch_id == upload_batch_id))
        or 0
    )


def mark_upload_batch_normalizing(upload_batch: UploadBatch) -> None:
    upload_batch.status = BATCH_STATUS_NORMALIZING
    upload_batch.completed_at = None


def mark_upload_batch_normalized(upload_batch: UploadBatch) -> None:
    now = utc_now()
    upload_batch.status = BATCH_STATUS_NORMALIZED
    upload_batch.normalized_at = now
    upload_batch.completed_at = now
    upload_batch.archived_at = None


def mark_upload_batch_normalization_failed(upload_batch: UploadBatch) -> None:
    upload_batch.status = BATCH_STATUS_NORMALIZATION_FAILED
    upload_batch.completed_at = utc_now()


def sync_legacy_normalized_status(
    db: Session,
    upload_batch: UploadBatch,
) -> int:
    ticket_count = count_normalized_tickets(db, upload_batch.id)
    if (
        ticket_count > 0
        and upload_batch.status not in NORMALIZATION_TERMINAL_STATUSES
        and upload_batch.status in LEGACY_ACTIVE_STATUSES | {
            BATCH_STATUS_UPLOADED,
            BATCH_STATUS_INGESTING,
            BATCH_STATUS_INGESTED,
            BATCH_STATUS_INGESTION_FAILED,
        }
    ):
        mark_upload_batch_normalized(upload_batch)
    return ticket_count
