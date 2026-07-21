import { useCallback, useEffect, useMemo, useState } from "react";

import {
  clearTicketClassificationAnalysis,
  getTicketClassificationPivot,
  getTicketClassificationSummary,
  getTicketClassificationUsageRuns,
  runTicketClassificationEnrichment,
} from "./api/genai";
import type {
  GenAITicketClassificationPivot,
  GenAITicketClassificationSummary,
  GenAITicketClassificationUsageRun,
} from "./api/genai";
import type { ProjectOption } from "./api/projects";
import CustomerSelector from "./CustomerSelector";
import { formatDisplayDateTime } from "./utils/dateFormat";

const clearConfirmation = "Clear GenAI classification analysis for this month?";

function formatNumber(value: number | null | undefined, maximumFractionDigits = 0): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "Not available";
  }
  return value.toLocaleString(undefined, { maximumFractionDigits });
}

function formatCurrency(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "Not available";
  }
  if (value === 0) {
    return "$0.00";
  }
  return value.toLocaleString(undefined, {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 4,
  });
}

function displayLabel(value: string | null | undefined): string {
  return value?.trim() || "-";
}

function SummaryMetric({
  label,
  value,
}: {
  label: string;
  value: string | number | null | undefined;
}) {
  return (
    <div className="workbench-metric">
      <span className="label">{label}</span>
      <strong>{typeof value === "number" ? formatNumber(value) : value || "Not available"}</strong>
    </div>
  );
}

