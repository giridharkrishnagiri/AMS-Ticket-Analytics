import type {
  AnalysisOutput,
  DashboardSummary,
  DataPoint,
  Deliverable,
  DeliverableReview,
  DeliverableReviewActionItem,
  DeliverableReviewWorkflow,
  Engagement,
  EvidenceItem,
  Finding,
  LlmRecommendation,
  LlmRecommendationActionItem,
  LlmRecommendationDecision,
  LlmRecommendationRevision,
  Reminder,
  StakeholderQuestion,
  Subtask,
  Task,
  TextRefinementRequest,
  TextRefinementResponse,
  TimesheetEntry,
  TimesheetSummary,
  UploadedFile,
  Workstream,
} from "./types";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8020/api";
const API_AUTH_ENABLED = String(import.meta.env.VITE_API_AUTH_ENABLED || "false").toLowerCase() === "true";
const API_AUTH_KEY = import.meta.env.VITE_API_AUTH_KEY || "";
const APP_LOGIN_REQUIRED = String(import.meta.env.VITE_APP_LOGIN_REQUIRED || "false").toLowerCase() === "true";

const SESSION_STORAGE_KEY = "asm_engagement_cockpit_session";

export type RuntimeDiagnostics = {
  app_name: string;
  app_env: string;
  database_status: string;
  cors_origins: string[];
  openai_model: string;
  openai_tracing: boolean;
  openai_api_key_configured: boolean;
  api_auth_enabled: boolean;
  api_auth_key_configured: boolean;
  app_login_enabled?: boolean;
  app_login_configured?: boolean;
  app_login_username?: string;
  app_session_duration_minutes?: number;
  log_requests: boolean;
};

export type FrontendRuntimeConfig = {
  api_base_url: string;
  api_auth_enabled: boolean;
  api_auth_key_configured: boolean;
  app_login_required: boolean;
  session_token_configured: boolean;
};

export type LoginResponse = {
  access_token: string;
  token_type: string;
  username: string;
  display_name: string;
  expires_in_minutes: number;
};

export type AuthStatusResponse = {
  authenticated: boolean;
  auth_type: string;
  username: string | null;
  display_name: string | null;
  expires_at: number | null;
  expires_at_utc: string | null;
};

export type StoredSession = {
  access_token: string;
  token_type: string;
  username: string;
  display_name: string;
  login_timestamp: string;
  expires_in_minutes: number;
};

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

export function storeSession(loginResponse: LoginResponse): StoredSession {
  const session: StoredSession = {
    access_token: loginResponse.access_token,
    token_type: loginResponse.token_type,
    username: loginResponse.username,
    display_name: loginResponse.display_name,
    login_timestamp: new Date().toISOString(),
    expires_in_minutes: loginResponse.expires_in_minutes,
  };

  window.localStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify(session));

  return session;
}

export function clearStoredSession(): void {
  window.localStorage.removeItem(SESSION_STORAGE_KEY);
}

export function isLoginRequired(): boolean {
  return APP_LOGIN_REQUIRED;
}

function getStoredSessionToken(): string {
  const session = getStoredSession();
  return session?.access_token ?? "";
}

function buildHeaders(extraHeaders?: HeadersInit): HeadersInit {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };

  if (API_AUTH_ENABLED && API_AUTH_KEY) {
    headers["X-API-Key"] = API_AUTH_KEY;
  }

  const sessionToken = getStoredSessionToken();

  if (sessionToken) {
    headers.Authorization = `Bearer ${sessionToken}`;
    headers["X-Session-Token"] = sessionToken;
  }

  if (extraHeaders) {
    Object.assign(headers, extraHeaders);
  }

  return headers;
}

function buildAuthHeaders(): HeadersInit {
  const headers: Record<string, string> = {};

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
    headers: buildAuthHeaders(),
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
    headers: buildHeaders(),
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
    headers: buildHeaders(),
    body: body === undefined ? undefined : JSON.stringify(body),
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`API request failed: ${response.status} ${response.statusText}. ${errorText}`);
  }

  return response.json() as Promise<T>;
}

async function postFormData<T>(path: string, formData: FormData): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    headers: buildAuthHeaders(),
    body: formData,
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`API request failed: ${response.status} ${response.statusText}. ${errorText}`);
  }

  return response.json() as Promise<T>;
}

