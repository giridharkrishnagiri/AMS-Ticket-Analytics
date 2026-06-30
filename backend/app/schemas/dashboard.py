from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class PeriodMetricRow(BaseModel):
    period_start: datetime
    period_end: datetime
    period_label: str


class CreatedResolvedOpenRow(PeriodMetricRow):
    created_count: int
    resolved_count: int
    open_end_count: int


class MttrTrendRow(PeriodMetricRow):
    completed_ticket_count: int
    mttr_actual_days: float | None
    mttr_business_days: float | None


class SlaTrendRow(PeriodMetricRow):
    total_tickets_with_sla: int
    sla_met_count: int
    sla_breached_count: int
    sla_unknown_count: int
    sla_met_percentage: float | None
    sla_breached_percentage: float | None


class IncidentSlaTrendRow(PeriodMetricRow):
    period: str
    incident_count: int
    response_sla_applicable_count: int
    response_sla_met_count: int
    response_sla_breached_count: int
    response_sla_adherence_pct: float | None
    response_sla_breach_pct: float | None
    response_sla_avg_business_elapsed_seconds: float | None
    response_sla_avg_business_elapsed_hours: float | None
    resolution_sla_applicable_count: int
    resolution_sla_met_count: int
    resolution_sla_breached_count: int
    resolution_sla_adherence_pct: float | None
    resolution_sla_breach_pct: float | None
    resolution_sla_avg_business_elapsed_seconds: float | None
    resolution_sla_avg_business_elapsed_hours: float | None


class IncidentSlaSummaryResponse(BaseModel):
    incident_count: int
    response_sla_applicable_count: int
    response_sla_met_count: int
    response_sla_breached_count: int
    response_sla_adherence_pct: float | None
    response_sla_breach_pct: float | None
    response_sla_avg_business_elapsed_hours: float | None
    resolution_sla_applicable_count: int
    resolution_sla_met_count: int
    resolution_sla_breached_count: int
    resolution_sla_adherence_pct: float | None
    resolution_sla_breach_pct: float | None
    resolution_sla_avg_business_elapsed_hours: float | None
    response_accenture_count: int
    response_default_count: int
    resolution_accenture_count: int
    resolution_default_count: int


class IncidentSlaNameBreakdownItem(BaseModel):
    sla_name: str
    ticket_count: int
    met_count: int
    breached_count: int
    adherence_pct: float | None
    breach_pct: float | None
    avg_business_elapsed_hours: float | None


class IncidentSlaNameBreakdownResponse(BaseModel):
    response_sla_names: list[IncidentSlaNameBreakdownItem]
    resolution_sla_names: list[IncidentSlaNameBreakdownItem]


class ReopenTrendRow(PeriodMetricRow):
    total_tickets: int
    reopened_ticket_count: int
    total_reopen_count: int
    average_reopen_count: float | None


class ReassignmentTrendRow(PeriodMetricRow):
    total_tickets: int
    tickets_with_more_than_2_reassignments: int
    total_reassignment_count: int
    average_reassignment_count: float | None


class CreationSourceTrendRow(PeriodMetricRow):
    user_created_count: int
    system_created_count: int
    unknown_count: int


class TechnicalFunctionalBreakdownResponse(BaseModel):
    technical_count: int
    functional_count: int
    unknown_count: int
    not_applicable_count: int


class DashboardOverviewInventorySummary(BaseModel):
    total_applications: int
    functional_track_count: int
    ams_owner_count: int
    supported_vendor_count: int
    assignment_group_count: int
    application_owner_count: int
    very_critical_application_count: int
    critical_application_count: int


class DashboardOverviewTicketSummary(BaseModel):
    total_in_scope_tickets: int
    incident_count: int
    sc_task_count: int
    completion_date_min: datetime | None
    completion_date_max: datetime | None
    applications_80pct_monthly_volume_count: int


class DashboardOverviewIngestedVolumeSummary(BaseModel):
    total_rows: int
    incident_rows: int
    sc_task_rows: int
    incident_sla_rows: int


class DashboardOverviewResponse(BaseModel):
    project_id: UUID
    customer_name: str
    project_name: str
    application_inventory: DashboardOverviewInventorySummary
    ingested_volume: DashboardOverviewIngestedVolumeSummary
    tickets: DashboardOverviewTicketSummary


