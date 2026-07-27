from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field


class ResourceDemandServiceLevelValues(BaseModel):
    l1_5: float | None = None
    l2: float | None = None
    l3: float | None = None


class ResourceDemandInputRow(BaseModel):
    key: str
    label: str
    ticket_type: str
    incident_source: str | None = None
    average_monthly_volume: float | None = None
    service_level_split: ResourceDemandServiceLevelValues = Field(
        default_factory=ResourceDemandServiceLevelValues,
    )
    notes: str | None = None


class ResourceDemandTechnologyView(BaseModel):
    key: str
    label: str
    rows: list[ResourceDemandInputRow]


class ResourceDemandUnitEffortRow(BaseModel):
    id: UUID | None = None
    ticket_type: str
    incident_source: str = "Any"
    technology: str = "Generic"
    l1_5_hours: float | None = None
    l2_hours: float | None = None
    l3_hours: float | None = None
    sort_order: int = 0


class ResourceDemandServiceLevelSplitRow(BaseModel):
    id: UUID | None = None
    ticket_type: str
    incident_source: str = "Any"
    technology: str = "Generic"
    l1_5_pct: float | None = None
    l2_pct: float | None = None
    l3_pct: float | None = None
    sort_order: int = 0


class ResourceDemandResponse(BaseModel):
    project_id: UUID
    period_from_month: str
    period_to_month: str
    month_count: int
    technologies: list[str]
    demand_views: list[ResourceDemandTechnologyView]
    unit_efforts: list[ResourceDemandUnitEffortRow]
    service_level_splits: list[ResourceDemandServiceLevelSplitRow]
    data_notes: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ResourceDemandUnitEffortUpdateRequest(BaseModel):
    project_id: UUID
    rows: list[ResourceDemandUnitEffortRow]


class ResourceDemandServiceLevelSplitUpdateRequest(BaseModel):
    project_id: UUID
    rows: list[ResourceDemandServiceLevelSplitRow]
