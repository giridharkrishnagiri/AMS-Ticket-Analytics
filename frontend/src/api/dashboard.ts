import { apiBaseUrl, requestJson } from "./client";

export type TimeGrain = "DAILY" | "WEEKLY" | "MONTHLY" | "QUARTERLY" | "YEARLY";
export type TicketTypeFilter = "INCIDENT" | "SERVICE_CATALOG_TASK";

export type DashboardQuery = {
  projectId: string;
  ticketTypes?: TicketTypeFilter[];
  timeGrain: TimeGrain;
  startDate?: string;
  endDate?: string;
  priorities?: string[];
  states?: string[];
  assignmentGroups?: string[];
  applications?: string[];
  customers?: string[];
  towers?: string[];
  clusters?: string[];
  applicationGroups?: string[];
  applicationNames?: string[];
  responseSlaNames?: string[];
  resolutionSlaNames?: string[];
  functionalTracks?: string[];
  amsOwners?: string[];
  supportedByVendors?: string[];
  supportLeads?: string[];
  applicationOwners?: string[];
  businessServiceCiNames?: string[];
  parentApplicationNames?: string[];
};

export type PeriodMetricRow = {
  period_start: string;
  period_end: string;
  period_label: string;
};

export type CreatedResolvedOpenRow = PeriodMetricRow & {
  created_count: number;
  resolved_count: number;
  open_end_count: number;
};

export type MttrTrendRow = PeriodMetricRow & {
  completed_ticket_count: number;
  mttr_actual_days: number | null;
  mttr_business_days: number | null;
};

export type SlaTrendRow = PeriodMetricRow & {
  total_tickets_with_sla: number;
  sla_met_count: number;
  sla_breached_count: number;
  sla_unknown_count: number;
  sla_met_percentage: number | null;
  sla_breached_percentage: number | null;
};

export type IncidentSlaTrendRow = PeriodMetricRow & {
  period: string;
  incident_count: number;
  response_sla_applicable_count: number;
  response_sla_met_count: number;
  response_sla_breached_count: number;
  response_sla_adherence_pct: number | null;
  response_sla_breach_pct: number | null;
  response_sla_avg_business_elapsed_seconds: number | null;
  response_sla_avg_business_elapsed_hours: number | null;
  resolution_sla_applicable_count: number;
  resolution_sla_met_count: number;
  resolution_sla_breached_count: number;
  resolution_sla_adherence_pct: number | null;
  resolution_sla_breach_pct: number | null;
  resolution_sla_avg_business_elapsed_seconds: number | null;
  resolution_sla_avg_business_elapsed_hours: number | null;
};

export type IncidentSlaSummary = {
  incident_count: number;
  response_sla_applicable_count: number;
  response_sla_met_count: number;
  response_sla_breached_count: number;
  response_sla_adherence_pct: number | null;
  response_sla_breach_pct: number | null;
  response_sla_avg_business_elapsed_hours: number | null;
  resolution_sla_applicable_count: number;
  resolution_sla_met_count: number;
  resolution_sla_breached_count: number;
  resolution_sla_adherence_pct: number | null;
  resolution_sla_breach_pct: number | null;
  resolution_sla_avg_business_elapsed_hours: number | null;
  response_accenture_count: number;
  response_default_count: number;
  resolution_accenture_count: number;
  resolution_default_count: number;
};

export type IncidentSlaNameBreakdownItem = {
  sla_name: string;
  ticket_count: number;
  met_count: number;
  breached_count: number;
  adherence_pct: number | null;
  breach_pct: number | null;
  avg_business_elapsed_hours: number | null;
};

export type IncidentSlaNameBreakdown = {
  response_sla_names: IncidentSlaNameBreakdownItem[];
  resolution_sla_names: IncidentSlaNameBreakdownItem[];
};

export type ReopenTrendRow = PeriodMetricRow & {
  total_tickets: number;
  reopened_ticket_count: number;
  total_reopen_count: number;
  average_reopen_count: number | null;
};

export type ReassignmentTrendRow = PeriodMetricRow & {
  total_tickets: number;
  tickets_with_more_than_2_reassignments: number;
  total_reassignment_count: number;
  average_reassignment_count: number | null;
};

export type CreationSourceTrendRow = PeriodMetricRow & {
  user_created_count: number;
  system_created_count: number;
  unknown_count: number;
};

export type TechnicalFunctionalBreakdown = {
  technical_count: number;
  functional_count: number;
  unknown_count: number;
  not_applicable_count: number;
};

export type DashboardFilterValues = {
  ticket_types: string[];
  priorities: string[];
  states: string[];
  assignment_groups: string[];
  applications: string[];
  customers: string[];
  towers: string[];
  clusters: string[];
  application_groups: string[];
  application_names: string[];
  month_keys: string[];
  response_sla_names: string[];
  resolution_sla_names: string[];
  functional_tracks: string[];
  ams_owners: string[];
  supported_by_vendors: string[];
  support_leads: string[];
  application_owners: string[];
  business_service_ci_names: string[];
  parent_application_names: string[];
};

