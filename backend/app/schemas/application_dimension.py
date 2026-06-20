from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ApplicationDimensionBase(BaseModel):
    project_id: UUID
    customer_name: str | None = None
    tower_name: str | None = None
    cluster_name: str | None = None
    application_group_name: str | None = None
    application_name: str
    application_alias: str | None = None
    business_service_alias: str | None = None
    cmdb_ci_alias: str | None = None
    notes: str | None = None
    is_active: bool = True


class ApplicationDimensionCreateRequest(ApplicationDimensionBase):
    pass


class ApplicationDimensionUpdateRequest(BaseModel):
    customer_name: str | None = None
    tower_name: str | None = None
    cluster_name: str | None = None
    application_group_name: str | None = None
    application_name: str | None = None
    application_alias: str | None = None
    business_service_alias: str | None = None
    cmdb_ci_alias: str | None = None
    notes: str | None = None
    is_active: bool | None = None


class ApplicationDimensionResponse(ApplicationDimensionBase):
    id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ApplicationDimensionBulkUploadResponse(BaseModel):
    project_id: UUID
    total_rows: int
    inserted_count: int
    updated_count: int
    skipped_count: int
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ApplicationDimensionEnrichRequest(BaseModel):
    project_id: UUID
    replace_existing: bool = True


class ValueCountResponse(BaseModel):
    value: str
    count: int


class ApplicationDimensionEnrichmentSummaryResponse(BaseModel):
    project_id: UUID
    total_tickets: int
    matched_tickets: int
    unmatched_tickets: int
    updated_tickets: int
    match_rate_pct: float | None
    match_counts_by_source: dict[str, int]
    top_unmatched_applications: list[ValueCountResponse]
    top_unmatched_business_services: list[ValueCountResponse]
    top_unmatched_cmdb_ci: list[ValueCountResponse]
    top_unmatched_service_offerings: list[ValueCountResponse]
    top_unmatched_catalog_items: list[ValueCountResponse]
