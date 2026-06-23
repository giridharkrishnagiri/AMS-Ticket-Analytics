import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Bar,
  CartesianGrid,
  ComposedChart,
  LabelList,
  Legend,
  Line,
  ReferenceLine,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import {
  getDashboardVolumetricsCreatedResolvedBacklog,
  getDashboardVolumetricsFilterValues,
  getDashboardVolumetricsSummary,
} from "./api/dashboard";
import type {
  DashboardVolumetricsBacklog,
  DashboardVolumetricsFilterValues,
  DashboardVolumetricsFilters,
  DashboardVolumetricsRequest,
  DashboardVolumetricsSummary,
  VolumetricsScope,
  VolumetricsTicketType,
  VolumetricsTimeGrain,
} from "./api/dashboard";
import ExcelMultiSelectFilter from "./components/ExcelMultiSelectFilter";
import type { ExcelFilterOption } from "./components/ExcelMultiSelectFilter";

type LoadStatus = "idle" | "loading" | "success" | "error";

type LoadState<T> = {
  status: LoadStatus;
  data: T;
  error: string | null;
};

type VolumetricsDashboardProps = {
  projectId: string;
  isActive: boolean;
};

type FilterKey = keyof DashboardVolumetricsFilters;

const monthNames = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

const defaultStartMonth = "2025-01";
const defaultEndMonth = "2026-06";
const defaultStartWeek = "2025-01-06";
const defaultEndWeek = "2026-06-15";

const emptyFilters: DashboardVolumetricsFilters = {
  functional_track_ams_owner: [],
  assignment_group_support_lead: [],
  parent_application_name: [],
  application_owner: [],
  supported_by_vendor: [],
};

const emptyFilterValues: DashboardVolumetricsFilterValues = {
  scope: [],
  ticket_type: [],
  functional_track_ams_owner: [],
  assignment_group_support_lead: [],
  parent_application_name: [],
  application_owner: [],
  supported_by_vendor: [],
};

const emptySummary: DashboardVolumetricsSummary = {
  period_count: 0,
  created: { total: 0, average_per_period: null },
  resolved_closed: { total: 0, average_per_period: null },
  cancelled: {
    total: 0,
    average_per_period: null,
    cancelled_pct_of_resolved_cancelled: null,
  },
  response_sla: { average_adherence_pct: null, applicable_count: 0, met_count: 0 },
  resolution_sla: { average_adherence_pct: null, applicable_count: 0, met_count: 0 },
};

const emptyBacklog: DashboardVolumetricsBacklog = {
  average_backlog_open: null,
  rows: [],
};

const chartColors = {
  created: "#0f766e",
  resolved: "#2563eb",
  backlog: "#d97706",
  average: "#7c3aed",
};

const chartImagePadding = 18;
const chartImageTitleHeight = 42;

function createLoadState<T>(data: T, status: LoadStatus = "idle"): LoadState<T> {
  return { status, data, error: null };
}

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

function pad(value: number): string {
  return value.toString().padStart(2, "0");
}

function formatNumber(value: number | null | undefined, maximumFractionDigits = 0): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "N/A";
  }
  return value.toLocaleString(undefined, { maximumFractionDigits });
}

function formatPercent(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "N/A";
  }
  return `${value.toFixed(1)}%`;
}

function formatDateShort(date: Date): string {
  return `${pad(date.getDate())}-${monthNames[date.getMonth()]}-${date.getFullYear().toString().slice(-2)}`;
}

function monthStartDate(monthValue: string): Date {
  const [year, month] = monthValue.split("-").map(Number);
  return new Date(year, month - 1, 1, 0, 0, 0, 0);
}

function monthEndDate(monthValue: string): Date {
  const [year, month] = monthValue.split("-").map(Number);
  return new Date(year, month, 0, 23, 59, 59, 999);
}

function parseDateInput(value: string): Date {
  const [year, month, day] = value.split("-").map(Number);
  return new Date(year, month - 1, day, 0, 0, 0, 0);
}

function weekStartDate(value: string): Date {
  const date = parseDateInput(value);
  const daysSinceMonday = (date.getDay() + 6) % 7;
  date.setDate(date.getDate() - daysSinceMonday);
  date.setHours(0, 0, 0, 0);
  return date;
}

function weekEndDate(value: string): Date {
  const date = weekStartDate(value);
  date.setDate(date.getDate() + 6);
  date.setHours(23, 59, 59, 999);
  return date;
}