class FilterValuesResponse(BaseModel):
    ticket_types: list[str]
    priorities: list[str]
    states: list[str]
    assignment_groups: list[str]
    applications: list[str]
    customers: list[str]
    towers: list[str]
    clusters: list[str]
    application_groups: list[str]
    application_names: list[str]
    month_keys: list[str]
    response_sla_names: list[str]
    resolution_sla_names: list[str]
    functional_tracks: list[str]
    ams_owners: list[str]
    supported_by_vendors: list[str]
    support_leads: list[str]
    application_owners: list[str]
    business_service_ci_names: list[str]
    parent_application_names: list[str]


class ApplicationCombinedFilterValue(BaseModel):
    label: str
    left_value: str
    right_value: str


class ApplicationFilterCountValue(BaseModel):
    label: str
    value: str
    count: int


class DashboardFilterCatalogValue(BaseModel):
    value: str
    label: str
    baseline_count: int
    sort_order: int


class DashboardFilterCatalogResponse(BaseModel):
    dashboard_area: str
    status: str
    data_version: str | None
    filters: dict[str, list[DashboardFilterCatalogValue]]
    warnings: list[str] = Field(default_factory=list)


class DashboardFilterCacheStatusItem(BaseModel):
    dashboard_area: str
    status: str
    data_version: str | None
    last_success_at: datetime | None
    is_stale: bool
    error_message: str | None


class DashboardFilterCacheStatusResponse(BaseModel):
    items: list[DashboardFilterCacheStatusItem]


class DashboardFilterCacheRefreshRequest(BaseModel):
    customer_id: UUID
    project_id: UUID
    dashboard_area: str = "all"


class DashboardFilterCacheRefreshResponse(BaseModel):
    status: str
    dashboard_area: str
    data_version: str
    facts_count: int
    catalog_count: int
    duration_ms: int


class DashboardFilterCountsDateRange(BaseModel):
    from_date: datetime | None = None
    to_date: datetime | None = None


class DashboardFilterCountsRequest(BaseModel):
    customer_id: UUID
    project_id: UUID
    dashboard_area: str
    selected_filters: dict[str, list[str]] = Field(default_factory=dict)
    date_range: DashboardFilterCountsDateRange | None = None
    ticket_type: str = "all"
    scope: str = "in_scope"


class DashboardFilterCountsResponse(BaseModel):
    dashboard_area: str
    status: str
    data_version: str | None
    counts: dict[str, dict[str, int]]
    duration_ms: int
    warnings: list[str] = Field(default_factory=list)


class ApplicationCombinedFilterCountValue(ApplicationCombinedFilterValue):
    count: int


class ApplicationsFilterValuesResponse(BaseModel):
    functional_track_ams_owner: list[ApplicationCombinedFilterValue]
    assignment_group_owner: list[ApplicationCombinedFilterValue]
    parent_application_name: list[str]
    application_owner: list[str]
    supported_by_vendor: list[str]
    sap_non_sap: list[str]
    architecture_type: list[str]
    application_type: list[str]
    business_critical: list[str]
    install_status: list[str]
    install_type: list[str]
    hosting_env: list[str]
    lifecycle_status_stage: list[ApplicationCombinedFilterValue]


class ApplicationsFilters(BaseModel):
    functional_track_ams_owner: list[str] = Field(default_factory=list)
    assignment_group_owner: list[str] = Field(default_factory=list)
    parent_application_name: list[str] = Field(default_factory=list)
    application_owner: list[str] = Field(default_factory=list)
    supported_by_vendor: list[str] = Field(default_factory=list)
    sap_non_sap: list[str] = Field(default_factory=list)
    architecture_type: list[str] = Field(default_factory=list)
    application_type: list[str] = Field(default_factory=list)
    business_critical: list[str] = Field(default_factory=list)
    install_status: list[str] = Field(default_factory=list)
    install_type: list[str] = Field(default_factory=list)
    hosting_env: list[str] = Field(default_factory=list)
    lifecycle_status_stage: list[str] = Field(default_factory=list)


class ApplicationsFilterValuesRequest(BaseModel):
    project_id: UUID
    filters: ApplicationsFilters = Field(default_factory=ApplicationsFilters)


