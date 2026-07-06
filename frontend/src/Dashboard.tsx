import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import {
  downloadOfflineDashboard,
  exportDashboardPowerPoint,
  getCreatedResolvedOpenTrend,
  getCreationSourceTrend,
  getDashboardFilterValues,
  getDashboardOverview,
  getIncidentSlaNameBreakdown,
  getIncidentSlaSummary,
  getIncidentSlaTrend,
  getMttrTrend,
  getReassignmentTrend,
  getReopenTrend,
  getTechnicalFunctionalBreakdown,
} from "./api/dashboard";
import type {
  CreatedResolvedOpenRow,
  CreationSourceTrendRow,
  DashboardFilterValues,
  DashboardOverview,
  DashboardQuery,
  IncidentSlaNameBreakdown,
  IncidentSlaTrendRow,
  IncidentSlaSummary,
  MttrTrendRow,
  ReassignmentTrendRow,
  ReopenTrendRow,
  TechnicalFunctionalBreakdown,
  TicketTypeFilter,
  TimeGrain,
} from "./api/dashboard";
import ApplicationsDashboard from "./ApplicationsDashboard";
import CommentaryEditor from "./components/CommentaryEditor";
import TableExportActions from "./components/TableExportActions";
import CustomerSelector from "./CustomerSelector";
import VolumetricsDashboard from "./VolumetricsDashboard";
import type { ProjectOption } from "./api/projects";
import { formatDisplayDateRange, formatDisplayDateTime } from "./utils/dateFormat";

type TicketTypeSelection = "ALL" | TicketTypeFilter;
type DashboardTab = "overview" | "applications" | "volumetrics";
type LoadStatus = "idle" | "loading" | "success" | "error";
type PowerPointScope = "all" | "in_scope" | "out_of_scope";
type PowerPointTicketType = "all" | "incident" | "sc_task";

type PowerPointExportContext = {
  functionalTrackAmsOwners: string[];
  scope: PowerPointScope;
  sourceLabel: string;
  ticketType: PowerPointTicketType;
};

type LoadState<T> = {
  status: LoadStatus;
  data: T;
  error: string | null;
};

type BreakdownDatum = {
  name: string;
  value: number;
  color: string;
};

const emptyFilterValues: DashboardFilterValues = {
  ticket_types: [],
  priorities: [],
  states: [],
  assignment_groups: [],
  applications: [],
  customers: [],
  towers: [],
  clusters: [],
  application_groups: [],
  application_names: [],
  month_keys: [],
  response_sla_names: [],
  resolution_sla_names: [],
  functional_tracks: [],
  ams_owners: [],
  supported_by_vendors: [],
  support_leads: [],
  application_owners: [],
  business_service_ci_names: [],
  parent_application_names: [],
};

const emptyTechnicalFunctional: TechnicalFunctionalBreakdown = {
  technical_count: 0,
  functional_count: 0,
  unknown_count: 0,
  not_applicable_count: 0,
};

const emptyIncidentSlaSummary: IncidentSlaSummary = {
  incident_count: 0,
  response_sla_applicable_count: 0,
  response_sla_met_count: 0,
  response_sla_breached_count: 0,
  response_sla_adherence_pct: null,
  response_sla_breach_pct: null,
  response_sla_avg_business_elapsed_hours: null,
  resolution_sla_applicable_count: 0,
  resolution_sla_met_count: 0,
  resolution_sla_breached_count: 0,
  resolution_sla_adherence_pct: null,
  resolution_sla_breach_pct: null,
  resolution_sla_avg_business_elapsed_hours: null,
  response_accenture_count: 0,
  response_default_count: 0,
  resolution_accenture_count: 0,
  resolution_default_count: 0,
};

const emptyIncidentSlaNameBreakdown: IncidentSlaNameBreakdown = {
  response_sla_names: [],
  resolution_sla_names: [],
};

const timeGrainOptions: TimeGrain[] = ["DAILY", "WEEKLY", "MONTHLY", "QUARTERLY", "YEARLY"];

const chartColors = {
  created: "#0f766e",
  resolved: "#2563eb",
  backlog: "#d97706",
  actual: "#dc2626",
  business: "#0891b2",
  met: "#16a34a",
  breached: "#dc2626",
  unknown: "#64748b",
  total: "#7c3aed",
  average: "#d97706",
  system: "#7c3aed",
  technical: "#2563eb",
  functional: "#16a34a",
  notApplicable: "#475569",
};
const chartWidth = 640;
const chartHeight = 320;
const chartMargin = { top: 16, right: 28, bottom: 18, left: 8 };

const defaultPowerPointExportContext: PowerPointExportContext = {
  functionalTrackAmsOwners: [],
  scope: "in_scope",
  sourceLabel: "Overview",
  ticketType: "all",
};

function createLoadState<T>(data: T, status: LoadStatus = "idle"): LoadState<T> {
  return { status, data, error: null };
}

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

function formatNumber(value: number | null | undefined, maximumFractionDigits = 0): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "Not available";
  }
  return value.toLocaleString(undefined, { maximumFractionDigits });
}

function formatPercent(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "Not available";
  }
  return `${value.toFixed(1)}%`;
}

function uniqueNonBlank(values: string[]): string[] {
  return Array.from(new Set(values.map((value) => value.trim()).filter(Boolean))).sort();
}

function functionalExportLabel(values: string[]): string {
  const selectedValues = uniqueNonBlank(values);
  if (selectedValues.length === 0) {
    return "All";
  }
  if (selectedValues.length <= 3) {
    return selectedValues.join("; ");
  }
  return `${selectedValues.slice(0, 3).join("; ")} and ${selectedValues.length - 3} more`;
}

function scopeExportLabel(scope: PowerPointScope): string {
  if (scope === "in_scope") {
    return "In-scope";
  }
  if (scope === "out_of_scope") {
    return "Out-of-scope";
  }
  return "All";
}

function ticketTypeExportLabel(ticketType: PowerPointTicketType): string {
  if (ticketType === "incident") {
    return "Incidents";
  }
  if (ticketType === "sc_task") {
    return "SC Tasks";
  }
  return "All";
}

function sumValues<T>(rows: T[], value: (row: T) => number | null | undefined): number {
  return rows.reduce((total, row) => total + (value(row) ?? 0), 0);
}

function weightedAverage<T>(
  rows: T[],
  value: (row: T) => number | null,
  weight: (row: T) => number
): number | null {
  const totals = rows.reduce(
    (accumulator, row) => {
      const nextValue = value(row);
      const nextWeight = weight(row);
      if (nextValue === null || nextWeight <= 0) {
        return accumulator;
      }
      return {
        weightedTotal: accumulator.weightedTotal + nextValue * nextWeight,
        weightTotal: accumulator.weightTotal + nextWeight,
      };
    },
    { weightedTotal: 0, weightTotal: 0 }
  );

  return totals.weightTotal > 0 ? totals.weightedTotal / totals.weightTotal : null;
}

