from __future__ import annotations

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.dashboard import (
    ApplicationsChartsResponse,
    ApplicationsDataRequest,
    ApplicationsFilterValueCountsResponse,
    ApplicationsFilterValuesRequest,
    ApplicationsFilterValuesResponse,
    ApplicationsListResponse,
    ApplicationsSummaryResponse,
    CreatedResolvedOpenRow,
    CreationSourceTrendRow,
    DashboardOverviewResponse,
    FilterValuesResponse,
    IncidentSlaNameBreakdownResponse,
    IncidentSlaSummaryResponse,
    IncidentSlaTrendRow,
    MttrTrendRow,
    ReassignmentTrendRow,
    ReopenTrendRow,
    SlaTrendRow,
    TechnicalFunctionalBreakdownResponse,
    VolumetricsBacklogResponse,
    VolumetricsCreatedPatternRequest,
    VolumetricsCreatedPatternResponse,
    VolumetricsCreatedResolvedBacklogResponse,
    VolumetricsCreatedResolvedCanceledResponse,
    VolumetricsFilterValuesResponse,
    VolumetricsRequest,
    VolumetricsSummaryResponse,
)
from app.services.dashboard import (
    DashboardFilters,
    DateFilterBasis,
    TimeGrain,
    applications_charts,
    applications_filter_value_counts,
    applications_filter_values,
    applications_list,
    applications_summary,
    created_resolved_open_trend,
    creation_source_trend,
    filter_values,
    incident_sla_name_breakdown,
    incident_sla_summary,
    incident_sla_trend,
    mttr_trend,
    overview_summary,
    reassignment_trend,
    reopen_trend,
    sla_trend,
    technical_functional_breakdown,
    volumetrics_backlog,
    volumetrics_created_pattern,
    volumetrics_created_resolved_backlog,
    volumetrics_created_resolved_cancelled,
    volumetrics_filter_value_counts,
    volumetrics_summary,
)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])
DbSession = Annotated[Session, Depends(get_db)]


def parse_multi_values(values: list[str] | None) -> list[str]:
    if not values:
        return []

    parsed: list[str] = []
    for value in values:
        parsed.extend(part.strip() for part in value.split(",") if part.strip())
    return parsed


def dashboard_filters(
    project_id: Annotated[UUID, Query(...)],
    ticket_type: Annotated[list[str] | None, Query()] = None,
    priority: Annotated[list[str] | None, Query()] = None,
    state: Annotated[list[str] | None, Query()] = None,
    assignment_group: Annotated[list[str] | None, Query()] = None,
    application: Annotated[list[str] | None, Query()] = None,
    customer_name: Annotated[list[str] | None, Query()] = None,
    tower_name: Annotated[list[str] | None, Query()] = None,
    cluster_name: Annotated[list[str] | None, Query()] = None,
    application_group_name: Annotated[list[str] | None, Query()] = None,
    application_name: Annotated[list[str] | None, Query()] = None,
    response_sla_name: Annotated[list[str] | None, Query()] = None,
    resolution_sla_name: Annotated[list[str] | None, Query()] = None,
    functional_track: Annotated[list[str] | None, Query()] = None,
    ams_owner: Annotated[list[str] | None, Query()] = None,
    supported_by_vendor: Annotated[list[str] | None, Query()] = None,
    support_lead: Annotated[list[str] | None, Query()] = None,
    application_owner: Annotated[list[str] | None, Query()] = None,
    business_service_ci_name: Annotated[list[str] | None, Query()] = None,
    parent_application_name: Annotated[list[str] | None, Query()] = None,
    start_date: date | None = None,
    end_date: date | None = None,
    month_key: str | None = None,
    time_grain: TimeGrain = TimeGrain.MONTHLY,
    date_filter_basis: DateFilterBasis = DateFilterBasis.CREATED,
) -> DashboardFilters:
    return DashboardFilters(
        project_id=project_id,
        ticket_type=parse_multi_values(ticket_type),
        priority=parse_multi_values(priority),
        state=parse_multi_values(state),
        assignment_group=parse_multi_values(assignment_group),
        application=parse_multi_values(application),
        customer_name=parse_multi_values(customer_name),
        tower_name=parse_multi_values(tower_name),
        cluster_name=parse_multi_values(cluster_name),
        application_group_name=parse_multi_values(application_group_name),
        application_name=parse_multi_values(application_name),
        response_sla_name=parse_multi_values(response_sla_name),
        resolution_sla_name=parse_multi_values(resolution_sla_name),
        functional_track=parse_multi_values(functional_track),
        ams_owner=parse_multi_values(ams_owner),
        supported_by_vendor=parse_multi_values(supported_by_vendor),
        support_lead=parse_multi_values(support_lead),
        application_owner=parse_multi_values(application_owner),
        business_service_ci_name=parse_multi_values(business_service_ci_name),
        parent_application_name=parse_multi_values(parent_application_name),
        start_date=start_date,
        end_date=end_date,
        month_key=month_key,
        time_grain=time_grain,
        date_filter_basis=date_filter_basis,
    )


DashboardFilterDependency = Annotated[DashboardFilters, Depends(dashboard_filters)]


