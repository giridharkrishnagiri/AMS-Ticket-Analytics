import { requestJson } from "./client";

export type IncidentSlaUploadResponse = {
  project_id: string;
  upload_id: string | null;
  uploaded_file_name: string;
  status: string;
  total_rows: number;
  inserted_rows: number;
  duplicate_rows_skipped: number;
  failed_rows: number;
  warnings: string[];
  errors: string[];
};

export type IncidentSlaUploadTotals = {
  total_files: number;
  total_rows_read: number;
  inserted_rows: number;
  duplicate_rows_skipped: number;
  error_rows: number;
};

export type IncidentSlaMultiUploadResponse = {
  project_id: string;
  files: IncidentSlaUploadResponse[];
  totals: IncidentSlaUploadTotals;
};

export type IncidentSlaUploadHistoryRow = {
  upload_id: string;
  filename: string;
  uploaded_at: string;
  total_rows_read: number;
  inserted_rows: number;
  duplicate_rows_skipped: number;
  error_rows: number;
  status: string;
};

export type IncidentSlaScopeStats = {
  incident_tickets_considered: number;
  incident_tickets_matched_to_sla_rows: number;
  incident_tickets_enriched: number;
  response_sla_enriched: number;
  resolution_sla_enriched: number;
  response_vendor_specific: number;
  response_default: number;
  response_fallback_default: number;
  response_not_found: number;
  resolution_vendor_specific: number;
  resolution_default: number;
  resolution_fallback_default: number;
  resolution_not_found: number;
};

export type IncidentSlaRowsStats = {
  total_rows: number;
  distinct_ticket_numbers_in_sla_rows: number;
  duplicate_rows_skipped_on_upload: number;
};

export type IncidentSlaUnmatchedStats = {
  sla_ticket_numbers_not_found_in_scope_or_out_of_scope: number;
  in_scope_incidents_without_sla_rows: number;
  out_of_scope_incidents_without_sla_rows: number;
};

export type IncidentSlaEnrichResponse = {
  project_id: string;
  ticket_type: string;
  replace_existing: boolean;
  matched_ticket_count: number;
  response_sla_updated_count: number;
  resolution_sla_updated_count: number;
  in_scope_incidents_considered: number;
  in_scope_incidents_enriched: number;
  out_of_scope_incidents_considered: number;
  out_of_scope_incidents_enriched: number;
  response_vendor_specific_count: number;
  response_default_count: number;
  resolution_vendor_specific_count: number;
  resolution_default_count: number;
  missing_response_sla_count: number;
  missing_resolution_sla_count: number;
  sla_rows: IncidentSlaRowsStats;
  in_scope: IncidentSlaScopeStats;
  out_of_scope: IncidentSlaScopeStats;
  unmatched: IncidentSlaUnmatchedStats;
  warnings: string[];
};

export type IncidentSlaSummaryResponse = {
  project_id: string;
  total_sla_rows: number;
  unique_incident_numbers: number;
  matched_tickets_count: number;
  unmatched_sla_incident_numbers_count: number;
  tickets_with_response_sla_selected: number;
  tickets_with_resolution_sla_selected: number;
  response_accenture_selected_count: number;
  response_default_selected_count: number;
  resolution_accenture_selected_count: number;
  resolution_default_selected_count: number;
  response_breached_count: number;
  resolution_breached_count: number;
};

export type IncidentSlaUnmatchedRow = {
  inc_number: string;
  row_count: number;
};

export type IncidentSlaUnmatchedResponse = {
  project_id: string;
  limit: number;
  offset: number;
  rows: IncidentSlaUnmatchedRow[];
};

export type IncidentSlaDeduplicateResponse = {
  project_id: string;
  duplicate_groups_found: number;
  duplicate_rows_deleted: number;
  remaining_sla_rows: number;
};

export function uploadIncidentSlaFile(
  projectId: string,
  file: File
): Promise<IncidentSlaUploadResponse> {
  const formData = new FormData();
  formData.append("project_id", projectId.trim());
  formData.append("file", file);

  return requestJson<IncidentSlaUploadResponse>("/sla/incidents/upload", {
    method: "POST",
    body: formData,
  });
}

export function uploadIncidentSlaFiles(
  projectId: string,
  files: File[]
): Promise<IncidentSlaMultiUploadResponse> {
  const formData = new FormData();
  formData.append("project_id", projectId.trim());
  files.forEach((file) => formData.append("files", file));

  return requestJson<IncidentSlaMultiUploadResponse>("/sla/incidents/upload-multiple", {
    method: "POST",
    body: formData,
  });
}

export function enrichIncidentSla(
  projectId: string,
  replaceExisting = true
): Promise<IncidentSlaEnrichResponse> {
  return requestJson<IncidentSlaEnrichResponse>("/sla/incidents/enrich", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      project_id: projectId.trim(),
      ticket_type: "INCIDENT",
      replace_existing: replaceExisting,
    }),
  });
}

export function getIncidentSlaSummary(projectId: string): Promise<IncidentSlaSummaryResponse> {
  const query = new URLSearchParams({ project_id: projectId.trim() });
  return requestJson<IncidentSlaSummaryResponse>(`/sla/incidents/summary?${query.toString()}`);
}

export function getUnmatchedIncidentSlaNumbers(
  projectId: string,
  limit = 100,
  offset = 0
): Promise<IncidentSlaUnmatchedResponse> {
  const query = new URLSearchParams({
    project_id: projectId.trim(),
    limit: String(limit),
    offset: String(offset),
  });
  return requestJson<IncidentSlaUnmatchedResponse>(`/sla/incidents/unmatched?${query.toString()}`);
}

export function getIncidentSlaUploadHistory(
  projectId: string
): Promise<IncidentSlaUploadHistoryRow[]> {
  const query = new URLSearchParams({ project_id: projectId.trim() });
  return requestJson<IncidentSlaUploadHistoryRow[]>(`/sla/incidents/uploads?${query.toString()}`);
}

export function deduplicateIncidentSlaRows(
  projectId: string,
  confirmation: string
): Promise<IncidentSlaDeduplicateResponse> {
  return requestJson<IncidentSlaDeduplicateResponse>("/sla/deduplicate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      project_id: projectId.trim(),
      confirmation,
    }),
  });
}
