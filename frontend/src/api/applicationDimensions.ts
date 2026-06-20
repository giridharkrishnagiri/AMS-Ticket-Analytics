import { requestJson } from "./client";

export type ApplicationDimension = {
  id: string;
  project_id: string;
  customer_name: string | null;
  tower_name: string | null;
  cluster_name: string | null;
  application_group_name: string | null;
  application_name: string;
  application_alias: string | null;
  business_service_alias: string | null;
  cmdb_ci_alias: string | null;
  notes: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

export type ApplicationDimensionPayload = {
  project_id: string;
  customer_name?: string | null;
  tower_name?: string | null;
  cluster_name?: string | null;
  application_group_name?: string | null;
  application_name: string;
  application_alias?: string | null;
  business_service_alias?: string | null;
  cmdb_ci_alias?: string | null;
  notes?: string | null;
  is_active?: boolean;
};

export type BulkUploadResponse = {
  project_id: string;
  total_rows: number;
  inserted_count: number;
  updated_count: number;
  skipped_count: number;
  errors: string[];
  warnings: string[];
};

export type ValueCount = {
  value: string;
  count: number;
};

export type EnrichmentSummary = {
  project_id: string;
  total_tickets: number;
  matched_tickets: number;
  unmatched_tickets: number;
  updated_tickets: number;
  match_rate_pct: number | null;
  match_counts_by_source: Record<string, number>;
  top_unmatched_applications: ValueCount[];
  top_unmatched_business_services: ValueCount[];
  top_unmatched_cmdb_ci: ValueCount[];
  top_unmatched_service_offerings: ValueCount[];
  top_unmatched_catalog_items: ValueCount[];
};

export function listApplicationDimensions(projectId: string): Promise<ApplicationDimension[]> {
  const query = new URLSearchParams({ project_id: projectId.trim() });
  return requestJson<ApplicationDimension[]>(`/application-dimensions?${query.toString()}`);
}

export function createApplicationDimension(
  input: ApplicationDimensionPayload
): Promise<ApplicationDimension> {
  return requestJson<ApplicationDimension>("/application-dimensions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
}

export function updateApplicationDimension(
  id: string,
  input: Partial<ApplicationDimensionPayload>
): Promise<ApplicationDimension> {
  return requestJson<ApplicationDimension>(`/application-dimensions/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
}

export function deactivateApplicationDimension(id: string): Promise<ApplicationDimension> {
  return requestJson<ApplicationDimension>(`/application-dimensions/${id}`, {
    method: "DELETE",
  });
}

export function uploadApplicationDimensionsCsv(
  projectId: string,
  file: File
): Promise<BulkUploadResponse> {
  const formData = new FormData();
  formData.append("project_id", projectId.trim());
  formData.append("file", file);
  return requestJson<BulkUploadResponse>("/application-dimensions/bulk-upload", {
    method: "POST",
    body: formData,
  });
}

export function enrichApplicationDimensions(
  projectId: string,
  replaceExisting: boolean
): Promise<EnrichmentSummary> {
  return requestJson<EnrichmentSummary>("/application-dimensions/enrich-tickets", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      project_id: projectId.trim(),
      replace_existing: replaceExisting,
    }),
  });
}

export function getApplicationDimensionSummary(projectId: string): Promise<EnrichmentSummary> {
  const query = new URLSearchParams({ project_id: projectId.trim() });
  return requestJson<EnrichmentSummary>(
    `/application-dimensions/enrichment-summary?${query.toString()}`
  );
}
