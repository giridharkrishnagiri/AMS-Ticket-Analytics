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

export type GenAIWorkbenchSettings = {
  ticket_classification_button_enabled: boolean;
  ticket_cluster_analysis_button_enabled: boolean;
  cluster_embedding_model_name: string;
  cluster_label_model_name: string | null;
  cluster_mode: string;
  cluster_level_1_count: number;
  cluster_level_2_count: number;
  cluster_level_3_count: number;
  cluster_level_1_distance_threshold: number;
  cluster_level_2_distance_threshold: number;
  cluster_level_3_distance_threshold: number;
  cluster_embedding_batch_size: number;
  cluster_label_batch_size: number;
};

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
  summary: GenAITicketClassificationSummary;
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
      )}.csv`,
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

export function runTicketClusterAnalysis(payload: {
  project_id: string;
  analysis_month: string;
  analysis_month_to?: string;
  force_reprocess: boolean;
  run_id?: string;
}): Promise<GenAITicketClusterRunResponse> {
  return requestJson<GenAITicketClusterRunResponse>("/genai/ticket-cluster-analysis/run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
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
