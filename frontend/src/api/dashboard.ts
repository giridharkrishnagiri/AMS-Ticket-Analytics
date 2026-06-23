import { requestJson } from "./client";

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

export type DashboardApplicationsList = {
  total: number;
  rows: DashboardApplicationRow[];
};

export type DashboardApplicationsChartDatum = {
  label: string;
  count: number;
};

export type DashboardApplicationsCharts = {
  lifecycle_stage: DashboardApplicationsChartDatum[];
  operating_system: DashboardApplicationsChartDatum[];
  sox_scope: DashboardApplicationsChartDatum[];
  strategic: DashboardApplicationsChartDatum[];
};

export type VolumetricsScope = "in_scope" | "out_of_scope" | "all";
export type VolumetricsTicketType = "all" | "incident" | "sc_task";
export type VolumetricsTimeGrain = "monthly" | "weekly";

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