function MultiSelectFilter({
  label,
  options,
  selectedValues,
  onChange,
  emptyMessage = "No values available.",
}: {
  label: string;
  options: string[];
  selectedValues: string[];
  onChange: (values: string[]) => void;
  emptyMessage?: string;
}) {
  const optionSet = useMemo(() => new Set(options), [options]);
  const safeSelectedValues = selectedValues.filter((value) => optionSet.has(value));

  function toggleValue(value: string) {
    if (safeSelectedValues.includes(value)) {
      onChange(safeSelectedValues.filter((selectedValue) => selectedValue !== value));
    } else {
      onChange([...safeSelectedValues, value]);
    }
  }

  return (
    <fieldset className="multi-filter" disabled={options.length === 0}>
      <div className="multi-filter-heading">
        <legend>{label}</legend>
        <span>
          {safeSelectedValues.length === 0 ? "All" : `${safeSelectedValues.length} selected`}
        </span>
      </div>
      {options.length === 0 ? (
        <p className="muted-text filter-empty-text">{emptyMessage}</p>
      ) : (
        <>
          <div className="multi-filter-actions">
            <button className="link-button" type="button" onClick={() => onChange(options)}>
              Select All
            </button>
            <button className="link-button" type="button" onClick={() => onChange([])}>
              Clear Selection
            </button>
          </div>
          <div className="multi-filter-options">
            {options.map((option) => (
              <label key={option}>
                <input
                  checked={safeSelectedValues.includes(option)}
                  type="checkbox"
                  onChange={() => toggleValue(option)}
                />
                <span>{option}</span>
              </label>
            ))}
          </div>
        </>
      )}
    </fieldset>
  );
}

function KpiCard({
  label,
  value,
  helper,
}: {
  label: string;
  value: string;
  helper: string;
}) {
  return (
    <article className="kpi-card">
      <p className="label">{label}</p>
      <strong>{value}</strong>
      <span>{helper}</span>
    </article>
  );
}

function summaryTileToneClass(index: number, columns: number): string {
  const row = Math.floor(index / columns);
  const column = index % columns;
  return (row + column) % 2 === 0 ? "summary-tile-dark" : "summary-tile-light";
}

function ChartCard({
  title,
  subtitle,
  status,
  error,
  isEmpty,
  children,
  note,
}: {
  title: string;
  subtitle?: string;
  status: LoadStatus;
  error: string | null;
  isEmpty: boolean;
  children: ReactNode;
  note?: string;
}) {
  return (
    <section className="chart-card" aria-labelledby={`${title.replace(/\W+/g, "-")}-heading`}>
      <div className="chart-card-heading">
        <div>
          <h3 id={`${title.replace(/\W+/g, "-")}-heading`}>{title}</h3>
          {subtitle ? <p>{subtitle}</p> : null}
        </div>
      </div>
      {status === "loading" ? (
        <p className="muted-text chart-state-text">Loading chart data...</p>
      ) : null}
      {status === "error" ? <p className="error-text chart-state-text">{error}</p> : null}
      {status === "success" && isEmpty ? (
        <p className="muted-text chart-state-text">
          No dashboard data returned for the selected filters.
        </p>
      ) : null}
      {status === "success" && !isEmpty ? children : null}
      {note && status === "success" ? <p className="chart-note">{note}</p> : null}
    </section>
  );
}

function ChartBox({ children }: { children: ReactNode }) {
  return <div className="recharts-box">{children}</div>;
}

