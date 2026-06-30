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
  | "scatter_3d"
  | "table";

export type ChartOrientation = "vertical" | "horizontal";
export type ChartDisplayMode = "2d" | "3d";
export type ChartSortOrder = "original" | "ascending" | "descending";

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
  is_archived: boolean;
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
    presentation_settings?: Partial<ChartEditSettings>;
  };
  table: ChartTable;
  source_tool_names: string[];
  source_tool_results_summary: Record<string, unknown>[];
  parameters: Record<string, unknown>;
  filters: Record<string, unknown>;
  data_notes: string[];
  warnings: string[];
};

export type ChartEditSettings = {
  title?: string;
  subtitle?: string | null;
  chart_type?: ChartType;
  orientation?: ChartOrientation;
  display_mode?: ChartDisplayMode;
  show_labels?: boolean;
  show_legend?: boolean;
  sort_order?: ChartSortOrder;
  top_n?: number | null;
  x_axis_title?: string | null;
  y_axis_title?: string | null;
  z_axis_title?: string | null;
  color_by?: string | null;
};

export type ChartDuplicateRequest = {
  title?: string;
};
