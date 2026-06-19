from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field


class IncidentSlaUploadResponse(BaseModel):
    project_id: UUID
    uploaded_file_name: str
    total_rows: int
    inserted_rows: int
    failed_rows: int
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class IncidentSlaEnrichRequest(BaseModel):
    project_id: UUID
    ticket_type: str = "INCIDENT"
    replace_existing: bool = True


class IncidentSlaEnrichResponse(BaseModel):
    project_id: UUID
    ticket_type: str
    replace_existing: bool
    matched_ticket_count: int
    response_sla_updated_count: int
    resolution_sla_updated_count: int
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
