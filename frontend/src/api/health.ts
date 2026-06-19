import { requestJson } from "./client";

export type BackendHealth = {
  status: string;
  service: string;
  version: string;
  environment: string;
  checked_at: string;
  storage_root: string;
};

export async function getBackendHealth(signal?: AbortSignal): Promise<BackendHealth> {
  return requestJson<BackendHealth>("/health", { signal });
}