function SlaNameDistributionTable({
  title,
  rows,
}: {
  title: string;
  rows: IncidentSlaNameBreakdown["response_sla_names"];
}) {
  const tableRef = useRef<HTMLTableElement | null>(null);

  return (
    <div className="sla-name-table">
      <h4>{title}</h4>
      {rows.length === 0 ? (
        <p className="muted-text">No SLA names returned for the selected filters.</p>
      ) : (
        <>
          <TableExportActions
            filename={`${title.toLowerCase().replace(/[^a-z0-9]+/g, "_")}.csv`}
            label={title}
            tableRef={tableRef}
          />
          <div className="table-wrap">
            <table ref={tableRef}>
              <thead>
                <tr>
                  <th>SLA name</th>
                  <th>Tickets</th>
                  <th>Met</th>
                  <th>Breached</th>
                  <th>Adherence</th>
                  <th>Avg hours</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.sla_name}>
                    <td>{row.sla_name}</td>
                    <td>{formatNumber(row.ticket_count)}</td>
                    <td>{formatNumber(row.met_count)}</td>
                    <td>{formatNumber(row.breached_count)}</td>
                    <td>{formatPercent(row.adherence_pct)}</td>
                    <td>{formatNumber(row.avg_business_elapsed_hours, 2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}

function createdResolvedOpenHasData(rows: CreatedResolvedOpenRow[]): boolean {
  return rows.some(
    (row) => row.created_count > 0 || row.resolved_count > 0 || row.open_end_count > 0
  );
}

function trendHasData<T>(rows: T[], value: (row: T) => number | null | undefined): boolean {
  return rows.some((row) => (value(row) ?? 0) > 0);
}

function Dashboard() {
  const [projectId, setProjectId] = useState("");
  const [selectedProject, setSelectedProject] = useState<ProjectOption | null>(null);
  const [activeDashboardTab, setActiveDashboardTab] = useState<DashboardTab>("overview");
  const [ticketType, setTicketType] = useState<TicketTypeSelection>("ALL");
  const [timeGrain, setTimeGrain] = useState<TimeGrain>("MONTHLY");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [selectedPriorities, setSelectedPriorities] = useState<string[]>([]);
  const [selectedStates, setSelectedStates] = useState<string[]>([]);
  const [selectedAssignmentGroups, setSelectedAssignmentGroups] = useState<string[]>([]);
  const [selectedApplications, setSelectedApplications] = useState<string[]>([]);
  const [selectedCustomers, setSelectedCustomers] = useState<string[]>([]);
  const [selectedTowers, setSelectedTowers] = useState<string[]>([]);
  const [selectedClusters, setSelectedClusters] = useState<string[]>([]);
  const [selectedApplicationGroups, setSelectedApplicationGroups] = useState<string[]>([]);
  const [selectedApplicationNames, setSelectedApplicationNames] = useState<string[]>([]);
  const [selectedResponseSlaNames, setSelectedResponseSlaNames] = useState<string[]>([]);
  const [selectedResolutionSlaNames, setSelectedResolutionSlaNames] = useState<string[]>([]);
  const [filterValues, setFilterValues] = useState<LoadState<DashboardFilterValues>>(
    createLoadState(emptyFilterValues)
  );
  const [overview, setOverview] = useState<LoadState<DashboardOverview | null>>(
    createLoadState<DashboardOverview | null>(null)
  );
  const [createdResolvedOpen, setCreatedResolvedOpen] = useState<
    LoadState<CreatedResolvedOpenRow[]>
  >(createLoadState([]));
  const [mttrTrend, setMttrTrend] = useState<LoadState<MttrTrendRow[]>>(createLoadState([]));
  const [incidentSlaTrend, setIncidentSlaTrend] = useState<LoadState<IncidentSlaTrendRow[]>>(
    createLoadState([])
  );
  const [incidentSlaSummary, setIncidentSlaSummary] = useState<LoadState<IncidentSlaSummary>>(
    createLoadState(emptyIncidentSlaSummary)
  );
  const [incidentSlaNameBreakdown, setIncidentSlaNameBreakdown] = useState<
    LoadState<IncidentSlaNameBreakdown>
  >(createLoadState(emptyIncidentSlaNameBreakdown));
  const [reopenTrend, setReopenTrend] = useState<LoadState<ReopenTrendRow[]>>(
    createLoadState([])
  );
  const [reassignmentTrend, setReassignmentTrend] = useState<
    LoadState<ReassignmentTrendRow[]>
  >(createLoadState([]));
  const [creationSourceTrend, setCreationSourceTrend] = useState<
    LoadState<CreationSourceTrendRow[]>
  >(createLoadState([]));
  const [technicalFunctional, setTechnicalFunctional] = useState<
    LoadState<TechnicalFunctionalBreakdown>
  >(createLoadState(emptyTechnicalFunctional));
  const [lastUpdatedAt, setLastUpdatedAt] = useState<string | null>(null);
  const [pageMessage, setPageMessage] = useState<string | null>(null);
  const [downloadStatus, setDownloadStatus] = useState<LoadStatus>("idle");
  const [powerPointStatus, setPowerPointStatus] = useState<LoadStatus>("idle");
  const [overviewShapeRefreshAttempted, setOverviewShapeRefreshAttempted] = useState(false);
  const [applicationsPowerPointContext, setApplicationsPowerPointContext] =
    useState<PowerPointExportContext>({
      ...defaultPowerPointExportContext,
      sourceLabel: "Applications",
    });
  const [volumetricsPowerPointContext, setVolumetricsPowerPointContext] =
    useState<PowerPointExportContext>({
      ...defaultPowerPointExportContext,
      sourceLabel: "Volumetrics & SLA",
    });

  function clearDashboardData() {
    setOverview(createLoadState<DashboardOverview | null>(null));
    setFilterValues(createLoadState(emptyFilterValues));
    setCreatedResolvedOpen(createLoadState([]));
    setMttrTrend(createLoadState([]));
    setIncidentSlaTrend(createLoadState([]));
    setIncidentSlaSummary(createLoadState(emptyIncidentSlaSummary));
    setIncidentSlaNameBreakdown(createLoadState(emptyIncidentSlaNameBreakdown));
    setReopenTrend(createLoadState([]));
    setReassignmentTrend(createLoadState([]));
    setCreationSourceTrend(createLoadState([]));
    setTechnicalFunctional(createLoadState(emptyTechnicalFunctional));
    setLastUpdatedAt(null);
    setPageMessage(null);
    setPowerPointStatus("idle");
    setOverviewShapeRefreshAttempted(false);
    setApplicationsPowerPointContext({
      ...defaultPowerPointExportContext,
      sourceLabel: "Applications",
    });
    setVolumetricsPowerPointContext({
      ...defaultPowerPointExportContext,
      sourceLabel: "Volumetrics & SLA",
    });
  }

  const handleProjectIdChange = useCallback(
    (nextProjectId: string) => {
      if (nextProjectId !== projectId) {
        clearDashboardData();
      }
      setProjectId(nextProjectId);
    },
    [projectId]
  );

  const handleDownloadDashboard = useCallback(async () => {
    const cleanedProjectId = projectId.trim();
    if (!cleanedProjectId) {
      setPageMessage("Select a customer and project to download dashboard.");
      return;
    }

    setDownloadStatus("loading");
    setPageMessage(null);
    try {
      const { blob, filename } = await downloadOfflineDashboard(cleanedProjectId);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      setPageMessage("Offline dashboard download is ready.");
      setDownloadStatus("success");
    } catch (error) {
      setPageMessage(errorMessage(error, "Unable to download offline dashboard"));
      setDownloadStatus("error");
    }
  }, [projectId]);

  const handleExportPowerPoint = useCallback(async () => {
    const cleanedProjectId = projectId.trim();
    if (!cleanedProjectId) {
      setPageMessage("Select a customer and project to export PowerPoint.");
      return;
    }

    const exportContext =
      activeDashboardTab === "volumetrics"
        ? volumetricsPowerPointContext
        : activeDashboardTab === "applications"
          ? applicationsPowerPointContext
          : defaultPowerPointExportContext;
    const functionalValues = uniqueNonBlank(exportContext.functionalTrackAmsOwners);
    const functionalLabel = functionalExportLabel(functionalValues);
    const projectLabel = selectedProject?.label ?? selectedProject?.name ?? "selected project";
    const confirmationMessage = [
      `Export PowerPoint for ${projectLabel}?`,
      "",
      `Export context: ${exportContext.sourceLabel}`,
      `Scope: ${scopeExportLabel(exportContext.scope)}`,
      `Ticket Type: ${ticketTypeExportLabel(exportContext.ticketType)}`,
      `Functional Track / AMS Owner: ${functionalLabel}`,
      "",
      "The PowerPoint deck is static and will use this filter context.",
      "Download Dashboard remains a full offline HTML export with built-in filters.",
    ].join("\n");

    if (!window.confirm(confirmationMessage)) {
      setPageMessage("PowerPoint export canceled.");
      return;
    }

    setPowerPointStatus("loading");
    setPageMessage(null);
    try {
      const { blob, filename } = await exportDashboardPowerPoint({
        projectId: cleanedProjectId,
        scope: exportContext.scope,
        ticketType: exportContext.ticketType,
        functionalTrackAmsOwner: functionalValues.length > 0 ? functionalValues : "all",
        includeCommentary: true,
      });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      setPageMessage(
        `PowerPoint export is ready. Scope: ${scopeExportLabel(
          exportContext.scope
        )}; Ticket Type: ${ticketTypeExportLabel(
          exportContext.ticketType
        )}; Functional Track / AMS Owner: ${functionalLabel}.`
      );
      setPowerPointStatus("success");
    } catch (error) {
      setPageMessage(errorMessage(error, "Unable to export PowerPoint"));
      setPowerPointStatus("error");
    }
  }, [
    activeDashboardTab,
    applicationsPowerPointContext,
    projectId,
    selectedProject,
    volumetricsPowerPointContext,
  ]);

  const handleApplicationsPowerPointContextChange = useCallback(
    (context: { functionalTrackAmsOwners: string[] }) => {
      setApplicationsPowerPointContext({
        functionalTrackAmsOwners: context.functionalTrackAmsOwners,
        scope: "in_scope",
        sourceLabel: "Applications",
        ticketType: "all",
      });
    },
    []
  );

  const handleVolumetricsPowerPointContextChange = useCallback(
    (context: {
      functionalTrackAmsOwners: string[];
      scope: PowerPointScope;
      ticketType: PowerPointTicketType;
    }) => {
      setVolumetricsPowerPointContext({
        functionalTrackAmsOwners: context.functionalTrackAmsOwners,
        scope: context.scope,
        sourceLabel: "Volumetrics & SLA",
        ticketType: context.ticketType,
      });
    },
    []
  );

  const chartQuery = useMemo<DashboardQuery | null>(() => {
    const cleanedProjectId = projectId.trim();
    if (!cleanedProjectId) {
      return null;
    }

    return {
      projectId: cleanedProjectId,
      ticketTypes: ticketType === "ALL" ? undefined : [ticketType],
      timeGrain,
      startDate: startDate || undefined,
      endDate: endDate || undefined,
      priorities: selectedPriorities,
      states: selectedStates,
      assignmentGroups: selectedAssignmentGroups,
      applications: selectedApplications,
      customers: selectedCustomers,
      towers: selectedTowers,
      clusters: selectedClusters,
      applicationGroups: selectedApplicationGroups,
      applicationNames: selectedApplicationNames,
      responseSlaNames: selectedResponseSlaNames,
      resolutionSlaNames: selectedResolutionSlaNames,
    };
  }, [
    endDate,
    projectId,
    selectedApplicationGroups,
    selectedApplicationNames,
    selectedApplications,
    selectedAssignmentGroups,
    selectedClusters,
    selectedCustomers,
    selectedPriorities,
    selectedResolutionSlaNames,
    selectedResponseSlaNames,
    selectedStates,
    selectedTowers,
    startDate,
    ticketType,
    timeGrain,
  ]);

  const filterValuesQuery = useMemo<DashboardQuery | null>(() => {
    const cleanedProjectId = projectId.trim();
    if (!cleanedProjectId) {
      return null;
    }

    return {
      projectId: cleanedProjectId,
      ticketTypes: ticketType === "ALL" ? undefined : [ticketType],
      timeGrain,
      startDate: startDate || undefined,
      endDate: endDate || undefined,
    };
  }, [endDate, projectId, startDate, ticketType, timeGrain]);

  const kpis = useMemo(() => {
    const createdRows = createdResolvedOpen.data;
    const mttrRows = mttrTrend.data;
    const reassignmentRows = reassignmentTrend.data;
    const totalCreated = sumValues(createdRows, (row) => row.created_count);
    const totalResolved = sumValues(createdRows, (row) => row.resolved_count);
    const latestOpenBacklog =
      createdRows.length > 0 ? createdRows[createdRows.length - 1].open_end_count : null;
    const actualMttr = weightedAverage(
      mttrRows,
      (row) => row.mttr_actual_days,
      (row) => row.completed_ticket_count
    );
    const businessMttr = weightedAverage(
      mttrRows,
      (row) => row.mttr_business_days,
      (row) => row.completed_ticket_count
    );
    const highReassignmentCount = sumValues(
      reassignmentRows,
      (row) => row.tickets_with_more_than_2_reassignments
    );

    return {
      totalCreated,
      totalResolved,
      latestOpenBacklog,
      actualMttr,
      businessMttr,
      highReassignmentCount,
    };
  }, [createdResolvedOpen.data, mttrTrend.data, reassignmentTrend.data]);

  const shouldShowIncidentSla = ticketType !== "SERVICE_CATALOG_TASK";
  const incidentSlaNotice =
    ticketType === "ALL"
      ? "SLA metrics below are calculated from Incident tickets only. Service Catalog Tasks are excluded because they do not have contractual SLAs."
      : "SLA metrics are calculated from enriched Incident response and resolution SLA data.";

  const technicalFunctionalItems = useMemo<BreakdownDatum[]>(
    () => [
      {
        name: "Technical",
        value: technicalFunctional.data.technical_count,
        color: chartColors.technical,
      },
      {
        name: "Functional",
        value: technicalFunctional.data.functional_count,
        color: chartColors.functional,
      },
      {
        name: "Unknown",
        value: technicalFunctional.data.unknown_count,
        color: chartColors.unknown,
      },
      {
        name: "Not applicable",
        value: technicalFunctional.data.not_applicable_count,
        color: chartColors.notApplicable,
      },
    ],
    [technicalFunctional.data]
  );

  const loadDashboardData = useCallback(async () => {
    if (!chartQuery || !filterValuesQuery) {
      setPageMessage("Enter a project ID before refreshing the dashboard.");
      return;
    }

    setPageMessage(null);
    setOverview(createLoadState<DashboardOverview | null>(null, "loading"));
    setFilterValues(createLoadState(emptyFilterValues, "loading"));
    setCreatedResolvedOpen(createLoadState([], "loading"));
    setMttrTrend(createLoadState([], "loading"));
    setIncidentSlaTrend(
      shouldShowIncidentSla ? createLoadState([], "loading") : createLoadState([])
    );
    setIncidentSlaSummary(
      shouldShowIncidentSla
        ? createLoadState(emptyIncidentSlaSummary, "loading")
        : createLoadState(emptyIncidentSlaSummary)
    );
    setIncidentSlaNameBreakdown(
      shouldShowIncidentSla
        ? createLoadState(emptyIncidentSlaNameBreakdown, "loading")
        : createLoadState(emptyIncidentSlaNameBreakdown)
    );
    setReopenTrend(createLoadState([], "loading"));
    setReassignmentTrend(createLoadState([], "loading"));
    setCreationSourceTrend(createLoadState([], "loading"));
    setTechnicalFunctional(createLoadState(emptyTechnicalFunctional, "loading"));

    async function loadResource<T>(
      promise: Promise<T>,
      setState: (state: LoadState<T>) => void,
      emptyValue: T,
      fallback: string
    ) {
      try {
        const data = await promise;
        setState({ status: "success", data, error: null });
      } catch (error) {
        setState({ status: "error", data: emptyValue, error: errorMessage(error, fallback) });
      }
    }

    await Promise.all([
      loadResource<DashboardOverview | null>(
        getDashboardOverview(chartQuery.projectId),
        setOverview,
        null,
        "Unable to load dashboard overview"
      ),
      loadResource(
        getDashboardFilterValues(filterValuesQuery),
        setFilterValues,
        emptyFilterValues,
        "Unable to load filter values"
      ),
      loadResource(
        getCreatedResolvedOpenTrend(chartQuery),
        setCreatedResolvedOpen,
        [],
        "Unable to load created/resolved/open trend"
      ),
      loadResource(getMttrTrend(chartQuery), setMttrTrend, [], "Unable to load MTTR trend"),
      ...(shouldShowIncidentSla
        ? [
            loadResource(
              getIncidentSlaTrend(chartQuery),
              setIncidentSlaTrend,
              [],
              "Unable to load Incident OLA trend"
            ),
            loadResource(
              getIncidentSlaSummary(chartQuery),
              setIncidentSlaSummary,
              emptyIncidentSlaSummary,
              "Unable to load Incident OLA summary"
            ),
            loadResource(
              getIncidentSlaNameBreakdown(chartQuery),
              setIncidentSlaNameBreakdown,
              emptyIncidentSlaNameBreakdown,
              "Unable to load Incident OLA name breakdown"
            ),
          ]
        : []),
      loadResource(getReopenTrend(chartQuery), setReopenTrend, [], "Unable to load reopen trend"),
      loadResource(
        getReassignmentTrend(chartQuery),
        setReassignmentTrend,
        [],
        "Unable to load reassignment trend"
      ),
      loadResource(
        getCreationSourceTrend(chartQuery),
        setCreationSourceTrend,
        [],
        "Unable to load creation source trend"
      ),
      loadResource(
        getTechnicalFunctionalBreakdown(chartQuery),
        setTechnicalFunctional,
        emptyTechnicalFunctional,
        "Unable to load technical/functional breakdown"
      ),
    ]);
    setLastUpdatedAt(formatDisplayDateTime(new Date()));
  }, [chartQuery, filterValuesQuery, shouldShowIncidentSla]);

  useEffect(() => {
    if (
      overview.status === "success" &&
      overview.data &&
      !overview.data.ingested_volume &&
      !overviewShapeRefreshAttempted
    ) {
      setOverviewShapeRefreshAttempted(true);
      void loadDashboardData();
    }
  }, [loadDashboardData, overview.data, overview.status, overviewShapeRefreshAttempted]);

  const overviewInventory = overview.data?.application_inventory;
  const overviewTickets = overview.data?.tickets;
  const overviewCompletionDateRange = formatDisplayDateRange(
    overviewTickets?.completion_date_min,
    overviewTickets?.completion_date_max
  );
  const overviewTotalTickets = overviewTickets?.total_in_scope_tickets ?? 0;
  const incidentTicketShare =
    overviewTotalTickets > 0
      ? `${(((overviewTickets?.incident_count ?? 0) / overviewTotalTickets) * 100).toFixed(
          1
        )}% of in-scope tickets`
      : "No in-scope tickets";
  const scTaskTicketShare =
    overviewTotalTickets > 0
      ? `${(((overviewTickets?.sc_task_count ?? 0) / overviewTotalTickets) * 100).toFixed(
          1
        )}% of in-scope tickets`
      : "No in-scope tickets";

  return (
    <div className="dashboard-layout">
      <section className="dashboard-header panel" aria-label="Dashboard controls">
        <div>
          <p className="label">Dashboard</p>
          <p>Uses normalized ticket data and backend SQL aggregate APIs.</p>
        </div>
        <div className="dashboard-header-actions">
          <div className="dashboard-selector-panel">
            <CustomerSelector
              label="Customer / Project"
              projectId={projectId}
              onProjectIdChange={handleProjectIdChange}
              onProjectChange={setSelectedProject}
            />
          </div>
          <div className="dashboard-button-row">
            <button
              className="primary-button"
              disabled={!projectId.trim()}
              type="button"
              onClick={() => void loadDashboardData()}
            >
              Refresh Dashboard
            </button>
            <button
              className="secondary-button"
              type="button"
              onClick={clearDashboardData}
            >
              Clear Dashboard Data
            </button>
            <button
              className="secondary-button"
              disabled={!projectId.trim() || downloadStatus === "loading"}
              title={
                projectId.trim()
                  ? "Download an offline interactive dashboard"
                  : "Select a customer and project to download dashboard."
              }
              type="button"
              onClick={() => void handleDownloadDashboard()}
            >
              {downloadStatus === "loading" ? "Preparing Download..." : "Download Dashboard"}
            </button>
            <button
              className="secondary-button"
              disabled={!projectId.trim() || powerPointStatus === "loading"}
              title={
                projectId.trim()
                  ? "Export the online dashboard as a PowerPoint deck"
                  : "Select a customer and project to export PowerPoint."
              }
              type="button"
              onClick={() => void handleExportPowerPoint()}
            >
              {powerPointStatus === "loading" ? "Preparing PowerPoint..." : "Export PowerPoint"}
            </button>
          </div>
        </div>
      </section>

      <div className="section-tabs" role="tablist" aria-label="Dashboard sections">
        <button
          className={activeDashboardTab === "overview" ? "section-tab active" : "section-tab"}
          type="button"
          onClick={() => setActiveDashboardTab("overview")}
        >
          Overview
        </button>
        <button
          className={activeDashboardTab === "applications" ? "section-tab active" : "section-tab"}
          type="button"
          onClick={() => setActiveDashboardTab("applications")}
        >
          Applications
        </button>
        <button
          className={activeDashboardTab === "volumetrics" ? "section-tab active" : "section-tab"}
          type="button"
          onClick={() => setActiveDashboardTab("volumetrics")}
        >
          Volumetrics &amp; SLA
        </button>
      </div>

      {activeDashboardTab === "overview" ? (
        <section className="panel" aria-labelledby="dashboard-overview-heading">
          <div className="panel-heading">
            <div>
              <p className="label">Overview</p>
              <h2 id="dashboard-overview-heading">Executive Summary</h2>
            </div>
          </div>
          <div className="summary-grid">
            <div className={summaryTileToneClass(0, 4)}>
              <p className="label">Total Applications</p>
              <strong>{formatNumber(overviewInventory?.total_applications)}</strong>
              <div className="overview-ticket-details">
                <span>
                  Very Critical: {formatNumber(overviewInventory?.very_critical_application_count)}
                </span>
                <span>Critical: {formatNumber(overviewInventory?.critical_application_count)}</span>
              </div>
            </div>
            <div className={summaryTileToneClass(1, 4)}>
              <p className="label">Functional Tracks / AMS Owners</p>
              <strong>{formatNumber(overviewInventory?.functional_track_count)}</strong>
              <div className="overview-ticket-details">
                <span>AMS Owners: {formatNumber(overviewInventory?.ams_owner_count)}</span>
              </div>
            </div>
            <div className={summaryTileToneClass(2, 4)}>
              <p className="label">Assignment Groups</p>
              <strong>{formatNumber(overviewInventory?.assignment_group_count)}</strong>
            </div>
            <div className={summaryTileToneClass(3, 4)}>
              <p className="label">Supported Vendors</p>
              <strong>{formatNumber(overviewInventory?.supported_vendor_count)}</strong>
            </div>
            <div className={`overview-slab-card ${summaryTileToneClass(4, 4)}`}>
              <p className="label">In-Scope Tickets</p>
              <strong>{formatNumber(overviewTickets?.total_in_scope_tickets)}</strong>
            </div>
            <div className={`overview-slab-card ${summaryTileToneClass(5, 4)}`}>
              <p className="label">Incidents</p>
              <strong>{formatNumber(overviewTickets?.incident_count)}</strong>
              <div className="overview-ticket-details">
                <span>{incidentTicketShare}</span>
              </div>
            </div>
            <div className={`overview-slab-card ${summaryTileToneClass(6, 4)}`}>
              <p className="label">SC Tasks</p>
              <strong>{formatNumber(overviewTickets?.sc_task_count)}</strong>
              <div className="overview-ticket-details">
                <span>{scTaskTicketShare}</span>
              </div>
            </div>
            <div className={summaryTileToneClass(7, 4)}>
              <p className="label">Apps Driving 80% Volume</p>
              <strong>
                {formatNumber(overviewTickets?.applications_80pct_monthly_volume_count)}
              </strong>
              <div className="overview-ticket-details">
                <span>Based on avg monthly ticket volume</span>
              </div>
            </div>
          </div>
          <p className="overview-date-note">Tickets data range: {overviewCompletionDateRange}</p>
          {overview.status === "loading" ? (
            <p className="muted-text">Loading dashboard overview...</p>
          ) : null}
          {overview.status === "error" ? <p className="error-text">{overview.error}</p> : null}
          {projectId.trim() ? (
            <CommentaryEditor
              project_id={projectId}
              dashboard_area="dashboard"
              tab_name="overview"
              section_key="overview_summary"
              scope_filter="all"
              ticket_type_filter="all"
              functional_track_ams_owner="all"
            />
          ) : null}
        </section>
      ) : null}

      <div hidden={activeDashboardTab !== "applications"}>
        <ApplicationsDashboard
          customerId={selectedProject?.client_id ?? ""}
          isActive={activeDashboardTab === "applications"}
          onExportContextChange={handleApplicationsPowerPointContextChange}
          projectId={projectId}
        />
      </div>

      <div hidden={activeDashboardTab !== "volumetrics"}>
        <VolumetricsDashboard
          customerId={selectedProject?.client_id ?? ""}
          isActive={activeDashboardTab === "volumetrics"}
          onExportContextChange={handleVolumetricsPowerPointContextChange}
          projectId={projectId}
        />
        {false ? (
          <>
      <section className="panel dashboard-filter-panel" aria-labelledby="dashboard-filters-heading">
        <div className="panel-heading">
          <div>
            <p className="label">Filters</p>
            <h2 id="dashboard-filters-heading">Dashboard Filters</h2>
          </div>
          {lastUpdatedAt ? <p className="muted-text">Last refreshed {lastUpdatedAt}</p> : null}
        </div>

        <div className="dashboard-filter-grid">
          <label>
            <span>Ticket Type</span>
            <select
              value={ticketType}
              onChange={(event) => setTicketType(event.target.value as TicketTypeSelection)}
            >
              <option value="ALL">All</option>
              <option value="INCIDENT">INCIDENT</option>
              <option value="SERVICE_CATALOG_TASK">SERVICE_CATALOG_TASK</option>
            </select>
          </label>

          <label>
            <span>Time Grain</span>
            <select
              value={timeGrain}
              onChange={(event) => setTimeGrain(event.target.value as TimeGrain)}
            >
              {timeGrainOptions.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          </label>

          <label>
            <span>Start Date</span>
            <input
              type="date"
              value={startDate}
              onChange={(event) => setStartDate(event.target.value)}
            />
          </label>

          <label>
            <span>End Date</span>
            <input
              type="date"
              value={endDate}
              onChange={(event) => setEndDate(event.target.value)}
            />
          </label>
        </div>

        {pageMessage ? <p className="error-text">{pageMessage}</p> : null}
        {filterValues.status === "loading" ? (
          <p className="muted-text">Loading filter values...</p>
        ) : null}
        {filterValues.status === "error" ? <p className="error-text">{filterValues.error}</p> : null}

        <div className="multi-filter-grid">
          <MultiSelectFilter
            label="Priority"
            options={filterValues.data.priorities}
            selectedValues={selectedPriorities}
            onChange={setSelectedPriorities}
          />
          <MultiSelectFilter
            label="State"
            options={filterValues.data.states}
            selectedValues={selectedStates}
            onChange={setSelectedStates}
          />
          <MultiSelectFilter
            label="Assignment Group"
            options={filterValues.data.assignment_groups}
            selectedValues={selectedAssignmentGroups}
            onChange={setSelectedAssignmentGroups}
          />
          <MultiSelectFilter
            label="Application"
            options={filterValues.data.applications}
            selectedValues={selectedApplications}
            onChange={setSelectedApplications}
          />
          <MultiSelectFilter
            label="Customer Name"
            options={filterValues.data.customers}
            selectedValues={selectedCustomers}
            onChange={setSelectedCustomers}
            emptyMessage="No customer dimension values available yet."
          />
          <MultiSelectFilter
            label="Tower Name"
            options={filterValues.data.towers}
            selectedValues={selectedTowers}
            onChange={setSelectedTowers}
            emptyMessage="No tower dimension values available yet."
          />
          <MultiSelectFilter
            label="Cluster Name"
            options={filterValues.data.clusters}
            selectedValues={selectedClusters}
            onChange={setSelectedClusters}
            emptyMessage="No cluster dimension values available yet."
          />
          <MultiSelectFilter
            label="Application Group Name"
            options={filterValues.data.application_groups}
            selectedValues={selectedApplicationGroups}
            onChange={setSelectedApplicationGroups}
            emptyMessage="No application group dimension values available yet."
          />
          <MultiSelectFilter
            label="Application Name"
            options={filterValues.data.application_names}
            selectedValues={selectedApplicationNames}
            onChange={setSelectedApplicationNames}
            emptyMessage="No application dimension values available yet."
          />
          <MultiSelectFilter
            label="Response OLA Name"
            options={filterValues.data.response_sla_names}
            selectedValues={selectedResponseSlaNames}
            onChange={setSelectedResponseSlaNames}
            emptyMessage="No enriched Incident response OLA names available yet."
          />
          <MultiSelectFilter
            label="Resolution OLA Name"
            options={filterValues.data.resolution_sla_names}
            selectedValues={selectedResolutionSlaNames}
            onChange={setSelectedResolutionSlaNames}
            emptyMessage="No enriched Incident resolution OLA names available yet."
          />
        </div>
      </section>

      <section className="kpi-grid" aria-label="Dashboard KPI summary">
        <KpiCard
          label="Total Created"
          value={formatNumber(kpis.totalCreated)}
          helper="Tickets created in selected periods"
        />
        <KpiCard
          label="Resolved/Closed"
          value={formatNumber(kpis.totalResolved)}
          helper="Completed by backend ticket-type rules"
        />
        <KpiCard
          label="Latest Open Backlog"
          value={formatNumber(kpis.latestOpenBacklog)}
          helper="Open at latest period end"
        />
        <KpiCard
          label="Actual MTTR Days"
          value={formatNumber(kpis.actualMttr, 2)}
          helper="Weighted by completed ticket count"
        />
        <KpiCard
          label="Business MTTR Days"
          value={formatNumber(kpis.businessMttr, 2)}
          helper="Uses business duration seconds"
        />
        <KpiCard
          label="High Reassignment"
          value={formatNumber(kpis.highReassignmentCount)}
          helper="Tickets with more than 2 reassignments"
        />
      </section>

      <section className="incident-sla-section panel" aria-labelledby="incident-sla-heading">
        <div className="panel-heading">
          <div>
            <p className="label">Incident OLA</p>
            <h2 id="incident-sla-heading">Response and Resolution OLA Adherence</h2>
          </div>
        </div>

        {ticketType === "SERVICE_CATALOG_TASK" ? (
          <p className="muted-text">
            OLA metrics are not applicable for Service Catalog Tasks in this legacy vendor view.
          </p>
        ) : (
          <>
            <p className="muted-text sla-section-note">{incidentSlaNotice}</p>
            <section className="kpi-grid" aria-label="Incident OLA KPI summary">
              <KpiCard
                label="Response OLA Adherence"
                value={formatPercent(incidentSlaSummary.data.response_sla_adherence_pct)}
                helper={`${formatNumber(
                  incidentSlaSummary.data.response_sla_met_count
                )} met / ${formatNumber(
                  incidentSlaSummary.data.response_sla_applicable_count
                )} applicable`}
              />
              <KpiCard
                label="Resolution OLA Adherence"
                value={formatPercent(incidentSlaSummary.data.resolution_sla_adherence_pct)}
                helper={`${formatNumber(
                  incidentSlaSummary.data.resolution_sla_met_count
                )} met / ${formatNumber(
                  incidentSlaSummary.data.resolution_sla_applicable_count
                )} applicable`}
              />
              <KpiCard
                label="Response Applicable"
                value={formatNumber(incidentSlaSummary.data.response_sla_applicable_count)}
                helper={`${formatNumber(
                  incidentSlaSummary.data.response_sla_breached_count
                )} breached`}
              />
              <KpiCard
                label="Resolution Applicable"
                value={formatNumber(incidentSlaSummary.data.resolution_sla_applicable_count)}
                helper={`${formatNumber(
                  incidentSlaSummary.data.resolution_sla_breached_count
                )} breached`}
              />
              <KpiCard
                label="Avg Response Hours"
                value={formatNumber(
                  incidentSlaSummary.data.response_sla_avg_business_elapsed_hours,
                  2
                )}
                helper="Business elapsed hours"
              />
              <KpiCard
                label="Avg Resolution Hours"
                value={formatNumber(
                  incidentSlaSummary.data.resolution_sla_avg_business_elapsed_hours,
                  2
                )}
                helper="Business elapsed hours"
              />
            </section>

            {incidentSlaSummary.status === "loading" ? (
              <p className="muted-text">Loading Incident OLA summary...</p>
            ) : null}
            {incidentSlaSummary.status === "error" ? (
              <p className="error-text">{incidentSlaSummary.error}</p>
            ) : null}

            <div className="dashboard-chart-grid incident-sla-chart-grid">
              <ChartCard
                title="Response vs Resolution OLA Adherence Trend"
                subtitle="Incident-only adherence percentage by created period."
                status={incidentSlaTrend.status}
                error={incidentSlaTrend.error}
                isEmpty={
                  !trendHasData(
                    incidentSlaTrend.data,
                    (row) =>
                      row.response_sla_applicable_count + row.resolution_sla_applicable_count
                  )
                }
              >
                <ChartBox>
                  <LineChart
                    data={incidentSlaTrend.data}
                    height={chartHeight}
                    margin={chartMargin}
                    width={chartWidth}
                  >
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="period_label" />
                    <YAxis />
                    <Tooltip />
                    <Legend />
                    <Line
                      connectNulls
                      dataKey="response_sla_adherence_pct"
                      name="Response OLA adherence %"
                      stroke={chartColors.met}
                      strokeWidth={2.5}
                      type="monotone"
                    />
                    <Line
                      connectNulls
                      dataKey="resolution_sla_adherence_pct"
                      name="Resolution OLA adherence %"
                      stroke={chartColors.business}
                      strokeWidth={2.5}
                      type="monotone"
                    />
                  </LineChart>
                </ChartBox>
              </ChartCard>

              <ChartCard
                title="Response OLA - Met vs Breached"
                subtitle="Incident response OLA met and breached counts."
                status={incidentSlaTrend.status}
                error={incidentSlaTrend.error}
                isEmpty={!trendHasData(incidentSlaTrend.data, (row) => row.response_sla_applicable_count)}
              >
                <ChartBox>
                  <BarChart
                    data={incidentSlaTrend.data}
                    height={chartHeight}
                    margin={chartMargin}
                    width={chartWidth}
                  >
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="period_label" />
                    <YAxis />
                    <Tooltip />
                    <Legend />
                    <Bar
                      dataKey="response_sla_met_count"
                      fill={chartColors.met}
                      name="Response OLA met"
                    />
                    <Bar
                      dataKey="response_sla_breached_count"
                      fill={chartColors.breached}
                      name="Response OLA breached"
                    />
                  </BarChart>
                </ChartBox>
              </ChartCard>

              <ChartCard
                title="Resolution OLA - Met vs Breached"
                subtitle="Incident resolution OLA met and breached counts."
                status={incidentSlaTrend.status}
                error={incidentSlaTrend.error}
                isEmpty={
                  !trendHasData(incidentSlaTrend.data, (row) => row.resolution_sla_applicable_count)
                }
              >
                <ChartBox>
                  <BarChart
                    data={incidentSlaTrend.data}
                    height={chartHeight}
                    margin={chartMargin}
                    width={chartWidth}
                  >
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="period_label" />
                    <YAxis />
                    <Tooltip />
                    <Legend />
                    <Bar
                      dataKey="resolution_sla_met_count"
                      fill={chartColors.met}
                      name="Resolution OLA met"
                    />
                    <Bar
                      dataKey="resolution_sla_breached_count"
                      fill={chartColors.breached}
                      name="Resolution OLA breached"
                    />
                  </BarChart>
                </ChartBox>
              </ChartCard>

              <ChartCard
                title="Avg Business Elapsed Hours"
                subtitle="Average business elapsed hours for selected Incident OLA records."
                status={incidentSlaTrend.status}
                error={incidentSlaTrend.error}
                isEmpty={
                  !trendHasData(
                    incidentSlaTrend.data,
                    (row) =>
                      (row.response_sla_avg_business_elapsed_hours ?? 0) +
                      (row.resolution_sla_avg_business_elapsed_hours ?? 0)
                  )
                }
              >
                <ChartBox>
                  <LineChart
                    data={incidentSlaTrend.data}
                    height={chartHeight}
                    margin={chartMargin}
                    width={chartWidth}
                  >
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="period_label" />
                    <YAxis />
                    <Tooltip />
                    <Legend />
                    <Line
                      connectNulls
                      dataKey="response_sla_avg_business_elapsed_hours"
                      name="Response avg business hours"
                      stroke={chartColors.average}
                      strokeWidth={2.5}
                      type="monotone"
                    />
                    <Line
                      connectNulls
                      dataKey="resolution_sla_avg_business_elapsed_hours"
                      name="Resolution avg business hours"
                      stroke={chartColors.resolved}
                      strokeWidth={2.5}
                      type="monotone"
                    />
                  </LineChart>
                </ChartBox>
              </ChartCard>

              <ChartCard
                title="OLA Name Distribution"
                subtitle="Response and resolution OLA definition performance."
                status={incidentSlaNameBreakdown.status}
                error={incidentSlaNameBreakdown.error}
                isEmpty={
                  incidentSlaNameBreakdown.data.response_sla_names.length === 0 &&
                  incidentSlaNameBreakdown.data.resolution_sla_names.length === 0
                }
              >
                <div className="sla-name-distribution">
                  <SlaNameDistributionTable
                    title="Response OLA Names"
                    rows={incidentSlaNameBreakdown.data.response_sla_names}
                  />
                  <SlaNameDistributionTable
                    title="Resolution OLA Names"
                    rows={incidentSlaNameBreakdown.data.resolution_sla_names}
                  />
                </div>
              </ChartCard>
            </div>
          </>
        )}
      </section>

      <div className="dashboard-chart-grid">
        <ChartCard
          title="Created vs Resolved/Closed and Open Backlog"
          subtitle="Created and resolved/closed volume with period-end open tickets."
          status={createdResolvedOpen.status}
          error={createdResolvedOpen.error}
          isEmpty={!createdResolvedOpenHasData(createdResolvedOpen.data)}
        >
          <ChartBox>
            <ComposedChart
              data={createdResolvedOpen.data}
              height={chartHeight}
              margin={chartMargin}
              width={chartWidth}
            >
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="period_label" />
                <YAxis />
                <Tooltip />
                <Legend />
                <Bar dataKey="created_count" fill={chartColors.created} name="Created" />
                <Bar dataKey="resolved_count" fill={chartColors.resolved} name="Resolved/closed" />
                <Line
                  dataKey="open_end_count"
                  name="Open at period end"
                  stroke={chartColors.backlog}
                  strokeWidth={2.5}
                  type="monotone"
                />
            </ComposedChart>
          </ChartBox>
        </ChartCard>

        <ChartCard
          title="MTTR Trend"
          subtitle="Actual elapsed days and business-duration days."
          status={mttrTrend.status}
          error={mttrTrend.error}
          isEmpty={!trendHasData(mttrTrend.data, (row) => row.completed_ticket_count)}
        >
          <ChartBox>
            <LineChart
              data={mttrTrend.data}
              height={chartHeight}
              margin={chartMargin}
              width={chartWidth}
            >
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="period_label" />
                <YAxis />
                <Tooltip />
                <Legend />
                <Line
                  connectNulls
                  dataKey="mttr_actual_days"
                  name="Actual MTTR days"
                  stroke={chartColors.actual}
                  strokeWidth={2.5}
                  type="monotone"
                />
                <Line
                  connectNulls
                  dataKey="mttr_business_days"
                  name="Business MTTR days"
                  stroke={chartColors.business}
                  strokeWidth={2.5}
                  type="monotone"
                />
            </LineChart>
          </ChartBox>
        </ChartCard>

        <ChartCard
          title="Reopen Trend"
          subtitle="Reopened ticket count, total reopens, and average reopens."
          status={reopenTrend.status}
          error={reopenTrend.error}
          isEmpty={!trendHasData(reopenTrend.data, (row) => row.total_tickets)}
        >
          <ChartBox>
            <ComposedChart
              data={reopenTrend.data}
              height={chartHeight}
              margin={chartMargin}
              width={chartWidth}
            >
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="period_label" />
                <YAxis />
                <Tooltip />
                <Legend />
                <Bar
                  dataKey="reopened_ticket_count"
                  fill={chartColors.created}
                  name="Reopened tickets"
                />
                <Bar dataKey="total_reopen_count" fill={chartColors.total} name="Total reopens" />
                <Line
                  connectNulls
                  dataKey="average_reopen_count"
                  name="Average reopen count"
                  stroke={chartColors.average}
                  strokeWidth={2.5}
                  type="monotone"
                />
            </ComposedChart>
          </ChartBox>
        </ChartCard>

        <ChartCard
          title="Reassignment Trend"
          subtitle="High reassignment tickets, total reassignments, and average reassignments."
          status={reassignmentTrend.status}
          error={reassignmentTrend.error}
          isEmpty={!trendHasData(reassignmentTrend.data, (row) => row.total_tickets)}
        >
          <ChartBox>
            <ComposedChart
              data={reassignmentTrend.data}
              height={chartHeight}
              margin={chartMargin}
              width={chartWidth}
            >
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="period_label" />
                <YAxis />
                <Tooltip />
                <Legend />
                <Bar
                  dataKey="tickets_with_more_than_2_reassignments"
                  fill={chartColors.total}
                  name="High reassignment tickets"
                />
                <Bar
                  dataKey="total_reassignment_count"
                  fill={chartColors.resolved}
                  name="Total reassignments"
                />
                <Line
                  connectNulls
                  dataKey="average_reassignment_count"
                  name="Average reassignment count"
                  stroke={chartColors.average}
                  strokeWidth={2.5}
                  type="monotone"
                />
            </ComposedChart>
          </ChartBox>
        </ChartCard>

        <ChartCard
          title="Creation Source Trend"
          subtitle="User-created, system-created, and unknown ticket creation source."
          status={creationSourceTrend.status}
          error={creationSourceTrend.error}
          isEmpty={!trendHasData(creationSourceTrend.data, (row) => row.unknown_count)}
          note="Creation source may remain mostly unknown until richer classification rules are enabled."
        >
          <ChartBox>
            <BarChart
              data={creationSourceTrend.data}
              height={chartHeight}
              margin={chartMargin}
              width={chartWidth}
            >
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="period_label" />
                <YAxis />
                <Tooltip />
                <Legend />
                <Bar dataKey="user_created_count" stackId="source" fill={chartColors.met} name="User-created" />
                <Bar dataKey="system_created_count" stackId="source" fill={chartColors.system} name="System-created" />
                <Bar dataKey="unknown_count" stackId="source" fill={chartColors.unknown} name="Unknown" />
            </BarChart>
          </ChartBox>
        </ChartCard>

        <ChartCard
          title="Technical vs Functional Breakdown"
          subtitle="Incident technical/functional grouping and non-applicable request records."
          status={technicalFunctional.status}
          error={technicalFunctional.error}
          isEmpty={sumValues(technicalFunctionalItems, (item) => item.value) === 0}
          note="Technical/functional classification will become richer after AI classification is enabled."
        >
          <ChartBox>
            <PieChart height={chartHeight} margin={chartMargin} width={chartWidth}>
                <Tooltip />
                <Legend />
                <Pie
                  data={technicalFunctionalItems}
                  dataKey="value"
                  innerRadius={70}
                  nameKey="name"
                  outerRadius={105}
                  paddingAngle={2}
                >
                  {technicalFunctionalItems.map((item) => (
                    <Cell fill={item.color} key={item.name} />
                  ))}
                </Pie>
            </PieChart>
          </ChartBox>
        </ChartCard>
      </div>
          </>
        ) : null}
      </div>
    </div>
  );
}

export default Dashboard;
