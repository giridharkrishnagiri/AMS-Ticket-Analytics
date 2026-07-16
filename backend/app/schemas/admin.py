from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class OperationalDataResetRequest(BaseModel):
    confirmation: str


class OperationalDataResetResponse(BaseModel):
    deleted_counts: dict[str, int]
    updated_counts: dict[str, int] = {}
    preserved: list[str]
    reset_incidents: bool | None = None
    reset_sc_tasks: bool | None = None
    reset_problems: bool | None = None
    reset_changes: bool | None = None
    reset_incident_sla: bool | None = None
    incident_sla_reset_reason: str | None = None


class ProjectOperationalDataResetRequest(BaseModel):
    project_id: UUID
    confirmation: str
    reset_incidents: bool = False
    reset_sc_tasks: bool = False
    reset_problems: bool = False
    reset_changes: bool = False
    reset_incident_sla: bool = False


class DashboardFilterFactsRefreshRequest(BaseModel):
    project_id: UUID


class DashboardFilterFactsRefreshResponse(BaseModel):
    project_id: UUID
    rows_deleted: int
    rows_inserted: int
    in_scope_rows: int
    out_of_scope_rows: int
    duration_ms: int


class InScopeAssignmentGroupPreviewRowResponse(BaseModel):
    assignment_group: str
    functional_track: str | None = None
    is_in_scope: bool = True
    source_row_number: int | None = None


class InScopeAssignmentGroupsImportResponse(BaseModel):
    project_id: UUID
    source_filename: str
    total_rows: int
    imported_count: int
    skipped_count: int
    duplicate_count: int
    warning_count: int
    error_count: int
    warnings: list[str]
    errors: list[str]
    preview_rows: list[InScopeAssignmentGroupPreviewRowResponse]


class InScopeAssignmentGroupsStatusResponse(BaseModel):
    project_id: UUID
    active_count: int
    last_imported_at: datetime | None = None
    preview_rows: list[InScopeAssignmentGroupPreviewRowResponse]


class InScopeAssignmentGroupRowResponse(BaseModel):
    id: UUID
    project_id: UUID
    assignment_group: str
    assignment_group_key: str
    functional_track: str | None = None
    is_in_scope: bool
    source_filename: str | None = None
    source_row_number: int | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class InScopeAssignmentGroupUpdateRowRequest(BaseModel):
    id: UUID
    functional_track: str | None = None
    is_in_scope: bool


class InScopeAssignmentGroupsUpdateRequest(BaseModel):
    project_id: UUID
    rows: list[InScopeAssignmentGroupUpdateRowRequest]


class InScopeAssignmentGroupChangeResponse(BaseModel):
    id: UUID
    assignment_group: str
    previous_functional_track: str | None = None
    next_functional_track: str | None = None
    previous_is_in_scope: bool
    next_is_in_scope: bool
    tickets_updated: int


class InScopeAssignmentGroupsUpdateResponse(BaseModel):
    project_id: UUID
    submitted_count: int
    changed_count: int
    unchanged_count: int
    tickets_updated_count: int
    inventory_rows_updated_count: int
    missing_count: int
    warnings: list[str]
    changes: list[InScopeAssignmentGroupChangeResponse]


class AssignmentGroupMasterPreviewRowResponse(BaseModel):
    assignment_group: str
    description: str | None = None
    manager_name: str | None = None
    source_sheet_name: str | None = None
    source_row_number: int | None = None


class AssignmentGroupMasterImportResponse(BaseModel):
    project_id: UUID
    source_filename: str
    total_rows: int
    imported_count: int
    manager_populated_count: int
    skipped_count: int
    duplicate_count: int
    warning_count: int
    error_count: int
    warnings: list[str]
    errors: list[str]
    preview_rows: list[AssignmentGroupMasterPreviewRowResponse]


class AssignmentGroupMasterStatusResponse(BaseModel):
    project_id: UUID
    active_count: int
    manager_populated_count: int
    last_imported_at: datetime | None = None
    last_imported_filename: str | None = None
    preview_rows: list[AssignmentGroupMasterPreviewRowResponse]


class AssignmentGroupMasterRowResponse(BaseModel):
    id: UUID
    project_id: UUID
    assignment_group: str
    assignment_group_key: str
    description: str | None = None
    manager_name: str | None = None
    source_filename: str | None = None
    source_sheet_name: str | None = None
    source_row_number: int | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


OperationalReprocessDomain = Literal["incidents", "sc_tasks", "problems", "changes"]
OperationalReprocessStartPoint = Literal[
    "resume_from_ingestion",
    "resume_from_normalization",
    "reapply_mapping_only",
]


class OperationalReprocessingRequest(BaseModel):
    project_id: UUID
    domains: list[OperationalReprocessDomain]
    start_point: OperationalReprocessStartPoint
    confirmation: str


class OperationalReprocessingResponse(BaseModel):
    project_id: UUID
    domains: list[str]
    start_point: str
    cleared_counts: dict[str, int]
    updated_counts: dict[str, int]
    preserved: list[str]
    warnings: list[str]


class ProjectDeleteRequest(BaseModel):
    project_id: UUID
    confirmation: str


class ClientDeleteRequest(BaseModel):
    client_id: UUID
    confirmation: str


class ScopedDeleteResponse(BaseModel):
    deleted_counts: dict[str, int]
    preserved: list[str]
