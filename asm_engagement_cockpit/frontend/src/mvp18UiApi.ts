const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8020/api";
const API_AUTH_ENABLED = String(import.meta.env.VITE_API_AUTH_ENABLED || "false").toLowerCase() === "true";
const API_AUTH_KEY = import.meta.env.VITE_API_AUTH_KEY || "";
const APP_LOGIN_REQUIRED = String(import.meta.env.VITE_APP_LOGIN_REQUIRED || "false").toLowerCase() === "true";

export const SESSION_STORAGE_KEY = "asm_engagement_cockpit_session";

export type StoredSession = {
  access_token: string;
  token_type: string;
  username: string;
  display_name: string;
  login_timestamp: string;
  expires_in_minutes: number;
};

export type LoginResponse = {
  access_token: string;
  token_type: string;
  username: string;
  display_name: string;
  expires_in_minutes: number;
};

export type StatusBucket = {
  total: number;
  not_started: number;
  in_progress: number;
  on_hold: number;
  completed: number;
  other: number;
};

export type DashboardStatusSummary = {
  engagements: StatusBucket;
  workstreams: StatusBucket;
  deliverables: StatusBucket;
  tasks: StatusBucket;
  subtasks: StatusBucket;
};

export type ReminderIndicator = {
  total_active: number;
  overdue: number;
  due_within_2_days: number;
  other_active: number;
  color: "red" | "amber" | "green" | "gray" | string;
  label: string;
};

export type EntitySummary = {
  id: string;
  external_id: string | null;
  name: string | null;
  title: string | null;
  description: string | null;
  status: string | null;
  priority: string | null;
  progress_percent: string | number | null;
  owner_name: string | null;
  secondary_owner_name?: string | null;
  ownership_rank?: number | null;
  start_date: string | null;
  target_date: string | null;
  revised_date: string | null;
  actual_date: string | null;
  created_at: string | null;
  updated_at: string | null;
};


export type RawHierarchyRecord = Record<string, string | number | null | undefined>;

function normalizeHierarchyRecord(row: RawHierarchyRecord): EntitySummary {
  return {
    id: String(row.id || ""),
    external_id: row.external_id == null ? null : String(row.external_id),
    name: row.name == null ? null : String(row.name),
    title: row.title == null ? null : String(row.title),
    description: row.description == null ? null : String(row.description),
    status: row.status == null ? null : String(row.status),
    priority: row.priority == null ? null : String(row.priority),
    progress_percent: row.progress_percent == null ? null : row.progress_percent,
    owner_name: row.owner_name == null ? null : String(row.owner_name),
    secondary_owner_name: row.secondary_owner_name == null ? null : String(row.secondary_owner_name),
    ownership_rank: row.ownership_rank == null ? null : Number(row.ownership_rank),
    start_date: row.start_date == null ? null : String(row.start_date),
    target_date: row.target_date == null
      ? row.target_completion_date == null
        ? row.target_end_date == null
          ? null
          : String(row.target_end_date)
        : String(row.target_completion_date)
      : String(row.target_date),
    revised_date: row.revised_date == null
      ? row.revised_completion_date == null
        ? row.revised_end_date == null
          ? null
          : String(row.revised_end_date)
        : String(row.revised_completion_date)
      : String(row.revised_date),
    actual_date: row.actual_date == null
      ? row.actual_completion_date == null
        ? row.actual_end_date == null
          ? null
          : String(row.actual_end_date)
        : String(row.actual_completion_date)
      : String(row.actual_date),
    created_at: row.created_at == null ? null : String(row.created_at),
    updated_at: row.updated_at == null ? null : String(row.updated_at),
  };
}

export type BreadcrumbItem = {
  entity_type: string;
  entity_id: string;
  label: string;
};

export type EngagementWorkspace = {
  engagement: EntitySummary;
  workstreams: EntitySummary[];
  breadcrumb: BreadcrumbItem[];
};

export type WorkstreamWorkspace = {
  owner_name?: string;
  engagement: EntitySummary;
  workstream: EntitySummary;
  deliverables: EntitySummary[];
  breadcrumb: BreadcrumbItem[];
};

