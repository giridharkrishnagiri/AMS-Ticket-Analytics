const configuredBaseUrl = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

export const apiBaseUrl = configuredBaseUrl.replace(/\/$/, "").endsWith("/api")
  ? configuredBaseUrl.replace(/\/$/, "")
  : `${configuredBaseUrl.replace(/\/$/, "")}/api`;

type ApiErrorPayload = {
  detail?: unknown;
};

function getErrorMessage(payload: ApiErrorPayload, status: number): string {
  if (typeof payload.detail === "string") {
    return payload.detail;
  }

  if (Array.isArray(payload.detail) && payload.detail.length > 0) {
    const firstDetail = payload.detail[0] as { msg?: unknown };
    if (typeof firstDetail.msg === "string") {
      return firstDetail.msg;
    }
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
  const headers = new Headers(init?.headers);
  if (!headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  try {
    response = await fetch(`${apiBaseUrl}${path}`, {
      ...init,
      headers
    });
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
