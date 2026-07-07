from __future__ import annotations

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.dashboard import (
    ApplicationsAssignmentGroupMappingRequest,
    ApplicationsAssignmentGroupMappingResponse,
    ApplicationsChartsResponse,
    ApplicationsDataRequest,
    ApplicationsFilterValueCountsResponse,
    ApplicationsFilterValuesRequest,
    ApplicationsFilterValuesResponse,
    ApplicationsLifecyclePlanningRequest,
    ApplicationsLifecyclePlanningResponse,
    ApplicationsListResponse,
    ApplicationsSummaryResponse,
    ApplicationsTopActiveUsersRequest,
    ApplicationsTopActiveUsersResponse,
    CreatedResolvedOpenRow,
    CreationSourceTrendRow,
    DashboardCommentaryBatchRequest,
    DashboardCommentaryBatchResponse,
    DashboardCommentaryContext,
    DashboardCommentaryContextResponse,
    DashboardCommentaryUpsertRequest,
    DashboardFilterCacheRefreshRequest,
    DashboardFilterCacheRefreshResponse,
    DashboardFilterCacheStatusResponse,
    DashboardFilterCatalogResponse,
    DashboardFilterCountsRequest,
    DashboardFilterCountsResponse,
    DashboardOverviewResponse,
    FilterValuesResponse,
    IncidentSlaNameBreakdownResponse,
    IncidentSlaSummaryResponse,
    IncidentSlaTrendRow,
    MttrTrendRow,
    OfflineDashboardExportRequest,
    PowerPointDashboardExportRequest,
    ReassignmentTrendRow,
    ReopenTrendRow,
    SlaTrendRow,
    TechnicalFunctionalBreakdownResponse,
    VolumetricsAssignmentGroupRequest,
    VolumetricsAssignmentGroupResponse,
    VolumetricsBacklogResponse,
    VolumetricsCreatedPatternRequest,
    VolumetricsCreatedPatternResponse,
    VolumetricsCreatedResolvedBacklogResponse,
    VolumetricsCreatedResolvedCanceledResponse,
    VolumetricsDataRangeResponse,
    VolumetricsDetailedArchitectureInstallSplitsResponse,
    VolumetricsDistributionSplitsResponse,
    VolumetricsFilterValuesResponse,
    VolumetricsHourlyCreatedResolvedRequest,
    VolumetricsHourlyCreatedResolvedResponse,
    VolumetricsIncidentBatchTrendResponse,
    VolumetricsKpiDurationBucketsResponse,
    VolumetricsKpiMttrTrendsResponse,
    VolumetricsOpenTicketAgingTrendResponse,
    VolumetricsPriorityDistributionResponse,
    VolumetricsProblemManagementTrendResponse,
    VolumetricsReassignmentHopsTrendResponse,
    VolumetricsRequest,
    VolumetricsScTaskCatalogItemProportionResponse,
    VolumetricsSlaTrendsResponse,
    VolumetricsSummaryResponse,
    VolumetricsTicketsPerUserResponse,
    VolumetricsTopApplicationsRequest,
    VolumetricsTopApplicationsResponse,
    VolumetricsTopIncidentBatchApplicationsResponse,
)
from app.services.dashboard import (
    DashboardFilters,
    DateFilterBasis,
    TimeGrain,
    applications_assignment_group_mapping,
    applications_charts,
    applications_filter_value_counts,
    applications_filter_values,
    applications_lifecycle_planning,
    applications_list,
    applications_summary,
    applications_top_active_users,
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
    volumetrics_assignment_group_volumetrics,
    volumetrics_backlog,
    volumetrics_created_pattern,
    volumetrics_created_resolved_backlog,
    volumetrics_created_resolved_cancelled,
    volumetrics_data_range,
    volumetrics_detailed_architecture_install_splits,
    volumetrics_distribution_splits,
    volumetrics_filter_value_counts,
    volumetrics_hourly_created_resolved,
    volumetrics_incident_batch_trend,
    volumetrics_kpi_duration_buckets,
    volumetrics_kpi_mttr_trends,
    volumetrics_kpi_open_ticket_aging_trend,
    volumetrics_kpi_problem_management_trend,
    volumetrics_kpi_reassignment_hops_trend,
    volumetrics_priority_distribution,
    volumetrics_sc_task_catalog_item_proportion,
    volumetrics_sla_trends,
    volumetrics_summary,
    volumetrics_tickets_per_user,
    volumetrics_top_applications,
    volumetrics_top_incident_batch_applications,
)
from app.services.dashboard_commentary import (
    batch_commentaries,
    get_commentary_by_context,
    upsert_commentary,
)
from app.services.dashboard_filter_cache import (
    dynamic_filter_counts,
    filter_cache_status_items,
    filter_catalog,
    refresh_filter_cache,
)
from app.services.offline_dashboard_export import build_offline_dashboard_export
from app.services.powerpoint_export import build_powerpoint_export

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