export type DashboardOverview = {
  project_id: string;
  customer_name: string;
  project_name: string;
  application_inventory: {
    total_applications: number;
    functional_track_count: number;
    ams_owner_count: number;
    supported_vendor_count: number;
    assignment_group_count: number;
    application_owner_count: number;
    very_critical_application_count: number;
    critical_application_count: number;
  };
  ingested_volume: {
    total_rows: number;
    incident_rows: number;
    sc_task_rows: number;
    incident_sla_rows: number;
  };
  tickets: {
    total_in_scope_tickets: number;
    incident_count: number;
    sc_task_count: number;
    completion_date_min: string | null;
    completion_date_max: string | null;
    applications_80pct_monthly_volume_count: number;
  };
};

export type ApplicationCombinedFilterValue = {
  label: string;
  left_value: string;
  right_value: string;
  count: number;
};

export type ApplicationFilterValue = {
  label: string;
  value: string;
  count: number;
};

export type DashboardApplicationsFilterValues = {
  functional_track_ams_owner: ApplicationCombinedFilterValue[];
  assignment_group_owner: ApplicationCombinedFilterValue[];
  parent_application_name: ApplicationFilterValue[];
  application_owner: ApplicationFilterValue[];
  supported_by_vendor: ApplicationFilterValue[];
  sap_non_sap: ApplicationFilterValue[];
  architecture_type: ApplicationFilterValue[];
  application_type: ApplicationFilterValue[];
  business_critical: ApplicationFilterValue[];
  install_status: ApplicationFilterValue[];
  install_type: ApplicationFilterValue[];
  hosting_env: ApplicationFilterValue[];
  lifecycle_status_stage: ApplicationCombinedFilterValue[];
};

export type DashboardApplicationsFilters = {
  functional_track_ams_owner: string[];
  assignment_group_owner: string[];
  parent_application_name: string[];
  application_owner: string[];
  supported_by_vendor: string[];
  sap_non_sap: string[];
  architecture_type: string[];
  application_type: string[];
  business_critical: string[];
  install_status: string[];
  install_type: string[];
  hosting_env: string[];
  lifecycle_status_stage: string[];
};

export type DashboardApplicationsSort = {
  column: string;
  direction: "asc" | "desc";
};

export type DashboardApplicationsRequest = {
  project_id: string;
  filters: DashboardApplicationsFilters;
  sort: DashboardApplicationsSort;
  limit: number;
  offset: number;
};

export type DashboardApplicationsFilterValuesRequest = {
  project_id: string;
  filters: DashboardApplicationsFilters;
};

export type DashboardApplicationsSummary = {
  applications: number;
  functional_groups: number;
  assignment_groups: number;
  parent_business_apps: number;
  business_applications: number;
  technical_applications: number;
  very_critical_applications: number;
  critical_applications: number;
  show_functional_groups: boolean;
  show_assignment_groups: boolean;
  show_parent_business_apps: boolean;
};

export type DashboardApplicationRow = {
  business_service_ci_name: string;
  parent_application_name: string;
  assignment_group: string;
  sap_non_sap: string;
  assignment_group_owner: string;
  application_owner: string;
  support_lead: string;
  functional_track: string;
  ams_owner: string;
  supported_by_vendor: string;
  hosting_env: string;
  global_application: string;
  lifecycle_stage_status: string;
  lifecycle_current: string;
  lifecycle_1_to_3_years: string;
  lifecycle_3_to_5_years: string;
  active_users: number | null;
  avg_monthly_ticket_volume_6m: number | null;
  tickets_per_user_per_month: number | null;
  app_family: string;
  biz_process: string;
  app_category: string;
  org_unit_level_1: string;
  org_unit_level_2: string;
  org_unit_level_3: string;
  app_type: string;
  architecture_type: string;
  biz_capabilities: string;
  business_reason_for_maintain_applications: string;
  business_units: string;
  biz_criticality: string;
  biz_owner: string;
  company: string;
  install_status: string;
  install_type: string;
  lifecycle_status: string;
  operating_system: string;
  sox_audited: string;
  sox_scope: string;
  strategic: string;
};

export type DashboardApplicationsTopActiveUsersPoint = {
  application_name: string;
  parent_application_name: string;
  active_users: number;
};

export type DashboardApplicationsTopActiveUsers = {
  top_n: number;
  duplicate_parent_active_user_count: number;
  points: DashboardApplicationsTopActiveUsersPoint[];
};

export type DashboardCommentaryContext = {
  project_id: string;
  dashboard_area: string;
  tab_name: string;
  sub_tab_name?: string | null;
  section_key: string;
  chart_key?: string | null;
  scope_filter?: string;
  ticket_type_filter?: string;
  functional_track_ams_owner?: string;
};

export type DashboardCommentaryRecord = {
  id: string;
  project_id: string;
  dashboard_area: string;
  tab_name: string;
  sub_tab_name: string | null;
  section_key: string;
  chart_key: string | null;
  scope_filter: string;
  ticket_type_filter: string;
  functional_track_ams_owner: string;
  commentary_html: string | null;
  commentary_text: string | null;
  updated_at: string;
  updated_by: string | null;
};

