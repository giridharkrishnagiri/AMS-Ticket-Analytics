import { useCallback, useEffect, useMemo, useState } from "react";

import {
  clearTicketClusterAnalysis,
  clearTicketClassificationAnalysis,
  downloadTicketClassificationDump,
  getGenAIWorkbenchSettings,
  getTicketCategoryQualityUsageRuns,
  getTicketClusterUsageRuns,
  getTicketClassificationPivot,
  getTicketClassificationSummary,
  getTicketClassificationUsageRuns,
  runTicketCategoryQualityAnalysis,
  runTicketClusterAnalysis,
  runTicketClassificationEnrichment,
} from "./api/genai";
import type {
  GenAIWorkbenchSettings,
  GenAITicketClusterRunResponse,
  GenAITicketClassificationPivot,
  GenAITicketClassificationSummary,
  GenAITicketClassificationUsageRun,
} from "./api/genai";
import type { ProjectOption } from "./api/projects";
import CustomerSelector from "./CustomerSelector";
import { formatDisplayDateTime } from "./utils/dateFormat";

const clearConfirmation = "Clear GenAI classification analysis for this selected period?";
const forceReprocessConfirmation =
  "Force reprocess will clear the existing analysis for this selected period before starting a new run. Continue?";
const categoryQualityForceConfirmation =
  "Force reprocess will reassess category quality for the selected period. Continue?";