class ApplicationsFilterValueCountsResponse(BaseModel):
    functional_track_ams_owner: list[ApplicationCombinedFilterCountValue]
    assignment_group_owner: list[ApplicationCombinedFilterCountValue]
    parent_application_name: list[ApplicationFilterCountValue]
    application_owner: list[ApplicationFilterCountValue]
    supported_by_vendor: list[ApplicationFilterCountValue]
    sap_non_sap: list[ApplicationFilterCountValue]
    architecture_type: list[ApplicationFilterCountValue]
    application_type: list[ApplicationFilterCountValue]
    business_critical: list[ApplicationFilterCountValue]
    install_status: list[ApplicationFilterCountValue]
    install_type: list[ApplicationFilterCountValue]
    hosting_env: list[ApplicationFilterCountValue]
    lifecycle_status_stage: list[ApplicationCombinedFilterCountValue]


class ApplicationsSort(BaseModel):
    column: str = "business_service_ci_name"
    direction: str = "asc"


class ApplicationsDataRequest(BaseModel):
    project_id: UUID
    filters: ApplicationsFilters = Field(default_factory=ApplicationsFilters)
    sort: ApplicationsSort = Field(default_factory=ApplicationsSort)
    limit: int = Field(default=500, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)


class ApplicationsTopActiveUsersRequest(ApplicationsDataRequest):
    top_n: int = Field(default=10, ge=10, le=20)


class ApplicationsLifecyclePlanningRequest(ApplicationsDataRequest):
    selected_plan: str = "Invest"


class ApplicationsSummaryResponse(BaseModel):
    applications: int
    functional_groups: int
    assignment_groups: int
    parent_business_apps: int
    business_applications: int
    technical_applications: int
    very_critical_applications: int
    critical_applications: int
    show_functional_groups: bool
    show_assignment_groups: bool
    show_parent_business_apps: bool


class ApplicationsListRow(BaseModel):
    business_service_ci_name: str
    parent_application_name: str
    assignment_group: str
    sap_non_sap: str
    assignment_group_owner: str
    application_owner: str
    support_lead: str
    functional_track: str
    ams_owner: str
    supported_by_vendor: str
    hosting_env: str
    global_application: str
    lifecycle_stage_status: str
    lifecycle_current: str
    lifecycle_1_to_3_years: str
    lifecycle_3_to_5_years: str
    active_users: int | None
    avg_monthly_ticket_volume_6m: float | None
    tickets_per_user_per_month: float | None
    app_family: str
    biz_process: str
    app_category: str
    org_unit_level_1: str
    org_unit_level_2: str
    org_unit_level_3: str
    app_type: str
    architecture_type: str
    biz_capabilities: str
    business_reason_for_maintain_applications: str
    business_units: str
    biz_criticality: str
    biz_owner: str
    company: str
    install_status: str
    install_type: str
    lifecycle_status: str
    operating_system: str
    sox_audited: str
    sox_scope: str
    strategic: str


class ApplicationsListResponse(BaseModel):
    total: int
    rows: list[ApplicationsListRow]


class ApplicationsChartDatum(BaseModel):
    label: str
    count: int


class ApplicationsCriticalityHostingPivotRow(BaseModel):
    business_criticality: str
    counts: dict[str, int]
    total: int


class ApplicationsCriticalityHostingPivot(BaseModel):
    rows: list[str]
    columns: list[str]
    values: list[ApplicationsCriticalityHostingPivotRow]
    column_totals: dict[str, int]
    grand_total: int


class ApplicationsTopActiveUsersPoint(BaseModel):
    application_name: str
    parent_application_name: str
    active_users: int


class ApplicationsTopActiveUsersResponse(BaseModel):
    top_n: int
    duplicate_parent_active_user_count: int = 0
    points: list[ApplicationsTopActiveUsersPoint]


class ApplicationsChartsResponse(BaseModel):
    lifecycle_stage: list[ApplicationsChartDatum]
    architecture_type: list[ApplicationsChartDatum]
    install_type: list[ApplicationsChartDatum]
    hosting_env: list[ApplicationsChartDatum]
    strategic: list[ApplicationsChartDatum]
    criticality_hosting_pivot: ApplicationsCriticalityHostingPivot
    global_local_applications: list[ApplicationsChartDatum]


class ApplicationsLifecyclePlanningMatrixRow(BaseModel):
    plan: str
    counts: dict[str, int]


