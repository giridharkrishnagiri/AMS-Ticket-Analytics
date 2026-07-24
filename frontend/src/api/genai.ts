import { apiBaseUrl, requestJson } from "./client";

export type GenAITicketClassificationUsageSummary = {
  prompt_tokens: number | null;
  completion_tokens: number | null;
  estimated_cost: number | null;
  duration_ms: number | null;
};

export type GenAITicketClassificationUsageRun = {
  run_id: string;
  project_id: string;
  analysis_month: string;
  analysis_month_from?: string | null;
  analysis_month_to?: string | null;
  model_name: string | null;
  provider: string | null;
  prompt_tokens: number | null;
  completion_tokens: number | null;
  total_tokens: number | null;
  estimated_cost: number | null;
  embedding_model_name?: string | null;
  embedding_tokens?: number | null;
  embedding_cost?: number | null;
  embedding_batch_count?: number | null;
  llm_model_name?: string | null;
  llm_prompt_tokens?: number | null;
  llm_completion_tokens?: number | null;
  llm_total_tokens?: number | null;
  llm_cost?: number | null;
  llm_batch_count?: number | null;
  duration_ms: number | null;
  ticket_count: number;
  batch_count: number;
  success_batch_count: number;
  error_batch_count: number;
  started_at: string | null;
  completed_at: string | null;
};

export type GenAITicketClassificationUsageRuns = {
  project_id: string;
  analysis_month: string;
  analysis_month_from?: string | null;
  analysis_month_to?: string | null;
  runs: GenAITicketClassificationUsageRun[];
};

export type GenAITicketClassificationSummary = {
  project_id: string;
  analysis_month: string;
  analysis_month_from?: string | null;
  analysis_month_to?: string | null;
  eligible_ticket_count: number;
  analyzed_ticket_count: number;
  error_ticket_count: number;
  category_count: number;
  subcategory_1_count: number;
  subcategory_2_count: number;
  category_llm_assessed_count: number;
  category_rare_count: number;
  subcategory_1_llm_assessed_count: number;
  subcategory_1_rare_count: number;
  subcategory_2_llm_assessed_count: number;
  subcategory_2_rare_count: number;
  llm_assessed_ticket_count: number;
  rare_ticket_count: number;
  incident_count: number;
  sc_task_count: number;
  last_processed_at: string | null;
  category_quality_counts: Record<string, number>;
};

export type GenAITicketClassificationPivotRow = {
  genai_category: string | null;
  genai_subcategory_1: string | null;
  genai_subcategory_2: string | null;
  incident_count: number;
  sc_task_count: number;
  total_count: number;
};

export type GenAITicketClassificationPivot = {
  project_id: string;
  analysis_month: string;
  analysis_month_from?: string | null;
  analysis_month_to?: string | null;
  rows: GenAITicketClassificationPivotRow[];
};

export type GenAITicketAutomationSummary = {
  project_id: string;
  analysis_month: string;
  analysis_month_from?: string | null;
  analysis_month_to?: string | null;
  assessed_cluster_count: number;
  error_cluster_count: number;
  ticket_count: number;
  high_potential_count: number;
  medium_potential_count: number;
  low_potential_count: number;
  not_recommended_count: number;
  insufficient_information_count: number;
  potential_counts: Record<string, number>;
  resolution_path_counts: Record<string, number>;
  last_processed_at: string | null;
};

export type GenAITicketAutomationRow = {
  id: string;
  cluster_key: string;
  cluster_label: string;
  category: string | null;
  subcategory_1: string | null;
  ticket_type: string;
  ticket_count: number;
  incident_count: number;
  sc_task_count: number;
  automation_potential: string | null;
  recommended_resolution_path: string | null;
  primary_automation_type: string | null;
  pattern_summary: string | null;
  current_resolution_summary: string | null;
  likely_root_cause: string | null;
  automation_recommendation: string | null;
  implementation_approach: string | null;
  prerequisites: string | null;
  expected_benefits: string | null;
  risks_or_constraints: string | null;
  confidence: number | null;
  business_services: Record<string, number>;
  evidence: Record<string, unknown>;
  status: string;
  error_message: string | null;
  processed_at: string | null;
};

export type GenAITicketAutomationResults = {
  project_id: string;
  analysis_month: string;
  analysis_month_from?: string | null;
  analysis_month_to?: string | null;
  summary: GenAITicketAutomationSummary;
  rows: GenAITicketAutomationRow[];
};

