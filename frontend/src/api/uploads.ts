import { requestJson } from "./client";

export type UploadBatch = {
  id: string;
  project_id: string;
  month_key: string | null;
  period_type: string;
  snapshot_date: string | null;
  batch_name: string;
  source_system: string | null;
  status: string;
  uploaded_by: string | null;
  file_count: number;
  total_size_bytes: number;
  description: string | null;
  ticket_type: string | null;
  uploaded_file_count: number | null;
  raw_row_count: number | null;
  normalized_ticket_count: number | null;
  normalized_at: string | null;
  archived_at: string | null;
  deleted_at: string | null;
  created_at: string;
  updated_at: string;
};

export type UploadBatchView = "active" | "history" | "all";

export type UploadedFile = {
  id: string;
  upload_batch_id: string;
  project_id: string;
  ticket_type: string;
  original_filename: string;
  saved_filename: string | null;
  storage_path: string;
  content_type: string | null;
  size_bytes: number;
  checksum_sha256: string | null;
  status: string;
  created_at: string;
  updated_at: string;
};

export type IngestionJob = {
  id: string;
  upload_batch_id: string;
  uploaded_file_id: string | null;
  job_type: string;
  status: string;
  rows_total: number;
  rows_processed: number;
  processed_row_count: number;
  started_at: string | null;
  completed_at: string | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
};

export type UploadResponse = {
  batch: UploadBatch;
  files: UploadedFile[];
  ingestion_jobs: IngestionJob[];
};

export type RawRowPreviewItem = {
  id: string;
  upload_batch_id: string;
  uploaded_file_id: string;
  ticket_type: string;
  row_number: number;
  source_filename: string | null;
  raw_ticket_number: string | null;
  raw_data: Record<string, unknown>;
  row_hash: string | null;
  created_at: string;
};

export type RawRowsPreviewResponse = {
  upload_batch_id: string;
  limit: number;
  rows: RawRowPreviewItem[];
  message: string | null;
};

export type RowsByUploadedFile = {
  uploaded_file_id: string;
  original_filename: string;
  saved_filename: string | null;
  row_count: number;
};

export type ValidationSummary = {
  upload_batch_id: string;
  total_raw_rows: number;
  missing_ticket_id_count: number;
  missing_created_date_count: number;
  duplicate_ticket_id_count: number;
  duplicate_ticket_ids: Record<string, number>;
  detected_source_columns: string[];
  rows_by_uploaded_file: RowsByUploadedFile[];
  message: string | null;
};

export type UploadTicketFilesInput = {
  projectId: string;
  ticketType: string;
  periodType: string;
  monthKey?: string;
  snapshotDate?: string;
  batchName: string;
  files: File[];
};

export async function uploadTicketFiles(input: UploadTicketFilesInput): Promise<UploadResponse> {
  const formData = new FormData();
  formData.append("project_id", input.projectId);
  formData.append("ticket_type", input.ticketType);
  formData.append("period_type", input.periodType);

  if (input.monthKey?.trim()) {
    formData.append("month_key", input.monthKey.trim());
  }

  if (input.snapshotDate?.trim()) {
    formData.append("snapshot_date", input.snapshotDate.trim());
  }

  formData.append("batch_name", input.batchName.trim());

  for (const file of input.files) {
    formData.append("files", file);
  }

  return requestJson<UploadResponse>("/uploads", {
    method: "POST",
    body: formData,
  });
}

export function listUploadBatches(
  projectId?: string,
  view: UploadBatchView = "all"
): Promise<UploadBatch[]> {
  const query = new URLSearchParams({ view });
  if (projectId) {
    query.set("project_id", projectId);
  }
  return requestJson<UploadBatch[]>(`/uploads/batches?${query.toString()}`);
}

export function deleteUploadBatch(uploadBatchId: string): Promise<UploadBatch> {
  return requestJson<UploadBatch>(`/uploads/batches/${uploadBatchId}`, {
    method: "DELETE",
  });
}

export function archiveUploadBatch(uploadBatchId: string): Promise<UploadBatch> {
  return requestJson<UploadBatch>(`/uploads/batches/${uploadBatchId}/archive`, {
    method: "POST",
  });
}

export function listUploadedFiles(uploadBatchId: string): Promise<UploadedFile[]> {
  return requestJson<UploadedFile[]>(`/uploads/batches/${uploadBatchId}/files`);
}

export function ingestUploadedFile(uploadedFileId: string): Promise<IngestionJob> {
  return requestJson<IngestionJob>(`/uploads/files/${uploadedFileId}/ingest`, {
    method: "POST",
  });
}

export function getIngestionJob(ingestionJobId: string): Promise<IngestionJob> {
  return requestJson<IngestionJob>(`/uploads/ingestion-jobs/${ingestionJobId}`);
}

export function getRawRowsPreview(
  uploadBatchId: string,
  limit = 5
): Promise<RawRowsPreviewResponse> {
  return requestJson<RawRowsPreviewResponse>(
    `/uploads/batches/${uploadBatchId}/raw-rows/preview?limit=${limit}`
  );
}

export function getValidationSummary(uploadBatchId: string): Promise<ValidationSummary> {
  return requestJson<ValidationSummary>(
    `/uploads/batches/${uploadBatchId}/validation-summary`
  );
}
