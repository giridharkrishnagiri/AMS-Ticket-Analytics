import { useEffect, useState } from "react";

import { getGeneratedChart, listGeneratedCharts } from "../api/charts";
import { ChartList } from "../components/charts/ChartList";
import { ChartViewer } from "../components/charts/ChartViewer";
import type { GeneratedChart, GeneratedChartListItem } from "../types/charts";

const chartTypes = [
  "bar",
  "horizontal_bar",
  "line",
  "multi_line",
  "pie",
  "donut",
  "scatter",
  "scatter_3d",
  "table"
];

function errorText(error: unknown): string {
  return error instanceof Error ? error.message : "Unexpected error";
}

type AIChartsPageProps = {
  selectedChartId: string | null;
  onSelectedChartChange: (chartId: string | null) => void;
};

export function AIChartsPage({ selectedChartId, onSelectedChartChange }: AIChartsPageProps) {
  const [charts, setCharts] = useState<GeneratedChartListItem[]>([]);
  const [selectedChart, setSelectedChart] = useState<GeneratedChart | null>(null);
  const [chartTypeFilter, setChartTypeFilter] = useState("");
  const [searchText, setSearchText] = useState("");
  const [includeArchived, setIncludeArchived] = useState(false);
  const [isLoadingList, setIsLoadingList] = useState(false);
  const [isLoadingChart, setIsLoadingChart] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [messageKind, setMessageKind] = useState<"success" | "error" | "info">("info");

  async function loadCharts(
    nextChartType = chartTypeFilter,
    nextIncludeArchived = includeArchived
  ) {
    setIsLoadingList(true);
    setMessage(null);
    try {
      const result = await listGeneratedCharts({
        chartType: nextChartType || undefined,
        includeArchived: nextIncludeArchived,
        limit: 50
      });
      setCharts(result.items);
      if (!selectedChartId && result.items.length > 0) {
        onSelectedChartChange(result.items[0].id);
      }
      setMessage("Generated charts loaded.");
      setMessageKind("success");
    } catch (error) {
      setMessage(errorText(error));
      setMessageKind("error");
    } finally {
      setIsLoadingList(false);
    }
  }

  async function loadChart(chartId: string) {
    setIsLoadingChart(true);
    setMessage(null);
    try {
      const chart = await getGeneratedChart(chartId);
      setSelectedChart(chart);
      onSelectedChartChange(chartId);
    } catch (error) {
      setSelectedChart(null);
      setMessage(errorText(error));
      setMessageKind("error");
    } finally {
      setIsLoadingChart(false);
    }
  }

  useEffect(() => {
    void loadCharts();
  }, []);

  useEffect(() => {
    if (selectedChartId) {
      void loadChart(selectedChartId);
    } else {
      setSelectedChart(null);
    }
  }, [selectedChartId]);

  const visibleCharts = charts.filter((chart) => {
    const query = searchText.trim().toLowerCase();
    if (!query) {
      return true;
    }
    return chart.title.toLowerCase().includes(query);
  });

  function handleChartChanged(chart: GeneratedChart) {
    setSelectedChart(chart);
    setCharts((current) => current.map((item) => (item.id === chart.id ? chart : item)));
  }

  function handleChartDuplicated(chart: GeneratedChart) {
    setSelectedChart(chart);
    setCharts((current) => [chart, ...current]);
    onSelectedChartChange(chart.id);
  }

  function handleChartArchived(chart: GeneratedChart) {
    setCharts((current) =>
      includeArchived
        ? current.map((item) => (item.id === chart.id ? chart : item))
        : current.filter((item) => item.id !== chart.id)
    );
    setSelectedChart(null);
    onSelectedChartChange(null);
    void loadCharts();
  }

  return (
    <div className="charts-layout">
      <aside className="charts-panel" aria-label="Chart list controls">
        <div className="section-heading compact-heading">
          <div>
            <p className="eyebrow">AI Charts</p>
            <h2>Recent Charts</h2>
          </div>
          <button type="button" className="secondary-button" onClick={() => void loadCharts()}>
            {isLoadingList ? "Loading..." : "Refresh"}
          </button>
        </div>

        <label>
          <span>Search</span>
          <input
            value={searchText}
            onChange={(event) => setSearchText(event.target.value)}
            placeholder="Search chart title"
          />
        </label>

        <label>
          <span>Chart type</span>
          <select
            value={chartTypeFilter}
            onChange={(event) => {
              setChartTypeFilter(event.target.value);
              void loadCharts(event.target.value, includeArchived);
            }}
          >
            <option value="">All chart types</option>
            {chartTypes.map((chartType) => (
              <option key={chartType} value={chartType}>
                {chartType.replace("_", " ")}
              </option>
            ))}
          </select>
        </label>

        <label className="checkbox-field archived-toggle">
          <input
            type="checkbox"
            checked={includeArchived}
            onChange={(event) => {
              setIncludeArchived(event.target.checked);
              void loadCharts(chartTypeFilter, event.target.checked);
            }}
          />
          <span>Show archived</span>
        </label>

        {message ? <div className={`status-message status-${messageKind}`}>{message}</div> : null}

        <ChartList
          charts={visibleCharts}
          selectedChartId={selectedChartId}
          isLoading={isLoadingList}
          onSelect={(chartId) => onSelectedChartChange(chartId)}
        />
      </aside>

      {isLoadingChart && !selectedChart ? (
        <section className="surface chart-viewer-empty">
          <p className="loading-text">Loading chart...</p>
        </section>
      ) : (
        <ChartViewer
          chart={selectedChart}
          onChartChanged={handleChartChanged}
          onChartDuplicated={handleChartDuplicated}
          onChartArchived={handleChartArchived}
        />
      )}
    </div>
  );
}