@router.get("/overview", response_model=DashboardOverviewResponse)
def get_dashboard_overview(
    project_id: Annotated[UUID, Query(...)],
    db: DbSession,
) -> dict[str, object]:
    try:
        return overview_summary(db, project_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get(
    "/applications/filter-values",
    response_model=ApplicationsFilterValuesResponse,
)
def get_dashboard_applications_filter_values(
    project_id: Annotated[UUID, Query(...)],
    db: DbSession,
) -> dict[str, object]:
    return applications_filter_values(db, project_id)


@router.post(
    "/applications/filter-values",
    response_model=ApplicationsFilterValueCountsResponse,
)
def get_dashboard_applications_filter_value_counts(
    request: ApplicationsFilterValuesRequest,
    db: DbSession,
) -> dict[str, object]:
    return applications_filter_value_counts(db, request)


@router.post("/applications/summary", response_model=ApplicationsSummaryResponse)
def get_dashboard_applications_summary(
    request: ApplicationsDataRequest,
    db: DbSession,
) -> dict[str, object]:
    return applications_summary(db, request)


@router.post("/applications/list", response_model=ApplicationsListResponse)
def get_dashboard_applications_list(
    request: ApplicationsDataRequest,
    db: DbSession,
) -> dict[str, object]:
    try:
        return applications_list(db, request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/applications/charts", response_model=ApplicationsChartsResponse)
def get_dashboard_applications_charts(
    request: ApplicationsDataRequest,
    db: DbSession,
) -> dict[str, object]:
    return applications_charts(db, request)


@router.post(
    "/volumetrics/filter-values",
    response_model=VolumetricsFilterValuesResponse,
)
def get_dashboard_volumetrics_filter_values(
    request: VolumetricsRequest,
    db: DbSession,
) -> dict[str, object]:
    try:
        return volumetrics_filter_value_counts(db, request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/volumetrics/summary", response_model=VolumetricsSummaryResponse)
def get_dashboard_volumetrics_summary(
    request: VolumetricsRequest,
    db: DbSession,
) -> dict[str, object]:
    try:
        return volumetrics_summary(db, request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/volumetrics/created-resolved-backlog",
    response_model=VolumetricsCreatedResolvedBacklogResponse,
)
def get_dashboard_volumetrics_created_resolved_backlog(
    request: VolumetricsRequest,
    db: DbSession,
) -> dict[str, object]:
    try:
        return volumetrics_created_resolved_backlog(db, request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/volumetrics/created-resolved-canceled",
    response_model=VolumetricsCreatedResolvedCanceledResponse,
)
def get_dashboard_volumetrics_created_resolved_canceled(
    request: VolumetricsRequest,
    db: DbSession,
) -> dict[str, object]:
    try:
        return volumetrics_created_resolved_cancelled(db, request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/volumetrics/backlog", response_model=VolumetricsBacklogResponse)
def get_dashboard_volumetrics_backlog(
    request: VolumetricsRequest,
    db: DbSession,
) -> dict[str, object]:
    try:
        return volumetrics_backlog(db, request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/volumetrics/created-pattern",
    response_model=VolumetricsCreatedPatternResponse,
)
def get_dashboard_volumetrics_created_pattern(
    request: VolumetricsCreatedPatternRequest,
    db: DbSession,
) -> dict[str, object]:
    try:
        return volumetrics_created_pattern(db, request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get(
    "/trends/created-resolved-open",
    response_model=list[CreatedResolvedOpenRow],
)
def get_created_resolved_open_trend(
    filters: DashboardFilterDependency,
    db: DbSession,
) -> list[dict[str, object]]:
    return created_resolved_open_trend(db, filters)


@router.get("/trends/mttr", response_model=list[MttrTrendRow])
def get_mttr_trend(
    filters: DashboardFilterDependency,
    db: DbSession,
) -> list[dict[str, object]]:
    return mttr_trend(db, filters)


@router.get("/trends/sla", response_model=list[SlaTrendRow])
def get_sla_trend(
    filters: DashboardFilterDependency,
    db: DbSession,
) -> list[dict[str, object]]:
    return sla_trend(db, filters)


@router.get("/trends/incident-sla", response_model=list[IncidentSlaTrendRow])
def get_incident_sla_trend(
    filters: DashboardFilterDependency,
    db: DbSession,
) -> list[dict[str, object]]:
    return incident_sla_trend(db, filters)


@router.get(
    "/breakdowns/incident-sla-names",
    response_model=IncidentSlaNameBreakdownResponse,
)
def get_incident_sla_name_breakdown(
    filters: DashboardFilterDependency,
    db: DbSession,
    name_type: Annotated[str, Query(pattern="^(RESPONSE|RESOLUTION|BOTH)$")] = "BOTH",
) -> dict[str, list[dict[str, object]]]:
    return incident_sla_name_breakdown(db, filters, name_type)


@router.get("/summary/incident-sla", response_model=IncidentSlaSummaryResponse)
def get_incident_sla_summary(
    filters: DashboardFilterDependency,
    db: DbSession,
) -> dict[str, object]:
    return incident_sla_summary(db, filters)


@router.get("/trends/reopen-count", response_model=list[ReopenTrendRow])
def get_reopen_trend(
    filters: DashboardFilterDependency,
    db: DbSession,
) -> list[dict[str, object]]:
    return reopen_trend(db, filters)


@router.get("/trends/reassignment-count", response_model=list[ReassignmentTrendRow])
def get_reassignment_trend(
    filters: DashboardFilterDependency,
    db: DbSession,
) -> list[dict[str, object]]:
    return reassignment_trend(db, filters)


@router.get("/trends/creation-source", response_model=list[CreationSourceTrendRow])
def get_creation_source_trend(
    filters: DashboardFilterDependency,
    db: DbSession,
) -> list[dict[str, object]]:
    return creation_source_trend(db, filters)


@router.get(
    "/breakdowns/technical-functional",
    response_model=TechnicalFunctionalBreakdownResponse,
)
def get_technical_functional_breakdown(
    filters: DashboardFilterDependency,
    db: DbSession,
) -> dict[str, int]:
    return technical_functional_breakdown(db, filters)


@router.get("/filter-values", response_model=FilterValuesResponse)
def get_filter_values(
    filters: DashboardFilterDependency,
    db: DbSession,
) -> dict[str, list[str]]:
    return filter_values(db, filters)
