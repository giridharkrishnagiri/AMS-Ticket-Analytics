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

  return query.toString();
}

export function getDashboardFilterValues(input: DashboardQuery): Promise<DashboardFilterValues> {
  return requestJson<DashboardFilterValues>(
    `/dashboard/filter-values?${buildDashboardQuery(input)}`
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