export function getFrontendRuntimeConfig(): FrontendRuntimeConfig {
  return {
    api_base_url: API_BASE_URL,
    api_auth_enabled: API_AUTH_ENABLED,
    api_auth_key_configured: Boolean(API_AUTH_KEY),
    app_login_required: APP_LOGIN_REQUIRED,
    session_token_configured: Boolean(getStoredSessionToken()),
  };
}

export function login(payload: {
  username: string;
  password: string;
}): Promise<LoginResponse> {
  return postJson<LoginResponse>("/auth/login", payload);
}

export function getAuthStatus(): Promise<AuthStatusResponse> {
  return getJson<AuthStatusResponse>("/auth/status");
}

export function getRuntimeDiagnostics(): Promise<RuntimeDiagnostics> {
  return getJson<RuntimeDiagnostics>("/diagnostics/runtime");
}

export function getDashboardSummary(): Promise<DashboardSummary> {
  return getJson<DashboardSummary>("/dashboard/summary");
}

export function getEngagements(): Promise<Engagement[]> {
  return getJson<Engagement[]>("/engagements");
}

export function getWorkstreams(): Promise<Workstream[]> {
  return getJson<Workstream[]>("/workstreams");
}

export function getDeliverables(): Promise<Deliverable[]> {
  return getJson<Deliverable[]>("/deliverables");
}

export function getTasks(): Promise<Task[]> {
  return getJson<Task[]>("/tasks");
}

export function getSubtasks(): Promise<Subtask[]> {
  return getJson<Subtask[]>("/subtasks");
}

export function getDataPoints(): Promise<DataPoint[]> {
  return getJson<DataPoint[]>("/data-points");
}

export function getStakeholderQuestions(): Promise<StakeholderQuestion[]> {
  return getJson<StakeholderQuestion[]>("/stakeholder-questions");
}

export function getFindings(): Promise<Finding[]> {
  return getJson<Finding[]>("/findings");
}

export function getAnalysisOutputs(): Promise<AnalysisOutput[]> {
  return getJson<AnalysisOutput[]>("/analysis-outputs");
}

export function getEvidenceItems(): Promise<EvidenceItem[]> {
  return getJson<EvidenceItem[]>("/evidence-items");
}

export function getUploadedFiles(): Promise<UploadedFile[]> {
  return getJson<UploadedFile[]>("/uploaded-files");
}

export function getLlmRecommendations(): Promise<LlmRecommendation[]> {
  return getJson<LlmRecommendation[]>("/llm-recommendations");
}

export function getLlmRecommendationDecisions(): Promise<LlmRecommendationDecision[]> {
  return getJson<LlmRecommendationDecision[]>("/llm-recommendation-decisions");
}

export function getLlmRecommendationRevisions(): Promise<LlmRecommendationRevision[]> {
  return getJson<LlmRecommendationRevision[]>("/llm-recommendation-revisions");
}

export function getLlmRecommendationActionItems(): Promise<LlmRecommendationActionItem[]> {
  return getJson<LlmRecommendationActionItem[]>("/llm-recommendation-action-items");
}

export function getDeliverableReviews(): Promise<DeliverableReview[]> {
  return getJson<DeliverableReview[]>("/deliverable-reviews");
}

export function getDeliverableReviewWorkflows(): Promise<DeliverableReviewWorkflow[]> {
  return getJson<DeliverableReviewWorkflow[]>("/deliverable-review-workflows");
}

export function getDeliverableReviewActionItems(): Promise<DeliverableReviewActionItem[]> {
  return getJson<DeliverableReviewActionItem[]>("/deliverable-review-action-items");
}

export function getTimesheets(): Promise<TimesheetEntry[]> {
  return getJson<TimesheetEntry[]>("/timesheets");
}

export function getTimesheetSummaries(): Promise<TimesheetSummary[]> {
  return getJson<TimesheetSummary[]>("/timesheet-summaries");
}

export function getUploadedFileDownloadUrl(uploadedFileId: string): string {
  return `${API_BASE_URL}/uploaded-files/${uploadedFileId}/download`;
}

export function getActiveReminders(): Promise<Reminder[]> {
  return getJson<Reminder[]>("/reminders/active");
}

export function generateReminders(): Promise<{
  generated_or_updated: number;
  active_reminders: number;
}> {
  return postJson("/reminders/generate");
}