function apiDateTime(date: Date, endOfDay = false): string {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${
    endOfDay ? "23:59:59" : "00:00:00"
  }+00:00`;
}

function formatMonthLabel(monthValue: string): string {
  const date = monthStartDate(monthValue);
  return `${monthNames[date.getMonth()]}-${date.getFullYear().toString().slice(-2)}`;
}

function combinedOptions(
  values: DashboardVolumetricsFilterValues["functional_track_ams_owner"]
): ExcelFilterOption[] {
  return values.map((value) => ({
    value: value.label,
    label: value.label,
    count: value.count,
  }));
}

function singleOptions(values: Array<{ label: string; value: string; count: number }>) {
  return values.map((value) => ({
    value: value.value,
    label: value.label,
    count: value.count,
  }));
}

function escapeXml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&apos;");
}

async function svgToImage(svgMarkup: string): Promise<HTMLImageElement> {
  const svgBlob = new Blob([svgMarkup], { type: "image/svg+xml;charset=utf-8" });
  const url = URL.createObjectURL(svgBlob);
  try {
    const image = new Image();
    await new Promise<void>((resolve, reject) => {
      image.onload = () => resolve();
      image.onerror = () => reject(new Error("Chart image could not be prepared."));
      image.src = url;
    });
    return image;
  } finally {
    URL.revokeObjectURL(url);
  }
}

async function copyChartToClipboard(chartElement: HTMLElement, title: string) {
  if (!navigator.clipboard || typeof ClipboardItem === "undefined") {
    throw new Error("Image clipboard copy is not supported in this browser.");
  }

  const sourceSvg = chartElement.querySelector("svg");
  if (!sourceSvg) {
    throw new Error("No chart image is available to copy.");
  }

  const chartWidth =
    Number(sourceSvg.getAttribute("width")) || Math.ceil(sourceSvg.getBoundingClientRect().width);
  const chartHeight =
    Number(sourceSvg.getAttribute("height")) || Math.ceil(sourceSvg.getBoundingClientRect().height);
  const outputWidth = chartWidth + chartImagePadding * 2;
  const outputHeight = chartHeight + chartImageTitleHeight + chartImagePadding;
  const svgMarkup = `
    <svg xmlns="http://www.w3.org/2000/svg" width="${outputWidth}" height="${outputHeight}" viewBox="0 0 ${outputWidth} ${outputHeight}">
      <rect x="0" y="0" width="${outputWidth}" height="${outputHeight}" rx="8" fill="#ffffff" stroke="#cbd5e1"/>
      <text x="${chartImagePadding}" y="27" fill="#111827" font-family="Inter, Arial, sans-serif" font-size="17" font-weight="700">${escapeXml(
        title
      )}</text>
      <g transform="translate(${chartImagePadding}, ${chartImageTitleHeight})">
        ${sourceSvg.innerHTML}
      </g>
    </svg>
  `;

  const image = await svgToImage(svgMarkup);
  const canvas = document.createElement("canvas");
  const scale = Math.max(1, Math.min(window.devicePixelRatio || 1, 2));
  canvas.width = Math.ceil(outputWidth * scale);
  canvas.height = Math.ceil(outputHeight * scale);
  const context = canvas.getContext("2d");
  if (!context) {
    throw new Error("Chart image could not be rendered.");
  }
  context.scale(scale, scale);
  context.drawImage(image, 0, 0, outputWidth, outputHeight);

  const pngBlob = await new Promise<Blob>((resolve, reject) => {
    canvas.toBlob((blob) => {
      if (!blob) {
        reject(new Error("Chart image could not be copied."));
        return;
      }
      resolve(blob);
    }, "image/png");
  });

  window.focus();
  try {
    await navigator.clipboard.write([new ClipboardItem({ "image/png": pngBlob })]);
  } catch (error) {
    const message = errorMessage(error, "This browser could not copy the chart image.");
    if (message.toLowerCase().includes("not focused")) {
      throw new Error("Click inside the app window and try Copy chart again.");
    }
    throw error;
  }
}

function useChartFrame(title: string) {
  const chartRef = useRef<HTMLDivElement>(null);
  const [plotWidth, setPlotWidth] = useState(0);
  const [copyMessage, setCopyMessage] = useState<string | null>(null);

  useEffect(() => {
    const element = chartRef.current;
    if (!element) {
      return undefined;
    }

    const updatePlotWidth = () => {
      setPlotWidth(Math.floor(element.clientWidth));
    };
    updatePlotWidth();

    const resizeObserver = new ResizeObserver(updatePlotWidth);
    resizeObserver.observe(element);
    return () => resizeObserver.disconnect();
  }, []);

  const handleCopy = useCallback(async () => {
    if (!chartRef.current) {
      return;
    }
    try {
      await copyChartToClipboard(chartRef.current, title);
      setCopyMessage("Copied chart image to clipboard.");
    } catch (error) {
      setCopyMessage(errorMessage(error, "This browser could not copy the chart image."));
    }
  }, [title]);

  return { chartRef, copyMessage, handleCopy, plotWidth };
}

function VolumetricsDashboard({ projectId, isActive }: VolumetricsDashboardProps) {
  const [scope, setScope] = useState<VolumetricsScope>("in_scope");
  const [ticketType, setTicketType] = useState<VolumetricsTicketType>("all");
  const [timeGrain, setTimeGrain] = useState<VolumetricsTimeGrain>("monthly");
  const [startMonth, setStartMonth] = useState(defaultStartMonth);
  const [endMonth, setEndMonth] = useState(defaultEndMonth);
  const [startWeek, setStartWeek] = useState(defaultStartWeek);
  const [endWeek, setEndWeek] = useState(defaultEndWeek);
  const [filters, setFilters] = useState<DashboardVolumetricsFilters>(emptyFilters);
  const [filterValues, setFilterValues] = useState<LoadState<DashboardVolumetricsFilterValues>>(
    createLoadState(emptyFilterValues)
  );
  const [summary, setSummary] = useState<LoadState<DashboardVolumetricsSummary>>(
    createLoadState(emptySummary)
  );
  const [backlog, setBacklog] = useState<LoadState<DashboardVolumetricsBacklog>>(
    createLoadState(emptyBacklog)
  );
  const [loadedProjectId, setLoadedProjectId] = useState("");

  const effectiveRange = useMemo(() => {
    if (timeGrain === "monthly") {
      const startDate = monthStartDate(startMonth);
      const endDate = monthEndDate(endMonth);
      return {
        startDate,
        endDate,
        startApi: apiDateTime(startDate),
        endApi: apiDateTime(endDate, true),
        selectedLabel: `${formatMonthLabel(startMonth)} to ${formatMonthLabel(endMonth)}`,
      };
    }

    const startDate = weekStartDate(startWeek);
    const endDate = weekEndDate(endWeek);
    return {
      startDate,
      endDate,
      startApi: apiDateTime(startDate),
      endApi: apiDateTime(endDate, true),
      selectedLabel: `${formatDateShort(startDate)} to ${formatDateShort(endDate)}`,
    };
  }, [endMonth, endWeek, startMonth, startWeek, timeGrain]);

  const filterOptions = useMemo(
    () => ({
      scope: singleOptions(filterValues.data.scope),
      ticket_type: singleOptions(filterValues.data.ticket_type),
      functional_track_ams_owner: combinedOptions(filterValues.data.functional_track_ams_owner),
      assignment_group_support_lead: combinedOptions(
        filterValues.data.assignment_group_support_lead
      ),
      parent_application_name: singleOptions(filterValues.data.parent_application_name),
      application_owner: singleOptions(filterValues.data.application_owner),
      supported_by_vendor: singleOptions(filterValues.data.supported_by_vendor),
    }),
    [filterValues.data]
  );

  const requestBody = useMemo<DashboardVolumetricsRequest | null>(() => {
    const cleanedProjectId = projectId.trim();
    if (!cleanedProjectId) {
      return null;
    }
    return {
      project_id: cleanedProjectId,
      scope,
      ticket_type: ticketType,
      time_grain: timeGrain,
      start_datetime: effectiveRange.startApi,
      end_datetime: effectiveRange.endApi,
      filters,
    };
  }, [effectiveRange.endApi, effectiveRange.startApi, filters, projectId, scope, ticketType, timeGrain]);

  const requestSignature = useMemo(
    () => (requestBody ? JSON.stringify(requestBody) : ""),
    [requestBody]
  );
  const hasActiveProjectContext = Boolean(projectId.trim()) && projectId === loadedProjectId;

  const loadVolumetricsData = useCallback(async () => {
    if (!requestBody) {
      return;
    }

    setFilterValues(createLoadState(emptyFilterValues, "loading"));
    setSummary(createLoadState(emptySummary, "loading"));
    setBacklog(createLoadState(emptyBacklog, "loading"));

    void getDashboardVolumetricsSummary(requestBody)
      .then((nextSummary) => {
        setSummary({ status: "success", data: nextSummary, error: null });
      })
      .catch((error) => {
        setSummary({
          status: "error",
          data: emptySummary,
          error: errorMessage(error, "Unable to load Volumetrics summary"),
        });
      });

    void getDashboardVolumetricsCreatedResolvedBacklog(requestBody)
      .then((nextBacklog) => {
        setBacklog({ status: "success", data: nextBacklog, error: null });
      })
      .catch((error) => {
        setBacklog({
          status: "error",
          data: emptyBacklog,
          error: errorMessage(error, "Unable to load backlog chart"),
        });
      });

    void getDashboardVolumetricsFilterValues(requestBody)
      .then((nextFilterValues) => {
        setFilterValues({ status: "success", data: nextFilterValues, error: null });
      })
      .catch((error) => {
        setFilterValues({
          status: "error",
          data: emptyFilterValues,
          error: errorMessage(error, "Unable to load Volumetrics filters"),
        });
      });
  }, [requestBody]);

  useEffect(() => {
    if (projectId !== loadedProjectId) {
      setLoadedProjectId(projectId);
      setScope("in_scope");
      setTicketType("all");
      setFilters(emptyFilters);
      setFilterValues(createLoadState(emptyFilterValues));
      setSummary(createLoadState(emptySummary));
      setBacklog(createLoadState(emptyBacklog));
    }
  }, [loadedProjectId, projectId]);

  useEffect(() => {
    if (isActive && hasActiveProjectContext && requestBody) {
      void loadVolumetricsData();
    }
  }, [hasActiveProjectContext, isActive, loadVolumetricsData, requestBody, requestSignature]);

  function updateFilter(filterName: FilterKey, values: string[]) {
    setFilters((currentFilters) => ({
      ...currentFilters,
      [filterName]: values,
    }));
  }

  function resetFilters() {
    setScope("in_scope");
    setTicketType("all");
    setFilters(emptyFilters);
  }

  const averageLabel = timeGrain === "monthly" ? "Avg monthly" : "Avg weekly";

  return (
    <section className="volumetrics-dashboard-layout" aria-labelledby="volumetrics-tab-heading">
      <aside className="applications-filter-pane panel" aria-label="Volumetrics filters">
        <div className="applications-filter-heading">
          <div>
            <p className="label">Filters</p>
            <h2>Volumetrics &amp; SLA</h2>
          </div>
          <button className="secondary-button" type="button" onClick={resetFilters}>
            Reset Filters
          </button>
        </div>

        {filterValues.status === "loading" ? (
          <p className="muted-text">Loading filter values...</p>
        ) : null}
        {filterValues.status === "error" ? (
          <p className="error-text">{filterValues.error}</p>
        ) : null}

        <div className="applications-filter-stack">
          <ExcelMultiSelectFilter
            label="Scope of Applications"
            options={filterOptions.scope}
            selectedValues={[scope]}
            selectionMode="single"
            onChange={(values) => setScope((values[0] as VolumetricsScope) ?? "in_scope")}
          />
          <ExcelMultiSelectFilter
            label="Ticket Type"
            options={filterOptions.ticket_type}
            selectedValues={[ticketType]}
            selectionMode="single"
            onChange={(values) => setTicketType((values[0] as VolumetricsTicketType) ?? "all")}
          />
          <ExcelMultiSelectFilter
            label="Functional Track - AMS Owner"
            options={filterOptions.functional_track_ams_owner}
            selectedValues={filters.functional_track_ams_owner}
            onChange={(values) => updateFilter("functional_track_ams_owner", values)}
          />
          <ExcelMultiSelectFilter
            label="Assignment Group - Support Lead"
            options={filterOptions.assignment_group_support_lead}
            selectedValues={filters.assignment_group_support_lead}
            onChange={(values) => updateFilter("assignment_group_support_lead", values)}
          />
          <ExcelMultiSelectFilter
            label="Parent Business Application"
            options={filterOptions.parent_application_name}
            selectedValues={filters.parent_application_name}
            onChange={(values) => updateFilter("parent_application_name", values)}
          />
          <ExcelMultiSelectFilter
            label="Application Owner"
            options={filterOptions.application_owner}
            selectedValues={filters.application_owner}
            onChange={(values) => updateFilter("application_owner", values)}
          />
          <ExcelMultiSelectFilter
            label="Supported by Vendor"
            options={filterOptions.supported_by_vendor}
            selectedValues={filters.supported_by_vendor}
            onChange={(values) => updateFilter("supported_by_vendor", values)}
          />
        </div>
      </aside>

      <div className="volumetrics-main-pane">
        <p className="volumetrics-date-note">
          Data range: {formatDateShort(effectiveRange.startDate)} to {formatDateShort(effectiveRange.endDate)}
        </p>

        <section className="panel" aria-labelledby="volumetrics-tab-heading">
          <div className="panel-heading">
            <div>
              <p className="label">Volumetrics &amp; SLA</p>
              <h2 id="volumetrics-tab-heading">Ticket Volume and SLA Summary</h2>
            </div>
            <span className="volumetrics-selected-range">{effectiveRange.selectedLabel}</span>
          </div>

          <div className="volumetrics-controls">
            <div className="segmented-control" aria-label="Time range">
              <button
                className={timeGrain === "monthly" ? "active" : ""}
                type="button"
                onClick={() => setTimeGrain("monthly")}
              >
                Monthly
              </button>
              <button
                className={timeGrain === "weekly" ? "active" : ""}
                type="button"
                onClick={() => setTimeGrain("weekly")}
              >
                Weekly
              </button>
            </div>

            {timeGrain === "monthly" ? (
              <>
                <label>
                  <span>From</span>
                  <input
                    type="month"
                    value={startMonth}
                    onChange={(event) => setStartMonth(event.target.value)}
                  />
                </label>
                <label>
                  <span>To</span>
                  <input
                    type="month"
                    value={endMonth}
                    onChange={(event) => setEndMonth(event.target.value)}
                  />
                </label>
              </>
            ) : (
              <>
                <label>
                  <span>From week</span>
                  <input
                    type="date"
                    value={startWeek}
                    onChange={(event) => setStartWeek(event.target.value)}
                  />
                </label>
                <label>
                  <span>To week</span>
                  <input
                    type="date"
                    value={endWeek}
                    onChange={(event) => setEndWeek(event.target.value)}
                  />
                </label>
              </>
            )}
          </div>

          <div className="summary-grid volumetrics-summary-grid">
            <MetricCard
              label="Created"
              primary={`Total: ${formatNumber(summary.data.created.total)}`}
              secondary={`${averageLabel}: ${formatNumber(summary.data.created.average_per_period, 1)}`}
            />
            <MetricCard
              label="Resolved / Closed"
              primary={`Total: ${formatNumber(summary.data.resolved_closed.total)}`}
              secondary={`${averageLabel}: ${formatNumber(
                summary.data.resolved_closed.average_per_period,
                1
              )}`}
            />
            <MetricCard
              label="Cancelled"
              primary={`Total: ${formatNumber(summary.data.cancelled.total)}`}
              secondary={`${averageLabel}: ${formatNumber(summary.data.cancelled.average_per_period, 1)}`}
              tertiary={`% of Resolved+Cancelled: ${formatPercent(
                summary.data.cancelled.cancelled_pct_of_resolved_cancelled
              )}`}
            />
            <MetricCard
              label="Response SLA"
              primary={`${averageLabel} adherence: ${formatPercent(
                summary.data.response_sla.average_adherence_pct
              )}`}
              secondary={`${formatNumber(summary.data.response_sla.met_count)} met / ${formatNumber(
                summary.data.response_sla.applicable_count
              )} applicable`}
            />
            <MetricCard
              label="Resolution SLA"
              primary={`${averageLabel} adherence: ${formatPercent(
                summary.data.resolution_sla.average_adherence_pct
              )}`}
              secondary={`${formatNumber(
                summary.data.resolution_sla.met_count
              )} met / ${formatNumber(summary.data.resolution_sla.applicable_count)} applicable`}
            />
          </div>

          {summary.status === "loading" ? <p className="muted-text">Loading summary...</p> : null}
          {summary.status === "error" ? <p className="error-text">{summary.error}</p> : null}
        </section>

        <CreatedResolvedBacklogChart
          data={backlog.data}
          status={backlog.status}
          error={backlog.error}
          timeGrain={timeGrain}
        />
      </div>
    </section>
  );
}

function MetricCard({
  label,
  primary,
  secondary,
  tertiary,
}: {
  label: string;
  primary: string;
  secondary: string;
  tertiary?: string;
}) {
  return (
    <div>
      <p className="label">{label}</p>
      <strong>{primary}</strong>
      <div className="overview-ticket-details">
        <span>{secondary}</span>
        {tertiary ? <span>{tertiary}</span> : null}
      </div>
    </div>
  );
}

function CreatedResolvedBacklogChart({
  data,
  error,
  status,
  timeGrain,
}: {
  data: DashboardVolumetricsBacklog;
  error: string | null;
  status: LoadStatus;
  timeGrain: VolumetricsTimeGrain;
}) {
  const title = "Created vs Resolved/Closed vs Backlog(Open)";
  const { chartRef, copyMessage, handleCopy, plotWidth } = useChartFrame(title);
  const hasRows = data.rows.length > 0;
  const chartWidth = Math.max(820, plotWidth - 24, data.rows.length * (timeGrain === "monthly" ? 74 : 92));
  const canCopy = status !== "loading" && hasRows;

  return (
    <section className="chart-card volumetrics-chart-card" aria-label={title}>
      <div className="applications-chart-header">
        <div>
          <h3>{title}</h3>
          <p className="muted-text">Created and resolved/closed volumes with period-end backlog.</p>
        </div>
        <button
          className="secondary-button chart-copy-button"
          type="button"
          disabled={!canCopy}
          onClick={handleCopy}
        >
          Copy chart
        </button>
      </div>

      {status === "loading" ? <p className="muted-text chart-state-text">Loading chart...</p> : null}
      {status === "error" ? <p className="error-text">{error}</p> : null}
      {status !== "loading" && status !== "error" && !hasRows ? (
        <p className="muted-text chart-state-text">No chart data available.</p>
      ) : null}

      {status !== "loading" && status !== "error" && hasRows ? (
        <div className="applications-chart-plot volumetrics-chart-plot" ref={chartRef}>
          <div className="applications-chart-scroll">
            <div className="applications-chart-stage">
              <ComposedChart
                data={data.rows}
                width={chartWidth}
                height={380}
                margin={{ top: 34, right: 64, bottom: 82, left: 42 }}
              >
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis
                  dataKey="period_label"
                  angle={-35}
                  height={86}
                  interval={0}
                  textAnchor="end"
                  tickMargin={12}
                />
                <YAxis yAxisId="volume" hide />
                <YAxis yAxisId="backlog" orientation="right" hide />
                <Tooltip />
                <Legend />
                <Bar
                  dataKey="created_count"
                  fill={chartColors.created}
                  name="Created"
                  radius={[4, 4, 0, 0]}
                  yAxisId="volume"
                >
                  <LabelList dataKey="created_count" position="top" fontSize={11} />
                </Bar>
                <Bar
                  dataKey="resolved_closed_count"
                  fill={chartColors.resolved}
                  name="Resolved/Closed"
                  radius={[4, 4, 0, 0]}
                  yAxisId="volume"
                >
                  <LabelList dataKey="resolved_closed_count" position="top" fontSize={11} />
                </Bar>
                <Line
                  dataKey="backlog_open_count"
                  dot={{ r: 3 }}
                  name="Backlog(Open)"
                  stroke={chartColors.backlog}
                  strokeWidth={2.5}
                  type="monotone"
                  yAxisId="backlog"
                />
                {data.average_backlog_open !== null ? (
                  <ReferenceLine
                    y={data.average_backlog_open}
                    yAxisId="backlog"
                    stroke={chartColors.average}
                    strokeDasharray="6 4"
                    label={{
                      value: `Avg backlog: ${formatNumber(data.average_backlog_open, 0)}`,
                      position: "insideTopRight",
                      fill: chartColors.average,
                      fontSize: 12,
                    }}
                  />
                ) : null}
              </ComposedChart>
            </div>
          </div>
        </div>
      ) : null}

      {copyMessage ? <p className="chart-copy-status">{copyMessage}</p> : null}
    </section>
  );
}

export default VolumetricsDashboard;
