export type ToolDomain = "applications" | "tickets" | "sla_ola" | string;

export type ToolColumn = {
  key: string;
  label: string;
  type: string;
};

export type ToolCatalogItem = {
  tool_name: string;
  domain: ToolDomain;
  display_name: string;
  description: string;
  input_schema: Record<string, unknown>;
  output_schema: Record<string, unknown>;
  allowed_dimensions: string[];
  allowed_metrics: string[];
  max_rows: number;
  data_safety_level: string;
};

export type ToolCatalogResponse = {
  items: ToolCatalogItem[];
};

export type ToolExecuteRequest = {
  tool_name: string;
  customer_id: string | null;
  project_id: string | null;
  parameters: Record<string, unknown>;
  filters: Record<string, unknown>;
};

export type ToolExecuteResponse = {
  tool_name: string;
  domain: ToolDomain;
  status: "success" | "rejected" | "unsupported" | "error" | string;
  summary: {
    title: string;
    description: string | null;
  };
  columns: ToolColumn[];
  rows: Record<string, unknown>[];
  totals: Record<string, unknown>;
  applied_filters: Record<string, unknown>;
  data_notes: string[];
  warnings: string[];
  row_count: number;
  truncated: boolean;
  execution_ms: number | null;
};

export type ToolRun = {
  id: string;
  tool_name: string;
  domain: ToolDomain | null;
  customer_id: string | null;
  project_id: string | null;
  status: string;
  parameters_json: Record<string, unknown> | null;
  filters_json: Record<string, unknown> | null;
  row_count: number | null;
  truncated: boolean;
  execution_ms: number | null;
  warnings_json: string[] | null;
  error_message: string | null;
  created_at: string;
};

export type ToolRunFilters = {
  limit?: number;
  offset?: number;
  toolName?: string;
  domain?: string;
  status?: string;
};
