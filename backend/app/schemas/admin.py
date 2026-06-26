from __future__ import annotations

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


class ProjectDeleteRequest(BaseModel):
    project_id: UUID
    confirmation: str


class ClientDeleteRequest(BaseModel):
    client_id: UUID
    confirmation: str


class ScopedDeleteResponse(BaseModel):
    deleted_counts: dict[str, int]
    preserved: list[str]