class ApplicationsLifecyclePlanningMatrix(BaseModel):
    plans: list[str]
    horizons: list[str]
    rows: list[ApplicationsLifecyclePlanningMatrixRow]
    in_use_application_count: int


class ApplicationsLifecyclePlanningChartDatum(BaseModel):
    horizon: str
    count: int


class ApplicationsLifecyclePlanningApplication(BaseModel):
    business_service_ci_name: str
    parent_business_application: str
    functional_track: str
    ams_owner: str
    application_owner: str
    supported_by_vendor: str
    install_type: str
    business_criticality: str
    architecture_type: str
    application_type: str
    hosting_env: str
    global_application: str
    active_users: int | None
    lifecycle_current: str
    lifecycle_1_to_3_years: str
    lifecycle_3_to_5_years: str
    selected_plan_horizons: list[str]


class ApplicationsLifecyclePlanningSelectedPlan(BaseModel):
    plan: str
    chart: list[ApplicationsLifecyclePlanningChartDatum]
    applications: list[ApplicationsLifecyclePlanningApplication]
    application_count: int


class ApplicationsLifecyclePlanningResponse(BaseModel):
    matrix: ApplicationsLifecyclePlanningMatrix
    selected_plan: ApplicationsLifecyclePlanningSelectedPlan


class VolumetricsFilters(BaseModel):
    functional_track_ams_owner: list[str] = Field(default_factory=list)
    assignment_group_support_lead: list[str] = Field(default_factory=list)
    parent_application_name: list[str] = Field(default_factory=list)
    application_owner: list[str] = Field(default_factory=list)
    supported_by_vendor: list[str] = Field(default_factory=list)
    sap_non_sap: list[str] = Field(default_factory=list)
    business_critical: list[str] = Field(default_factory=list)


class VolumetricsRequest(BaseModel):
    project_id: UUID
    scope: str = "in_scope"
    ticket_type: str = "all"
    time_grain: str = "monthly"
    agreement_mode: str = "sla"
    start_datetime: datetime
    end_datetime: datetime
    filters: VolumetricsFilters = Field(default_factory=VolumetricsFilters)


class VolumetricsFilterValuesResponse(BaseModel):
    scope: list[ApplicationFilterCountValue]
    ticket_type: list[ApplicationFilterCountValue]
    functional_track_ams_owner: list[ApplicationCombinedFilterCountValue]
    assignment_group_support_lead: list[ApplicationCombinedFilterCountValue]
    parent_application_name: list[ApplicationFilterCountValue]
    application_owner: list[ApplicationFilterCountValue]
    supported_by_vendor: list[ApplicationFilterCountValue]
    sap_non_sap: list[ApplicationFilterCountValue]
    business_critical: list[ApplicationFilterCountValue]
    source: str = "dashboard_filter_facts"
    duration_ms: int | None = None


class VolumetricsSummaryMetric(BaseModel):
    total: int
    average_per_period: float | None


class VolumetricsSlaMetric(BaseModel):
    average_adherence_pct: float | None
    applicable_count: int
    met_count: int


class VolumetricsCancelledMetric(VolumetricsSummaryMetric):
    cancelled_pct_of_resolved_cancelled: float | None


class VolumetricsSummaryResponse(BaseModel):
    period_count: int
    created: VolumetricsSummaryMetric
    resolved_closed: VolumetricsSummaryMetric
    cancelled: VolumetricsCancelledMetric
    response_sla: VolumetricsSlaMetric
    resolution_sla: VolumetricsSlaMetric


class VolumetricsDataRangeResponse(BaseModel):
    completion_date_min: datetime | None
    completion_date_max: datetime | None


class VolumetricsCreatedResolvedBacklogRow(BaseModel):
    period_start: datetime
    period_end: datetime
    period_label: str
    created_count: int
    resolved_closed_count: int
    backlog_open_count: int
    average_backlog_open: float | None


class VolumetricsCreatedResolvedBacklogResponse(BaseModel):
    average_backlog_open: float | None
    rows: list[VolumetricsCreatedResolvedBacklogRow]


class VolumetricsCreatedResolvedCanceledRow(PeriodMetricRow):
    created_count: int
    resolved_closed_count: int
    canceled_closed_incomplete_count: int


class VolumetricsCreatedResolvedCanceledResponse(BaseModel):
    time_grain: str
    points: list[VolumetricsCreatedResolvedCanceledRow]


