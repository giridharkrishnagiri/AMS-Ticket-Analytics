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

export type InScopeAssignmentGroupPreviewRow = {
  assignment_group: string;
  functional_track: string | null;
  is_in_scope: boolean;
  source_row_number: number | null;
};

export type InScopeAssignmentGroupsImportResponse = {
  project_id: string;
  source_filename: string;
  total_rows: number;
  imported_count: number;
  skipped_count: number;
  duplicate_count: number;
  warning_count: number;
  error_count: number;
  warnings: string[];
  errors: string[];
  preview_rows: InScopeAssignmentGroupPreviewRow[];
};

export type InScopeAssignmentGroupsStatusResponse = {
  project_id: string;
  active_count: number;
  last_imported_at: string | null;
  preview_rows: InScopeAssignmentGroupPreviewRow[];
};

export type InScopeAssignmentGroupRow = {
  id: string;
  project_id: string;
  assignment_group: string;
  assignment_group_key: string;
  functional_track: string | null;
  is_in_scope: boolean;
  source_filename: string | null;
  source_row_number: number | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

export type InScopeAssignmentGroupChange = {
  id: string;
  assignment_group: string;
  previous_functional_track: string | null;
  next_functional_track: string | null;
  previous_is_in_scope: boolean;
  next_is_in_scope: boolean;
  tickets_updated: number;
};

export type InScopeAssignmentGroupsUpdateResponse = {
  project_id: string;
  submitted_count: number;
  changed_count: number;
  unchanged_count: number;
  tickets_updated_count: number;
  inventory_rows_updated_count: number;
  missing_count: number;
  warnings: string[];
  changes: InScopeAssignmentGroupChange[];
};

export type AssignmentGroupMasterPreviewRow = {
  assignment_group: string;
  description: string | null;
  manager_name: string | null;
  source_sheet_name: string | null;
  source_row_number: number | null;
};

export type AssignmentGroupMasterImportResponse = {
  project_id: string;
  source_filename: string;
  total_rows: number;
  imported_count: number;
  manager_populated_count: number;
  skipped_count: number;
  duplicate_count: number;
  warning_count: number;
  error_count: number;
  warnings: string[];
  errors: string[];
  preview_rows: AssignmentGroupMasterPreviewRow[];
};

export type AssignmentGroupMasterStatusResponse = {
  project_id: string;
  active_count: number;
  manager_populated_count: number;
  last_imported_at: string | null;
  last_imported_filename: string | null;
  preview_rows: AssignmentGroupMasterPreviewRow[];
};

export type OperationalReprocessingResponse = {
  project_id: string;
  domains: string[];
  start_point: string;
  cleared_counts: Record<string, number>;
  updated_counts: Record<string, number>;
  preserved: string[];
  warnings: string[];
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

export function importInScopeAssignmentGroups(
  projectId: string,
  file: File
): Promise<InScopeAssignmentGroupsImportResponse> {
  const body = new FormData();
  body.append("project_id", projectId);
  body.append("file", file);
  return requestJson<InScopeAssignmentGroupsImportResponse>(
    "/admin/in-scope-assignment-groups/import",
    {
      method: "POST",
      body,
    }
  );
}

export function getInScopeAssignmentGroupsStatus(
  projectId: string
): Promise<InScopeAssignmentGroupsStatusResponse> {
  const query = new URLSearchParams({ project_id: projectId.trim() });
  return requestJson<InScopeAssignmentGroupsStatusResponse>(
    `/admin/in-scope-assignment-groups/status?${query.toString()}`
  );
}

export function listInScopeAssignmentGroups(
  projectId: string,
  limit = 5000
): Promise<InScopeAssignmentGroupRow[]> {
  const query = new URLSearchParams({
    project_id: projectId.trim(),
    limit: String(limit),
  });
  return requestJson<InScopeAssignmentGroupRow[]>(
    `/admin/in-scope-assignment-groups?${query.toString()}`
  );
}

export function updateInScopeAssignmentGroups(
  projectId: string,
  rows: Array<{
    id: string;
    functional_track: string | null;
    is_in_scope: boolean;
  }>
): Promise<InScopeAssignmentGroupsUpdateResponse> {
  return requestJson<InScopeAssignmentGroupsUpdateResponse>(
    "/admin/in-scope-assignment-groups/update",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        project_id: projectId.trim(),
        rows,
      }),
    }
  );
}

export function importAssignmentGroupMasterReference(
  projectId: string,
  file: File
): Promise<AssignmentGroupMasterImportResponse> {
  const body = new FormData();
  body.append("project_id", projectId);
  body.append("file", file);
  return requestJson<AssignmentGroupMasterImportResponse>(
    "/admin/assignment-group-master-reference/import",
    {
      method: "POST",
      body,
    }
  );
}

export function getAssignmentGroupMasterReferenceStatus(
  projectId: string
): Promise<AssignmentGroupMasterStatusResponse> {
  const query = new URLSearchParams({ project_id: projectId.trim() });
  return requestJson<AssignmentGroupMasterStatusResponse>(
    `/admin/assignment-group-master-reference/status?${query.toString()}`
  );
}

export function prepareOperationalReprocessing(
  projectId: string,
  domains: string[],
  startPoint: string,
  confirmation: string
): Promise<OperationalReprocessingResponse> {
  return requestJson<OperationalReprocessingResponse>(
    "/admin/projects/prepare-operational-reprocessing",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        project_id: projectId,
        domains,
        start_point: startPoint,
        confirmation,
      }),
    }
  );
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
