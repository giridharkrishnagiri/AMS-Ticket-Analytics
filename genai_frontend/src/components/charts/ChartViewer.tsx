import { useEffect, useMemo, useState } from "react";
import type { Dispatch, SetStateAction } from "react";
import createPlotlyComponent from "react-plotly.js/factory";
import Plotly from "plotly.js-dist-min";

import {
  archiveGeneratedChart,
  duplicateGeneratedChart,
  resetGeneratedChart,
  updateGeneratedChart
} from "../../api/charts";
import { ChartDataTable } from "./ChartDataTable";
import type {
  ChartDisplayMode,
  ChartEditSettings,
  ChartOrientation,
  ChartSortOrder,
  ChartType,
  GeneratedChart
} from "../../types/charts";

type PlotlyGraphDiv = HTMLElement;
const Plot = createPlotlyComponent(
  Plotly as unknown as Parameters<typeof createPlotlyComponent>[0]
);

const chartTypeOptions: ChartType[] = [
  "bar",
  "horizontal_bar",
  "grouped_bar",
  "stacked_bar",
  "line",
  "multi_line",
  "pie",
  "donut",
  "scatter",
  "scatter_3d",
  "table"
];

type ChartForm = {
  title: string;
  subtitle: string;
  chart_type: ChartType;
  orientation: ChartOrientation;
  display_mode: ChartDisplayMode;
  show_labels: boolean;
  show_legend: boolean;
  sort_order: ChartSortOrder;
  top_n: string;
  x_axis_title: string;
  y_axis_title: string;
  z_axis_title: string;
};

type ChartViewerProps = {
  chart: GeneratedChart | null;
  onChartChanged: (chart: GeneratedChart) => void;
  onChartDuplicated: (chart: GeneratedChart) => void;
  onChartArchived: (chart: GeneratedChart) => void;
};

function safeFilename(title: string): string {
  const stamp = new Date()
    .toISOString()
    .replace(/[-:]/g, "")
    .replace(/\.\d{3}Z$/, "")
    .replace("T", "_");
  const safeTitle =
    title
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "_")
      .replace(/^_|_$/g, "") || "genai_chart";
  return `AMS_GenAI_Chart_${safeTitle}_${stamp}.png`;
}

function noteList({
  title,
  values,
  kind
}: {
  title: string;
  values: string[];
  kind: "note" | "warning";
}) {
  if (values.length === 0) {
    return null;
  }
  return (
    <div className={kind === "note" ? "note-list" : "warning-list"}>
      <strong>{title}</strong>
      <ul>
        {values.map((value) => (
          <li key={value}>{value}</li>
        ))}
      </ul>
    </div>
  );
}

function formFromChart(chart: GeneratedChart): ChartForm {
  const settings = chart.chart_spec.presentation_settings ?? {};
  const chartType = chart.chart_type as ChartType;
  return {
    title: chart.title,
    subtitle: chart.subtitle ?? "",
    chart_type: (settings.chart_type as ChartType | undefined) ?? chartType,
    orientation:
      (settings.orientation as ChartOrientation | undefined) ??
      (chart.chart_type === "horizontal_bar" ? "horizontal" : "vertical"),
    display_mode:
      (settings.display_mode as ChartDisplayMode | undefined) ??
      (chart.chart_type === "scatter_3d" ? "3d" : "2d"),
    show_labels: settings.show_labels !== false,
    show_legend: settings.show_legend !== false,
    sort_order: (settings.sort_order as ChartSortOrder | undefined) ?? "original",
    top_n: settings.top_n ? String(settings.top_n) : "",
    x_axis_title: typeof settings.x_axis_title === "string" ? settings.x_axis_title : "",
    y_axis_title: typeof settings.y_axis_title === "string" ? settings.y_axis_title : "",
    z_axis_title: typeof settings.z_axis_title === "string" ? settings.z_axis_title : ""
  };
}

function updatePayload(form: ChartForm): ChartEditSettings {
  return {
    title: form.title.trim(),
    subtitle: form.subtitle.trim() || null,
    chart_type: form.chart_type,
    orientation: form.orientation,
    display_mode: form.display_mode,
    show_labels: form.show_labels,
    show_legend: form.show_legend,
    sort_order: form.sort_order,
    top_n: form.top_n ? Number(form.top_n) : null,
    x_axis_title: form.x_axis_title.trim() || null,
    y_axis_title: form.y_axis_title.trim() || null,
    z_axis_title: form.z_axis_title.trim() || null
  };
}

function setFormField<K extends keyof ChartForm>(
  setForm: Dispatch<SetStateAction<ChartForm | null>>,
  key: K,
  value: ChartForm[K]
) {
  setForm((current) => (current ? { ...current, [key]: value } : current));
}