class VolumetricsBacklogRow(PeriodMetricRow):
    backlog_open: int


class VolumetricsBacklogResponse(BaseModel):
    time_grain: str
    average_backlog: float | None
    points: list[VolumetricsBacklogRow]


class VolumetricsCreatedPatternRequest(VolumetricsRequest):
    pattern_type: str = "day_of_month"


class OfflineDashboardExportRequest(BaseModel):
    project_id: UUID
    format: str = Field(default="html", pattern="^html$")


class PowerPointDashboardExportRequest(BaseModel):
    project_id: UUID
    scope: str = "in_scope"
    ticket_type: str = "all"
    functional_track_ams_owner: str | list[str] = "all"
    include_commentary: bool = True


class DashboardCommentaryContext(BaseModel):
    project_id: UUID
    dashboard_area: str
    tab_name: str
    sub_tab_name: str | None = None
    section_key: str
    chart_key: str | None = None
    scope_filter: str = "all"
    ticket_type_filter: str = "all"
    functional_track_ams_owner: str = "all"


class DashboardCommentaryRecord(DashboardCommentaryContext):
    id: UUID
    commentary_html: str | None
    commentary_text: str | None
    updated_at: datetime
    updated_by: str | None = None


class DashboardCommentaryContextResponse(BaseModel):
    commentary: DashboardCommentaryRecord | None


class DashboardCommentaryBatchRequest(BaseModel):
    project_id: UUID
    dashboard_area: str
    tab_name: str
    sub_tab_name: str | None = None
    scope_filter: str = "all"
    ticket_type_filter: str = "all"
    functional_track_ams_owner: str = "all"


class DashboardCommentaryBatchResponse(BaseModel):
    commentaries: list[DashboardCommentaryRecord]


class DashboardCommentaryUpsertRequest(DashboardCommentaryContext):
    commentary_html: str | None = None
    commentary_text: str | None = None
    updated_by: str | None = None


class VolumetricsCreatedPatternPoint(BaseModel):
    label: str
    average_created: float
    total_created: int
    denominator: int


class VolumetricsCreatedPatternResponse(BaseModel):
    pattern_type: str
    points: list[VolumetricsCreatedPatternPoint]


class VolumetricsHourlyCreatedResolvedRequest(VolumetricsRequest):
    day_type: str = "weekdays"


class VolumetricsHourlyCreatedResolvedPoint(BaseModel):
    hour: str
    average_created: float
    average_resolved_closed: float
    created_label: int
    resolved_closed_label: int


class VolumetricsHourlyCreatedResolvedResponse(BaseModel):
    day_type: str
    denominator_days: int
    points: list[VolumetricsHourlyCreatedResolvedPoint]


class VolumetricsPriorityDistributionPoint(BaseModel):
    period_key: str
    period_label: str
    values: dict[str, int]
    percentages: dict[str, float | None]
    total: int


class VolumetricsPriorityDistributionResponse(BaseModel):
    time_grain: str
    priorities: list[str]
    points: list[VolumetricsPriorityDistributionPoint]


class VolumetricsSlaTrendRow(BaseModel):
    period_key: str
    period_label: str
    total_closed_ticket_count: int
    sla_captured_count: int
    sla_adhered_count: int
    sla_adherence_pct: float | None


class VolumetricsSlaTrendLogic(BaseModel):
    response_adherence_formula: str
    resolution_adherence_formula: str
    captured_definition: str


class VolumetricsSlaTrendsResponse(BaseModel):
    time_grain: str
    agreement_mode: str = "sla"
    not_applicable: bool
    response: list[VolumetricsSlaTrendRow]
    resolution: list[VolumetricsSlaTrendRow]
    logic: VolumetricsSlaTrendLogic


class VolumetricsTopApplicationsRequest(VolumetricsRequest):
    top_n: int = Field(default=10, ge=10, le=20)


class VolumetricsRankingWindow(BaseModel):
    start_month: str
    end_month: str
    description: str


class VolumetricsTopApplicationPoint(BaseModel):
    application_name: str
    average_created: float
    average_canceled_closed_incomplete: float
    created_label: int
    canceled_label: int
    volume_pct: float | None
    display_label: str


class VolumetricsTopApplicationsResponse(BaseModel):
    ranking_window: VolumetricsRankingWindow
    top_n: int
    overall_average_monthly_volume: float
    points: list[VolumetricsTopApplicationPoint]