export type DashboardCommentaryResponse = {
  commentary: DashboardCommentaryRecord | null;
};

export type DashboardCommentaryBatchRequest = {
  project_id: string;
  dashboard_area: string;
  tab_name: string;
  sub_tab_name?: string | null;
  scope_filter?: string;
  ticket_type_filter?: string;
  functional_track_ams_owner?: string;
};

export type DashboardCommentaryBatchResponse = {
  commentaries: DashboardCommentaryRecord[];
};

export type DashboardCommentaryUpsertRequest = DashboardCommentaryContext & {
  commentary_html: string | null;
  commentary_text: string | null;
  updated_by?: string | null;
};

export type DashboardApplicationsList = {
  total: number;
  rows: DashboardApplicationRow[];
};

export type DashboardApplicationsChartDatum = {
  label: string;
  count: number;
};

export type DashboardApplicationsCriticalityHostingPivotRow = {
  business_criticality: string;
  counts: Record<string, number>;
  total: number;
};

export type DashboardApplicationsCriticalityHostingPivot = {
  rows: string[];
  columns: string[];
  values: DashboardApplicationsCriticalityHostingPivotRow[];
  column_totals: Record<string, number>;
  grand_total: number;
};

export type DashboardApplicationsCharts = {
  lifecycle_stage: DashboardApplicationsChartDatum[];
  architecture_type: DashboardApplicationsChartDatum[];
  install_type: DashboardApplicationsChartDatum[];
  hosting_env: DashboardApplicationsChartDatum[];
  strategic: DashboardApplicationsChartDatum[];
  criticality_hosting_pivot: DashboardApplicationsCriticalityHostingPivot;
  global_local_applications: DashboardApplicationsChartDatum[];
};

export type DashboardApplicationsLifecyclePlan = "Invest" | "Disinvest" | "Maintain" | "Retired";

export type DashboardApplicationsLifecycleMatrixRow = {
  plan: DashboardApplicationsLifecyclePlan;
  counts: Record<string, number>;
};

export type DashboardApplicationsLifecycleMatrix = {
  plans: DashboardApplicationsLifecyclePlan[];
  horizons: string[];
  rows: DashboardApplicationsLifecycleMatrixRow[];
  in_use_application_count: number;
};

export type DashboardApplicationsLifecycleChartDatum = {
  horizon: string;
  count: number;
};

export type DashboardApplicationsLifecycleApplication = {
  business_service_ci_name: string;
  parent_business_application: string;
  functional_track: string;
  ams_owner: string;
  application_owner: string;
  supported_by_vendor: string;
  install_type: string;
  business_criticality: string;
  architecture_type: string;
  application_type: string;
  hosting_env: string;
  global_application: string;
  active_users: number | null;
  lifecycle_current: string;
  lifecycle_1_to_3_years: string;
  lifecycle_3_to_5_years: string;
  selected_plan_horizons: string[];
};

export type DashboardApplicationsLifecyclePlanning = {
  matrix: DashboardApplicationsLifecycleMatrix;
  selected_plan: {
    plan: DashboardApplicationsLifecyclePlan;
    chart: DashboardApplicationsLifecycleChartDatum[];
    applications: DashboardApplicationsLifecycleApplication[];
    application_count: number;
  };
};

export type VolumetricsScope = "in_scope" | "out_of_scope" | "all";
export type VolumetricsTicketType = "all" | "incident" | "sc_task";
export type VolumetricsTimeGrain = "monthly" | "weekly";
export type VolumetricsAgreementMode = "sla" | "ola";

export type DashboardVolumetricsFilters = {
  functional_track_ams_owner: string[];
  assignment_group_support_lead: string[];
  parent_application_name: string[];
  application_owner: string[];
  supported_by_vendor: string[];
  sap_non_sap: string[];
};

export type DashboardVolumetricsRequest = {
  project_id: string;
  scope: VolumetricsScope;
  ticket_type: VolumetricsTicketType;
  time_grain: VolumetricsTimeGrain;
  agreement_mode?: VolumetricsAgreementMode;
  start_datetime: string;
  end_datetime: string;
  filters: DashboardVolumetricsFilters;
};

export type DashboardVolumetricsFilterValues = {
  scope: ApplicationFilterValue[];
  ticket_type: ApplicationFilterValue[];
  functional_track_ams_owner: ApplicationCombinedFilterValue[];
  assignment_group_support_lead: ApplicationCombinedFilterValue[];
  parent_application_name: ApplicationFilterValue[];
  application_owner: ApplicationFilterValue[];
  supported_by_vendor: ApplicationFilterValue[];
  sap_non_sap: ApplicationFilterValue[];
  source?: string;
  duration_ms?: number | null;
};

export type DashboardVolumetricsSummaryMetric = {
  total: number;
  average_per_period: number | null;
};

export type DashboardVolumetricsCancelledMetric = DashboardVolumetricsSummaryMetric & {
  cancelled_pct_of_resolved_cancelled: number | null;
};

