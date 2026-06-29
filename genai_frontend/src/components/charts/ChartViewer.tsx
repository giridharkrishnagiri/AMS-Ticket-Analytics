import { useMemo, useState } from "react";
import createPlotlyComponent from "react-plotly.js/factory";
import Plotly from "plotly.js-basic-dist-min";

import { ChartDataTable } from "./ChartDataTable";
import type { GeneratedChart } from "../../types/charts";

type PlotlyGraphDiv = HTMLElement;
const Plot = createPlotlyComponent(
  Plotly as unknown as Parameters<typeof createPlotlyComponent>[0]
);

function safeFilename(title: string): string {
  return `${title.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "genai-chart"}.png`;
}

function NoteList({ title, values, kind }: { title: string; values: string[]; kind: "note" | "warning" }) {
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

export function ChartViewer({ chart }: { chart: GeneratedChart | null }) {
  const [graphDiv, setGraphDiv] = useState<PlotlyGraphDiv | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [messageKind, setMessageKind] = useState<"success" | "error" | "info">("info");

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
        <NoteList title="Data Notes" values={chart.data_notes} kind="note" />
        <NoteList title="Warnings" values={chart.warnings} kind="warning" />
        <div>
          <h3>Chart Data</h3>
          <ChartDataTable table={table} />
        </div>
      </div>
    </section>
  );
}
