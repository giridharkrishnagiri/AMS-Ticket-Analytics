import { requestJson } from "./client";

export type IncidentSlaUploadResponse = {
  project_id: string;
  uploaded_file_name: string;
  total_rows: number;
  inserted_rows: number;
  failed_rows: number;
  warnings: string[];
  errors: string[];
};

export type IncidentSlaEnrichResponse = {
  project_id: string;
  ticket_type: string;
  replace_existing: boolean;
  matched_ticket_count: number;
  response_sla_updated_count: number;
  resolution_sla_updated_count: number;
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