export type DashboardVolumetricsSlaMetric = {
  average_adherence_pct: number | null;
  applicable_count: number;
  met_count: number;
};

export type DashboardVolumetricsSummary = {
  period_count: number;
  created: DashboardVolumetricsSummaryMetric;
  resolved_closed: DashboardVolumetricsSummaryMetric;
  cancelled: DashboardVolumetricsCancelledMetric;
  response_sla: DashboardVolumetricsSlaMetric;
  resolution_sla: DashboardVolumetricsSlaMetric;
};

export type DashboardVolumetricsDataRange = {
  completion_date_min: string | null;
  completion_date_max: string | null;
};

export type DashboardVolumetricsBacklogRow = PeriodMetricRow & {
  created_count: number;
  resolved_closed_count: number;
  backlog_open_count: number;
  average_backlog_open: number | null;
};

export type DashboardVolumetricsBacklog = {
  average_backlog_open: number | null;
  rows: DashboardVolumetricsBacklogRow[];
};

export type DashboardVolumetricsCreatedResolvedCanceledRow = PeriodMetricRow & {
  created_count: number;
  resolved_closed_count: number;
  canceled_closed_incomplete_count: number;
};

export type DashboardVolumetricsCreatedResolvedCanceled = {
  time_grain: VolumetricsTimeGrain;
  points: DashboardVolumetricsCreatedResolvedCanceledRow[];
};

export type DashboardVolumetricsBacklogPoint = PeriodMetricRow & {
  backlog_open: number;
};

export type DashboardVolumetricsBacklogOnly = {
  time_grain: VolumetricsTimeGrain;
  average_backlog: number | null;
  points: DashboardVolumetricsBacklogPoint[];
};

export type CreatedPatternType =
  | "day_of_month"
  | "day_of_week"
  | "hour_weekdays"
  | "hour_weekends";

export type VolumetricsDayType = "weekdays" | "weekends";

export type DashboardVolumetricsCreatedPatternPoint = {
  label: string;
  average_created: number;
  total_created: number;
  denominator: number;
};

export type DashboardVolumetricsCreatedPattern = {
  pattern_type: CreatedPatternType;
  points: DashboardVolumetricsCreatedPatternPoint[];
};

export type DashboardVolumetricsHourlyCreatedResolvedPoint = {
  hour: string;
  average_created: number;
  average_resolved_closed: number;
  created_label: number;
  resolved_closed_label: number;
};

export type DashboardVolumetricsHourlyCreatedResolved = {
  day_type: VolumetricsDayType;
  denominator_days: number;
  points: DashboardVolumetricsHourlyCreatedResolvedPoint[];
};

export type DashboardVolumetricsPriorityDistributionPoint = {
  period_key: string;
  period_label: string;
  values: Record<string, number>;
  percentages: Record<string, number | null>;
  total: number;
};

export type DashboardVolumetricsPriorityDistribution = {
  time_grain: VolumetricsTimeGrain;
  priorities: string[];
  points: DashboardVolumetricsPriorityDistributionPoint[];
};

export type DashboardVolumetricsSlaTrendRow = {
  period_key: string;
  period_label: string;
  total_closed_ticket_count: number;
  sla_captured_count: number;
  sla_adhered_count: number;
  sla_adherence_pct: number | null;
};

export type DashboardVolumetricsSlaTrends = {
  time_grain: VolumetricsTimeGrain;
  agreement_mode: VolumetricsAgreementMode;
  not_applicable: boolean;
  response: DashboardVolumetricsSlaTrendRow[];
  resolution: DashboardVolumetricsSlaTrendRow[];
  logic: {
    response_adherence_formula: string;
    resolution_adherence_formula: string;
    captured_definition: string;
  };
};

export type DashboardVolumetricsRankingWindow = {
  start_month: string;
  end_month: string;
  description: string;
};

export type DashboardVolumetricsTopApplicationPoint = {
  application_name: string;
  average_created: number;
  average_canceled_closed_incomplete: number;
  created_label: number;
  canceled_label: number;
  volume_pct: number | null;
  display_label: string;
};

export type DashboardVolumetricsTopApplications = {
  ranking_window: DashboardVolumetricsRankingWindow;
  top_n: number;
  overall_average_monthly_volume: number;
  points: DashboardVolumetricsTopApplicationPoint[];
};

export type DashboardVolumetricsIncidentBatchTrendPoint = {
  period_key: string;
  period_label: string;
  batch_created_count: number;
};

export type DashboardVolumetricsIncidentBatchTrend = {
  applicable: boolean;
  message: string;
  batch_rule: {
    field: string;
    rule_description: string;
  };
  points: DashboardVolumetricsIncidentBatchTrendPoint[];
};

export type DashboardVolumetricsTopIncidentBatchApplicationPoint = {
  application_name: string;
  average_batch_created: number;
  average_batch_canceled: number;
  batch_created_label: number;
  batch_canceled_label: number;
  pareto_cumulative_pct: number | null;
};

