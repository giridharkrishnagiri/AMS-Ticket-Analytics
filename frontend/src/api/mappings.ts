import { requestJson } from "./client";

export type SourceColumn = {
  name: string;
  normalized_name: string;
  occurrence_count: number;
};

export type SourceColumnsResponse = {
  upload_batch_id: string | null;
  project_id: string | null;
  ticket_type: string | null;
  source_columns: SourceColumn[];
};

export type MappingSource = "SAVED_TEMPLATE" | "BUILT_IN_SUGGESTION";
export type ApplyMappingSource = MappingSource | "REQUEST_BODY";
export type ApplyScope = "BATCH" | "TICKET_TYPE";

export type SuggestedMappingResponse = {
  upload_batch_id: string | null;
  project_id: string | null;
  ticket_type: string | null;
  mapping_source: MappingSource;
  mapping: Record<string, string>;
  source_columns: string[];
  suggested_mapping: Record<string, string>;
};

export type MappingTemplateResponse = {
  project_id: string;
  ticket_type: string;
  mapping: Record<string, string>;
};

export type NormalizationErrorSample = {
  row_number: number;
  raw_row_id: string;
  message: string;
};

export type ApplyMappingResponse = {
  upload_batch_id: string;
  status: string | null;
  total_raw_rows: number;
  normalized_ticket_count: number;
  out_of_scope_ticket_count: number;
  blank_assignment_group_count: number;
  assignment_group_not_in_inventory_count: number;
  duplicate_skipped_count: number;
  failed_row_count: number;
  warnings: string[];
  errors: NormalizationErrorSample[];
};

export type BatchApplyMappingResult = ApplyMappingResponse & {
  batch_name: string;
};

export type ScopedApplyMappingResponse = {
  scope: ApplyScope;
  project_id: string;
  ticket_type: string;
  mapping_source: ApplyMappingSource;
  saved_as_default_for_ticket_type: boolean;
  batch_results: BatchApplyMappingResult[];
  total_raw_rows: number;
  normalized_ticket_count: number;
  out_of_scope_ticket_count: number;
  blank_assignment_group_count: number;
  assignment_group_not_in_inventory_count: number;
  duplicate_skipped_count: number;
  failed_row_count: number;
  warnings: string[];
  errors: NormalizationErrorSample[];
};

export type SaveMappingTemplateInput = {
  projectId: string;
  ticketType: string;
  mapping: Record<string, string>;
};

export type ApplyMappingInput = {
  uploadBatchId: string;
  mapping: Record<string, string>;
  deleteExisting: boolean;
  saveAsDefaultForTicketType?: boolean;
};

export type ScopedApplyMappingInput = {
  projectId: string;
  ticketType: string;
  uploadBatchId?: string;
  scope: ApplyScope;
  mapping: Record<string, string>;
  deleteExisting: boolean;
  saveAsDefaultForTicketType: boolean;
};

export function getSourceColumns(uploadBatchId: string): Promise<SourceColumnsResponse> {
  return requestJson<SourceColumnsResponse>(
    `/mappings/batches/${uploadBatchId}/source-columns`
  );
}

export function getSourceColumnsForTicketType(
  projectId: string,
  ticketType: string,
  uploadBatchId?: string
): Promise<SourceColumnsResponse> {
  const query = new URLSearchParams({
    project_id: projectId,
    ticket_type: ticketType,
  });
  if (uploadBatchId) {
    query.set("upload_batch_id", uploadBatchId);
  }
  return requestJson<SourceColumnsResponse>(`/mappings/source-columns?${query.toString()}`);
}

export function getSuggestedMapping(uploadBatchId: string): Promise<SuggestedMappingResponse> {
  return requestJson<SuggestedMappingResponse>(
    `/mappings/batches/${uploadBatchId}/suggested-mapping`
  );
}

export function getSuggestedMappingForTicketType(
  projectId: string,
  ticketType: string,
  uploadBatchId?: string
): Promise<SuggestedMappingResponse> {
  const query = new URLSearchParams({
    project_id: projectId,
    ticket_type: ticketType,
  });
  if (uploadBatchId) {
    query.set("upload_batch_id", uploadBatchId);
  }
  return requestJson<SuggestedMappingResponse>(`/mappings/suggested-mapping?${query.toString()}`);
}

export function saveMappingTemplate(
  input: SaveMappingTemplateInput
): Promise<MappingTemplateResponse> {
  return requestJson<MappingTemplateResponse>("/mappings/templates", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      project_id: input.projectId,
      ticket_type: input.ticketType,
      mapping: input.mapping,
    }),
  });
}

export function getMappingTemplate(
  projectId: string,
  ticketType: string
): Promise<MappingTemplateResponse> {
  const query = new URLSearchParams({
    project_id: projectId,
    ticket_type: ticketType,
  });
  return requestJson<MappingTemplateResponse>(`/mappings/templates?${query.toString()}`);
}

export function applyMapping(input: ApplyMappingInput): Promise<ApplyMappingResponse> {
  return requestJson<ApplyMappingResponse>(
    `/mappings/batches/${input.uploadBatchId}/apply`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        mapping: input.mapping,
        delete_existing: input.deleteExisting,
        save_as_default_for_ticket_type: input.saveAsDefaultForTicketType ?? false,
      }),
    }
  );
}

export function applyMappingForScope(
  input: ScopedApplyMappingInput
): Promise<ScopedApplyMappingResponse> {
  return requestJson<ScopedApplyMappingResponse>("/mappings/apply", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      project_id: input.projectId,
      ticket_type: input.ticketType,
      upload_batch_id: input.uploadBatchId || null,
      scope: input.scope,
      mapping: input.mapping,
      delete_existing: input.deleteExisting,
      save_as_default_for_ticket_type: input.saveAsDefaultForTicketType,
    }),
  });
}