export function ChartViewer({
  chart,
  onChartChanged,
  onChartDuplicated,
  onChartArchived
}: ChartViewerProps) {
  const [graphDiv, setGraphDiv] = useState<PlotlyGraphDiv | null>(null);
  const [form, setForm] = useState<ChartForm | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [messageKind, setMessageKind] = useState<"success" | "error" | "info">("info");
  const [isSaving, setIsSaving] = useState(false);
  const [isCopying, setIsCopying] = useState(false);
  const [isResetting, setIsResetting] = useState(false);
  const [isArchiving, setIsArchiving] = useState(false);

  const plotly = chart?.chart_spec.plotly;
  const table = chart?.table ?? { columns: [], rows: [] };
  const plotConfig = useMemo(
    () => ({
      responsive: true,
      displaylogo: false,
      ...(plotly?.config ?? {})
    }),
    [plotly?.config]
  );

  useEffect(() => {
    setForm(chart ? formFromChart(chart) : null);
    setGraphDiv(null);
    setMessage(null);
  }, [chart?.id]);

  async function chartImageDataUrl(): Promise<string> {
    if (!graphDiv) {
      throw new Error("Chart is not ready yet.");
    }
    return Plotly.toImage(graphDiv, {
      format: "png",
      width: 1200,
      height: 760,
      scale: 2
    });
  }

  async function downloadPng() {
    if (!chart) {
      return;
    }
    setMessage(null);
    try {
      const dataUrl = await chartImageDataUrl();
      const link = document.createElement("a");
      link.href = dataUrl;
      link.download = safeFilename(chart.title);
      link.click();
      setMessage("Chart PNG downloaded.");
      setMessageKind("success");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Download failed.");
      setMessageKind("error");
    }
  }

  async function copyPng() {
    setMessage(null);
    try {
      if (!navigator.clipboard || typeof ClipboardItem === "undefined") {
        throw new Error("Copy is not available in this browser. Please use Download PNG.");
      }
      const dataUrl = await chartImageDataUrl();
      const blob = await (await fetch(dataUrl)).blob();
      await navigator.clipboard.write([new ClipboardItem({ "image/png": blob })]);
      setMessage("Chart image copied to clipboard.");
      setMessageKind("success");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Copy failed. Please use Download PNG.");
      setMessageKind("error");
    }
  }

  async function saveChanges() {
    if (!chart || !form) {
      return;
    }
    setIsSaving(true);
    setMessage(null);
    try {
      const updated = await updateGeneratedChart(chart.id, updatePayload(form));
      onChartChanged(updated);
      setMessage("Chart changes saved.");
      setMessageKind("success");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Save failed.");
      setMessageKind("error");
    } finally {
      setIsSaving(false);
    }
  }

  async function saveAsCopy() {
    if (!chart || !form) {
      return;
    }
    setIsCopying(true);
    setMessage(null);
    try {
      const copy = await duplicateGeneratedChart(chart.id, {
        title: form.title.trim() ? `Copy of ${form.title.trim()}` : undefined
      });
      onChartDuplicated(copy);
      setMessage("Chart copy created.");
      setMessageKind("success");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Save as copy failed.");
      setMessageKind("error");
    } finally {
      setIsCopying(false);
    }
  }

  async function resetChart() {
    if (!chart) {
      return;
    }
    setIsResetting(true);
    setMessage(null);
    try {
      const reset = await resetGeneratedChart(chart.id);
      onChartChanged(reset);
      setMessage("Chart reset completed.");
      setMessageKind("success");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Reset failed.");
      setMessageKind("error");
    } finally {
      setIsResetting(false);
    }
  }

  async function archiveChart() {
    if (!chart) {
      return;
    }
    setIsArchiving(true);
    setMessage(null);
    try {
      const archived = await archiveGeneratedChart(chart.id);
      onChartArchived(archived);
      setMessage("Chart archived.");
      setMessageKind("success");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Archive failed.");
      setMessageKind("error");
    } finally {
      setIsArchiving(false);
    }
  }

  if (!chart) {
    return (
      <section className="surface chart-viewer-empty">
        <p className="eyebrow">AI Charts</p>
        <h2>Generated Charts</h2>
        <p>Ask a chart question in Chat to generate a governed Plotly chart.</p>
      </section>
    );
  }

  return (
    <section className="surface chart-viewer" aria-labelledby="chart-viewer-heading">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Plotly Chart</p>
          <h2 id="chart-viewer-heading">{chart.title}</h2>
          {chart.subtitle ? <p className="helper-text">{chart.subtitle}</p> : null}
        </div>
        <div className="button-row">
          <button type="button" className="secondary-button" onClick={() => void copyPng()}>
            Copy PNG
          </button>
          <button type="button" className="primary-button" onClick={() => void downloadPng()}>
            Download PNG
          </button>
        </div>
      </div>

      {message ? <div className={`status-message status-${messageKind}`}>{message}</div> : null}

      {form ? (
        <div className="chart-controls-panel" aria-label="Chart presentation controls">
          <div className="chart-controls-grid">
            <label className="wide-field">
              <span>Title</span>
              <input
                value={form.title}
                onChange={(event) => setFormField(setForm, "title", event.target.value)}
              />
            </label>
            <label className="wide-field">
              <span>Subtitle</span>
              <input
                value={form.subtitle}
                onChange={(event) => setFormField(setForm, "subtitle", event.target.value)}
              />
            </label>
            <label>
              <span>Chart type</span>
              <select
                value={form.chart_type}
                onChange={(event) =>
                  setFormField(setForm, "chart_type", event.target.value as ChartType)
                }
              >
                {chartTypeOptions.map((chartType) => (
                  <option key={chartType} value={chartType}>
                    {chartType.replace("_", " ")}
                  </option>
                ))}
              </select>
            </label>
            <label>
              <span>Orientation</span>
              <select
                value={form.orientation}
                onChange={(event) =>
                  setFormField(setForm, "orientation", event.target.value as ChartOrientation)
                }
              >
                <option value="vertical">Vertical</option>
                <option value="horizontal">Horizontal</option>
              </select>
            </label>
            <label>
              <span>Display mode</span>
              <select
                value={form.display_mode}
                onChange={(event) =>
                  setFormField(setForm, "display_mode", event.target.value as ChartDisplayMode)
                }
              >
                <option value="2d">2D</option>
                <option value="3d">3D where compatible</option>
              </select>
            </label>
            <label>
              <span>Top N</span>
              <input
                type="number"
                min="1"
                value={form.top_n}
                onChange={(event) => setFormField(setForm, "top_n", event.target.value)}
                placeholder="All rows"
              />
            </label>
            <label>
              <span>Sort order</span>
              <select
                value={form.sort_order}
                onChange={(event) =>
                  setFormField(setForm, "sort_order", event.target.value as ChartSortOrder)
                }
              >
                <option value="original">Original</option>
                <option value="ascending">Ascending</option>
                <option value="descending">Descending</option>
              </select>
            </label>
            <label className="checkbox-field">
              <input
                type="checkbox"
                checked={form.show_labels}
                onChange={(event) => setFormField(setForm, "show_labels", event.target.checked)}
              />
              <span>Show data labels</span>
            </label>
            <label className="checkbox-field">
              <input
                type="checkbox"
                checked={form.show_legend}
                onChange={(event) => setFormField(setForm, "show_legend", event.target.checked)}
              />
              <span>Show legend</span>
            </label>
            <label>
              <span>X-axis title</span>
              <input
                value={form.x_axis_title}
                onChange={(event) => setFormField(setForm, "x_axis_title", event.target.value)}
              />
            </label>
            <label>
              <span>Y-axis title</span>
              <input
                value={form.y_axis_title}
                onChange={(event) => setFormField(setForm, "y_axis_title", event.target.value)}
              />
            </label>
            <label>
              <span>Z-axis title</span>
              <input
                value={form.z_axis_title}
                onChange={(event) => setFormField(setForm, "z_axis_title", event.target.value)}
              />
            </label>
          </div>
          <div className="button-row chart-control-actions">
            <button
              type="button"
              className="primary-button"
              disabled={isSaving || !form.title.trim()}
              onClick={() => void saveChanges()}
            >
              {isSaving ? "Saving..." : "Save Changes"}
            </button>
            <button
              type="button"
              className="secondary-button"
              disabled={isCopying}
              onClick={() => void saveAsCopy()}
            >
              {isCopying ? "Copying..." : "Save as Copy"}
            </button>
            <button
              type="button"
              className="secondary-button"
              disabled={isResetting}
              onClick={() => void resetChart()}
            >
              {isResetting ? "Resetting..." : "Reset"}
            </button>
            <button
              type="button"
              className="secondary-button"
              disabled={isArchiving}
              onClick={() => void archiveChart()}
            >
              {isArchiving ? "Archiving..." : "Archive"}
            </button>
          </div>
        </div>
      ) : null}

      {plotly ? (
        <div className="plotly-frame">
          <Plot
            data={plotly.data}
            layout={plotly.layout}
            config={plotConfig}
            useResizeHandler
            style={{ width: "100%", height: "100%" }}
            onInitialized={(_, nextGraphDiv) => setGraphDiv(nextGraphDiv as PlotlyGraphDiv)}
            onUpdate={(_, nextGraphDiv) => setGraphDiv(nextGraphDiv as PlotlyGraphDiv)}
          />
        </div>
      ) : (
        <div className="empty-thread">This chart record does not include a Plotly spec.</div>
      )}

      <div className="chart-supporting-content">
        {noteList({ title: "Data Notes", values: chart.data_notes, kind: "note" })}
        {noteList({ title: "Warnings", values: chart.warnings, kind: "warning" })}
        <div>
          <h3>Chart Data</h3>
          <ChartDataTable table={table} />
        </div>
      </div>
    </section>
  );
}
