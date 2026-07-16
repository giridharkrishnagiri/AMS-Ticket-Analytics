from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


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
    error_message: str | None = None
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
    in_scope_ticket_count: int | None = None
    out_of_scope_ticket_count: int | None = None
    normalized_at: datetime | None = None
    archived_at: datetime | None = None
    deleted_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class UploadCreateResponse(BaseModel):
    batch: UploadBatchResponse
    files: list[UploadedFileResponse]
    ingestion_jobs: list[IngestionJobResponse]


class UploadMultipleFileResponse(BaseModel):
    filename: str
    size_bytes: int | None = None
    upload_batch_id: UUID | None = None
    uploaded_file_id: UUID | None = None
    ingestion_job_id: UUID | None = None
    status: str
    message: str | None = None
    warnings: list[str] = Field(default_factory=list)


class UploadMultipleTotalsResponse(BaseModel):
    files_selected: int
    files_uploaded: int
    files_failed: int


class UploadMultipleResponse(BaseModel):
    project_id: UUID
    ticket_type: str
    period_type: str
    files: list[UploadMultipleFileResponse]
    totals: UploadMultipleTotalsResponse


class UploadBatchActionRequest(BaseModel):
    project_id: UUID
    upload_batch_ids: list[UUID]


class UploadBatchIngestResultResponse(BaseModel):
    upload_batch_id: UUID
    batch_name: str
    filename: str | None = None
    status: str
    raw_rows_inserted: int
    error: str | None = None


class UploadBatchIngestTotalsResponse(BaseModel):
    batches_requested: int
    batches_ingested: int
    batches_failed: int
    raw_rows_inserted: int


class UploadBatchIngestMultipleResponse(BaseModel):
    project_id: UUID
    batches: list[UploadBatchIngestResultResponse]
    totals: UploadBatchIngestTotalsResponse


class UploadBatchNormalizeRequest(BaseModel):
    project_id: UUID
    ticket_type: str
    upload_batch_ids: list[UUID]
    delete_existing: bool = True


class UploadBatchNormalizeResultResponse(BaseModel):
    upload_batch_id: UUID
    batch_name: str
    filename: str | None = None
    status: str
    raw_rows: int
    in_scope_inserted: int
    out_of_scope_inserted: int
    assignment_group_not_in_inventory_rows: int = 0
    duplicate_skipped_rows: int = 0
    failed_rows: int
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class UploadBatchNormalizeTotalsResponse(BaseModel):
    raw_rows: int
    in_scope_inserted: int
    out_of_scope_inserted: int
    assignment_group_not_in_inventory_rows: int = 0
    duplicate_skipped_rows: int = 0
    failed_batches: int


class UploadBatchNormalizeMultipleResponse(BaseModel):
    project_id: UUID
    ticket_type: str
    batches: list[UploadBatchNormalizeResultResponse]
    totals: UploadBatchNormalizeTotalsResponse


class UploadBatchApplyMappingRequest(BaseModel):
    project_id: UUID
    ticket_type: str
    upload_batch_ids: list[UUID]
    mapping: dict[str, str] | None = None
    delete_existing: bool = True
    save_as_default_for_ticket_type: bool = True
    skip_already_applied: bool = True


class UploadBatchApplyMappingFileResponse(BaseModel):
    upload_batch_id: UUID
    batch_name: str
    filename: str | None = None
    status: str
    input_rows: int
    in_scope_rows: int
    out_of_scope_rows: int
    blank_assignment_group_rows: int = 0
    assignment_group_not_in_inventory_rows: int = 0
    duplicate_skipped_rows: int = 0
    failed_rows: int = 0
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    error: str | None = None


class UploadBatchApplyMappingTotalsResponse(BaseModel):
    total_files: int
    applied: int
    skipped: int
    failed: int
    input_rows: int
    in_scope_rows: int
    out_of_scope_rows: int
    blank_assignment_group_rows: int
    assignment_group_not_in_inventory_rows: int
    duplicate_skipped_rows: int = 0
    failed_rows: int


class UploadBatchApplyMappingMultipleResponse(BaseModel):
    project_id: UUID
    ticket_type: str
    files: list[UploadBatchApplyMappingFileResponse]
    totals: UploadBatchApplyMappingTotalsResponse


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