export type GenAITicketClassificationRunResponse = {
  project_id: string;
  analysis_month: string;
  eligible_ticket_count: number;
  processed_count: number;
  skipped_cached_count: number;
  skipped_error_count: number;
  failed_count: number;
  remaining_ticket_count: number;
  processed_batch_count: number;
  total_batch_count: number;
  summary: GenAITicketClassificationSummary;
  usage: GenAITicketClassificationUsageSummary;
  usage_run: GenAITicketClassificationUsageRun | null;
};

export type GenAITicketCategoryQualityRunResponse = {
  project_id: string;
  analysis_month: string;
  analysis_month_from?: string | null;
  analysis_month_to?: string | null;
  run_id: string;
  eligible_ticket_count: number;
  existing_classification_count: number;
  processed_count: number;
  skipped_cached_count: number;
  skipped_missing_classification_count: number;
  skipped_blank_category_count: number;
  failed_count: number;
  remaining_ticket_count: number;
  processed_batch_count: number;
  total_batch_count: number;
  summary: GenAITicketClassificationSummary;
  usage: GenAITicketClassificationUsageSummary;
  usage_run: GenAITicketClassificationUsageRun | null;
};

export type GenAIWorkbenchSettings = {
  ticket_classification_button_enabled: boolean;
  ticket_cluster_analysis_button_enabled: boolean;
  ticket_automation_analysis_button_enabled: boolean;
  ticket_classification_model_name: string | null;
  ticket_classification_max_output_tokens: number | null;
  cluster_embedding_model_name: string;
  cluster_label_model_name: string | null;
  cluster_label_max_output_tokens: number | null;
  automation_model_name: string | null;
  automation_max_output_tokens: number | null;
  cluster_mode: string;
  cluster_level_1_mode: string;
  cluster_level_2_mode: string;
  cluster_level_3_mode: string;
  cluster_level_1_count: number;
  cluster_level_2_count: number;
  cluster_level_3_count: number;
  cluster_level_1_distance_threshold: number;
  cluster_level_2_distance_threshold: number;
  cluster_level_3_distance_threshold: number;
  cluster_embedding_batch_size: number;
  cluster_label_batch_size: number;
  cluster_min_llm_label_ticket_count: number;
  cluster_representative_ticket_count: number;
  automation_representative_ticket_count: number;
  automation_clusters_per_request: number;
  clustering_columns: string[];
  classification_columns: string[];
  automation_columns: string[];
  available_ticket_columns: Array<{
    key: string;
    label: string;
    description: string;
  }>;
};

export type GenAIWorkbenchSettingsUpdate = Partial<
  Omit<GenAIWorkbenchSettings, "available_ticket_columns">
>;

export type GenAITicketClusterRunResponse = {
  project_id: string;
  analysis_month: string;
  analysis_month_from?: string | null;
  analysis_month_to?: string | null;
  run_id: string;
  eligible_ticket_count: number;
  embedded_ticket_count: number;
  cached_embedding_count: number;
  new_embedding_count: number;
  level_1_cluster_count: number;
  level_2_cluster_count: number;
  level_3_cluster_count: number;
  labeled_cluster_count: number;
  assigned_ticket_count: number;
  failed_count: number;
  llm_labeling_enabled: boolean;
  summary: GenAITicketClassificationSummary;
  usage_run: GenAITicketClassificationUsageRun | null;
};

export type GenAITicketAutomationRunResponse = {
  project_id: string;
  analysis_month: string;
  analysis_month_from?: string | null;
  analysis_month_to?: string | null;
  run_id: string;
  eligible_cluster_count: number;
  processed_count: number;
  skipped_cached_count: number;
  failed_count: number;
  remaining_cluster_count: number;
  processed_batch_count: number;
  total_batch_count: number;
  summary: GenAITicketAutomationSummary;
  usage: GenAITicketClassificationUsageSummary;
  usage_run: GenAITicketClassificationUsageRun | null;
};

export type GenAITicketClassificationClearResponse = {
  project_id: string;
  analysis_month: string;
  analysis_month_from?: string | null;
  analysis_month_to?: string | null;
  deleted_count: number;
};

export type GenAITicketClusterClearResponse = {
  project_id: string;
  analysis_month: string;
  analysis_month_from?: string | null;
  analysis_month_to?: string | null;
  deleted_classification_count: number;
  deleted_cluster_label_count: number;
  deleted_automation_assessment_count: number;
};

export type GenAITicketAutomationClearResponse = {
  project_id: string;
  analysis_month: string;
  analysis_month_from?: string | null;
  analysis_month_to?: string | null;
  deleted_count: number;
};

export type GenAITicketEmbeddingClearResponse = {
  project_id: string;
  deleted_embedding_count: number;
};

function queryString(params: Record<string, string>): string {
  return new URLSearchParams(params).toString();
}