@router.get("/filter-cache/status", response_model=DashboardFilterCacheStatusResponse)
def get_dashboard_filter_cache_status(
    customer_id: Annotated[UUID, Query(...)],
    project_id: Annotated[UUID, Query(...)],
    db: DbSession,
    dashboard_area: Annotated[str | None, Query()] = None,
) -> dict[str, object]:
    try:
        return {
            "items": filter_cache_status_items(
                db,
                customer_id,
                project_id,
                dashboard_area,
            ),
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/filter-cache/refresh", response_model=DashboardFilterCacheRefreshResponse)
def post_dashboard_filter_cache_refresh(
    request: DashboardFilterCacheRefreshRequest,
    db: DbSession,
) -> dict[str, object]:
    try:
        result = refresh_filter_cache(db, request.project_id, request.dashboard_area)
        db.commit()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        db.commit()
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {
        "status": result.status,
        "dashboard_area": result.dashboard_area,
        "data_version": result.data_version,
        "facts_count": result.facts_count,
        "catalog_count": result.catalog_count,
        "duration_ms": result.duration_ms,
    }


@router.get("/filter-catalog", response_model=DashboardFilterCatalogResponse)
def get_dashboard_filter_catalog(
    customer_id: Annotated[UUID, Query(...)],
    project_id: Annotated[UUID, Query(...)],
    dashboard_area: Annotated[str, Query(...)],
    db: DbSession,
) -> dict[str, object]:
    try:
        return filter_catalog(db, customer_id, project_id, dashboard_area)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/filter-counts", response_model=DashboardFilterCountsResponse)
def post_dashboard_filter_counts(
    request: DashboardFilterCountsRequest,
    db: DbSession,
) -> dict[str, object]:
    date_range = request.date_range
    try:
        return dynamic_filter_counts(
            db,
            request.customer_id,
            request.project_id,
            request.dashboard_area,
            request.selected_filters,
            scope=request.scope,
            ticket_type=request.ticket_type,
            from_datetime=date_range.from_date if date_range else None,
            to_datetime=date_range.to_date if date_range else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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
    "/applications/lifecycle-planning",
    response_model=ApplicationsLifecyclePlanningResponse,
)
def get_dashboard_applications_lifecycle_planning(
    request: ApplicationsLifecyclePlanningRequest,
    db: DbSession,
) -> dict[str, object]:
    return applications_lifecycle_planning(db, request)


@router.post("/applications/top-active-users", response_model=ApplicationsTopActiveUsersResponse)
def get_dashboard_applications_top_active_users(
    request: ApplicationsTopActiveUsersRequest,
    db: DbSession,
) -> dict[str, object]:
    try:
        return applications_top_active_users(db, request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/applications/assignment-group-mapping",
    response_model=ApplicationsAssignmentGroupMappingResponse,
)
def get_dashboard_applications_assignment_group_mapping(
    request: ApplicationsAssignmentGroupMappingRequest,
    db: DbSession,
) -> dict[str, object]:
    try:
        return applications_assignment_group_mapping(db, request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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


@router.post(
    "/volumetrics/assignment-group-volumetrics",
    response_model=VolumetricsAssignmentGroupResponse,
)
def get_dashboard_volumetrics_assignment_group_volumetrics(
    request: VolumetricsAssignmentGroupRequest,
    db: DbSession,
) -> dict[str, object]:
    try:
        return volumetrics_assignment_group_volumetrics(db, request)
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


@router.get(
    "/volumetrics/data-range",
    response_model=VolumetricsDataRangeResponse,
)
def get_dashboard_volumetrics_data_range(
    project_id: Annotated[UUID, Query(...)],
    db: DbSession,
) -> dict[str, object]:
    return volumetrics_data_range(db, project_id)


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


@router.post(
    "/volumetrics/hourly-created-resolved",
    response_model=VolumetricsHourlyCreatedResolvedResponse,
)
def get_dashboard_volumetrics_hourly_created_resolved(
    request: VolumetricsHourlyCreatedResolvedRequest,
    db: DbSession,
) -> dict[str, object]:
    try:
        return volumetrics_hourly_created_resolved(db, request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/volumetrics/priority-distribution",
    response_model=VolumetricsPriorityDistributionResponse,
)
def get_dashboard_volumetrics_priority_distribution(
    request: VolumetricsRequest,
    db: DbSession,
) -> dict[str, object]:
    try:
        return volumetrics_priority_distribution(db, request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/volumetrics/sla-trends",
    response_model=VolumetricsSlaTrendsResponse,
)
def get_dashboard_volumetrics_sla_trends(
    request: VolumetricsRequest,
    db: DbSession,
) -> dict[str, object]:
    try:
        return volumetrics_sla_trends(db, request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/volumetrics/top-applications",
    response_model=VolumetricsTopApplicationsResponse,
)
def get_dashboard_volumetrics_top_applications(
    request: VolumetricsTopApplicationsRequest,
    db: DbSession,
) -> dict[str, object]:
    try:
        return volumetrics_top_applications(db, request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/volumetrics/incident-batch-trend",
    response_model=VolumetricsIncidentBatchTrendResponse,
)
def get_dashboard_volumetrics_incident_batch_trend(
    request: VolumetricsRequest,
    db: DbSession,
) -> dict[str, object]:
    try:
        return volumetrics_incident_batch_trend(db, request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/volumetrics/top-incident-batch-applications",
    response_model=VolumetricsTopIncidentBatchApplicationsResponse,
)
def get_dashboard_volumetrics_top_incident_batch_applications(
    request: VolumetricsTopApplicationsRequest,
    db: DbSession,
) -> dict[str, object]:
    try:
        return volumetrics_top_incident_batch_applications(db, request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/volumetrics/detailed-architecture-install-splits",
    response_model=VolumetricsDetailedArchitectureInstallSplitsResponse,
)
def get_dashboard_volumetrics_detailed_architecture_install_splits(
    request: VolumetricsRequest,
    db: DbSession,
) -> dict[str, object]:
    try:
        return volumetrics_detailed_architecture_install_splits(db, request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/volumetrics/tickets-per-user",
    response_model=VolumetricsTicketsPerUserResponse,
)
def get_dashboard_volumetrics_tickets_per_user(
    request: VolumetricsTopApplicationsRequest,
    db: DbSession,
) -> dict[str, object]:
    try:
        return volumetrics_tickets_per_user(db, request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/volumetrics/distribution-splits",
    response_model=VolumetricsDistributionSplitsResponse,
)
def get_dashboard_volumetrics_distribution_splits(
    request: VolumetricsRequest,
    db: DbSession,
) -> dict[str, object]:
    try:
        return volumetrics_distribution_splits(db, request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/volumetrics/sc-task-catalog-item-proportion",
    response_model=VolumetricsScTaskCatalogItemProportionResponse,
)
def get_dashboard_volumetrics_sc_task_catalog_item_proportion(
    request: VolumetricsRequest,
    db: DbSession,
) -> dict[str, object]:
    try:
        return volumetrics_sc_task_catalog_item_proportion(db, request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/volumetrics/kpi-mttr-trends",
    response_model=VolumetricsKpiMttrTrendsResponse,
)
def get_dashboard_volumetrics_kpi_mttr_trends(
    request: VolumetricsRequest,
    db: DbSession,
) -> dict[str, object]:
    try:
        return volumetrics_kpi_mttr_trends(db, request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/volumetrics/kpi-duration-buckets",
    response_model=VolumetricsKpiDurationBucketsResponse,
)
def get_dashboard_volumetrics_kpi_duration_buckets(
    request: VolumetricsRequest,
    db: DbSession,
) -> dict[str, object]:
    try:
        return volumetrics_kpi_duration_buckets(db, request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/volumetrics/kpi-open-ticket-aging-trend",
    response_model=VolumetricsOpenTicketAgingTrendResponse,
)
def get_dashboard_volumetrics_kpi_open_ticket_aging_trend(
    request: VolumetricsRequest,
    db: DbSession,
) -> dict[str, object]:
    try:
        return volumetrics_kpi_open_ticket_aging_trend(db, request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/volumetrics/kpi-reassignment-hops-trend",
    response_model=VolumetricsReassignmentHopsTrendResponse,
)
def get_dashboard_volumetrics_kpi_reassignment_hops_trend(
    request: VolumetricsRequest,
    db: DbSession,
) -> dict[str, object]:
    try:
        return volumetrics_kpi_reassignment_hops_trend(db, request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/volumetrics/kpi-problem-management-trend",
    response_model=VolumetricsProblemManagementTrendResponse,
)
def get_dashboard_volumetrics_kpi_problem_management_trend(
    request: VolumetricsRequest,
    db: DbSession,
) -> dict[str, object]:
    try:
        return volumetrics_kpi_problem_management_trend(db, request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/offline-export")
def download_offline_dashboard(
    request: OfflineDashboardExportRequest,
    db: DbSession,
) -> Response:
    try:
        document, filename = build_offline_dashboard_export(db, request.project_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(
        content=document,
        media_type="text/html; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/powerpoint-export")
def download_powerpoint_dashboard(
    request: PowerPointDashboardExportRequest,
    db: DbSession,
) -> Response:
    try:
        document, filename = build_powerpoint_export(
            db,
            request.project_id,
            scope_filter=request.scope,
            ticket_type_filter=request.ticket_type,
            functional_track_ams_owner=request.functional_track_ams_owner,
            include_commentary=request.include_commentary,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(
        content=document,
        media_type=(
            "application/vnd.openxmlformats-officedocument.presentationml.presentation"
        ),
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post(
    "/commentaries/context",
    response_model=DashboardCommentaryContextResponse,
)
def get_dashboard_commentary_context(
    request: DashboardCommentaryContext,
    db: DbSession,
) -> dict[str, object]:
    return get_commentary_by_context(db, request)


@router.post(
    "/commentaries/batch",
    response_model=DashboardCommentaryBatchResponse,
)
def get_dashboard_commentaries_batch(
    request: DashboardCommentaryBatchRequest,
    db: DbSession,
) -> dict[str, object]:
    return batch_commentaries(db, request)


@router.post(
    "/commentaries/upsert",
    response_model=DashboardCommentaryContextResponse,
)
def upsert_dashboard_commentary(
    request: DashboardCommentaryUpsertRequest,
    db: DbSession,
) -> dict[str, object]:
    try:
        return upsert_commentary(db, request)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


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