class VolumetricsBatchRule(BaseModel):
    field: str
    rule_description: str


class VolumetricsIncidentBatchTrendPoint(BaseModel):
    period_key: str
    period_label: str
    batch_created_count: int


class VolumetricsIncidentBatchTrendResponse(BaseModel):
    applicable: bool
    message: str
    batch_rule: VolumetricsBatchRule
    points: list[VolumetricsIncidentBatchTrendPoint]


class VolumetricsTopIncidentBatchApplicationPoint(BaseModel):
    application_name: str
    average_batch_created: float
    average_batch_canceled: float
    batch_created_label: int
    batch_canceled_label: int
    pareto_cumulative_pct: float | None


class VolumetricsTopIncidentBatchApplicationsResponse(BaseModel):
    applicable: bool
    message: str
    ranking_window: VolumetricsRankingWindow
    top_n: int
    points: list[VolumetricsTopIncidentBatchApplicationPoint]


class VolumetricsSplitDatum(BaseModel):
    label: str
    average_monthly_count: float
    display_count: int
    percentage: float | None


class VolumetricsTicketTypeSplit(BaseModel):
    incidents: list[VolumetricsSplitDatum]
    sc_tasks: list[VolumetricsSplitDatum]


class VolumetricsDetailedArchitectureInstallSplitsResponse(BaseModel):
    rolling_window: VolumetricsRankingWindow
    architecture_type: VolumetricsTicketTypeSplit
    install_type: VolumetricsTicketTypeSplit


class VolumetricsTicketsPerUserPoint(BaseModel):
    application_name: str
    active_users: int
    average_monthly_ticket_volume: float
    tickets_per_user_per_month: float
    display_label: str


class VolumetricsTicketsPerUserResponse(BaseModel):
    ranking_window: VolumetricsRankingWindow
    top_n: int
    points: list[VolumetricsTicketsPerUserPoint]


class VolumetricsTripleTicketTypeSplit(BaseModel):
    all: list[VolumetricsSplitDatum]
    incidents: list[VolumetricsSplitDatum]
    sc_tasks: list[VolumetricsSplitDatum]


class VolumetricsDistributionSplitsResponse(BaseModel):
    ranking_window: VolumetricsRankingWindow
    sap_non_sap: VolumetricsTripleTicketTypeSplit
    architecture_type: VolumetricsTripleTicketTypeSplit
    install_type: VolumetricsTripleTicketTypeSplit
    hosting_env: VolumetricsTripleTicketTypeSplit


class VolumetricsKpiMttrPoint(BaseModel):
    period_key: str
    period_label: str
    average_mttr_days: float | None
    ticket_count: int
    show_label: bool
    label_text: str | None


class VolumetricsKpiMttrPrioritySet(BaseModel):
    P1: list[VolumetricsKpiMttrPoint]
    P2: list[VolumetricsKpiMttrPoint]
    P3: list[VolumetricsKpiMttrPoint]
    P4: list[VolumetricsKpiMttrPoint]


class VolumetricsKpiMttrTrendsResponse(BaseModel):
    time_grain: str
    incident: VolumetricsKpiMttrPrioritySet
    sc_task: VolumetricsKpiMttrPrioritySet


class VolumetricsDurationBucketRow(BaseModel):
    period_key: str
    period_label: str
    buckets: dict[str, int]


class VolumetricsKpiDurationBucketsResponse(BaseModel):
    months: list[str]
    incident: list[VolumetricsDurationBucketRow]
    sc_task: list[VolumetricsDurationBucketRow]


class VolumetricsReassignmentHopsDateRange(BaseModel):
    from_date: datetime
    to_date: datetime
    complete_month_cutoff_applied: bool


class VolumetricsReassignmentHopsPoint(PeriodMetricRow):
    period_key: str
    total_created_tickets: int
    tickets_with_2_plus_reassignments: int
    total_reassignment_hops_ge_2: int
    pct_tickets_with_2_plus_reassignments: float | None
    reassignment_hops_pct_of_created: float | None


class VolumetricsReassignmentHopsTrendResponse(BaseModel):
    time_grain: str
    date_range: VolumetricsReassignmentHopsDateRange
    points: list[VolumetricsReassignmentHopsPoint]
    data_notes: list[str]
    warnings: list[str]
