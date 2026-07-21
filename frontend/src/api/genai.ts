import { requestJson } from "./client";

export type GenAITicketClassificationUsageSummary = {
  prompt_tokens: number | null;
  completion_tokens: number | null;
  estimated_cost: number | null;
  duration_ms: number | null;
};

export type GenAITicketClassificationSummary = {
  project_id: string;
  analysis_month: string;
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
  rows: GenAITicketClassificationPivotRow[];
};

export type GenAITicketClassificationRunResponse = {
  project_id: string;
  analysis_month: string;
  eligible_ticket_count: number;
  processed_count: number;
  skipped_cached_count: number;
  failed_count: number;
  summary: GenAITicketClassificationSummary;
  usage: GenAITicketClassificationUsageSummary;
};

export type GenAITicketClassificationClearResponse = {
  project_id: string;
  analysis_month: string;
  deleted_count: number;
};

function queryString(params: Record<string, string>): string {
  return new URLSearchParams(params).toString();
}

export function getTicketClassificationSummary(
  projectId: string,
  analysisMonth: string
): Promise<GenAITicketClassificationSummary> {
  return requestJson<GenAITicketClassificationSummary>(
    `/genai/ticket-classification/summary?${queryString({
      project_id: projectId,
      analysis_month: analysisMonth,
    })}`
  );
}

export function getTicketClassificationPivot(
  projectId: string,
  analysisMonth: string
): Promise<GenAITicketClassificationPivot> {
  return requestJson<GenAITicketClassificationPivot>(
    `/genai/ticket-classification/pivot?${queryString({
      project_id: projectId,
      analysis_month: analysisMonth,
    })}`
  );
}

export function runTicketClassificationEnrichment(payload: {
  project_id: string;
  analysis_month: string;
  force_reprocess: boolean;
  batch_size: number;
}): Promise<GenAITicketClassificationRunResponse> {
  return requestJson<GenAITicketClassificationRunResponse>("/genai/ticket-classification/run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function clearTicketClassificationAnalysis(payload: {
  project_id: string;
  analysis_month: string;
}): Promise<GenAITicketClassificationClearResponse> {
  return requestJson<GenAITicketClassificationClearResponse>("/genai/ticket-classification/clear", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}