export function refineText(payload: TextRefinementRequest): Promise<TextRefinementResponse> {
  return postJson<TextRefinementResponse>("/refine-text", payload);
}

export function createFinding(payload: {
  subtask_id: string;
  title: string;
  finding_type?: string | null;
  severity?: string | null;
  finding_text: string;
  business_impact?: string | null;
  recommendation?: string | null;
  status?: string;
  confidence_level?: string | null;
}): Promise<Finding> {
  return postJson<Finding>("/findings", payload);
}

export function createAnalysisOutput(payload: {
  subtask_id: string;
  analysis_title: string;
  analysis_type?: string | null;
  analysis_text: string;
  methodology?: string | null;
  assumptions?: string | null;
  limitations?: string | null;
  status?: string;
  confidence_level?: string | null;
}): Promise<AnalysisOutput> {
  return postJson<AnalysisOutput>("/analysis-outputs", payload);
}

export function uploadFile(payload: {
  file: File;
  description?: string;
  upload_category?: string;
  subtask_id?: string;
  data_point_id?: string;
  stakeholder_question_id?: string;
  finding_id?: string;
  analysis_output_id?: string;
  evidence_item_id?: string;
  uploaded_by?: string;
}): Promise<UploadedFile> {
  const formData = new FormData();

  formData.append("file", payload.file);

  if (payload.description) formData.append("description", payload.description);
  if (payload.upload_category) formData.append("upload_category", payload.upload_category);
  if (payload.subtask_id) formData.append("subtask_id", payload.subtask_id);
  if (payload.data_point_id) formData.append("data_point_id", payload.data_point_id);
  if (payload.stakeholder_question_id) formData.append("stakeholder_question_id", payload.stakeholder_question_id);
  if (payload.finding_id) formData.append("finding_id", payload.finding_id);
  if (payload.analysis_output_id) formData.append("analysis_output_id", payload.analysis_output_id);
  if (payload.evidence_item_id) formData.append("evidence_item_id", payload.evidence_item_id);
  if (payload.uploaded_by) formData.append("uploaded_by", payload.uploaded_by);

  return postFormData<UploadedFile>("/uploaded-files", formData);
}

export function generateLlmRecommendation(payload: {
  deliverable_id?: string | null;
  task_id?: string | null;
  subtask_id?: string | null;
  finding_id?: string | null;
  analysis_output_id?: string | null;
  recommendation_type: string;
  focus_area: string;
  created_by: string;
}): Promise<LlmRecommendation> {
  return postJson<LlmRecommendation>("/llm-recommendations/generate", payload);
}

export function generateDeliverableReview(payload: {
  deliverable_id: string;
  review_type: string;
  created_by: string;
}): Promise<DeliverableReview> {
  return postJson<DeliverableReview>("/deliverable-reviews/generate", payload);
}

export function recordLlmRecommendationDecision(payload: {
  recommendation_id: string;
  decision: string;
  decision_notes?: string | null;
  decided_by?: string | null;
}): Promise<LlmRecommendationDecision> {
  return postJson<LlmRecommendationDecision>(
    `/llm-recommendations/${payload.recommendation_id}/decision`,
    {
      decision: payload.decision,
      decision_notes: payload.decision_notes,
      decided_by: payload.decided_by,
    },
  );
}

export function reviseLlmRecommendation(payload: {
  recommendation_id: string;
  title?: string | null;
  recommendation_text?: string | null;
  rationale?: string | null;
  expected_benefit?: string | null;
  implementation_notes?: string | null;
  revision_notes?: string | null;
  revised_by?: string | null;
}): Promise<LlmRecommendationRevision> {
  return putJson<LlmRecommendationRevision>(
    `/llm-recommendations/${payload.recommendation_id}/revise`,
    {
      title: payload.title,
      recommendation_text: payload.recommendation_text,
      rationale: payload.rationale,
      expected_benefit: payload.expected_benefit,
      implementation_notes: payload.implementation_notes,
      revision_notes: payload.revision_notes,
      revised_by: payload.revised_by,
    },
  );
}

export function createLlmRecommendationActionItem(payload: {
  recommendation_id: string;
  action_title: string;
  action_description?: string | null;
  owner_name?: string | null;
  priority?: string | null;
  status: string;
  due_date?: string | null;
  created_by?: string | null;
}): Promise<LlmRecommendationActionItem> {
  return postJson<LlmRecommendationActionItem>("/llm-recommendation-action-items", payload);
}

