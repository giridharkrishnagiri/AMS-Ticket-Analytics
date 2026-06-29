import { requestJson } from "./client";
import type {
  ToolCatalogResponse,
  ToolExecuteRequest,
  ToolExecuteResponse,
  ToolRun,
  ToolRunFilters
} from "../types/tools";

export async function listToolCatalog(signal?: AbortSignal): Promise<ToolCatalogResponse> {
  return requestJson<ToolCatalogResponse>("/genai/tools/catalog", { signal });
}

export async function executeGovernedTool(
  payload: ToolExecuteRequest
): Promise<ToolExecuteResponse> {
  return requestJson<ToolExecuteResponse>("/genai/tools/execute", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function listToolRuns(
  filters: ToolRunFilters = {},
  signal?: AbortSignal
): Promise<ToolRun[]> {
  const params = new URLSearchParams();
  if (filters.limit) {
    params.set("limit", String(filters.limit));
  }
  if (filters.offset) {
    params.set("offset", String(filters.offset));
  }
  if (filters.toolName) {
    params.set("tool_name", filters.toolName);
  }
  if (filters.domain) {
    params.set("domain", filters.domain);
  }
  if (filters.status) {
    params.set("status", filters.status);
  }
  const query = params.toString();
  return requestJson<ToolRun[]>(`/genai/tools/runs${query ? `?${query}` : ""}`, { signal });
}
