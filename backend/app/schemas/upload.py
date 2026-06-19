from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class UploadedFileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    upload_batch_id: UUID
    project_id: UUID
    ticket_type: str
    original_filename: str
    saved_filename: str | None
    storage_path: str
    content_type: str | None
    size_bytes: int
    checksum_sha256: str | None
    status: str
    created_at: datetime
    updated_at: datetime


class IngestionJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    upload_batch_id: UUID
    uploaded_file_id: UUID | None
    job_type: str
    status: str
    rows_total: int
    rows_processed: int
    processed_row_count: int
    started_at: datetime | None
    completed_at: datetime | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime


class UploadBatchResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    month_key: str | None
    period_type: str
    snapshot_date: date | None
    batch_name: str
    source_system: str | None
    status: str
    uploaded_by: str | None
    file_count: int
    total_size_bytes: int
    description: str | None
    ticket_type: str | None = None
    uploaded_file_count: int | None = None
    raw_row_count: int | None = None
    normalized_ticket_count: int | None = None
    normalized_at: datetime | None = None
    archived_at: datetime | None = None
    deleted_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class UploadCreateResponse(BaseModel):
    batch: UploadBatchResponse
    files: list[UploadedFileResponse]
    ingestion_jobs: list[IngestionJobResponse]


class RawRowPreviewItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    upload_batch_id: UUID
    uploaded_file_id: UUID
    ticket_type: str
    row_number: int
    source_filename: str | None
    raw_ticket_number: str | None
    raw_data: dict[str, object]
    row_hash: str | None
    created_at: datetime


class RawRowsPreviewResponse(BaseModel):
    upload_batch_id: UUID
    limit: int
    rows: list[RawRowPreviewItem]
    message: str | None = None


class RowsByUploadedFileResponse(BaseModel):
    uploaded_file_id: UUID
    original_filename: str
    saved_filename: str | None
    row_count: int


class ValidationSummaryResponse(BaseModel):
    upload_batch_id: UUID
    total_raw_rows: int
    missing_ticket_id_count: int
    missing_created_date_count: int
    duplicate_ticket_id_count: int
    duplicate_ticket_ids: dict[str, int]
    detected_source_columns: list[str]
    rows_by_uploaded_file: list[RowsByUploadedFileResponse]
    message: str | None = None
