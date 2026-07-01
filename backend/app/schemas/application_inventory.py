from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class ApplicationInventoryItemUpdateRequest(BaseModel):
    application_number_apm: str | None = None
    parent_application_name: str | None = None
    assignment_group: str | None = None
    assignment_group_owner: str | None = None
    application_owner: str | None = None
    business_service_ci_name: str | None = None
    support_lead: str | None = None
    functional_track: str | None = None
    ams_owner: str | None = None
    supported_by_vendor: str | None = None
    hosting_env: str | None = None
    global_application: str | None = None
    scope_status: str | None = None
    lifecycle_stage_status: str | None = None
    lifecycle_current: str | None = None
    lifecycle_1_to_3_years: str | None = None
    lifecycle_3_to_5_years: str | None = None
    active: bool | None = None
    active_users: int | None = None
    avg_monthly_ticket_volume_6m: float | None = None
    tickets_per_user_per_month: float | None = None
    cmdb_payload: dict[str, Any] | None = None


class ApplicationInventoryItemResponse(BaseModel):
    id: UUID
    project_id: UUID
    application_number_apm: str | None
    parent_application_name: str | None
    assignment_group: str | None
    assignment_group_owner: str | None
    application_owner: str | None
    business_service_ci_name: str
    support_lead: str | None
    functional_track: str | None
    ams_owner: str | None
    supported_by_vendor: str | None
    hosting_env: str | None
    global_application: str | None
    scope_status: str
    lifecycle_stage_status: str | None
    lifecycle_current: str | None
    lifecycle_1_to_3_years: str | None
    lifecycle_3_to_5_years: str | None
    active: bool | None
    active_users: int | None
    avg_monthly_ticket_volume_6m: float | None
    tickets_per_user_per_month: float | None
    cmdb_payload: dict[str, Any] | None
    source_filename: str | None
    source_row_number: int | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ApplicationInventoryUploadResponse(BaseModel):
    project_id: UUID
    total_rows: int
    inserted_count: int
    updated_count: int
    skipped_count: int
    error_count: int
    warning_count: int
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    distinct_business_service_count: int
    distinct_parent_application_count: int
    distinct_assignment_group_count: int
    distinct_application_owner_count: int
    distinct_support_lead_count: int
    distinct_functional_track_count: int
    distinct_ams_owner_count: int
    distinct_supported_vendor_count: int


class ApplicationInventoryEnrichRequest(BaseModel):
    project_id: UUID
    replace_existing: bool = True


class ApplicationTicketUserMetricsRecomputeResponse(BaseModel):
    project_id: UUID
    inventory_count: int
    active_users_count: int
    metrics_updated_count: int
    window_start: datetime
    window_end: datetime


class ValueCountResponse(BaseModel):
    value: str
    count: int


class ApplicationInventoryEnrichmentSummaryResponse(BaseModel):
    project_id: UUID
    total_tickets: int
    matched_tickets: int
    unmatched_tickets: int
    updated_tickets: int
    match_rate_pct: float | None
    matched_by_business_service_count: int
    matched_by_application_count: int
    unmatched_business_service_count: int
    distinct_ticket_business_service_count: int
    distinct_inventory_business_service_count: int
    top_unmatched_business_services: list[ValueCountResponse]
    top_unmatched_applications: list[ValueCountResponse]
    top_unmatched_assignment_groups: list[ValueCountResponse]


class UnmatchedBusinessServiceResponse(BaseModel):
    business_service: str
    ticket_count: int
    assignment_group_count: int
    sample_assignment_groups: list[str]
    sample_ticket_numbers: list[str]


class UnmatchedBusinessServicesResponse(BaseModel):
    project_id: UUID
    distinct_ticket_business_service_count: int
    distinct_inventory_business_service_count: int
    matched_business_service_count: int
    unmatched_business_service_count: int
    business_service_coverage_pct: float | None
    rows: list[UnmatchedBusinessServiceResponse]


class ApplicationInventoryFilterValuesResponse(BaseModel):
    application_owners: list[str]
    support_leads: list[str]
    functional_tracks: list[str]
    ams_owners: list[str]
    supported_by_vendors: list[str]
    hosting_envs: list[str]
    parent_application_names: list[str]
    business_service_ci_names: list[str]
    assignment_groups: list[str]


class ScopeSummaryValueCountResponse(BaseModel):
    value: str
    count: int


class ScopeSummaryResponse(BaseModel):
    project_id: UUID
    in_scope_tickets: int
    out_of_scope_tickets: int
    total_classified_tickets: int
    in_scope_pct: float | None
    out_of_scope_pct: float | None
    distinct_in_scope_assignment_groups: int
    distinct_out_of_scope_assignment_groups: int
    top_out_of_scope_assignment_groups: list[ScopeSummaryValueCountResponse]
    top_out_of_scope_business_services: list[ScopeSummaryValueCountResponse]
