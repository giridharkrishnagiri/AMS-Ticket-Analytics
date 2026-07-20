const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8020/api";
const API_AUTH_ENABLED = String(import.meta.env.VITE_API_AUTH_ENABLED || "false").toLowerCase() === "true";
const API_AUTH_KEY = import.meta.env.VITE_API_AUTH_KEY || "";
const SESSION_STORAGE_KEY = "asm_engagement_cockpit_session";

export type WorkspaceScopeType = "task" | "subtask";

export type StoredSession = {
  access_token: string;
  token_type: string;
  username: string;
  display_name: string;
  login_timestamp: string;
  expires_in_minutes: number;
};

export type DeleteResponse = {
  deleted: boolean;
  entity_type: string;
  entity_id: string;
  message: string;
};

export type WorkspaceDataCollection = {
  id: string;
  scope_type: string;
  scope_id: string;
  topic: string;
  source: string | null;
  details: string | null;
  status: string;
  expected_received_date: string | null;
  actual_received_date: string | null;
  data_quality: string | null;
  notes: string | null;
  created_by: string | null;
  updated_by: string | null;
  created_at: string;
  updated_at: string;
};

export type WorkspaceQuestion = {
  id: string;
  scope_type: string;
  scope_id: string;
  question_text: string;
  question_category: string | null;
  stakeholder_name: string | null;
  stakeholder_role: string | null;
  stakeholder_email: string | null;
  response_status: string;
  expected_response_date: string | null;
  actual_response_date: string | null;
  response_details: string | null;
  follow_up_required: boolean;
  follow_up_notes: string | null;
  created_by: string | null;
  updated_by: string | null;
  created_at: string;
  updated_at: string;
};

export type WorkspaceFinding = {
  id: string;
  scope_type: string;
  scope_id: string;
  title: string;
  finding_type: string | null;
  severity: string | null;
  raw_text: string | null;
  refined_text: string | null;
  finding_text: string;
  business_impact: string | null;
  recommendation: string | null;
  status: string;
  confidence_level: string | null;
  is_validated: boolean;
  created_by: string | null;
  updated_by: string | null;
  created_at: string;
  updated_at: string;
};

export type WorkspaceAnalysis = {
  id: string;
  scope_type: string;
  scope_id: string;
  analysis_title: string;
  analysis_type: string | null;
  raw_text: string | null;
  refined_text: string | null;
  analysis_text: string;
  methodology: string | null;
  assumptions: string | null;
  limitations: string | null;
  status: string;
  confidence_level: string | null;
  reviewed_by: string | null;
  reviewed_date: string | null;
  created_by: string | null;
  updated_by: string | null;
  created_at: string;
  updated_at: string;
};

export type WorkspaceEvidence = {
  id: string;
  scope_type: string;
  scope_id: string;
  title: string;
  description: string | null;
  evidence_type: string;
  source_name: string | null;
  source_reference: string | null;
  evidence_date: string | null;
  confidence_level: string | null;
  is_primary_evidence: boolean;
  created_by: string | null;
  updated_by: string | null;
  created_at: string;
  updated_at: string;
};

export type WorkspaceFile = {
  id: string;
  scope_type: string;
  scope_id: string;
  linked_entity_type: string | null;
  linked_entity_id: string | null;
  original_filename: string;
  stored_filename: string;
  storage_path: string;
  content_type: string | null;
  file_size_bytes: number | null;
  upload_category: string;
  description: string | null;
  uploaded_by: string | null;
  uploaded_at: string;
};

export type WorkspaceRecommendation = {
  id: string;
  scope_type: string;
  scope_id: string;
  recommendation_type: string;
  focus_area: string | null;
  title: string;
  ai_analysis: string | null;
  recommendation_text: string;
  additional_data_to_collect: string | null;
  additional_questions_to_ask: string | null;
  risks: string | null;
  next_steps: string | null;
  suggested_evidence: string | null;
  automation_opportunities: string | null;
  source_context_json: string | null;
  status: string;
  confidence_score: string | number | null;
  created_by: string | null;
  created_at: string;
  updated_at: string;
};

export type WorkspaceFullRecords = {
  data_collections: WorkspaceDataCollection[];
  questions: WorkspaceQuestion[];
  findings: WorkspaceFinding[];
  analysis: WorkspaceAnalysis[];
  evidence: WorkspaceEvidence[];
  files: WorkspaceFile[];
  recommendations: WorkspaceRecommendation[];
};

export type TextRefinementResponse = {
  original_text: string;
  refined_text: string;
  refinement_goal: string;
};