function monthRangeParams(
  projectId: string,
  analysisMonthFrom: string,
  analysisMonthTo?: string
): Record<string, string> {
  const params: Record<string, string> = {
    project_id: projectId,
    analysis_month: analysisMonthFrom,
  };
  if (analysisMonthTo && analysisMonthTo !== analysisMonthFrom) {
    params.analysis_month_to = analysisMonthTo;
  }
  return params;
}

function monthRangeSlug(analysisMonthFrom: string, analysisMonthTo?: string): string {
  return analysisMonthTo && analysisMonthTo !== analysisMonthFrom
    ? `${analysisMonthFrom}_to_${analysisMonthTo}`
    : analysisMonthFrom;
}

function getDownloadFilename(contentDisposition: string | null): string | null {
  if (!contentDisposition) {
    return null;
  }
  const utf8Match = contentDisposition.match(/filename\*=UTF-8''([^;]+)/i);
  if (utf8Match?.[1]) {
    return decodeURIComponent(utf8Match[1].trim());
  }
  const filenameMatch = contentDisposition.match(/filename="?([^";]+)"?/i);
  return filenameMatch?.[1]?.trim() ?? null;
}

export function getGenAIWorkbenchSettings(): Promise<GenAIWorkbenchSettings> {
  return requestJson<GenAIWorkbenchSettings>("/genai/workbench-settings");
}