export type DashboardVolumetricsTopIncidentBatchApplications = {
  applicable: boolean;
  message: string;
  ranking_window: DashboardVolumetricsRankingWindow;
  top_n: number;
  points: DashboardVolumetricsTopIncidentBatchApplicationPoint[];
};

export type DashboardVolumetricsSplitDatum = {
  label: string;
  average_monthly_count: number;
  display_count: number;
  percentage: number | null;
};

export type DashboardVolumetricsTicketTypeSplit = {
  incidents: DashboardVolumetricsSplitDatum[];
  sc_tasks: DashboardVolumetricsSplitDatum[];
};

export type DashboardVolumetricsDetailedArchitectureInstallSplits = {
  rolling_window: DashboardVolumetricsRankingWindow;
  architecture_type: DashboardVolumetricsTicketTypeSplit;
  install_type: DashboardVolumetricsTicketTypeSplit;
};

export type DashboardVolumetricsTicketsPerUserPoint = {
  application_name: string;
  active_users: number;
  average_monthly_ticket_volume: number;
  tickets_per_user_per_month: number;
  display_label: string;
};

export type DashboardVolumetricsTicketsPerUser = {
  ranking_window: DashboardVolumetricsRankingWindow;
  top_n: number;
  points: DashboardVolumetricsTicketsPerUserPoint[];
};

export type DashboardVolumetricsTripleTicketTypeSplit = {
  all: DashboardVolumetricsSplitDatum[];
  incidents: DashboardVolumetricsSplitDatum[];
  sc_tasks: DashboardVolumetricsSplitDatum[];
};

export type DashboardVolumetricsDistributionSplits = {
  ranking_window: DashboardVolumetricsRankingWindow;
  sap_non_sap: DashboardVolumetricsTripleTicketTypeSplit;
  architecture_type: DashboardVolumetricsTripleTicketTypeSplit;
  install_type: DashboardVolumetricsTripleTicketTypeSplit;
  hosting_env: DashboardVolumetricsTripleTicketTypeSplit;
};

export type DashboardVolumetricsKpiMttrPoint = {
  period_key: string;
  period_label: string;
  average_mttr_days: number | null;
  ticket_count: number;
  show_label: boolean;
  label_text: string | null;
};

export type DashboardVolumetricsKpiMttrPrioritySet = {
  P1: DashboardVolumetricsKpiMttrPoint[];
  P2: DashboardVolumetricsKpiMttrPoint[];
  P3: DashboardVolumetricsKpiMttrPoint[];
  P4: DashboardVolumetricsKpiMttrPoint[];
};

export type DashboardVolumetricsKpiMttrTrends = {
  time_grain: VolumetricsTimeGrain;
  incident: DashboardVolumetricsKpiMttrPrioritySet;
  sc_task: DashboardVolumetricsKpiMttrPrioritySet;
};

export type DashboardVolumetricsDurationBucketRow = {
  period_key: string;
  period_label: string;
  buckets: Record<string, number>;
};

export type DashboardVolumetricsKpiDurationBuckets = {
  months: string[];
  incident: DashboardVolumetricsDurationBucketRow[];
  sc_task: DashboardVolumetricsDurationBucketRow[];
};

function appendMulti(query: URLSearchParams, key: string, values: string[] | undefined) {
  for (const value of values ?? []) {
    if (value.trim()) {
      query.append(key, value.trim());
    }
  }
}

function buildDashboardQuery(input: DashboardQuery): string {
  const query = new URLSearchParams({
    project_id: input.projectId,
    time_grain: input.timeGrain,
  });

  if (input.startDate) {
    query.set("start_date", input.startDate);
  }
  if (input.endDate) {
    query.set("end_date", input.endDate);
  }

  appendMulti(query, "ticket_type", input.ticketTypes);
  appendMulti(query, "priority", input.priorities);
  appendMulti(query, "state", input.states);
  appendMulti(query, "assignment_group", input.assignmentGroups);
  appendMulti(query, "application", input.applications);
  appendMulti(query, "customer_name", input.customers);
  appendMulti(query, "tower_name", input.towers);
  appendMulti(query, "cluster_name", input.clusters);
  appendMulti(query, "application_group_name", input.applicationGroups);
  appendMulti(query, "application_name", input.applicationNames);
  appendMulti(query, "response_sla_name", input.responseSlaNames);
  appendMulti(query, "resolution_sla_name", input.resolutionSlaNames);
  appendMulti(query, "functional_track", input.functionalTracks);
  appendMulti(query, "ams_owner", input.amsOwners);
  appendMulti(query, "supported_by_vendor", input.supportedByVendors);
  appendMulti(query, "support_lead", input.supportLeads);
  appendMulti(query, "application_owner", input.applicationOwners);
  appendMulti(query, "business_service_ci_name", input.businessServiceCiNames);
  appendMulti(query, "parent_application_name", input.parentApplicationNames);

  return query.toString();
}

export function getDashboardFilterValues(input: DashboardQuery): Promise<DashboardFilterValues> {
  return requestJson<DashboardFilterValues>(
    `/dashboard/filter-values?${buildDashboardQuery(input)}`
  );
}

