export const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8001/api";

type ApiErrorPayload = {
  detail?: unknown;
};

function getErrorMessage(payload: ApiErrorPayload, status: number): string {
  if (typeof payload.detail === "string") {
    return payload.detail;
  }

  if (payload.detail && typeof payload.detail === "object") {
    const detail = payload.detail as { message?: unknown };
    if (typeof detail.message === "string") {
      return detail.message;
    }
  }

  return `Request failed with HTTP ${status}`;
}

export async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${apiBaseUrl}${path}`, init);
  } catch (error) {
    const message = error instanceof Error ? error.message : "unknown network error";
    throw new Error(`Backend request failed: ${message}`);
  }

  if (!response.ok) {
    let payload: ApiErrorPayload = {};
    try {
      payload = (await response.json()) as ApiErrorPayload;
    } catch {
      payload = {};
    }

    throw new Error(getErrorMessage(payload, response.status));
  }

  return response.json() as Promise<T>;
}
