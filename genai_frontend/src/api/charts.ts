import { requestJson } from "./client";
import type { GeneratedChart, GeneratedChartList } from "../types/charts";

export type ChartListFilters = {
  customerId?: string | null;
  projectId?: string | null;
  sessionId?: string | null;
  chartType?: string;
  limit?: number;
  offset?: number;
};

function chartListQuery(filters: ChartListFilters): string {
  const params = new URLSearchParams();
  if (filters.customerId) {
    params.set("customer_id", filters.customerId);
  }
  if (filters.projectId) {
    params.set("project_id", filters.projectId);
  }
  if (filters.sessionId) {
    params.set("session_id", filters.sessionId);
  }
  if (filters.chartType) {
    params.set("chart_type", filters.chartType);
  }
  if (filters.limit) {
    params.set("limit", String(filters.limit));
  }
  if (filters.offset) {
    params.set("offset", String(filters.offset));
  }
  const query = params.toString();
  return query ? `?${query}` : "";
}

export async function listGeneratedCharts(
  filters: ChartListFilters = {},
  signal?: AbortSignal
): Promise<GeneratedChartList> {
  return requestJson<GeneratedChartList>(`/genai/charts${chartListQuery(filters)}`, { signal });
}

export async function getGeneratedChart(
  chartId: string,
  signal?: AbortSignal
): Promise<GeneratedChart> {
  return requestJson<GeneratedChart>(`/genai/charts/${chartId}`, { signal });
}