export function getDashboardOverview(projectId: string): Promise<DashboardOverview> {
  const query = new URLSearchParams({ project_id: projectId.trim() });
  return requestJson<DashboardOverview>(`/dashboard/overview?${query.toString()}`);
}

function getDownloadFilename(contentDisposition: string | null): string | null {
  if (!contentDisposition) {
    return null;
  }
  const utf8Match = contentDisposition.match(/filename\*=UTF-8''([^;]+)/i);
  if (utf8Match?.[1]) {
    return decodeURIComponent(utf8Match[1].trim());
  }
  const filenameMatch = contentDisposition.match(/filename="?([^";]+)"?/i);
  return filenameMatch?.[1]?.trim() ?? null;
}

export async function downloadOfflineDashboard(
  projectId: string
): Promise<{ blob: Blob; filename: string }> {
  const response = await fetch(`${apiBaseUrl}/dashboard/offline-export`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ project_id: projectId.trim(), format: "html" }),
  });

  if (!response.ok) {
    let message = `Request failed with HTTP ${response.status}`;
    try {
      const payload = (await response.json()) as { detail?: unknown };
      if (typeof payload.detail === "string") {
        message = payload.detail;
      }
    } catch {
      // Keep the HTTP status fallback when the response is not JSON.
    }
    throw new Error(message);
  }

  const filename =
    getDownloadFilename(response.headers.get("Content-Disposition")) ??
    `AMS_Apps_Volumetrics_Dashboard_${new Date()
      .toISOString()
      .slice(0, 16)
      .replace(/[-:T]/g, "")}.html`;

  return { blob: await response.blob(), filename };
}

export async function exportDashboardPowerPoint(input: {
  functionalTrackAmsOwner?: string | string[];
  includeCommentary?: boolean;
  projectId: string;
  scope?: string;
  ticketType?: string;
}): Promise<{ blob: Blob; filename: string }> {
  const response = await fetch(`${apiBaseUrl}/dashboard/powerpoint-export`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      project_id: input.projectId.trim(),
      scope: input.scope ?? "in_scope",
      ticket_type: input.ticketType ?? "all",
      functional_track_ams_owner: input.functionalTrackAmsOwner ?? "all",
      include_commentary: input.includeCommentary ?? true,
    }),
  });

  if (!response.ok) {
    let message = `Request failed with HTTP ${response.status}`;
    try {
      const payload = (await response.json()) as { detail?: unknown };
      if (typeof payload.detail === "string") {
        message = payload.detail;
      }
    } catch {
      // Keep the HTTP status fallback when the response is not JSON.
    }
    throw new Error(message);
  }

  const filename =
    getDownloadFilename(response.headers.get("Content-Disposition")) ??
    `AMS_Apps_Volumetrics_Dashboard_${new Date()
      .toISOString()
      .slice(0, 16)
      .replace(/[-:T]/g, "")}.pptx`;

  return { blob: await response.blob(), filename };
}

export function getDashboardApplicationsFilterValues(
  input: DashboardApplicationsFilterValuesRequest
): Promise<DashboardApplicationsFilterValues> {
  return requestJson<DashboardApplicationsFilterValues>(
    "/dashboard/applications/filter-values",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    }
  );
}

function postApplicationsRequest<T>(
  path: string,
  input: DashboardApplicationsRequest
): Promise<T> {
  return requestJson<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
}

export function getDashboardApplicationsSummary(
  input: DashboardApplicationsRequest
): Promise<DashboardApplicationsSummary> {
  return postApplicationsRequest<DashboardApplicationsSummary>(
    "/dashboard/applications/summary",
    input
  );
}

export function getDashboardApplicationsList(
  input: DashboardApplicationsRequest
): Promise<DashboardApplicationsList> {
  return postApplicationsRequest<DashboardApplicationsList>("/dashboard/applications/list", input);
}

export function getDashboardApplicationsCharts(
  input: DashboardApplicationsRequest
): Promise<DashboardApplicationsCharts> {
  return postApplicationsRequest<DashboardApplicationsCharts>(
    "/dashboard/applications/charts",
    input
  );
}

export function getDashboardApplicationsTopActiveUsers(
  input: DashboardApplicationsRequest,
  topN: 10 | 20
): Promise<DashboardApplicationsTopActiveUsers> {
  return postApplicationsRequest<DashboardApplicationsTopActiveUsers>(
    "/dashboard/applications/top-active-users",
    { ...input, top_n: topN } as DashboardApplicationsRequest & { top_n: 10 | 20 }
  );
}

export function getDashboardApplicationsLifecyclePlanning(
  input: DashboardApplicationsRequest,
  selectedPlan: DashboardApplicationsLifecyclePlan
): Promise<DashboardApplicationsLifecyclePlanning> {
  return postApplicationsRequest<DashboardApplicationsLifecyclePlanning>(
    "/dashboard/applications/lifecycle-planning",
    {
      ...input,
      selected_plan: selectedPlan,
    } as DashboardApplicationsRequest & { selected_plan: DashboardApplicationsLifecyclePlan }
  );
}

