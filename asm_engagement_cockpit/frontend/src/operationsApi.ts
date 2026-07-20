const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8020/api";
const API_AUTH_ENABLED = String(import.meta.env.VITE_API_AUTH_ENABLED || "false").toLowerCase() === "true";
const API_AUTH_KEY = import.meta.env.VITE_API_AUTH_KEY || "";

const SESSION_STORAGE_KEY = "asm_engagement_cockpit_session";

type StoredSession = {
  access_token: string;
  token_type: string;
  username: string;
  display_name: string;
  login_timestamp: string;
  expires_in_minutes: number;
};

export type AppUser = {
  id: string;
  username: string;
  display_name: string;
  email: string | null;
  role: string;
  is_active: boolean;
  source: string;
  created_at: string;
  updated_at: string;
};

export type RoleDefinition = {
  role: string;
  permissions: string[];
};

export type AuditEvent = {
  id: string;
  event_type: string;
  event_category: string;
  entity_type: string | null;
  entity_id: string | null;
  entity_title: string | null;
  actor_name: string | null;
  actor_role: string | null;
  description: string;
  details_json: string | null;
  severity: string;
  created_at: string;
};

export type OperationNotification = {
  id: string;
  notification_type: string;
  title: string;
  message: string;
  severity: string;
  status: string;
  target_role: string | null;
  target_user_name: string | null;
  source_type: string | null;
  source_id: string | null;
  due_date: string | null;
  read_at: string | null;
  dismissed_at: string | null;
  created_at: string;
  updated_at: string;
};

export type ExecutiveSummary = {
  generated_at: string;
  health_status: string;
  summary_text: string;
  counts: Record<string, number>;
  risks: string[];
  recommended_management_actions: string[];
};

export type ExecutiveSnapshot = {
  id: string;
  snapshot_title: string;
  summary_text: string;
  health_status: string;
  total_workstreams: number;
  total_deliverables: number;
  total_tasks: number;
  total_subtasks: number;
  open_reminders: number;
  open_notifications: number;
  open_review_actions: number;
  open_recommendation_actions: number;
  generated_by: string | null;
  created_at: string;
};

export type OperationsDashboard = {
  users: number;
  active_users: number;
  audit_events: number;
  unread_notifications: number;
  open_notifications: number;
  latest_audit_events: AuditEvent[];
  latest_notifications: OperationNotification[];
  executive_summary: ExecutiveSummary;
};

export type AppUserCreate = {
  username: string;
  display_name: string;
  email?: string | null;
  role: string;
  is_active: boolean;
};

export type AuditEventCreate = {
  event_type: string;
  event_category: string;
  entity_type?: string | null;
  entity_id?: string | null;
  entity_title?: string | null;
  actor_name?: string | null;
  actor_role?: string | null;
  description: string;
  details?: Record<string, unknown> | null;
  severity: string;
};

function getStoredSessionToken(): string {
  const raw = window.localStorage.getItem(SESSION_STORAGE_KEY);

  if (!raw) {
    return "";
  }

  try {
    const session = JSON.parse(raw) as StoredSession;
    return session.access_token || "";
  } catch {
    window.localStorage.removeItem(SESSION_STORAGE_KEY);
    return "";
  }
}

function buildHeaders(includeJson: boolean): HeadersInit {
  const headers: Record<string, string> = {};

  if (includeJson) {
    headers["Content-Type"] = "application/json";
  }

  if (API_AUTH_ENABLED && API_AUTH_KEY) {
    headers["X-API-Key"] = API_AUTH_KEY;
  }

  const sessionToken = getStoredSessionToken();

  if (sessionToken) {
    headers.Authorization = `Bearer ${sessionToken}`;
    headers["X-Session-Token"] = sessionToken;
  }

  return headers;
}

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: buildHeaders(false),
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`API request failed: ${response.status} ${response.statusText}. ${errorText}`);
  }

  return response.json() as Promise<T>;
}

async function postJson<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    headers: buildHeaders(true),
    body: body === undefined ? undefined : JSON.stringify(body),
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`API request failed: ${response.status} ${response.statusText}. ${errorText}`);
  }

  return response.json() as Promise<T>;
}

async function putJson<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "PUT",
    headers: buildHeaders(true),
    body: body === undefined ? undefined : JSON.stringify(body),
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`API request failed: ${response.status} ${response.statusText}. ${errorText}`);
  }

  return response.json() as Promise<T>;
}

export function bootstrapCurrentUser(): Promise<AppUser> {
  return postJson<AppUser>("/operations/bootstrap-current-user");
}

export function createAppUser(payload: AppUserCreate): Promise<AppUser> {
  return postJson<AppUser>("/operations/users", payload);
}

export function getAppUsers(): Promise<AppUser[]> {
  return getJson<AppUser[]>("/operations/users");
}

export function getRoles(): Promise<RoleDefinition[]> {
  return getJson<RoleDefinition[]>("/operations/roles");
}

export function createAuditEvent(payload: AuditEventCreate): Promise<AuditEvent> {
  return postJson<AuditEvent>("/operations/audit-events", payload);
}

export function getAuditEvents(): Promise<AuditEvent[]> {
  return getJson<AuditEvent[]>("/operations/audit-events?limit=50");
}

export function generateOperationNotifications(): Promise<OperationNotification[]> {
  return postJson<OperationNotification[]>("/operations/notifications/generate");
}

export function getOperationNotifications(): Promise<OperationNotification[]> {
  return getJson<OperationNotification[]>("/operations/notifications");
}

export function updateOperationNotification(payload: {
  notification_id: string;
  status: "Unread" | "Read" | "Dismissed";
  target_user_name?: string | null;
}): Promise<OperationNotification> {
  return putJson<OperationNotification>(
    `/operations/notifications/${payload.notification_id}`,
    {
      status: payload.status,
      target_user_name: payload.target_user_name,
    },
  );
}

export function getExecutiveSummary(): Promise<ExecutiveSummary> {
  return getJson<ExecutiveSummary>("/operations/executive-summary");
}

export function createExecutiveSnapshot(): Promise<ExecutiveSnapshot> {
  return postJson<ExecutiveSnapshot>("/operations/executive-snapshots");
}

export function getExecutiveSnapshots(): Promise<ExecutiveSnapshot[]> {
  return getJson<ExecutiveSnapshot[]>("/operations/executive-snapshots");
}

export function getOperationsDashboard(): Promise<OperationsDashboard> {
  return getJson<OperationsDashboard>("/operations/dashboard");
}