export type DeliverableWorkspace = {
  owner_name?: string;
  engagement: EntitySummary;
  workstream: EntitySummary;
  deliverable: EntitySummary;
  tasks: EntitySummary[];
  breadcrumb: BreadcrumbItem[];
};

export type WorkspaceRecordCounts = {
  data_collections: number;
  questions: number;
  findings: number;
  analysis: number;
  evidence: number;
  files: number;
  recommendations: number;
  reminders: number;
};

export type TaskWorkspace = {
  owner_name?: string;
  engagement: EntitySummary;
  workstream: EntitySummary;
  deliverable: EntitySummary;
  task: EntitySummary;
  subtasks: EntitySummary[];
  breadcrumb: BreadcrumbItem[];
  record_counts: WorkspaceRecordCounts;
};

export type SubtaskWorkspace = {
  owner_name?: string;
  engagement: EntitySummary;
  workstream: EntitySummary;
  deliverable: EntitySummary;
  task: EntitySummary;
  subtask: EntitySummary;
  breadcrumb: BreadcrumbItem[];
  record_counts: WorkspaceRecordCounts;
};

export type HierarchyFormPayload = {
  external_id?: string | null;
  name?: string | null;
  title?: string | null;
  description?: string | null;
  status?: string | null;
  priority?: string | null;
  owner_name?: string | null;
  start_date?: string | null;
  target_end_date?: string | null;
  target_completion_date?: string | null;
  revised_end_date?: string | null;
  revised_completion_date?: string | null;
  actual_end_date?: string | null;
  actual_completion_date?: string | null;
};


export type MyWorkResponse = {
  owner_name: string;
  primary_workstreams: EntitySummary[];
  secondary_workstreams: EntitySummary[];
  primary_deliverables: EntitySummary[];
  secondary_deliverables: EntitySummary[];
  primary_tasks: EntitySummary[];
  secondary_tasks: EntitySummary[];
  counts: {
    primary_workstreams: number;
    secondary_workstreams: number;
    primary_deliverables: number;
    secondary_deliverables: number;
    primary_tasks: number;
    secondary_tasks: number;
  };
};

export type DeleteResponse = {
  deleted: boolean;
  entity_type: string;
  entity_id: string;
  message: string;
};

export function isLoginRequired(): boolean {
  return APP_LOGIN_REQUIRED;
}

export function getStoredSession(): StoredSession | null {
  const raw = window.localStorage.getItem(SESSION_STORAGE_KEY);

  if (!raw) {
    return null;
  }

  try {
    return JSON.parse(raw) as StoredSession;
  } catch {
    window.localStorage.removeItem(SESSION_STORAGE_KEY);
    return null;
  }
}

export function storeSession(response: LoginResponse): StoredSession {
  const session: StoredSession = {
    access_token: response.access_token,
    token_type: response.token_type,
    username: response.username,
    display_name: response.display_name,
    expires_in_minutes: response.expires_in_minutes,
    login_timestamp: new Date().toISOString(),
  };

  window.localStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify(session));
  return session;
}

export function clearStoredSession(): void {
  window.localStorage.removeItem(SESSION_STORAGE_KEY);
}

function getStoredSessionToken(): string {
  return getStoredSession()?.access_token || "";
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

async function responseErrorMessage(response: Response): Promise<string> {
  const fallback = `API request failed: ${response.status} ${response.statusText}`;
  const errorText = await response.text();
  if (!errorText) {
    return fallback;
  }

  try {
    const payload = JSON.parse(errorText) as { detail?: unknown };
    if (typeof payload.detail === "string") {
      return payload.detail;
    }
    if (payload.detail) {
      return `${fallback}. ${JSON.stringify(payload.detail)}`;
    }
  } catch {
    // Fall back to the raw body when the API did not return JSON.
  }

  return `${fallback}. ${errorText}`;
}

async function requestJson<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: {
      ...buildHeaders(Boolean(options.body)),
      ...(options.headers || {}),
    },
  });

  if (!response.ok) {
    throw new Error(await responseErrorMessage(response));
  }

  return response.json() as Promise<T>;
}

function getJson<T>(path: string): Promise<T> {
  return requestJson<T>(path);
}