export function updateLlmRecommendationActionItem(payload: {
  action_item_id: string;
  action_title?: string | null;
  action_description?: string | null;
  owner_name?: string | null;
  priority?: string | null;
  status?: string | null;
  due_date?: string | null;
  completion_notes?: string | null;
}): Promise<LlmRecommendationActionItem> {
  return putJson<LlmRecommendationActionItem>(
    `/llm-recommendation-action-items/${payload.action_item_id}`,
    {
      action_title: payload.action_title,
      action_description: payload.action_description,
      owner_name: payload.owner_name,
      priority: payload.priority,
      status: payload.status,
      due_date: payload.due_date,
      completion_notes: payload.completion_notes,
    },
  );
}

export function markLlmRecommendationCompleted(payload: {
  recommendation_id: string;
}): Promise<{
  recommendation_id: string;
  status: string;
  message: string;
}> {
  return postJson(`/llm-recommendations/${payload.recommendation_id}/mark-completed`);
}

export function createTimesheet(payload: {
  entry_date: string;
  person_name: string;
  workstream_id?: string | null;
  deliverable_id?: string | null;
  task_id?: string | null;
  subtask_id?: string | null;
  activity_type: string;
  accomplishments: string;
  blockers?: string | null;
  next_steps?: string | null;
  effort_hours: number;
  status: string;
}): Promise<TimesheetEntry> {
  return postJson<TimesheetEntry>("/timesheets", payload);
}

export function submitTimesheetWeek(payload: {
  start_date: string;
  end_date: string;
  person_name: string;
  submitted_by: string;
}): Promise<{
  submitted_count: number;
  start_date: string;
  end_date: string;
  person_name: string;
}> {
  return postJson("/timesheets/submit-week", payload);
}

export function generateTimesheetSummary(payload: {
  start_date: string;
  end_date: string;
  person_name: string;
  summary_type: string;
  created_by: string;
}): Promise<TimesheetSummary> {
  return postJson<TimesheetSummary>("/timesheets/generate-summary", payload);
}

export function createDeliverableReviewWorkflow(payload: {
  deliverable_id: string;
  workflow_title: string;
  workflow_status: string;
  review_type: string;
  submitted_by?: string | null;
  reviewer_name?: string | null;
  reviewer_role?: string | null;
  review_due_date?: string | null;
  review_notes?: string | null;
  created_by?: string | null;
}): Promise<DeliverableReviewWorkflow> {
  return postJson<DeliverableReviewWorkflow>("/deliverable-review-workflows", payload);
}

export function recordDeliverableReviewDecision(payload: {
  workflow_id: string;
  decision: string;
  decision_by: string;
  approval_notes?: string | null;
  rework_notes?: string | null;
  review_notes?: string | null;
}): Promise<DeliverableReviewWorkflow> {
  return postJson<DeliverableReviewWorkflow>(
    `/deliverable-review-workflows/${payload.workflow_id}/decision`,
    {
      decision: payload.decision,
      decision_by: payload.decision_by,
      approval_notes: payload.approval_notes,
      rework_notes: payload.rework_notes,
      review_notes: payload.review_notes,
    },
  );
}

export function createDeliverableReviewActionItem(payload: {
  review_workflow_id: string;
  action_title: string;
  action_description?: string | null;
  owner_name?: string | null;
  priority?: string | null;
  status: string;
  due_date?: string | null;
  created_by?: string | null;
}): Promise<DeliverableReviewActionItem> {
  return postJson<DeliverableReviewActionItem>("/deliverable-review-action-items", payload);
}

export function updateDeliverableReviewActionItem(payload: {
  action_item_id: string;
  action_title?: string | null;
  action_description?: string | null;
  owner_name?: string | null;
  priority?: string | null;
  status?: string | null;
  due_date?: string | null;
  completion_notes?: string | null;
}): Promise<DeliverableReviewActionItem> {
  return putJson<DeliverableReviewActionItem>(
    `/deliverable-review-action-items/${payload.action_item_id}`,
    {
      action_title: payload.action_title,
      action_description: payload.action_description,
      owner_name: payload.owner_name,
      priority: payload.priority,
      status: payload.status,
      due_date: payload.due_date,
      completion_notes: payload.completion_notes,
    },
  );
}