export function updateGenAIWorkbenchSettings(
  payload: GenAIWorkbenchSettingsUpdate
): Promise<GenAIWorkbenchSettings> {
  return requestJson<GenAIWorkbenchSettings>("/genai/workbench-settings", {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function getTicketClassificationSummary(
  projectId: string,
  analysisMonthFrom: string,
  analysisMonthTo?: string
): Promise<GenAITicketClassificationSummary> {
  return requestJson<GenAITicketClassificationSummary>(
    `/genai/ticket-classification/summary?${queryString(
      monthRangeParams(projectId, analysisMonthFrom, analysisMonthTo)
    )}`
  );
}

export function getTicketClassificationPivot(
  projectId: string,
  analysisMonthFrom: string,
  analysisMonthTo?: string
): Promise<GenAITicketClassificationPivot> {
  return requestJson<GenAITicketClassificationPivot>(
    `/genai/ticket-classification/pivot?${queryString(
      monthRangeParams(projectId, analysisMonthFrom, analysisMonthTo)
    )}`
  );
}

export function getTicketClassificationUsageRuns(
  projectId: string,
  analysisMonthFrom: string,
  analysisMonthTo?: string
): Promise<GenAITicketClassificationUsageRuns> {
  return requestJson<GenAITicketClassificationUsageRuns>(
    `/genai/ticket-classification/usage-runs?${queryString({
      ...monthRangeParams(projectId, analysisMonthFrom, analysisMonthTo),
      limit: "10",
    })}`
  );
}

export async function downloadTicketClassificationDump(
  projectId: string,
  analysisMonthFrom: string,
  analysisMonthTo?: string
): Promise<{ blob: Blob; filename: string }> {
  const response = await fetch(
    `${apiBaseUrl}/genai/ticket-classification/ticket-dump?${queryString(
      monthRangeParams(projectId, analysisMonthFrom, analysisMonthTo)
    )}`
  );

  if (!response.ok) {
    let message = `Request failed with HTTP ${response.status}`;
    try {
      const payload = (await response.json()) as { detail?: unknown };
      if (typeof payload.detail === "string") {
        message = payload.detail;
      }
    } catch {
      // Keep the HTTP status fallback when the response is not JSON.
    }
    throw new Error(message);
  }

  return {
    blob: await response.blob(),
    filename:
      getDownloadFilename(response.headers.get("Content-Disposition")) ??
      `genai_ticket_classification_dump_${monthRangeSlug(
        analysisMonthFrom,
        analysisMonthTo
      )}.xlsx`,
  };
}

export function getTicketClusterUsageRuns(
  projectId: string,
  analysisMonthFrom: string,
  analysisMonthTo?: string
): Promise<GenAITicketClassificationUsageRuns> {
  return requestJson<GenAITicketClassificationUsageRuns>(
    `/genai/ticket-cluster-analysis/usage-runs?${queryString({
      ...monthRangeParams(projectId, analysisMonthFrom, analysisMonthTo),
      limit: "10",
    })}`
  );
}

export function getTicketCategoryQualityUsageRuns(
  projectId: string,
  analysisMonthFrom: string,
  analysisMonthTo?: string
): Promise<GenAITicketClassificationUsageRuns> {
  return requestJson<GenAITicketClassificationUsageRuns>(
    `/genai/ticket-category-quality/usage-runs?${queryString({
      ...monthRangeParams(projectId, analysisMonthFrom, analysisMonthTo),
      limit: "10",
    })}`
  );
}

export function getTicketAutomationResults(
  projectId: string,
  analysisMonthFrom: string,
  analysisMonthTo?: string
): Promise<GenAITicketAutomationResults> {
  return requestJson<GenAITicketAutomationResults>(
    `/genai/ticket-automation-analysis/results?${queryString(
      monthRangeParams(projectId, analysisMonthFrom, analysisMonthTo)
    )}`
  );
}

export function getTicketAutomationUsageRuns(
  projectId: string,
  analysisMonthFrom: string,
  analysisMonthTo?: string
): Promise<GenAITicketClassificationUsageRuns> {
  return requestJson<GenAITicketClassificationUsageRuns>(
    `/genai/ticket-automation-analysis/usage-runs?${queryString({
      ...monthRangeParams(projectId, analysisMonthFrom, analysisMonthTo),
      limit: "10",
    })}`
  );
}

export async function downloadTicketAutomationAnalysis(
  projectId: string,
  analysisMonthFrom: string,
  analysisMonthTo?: string
): Promise<{ blob: Blob; filename: string }> {
  const response = await fetch(
    `${apiBaseUrl}/genai/ticket-automation-analysis/download?${queryString(
      monthRangeParams(projectId, analysisMonthFrom, analysisMonthTo)
    )}`
  );

  if (!response.ok) {
    let message = `Request failed with HTTP ${response.status}`;
    try {
      const payload = (await response.json()) as { detail?: unknown };
      if (typeof payload.detail === "string") {
        message = payload.detail;
      }
    } catch {
      // Keep the HTTP status fallback when the response is not JSON.
    }
    throw new Error(message);
  }

  return {
    blob: await response.blob(),
    filename:
      getDownloadFilename(response.headers.get("Content-Disposition")) ??
      `genai_ticket_automation_analysis_${monthRangeSlug(
        analysisMonthFrom,
        analysisMonthTo
      )}.xlsx`,
  };
}

export function runTicketClassificationEnrichment(payload: {
  project_id: string;
  analysis_month: string;
  force_reprocess: boolean;
  batch_size: number;
  batch_limit?: number;
  run_id?: string;
}): Promise<GenAITicketClassificationRunResponse> {
  return requestJson<GenAITicketClassificationRunResponse>("/genai/ticket-classification/run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function runTicketCategoryQualityAnalysis(payload: {
  project_id: string;
  analysis_month: string;
  analysis_month_to?: string;
  force_reprocess: boolean;
  batch_size: number;
  batch_limit?: number;
  run_id?: string;
}): Promise<GenAITicketCategoryQualityRunResponse> {
  return requestJson<GenAITicketCategoryQualityRunResponse>(
    "/genai/ticket-category-quality/run",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }
  );
}

export function runTicketClusterAnalysis(payload: {
  project_id: string;
  analysis_month: string;
  analysis_month_to?: string;
  force_reprocess: boolean;
  use_llm_labels: boolean;
  run_id?: string;
}): Promise<GenAITicketClusterRunResponse> {
  return requestJson<GenAITicketClusterRunResponse>("/genai/ticket-cluster-analysis/run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function runTicketAutomationAnalysis(payload: {
  project_id: string;
  analysis_month: string;
  analysis_month_to?: string;
  force_reprocess: boolean;
  cluster_limit?: number;
  run_id?: string;
}): Promise<GenAITicketAutomationRunResponse> {
  return requestJson<GenAITicketAutomationRunResponse>(
    "/genai/ticket-automation-analysis/run",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }
  );
}

export function clearTicketClassificationAnalysis(payload: {
  project_id: string;
  analysis_month: string;
  analysis_month_to?: string;
}): Promise<GenAITicketClassificationClearResponse> {
  return requestJson<GenAITicketClassificationClearResponse>("/genai/ticket-classification/clear", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function clearTicketClusterAnalysis(payload: {
  project_id: string;
  analysis_month: string;
  analysis_month_to?: string;
}): Promise<GenAITicketClusterClearResponse> {
  return requestJson<GenAITicketClusterClearResponse>("/genai/ticket-cluster-analysis/clear", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function clearTicketAutomationAnalysis(payload: {
  project_id: string;
  analysis_month: string;
  analysis_month_to?: string;
}): Promise<GenAITicketAutomationClearResponse> {
  return requestJson<GenAITicketAutomationClearResponse>(
    "/genai/ticket-automation-analysis/clear",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }
  );
}

export function clearProjectTicketEmbeddings(payload: {
  project_id: string;
}): Promise<GenAITicketEmbeddingClearResponse> {
  return requestJson<GenAITicketEmbeddingClearResponse>("/genai/ticket-embeddings/clear", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}