function postJson<T>(path: string, body?: unknown): Promise<T> {
  return requestJson<T>(path, {
    method: "POST",
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

function putJson<T>(path: string, body?: unknown): Promise<T> {
  return requestJson<T>(path, {
    method: "PUT",
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

function deleteJson<T>(path: string): Promise<T> {
  return requestJson<T>(path, { method: "DELETE" });
}

async function requestFormJson<T>(path: string, method: "POST" | "PUT", body: FormData): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method,
    body,
    headers: buildHeaders(false),
  });

  if (!response.ok) {
    throw new Error(await responseErrorMessage(response));
  }

  return response.json() as Promise<T>;
}

export function login(payload: { username: string; password: string }): Promise<LoginResponse> {
  return postJson<LoginResponse>("/auth/login", payload);
}

export function getDashboardStatusSummary(): Promise<DashboardStatusSummary> {
  return getJson<DashboardStatusSummary>("/ui/dashboard-status-summary");
}

export function getReminderIndicator(): Promise<ReminderIndicator> {
  return getJson<ReminderIndicator>("/ui/reminder-indicator");
}

export function getMyWork(ownerName = "Giridhar"): Promise<MyWorkResponse> {
  return getJson<MyWorkResponse>(`/ui/my-work?owner_name=${encodeURIComponent(ownerName)}`);
}

export function getMyWorkWorkstreamWorkspace(id: string, ownerName = "Giridhar"): Promise<WorkstreamWorkspace> {
  return getJson<WorkstreamWorkspace>(`/ui/my-work/workstreams/${id}/workspace?owner_name=${encodeURIComponent(ownerName)}`);
}

export function getMyWorkDeliverableWorkspace(id: string, ownerName = "Giridhar"): Promise<DeliverableWorkspace> {
  return getJson<DeliverableWorkspace>(`/ui/my-work/deliverables/${id}/workspace?owner_name=${encodeURIComponent(ownerName)}`);
}

export function getMyWorkTaskWorkspace(id: string, ownerName = "Giridhar"): Promise<TaskWorkspace> {
  return getJson<TaskWorkspace>(`/ui/my-work/tasks/${id}/workspace?owner_name=${encodeURIComponent(ownerName)}`);
}

export function getMyWorkSubtaskWorkspace(id: string, ownerName = "Giridhar"): Promise<SubtaskWorkspace> {
  return getJson<SubtaskWorkspace>(`/ui/my-work/subtasks/${id}/workspace?owner_name=${encodeURIComponent(ownerName)}`);
}

export function getEngagements(): Promise<EntitySummary[]> {
  return getJson<EntitySummary[]>("/ui/engagements");
}

export function createEngagement(payload: HierarchyFormPayload): Promise<EntitySummary> {
  return postJson<EntitySummary>("/ui/engagements", payload);
}

export function updateEngagement(id: string, payload: HierarchyFormPayload): Promise<EntitySummary> {
  return putJson<EntitySummary>(`/ui/engagements/${id}`, payload);
}

export function deleteEngagement(id: string): Promise<DeleteResponse> {
  return deleteJson<DeleteResponse>(`/ui/engagements/${id}`);
}

export function getEngagementWorkspace(id: string): Promise<EngagementWorkspace> {
  return getJson<EngagementWorkspace>(`/ui/engagements/${id}/workspace`);
}

export function createWorkstream(engagementId: string, payload: HierarchyFormPayload): Promise<EntitySummary> {
  return postJson<EntitySummary>(`/ui/engagements/${engagementId}/workstreams`, payload);
}

export function updateWorkstream(id: string, payload: HierarchyFormPayload): Promise<EntitySummary> {
  return putJson<EntitySummary>(`/ui/workstreams/${id}`, payload);
}

export function deleteWorkstream(id: string): Promise<DeleteResponse> {
  return deleteJson<DeleteResponse>(`/ui/workstreams/${id}`);
}

export function getWorkstreamWorkspace(id: string): Promise<WorkstreamWorkspace> {
  return getJson<WorkstreamWorkspace>(`/ui/workstreams/${id}/workspace`);
}

export function createDeliverable(workstreamId: string, payload: HierarchyFormPayload): Promise<EntitySummary> {
  return postJson<EntitySummary>(`/ui/workstreams/${workstreamId}/deliverables`, payload);
}

export function updateDeliverable(id: string, payload: HierarchyFormPayload): Promise<EntitySummary> {
  return putJson<EntitySummary>(`/ui/deliverables/${id}`, payload);
}

export function deleteDeliverable(id: string): Promise<DeleteResponse> {
  return deleteJson<DeleteResponse>(`/ui/deliverables/${id}`);
}

export function getDeliverableWorkspace(id: string): Promise<DeliverableWorkspace> {
  return getJson<DeliverableWorkspace>(`/ui/deliverables/${id}/workspace`);
}

export function createTask(deliverableId: string, payload: HierarchyFormPayload): Promise<EntitySummary> {
  return postJson<EntitySummary>(`/ui/deliverables/${deliverableId}/tasks`, payload);
}

export function updateTask(id: string, payload: HierarchyFormPayload): Promise<EntitySummary> {
  return putJson<EntitySummary>(`/ui/tasks/${id}`, payload);
}

export function deleteTask(id: string): Promise<DeleteResponse> {
  return deleteJson<DeleteResponse>(`/ui/tasks/${id}`);
}

export function getTaskWorkspace(id: string): Promise<TaskWorkspace> {
  return getJson<TaskWorkspace>(`/ui/tasks/${id}/workspace`);
}

export function createSubtask(taskId: string, payload: HierarchyFormPayload): Promise<EntitySummary> {
  return postJson<EntitySummary>(`/ui/tasks/${taskId}/subtasks`, payload);
}

export function updateSubtask(id: string, payload: HierarchyFormPayload): Promise<EntitySummary> {
  return putJson<EntitySummary>(`/ui/subtasks/${id}`, payload);
}

export function deleteSubtask(id: string): Promise<DeleteResponse> {
  return deleteJson<DeleteResponse>(`/ui/subtasks/${id}`);
}

export function getSubtaskWorkspace(id: string): Promise<SubtaskWorkspace> {
  return getJson<SubtaskWorkspace>(`/ui/subtasks/${id}/workspace`);
}


export async function getAllWorkstreams(): Promise<EntitySummary[]> {
  const rows = await getJson<RawHierarchyRecord[]>("/workstreams");
  return rows.map(normalizeHierarchyRecord);
}

export async function getAllDeliverables(): Promise<EntitySummary[]> {
  const rows = await getJson<RawHierarchyRecord[]>("/deliverables");
  return rows.map(normalizeHierarchyRecord);
}

export async function getAllTasks(): Promise<EntitySummary[]> {
  const rows = await getJson<RawHierarchyRecord[]>("/tasks");
  return rows.map(normalizeHierarchyRecord);
}

export async function getAllSubtasks(): Promise<EntitySummary[]> {
  const rows = await getJson<RawHierarchyRecord[]>("/subtasks");
  return rows.map(normalizeHierarchyRecord);
}

export type WorkshopAction = {
  id: string;
  workshop_id: string;
  action_text: string;
  owner_name: string | null;
  due_date: string | null;
  status: string;
  notes: string | null;
  order_index: number;
  created_at: string;
  updated_at: string;
};

export type Workshop = {
  id: string;
  workshop_date: string;
  title: string;
  functional_track: string | null;
  participants_text: string | null;
  agenda: string | null;
  duration_hours: string | number | null;
  transcript_filename: string | null;
  transcript_content_type: string | null;
  transcript_text: string | null;
  transcript_uploaded_at: string | null;
  recording_path: string | null;
  meeting_notes: string | null;
  key_decisions: string | null;
  llm_raw_output: string | null;
  last_system_prompt: string | null;
  last_user_prompt: string | null;
  last_analyzed_at: string | null;
  created_by: string | null;
  updated_by: string | null;
  created_at: string;
  updated_at: string;
  actions: WorkshopAction[];
};

export type WorkshopListItem = {
  id: string;
  workshop_date: string;
  title: string;
  functional_track: string | null;
  duration_hours: string | number | null;
  transcript_filename: string | null;
  recording_path: string | null;
  last_analyzed_at: string | null;
  action_count: number;
};

export type WorkshopFormPayload = {
  workshop_date: string;
  title: string;
  functional_track?: string | null;
  participants_text?: string | null;
  agenda?: string | null;
  duration_hours?: string | number | null;
  recording_path?: string | null;
  transcript_file?: File | null;
};

export type WorkshopActionPayload = {
  action_text?: string;
  owner_name?: string | null;
  due_date?: string | null;
  status?: string;
  notes?: string | null;
  order_index?: number;
};

export type PromptPreview = {
  prompt_key: string;
  system_prompt: string;
  user_prompt: string;
};

export type LlmPromptTemplate = {
  id: string;
  prompt_key: string;
  name: string;
  description: string | null;
  system_prompt: string;
  user_prompt_template: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

export type LlmPromptTemplatePayload = {
  name?: string;
  description?: string | null;
  system_prompt?: string;
  user_prompt_template?: string;
  is_active?: boolean;
};

function workshopFormData(payload: WorkshopFormPayload): FormData {
  const formData = new FormData();
  formData.append("workshop_date", payload.workshop_date);
  formData.append("title", payload.title);
  formData.append("functional_track", payload.functional_track || "");
  formData.append("participants_text", payload.participants_text || "");
  formData.append("agenda", payload.agenda || "");
  formData.append("duration_hours", payload.duration_hours == null ? "" : String(payload.duration_hours));
  formData.append("recording_path", payload.recording_path || "");

  if (payload.transcript_file) {
    formData.append("transcript_file", payload.transcript_file);
  }

  return formData;
}

export function getWorkshops(): Promise<WorkshopListItem[]> {
  return getJson<WorkshopListItem[]>("/ui/workshops");
}

export function createWorkshop(payload: WorkshopFormPayload): Promise<Workshop> {
  return requestFormJson<Workshop>("/ui/workshops", "POST", workshopFormData(payload));
}

export function getWorkshop(id: string): Promise<Workshop> {
  return getJson<Workshop>(`/ui/workshops/${id}`);
}

export function updateWorkshop(id: string, payload: WorkshopFormPayload): Promise<Workshop> {
  return requestFormJson<Workshop>(`/ui/workshops/${id}`, "PUT", workshopFormData(payload));
}

export function deleteWorkshop(id: string): Promise<DeleteResponse> {
  return deleteJson<DeleteResponse>(`/ui/workshops/${id}`);
}

export function analyzeWorkshop(id: string): Promise<Workshop> {
  return postJson<Workshop>(`/ui/workshops/${id}/analyze`);
}

export function getWorkshopPromptPreview(id: string): Promise<PromptPreview> {
  return getJson<PromptPreview>(`/ui/workshops/${id}/prompt-preview`);
}

export function updateWorkshopAnalysis(id: string, payload: { meeting_notes?: string | null; key_decisions?: string | null }): Promise<Workshop> {
  return putJson<Workshop>(`/ui/workshops/${id}/analysis`, payload);
}

export function createWorkshopAction(workshopId: string, payload: Required<Pick<WorkshopActionPayload, "action_text">> & WorkshopActionPayload): Promise<WorkshopAction> {
  return postJson<WorkshopAction>(`/ui/workshops/${workshopId}/actions`, payload);
}

export function updateWorkshopAction(actionId: string, payload: WorkshopActionPayload): Promise<WorkshopAction> {
  return putJson<WorkshopAction>(`/ui/workshops/actions/${actionId}`, payload);
}

export function deleteWorkshopAction(actionId: string): Promise<DeleteResponse> {
  return deleteJson<DeleteResponse>(`/ui/workshops/actions/${actionId}`);
}

export function getLlmPrompts(): Promise<LlmPromptTemplate[]> {
  return getJson<LlmPromptTemplate[]>("/ui/llm-prompts");
}

export function updateLlmPrompt(promptKey: string, payload: LlmPromptTemplatePayload): Promise<LlmPromptTemplate> {
  return putJson<LlmPromptTemplate>(`/ui/llm-prompts/${encodeURIComponent(promptKey)}`, payload);
}
