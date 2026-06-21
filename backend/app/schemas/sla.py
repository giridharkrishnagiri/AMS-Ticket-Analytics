from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class IncidentSlaUploadResponse(BaseModel):
    project_id: UUID
    upload_id: UUID | None = None
    uploaded_file_name: str
    status: str = "UPLOADED"
    total_rows: int
    inserted_rows: int
    duplicate_rows_skipped: int = 0
    failed_rows: int
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class IncidentSlaUploadFileResponse(IncidentSlaUploadResponse):
    pass


class IncidentSlaUploadTotalsResponse(BaseModel):
    total_files: int
    total_rows_read: int
    inserted_rows: int
    duplicate_rows_skipped: int
    error_rows: int


class IncidentSlaMultiUploadResponse(BaseModel):
    project_id: UUID
    files: list[IncidentSlaUploadFileResponse]
    totals: IncidentSlaUploadTotalsResponse


class IncidentSlaUploadHistoryRowResponse(BaseModel):
    upload_id: UUID
    filename: str
    uploaded_at: datetime
    total_rows_read: int
    inserted_rows: int
    duplicate_rows_skipped: int
    error_rows: int
    status: str


class IncidentSlaEnrichRequest(BaseModel):
    project_id: UUID
    ticket_type: str = "INCIDENT"
    replace_existing: bool = True


class IncidentSlaRowsStatsResponse(BaseModel):
    total_rows: int
    distinct_ticket_numbers_in_sla_rows: int
    duplicate_rows_skipped_on_upload: int


class IncidentSlaScopeStatsResponse(BaseModel):
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


class IncidentSlaUnmatchedStatsResponse(BaseModel):
    sla_ticket_numbers_not_found_in_scope_or_out_of_scope: int
    in_scope_incidents_without_sla_rows: int
    out_of_scope_incidents_without_sla_rows: int


class IncidentSlaEnrichResponse(BaseModel):
    project_id: UUID
    ticket_type: str
    replace_existing: bool
    matched_ticket_count: int
    response_sla_updated_count: int
    resolution_sla_updated_count: int
    in_scope_incidents_considered: int = 0
    in_scope_incidents_enriched: int = 0
    out_of_scope_incidents_considered: int = 0
    out_of_scope_incidents_enriched: int = 0
    response_vendor_specific_count: int = 0
    response_default_count: int = 0
    resolution_vendor_specific_count: int = 0
    resolution_default_count: int = 0
    missing_response_sla_count: int = 0
    missing_resolution_sla_count: int = 0
    sla_rows: IncidentSlaRowsStatsResponse
    in_scope: IncidentSlaScopeStatsResponse
    out_of_scope: IncidentSlaScopeStatsResponse
    unmatched: IncidentSlaUnmatchedStatsResponse
    warnings: list[str] = Field(default_factory=list)


class IncidentSlaSummaryResponse(BaseModel):
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


class IncidentSlaUnmatchedRow(BaseModel):
    inc_number: str
    row_count: int


class IncidentSlaUnmatchedResponse(BaseModel):
    project_id: UUID
    limit: int
    offset: int
    rows: list[IncidentSlaUnmatchedRow]


class IncidentSlaDeduplicateRequest(BaseModel):
    project_id: UUID
    confirmation: str


class IncidentSlaDeduplicateResponse(BaseModel):
    project_id: UUID
    duplicate_groups_found: int
    duplicate_rows_deleted: int
    remaining_sla_rows: int
