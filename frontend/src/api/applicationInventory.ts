import { requestJson } from "./client";

export type ApplicationInventoryItem = {
  id: string;
  project_id: string;
  application_number_apm: string | null;
  parent_application_name: string | null;
  assignment_group: string | null;
  assignment_group_owner: string | null;
  application_owner: string | null;
  business_service_ci_name: string;
  support_lead: string | null;
  functional_track: string | null;
  ams_owner: string | null;
  supported_by_vendor: string | null;
  hosting_env: string | null;
  global_application: string | null;
  scope_status: string;
  lifecycle_stage_status: string | null;
  lifecycle_current: string | null;
  lifecycle_1_to_3_years: string | null;
  lifecycle_3_to_5_years: string | null;
  active: boolean | null;
  active_users: number | null;
  cmdb_payload: Record<string, unknown> | null;
  source_filename: string | null;
  source_row_number: number | null;
  created_at: string;
  updated_at: string;
};

export type ApplicationInventoryUploadResponse = {
  project_id: string;
  total_rows: number;
  inserted_count: number;
  updated_count: number;
  skipped_count: number;
  error_count: number;
  warning_count: number;
  errors: string[];
  warnings: string[];
  distinct_business_service_count: number;
  distinct_parent_application_count: number;
  distinct_assignment_group_count: number;
  distinct_application_owner_count: number;
  distinct_support_lead_count: number;
  distinct_functional_track_count: number;
  distinct_ams_owner_count: number;
  distinct_supported_vendor_count: number;
};

export type ValueCount = {
  value: string;
  count: number;
};

export type ApplicationInventoryEnrichmentSummary = {
  project_id: string;
  total_tickets: number;
  matched_tickets: number;
  unmatched_tickets: number;
  updated_tickets: number;
  match_rate_pct: number | null;
  matched_by_business_service_count: number;
  matched_by_application_count: number;
  unmatched_business_service_count: number;
  distinct_ticket_business_service_count: number;
  distinct_inventory_business_service_count: number;
  top_unmatched_business_services: ValueCount[];
  top_unmatched_applications: ValueCount[];
  top_unmatched_assignment_groups: ValueCount[];
};

export type UnmatchedBusinessServiceRow = {
  business_service: string;
  ticket_count: number;
  assignment_group_count: number;
  sample_assignment_groups: string[];
  sample_ticket_numbers: string[];
};

export type UnmatchedBusinessServicesResponse = {
  project_id: string;
  distinct_ticket_business_service_count: number;
  distinct_inventory_business_service_count: number;
  matched_business_service_count: number;
  unmatched_business_service_count: number;
  business_service_coverage_pct: number | null;
  rows: UnmatchedBusinessServiceRow[];
};

export type ApplicationInventoryFilterValues = {
  application_owners: string[];
  support_leads: string[];
  functional_tracks: string[];
  ams_owners: string[];
  supported_by_vendors: string[];
  hosting_envs: string[];
  parent_application_names: string[];
  business_service_ci_names: string[];
  assignment_groups: string[];
};

export type ScopeSummaryValueCount = {
  value: string;
  count: number;
};

export type ScopeSummary = {
  project_id: string;
  in_scope_tickets: number;
  out_of_scope_tickets: number;
  total_classified_tickets: number;
  in_scope_pct: number | null;
  out_of_scope_pct: number | null;
  distinct_in_scope_assignment_groups: number;
  distinct_out_of_scope_assignment_groups: number;
  top_out_of_scope_assignment_groups: ScopeSummaryValueCount[];
  top_out_of_scope_business_services: ScopeSummaryValueCount[];
};

export function listApplicationInventory(projectId: string): Promise<ApplicationInventoryItem[]> {
  const query = new URLSearchParams({ project_id: projectId.trim() });
  return requestJson<ApplicationInventoryItem[]>(`/application-inventory?${query.toString()}`);
}

export function uploadApplicationInventoryFile(
  projectId: string,
  file: File
): Promise<ApplicationInventoryUploadResponse> {
  const formData = new FormData();
  formData.append("project_id", projectId.trim());
  formData.append("file", file);

  return requestJson<ApplicationInventoryUploadResponse>("/application-inventory/upload", {
    method: "POST",
    body: formData,
  });
}

export function enrichApplicationInventory(
  projectId: string,
  replaceExisting: boolean
): Promise<ApplicationInventoryEnrichmentSummary> {
  return requestJson<ApplicationInventoryEnrichmentSummary>(
    "/application-inventory/enrich-tickets",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        project_id: projectId.trim(),
        replace_existing: replaceExisting,
      }),
    }
  );
}

export function getApplicationInventorySummary(
  projectId: string
): Promise<ApplicationInventoryEnrichmentSummary> {
  const query = new URLSearchParams({ project_id: projectId.trim() });
  return requestJson<ApplicationInventoryEnrichmentSummary>(
    `/application-inventory/enrichment-summary?${query.toString()}`
  );
}

export function getUnmatchedBusinessServices(
  projectId: string,
  limit = 50
): Promise<UnmatchedBusinessServicesResponse> {
  const query = new URLSearchParams({
    project_id: projectId.trim(),
    limit: String(limit),
  });
  return requestJson<UnmatchedBusinessServicesResponse>(
    `/application-inventory/unmatched-business-services?${query.toString()}`
  );
}

export function getApplicationInventoryFilterValues(
  projectId: string
): Promise<ApplicationInventoryFilterValues> {
  const query = new URLSearchParams({ project_id: projectId.trim() });
  return requestJson<ApplicationInventoryFilterValues>(
    `/application-inventory/filter-values?${query.toString()}`
  );
}

export function getScopeSummary(projectId: string): Promise<ScopeSummary> {
  const query = new URLSearchParams({ project_id: projectId.trim() });
  return requestJson<ScopeSummary>(`/application-inventory/scope-summary?${query.toString()}`);
}
