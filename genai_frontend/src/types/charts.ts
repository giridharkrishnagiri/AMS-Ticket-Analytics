export type ChartType =
  | "bar"
  | "horizontal_bar"
  | "grouped_bar"
  | "stacked_bar"
  | "line"
  | "multi_line"
  | "pie"
  | "donut"
  | "scatter"
  | "table";

export type ChartColumn = {
  key: string;
  label: string;
  type?: string;
};

export type ChartTable = {
  columns: ChartColumn[];
  rows: Record<string, unknown>[];
};

export type PlotlyJsonSpec = {
  data: Record<string, unknown>[];
  layout: Record<string, unknown>;
  config: Record<string, unknown>;
};

export type GeneratedChartListItem = {
  id: string;
  customer_id: string | null;
  project_id: string | null;
  session_id: string | null;
  message_id: string | null;
  title: string;
  subtitle: string | null;
  chart_type: ChartType | string;
  chart_library: string;
  created_at: string;
  updated_at: string;
};

export type GeneratedChartList = {
  items: GeneratedChartListItem[];
  total: number;
};

export type GeneratedChart = GeneratedChartListItem & {
  chart_spec: {
    title?: string;
    subtitle?: string | null;
    chart_type?: string;
    chart_library?: string;
    plotly?: PlotlyJsonSpec;
    table?: ChartTable;
    data_notes?: string[];
    warnings?: string[];
  };
  table: ChartTable;
  source_tool_names: string[];
  source_tool_results_summary: Record<string, unknown>[];
  parameters: Record<string, unknown>;
  filters: Record<string, unknown>;
  data_notes: string[];
  warnings: string[];
};
