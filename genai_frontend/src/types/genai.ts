export type GenAIProvider = "openai" | "azure" | "anthropic" | "ollama" | "custom";
export type GenAIResponseStyle = "concise" | "standard" | "detailed";

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

export type GenAIConfig = {
  id: string;
  is_enabled: boolean;
  provider: GenAIProvider;
  model_name: string | null;
  temperature: number;
  top_p: number;
  max_output_tokens: number;
  timeout_seconds: number;
  max_tool_calls: number;
  allow_recommendations: boolean;
  allow_chart_generation: boolean;
  response_style: GenAIResponseStyle;
  created_at: string;
  updated_at: string;
};

export type GenAIConfigUpdate = Omit<GenAIConfig, "id" | "created_at" | "updated_at">;

export type GenAIPromptTemplate = {
  id: string;
  prompt_key: string;
  display_name: string;
  description: string | null;
  default_prompt: string;
  custom_prompt: string | null;
  is_custom_enabled: boolean;
  version: number;
  created_at: string;
  updated_at: string;
};

export type GenAIPromptUpdate = {
  custom_prompt: string | null;
  is_custom_enabled: boolean;
};

export type GenAISafetySettings = {
  id: string;
  allow_application_detail_rows: boolean;
  allow_ticket_detail_rows: boolean;
  allow_aggregate_ticket_data: boolean;
  allow_problem_change_data: boolean;
  allow_sla_ola_aggregate_data: boolean;
  max_rows_returned_to_llm: number;
  max_chart_data_points: number;
  enforce_complete_month_cutoff: boolean;
  mask_sensitive_fields: boolean;
  created_at: string;
  updated_at: string;
};

export type GenAISafetySettingsUpdate = Omit<
  GenAISafetySettings,
  "id" | "created_at" | "updated_at"
>;

export type GenAITestResponse = {
  ok: boolean;
  provider: string;
  model_name: string | null;
  response_text: string | null;
  duration_ms: number | null;
  usage: {
    prompt_tokens: number | null;
    completion_tokens: number | null;
    estimated_cost: number | null;
  } | null;
  error_message: string | null;
};

export type GenAIUsageLog = {
  id: string;
  customer_id: string | null;
  project_id: string | null;
  session_id: string | null;
  message_id: string | null;
  provider: string | null;
  model_name: string | null;
  operation: string;
  question: string | null;
  status: string;
  tools_used_json: Record<string, unknown> | unknown[] | null;
  prompt_tokens: number | null;
  completion_tokens: number | null;
  estimated_cost: number | null;
  duration_ms: number | null;
  error_message: string | null;
  created_at: string;
};

export type UsageLogFilters = {
  status?: string;
  operation?: string;
  limit?: number;
};