function GenAIWorkbench() {
  const [projectId, setProjectId] = useState("");
  const [selectedProject, setSelectedProject] = useState<ProjectOption | null>(null);
  const [analysisMonth, setAnalysisMonth] = useState("2026-05");
  const [batchSize, setBatchSize] = useState(10);
  const [forceReprocess, setForceReprocess] = useState(false);
  const [summary, setSummary] = useState<GenAITicketClassificationSummary | null>(null);
  const [pivot, setPivot] = useState<GenAITicketClassificationPivot | null>(null);
  const [usageRuns, setUsageRuns] = useState<GenAITicketClassificationUsageRun[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isRunning, setIsRunning] = useState(false);
  const [isClearing, setIsClearing] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const canAct = Boolean(projectId.trim()) && Boolean(analysisMonth.trim());

  const qualityRows = useMemo(
    () =>
      Object.entries(summary?.category_quality_counts ?? {}).sort(([left], [right]) =>
        left.localeCompare(right)
      ),
    [summary?.category_quality_counts]
  );

  const loadSummaryAndPivot = useCallback(async () => {
    if (!projectId || !analysisMonth) {
      setSummary(null);
      setPivot(null);
      setUsageRuns([]);
      return;
    }
    setIsLoading(true);
    setError(null);
    try {
      const [nextSummary, nextPivot, nextUsageRuns] = await Promise.all([
        getTicketClassificationSummary(projectId, analysisMonth),
        getTicketClassificationPivot(projectId, analysisMonth),
        getTicketClassificationUsageRuns(projectId, analysisMonth),
      ]);
      setSummary(nextSummary);
      setPivot(nextPivot);
      setUsageRuns(nextUsageRuns.runs);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Unable to load analysis.");
      setSummary(null);
      setPivot(null);
      setUsageRuns([]);
    } finally {
      setIsLoading(false);
    }
  }, [analysisMonth, projectId]);

  useEffect(() => {
    void loadSummaryAndPivot();
  }, [loadSummaryAndPivot]);

  function handleProjectIdChange(nextProjectId: string) {
    setProjectId(nextProjectId);
    setSummary(null);
    setPivot(null);
    setUsageRuns([]);
    setMessage(null);
    setError(null);
  }

  async function handleRun() {
    if (!canAct) {
      return;
    }
    setIsRunning(true);
    setMessage(null);
    setError(null);
    try {
      const result = await runTicketClassificationEnrichment({
        project_id: projectId,
        analysis_month: analysisMonth,
        batch_size: batchSize,
        force_reprocess: forceReprocess,
      });
      setSummary(result.summary);
      const [nextPivot, nextUsageRuns] = await Promise.all([
        getTicketClassificationPivot(projectId, analysisMonth),
        getTicketClassificationUsageRuns(projectId, analysisMonth),
      ]);
      setPivot(nextPivot);
      setUsageRuns(
        result.usage_run
          ? [result.usage_run, ...nextUsageRuns.runs.filter((run) => run.run_id !== result.usage_run?.run_id)]
          : nextUsageRuns.runs
      );
      setMessage(
        `Analysis complete: ${formatNumber(result.processed_count)} processed, ${formatNumber(
          result.skipped_cached_count
        )} cached, ${formatNumber(result.failed_count)} failed.`
      );
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Analysis failed.");
    } finally {
      setIsRunning(false);
    }
  }

  async function handleClear() {
    if (!canAct || !window.confirm(clearConfirmation)) {
      return;
    }
    setIsClearing(true);
    setMessage(null);
    setError(null);
    try {
      const result = await clearTicketClassificationAnalysis({
        project_id: projectId,
        analysis_month: analysisMonth,
      });
      setMessage(`Cleared ${formatNumber(result.deleted_count)} analysis rows.`);
      await loadSummaryAndPivot();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Clear failed.");
    } finally {
      setIsClearing(false);
    }
  }

  return (
    <section className="workbench-layout" aria-labelledby="genai-workbench-heading">
      <div className="panel workbench-control-panel">
        <div className="panel-heading">
          <div>
            <p className="label">GenAI Workbench</p>
            <h2 id="genai-workbench-heading">Ticket Classification Enrichment</h2>
          </div>
          <button
            className="secondary-button"
            type="button"
            onClick={() => void loadSummaryAndPivot()}
            disabled={!canAct || isLoading || isRunning}
          >
            {isLoading ? "Refreshing..." : "Refresh Pivot"}
          </button>
        </div>

        <div className="workbench-controls">
          <CustomerSelector
            projectId={projectId}
            onProjectIdChange={handleProjectIdChange}
            onProjectChange={setSelectedProject}
          />
          <label>
            <span>Closed Month</span>
            <input
              type="month"
              value={analysisMonth}
              onChange={(event) => setAnalysisMonth(event.target.value)}
            />
          </label>
          <label>
            <span>Batch Size</span>
            <input
              type="number"
              min={1}
              max={25}
              value={batchSize}
              onChange={(event) => setBatchSize(Number(event.target.value))}
            />
          </label>
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={forceReprocess}
              onChange={(event) => setForceReprocess(event.target.checked)}
            />
            <span>Force reprocess</span>
          </label>
        </div>

        <div className="workbench-actions">
          <button
            className="primary-button"
            type="button"
            disabled={!canAct || isRunning || isClearing}
            onClick={() => void handleRun()}
          >
            {isRunning ? "Running Analysis..." : "Run Analysis"}
          </button>
          <button
            className="secondary-button danger-button"
            type="button"
            disabled={!canAct || isRunning || isClearing}
            onClick={() => void handleClear()}
          >
            {isClearing ? "Clearing..." : "Clear GenAI Analysis"}
          </button>
        </div>

        {selectedProject ? (
          <p className="muted-text summary-block">Selected project: {selectedProject.label}</p>
        ) : null}
        {message ? <p className="success-text summary-block">{message}</p> : null}
        {error ? <p className="error-text summary-block">{error}</p> : null}
      </div>

      <div className="workbench-summary-grid">
        <SummaryMetric label="Eligible" value={summary?.eligible_ticket_count} />
        <SummaryMetric label="Analyzed" value={summary?.analyzed_ticket_count} />
        <SummaryMetric label="Errors" value={summary?.error_ticket_count} />
        <SummaryMetric label="Categories" value={summary?.category_count} />
        <SummaryMetric label="Subcategory 1" value={summary?.subcategory_1_count} />
        <SummaryMetric label="Subcategory 2" value={summary?.subcategory_2_count} />
        <SummaryMetric label="Incidents" value={summary?.incident_count} />
        <SummaryMetric label="SC Tasks" value={summary?.sc_task_count} />
      </div>

      <section className="panel" aria-labelledby="classification-pivot-heading">
        <div className="panel-heading">
          <div>
            <p className="label">Classification Pivot</p>
            <h2 id="classification-pivot-heading">Category, Subcategory, Ticket Type</h2>
          </div>
          <span className="helper-text">
            Last processed: {formatDisplayDateTime(summary?.last_processed_at)}
          </span>
        </div>
        <div className="scroll-frame workbench-table-frame">
          <table>
            <thead>
              <tr>
                <th>GenAI Category</th>
                <th>GenAI SubCategory-1</th>
                <th>GenAI SubCategory-2</th>
                <th>Incidents</th>
                <th>SC Tasks</th>
                <th>Total</th>
              </tr>
            </thead>
            <tbody>
              {(pivot?.rows ?? []).length === 0 ? (
                <tr>
                  <td colSpan={6}>No classification rows for the selected month.</td>
                </tr>
              ) : (
                pivot?.rows.map((row) => (
                  <tr
                    key={`${row.genai_category ?? ""}|${row.genai_subcategory_1 ?? ""}|${
                      row.genai_subcategory_2 ?? ""
                    }`}
                  >
                    <td>{displayLabel(row.genai_category)}</td>
                    <td>{displayLabel(row.genai_subcategory_1)}</td>
                    <td>{displayLabel(row.genai_subcategory_2)}</td>
                    <td>{formatNumber(row.incident_count)}</td>
                    <td>{formatNumber(row.sc_task_count)}</td>
                    <td>{formatNumber(row.total_count)}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section className="panel" aria-labelledby="classification-usage-heading">
        <div className="panel-heading">
          <div>
            <p className="label">Enrichment Usage</p>
            <h2 id="classification-usage-heading">Token and Cost Summary</h2>
          </div>
        </div>
        <div className="scroll-frame workbench-usage-frame">
          <table>
            <thead>
              <tr>
                <th>Completed</th>
                <th>Model</th>
                <th>Tickets</th>
                <th>Batches</th>
                <th>Input Tokens</th>
                <th>Output Tokens</th>
                <th>Total Tokens</th>
                <th>Cost</th>
                <th>Duration</th>
              </tr>
            </thead>
            <tbody>
              {usageRuns.length === 0 ? (
                <tr>
                  <td colSpan={9}>No enrichment usage rows for the selected month.</td>
                </tr>
              ) : (
                usageRuns.map((run) => (
                  <tr key={run.run_id}>
                    <td>{formatDisplayDateTime(run.completed_at)}</td>
                    <td>{displayLabel(run.model_name)}</td>
                    <td>{formatNumber(run.ticket_count)}</td>
                    <td>
                      {formatNumber(run.batch_count)}
                      {run.error_batch_count > 0 ? ` (${formatNumber(run.error_batch_count)} failed)` : ""}
                    </td>
                    <td>{formatNumber(run.prompt_tokens)}</td>
                    <td>{formatNumber(run.completion_tokens)}</td>
                    <td>{formatNumber(run.total_tokens)}</td>
                    <td>{formatCurrency(run.estimated_cost)}</td>
                    <td>
                      {run.duration_ms === null || run.duration_ms === undefined
                        ? "Not available"
                        : `${formatNumber(run.duration_ms)} ms`}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section className="panel" aria-labelledby="category-quality-heading">
        <div className="panel-heading">
          <div>
            <p className="label">Category Quality</p>
            <h2 id="category-quality-heading">Existing Category/Subcategory Check</h2>
          </div>
        </div>
        <div className="quality-strip">
          {qualityRows.length === 0 ? (
            <p className="muted-text">No assessed category quality rows.</p>
          ) : (
            qualityRows.map(([label, count]) => (
              <div className="workbench-metric compact" key={label}>
                <span className="label">{label}</span>
                <strong>{formatNumber(count)}</strong>
              </div>
            ))
          )}
        </div>
      </section>
    </section>
  );
}

export default GenAIWorkbench;