function getStoredSessionToken(): string {
  const raw = window.localStorage.getItem(SESSION_STORAGE_KEY);
  if (!raw) return "";

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

  if (includeJson) headers["Content-Type"] = "application/json";
  if (API_AUTH_ENABLED && API_AUTH_KEY) headers["X-API-Key"] = API_AUTH_KEY;

  const sessionToken = getStoredSessionToken();
  if (sessionToken) {
    headers.Authorization = `Bearer ${sessionToken}`;
    headers["X-Session-Token"] = sessionToken;
  }

  return headers;
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
    const errorText = await response.text();
    throw new Error(`API request failed: ${response.status} ${response.statusText}. ${errorText}`);
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

export function getWorkspaceRecords(scopeType: WorkspaceScopeType, scopeId: string): Promise<WorkspaceFullRecords> {
  return getJson<WorkspaceFullRecords>(`/ui/workspace/${scopeType}/${scopeId}/records`);
}

export function createDataCollection(scopeType: WorkspaceScopeType, scopeId: string, payload: Partial<WorkspaceDataCollection>): Promise<WorkspaceDataCollection> {
  return postJson<WorkspaceDataCollection>(`/ui/workspace/${scopeType}/${scopeId}/data-collections`, payload);
}

export function updateDataCollection(id: string, payload: Partial<WorkspaceDataCollection>): Promise<WorkspaceDataCollection> {
  return putJson<WorkspaceDataCollection>(`/ui/workspace/data-collections/${id}`, payload);
}

export function deleteDataCollection(id: string): Promise<DeleteResponse> {
  return deleteJson<DeleteResponse>(`/ui/workspace/data-collections/${id}`);
}

export function createQuestion(scopeType: WorkspaceScopeType, scopeId: string, payload: Partial<WorkspaceQuestion>): Promise<WorkspaceQuestion> {
  return postJson<WorkspaceQuestion>(`/ui/workspace/${scopeType}/${scopeId}/questions`, payload);
}

export function updateQuestion(id: string, payload: Partial<WorkspaceQuestion>): Promise<WorkspaceQuestion> {
  return putJson<WorkspaceQuestion>(`/ui/workspace/questions/${id}`, payload);
}

export function deleteQuestion(id: string): Promise<DeleteResponse> {
  return deleteJson<DeleteResponse>(`/ui/workspace/questions/${id}`);
}

export function createFinding(scopeType: WorkspaceScopeType, scopeId: string, payload: Partial<WorkspaceFinding>): Promise<WorkspaceFinding> {
  return postJson<WorkspaceFinding>(`/ui/workspace/${scopeType}/${scopeId}/findings`, payload);
}

export function updateFinding(id: string, payload: Partial<WorkspaceFinding>): Promise<WorkspaceFinding> {
  return putJson<WorkspaceFinding>(`/ui/workspace/findings/${id}`, payload);
}

export function deleteFinding(id: string): Promise<DeleteResponse> {
  return deleteJson<DeleteResponse>(`/ui/workspace/findings/${id}`);
}

export function createAnalysis(scopeType: WorkspaceScopeType, scopeId: string, payload: Partial<WorkspaceAnalysis>): Promise<WorkspaceAnalysis> {
  return postJson<WorkspaceAnalysis>(`/ui/workspace/${scopeType}/${scopeId}/analysis`, payload);
}

export function updateAnalysis(id: string, payload: Partial<WorkspaceAnalysis>): Promise<WorkspaceAnalysis> {
  return putJson<WorkspaceAnalysis>(`/ui/workspace/analysis/${id}`, payload);
}

export function deleteAnalysis(id: string): Promise<DeleteResponse> {
  return deleteJson<DeleteResponse>(`/ui/workspace/analysis/${id}`);
}

export function createEvidence(scopeType: WorkspaceScopeType, scopeId: string, payload: Partial<WorkspaceEvidence>): Promise<WorkspaceEvidence> {
  return postJson<WorkspaceEvidence>(`/ui/workspace/${scopeType}/${scopeId}/evidence`, payload);
}

export function updateEvidence(id: string, payload: Partial<WorkspaceEvidence>): Promise<WorkspaceEvidence> {
  return putJson<WorkspaceEvidence>(`/ui/workspace/evidence/${id}`, payload);
}

export function deleteEvidence(id: string): Promise<DeleteResponse> {
  return deleteJson<DeleteResponse>(`/ui/workspace/evidence/${id}`);
}

export function deleteWorkspaceFile(id: string): Promise<DeleteResponse> {
  return deleteJson<DeleteResponse>(`/ui/workspace/files/${id}`);
}

export async function uploadWorkspaceFile(params: {
  scopeType: WorkspaceScopeType;
  scopeId: string;
  file: File;
  uploadCategory: string;
  description?: string;
  linkedEntityType?: string;
  linkedEntityId?: string;
  uploadedBy?: string;
}): Promise<WorkspaceFile> {
  const formData = new FormData();
  formData.append("file", params.file);

  const query = new URLSearchParams();
  query.set("upload_category", params.uploadCategory || "General");
  if (params.description) query.set("description", params.description);
  if (params.linkedEntityType) query.set("linked_entity_type", params.linkedEntityType);
  if (params.linkedEntityId) query.set("linked_entity_id", params.linkedEntityId);
  if (params.uploadedBy) query.set("uploaded_by", params.uploadedBy);

  const response = await fetch(`${API_BASE_URL}/ui/workspace/${params.scopeType}/${params.scopeId}/files?${query.toString()}`, {
    method: "POST",
    headers: buildHeaders(false),
    body: formData,
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`API request failed: ${response.status} ${response.statusText}. ${errorText}`);
  }

  return response.json() as Promise<WorkspaceFile>;
}

export function refineWorkspaceText(payload: { text: string; refinement_goal?: string; context?: string | null }): Promise<TextRefinementResponse> {
  return postJson<TextRefinementResponse>("/ui/workspace/refine-text", {
    text: payload.text,
    refinement_goal: payload.refinement_goal || "Rewrite this as clear professional consulting analysis.",
    context: payload.context || null,
  });
}

export function generateWorkspaceRecommendation(params: {
  scopeType: WorkspaceScopeType;
  scopeId: string;
  recommendationType?: string;
  focusArea?: string;
  createdBy?: string | null;
}): Promise<WorkspaceRecommendation> {
  return postJson<WorkspaceRecommendation>(`/ui/workspace/${params.scopeType}/${params.scopeId}/generate-recommendation`, {
    recommendation_type: params.recommendationType || "Workspace Advisory",
    focus_area: params.focusArea || "Data gaps, questions, findings, risks, next steps",
    created_by: params.createdBy || null,
  });
}
