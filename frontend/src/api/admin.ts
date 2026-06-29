import { requestJson } from "./client";

export type OperationalDataResetResponse = {
  deleted_counts: Record<string, number>;
  updated_counts?: Record<string, number>;
  preserved: string[];
  reset_incidents?: boolean | null;
  reset_sc_tasks?: boolean | null;
  reset_problems?: boolean | null;
  reset_changes?: boolean | null;
  reset_incident_sla?: boolean | null;
  incident_sla_reset_reason?: string | null;
};

export type DashboardFilterCacheStatusItem = {
  dashboard_area: string;
  status: string;
  data_version: string | null;
  last_success_at: string | null;
  is_stale: boolean;
  error_message: string | null;
};

export type DashboardFilterCacheStatusResponse = {
  items: DashboardFilterCacheStatusItem[];
};

export type DashboardFilterCacheRefreshResponse = {
  status: string;
  dashboard_area: string;
  data_version: string;
  facts_count: number;
  catalog_count: number;
  duration_ms: number;
};

export function resetOperationalData(
  confirmation: string
): Promise<OperationalDataResetResponse> {
  return requestJson<OperationalDataResetResponse>("/admin/reset-operational-data", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ confirmation }),
  });
}

export function resetProjectOperationalData(
  projectId: string,
  confirmation: string,
  options: {
    resetIncidents: boolean;
    resetScTasks: boolean;
    resetProblems: boolean;
    resetChanges: boolean;
    resetIncidentSla: boolean;
  }
): Promise<OperationalDataResetResponse> {
  return requestJson<OperationalDataResetResponse>("/admin/projects/reset-operational-data", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      project_id: projectId,
      confirmation,
      reset_incidents: options.resetIncidents,
      reset_sc_tasks: options.resetScTasks,
      reset_problems: options.resetProblems,
      reset_changes: options.resetChanges,
      reset_incident_sla: options.resetIncidentSla,
    }),
  });
}

export function deleteProjectAndRelatedData(
  projectId: string,
  confirmation: string
): Promise<OperationalDataResetResponse> {
  return requestJson<OperationalDataResetResponse>("/admin/projects/delete", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ project_id: projectId, confirmation }),
  });
}

export function deleteClientAndRelatedData(
  clientId: string,
  confirmation: string
): Promise<OperationalDataResetResponse> {
  return requestJson<OperationalDataResetResponse>("/admin/clients/delete", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ client_id: clientId, confirmation }),
  });
}

export function getDashboardFilterCacheStatus(
  customerId: string,
  projectId: string
): Promise<DashboardFilterCacheStatusResponse> {
  const query = new URLSearchParams({
    customer_id: customerId.trim(),
    project_id: projectId.trim(),
  });
  return requestJson<DashboardFilterCacheStatusResponse>(
    `/dashboard/filter-cache/status?${query.toString()}`
  );
}

export function refreshDashboardFilterCache(
  customerId: string,
  projectId: string,
  dashboardArea: "applications" | "volumetrics" | "all"
): Promise<DashboardFilterCacheRefreshResponse> {
  return requestJson<DashboardFilterCacheRefreshResponse>("/dashboard/filter-cache/refresh", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      customer_id: customerId.trim(),
      project_id: projectId.trim(),
      dashboard_area: dashboardArea,
    }),
  });
}
