import { useCallback, useEffect, useMemo, useState } from "react";

import {
  clearProjectTicketEmbeddings,
  clearTicketAutomationAnalysis,
  clearTicketClusterAnalysis,
  clearTicketClassificationAnalysis,
  downloadTicketAutomationAnalysis,
  downloadTicketClassificationDump,
  getGenAIWorkbenchSettings,
  getTicketAutomationResults,
  getTicketAutomationUsageRuns,
  getTicketCategoryQualityUsageRuns,
  getTicketClusterUsageRuns,
  getTicketClassificationPivot,
  getTicketClassificationSummary,
  getTicketClassificationUsageRuns,
  runTicketCategoryQualityAnalysis,
  runTicketAutomationAnalysis,
  runTicketClusterAnalysis,
  runTicketClassificationEnrichment,
} from "./api/genai";
import type {
  GenAITicketAutomationSummary,
  GenAITicketAutomationResults,
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
const automationForceConfirmation =
  "Force reprocess will clear saved automation analysis for the selected period before starting a new run. Continue?";
const clearAutomationConfirmation =
  "Clear saved automation analysis for this selected period?";
const clearProjectEmbeddingsConfirmation =
  "This will clear all saved ticket embeddings for the selected project. The next cluster run will recreate them. Continue?";
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

function formatClusterMode(value: string | null | undefined): string {
  if (value === "threshold_only") {
    return "threshold-only";
  }
  return value?.replace(/_/g, " ") || "-";
}

function formatTicketType(value: string | null | undefined): string {
  if (value === "INCIDENT") {
    return "Incident";
  }
  if (value === "SERVICE_CATALOG_TASK") {
    return "SC Task";
  }
  return displayLabel(value);
}

function formatBusinessServices(values: Record<string, number> | null | undefined): string {
  const entries = Object.entries(values ?? {});
  if (entries.length === 0) {
    return "-";
  }
  return entries
    .slice(0, 3)
    .map(([label, count]) => `${label}: ${formatNumber(count)}`)
    .join("; ");
}

function evidenceText(evidence: Record<string, unknown> | null | undefined, key: string): string {
  const value = evidence?.[key];
  if (Array.isArray(value)) {
    return value.map((item) => String(item)).join("; ") || "-";
  }
  return typeof value === "string" && value.trim() ? value : "-";
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

function ClusterSummaryTable({
  summary,
}: {
  summary: GenAITicketClassificationSummary | null;
}) {
  return (
    <section className="panel workbench-summary-panel" aria-labelledby="cluster-summary-heading">
      <div className="panel-heading compact-heading">
        <div>
          <p className="label">Cluster Ticket Analysis</p>
          <h2 id="cluster-summary-heading">LLM-Assessed and Rare Cluster Split</h2>
        </div>
      </div>
      <div className="scroll-frame workbench-summary-table-frame">
        <table className="workbench-summary-table">
          <thead>
            <tr>
              <th colSpan={4}>Ticket Count</th>
              <th colSpan={3}>Categories</th>
              <th colSpan={3}>SubCategory-1</th>
              <th colSpan={3}>SubCategory-2</th>
            </tr>
            <tr>
              <th>Eligible</th>
              <th>Analyzed</th>
              <th>LLM Assessed</th>
              <th>Rare</th>
              <th>Total</th>
              <th>LLM Assessed</th>
              <th>Rare</th>
              <th>Total</th>
              <th>LLM Assessed</th>
              <th>Rare</th>
              <th>Total</th>
              <th>LLM Assessed</th>
              <th>Rare</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>{formatNumber(summary?.eligible_ticket_count)}</td>
              <td>{formatNumber(summary?.analyzed_ticket_count)}</td>
              <td>{formatNumber(summary?.llm_assessed_ticket_count)}</td>
              <td>{formatNumber(summary?.rare_ticket_count)}</td>
              <td>{formatNumber(summary?.category_count)}</td>
              <td>{formatNumber(summary?.category_llm_assessed_count)}</td>
              <td>{formatNumber(summary?.category_rare_count)}</td>
              <td>{formatNumber(summary?.subcategory_1_count)}</td>
              <td>{formatNumber(summary?.subcategory_1_llm_assessed_count)}</td>
              <td>{formatNumber(summary?.subcategory_1_rare_count)}</td>
              <td>{formatNumber(summary?.subcategory_2_count)}</td>
              <td>{formatNumber(summary?.subcategory_2_llm_assessed_count)}</td>
              <td>{formatNumber(summary?.subcategory_2_rare_count)}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  );
}

function AutomationSummaryTable({
  summary,
}: {
  summary: GenAITicketAutomationSummary | null | undefined;
}) {
  return (
    <section className="panel workbench-summary-panel" aria-labelledby="automation-summary-heading">
      <div className="panel-heading compact-heading">
        <div>
          <p className="label">Automation Analysis</p>
          <h2 id="automation-summary-heading">Coverage and Automation Potential Clusters</h2>
        </div>
      </div>
      <div className="scroll-frame workbench-summary-table-frame">
        <table className="workbench-summary-table">
          <thead>
            <tr>
              <th colSpan={3}>Coverage</th>
              <th colSpan={5}>Automation Potential Clusters</th>
              <th>Error</th>
            </tr>
            <tr>
              <th>Clusters Assessed</th>
              <th>Tickets Covered</th>
              <th>Last Processed</th>
              <th>High</th>
              <th>Medium</th>
              <th>Low</th>
              <th>Insufficient Info</th>
              <th>Not Recommended</th>
              <th>Clusters</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>{formatNumber(summary?.assessed_cluster_count)}</td>
              <td>{formatNumber(summary?.ticket_count)}</td>
              <td>{formatDisplayDateTime(summary?.last_processed_at)}</td>
              <td>{formatNumber(summary?.high_potential_count)}</td>
              <td>{formatNumber(summary?.medium_potential_count)}</td>
              <td>{formatNumber(summary?.low_potential_count)}</td>
              <td>{formatNumber(summary?.insufficient_information_count)}</td>
              <td>{formatNumber(summary?.not_recommended_count)}</td>
              <td>{formatNumber(summary?.error_cluster_count)}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
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
  const [automationResults, setAutomationResults] =
    useState<GenAITicketAutomationResults | null>(null);
  const [usageRuns, setUsageRuns] = useState<GenAITicketClassificationUsageRun[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isRunning, setIsRunning] = useState(false);
  const [isCategoryQualityRunning, setIsCategoryQualityRunning] = useState(false);
  const [isAutomationRunning, setIsAutomationRunning] = useState(false);
  const [isClearing, setIsClearing] = useState(false);
  const [isClearingAutomation, setIsClearingAutomation] = useState(false);
  const [isClearingEmbeddings, setIsClearingEmbeddings] = useState(false);
  const [isDownloadingDump, setIsDownloadingDump] = useState(false);
  const [isDownloadingAutomation, setIsDownloadingAutomation] = useState(false);
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
  const automationButtonEnabled =
    workbenchSettings?.ticket_automation_analysis_button_enabled ?? true;
  const canRunTicketClassification = canAct && analysisMonthFrom === analysisMonthTo;
  const hasAutomationRows = (automationResults?.rows.length ?? 0) > 0;

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
    const automationUsageRuns = getTicketAutomationUsageRuns(
      projectId,
      analysisMonthFrom,
      analysisMonthTo
    );
    const usageResults = await Promise.all([
      primaryUsageRuns,
      categoryQualityUsageRuns,
      automationUsageRuns,
    ]);
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
      setAutomationResults(null);
      setUsageRuns([]);
      return;
    }
    setIsLoading(true);
    setError(null);
    try {
      const [nextSummary, nextPivot, nextAutomationResults, nextUsageRuns] = await Promise.all([
        getTicketClassificationSummary(projectId, analysisMonthFrom, analysisMonthTo),
        getTicketClassificationPivot(projectId, analysisMonthFrom, analysisMonthTo),
        getTicketAutomationResults(projectId, analysisMonthFrom, analysisMonthTo),
        loadUsageRuns(),
      ]);
      setSummary(nextSummary);
      setPivot(nextPivot);
      setAutomationResults(nextAutomationResults);
      setUsageRuns(nextUsageRuns);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Unable to load analysis.");
      setSummary(null);
      setPivot(null);
      setAutomationResults(null);
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
    setAutomationResults(null);
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

      const [nextPivot, nextAutomationResults, nextUsageRuns] = await Promise.all([
        getTicketClassificationPivot(projectId, analysisMonthFrom, analysisMonthTo),
        getTicketAutomationResults(projectId, analysisMonthFrom, analysisMonthTo),
        getTicketClusterUsageRuns(projectId, analysisMonthFrom, analysisMonthTo),
      ]);
      setPivot(nextPivot);
      setAutomationResults(nextAutomationResults);
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

  async function handleRunAutomation() {
    if (!canAct || !automationButtonEnabled) {
      return;
    }
    if (forceReprocess && !window.confirm(automationForceConfirmation)) {
      return;
    }
    setIsRunning(true);
    setIsAutomationRunning(true);
    setMessage("Starting automation analysis...");
    setError(null);
    try {
      if (forceReprocess) {
        const clearResult = await clearTicketAutomationAnalysis({
          project_id: projectId,
          analysis_month: analysisMonthFrom,
          analysis_month_to: analysisMonthTo,
        });
        setMessage(
          `Cleared ${formatNumber(
            clearResult.deleted_count
          )} automation analysis rows. Starting analysis...`
        );
      }

      const runId = createRunId();
      let latestResult = null as Awaited<ReturnType<typeof runTicketAutomationAnalysis>> | null;
      let requestCount = 0;
      let totalProcessedThisRun = 0;
      let totalFailedThisRun = 0;
      let totalCachedThisRun = 0;

      while (true) {
        const result = await runTicketAutomationAnalysis({
          project_id: projectId,
          analysis_month: analysisMonthFrom,
          analysis_month_to: analysisMonthTo,
          force_reprocess: false,
          cluster_limit: workbenchSettings?.automation_clusters_per_request,
          run_id: runId,
        });
        latestResult = result;
        requestCount += 1;
        totalProcessedThisRun += result.processed_count;
        totalFailedThisRun += result.failed_count;
        totalCachedThisRun += result.skipped_cached_count;
        if (result.usage_run) {
          setUsageRuns((currentRuns) => [
            result.usage_run as GenAITicketClassificationUsageRun,
            ...currentRuns.filter((run) => run.run_id !== result.usage_run?.run_id),
          ]);
        }
        setMessage(
          `Running automation analysis... ${formatNumber(
            totalProcessedThisRun
          )} clusters assessed in this run, ${formatNumber(
            totalCachedThisRun
          )} cached, ${formatNumber(result.remaining_cluster_count)} remaining${
            result.failed_count > 0
              ? `; ${formatNumber(result.failed_count)} cluster-level issue logged in this request`
              : ""
          }.`
        );

        if (result.failed_count > 0 && result.processed_count === 0) {
          setError(
            `Stopped because this request made no progress and returned ${formatNumber(
              result.failed_count
            )} failed clusters.`
          );
          break;
        }
        if (result.remaining_cluster_count <= 0 || result.processed_batch_count === 0) {
          break;
        }
      }

      const [nextAutomationResults, nextUsageRuns] = await Promise.all([
        getTicketAutomationResults(projectId, analysisMonthFrom, analysisMonthTo),
        loadUsageRuns(),
      ]);
      setAutomationResults(nextAutomationResults);
      setUsageRuns(nextUsageRuns);
      if (latestResult) {
        setMessage(
          `Automation analysis complete: ${formatNumber(
            latestResult.summary.assessed_cluster_count
          )} clusters assessed, covering ${formatNumber(
            latestResult.summary.ticket_count
          )} tickets. This run processed ${formatNumber(
            totalProcessedThisRun
          )} clusters across ${formatNumber(requestCount)} requests, ${formatNumber(
            totalCachedThisRun
          )} cached, ${formatNumber(totalFailedThisRun)} failed.`
        );
      }
    } catch (requestError) {
      setError(
        requestError instanceof Error ? requestError.message : "Automation analysis failed."
      );
    } finally {
      setIsAutomationRunning(false);
      setIsRunning(false);
    }
  }

  async function handleClearAutomation() {
    if (!canAct || !window.confirm(clearAutomationConfirmation)) {
      return;
    }
    setIsClearingAutomation(true);
    setMessage(null);
    setError(null);
    try {
      const result = await clearTicketAutomationAnalysis({
        project_id: projectId,
        analysis_month: analysisMonthFrom,
        analysis_month_to: analysisMonthTo,
      });
      setMessage(`Cleared ${formatNumber(result.deleted_count)} automation analysis rows.`);
      const [nextAutomationResults, nextUsageRuns] = await Promise.all([
        getTicketAutomationResults(projectId, analysisMonthFrom, analysisMonthTo),
        loadUsageRuns(),
      ]);
      setAutomationResults(nextAutomationResults);
      setUsageRuns(nextUsageRuns);
    } catch (requestError) {
      setError(
        requestError instanceof Error ? requestError.message : "Automation analysis clear failed."
      );
    } finally {
      setIsClearingAutomation(false);
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
          )} analysis rows, ${formatNumber(
            result.deleted_cluster_label_count
          )} cluster labels, and ${formatNumber(
            result.deleted_automation_assessment_count
          )} automation rows.`
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

  async function handleClearEmbeddings() {
    if (!projectId || !window.confirm(clearProjectEmbeddingsConfirmation)) {
      return;
    }
    setIsClearingEmbeddings(true);
    setMessage(null);
    setError(null);
    try {
      const result = await clearProjectTicketEmbeddings({
        project_id: projectId,
      });
      setMessage(
        `Cleared ${formatNumber(
          result.deleted_embedding_count
        )} saved ticket embeddings for the selected project.`
      );
    } catch (requestError) {
      setError(
        requestError instanceof Error ? requestError.message : "Embedding cache clear failed."
      );
    } finally {
      setIsClearingEmbeddings(false);
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
      setMessage("Ticket classification workbook downloaded.");
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

  async function handleDownloadAutomation() {
    if (!canAct) {
      return;
    }
    if (!hasAutomationRows) {
      setError("Run automation analysis before downloading the automation workbook.");
      return;
    }
    setIsDownloadingAutomation(true);
    setMessage(null);
    setError(null);
    try {
      const { blob, filename } = await downloadTicketAutomationAnalysis(
        projectId,
        analysisMonthFrom,
        analysisMonthTo
      );
      downloadBlob(blob, filename);
      setMessage("Automation analysis workbook downloaded.");
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Automation analysis workbook download failed."
      );
    } finally {
      setIsDownloadingAutomation(false);
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
          <span className="label">Workbench Actions</span>
          <button
            className="secondary-button"
            type="button"
            disabled={!canAct || isRunning || isClearing || isClearingEmbeddings}
            onClick={() => void handleRunCategoryQuality()}
          >
            {isCategoryQualityRunning
              ? "Running Category Quality..."
              : "Run Category Quality Analysis"}
          </button>
          <button
            className="secondary-button"
            type="button"
            disabled={
              !canAct ||
              isRunning ||
              isClearing ||
              isClearingAutomation ||
              !automationButtonEnabled
            }
            onClick={() => void handleRunAutomation()}
          >
            {isAutomationRunning ? "Running Automation..." : "Run Automation Analysis"}
          </button>
          <button
            className="secondary-button"
            type="button"
            disabled={!canAct || isRunning || isClearing || isClearingAutomation || !hasAutomationRows}
            onClick={() => void handleDownloadAutomation()}
          >
            {isDownloadingAutomation ? "Preparing Automation XLSX..." : "Download Automation XLSX"}
          </button>
          <button
            className="secondary-button danger-button"
            type="button"
            disabled={!canAct || isRunning || isClearing || isClearingAutomation}
            onClick={() => void handleClearAutomation()}
          >
            {isClearingAutomation ? "Clearing Automation..." : "Clear Automation Analysis"}
          </button>
          <button
            className="secondary-button danger-button"
            type="button"
            disabled={!projectId || isRunning || isClearing || isClearingEmbeddings}
            onClick={() => void handleClearEmbeddings()}
          >
            {isClearingEmbeddings ? "Clearing Embeddings..." : "Clear Project Embeddings"}
          </button>
        </div>

        {selectedProject ? (
          <p className="muted-text summary-block">Selected project: {selectedProject.label}</p>
        ) : null}
        {workbenchSettings ? (
          <p className="muted-text summary-block">
            Cluster settings: L1 {formatNumber(workbenchSettings.cluster_level_1_count)} (
            {formatClusterMode(workbenchSettings.cluster_level_1_mode)}), L2{" "}
            {formatNumber(workbenchSettings.cluster_level_2_count)} (
            {formatClusterMode(workbenchSettings.cluster_level_2_mode)}), L3{" "}
            {formatNumber(workbenchSettings.cluster_level_3_count)} (
            {formatClusterMode(workbenchSettings.cluster_level_3_mode)}). Mode:{" "}
            {workbenchSettings.cluster_mode}. Thresholds:{" "}
            {workbenchSettings.cluster_level_1_distance_threshold.toFixed(2)} /{" "}
            {workbenchSettings.cluster_level_2_distance_threshold.toFixed(2)} /{" "}
            {workbenchSettings.cluster_level_3_distance_threshold.toFixed(2)}. Rare label skip:{" "}
            below {formatNumber(workbenchSettings.cluster_min_llm_label_ticket_count)} tickets.
            Embedding model: {workbenchSettings.cluster_embedding_model_name}. Automation model:{" "}
            {displayLabel(workbenchSettings.automation_model_name)}; representatives:{" "}
            {formatNumber(workbenchSettings.automation_representative_ticket_count)} tickets,
            {formatNumber(workbenchSettings.automation_clusters_per_request)} clusters/request.
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

      <ClusterSummaryTable summary={summary} />

      <AutomationSummaryTable summary={automationResults?.summary} />

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
              {isDownloadingDump ? "Preparing XLSX..." : "Download Ticket Dump XLSX"}
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

      <section className="panel" aria-labelledby="automation-analysis-heading">
        <div className="panel-heading">
          <div>
            <p className="label">Automation Analysis</p>
            <h2 id="automation-analysis-heading">Cluster-Level Automation Opportunities</h2>
          </div>
          <span className="helper-text">
            Last processed:{" "}
            {formatDisplayDateTime(automationResults?.summary.last_processed_at)}
          </span>
        </div>
        <div className="scroll-frame workbench-table-frame">
          <table>
            <thead>
              <tr>
                <th>SubCategory-2 Cluster</th>
                <th>Type</th>
                <th>Tickets</th>
                <th>Potential</th>
                <th>Path</th>
                <th>Automation Type</th>
                <th>Business Service</th>
                <th>Recommendation</th>
                <th>Confidence</th>
              </tr>
            </thead>
            <tbody>
              {(automationResults?.rows ?? []).length === 0 ? (
                <tr>
                  <td colSpan={9}>
                    No automation analysis rows for the selected period.
                  </td>
                </tr>
              ) : (
                automationResults?.rows.map((row) => (
                  <tr key={row.id}>
                    <td>
                      <strong>{displayLabel(row.cluster_label)}</strong>
                      <div className="helper-text">{row.cluster_key}</div>
                      <div className="helper-text">
                        {displayLabel(row.category)} - {displayLabel(row.subcategory_1)}
                      </div>
                    </td>
                    <td>{formatTicketType(row.ticket_type)}</td>
                    <td>{formatNumber(row.ticket_count)}</td>
                    <td>{displayLabel(row.automation_potential)}</td>
                    <td>{displayLabel(row.recommended_resolution_path)}</td>
                    <td>{displayLabel(row.primary_automation_type)}</td>
                    <td>{formatBusinessServices(row.business_services)}</td>
                    <td>
                      <div>{displayLabel(row.automation_recommendation)}</div>
                      <div className="helper-text">
                        Evidence: {evidenceText(row.evidence, "evidence_from_tickets")}
                      </div>
                    </td>
                    <td>{formatNumber(row.confidence, 2)}</td>
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
