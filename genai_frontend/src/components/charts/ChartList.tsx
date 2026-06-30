import type { GeneratedChartListItem } from "../../types/charts";

function formatDateTime(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleString();
}

type ChartListProps = {
  charts: GeneratedChartListItem[];
  selectedChartId: string | null;
  isLoading: boolean;
  onSelect: (chartId: string) => void;
};

export function ChartList({ charts, selectedChartId, isLoading, onSelect }: ChartListProps) {
  return (
    <div className="chart-list" aria-label="Generated charts">
      {isLoading ? <p className="loading-text">Loading generated charts...</p> : null}
      {charts.map((chart) => (
        <button
          key={chart.id}
          type="button"
          className={`chart-list-item ${selectedChartId === chart.id ? "active" : ""}`}
          onClick={() => onSelect(chart.id)}
        >
          <strong>{chart.title}</strong>
          <span>{chart.chart_type.replace("_", " ")}</span>
          {chart.session_id ? <span>Session {chart.session_id.slice(0, 8)}</span> : null}
          {chart.is_archived ? <span>Archived</span> : null}
          <small>{formatDateTime(chart.created_at)}</small>
        </button>
      ))}
      {charts.length === 0 && !isLoading ? (
        <div className="empty-session-list">
          Ask a chart question in Chat to generate a governed chart.
        </div>
      ) : null}
    </div>
  );
}
