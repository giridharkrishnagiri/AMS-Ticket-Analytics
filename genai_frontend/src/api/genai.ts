import { requestJson } from "./client";
import type {
  BackendHealth,
  GenAIConfig,
  GenAIConfigUpdate,
  GenAIPromptTemplate,
  GenAIPromptUpdate,
  GenAISafetySettings,
  GenAISafetySettingsUpdate,
  GenAITestResponse,
  GenAIUsageLog,
  UsageLogFilters
} from "../types/genai";

export async function getBackendHealth(signal?: AbortSignal): Promise<BackendHealth> {
  return requestJson<BackendHealth>("/health", { signal });
}

export async function getGenAIConfig(signal?: AbortSignal): Promise<GenAIConfig> {
  return requestJson<GenAIConfig>("/genai/config", { signal });
}

export async function updateGenAIConfig(payload: GenAIConfigUpdate): Promise<GenAIConfig> {
  return requestJson<GenAIConfig>("/genai/config", {
    method: "PUT",
    body: JSON.stringify(payload)
  });
}

export async function testGenAIConnection(testPrompt?: string): Promise<GenAITestResponse> {
  return requestJson<GenAITestResponse>("/genai/test", {
    method: "POST",
    body: JSON.stringify({ test_prompt: testPrompt ?? null })
  });
}

export async function listGenAIPrompts(signal?: AbortSignal): Promise<GenAIPromptTemplate[]> {
  return requestJson<GenAIPromptTemplate[]>("/genai/prompts", { signal });
}

export async function updateGenAIPrompt(
  promptKey: string,
  payload: GenAIPromptUpdate
): Promise<GenAIPromptTemplate> {
  return requestJson<GenAIPromptTemplate>(`/genai/prompts/${promptKey}`, {
    method: "PUT",
    body: JSON.stringify(payload)
  });
}

export async function resetGenAIPrompt(promptKey: string): Promise<GenAIPromptTemplate> {
  return requestJson<GenAIPromptTemplate>(`/genai/prompts/${promptKey}/reset`, {
    method: "POST",
    body: JSON.stringify({})
  });
}

export async function reseedGenAIPrompts(): Promise<{ prompt_count: number; prompt_keys: string[] }> {
  return requestJson<{ prompt_count: number; prompt_keys: string[] }>(
    "/genai/prompts/reseed-defaults",
    {
      method: "POST",
      body: JSON.stringify({})
    }
  );
}

export async function getGenAISafetySettings(signal?: AbortSignal): Promise<GenAISafetySettings> {
  return requestJson<GenAISafetySettings>("/genai/safety-settings", { signal });
}

export async function updateGenAISafetySettings(
  payload: GenAISafetySettingsUpdate
): Promise<GenAISafetySettings> {
  return requestJson<GenAISafetySettings>("/genai/safety-settings", {
    method: "PUT",
    body: JSON.stringify(payload)
  });
}

export async function listGenAIUsageLogs(
  filters: UsageLogFilters,
  signal?: AbortSignal
): Promise<GenAIUsageLog[]> {
  const params = new URLSearchParams();
  if (filters.status) {
    params.set("status", filters.status);
  }
  if (filters.operation) {
    params.set("operation", filters.operation);
  }
  if (filters.limit) {
    params.set("limit", String(filters.limit));
  }
  const query = params.toString();
  return requestJson<GenAIUsageLog[]>(`/genai/usage-logs${query ? `?${query}` : ""}`, {
    signal
  });
}