export function getDashboardCommentary(
  input: DashboardCommentaryContext
): Promise<DashboardCommentaryResponse> {
  return requestJson<DashboardCommentaryResponse>("/dashboard/commentaries/context", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
}

export function getDashboardCommentariesBatch(
  input: DashboardCommentaryBatchRequest
): Promise<DashboardCommentaryBatchResponse> {
  return requestJson<DashboardCommentaryBatchResponse>("/dashboard/commentaries/batch", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
}

export function upsertDashboardCommentary(
  input: DashboardCommentaryUpsertRequest
): Promise<DashboardCommentaryResponse> {
  return requestJson<DashboardCommentaryResponse>("/dashboard/commentaries/upsert", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
}

function postVolumetricsRequest<T>(
  path: string,
  input: DashboardVolumetricsRequest
): Promise<T> {
  return requestJson<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
}

export function getDashboardVolumetricsFilterValues(
  input: DashboardVolumetricsRequest
): Promise<DashboardVolumetricsFilterValues> {
  return postVolumetricsRequest<DashboardVolumetricsFilterValues>(
    "/dashboard/volumetrics/filter-values",
    input
  );
}

export function getDashboardVolumetricsSummary(
  input: DashboardVolumetricsRequest
): Promise<DashboardVolumetricsSummary> {
  return postVolumetricsRequest<DashboardVolumetricsSummary>(
    "/dashboard/volumetrics/summary",
    input
  );
}

export function getDashboardVolumetricsDataRange(
  projectId: string
): Promise<DashboardVolumetricsDataRange> {
  const query = new URLSearchParams({ project_id: projectId.trim() });
  return requestJson<DashboardVolumetricsDataRange>(
    `/dashboard/volumetrics/data-range?${query.toString()}`
  );
}

export function getDashboardVolumetricsCreatedResolvedBacklog(
  input: DashboardVolumetricsRequest
): Promise<DashboardVolumetricsBacklog> {
  return postVolumetricsRequest<DashboardVolumetricsBacklog>(
    "/dashboard/volumetrics/created-resolved-backlog",
    input
  );
}

export function getDashboardVolumetricsCreatedResolvedCanceled(
  input: DashboardVolumetricsRequest
): Promise<DashboardVolumetricsCreatedResolvedCanceled> {
  return postVolumetricsRequest<DashboardVolumetricsCreatedResolvedCanceled>(
    "/dashboard/volumetrics/created-resolved-canceled",
    input
  );
}

export function getDashboardVolumetricsBacklog(
  input: DashboardVolumetricsRequest
): Promise<DashboardVolumetricsBacklogOnly> {
  return postVolumetricsRequest<DashboardVolumetricsBacklogOnly>(
    "/dashboard/volumetrics/backlog",
    input
  );
}

export function getDashboardVolumetricsCreatedPattern(
  input: DashboardVolumetricsRequest,
  patternType: CreatedPatternType
): Promise<DashboardVolumetricsCreatedPattern> {
  return postVolumetricsRequest<DashboardVolumetricsCreatedPattern>(
    "/dashboard/volumetrics/created-pattern",
    { ...input, pattern_type: patternType } as DashboardVolumetricsRequest & {
      pattern_type: CreatedPatternType;
    }
  );
}

export function getDashboardVolumetricsHourlyCreatedResolved(
  input: DashboardVolumetricsRequest,
  dayType: VolumetricsDayType
): Promise<DashboardVolumetricsHourlyCreatedResolved> {
  return postVolumetricsRequest<DashboardVolumetricsHourlyCreatedResolved>(
    "/dashboard/volumetrics/hourly-created-resolved",
    { ...input, day_type: dayType } as DashboardVolumetricsRequest & {
      day_type: VolumetricsDayType;
    }
  );
}

export function getDashboardVolumetricsPriorityDistribution(
  input: DashboardVolumetricsRequest
): Promise<DashboardVolumetricsPriorityDistribution> {
  return postVolumetricsRequest<DashboardVolumetricsPriorityDistribution>(
    "/dashboard/volumetrics/priority-distribution",
    input
  );
}

export function getDashboardVolumetricsSlaTrends(
  input: DashboardVolumetricsRequest
): Promise<DashboardVolumetricsSlaTrends> {
  return postVolumetricsRequest<DashboardVolumetricsSlaTrends>(
    "/dashboard/volumetrics/sla-trends",
    input
  );
}

export function getDashboardVolumetricsTopApplications(
  input: DashboardVolumetricsRequest,
  topN: 10 | 20
): Promise<DashboardVolumetricsTopApplications> {
  return postVolumetricsRequest<DashboardVolumetricsTopApplications>(
    "/dashboard/volumetrics/top-applications",
    { ...input, top_n: topN } as DashboardVolumetricsRequest & { top_n: 10 | 20 }
  );
}

export function getDashboardVolumetricsIncidentBatchTrend(
  input: DashboardVolumetricsRequest
): Promise<DashboardVolumetricsIncidentBatchTrend> {
  return postVolumetricsRequest<DashboardVolumetricsIncidentBatchTrend>(
    "/dashboard/volumetrics/incident-batch-trend",
    input
  );
}

export function getDashboardVolumetricsTopIncidentBatchApplications(
  input: DashboardVolumetricsRequest,
  topN: 10 | 20
): Promise<DashboardVolumetricsTopIncidentBatchApplications> {
  return postVolumetricsRequest<DashboardVolumetricsTopIncidentBatchApplications>(
    "/dashboard/volumetrics/top-incident-batch-applications",
    { ...input, top_n: topN } as DashboardVolumetricsRequest & { top_n: 10 | 20 }
  );
}

export function getDashboardVolumetricsDetailedArchitectureInstallSplits(
  input: DashboardVolumetricsRequest
): Promise<DashboardVolumetricsDetailedArchitectureInstallSplits> {
  return postVolumetricsRequest<DashboardVolumetricsDetailedArchitectureInstallSplits>(
    "/dashboard/volumetrics/detailed-architecture-install-splits",
    input
  );
}

export function getDashboardVolumetricsTicketsPerUser(
  input: DashboardVolumetricsRequest,
  topN: 10 | 20
): Promise<DashboardVolumetricsTicketsPerUser> {
  return postVolumetricsRequest<DashboardVolumetricsTicketsPerUser>(
    "/dashboard/volumetrics/tickets-per-user",
    { ...input, top_n: topN } as DashboardVolumetricsRequest & { top_n: 10 | 20 }
  );
}

export function getDashboardVolumetricsDistributionSplits(
  input: DashboardVolumetricsRequest
): Promise<DashboardVolumetricsDistributionSplits> {
  return postVolumetricsRequest<DashboardVolumetricsDistributionSplits>(
    "/dashboard/volumetrics/distribution-splits",
    input
  );
}

export function getDashboardVolumetricsKpiMttrTrends(
  input: DashboardVolumetricsRequest
): Promise<DashboardVolumetricsKpiMttrTrends> {
  return postVolumetricsRequest<DashboardVolumetricsKpiMttrTrends>(
    "/dashboard/volumetrics/kpi-mttr-trends",
    input
  );
}

export function getDashboardVolumetricsKpiDurationBuckets(
  input: DashboardVolumetricsRequest
): Promise<DashboardVolumetricsKpiDurationBuckets> {
  return postVolumetricsRequest<DashboardVolumetricsKpiDurationBuckets>(
    "/dashboard/volumetrics/kpi-duration-buckets",
    input
  );
}

export function getCreatedResolvedOpenTrend(
  input: DashboardQuery
): Promise<CreatedResolvedOpenRow[]> {
  return requestJson<CreatedResolvedOpenRow[]>(
    `/dashboard/trends/created-resolved-open?${buildDashboardQuery(input)}`
  );
}

export function getMttrTrend(input: DashboardQuery): Promise<MttrTrendRow[]> {
  return requestJson<MttrTrendRow[]>(`/dashboard/trends/mttr?${buildDashboardQuery(input)}`);
}

export function getSlaTrend(input: DashboardQuery): Promise<SlaTrendRow[]> {
  return requestJson<SlaTrendRow[]>(`/dashboard/trends/sla?${buildDashboardQuery(input)}`);
}

export function getIncidentSlaTrend(input: DashboardQuery): Promise<IncidentSlaTrendRow[]> {
  return requestJson<IncidentSlaTrendRow[]>(
    `/dashboard/trends/incident-sla?${buildDashboardQuery(input)}`
  );
}

export function getIncidentSlaSummary(input: DashboardQuery): Promise<IncidentSlaSummary> {
  return requestJson<IncidentSlaSummary>(
    `/dashboard/summary/incident-sla?${buildDashboardQuery(input)}`
  );
}

export function getIncidentSlaNameBreakdown(
  input: DashboardQuery
): Promise<IncidentSlaNameBreakdown> {
  return requestJson<IncidentSlaNameBreakdown>(
    `/dashboard/breakdowns/incident-sla-names?${buildDashboardQuery(input)}&name_type=BOTH`
  );
}

export function getReopenTrend(input: DashboardQuery): Promise<ReopenTrendRow[]> {
  return requestJson<ReopenTrendRow[]>(
    `/dashboard/trends/reopen-count?${buildDashboardQuery(input)}`
  );
}

export function getReassignmentTrend(input: DashboardQuery): Promise<ReassignmentTrendRow[]> {
  return requestJson<ReassignmentTrendRow[]>(
    `/dashboard/trends/reassignment-count?${buildDashboardQuery(input)}`
  );
}

export function getCreationSourceTrend(input: DashboardQuery): Promise<CreationSourceTrendRow[]> {
  return requestJson<CreationSourceTrendRow[]>(
    `/dashboard/trends/creation-source?${buildDashboardQuery(input)}`
  );
}

export function getTechnicalFunctionalBreakdown(
  input: DashboardQuery
): Promise<TechnicalFunctionalBreakdown> {
  return requestJson<TechnicalFunctionalBreakdown>(
    `/dashboard/breakdowns/technical-functional?${buildDashboardQuery(input)}`
  );
}
