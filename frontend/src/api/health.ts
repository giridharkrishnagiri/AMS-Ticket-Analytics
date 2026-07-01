import { requestJson } from "./client";

export type HealthCheckItem = {
  name: string;
  status: string;
  message: string;
  duration_ms: number | null;
  details: Record<string, unknown>;
};

export type BackendHealth = {
  status: string;
  service: string;
  version: string;
  environment: string;
  checked_at: string;
  storage_root: string;
  checks?: HealthCheckItem[];
  database?: Record<string, unknown>;
  frontends?: Record<string, HealthCheckItem>;
};

export async function getBackendHealth(signal?: AbortSignal): Promise<BackendHealth> {
  return requestJson<BackendHealth>("/health", { signal });
}