const batchesPerRequest = 1;

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

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.append(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function createRunId(): string {
  if (globalThis.crypto?.randomUUID) {
    return globalThis.crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
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
  const [analysisMonthFrom, setAnalysisMonthFrom] = useState("2026-05");
  const [analysisMonthTo, setAnalysisMonthTo] = useState("2026-05");
  const [batchSize, setBatchSize] = useState(10);
  const [forceReprocess, setForceReprocess] = useState(false);
  const [useLlmLabels, setUseLlmLabels] = useState(true);
  const [workbenchSettings, setWorkbenchSettings] = useState<GenAIWorkbenchSettings | null>(null);
  const [summary, setSummary] = useState<GenAITicketClassificationSummary | null>(null);
  const [pivot, setPivot] = useState<GenAITicketClassificationPivot | null>(null);
  const [usageRuns, setUsageRuns] = useState<GenAITicketClassificationUsageRun[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isRunning, setIsRunning] = useState(false);
  const [isCategoryQualityRunning, setIsCategoryQualityRunning] = useState(false);
  const [isClearing, setIsClearing] = useState(false);
  const [isDownloadingDump, setIsDownloadingDump] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const isMonthRangeValid =
    Boolean(analysisMonthFrom.trim()) &&
    Boolean(analysisMonthTo.trim()) &&
    analysisMonthFrom <= analysisMonthTo;
  const canAct = Boolean(projectId.trim()) && isMonthRangeValid;
  const hasAnalyzedRows = (summary?.analyzed_ticket_count ?? 0) > 0;
  const classificationButtonEnabled =
    workbenchSettings?.ticket_classification_button_enabled ?? false;
  const clusterButtonEnabled = workbenchSettings?.ticket_cluster_analysis_button_enabled ?? true;
  const canRunTicketClassification = canAct && analysisMonthFrom === analysisMonthTo;

  const qualityRows = useMemo(
    () =>
      Object.entries(summary?.category_quality_counts ?? {}).sort(([left], [right]) =>
        left.localeCompare(right)
      ),
    [summary?.category_quality_counts]
  );

  useEffect(() => {
    let isActive = true;
    getGenAIWorkbenchSettings()
      .then((settings) => {
        if (isActive) {
          setWorkbenchSettings(settings);
        }
      })
      .catch((requestError) => {
        if (isActive) {
          setError(
            requestError instanceof Error
              ? requestError.message
              : "Unable to load workbench settings."
          );
        }
      });
    return () => {
      isActive = false;
    };
  }, []);

  const loadUsageRuns = useCallback(async () => {
    if (!projectId || !isMonthRangeValid) {
      return [];
    }
    const primaryUsageRuns = clusterButtonEnabled
      ? getTicketClusterUsageRuns(projectId, analysisMonthFrom, analysisMonthTo)
      : getTicketClassificationUsageRuns(projectId, analysisMonthFrom, analysisMonthTo);
    const categoryQualityUsageRuns = getTicketCategoryQualityUsageRuns(
      projectId,
      analysisMonthFrom,
      analysisMonthTo
    );
    const usageResults = await Promise.all([primaryUsageRuns, categoryQualityUsageRuns]);
    const runsById = new Map<string, GenAITicketClassificationUsageRun>();
    for (const result of usageResults) {
      for (const run of result.runs) {
        runsById.set(run.run_id, run);
      }
    }
    return Array.from(runsById.values())
      .sort((left, right) =>
        String(right.completed_at ?? "").localeCompare(String(left.completed_at ?? ""))
      )
      .slice(0, 10);
  }, [analysisMonthFrom, analysisMonthTo, clusterButtonEnabled, isMonthRangeValid, projectId]);

  const loadSummaryAndPivot = useCallback(async () => {
    if (!projectId || !isMonthRangeValid) {
      setSummary(null);
      setPivot(null);
      setUsageRuns([]);
      return;
    }
    setIsLoading(true);
    setError(null);
    try {
      const [nextSummary, nextPivot, nextUsageRuns] = await Promise.all([
        getTicketClassificationSummary(projectId, analysisMonthFrom, analysisMonthTo),
        getTicketClassificationPivot(projectId, analysisMonthFrom, analysisMonthTo),
        loadUsageRuns(),
      ]);
      setSummary(nextSummary);
      setPivot(nextPivot);
      setUsageRuns(nextUsageRuns);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Unable to load analysis.");
      setSummary(null);
      setPivot(null);
      setUsageRuns([]);
    } finally {
      setIsLoading(false);
    }
  }, [analysisMonthFrom, analysisMonthTo, isMonthRangeValid, loadUsageRuns, projectId]);

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
    if (!canRunTicketClassification) {
      if (analysisMonthFrom !== analysisMonthTo) {
        setError("Run GenAI Analysis supports one closed month at a time. Use cluster-based analysis for a period.");
      }
      return;
    }
    if (forceReprocess && !window.confirm(forceReprocessConfirmation)) {
      return;
    }
    setIsRunning(true);
    setMessage(null);
    setError(null);
    try {
      if (forceReprocess) {
        const clearResult = await clearTicketClassificationAnalysis({
          project_id: projectId,
          analysis_month: analysisMonthFrom,
        });
        setMessage(`Cleared ${formatNumber(clearResult.deleted_count)} rows. Starting analysis...`);
      }

      const runId = createRunId();
      let latestResult = null as Awaited<
        ReturnType<typeof runTicketClassificationEnrichment>
      > | null;
      let requestCount = 0;
      let totalProcessedThisRun = 0;
      let totalFailedThisRun = 0;

      while (true) {
        const result = await runTicketClassificationEnrichment({
          project_id: projectId,
          analysis_month: analysisMonthFrom,
          batch_size: batchSize,
          batch_limit: batchesPerRequest,
          run_id: runId,
          force_reprocess: false,
        });
        latestResult = result;
        requestCount += 1;
        totalProcessedThisRun += result.processed_count;
        totalFailedThisRun += result.failed_count;

        setSummary(result.summary);
        if (result.usage_run) {
          setUsageRuns((currentRuns) => [
            result.usage_run as GenAITicketClassificationUsageRun,
            ...currentRuns.filter((run) => run.run_id !== result.usage_run?.run_id),
          ]);
        }
        setMessage(
          `Running... ${formatNumber(result.summary.analyzed_ticket_count)} of ${formatNumber(
            result.eligible_ticket_count
          )} tickets classified, ${formatNumber(result.remaining_ticket_count)} remaining${
            result.failed_count > 0
              ? `; ${formatNumber(result.failed_count)} ticket-level issue logged in this batch`
              : ""
          }.`
        );

        if (result.failed_count > 0 && result.processed_count === 0) {
          setError(
            `Stopped because this request made no progress and returned ${formatNumber(
              result.failed_count
            )} failed tickets.`
          );
          break;
        }
        if (result.remaining_ticket_count <= 0 || result.processed_batch_count === 0) {
          break;
        }
      }

      const [nextPivot, nextUsageRuns] = await Promise.all([
        getTicketClassificationPivot(projectId, analysisMonthFrom, analysisMonthTo),
        getTicketClassificationUsageRuns(projectId, analysisMonthFrom, analysisMonthTo),
      ]);
      setPivot(nextPivot);
      setUsageRuns(nextUsageRuns.runs);
      if (latestResult) {
        setMessage(
          `Analysis complete: ${formatNumber(
            latestResult.summary.analyzed_ticket_count
          )} analyzed, ${formatNumber(latestResult.skipped_cached_count)} cached, ${formatNumber(
            totalProcessedThisRun
          )} processed in this run across ${formatNumber(requestCount)} requests, ${formatNumber(
            totalFailedThisRun
          )} failed.`
        );
      }
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Analysis failed.");
    } finally {
      setIsRunning(false);
    }
  }

  async function handleRunCluster() {
    if (!canAct || !clusterButtonEnabled) {
      return;
    }
    if (forceReprocess && !window.confirm(forceReprocessConfirmation)) {
      return;
    }
    setIsRunning(true);
    setMessage("Starting cluster-based analysis...");
    setError(null);
    try {
      const result: GenAITicketClusterRunResponse = await runTicketClusterAnalysis({
        project_id: projectId,
        analysis_month: analysisMonthFrom,
        analysis_month_to: analysisMonthTo,
        force_reprocess: forceReprocess,
        use_llm_labels: useLlmLabels,
        run_id: createRunId(),
      });
      setSummary(result.summary);
      if (result.usage_run) {
        setUsageRuns((currentRuns) => [
          result.usage_run as GenAITicketClassificationUsageRun,
          ...currentRuns.filter((run) => run.run_id !== result.usage_run?.run_id),
        ]);
      }

      const [nextPivot, nextUsageRuns] = await Promise.all([
        getTicketClassificationPivot(projectId, analysisMonthFrom, analysisMonthTo),
        getTicketClusterUsageRuns(projectId, analysisMonthFrom, analysisMonthTo),
      ]);
      setPivot(nextPivot);
      setUsageRuns(nextUsageRuns.runs);
      setMessage(
        `Cluster analysis complete: ${formatNumber(
          result.assigned_ticket_count
        )} tickets assigned across ${formatNumber(result.level_1_cluster_count)} / ${formatNumber(
          result.level_2_cluster_count
        )} / ${formatNumber(result.level_3_cluster_count)} clusters. Embeddings: ${formatNumber(
          result.cached_embedding_count
        )} cached, ${formatNumber(result.new_embedding_count)} new${
          result.llm_labeling_enabled ? "" : "; LLM naming skipped"
        }${
          result.failed_count > 0
            ? `; ${formatNumber(result.failed_count)} cluster labels used fallback naming`
            : ""
        }.`
      );
    } catch (requestError) {
      setError(
        requestError instanceof Error ? requestError.message : "Cluster analysis failed."
      );
    } finally {
      setIsRunning(false);
    }
  }

  async function handleRunCategoryQuality() {
    if (!canAct) {
      return;
    }
    if (forceReprocess && !window.confirm(categoryQualityForceConfirmation)) {
      return;
    }
    setIsRunning(true);
    setIsCategoryQualityRunning(true);
    setMessage("Starting category quality analysis...");
    setError(null);
    try {
      const runId = createRunId();
      let latestResult = null as Awaited<
        ReturnType<typeof runTicketCategoryQualityAnalysis>
      > | null;
      let requestCount = 0;
      let totalProcessedThisRun = 0;
      let totalFailedThisRun = 0;

      while (true) {
        const result = await runTicketCategoryQualityAnalysis({
          project_id: projectId,
          analysis_month: analysisMonthFrom,
          analysis_month_to: analysisMonthTo,
          batch_size: batchSize,
          batch_limit: batchesPerRequest,
          force_reprocess: forceReprocess,
          run_id: runId,
        });
        latestResult = result;
        requestCount += 1;
        totalProcessedThisRun += result.processed_count;
        totalFailedThisRun += result.failed_count;
        setSummary(result.summary);
        if (result.usage_run) {
          setUsageRuns((currentRuns) => [
            result.usage_run as GenAITicketClassificationUsageRun,
            ...currentRuns.filter((run) => run.run_id !== result.usage_run?.run_id),
          ]);
        }
        setMessage(
          `Running category quality... ${formatNumber(totalProcessedThisRun)} assessed in this run, ${formatNumber(
            result.skipped_cached_count
          )} cached, ${formatNumber(result.skipped_blank_category_count)} blank-category tickets skipped, ${formatNumber(
            result.remaining_ticket_count
          )} remaining${
            result.failed_count > 0
              ? `; ${formatNumber(result.failed_count)} ticket-level issue logged in this batch`
              : ""
          }.`
        );

        if (result.failed_count > 0 && result.processed_count === 0) {
          setError(
            `Stopped because this request made no progress and returned ${formatNumber(
              result.failed_count
            )} failed tickets.`
          );
          break;
        }
        if (result.remaining_ticket_count <= 0 || result.processed_batch_count === 0) {
          break;
        }
      }

      const [nextSummary, nextPivot, nextUsageRuns] = await Promise.all([
        getTicketClassificationSummary(projectId, analysisMonthFrom, analysisMonthTo),
        getTicketClassificationPivot(projectId, analysisMonthFrom, analysisMonthTo),
        loadUsageRuns(),
      ]);
      setSummary(nextSummary);
      setPivot(nextPivot);
      setUsageRuns(nextUsageRuns);
      if (latestResult) {
        setMessage(
          `Category quality analysis complete: ${formatNumber(
            totalProcessedThisRun
          )} assessed across ${formatNumber(requestCount)} requests, ${formatNumber(
            latestResult.skipped_cached_count
          )} cached, ${formatNumber(
            latestResult.skipped_blank_category_count
          )} blank-category tickets skipped, ${formatNumber(
            latestResult.skipped_missing_classification_count
          )} tickets skipped because no classification row exists, ${formatNumber(
            totalFailedThisRun
          )} failed.`
        );
      }
    } catch (requestError) {
      setError(
        requestError instanceof Error ? requestError.message : "Category quality analysis failed."
      );
    } finally {
      setIsCategoryQualityRunning(false);
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
      if (clusterButtonEnabled) {
        const result = await clearTicketClusterAnalysis({
          project_id: projectId,
          analysis_month: analysisMonthFrom,
          analysis_month_to: analysisMonthTo,
        });
        setMessage(
          `Cleared ${formatNumber(
            result.deleted_classification_count
          )} analysis rows and ${formatNumber(result.deleted_cluster_label_count)} cluster labels.`
        );
      } else {
        const result = await clearTicketClassificationAnalysis({
          project_id: projectId,
          analysis_month: analysisMonthFrom,
          analysis_month_to: analysisMonthTo,
        });
        setMessage(`Cleared ${formatNumber(result.deleted_count)} analysis rows.`);
      }
      await loadSummaryAndPivot();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Clear failed.");
    } finally {
      setIsClearing(false);
    }
  }

  async function handleDownloadDump() {
    if (!canAct) {
      return;
    }
    if (!hasAnalyzedRows) {
      setError("Run cluster-based analysis before downloading the ticket dump.");
      return;
    }
    setIsDownloadingDump(true);
    setMessage(null);
    setError(null);
    try {
      const { blob, filename } = await downloadTicketClassificationDump(
        projectId,
        analysisMonthFrom,
        analysisMonthTo
      );
      downloadBlob(blob, filename);
      setMessage("Ticket classification dump downloaded.");
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Ticket classification dump download failed."
      );
    } finally {
      setIsDownloadingDump(false);
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
            <span>From Closed Month</span>
            <input
              type="month"
              value={analysisMonthFrom}
              onChange={(event) => {
                const nextMonth = event.target.value;
                setAnalysisMonthFrom(nextMonth);
                if (analysisMonthTo < nextMonth) {
                  setAnalysisMonthTo(nextMonth);
                }
              }}
            />
          </label>
          <label>
            <span>To Closed Month</span>
            <input
              type="month"
              value={analysisMonthTo}
              onChange={(event) => setAnalysisMonthTo(event.target.value)}
            />
          </label>
          <label>
            <span>Batch Size</span>
            <input
              type="number"
              min={1}
              max={25}
              value={batchSize}
              disabled={!classificationButtonEnabled}
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
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={useLlmLabels}
              onChange={(event) => setUseLlmLabels(event.target.checked)}
            />
            <span>Use LLM labels</span>
          </label>
        </div>

        <div className="workbench-actions">
          <button
            className="primary-button"
            type="button"
            disabled={
              !canRunTicketClassification ||
              isRunning ||
              isClearing ||
              !classificationButtonEnabled
            }
            title={
              analysisMonthFrom === analysisMonthTo
                ? undefined
                : "Run GenAI Analysis supports one closed month at a time"
            }
            onClick={() => void handleRun()}
          >
            {isRunning && classificationButtonEnabled
              ? "Running Analysis..."
              : classificationButtonEnabled
                ? "Run GenAI Analysis"
                : "GenAI Analysis Disabled"}
          </button>
          <button
            className="primary-button"
            type="button"
            disabled={!canAct || isRunning || isClearing || !clusterButtonEnabled}
            onClick={() => void handleRunCluster()}
          >
            {isRunning && clusterButtonEnabled
              ? "Running Cluster Analysis..."
              : "Run Cluster-Based Analysis"}
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

        <div className="workbench-analysis-actions">
          <span className="label">Separate Analyses</span>
          <button
            className="secondary-button"
            type="button"
            disabled={!canAct || isRunning || isClearing}
            onClick={() => void handleRunCategoryQuality()}
          >
            {isCategoryQualityRunning
              ? "Running Category Quality..."
              : "Run Category Quality Analysis"}
          </button>
        </div>

        {selectedProject ? (
          <p className="muted-text summary-block">Selected project: {selectedProject.label}</p>
        ) : null}
        {workbenchSettings ? (
          <p className="muted-text summary-block">
            Cluster {workbenchSettings.cluster_mode === "adaptive" ? "settings" : "targets"}: L1{" "}
            {formatNumber(workbenchSettings.cluster_level_1_count)}
            {workbenchSettings.cluster_mode === "adaptive"
              ? ", L2 threshold-driven, L3 threshold-driven"
              : `, L2 ${formatNumber(workbenchSettings.cluster_level_2_count)}, L3 ${formatNumber(
                  workbenchSettings.cluster_level_3_count
                )}`}
            . Mode: {workbenchSettings.cluster_mode}. Thresholds:{" "}
            {workbenchSettings.cluster_level_1_distance_threshold.toFixed(2)} /{" "}
            {workbenchSettings.cluster_level_2_distance_threshold.toFixed(2)} /{" "}
            {workbenchSettings.cluster_level_3_distance_threshold.toFixed(2)}. Embedding model:{" "}
            {workbenchSettings.cluster_embedding_model_name}.
          </p>
        ) : null}
        {!isMonthRangeValid ? (
          <p className="error-text summary-block">
            To Closed Month must be same as or later than From Closed Month.
          </p>
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
          <div className="workbench-pivot-actions">
            <span className="helper-text">
              Last processed: {formatDisplayDateTime(summary?.last_processed_at)}
            </span>
            <button
              className="secondary-button"
              type="button"
              disabled={!canAct || isDownloadingDump || !hasAnalyzedRows}
              onClick={() => void handleDownloadDump()}
              title={
                hasAnalyzedRows
                  ? "Download ticket dump with GenAI categorization columns"
                  : "Run cluster-based analysis before downloading the ticket dump"
              }
            >
              {isDownloadingDump ? "Preparing CSV..." : "Download Ticket Dump"}
            </button>
          </div>
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
                  <td colSpan={6}>No classification rows for the selected period.</td>
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
                <th>Tickets</th>
                <th>Embedding Model</th>
                <th>Embedding Batches</th>
                <th>Embedding Tokens</th>
                <th>Embedding Cost</th>
                <th>LLM Model</th>
                <th>LLM Batches</th>
                <th>LLM Input Tokens</th>
                <th>LLM Output Tokens</th>
                <th>LLM Total Tokens</th>
                <th>LLM Cost</th>
                <th>Total Cost</th>
                <th>Duration</th>
              </tr>
            </thead>
            <tbody>
              {usageRuns.length === 0 ? (
                <tr>
                  <td colSpan={14}>No enrichment usage rows for the selected period.</td>
                </tr>
              ) : (
                usageRuns.map((run) => {
                  const hasEmbeddingSplit = run.embedding_tokens !== undefined;
                  const llmPromptTokens =
                    run.llm_prompt_tokens ?? (hasEmbeddingSplit ? null : run.prompt_tokens);
                  const llmCompletionTokens =
                    run.llm_completion_tokens ?? (hasEmbeddingSplit ? null : run.completion_tokens);
                  const llmTotalTokens =
                    run.llm_total_tokens ?? (hasEmbeddingSplit ? null : run.total_tokens);
                  const llmCost = run.llm_cost ?? (hasEmbeddingSplit ? null : run.estimated_cost);
                  return (
                    <tr key={run.run_id}>
                      <td>{formatDisplayDateTime(run.completed_at)}</td>
                      <td>{formatNumber(run.ticket_count)}</td>
                      <td>{displayLabel(run.embedding_model_name)}</td>
                      <td>{formatNumber(run.embedding_batch_count)}</td>
                      <td>{formatNumber(run.embedding_tokens)}</td>
                      <td>{formatCurrency(run.embedding_cost)}</td>
                      <td>{displayLabel(run.llm_model_name ?? run.model_name)}</td>
                      <td>{formatNumber(run.llm_batch_count)}</td>
                      <td>{formatNumber(llmPromptTokens)}</td>
                      <td>{formatNumber(llmCompletionTokens)}</td>
                      <td>{formatNumber(llmTotalTokens)}</td>
                      <td>{formatCurrency(llmCost)}</td>
                      <td>{formatCurrency(run.estimated_cost)}</td>
                      <td>
                        {run.duration_ms === null || run.duration_ms === undefined
                          ? "Not available"
                          : `${formatNumber(run.duration_ms)} ms`}
                      </td>
                    </tr>
                  );
                })
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
