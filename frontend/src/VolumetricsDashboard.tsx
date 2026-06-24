import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ComposedChart,
  Customized,
  LabelList,
  Legend,
  Line,
  ReferenceLine,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import {
  getDashboardVolumetricsBacklog,
  getDashboardVolumetricsCreatedPattern,
  getDashboardVolumetricsCreatedResolvedCanceled,
  getDashboardVolumetricsDataRange,
  getDashboardVolumetricsFilterValues,
  getDashboardVolumetricsHourlyCreatedResolved,
  getDashboardVolumetricsIncidentBatchTrend,
  getDashboardVolumetricsPriorityDistribution,
  getDashboardVolumetricsSlaTrends,
  getDashboardVolumetricsSummary,
  getDashboardVolumetricsTopApplications,
  getDashboardVolumetricsTopIncidentBatchApplications,
} from "./api/dashboard";
import type {
  CreatedPatternType,
  DashboardVolumetricsBacklogOnly,
  DashboardVolumetricsCreatedPattern,
  DashboardVolumetricsCreatedResolvedCanceled,
  DashboardVolumetricsDataRange,
  DashboardVolumetricsFilterValues,
  DashboardVolumetricsFilters,
  DashboardVolumetricsHourlyCreatedResolved,
  DashboardVolumetricsIncidentBatchTrend,
  DashboardVolumetricsPriorityDistribution,
  DashboardVolumetricsRequest,
  DashboardVolumetricsSlaTrends,
  DashboardVolumetricsSummary,
  DashboardVolumetricsTopApplications,
  DashboardVolumetricsTopIncidentBatchApplications,
  VolumetricsDayType,
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
type VolumetricsSubTab =
  | "overall_volume"
  | "overall_sla"
  | "detailed_volume"
  | "kpi"
  | "category";
type PriorityDistributionView = "graph" | "table";
type TopNSelection = 10 | 20;

const monthNames = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

const defaultStartMonth = "2025-01";
const defaultEndMonth = "2026-06";
const maxWeeklyRangeWeeks = 15;

const emptyFilters: DashboardVolumetricsFilters = {
  functional_track_ams_owner: [],
  assignment_group_support_lead: [],
  parent_application_name: [],
  application_owner: [],
  supported_by_vendor: [],
  sap_non_sap: [],
};

const emptyFilterValues: DashboardVolumetricsFilterValues = {
  scope: [],
  ticket_type: [],
  functional_track_ams_owner: [],
  assignment_group_support_lead: [],
  parent_application_name: [],
  application_owner: [],
  supported_by_vendor: [],
  sap_non_sap: [],
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

const emptyDataRange: DashboardVolumetricsDataRange = {
  completion_date_min: null,
  completion_date_max: null,
};

const emptyVolumeTrend: DashboardVolumetricsCreatedResolvedCanceled = {
  time_grain: "monthly",
  points: [],
};

const emptyBacklog: DashboardVolumetricsBacklogOnly = {
  time_grain: "monthly",
  average_backlog: null,
  points: [],
};

const emptyCreatedPattern: DashboardVolumetricsCreatedPattern = {
  pattern_type: "day_of_month",
  points: [],
};

const emptyHourlyCreatedResolved: DashboardVolumetricsHourlyCreatedResolved = {
  day_type: "weekdays",
  denominator_days: 0,
  points: [],
};

const emptyPriorityDistribution: DashboardVolumetricsPriorityDistribution = {
  time_grain: "monthly",
  priorities: [],
  points: [],
};

const emptySlaTrends: DashboardVolumetricsSlaTrends = {
  time_grain: "monthly",
  not_applicable: false,
  response: [],
  resolution: [],
  logic: {
    response_adherence_formula:
      "response_sla_adhered_count / response_sla_captured_count * 100",
    resolution_adherence_formula:
      "resolution_sla_adhered_count / resolution_sla_captured_count * 100",
    captured_definition: "sla_breached IS NOT NULL",
  },
};

const emptyTopApplications: DashboardVolumetricsTopApplications = {
  ranking_window: {
    start_month: "",
    end_month: "",
    description: "Last 6 complete months excluding current month",
  },
  top_n: 10,
  points: [],
};

const emptyIncidentBatchTrend: DashboardVolumetricsIncidentBatchTrend = {
  applicable: true,
  message: "Batch-related charts are Incident-only and use Incident tickets within the selected filters.",
  batch_rule: {
    field: "short_description",
    rule_description:
      "Incident is batch-related when short_description contains Automic, case-insensitive.",
  },
  points: [],
};

const emptyTopIncidentBatchApplications: DashboardVolumetricsTopIncidentBatchApplications = {
  applicable: true,
  message: "Batch-related charts are Incident-only and use Incident tickets within the selected filters.",
  ranking_window: {
    start_month: "",
    end_month: "",
    description: "Last 6 complete months excluding current month",
  },
  top_n: 10,
  points: [],
};

const chartColors = {
  created: "#0f766e",
  resolved: "#2563eb",
  canceled: "#dc2626",
  backlog: "#d97706",
  average: "#7c3aed",
  pattern: "#0891b2",
  patternAlt: "#7c3aed",
  priority: ["#0f766e", "#2563eb", "#d97706", "#7c3aed", "#dc2626", "#64748b"],
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

function formatRoundedNumber(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "N/A";
  }
  return Math.ceil(value).toLocaleString();
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

function parseApiDateValue(value: string | null): Date | null {
  if (!value) {
    return null;
  }
  const [datePart] = value.split("T");
  const [year, month, day] = datePart.split("-").map(Number);
  if (!year || !month || !day) {
    return null;
  }
  return new Date(year, month - 1, day, 0, 0, 0, 0);
}

function formatApiDateLong(value: string | null): string {
  const date = parseApiDateValue(value);
  if (!date) {
    return "Not available";
  }
  return `${pad(date.getDate())}-${monthNames[date.getMonth()]}-${date.getFullYear()}`;
}

function formatDataAvailabilityRange(dataRange: DashboardVolumetricsDataRange): string {
  if (!dataRange.completion_date_min || !dataRange.completion_date_max) {
    return "Data availability: Not available";
  }
  return `Data available from ${formatApiDateLong(
    dataRange.completion_date_min
  )} to ${formatApiDateLong(dataRange.completion_date_max)}`;
}

function trendChartWidth(
  pointCount: number,
  timeGrain: VolumetricsTimeGrain,
  plotWidth: number
): number {
  const availableWidth = Math.max(760, plotWidth - 24);
  if (timeGrain === "monthly") {
    return availableWidth;
  }
  return Math.max(availableWidth, pointCount * 56);
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

function dateInputValue(date: Date): string {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

function monthInputValue(date: Date): string {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}`;
}

function subtractMonths(date: Date, months: number): Date {
  const nextDate = new Date(date);
  const originalDay = nextDate.getDate();
  nextDate.setMonth(nextDate.getMonth() - months);
  if (nextDate.getDate() !== originalDay) {
    nextDate.setDate(0);
  }
  return nextDate;
}

function defaultWeeklyRange() {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  return {
    start: dateInputValue(weekStartDate(dateInputValue(subtractMonths(today, 3)))),
    end: dateInputValue(weekStartDate(dateInputValue(today))),
  };
}

function weeksBetween(startDate: Date, endDate: Date): number {
  return Math.floor((endDate.getTime() - startDate.getTime()) / (7 * 24 * 60 * 60 * 1000));
}

function clampWeeklyStart(startValue: string, endValue: string): string {
  const startDate = weekStartDate(startValue);
  const endDate = weekStartDate(endValue);
  if (weeksBetween(startDate, endDate) <= maxWeeklyRangeWeeks - 1) {
    return dateInputValue(startDate);
  }
  const clampedStart = new Date(endDate);
  clampedStart.setDate(endDate.getDate() - (maxWeeklyRangeWeeks - 1) * 7);
  return dateInputValue(clampedStart);
}

function clampWeeklyEnd(startValue: string, endValue: string): string {
  const startDate = weekStartDate(startValue);
  const endDate = weekStartDate(endValue);
  if (weeksBetween(startDate, endDate) <= maxWeeklyRangeWeeks - 1) {
    return dateInputValue(endDate);
  }
  const clampedEnd = new Date(startDate);
  clampedEnd.setDate(startDate.getDate() + (maxWeeklyRangeWeeks - 1) * 7);
  return dateInputValue(clampedEnd);
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
  const [chartElement, setChartElement] = useState<HTMLDivElement | null>(null);
  const [plotWidth, setPlotWidth] = useState(0);
  const [copyMessage, setCopyMessage] = useState<string | null>(null);

  const chartRef = useCallback((element: HTMLDivElement | null) => {
    setChartElement(element);
  }, []);

  useEffect(() => {
    if (!chartElement) {
      return undefined;
    }

    const updatePlotWidth = () => {
      setPlotWidth(Math.floor(chartElement.clientWidth));
    };
    updatePlotWidth();

    const resizeObserver = new ResizeObserver(updatePlotWidth);
    resizeObserver.observe(chartElement);
    return () => resizeObserver.disconnect();
  }, [chartElement]);

  const handleCopy = useCallback(async () => {
    if (!chartElement) {
      return;
    }
    try {
      await copyChartToClipboard(chartElement, title);
      setCopyMessage("Copied chart image to clipboard.");
    } catch (error) {
      setCopyMessage(errorMessage(error, "This browser could not copy the chart image."));
    }
  }, [chartElement, title]);

  return { chartRef, copyMessage, handleCopy, plotWidth };
}

function VolumetricsDashboard({ projectId, isActive }: VolumetricsDashboardProps) {
  const [scope, setScope] = useState<VolumetricsScope>("in_scope");
  const [ticketType, setTicketType] = useState<VolumetricsTicketType>("all");
  const [timeGrain, setTimeGrain] = useState<VolumetricsTimeGrain>("monthly");
  const [startMonth, setStartMonth] = useState(defaultStartMonth);
  const [endMonth, setEndMonth] = useState(defaultEndMonth);
  const [startWeek, setStartWeek] = useState(() => defaultWeeklyRange().start);
  const [endWeek, setEndWeek] = useState(() => defaultWeeklyRange().end);
  const [activeSubTab, setActiveSubTab] = useState<VolumetricsSubTab>("overall_volume");
  const [createdPatternType, setCreatedPatternType] =
    useState<CreatedPatternType>("day_of_month");
  const [hourlyDayType, setHourlyDayType] = useState<VolumetricsDayType>("weekdays");
  const [priorityView, setPriorityView] = useState<PriorityDistributionView>("graph");
  const [topApplicationsN, setTopApplicationsN] = useState<TopNSelection>(10);
  const [topBatchApplicationsN, setTopBatchApplicationsN] = useState<TopNSelection>(10);
  const [filters, setFilters] = useState<DashboardVolumetricsFilters>(emptyFilters);
  const [filterValues, setFilterValues] = useState<LoadState<DashboardVolumetricsFilterValues>>(
    createLoadState(emptyFilterValues)
  );
  const [summary, setSummary] = useState<LoadState<DashboardVolumetricsSummary>>(
    createLoadState(emptySummary)
  );
  const [dataRange, setDataRange] = useState<LoadState<DashboardVolumetricsDataRange>>(
    createLoadState(emptyDataRange)
  );
  const [volumeTrend, setVolumeTrend] = useState<
    LoadState<DashboardVolumetricsCreatedResolvedCanceled>
  >(createLoadState(emptyVolumeTrend));
  const [backlog, setBacklog] = useState<LoadState<DashboardVolumetricsBacklogOnly>>(
    createLoadState(emptyBacklog)
  );
  const [createdPattern, setCreatedPattern] = useState<
    LoadState<DashboardVolumetricsCreatedPattern>
  >(createLoadState(emptyCreatedPattern));
  const [hourlyCreatedResolved, setHourlyCreatedResolved] = useState<
    LoadState<DashboardVolumetricsHourlyCreatedResolved>
  >(createLoadState(emptyHourlyCreatedResolved));
  const [priorityDistribution, setPriorityDistribution] = useState<
    LoadState<DashboardVolumetricsPriorityDistribution>
  >(createLoadState(emptyPriorityDistribution));
  const [slaTrends, setSlaTrends] = useState<LoadState<DashboardVolumetricsSlaTrends>>(
    createLoadState(emptySlaTrends)
  );
  const [topApplications, setTopApplications] = useState<
    LoadState<DashboardVolumetricsTopApplications>
  >(createLoadState(emptyTopApplications));
  const [incidentBatchTrend, setIncidentBatchTrend] = useState<
    LoadState<DashboardVolumetricsIncidentBatchTrend>
  >(createLoadState(emptyIncidentBatchTrend));
  const [topIncidentBatchApplications, setTopIncidentBatchApplications] = useState<
    LoadState<DashboardVolumetricsTopIncidentBatchApplications>
  >(createLoadState(emptyTopIncidentBatchApplications));
  const [loadedProjectId, setLoadedProjectId] = useState("");
  const [rangeInitializedProjectId, setRangeInitializedProjectId] = useState("");

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
  const availableStartDate = parseApiDateValue(dataRange.data.completion_date_min);
  const availableEndDate = parseApiDateValue(dataRange.data.completion_date_max);
  const availableStartMonth = availableStartDate ? monthInputValue(availableStartDate) : undefined;
  const availableEndMonth = availableEndDate ? monthInputValue(availableEndDate) : undefined;
  const availableStartWeek = availableStartDate
    ? dateInputValue(weekStartDate(dateInputValue(availableStartDate)))
    : undefined;
  const availableEndWeek = availableEndDate ? dateInputValue(availableEndDate) : undefined;

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
      sap_non_sap: singleOptions(filterValues.data.sap_non_sap),
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
  const isDateRangeReady = dataRange.status === "error" || rangeInitializedProjectId === projectId;

  const loadDataRange = useCallback(async () => {
    const cleanedProjectId = projectId.trim();
    if (!cleanedProjectId) {
      return;
    }
    setDataRange(createLoadState(emptyDataRange, "loading"));
    try {
      const nextDataRange = await getDashboardVolumetricsDataRange(cleanedProjectId);
      setDataRange({ status: "success", data: nextDataRange, error: null });
    } catch (error) {
      setDataRange({
        status: "error",
        data: emptyDataRange,
        error: errorMessage(error, "Unable to load available data range"),
      });
    }
  }, [projectId]);

  const loadVolumetricsData = useCallback(async () => {
    if (!requestBody) {
      return;
    }

    setFilterValues(createLoadState(emptyFilterValues, "loading"));
    setSummary(createLoadState(emptySummary, "loading"));
    setVolumeTrend(createLoadState(emptyVolumeTrend, "loading"));
    setBacklog(createLoadState(emptyBacklog, "loading"));
    setCreatedPattern(createLoadState(emptyCreatedPattern, "loading"));
    setHourlyCreatedResolved(createLoadState(emptyHourlyCreatedResolved, "loading"));
    setPriorityDistribution(createLoadState(emptyPriorityDistribution, "loading"));
    setSlaTrends(createLoadState(emptySlaTrends, "loading"));
    setTopApplications(createLoadState(emptyTopApplications, "loading"));
    setIncidentBatchTrend(createLoadState(emptyIncidentBatchTrend, "loading"));
    setTopIncidentBatchApplications(createLoadState(emptyTopIncidentBatchApplications, "loading"));

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

    void getDashboardVolumetricsCreatedResolvedCanceled(requestBody)
      .then((nextVolumeTrend) => {
        setVolumeTrend({ status: "success", data: nextVolumeTrend, error: null });
      })
      .catch((error) => {
        setVolumeTrend({
          status: "error",
          data: emptyVolumeTrend,
          error: errorMessage(error, "Unable to load Created/Resolved/Canceled chart"),
        });
      });

    void getDashboardVolumetricsBacklog(requestBody)
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

    void getDashboardVolumetricsCreatedPattern(requestBody, createdPatternType)
      .then((nextCreatedPattern) => {
        setCreatedPattern({ status: "success", data: nextCreatedPattern, error: null });
      })
      .catch((error) => {
        setCreatedPattern({
          status: "error",
          data: emptyCreatedPattern,
          error: errorMessage(error, "Unable to load created pattern chart"),
        });
      });

    void getDashboardVolumetricsHourlyCreatedResolved(requestBody, hourlyDayType)
      .then((nextHourlyCreatedResolved) => {
        setHourlyCreatedResolved({
          status: "success",
          data: nextHourlyCreatedResolved,
          error: null,
        });
      })
      .catch((error) => {
        setHourlyCreatedResolved({
          status: "error",
          data: emptyHourlyCreatedResolved,
          error: errorMessage(error, "Unable to load hourly created/resolved chart"),
        });
      });

    void getDashboardVolumetricsPriorityDistribution(requestBody)
      .then((nextPriorityDistribution) => {
        setPriorityDistribution({
          status: "success",
          data: nextPriorityDistribution,
          error: null,
        });
      })
      .catch((error) => {
        setPriorityDistribution({
          status: "error",
          data: emptyPriorityDistribution,
          error: errorMessage(error, "Unable to load priority distribution"),
        });
      });

    void getDashboardVolumetricsSlaTrends(requestBody)
      .then((nextSlaTrends) => {
        setSlaTrends({ status: "success", data: nextSlaTrends, error: null });
      })
      .catch((error) => {
        setSlaTrends({
          status: "error",
          data: emptySlaTrends,
          error: errorMessage(error, "Unable to load SLA trends"),
        });
      });

    void getDashboardVolumetricsTopApplications(requestBody, topApplicationsN)
      .then((nextTopApplications) => {
        setTopApplications({ status: "success", data: nextTopApplications, error: null });
      })
      .catch((error) => {
        setTopApplications({
          status: "error",
          data: emptyTopApplications,
          error: errorMessage(error, "Unable to load top applications"),
        });
      });

    void getDashboardVolumetricsIncidentBatchTrend(requestBody)
      .then((nextIncidentBatchTrend) => {
        setIncidentBatchTrend({
          status: "success",
          data: nextIncidentBatchTrend,
          error: null,
        });
      })
      .catch((error) => {
        setIncidentBatchTrend({
          status: "error",
          data: emptyIncidentBatchTrend,
          error: errorMessage(error, "Unable to load Incident batch trend"),
        });
      });

    void getDashboardVolumetricsTopIncidentBatchApplications(
      requestBody,
      topBatchApplicationsN
    )
      .then((nextTopIncidentBatchApplications) => {
        setTopIncidentBatchApplications({
          status: "success",
          data: nextTopIncidentBatchApplications,
          error: null,
        });
      })
      .catch((error) => {
        setTopIncidentBatchApplications({
          status: "error",
          data: emptyTopIncidentBatchApplications,
          error: errorMessage(error, "Unable to load top Incident batch applications"),
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
  }, [
    createdPatternType,
    hourlyDayType,
    requestBody,
    topApplicationsN,
    topBatchApplicationsN,
  ]);

  useEffect(() => {
    if (projectId !== loadedProjectId) {
      setLoadedProjectId(projectId);
      setScope("in_scope");
      setTicketType("all");
      setFilters(emptyFilters);
      setActiveSubTab("overall_volume");
      setHourlyDayType("weekdays");
      setPriorityView("graph");
      setTopApplicationsN(10);
      setTopBatchApplicationsN(10);
      setFilterValues(createLoadState(emptyFilterValues));
      setSummary(createLoadState(emptySummary));
      setDataRange(createLoadState(emptyDataRange));
      setVolumeTrend(createLoadState(emptyVolumeTrend));
      setBacklog(createLoadState(emptyBacklog));
      setCreatedPattern(createLoadState(emptyCreatedPattern));
      setHourlyCreatedResolved(createLoadState(emptyHourlyCreatedResolved));
      setPriorityDistribution(createLoadState(emptyPriorityDistribution));
      setSlaTrends(createLoadState(emptySlaTrends));
      setTopApplications(createLoadState(emptyTopApplications));
      setIncidentBatchTrend(createLoadState(emptyIncidentBatchTrend));
      setTopIncidentBatchApplications(createLoadState(emptyTopIncidentBatchApplications));
      setRangeInitializedProjectId("");
    }
  }, [loadedProjectId, projectId]);

  useEffect(() => {
    if (isActive && hasActiveProjectContext && dataRange.status === "idle") {
      void loadDataRange();
    }
  }, [dataRange.status, hasActiveProjectContext, isActive, loadDataRange]);

  useEffect(() => {
    if (
      dataRange.status !== "success" ||
      !projectId.trim() ||
      rangeInitializedProjectId === projectId
    ) {
      return;
    }

    const availableStart = parseApiDateValue(dataRange.data.completion_date_min);
    const availableEnd = parseApiDateValue(dataRange.data.completion_date_max);
    if (!availableStart || !availableEnd) {
      setRangeInitializedProjectId(projectId);
      return;
    }

    setStartMonth(monthInputValue(availableStart));
    setEndMonth(monthInputValue(availableEnd));

    const latestWeekStart = weekStartDate(dateInputValue(availableEnd));
    const earliestAvailableWeekStart = weekStartDate(dateInputValue(availableStart));
    const earliestAllowedWeekStart = new Date(latestWeekStart);
    earliestAllowedWeekStart.setDate(
      latestWeekStart.getDate() - (maxWeeklyRangeWeeks - 1) * 7
    );
    const nextWeeklyStart =
      earliestAvailableWeekStart > earliestAllowedWeekStart
        ? earliestAvailableWeekStart
        : earliestAllowedWeekStart;

    setStartWeek(dateInputValue(nextWeeklyStart));
    setEndWeek(dateInputValue(availableEnd));
    setRangeInitializedProjectId(projectId);
  }, [
    dataRange.data.completion_date_max,
    dataRange.data.completion_date_min,
    dataRange.status,
    projectId,
    rangeInitializedProjectId,
  ]);

  useEffect(() => {
    if (isActive && hasActiveProjectContext && isDateRangeReady && requestBody) {
      void loadVolumetricsData();
    }
  }, [
    hasActiveProjectContext,
    isActive,
    isDateRangeReady,
    loadVolumetricsData,
    requestBody,
    requestSignature,
  ]);

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

  function handleStartWeekChange(value: string) {
    const nextStartWeek = clampWeeklyStart(value, endWeek);
    setStartWeek(nextStartWeek);
    if (weekStartDate(nextStartWeek) > weekStartDate(endWeek)) {
      setEndWeek(nextStartWeek);
    }
  }

  function handleEndWeekChange(value: string) {
    const nextEndWeek = clampWeeklyEnd(startWeek, value);
    setEndWeek(nextEndWeek);
    if (weekStartDate(nextEndWeek) < weekStartDate(startWeek)) {
      setStartWeek(nextEndWeek);
    }
  }

  const averageLabel = timeGrain === "monthly" ? "Avg monthly" : "Avg weekly";
  const canceledMetricLabel = cancellationMetricLabel(ticketType);

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
            label="SAP / Non-SAP"
            options={filterOptions.sap_non_sap}
            selectedValues={filters.sap_non_sap}
            onChange={(values) => updateFilter("sap_non_sap", values)}
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
          {dataRange.status === "loading"
            ? "Loading available data range..."
            : formatDataAvailabilityRange(dataRange.data)}
        </p>
        {dataRange.status === "error" ? (
          <p className="error-text volumetrics-date-note">{dataRange.error}</p>
        ) : null}

        <VolumetricsSubTabs activeSubTab={activeSubTab} onChange={setActiveSubTab} />

        <section className="panel" aria-labelledby="volumetrics-tab-heading">
          <div className="panel-heading">
            <div>
              <p className="label">Volumetrics &amp; SLA</p>
              <h2 id="volumetrics-tab-heading">Ticket Volume and SLA Controls</h2>
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
                    min={availableStartMonth}
                    max={availableEndMonth}
                    onChange={(event) => setStartMonth(event.target.value)}
                  />
                </label>
                <label>
                  <span>To</span>
                  <input
                    type="month"
                    value={endMonth}
                    min={availableStartMonth}
                    max={availableEndMonth}
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
                    min={availableStartWeek}
                    max={availableEndWeek}
                    onChange={(event) => handleStartWeekChange(event.target.value)}
                  />
                </label>
                <label>
                  <span>To week</span>
                  <input
                    type="date"
                    value={endWeek}
                    min={availableStartWeek}
                    max={availableEndWeek}
                    onChange={(event) => handleEndWeekChange(event.target.value)}
                  />
                </label>
                <p className="volumetrics-range-note">
                  Weekly view is limited to 3 months, about 15 weeks, to keep charts easy to read.
                </p>
              </>
            )}
          </div>
        </section>

        {activeSubTab === "overall_volume" ? (
          <>
            <section className="panel">
              <div className="summary-grid volumetrics-summary-grid">
                <MetricCard
                  label="Created"
                  primary={`Total: ${formatNumber(summary.data.created.total)}`}
                  secondary={`${averageLabel}: ${formatNumber(
                    summary.data.created.average_per_period,
                    1
                  )}`}
                  index={0}
                />
                <MetricCard
                  label="Resolved / Closed"
                  primary={`Total: ${formatNumber(summary.data.resolved_closed.total)}`}
                  secondary={`${averageLabel}: ${formatNumber(
                    summary.data.resolved_closed.average_per_period,
                    1
                  )}`}
                  index={1}
                />
                <MetricCard
                  label={canceledMetricLabel}
                  primary={`Total: ${formatNumber(summary.data.cancelled.total)}`}
                  secondary={`${averageLabel}: ${formatNumber(
                    summary.data.cancelled.average_per_period,
                    1
                  )}`}
                  tertiary={`% of Resolved+${canceledMetricLabel}: ${formatPercent(
                    summary.data.cancelled.cancelled_pct_of_resolved_cancelled
                  )}`}
                  index={2}
                />
                <MetricCard
                  label="Response SLA"
                  primary={`${averageLabel} adherence: ${formatPercent(
                    summary.data.response_sla.average_adherence_pct
                  )}`}
                  secondary={`${formatNumber(
                    summary.data.response_sla.met_count
                  )} met / ${formatNumber(summary.data.response_sla.applicable_count)} applicable`}
                  index={3}
                />
                <MetricCard
                  label="Resolution SLA"
                  primary={`${averageLabel} adherence: ${formatPercent(
                    summary.data.resolution_sla.average_adherence_pct
                  )}`}
                  secondary={`${formatNumber(
                    summary.data.resolution_sla.met_count
                  )} met / ${formatNumber(
                    summary.data.resolution_sla.applicable_count
                  )} applicable`}
                  index={4}
                />
              </div>

              {summary.status === "loading" ? (
                <p className="muted-text">Loading summary...</p>
              ) : null}
              {summary.status === "error" ? <p className="error-text">{summary.error}</p> : null}
            </section>

            <CreatedResolvedCanceledChart
              data={volumeTrend.data}
              status={volumeTrend.status}
              error={volumeTrend.error}
              ticketType={ticketType}
              timeGrain={timeGrain}
            />

            <BacklogChart
              data={backlog.data}
              status={backlog.status}
              error={backlog.error}
              timeGrain={timeGrain}
            />

            <CreatedPatternChart
              data={createdPattern.data}
              status={createdPattern.status}
              error={createdPattern.error}
              patternType={createdPatternType}
              onPatternTypeChange={setCreatedPatternType}
            />

            <HourlyCreatedResolvedChart
              data={hourlyCreatedResolved.data}
              status={hourlyCreatedResolved.status}
              error={hourlyCreatedResolved.error}
              dayType={hourlyDayType}
              onDayTypeChange={setHourlyDayType}
              ticketType={ticketType}
            />

            <PriorityDistributionChart
              data={priorityDistribution.data}
              status={priorityDistribution.status}
              error={priorityDistribution.error}
              view={priorityView}
              onViewChange={setPriorityView}
              timeGrain={timeGrain}
            />
          </>
        ) : null}

        {activeSubTab === "overall_sla" ? (
          <OverallSlaTrends
            data={slaTrends.data}
            status={slaTrends.status}
            error={slaTrends.error}
            ticketType={ticketType}
            timeGrain={timeGrain}
          />
        ) : null}

        {activeSubTab === "detailed_volume" ? (
          <DetailedVolumeTrends
            incidentBatchTrend={incidentBatchTrend.data}
            incidentBatchTrendError={incidentBatchTrend.error}
            incidentBatchTrendStatus={incidentBatchTrend.status}
            onTopApplicationsNChange={setTopApplicationsN}
            onTopBatchApplicationsNChange={setTopBatchApplicationsN}
            ticketType={ticketType}
            topApplications={topApplications.data}
            topApplicationsError={topApplications.error}
            topApplicationsN={topApplicationsN}
            topApplicationsStatus={topApplications.status}
            topIncidentBatchApplications={topIncidentBatchApplications.data}
            topIncidentBatchApplicationsError={topIncidentBatchApplications.error}
            topIncidentBatchApplicationsStatus={topIncidentBatchApplications.status}
            topBatchApplicationsN={topBatchApplicationsN}
          />
        ) : null}
        {activeSubTab === "kpi" ? <VolumetricsPlaceholder title="KPI Trends" /> : null}
        {activeSubTab === "category" ? (
          <VolumetricsPlaceholder title="Category-wise Trends" />
        ) : null}
      </div>
    </section>
  );
}

function cancellationMetricLabel(ticketType: VolumetricsTicketType): string {
  if (ticketType === "incident") {
    return "Canceled";
  }
  if (ticketType === "sc_task") {
    return "Closed Incomplete";
  }
  return "Canceled / Closed Incomplete";
}

function summaryTileToneClass(index: number, columns: number): string {
  const row = Math.floor(index / columns);
  const column = index % columns;
  return (row + column) % 2 === 0 ? "summary-tile-dark" : "summary-tile-light";
}

function MetricCard({
  label,
  primary,
  secondary,
  tertiary,
  index,
}: {
  label: string;
  primary: string;
  secondary: string;
  tertiary?: string;
  index: number;
}) {
  return (
    <div className={summaryTileToneClass(index, 5)}>
      <p className="label">{label}</p>
      <strong>{primary}</strong>
      <div className="overview-ticket-details">
        <span>{secondary}</span>
        {tertiary ? <span>{tertiary}</span> : null}
      </div>
    </div>
  );
}

const volumetricsSubTabs: Array<{ value: VolumetricsSubTab; label: string }> = [
  { value: "overall_volume", label: "Overall Volume Trends" },
  { value: "overall_sla", label: "Overall SLA Trends" },
  { value: "detailed_volume", label: "Detailed Volume Trends" },
  { value: "kpi", label: "KPI Trends" },
  { value: "category", label: "Category-wise Trends" },
];

function VolumetricsSubTabs({
  activeSubTab,
  onChange,
}: {
  activeSubTab: VolumetricsSubTab;
  onChange: (value: VolumetricsSubTab) => void;
}) {
  return (
    <div className="dashboard-subtabs volumetrics-subtabs" role="tablist">
      {volumetricsSubTabs.map((tab) => (
        <button
          aria-selected={activeSubTab === tab.value}
          className={activeSubTab === tab.value ? "active" : ""}
          key={tab.value}
          type="button"
          onClick={() => onChange(tab.value)}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}

function VolumetricsPlaceholder({ title }: { title: string }) {
  return (
    <section className="panel volumetrics-placeholder-panel">
      <p className="label">{title}</p>
      <h3>Detailed requirements for this section will be added in the next prompts.</h3>
    </section>
  );
}

const topNOptions: TopNSelection[] = [10, 20];

function topNSelector(
  label: string,
  selectedValue: TopNSelection,
  onChange: (value: TopNSelection) => void
) {
  return (
    <div className="segmented-control volumetrics-compact-toggle" aria-label={label}>
      {topNOptions.map((value) => (
        <button
          className={selectedValue === value ? "active" : ""}
          key={value}
          type="button"
          onClick={() => onChange(value)}
        >
          Top {value}
        </button>
      ))}
    </div>
  );
}

function rankingWindowText(
  rankingWindow: DashboardVolumetricsTopApplications["ranking_window"]
): string {
  if (!rankingWindow.start_month || !rankingWindow.end_month) {
    return "Ranking uses average monthly created tickets for the last 6 complete months, excluding the current month.";
  }
  return `Ranking uses average monthly created tickets for ${rankingWindow.start_month} to ${rankingWindow.end_month}, excluding the current month.`;
}

function DetailedVolumeTrends({
  incidentBatchTrend,
  incidentBatchTrendError,
  incidentBatchTrendStatus,
  onTopApplicationsNChange,
  onTopBatchApplicationsNChange,
  ticketType,
  topApplications,
  topApplicationsError,
  topApplicationsN,
  topApplicationsStatus,
  topBatchApplicationsN,
  topIncidentBatchApplications,
  topIncidentBatchApplicationsError,
  topIncidentBatchApplicationsStatus,
}: {
  incidentBatchTrend: DashboardVolumetricsIncidentBatchTrend;
  incidentBatchTrendError: string | null;
  incidentBatchTrendStatus: LoadStatus;
  onTopApplicationsNChange: (value: TopNSelection) => void;
  onTopBatchApplicationsNChange: (value: TopNSelection) => void;
  ticketType: VolumetricsTicketType;
  topApplications: DashboardVolumetricsTopApplications;
  topApplicationsError: string | null;
  topApplicationsN: TopNSelection;
  topApplicationsStatus: LoadStatus;
  topBatchApplicationsN: TopNSelection;
  topIncidentBatchApplications: DashboardVolumetricsTopIncidentBatchApplications;
  topIncidentBatchApplicationsError: string | null;
  topIncidentBatchApplicationsStatus: LoadStatus;
}) {
  return (
    <>
      <TopApplicationsParetoChart
        canceledLabel={
          ticketType === "incident"
            ? "Average Canceled Count"
            : ticketType === "sc_task"
              ? "Average Closed Incomplete Count"
              : "Average Canceled / Closed Incomplete Count"
        }
        createdLabel="Average Created Count"
        data={topApplications.points.map((point) => ({
          application_name: point.application_name,
          average_created: point.average_created,
          average_canceled: point.average_canceled_closed_incomplete,
          created_label: point.created_label,
          canceled_label: point.canceled_label,
          pareto_cumulative_pct: point.pareto_cumulative_pct,
        }))}
        description={rankingWindowText(topApplications.ranking_window)}
        error={topApplicationsError}
        onTopNChange={onTopApplicationsNChange}
        status={topApplicationsStatus}
        title="Top High-Volume Applications"
        topN={topApplicationsN}
      />

      <IncidentBatchTrendChart
        data={incidentBatchTrend}
        error={incidentBatchTrendError}
        status={incidentBatchTrendStatus}
      />

      <TopApplicationsParetoChart
        canceledLabel="Average Batch Canceled Count"
        createdLabel="Average Batch Created Count"
        data={topIncidentBatchApplications.points.map((point) => ({
          application_name: point.application_name,
          average_created: point.average_batch_created,
          average_canceled: point.average_batch_canceled,
          created_label: point.batch_created_label,
          canceled_label: point.batch_canceled_label,
          pareto_cumulative_pct: point.pareto_cumulative_pct,
        }))}
        description={`${topIncidentBatchApplications.message} ${rankingWindowText(
          topIncidentBatchApplications.ranking_window
        )}`}
        error={topIncidentBatchApplicationsError}
        notApplicable={!topIncidentBatchApplications.applicable}
        notApplicableMessage={topIncidentBatchApplications.message}
        onTopNChange={onTopBatchApplicationsNChange}
        status={topIncidentBatchApplicationsStatus}
        title="Top Applications with Incident Batch-Related Tickets"
        topN={topBatchApplicationsN}
      />
    </>
  );
}

type ParetoChartPoint = {
  application_name: string;
  average_created: number;
  average_canceled: number;
  created_label: number;
  canceled_label: number;
  pareto_cumulative_pct: number | null;
};

function TopApplicationsParetoChart({
  canceledLabel,
  createdLabel,
  data,
  description,
  error,
  notApplicable = false,
  notApplicableMessage,
  onTopNChange,
  status,
  title,
  topN,
}: {
  canceledLabel: string;
  createdLabel: string;
  data: ParetoChartPoint[];
  description: string;
  error: string | null;
  notApplicable?: boolean;
  notApplicableMessage?: string;
  onTopNChange: (value: TopNSelection) => void;
  status: LoadStatus;
  title: string;
  topN: TopNSelection;
}) {
  const { chartRef, copyMessage, handleCopy, plotWidth } = useChartFrame(title);
  const hasRows = data.length > 0;
  const chartWidth = Math.max(Math.max(860, plotWidth - 24), data.length * 68);
  const canCopy = status !== "loading" && hasRows && !notApplicable;

  return (
    <section className="chart-card volumetrics-chart-card" aria-label={title}>
      <div className="applications-chart-header">
        <div>
          <h3>{title}</h3>
          <p className="muted-text">{description}</p>
        </div>
        <div className="volumetrics-chart-actions">
          {topNSelector(`${title} top N`, topN, onTopNChange)}
          <button
            className="secondary-button chart-copy-button"
            type="button"
            disabled={!canCopy}
            onClick={handleCopy}
          >
            Copy chart
          </button>
        </div>
      </div>

      {status === "loading" ? <p className="muted-text chart-state-text">Loading chart...</p> : null}
      {status === "error" ? <p className="error-text">{error}</p> : null}
      {notApplicable ? (
        <p className="muted-text chart-state-text">{notApplicableMessage}</p>
      ) : null}
      {status !== "loading" && status !== "error" && !notApplicable && !hasRows ? (
        <p className="muted-text chart-state-text">No chart data available.</p>
      ) : null}

      {status !== "loading" && status !== "error" && !notApplicable && hasRows ? (
        <div className="applications-chart-plot volumetrics-chart-plot" ref={chartRef}>
          <div className="applications-chart-scroll">
            <div className="applications-chart-stage">
              <ComposedChart
                data={data}
                width={chartWidth}
                height={430}
                margin={{ top: 56, right: 68, bottom: 132, left: 44 }}
              >
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis
                  dataKey="application_name"
                  angle={-35}
                  height={128}
                  interval={0}
                  textAnchor="end"
                  tickMargin={14}
                />
                <YAxis yAxisId="volume" hide />
                <YAxis
                  yAxisId="pareto"
                  orientation="right"
                  domain={[0, 100]}
                  tickFormatter={(value) => `${value}%`}
                />
                <Tooltip
                  formatter={(value, name) =>
                    name === "Pareto cumulative %"
                      ? formatPercent(Number(value))
                      : formatNumber(Number(value), 1)
                  }
                />
                <Legend />
                <Bar
                  dataKey="average_created"
                  fill={chartColors.created}
                  name={createdLabel}
                  radius={[4, 4, 0, 0]}
                  yAxisId="volume"
                >
                  <LabelList dataKey="created_label" position="top" fontSize={10} />
                </Bar>
                <Bar
                  dataKey="average_canceled"
                  fill={chartColors.canceled}
                  name={canceledLabel}
                  radius={[4, 4, 0, 0]}
                  yAxisId="volume"
                >
                  <LabelList dataKey="canceled_label" position="top" fontSize={10} />
                </Bar>
                <Line
                  connectNulls
                  dataKey="pareto_cumulative_pct"
                  dot={{ r: 4 }}
                  name="Pareto cumulative %"
                  stroke={chartColors.average}
                  strokeWidth={2.5}
                  type="monotone"
                  yAxisId="pareto"
                >
                  <LabelList
                    dataKey="pareto_cumulative_pct"
                    fontSize={11}
                    fontWeight={900}
                    formatter={(value) => formatPercent(Number(value))}
                    position="top"
                  />
                </Line>
              </ComposedChart>
            </div>
          </div>
        </div>
      ) : null}

      {copyMessage ? <p className="chart-copy-status">{copyMessage}</p> : null}
    </section>
  );
}

function IncidentBatchTrendChart({
  data,
  error,
  status,
}: {
  data: DashboardVolumetricsIncidentBatchTrend;
  error: string | null;
  status: LoadStatus;
}) {
  const title = "Incident Batch-Related Tickets Created Trend";
  const { chartRef, copyMessage, handleCopy, plotWidth } = useChartFrame(title);
  const hasRows = data.points.length > 0;
  const chartWidth = Math.max(760, plotWidth - 24);
  const canCopy = status !== "loading" && data.applicable && hasRows;

  return (
    <section className="chart-card volumetrics-chart-card" aria-label={title}>
      <div className="applications-chart-header">
        <div>
          <h3>{title}</h3>
          <p className="muted-text">{data.message}</p>
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
      {!data.applicable ? <p className="muted-text chart-state-text">{data.message}</p> : null}
      {status !== "loading" && status !== "error" && data.applicable && !hasRows ? (
        <p className="muted-text chart-state-text">No Incident batch-related tickets found.</p>
      ) : null}

      {status !== "loading" && status !== "error" && data.applicable && hasRows ? (
        <div className="applications-chart-plot volumetrics-chart-plot" ref={chartRef}>
          <div className="applications-chart-scroll">
            <div className="applications-chart-stage">
              <BarChart
                data={data.points}
                width={chartWidth}
                height={340}
                margin={{ top: 34, right: 42, bottom: 82, left: 34 }}
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
                <YAxis hide />
                <Tooltip />
                <Legend />
                <Bar
                  dataKey="batch_created_count"
                  fill={chartColors.backlog}
                  name="Batch Created"
                  radius={[4, 4, 0, 0]}
                >
                  <LabelList dataKey="batch_created_count" position="top" fontSize={11} />
                </Bar>
              </BarChart>
            </div>
          </div>
        </div>
      ) : null}

      {copyMessage ? <p className="chart-copy-status">{copyMessage}</p> : null}
    </section>
  );
}

function resolvedClosedMetricLabel(ticketType: VolumetricsTicketType): string {
  if (ticketType === "incident") {
    return "Resolved";
  }
  if (ticketType === "sc_task") {
    return "Closed";
  }
  return "Resolved/Closed";
}

function createdResolvedCanceledTitle(ticketType: VolumetricsTicketType): string {
  if (ticketType === "incident") {
    return "Created vs Resolved vs Canceled";
  }
  if (ticketType === "sc_task") {
    return "Created vs Closed vs Closed Incomplete";
  }
  return "Created vs Resolved/Closed vs Canceled / Closed Incomplete";
}

function CreatedResolvedCanceledChart({
  data,
  error,
  status,
  ticketType,
  timeGrain,
}: {
  data: DashboardVolumetricsCreatedResolvedCanceled;
  error: string | null;
  status: LoadStatus;
  ticketType: VolumetricsTicketType;
  timeGrain: VolumetricsTimeGrain;
}) {
  const title = createdResolvedCanceledTitle(ticketType);
  const resolvedLabel = resolvedClosedMetricLabel(ticketType);
  const canceledLabel = cancellationMetricLabel(ticketType);
  const { chartRef, copyMessage, handleCopy, plotWidth } = useChartFrame(title);
  const hasRows = data.points.length > 0;
  const chartWidth = trendChartWidth(data.points.length, timeGrain, plotWidth);
  const canCopy = status !== "loading" && hasRows;

  return (
    <section className="chart-card volumetrics-chart-card" aria-label={title}>
      <div className="applications-chart-header">
        <div>
          <h3>{title}</h3>
          <p className="muted-text">
            Period movement for created, completed, and canceled/closed incomplete tickets.
          </p>
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
                data={data.points}
                width={chartWidth}
                height={380}
                margin={{ top: 58, right: 44, bottom: 82, left: 34 }}
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
                <Tooltip />
                <Legend />
                <Bar
                  dataKey="created_count"
                  fill={chartColors.created}
                  name="Created"
                  radius={[4, 4, 0, 0]}
                  yAxisId="volume"
                >
                  <LabelList
                    angle={-90}
                    dataKey="created_count"
                    fontSize={10}
                    offset={14}
                    position="top"
                  />
                </Bar>
                <Bar
                  dataKey="resolved_closed_count"
                  fill={chartColors.resolved}
                  name={resolvedLabel}
                  radius={[4, 4, 0, 0]}
                  yAxisId="volume"
                >
                  <LabelList
                    angle={-90}
                    dataKey="resolved_closed_count"
                    fontSize={10}
                    offset={14}
                    position="top"
                  />
                </Bar>
                <Bar
                  dataKey="canceled_closed_incomplete_count"
                  fill={chartColors.canceled}
                  name={canceledLabel}
                  radius={[4, 4, 0, 0]}
                  yAxisId="volume"
                >
                  <LabelList
                    angle={-90}
                    dataKey="canceled_closed_incomplete_count"
                    fontSize={10}
                    offset={14}
                    position="top"
                  />
                </Bar>
              </ComposedChart>
            </div>
          </div>
        </div>
      ) : null}

      {copyMessage ? <p className="chart-copy-status">{copyMessage}</p> : null}
    </section>
  );
}

function BacklogChart({
  data,
  error,
  status,
  timeGrain,
}: {
  data: DashboardVolumetricsBacklogOnly;
  error: string | null;
  status: LoadStatus;
  timeGrain: VolumetricsTimeGrain;
}) {
  const title = "Backlog(Open)";
  const { chartRef, copyMessage, handleCopy, plotWidth } = useChartFrame(title);
  const hasRows = data.points.length > 0;
  const chartWidth = trendChartWidth(data.points.length, timeGrain, plotWidth);
  const canCopy = status !== "loading" && hasRows;

  return (
    <section className="chart-card volumetrics-chart-card" aria-label={title}>
      <div className="applications-chart-header">
        <div>
          <h3>{title}</h3>
          <p className="muted-text">Open ticket backlog at each period end.</p>
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
                data={data.points}
                width={chartWidth}
                height={340}
                margin={{ top: 42, right: 44, bottom: 82, left: 34 }}
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
                <YAxis hide />
                <Tooltip />
                <Legend />
                <Line
                  dataKey="backlog_open"
                  dot={{ r: 3 }}
                  name="Backlog(Open)"
                  stroke={chartColors.backlog}
                  strokeWidth={2.5}
                  type="monotone"
                >
                  <LabelList dataKey="backlog_open" position="top" fontSize={11} />
                </Line>
                {data.average_backlog !== null ? (
                  <ReferenceLine
                    y={data.average_backlog}
                    stroke={chartColors.average}
                    strokeDasharray="6 4"
                  />
                ) : null}
                {data.average_backlog !== null ? (
                  <Customized
                    component={() => (
                      <text
                        x={chartWidth - 48}
                        y={22}
                        fill={chartColors.average}
                        fontSize={13}
                        fontWeight={900}
                        textAnchor="end"
                      >
                        {`Avg backlog: ${formatNumber(data.average_backlog, 0)}`}
                      </text>
                    )}
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

const createdPatternOptions: Array<{ value: CreatedPatternType; label: string }> = [
  { value: "day_of_month", label: "Created by day of month" },
  { value: "day_of_week", label: "Created by day of week" },
  { value: "hour_weekdays", label: "Created by hour - weekdays" },
  { value: "hour_weekends", label: "Created by hour - weekends" },
];

function CreatedPatternChart({
  data,
  error,
  onPatternTypeChange,
  patternType,
  status,
}: {
  data: DashboardVolumetricsCreatedPattern;
  error: string | null;
  onPatternTypeChange: (value: CreatedPatternType) => void;
  patternType: CreatedPatternType;
  status: LoadStatus;
}) {
  const selectedOption =
    createdPatternOptions.find((option) => option.value === patternType) ??
    createdPatternOptions[0];
  const title = selectedOption.label;
  const { chartRef, copyMessage, handleCopy, plotWidth } = useChartFrame(title);
  const hasRows = data.points.length > 0;
  const availablePatternWidth = Math.max(760, plotWidth - 24);
  const chartWidth =
    patternType === "day_of_month"
      ? availablePatternWidth
      : Math.max(availablePatternWidth, data.points.length * 42);
  const canCopy = status !== "loading" && hasRows;
  const barColor =
    patternType === "hour_weekdays" || patternType === "hour_weekends"
      ? chartColors.patternAlt
      : chartColors.pattern;

  return (
    <section className="chart-card volumetrics-chart-card" aria-label={title}>
      <div className="applications-chart-header">
        <div>
          <h3>Created Pattern</h3>
          <p className="muted-text">Average created/opened tickets across the selected range.</p>
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

      <div className="segmented-control volumetrics-pattern-control" aria-label="Created pattern">
        {createdPatternOptions.map((option) => (
          <button
            className={patternType === option.value ? "active" : ""}
            key={option.value}
            type="button"
            onClick={() => onPatternTypeChange(option.value)}
          >
            {option.label}
          </button>
        ))}
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
              <BarChart
                data={data.points}
                width={chartWidth}
                height={330}
                margin={{ top: 34, right: 42, bottom: 72, left: 36 }}
              >
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis
                  dataKey="label"
                  angle={patternType === "day_of_week" ? 0 : -25}
                  height={72}
                  interval={0}
                  textAnchor={patternType === "day_of_week" ? "middle" : "end"}
                  tickMargin={12}
                />
                <YAxis hide />
                <Tooltip />
                <Bar
                  dataKey="average_created"
                  fill={barColor}
                  name="Average Created"
                  radius={[4, 4, 0, 0]}
                >
                  <LabelList
                    dataKey="average_created"
                    position="top"
                    fontSize={11}
                    formatter={(value) => formatRoundedNumber(Number(value ?? 0))}
                  />
                </Bar>
              </BarChart>
            </div>
          </div>
        </div>
      ) : null}

      {copyMessage ? <p className="chart-copy-status">{copyMessage}</p> : null}
    </section>
  );
}

const hourlyDayTypeOptions: Array<{ value: VolumetricsDayType; label: string }> = [
  { value: "weekdays", label: "Weekdays" },
  { value: "weekends", label: "Weekends" },
];

function HourlyCreatedResolvedChart({
  data,
  dayType,
  error,
  onDayTypeChange,
  status,
  ticketType,
}: {
  data: DashboardVolumetricsHourlyCreatedResolved;
  dayType: VolumetricsDayType;
  error: string | null;
  onDayTypeChange: (value: VolumetricsDayType) => void;
  status: LoadStatus;
  ticketType: VolumetricsTicketType;
}) {
  const title = "Created vs Resolved by hour of the day";
  const resolvedLabel = resolvedClosedMetricLabel(ticketType);
  const { chartRef, copyMessage, handleCopy, plotWidth } = useChartFrame(title);
  const hasRows = data.points.length > 0;
  const chartWidth = Math.max(820, plotWidth - 24);
  const canCopy = status !== "loading" && hasRows;

  return (
    <section className="chart-card volumetrics-chart-card" aria-label={title}>
      <div className="applications-chart-header">
        <div>
          <h3>{title}</h3>
          <p className="muted-text">
            Average created/opened and {resolvedLabel.toLowerCase()} tickets by hour.
          </p>
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

      <div className="segmented-control volumetrics-pattern-control" aria-label="Day type">
        {hourlyDayTypeOptions.map((option) => (
          <button
            className={dayType === option.value ? "active" : ""}
            key={option.value}
            type="button"
            onClick={() => onDayTypeChange(option.value)}
          >
            {option.label}
          </button>
        ))}
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
              <BarChart
                data={data.points}
                width={chartWidth}
                height={340}
                margin={{ top: 34, right: 42, bottom: 64, left: 34 }}
              >
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="hour" height={56} interval={0} tickMargin={12} />
                <YAxis hide />
                <Tooltip formatter={(value) => formatNumber(Number(value), 1)} />
                <Legend />
                <Bar
                  dataKey="average_created"
                  fill={chartColors.created}
                  name="Created"
                  radius={[4, 4, 0, 0]}
                >
                  <LabelList
                    dataKey="created_label"
                    position="top"
                    fontSize={10}
                    formatter={(value) => formatNumber(Number(value))}
                  />
                </Bar>
                <Bar
                  dataKey="average_resolved_closed"
                  fill={chartColors.resolved}
                  name={resolvedLabel}
                  radius={[4, 4, 0, 0]}
                >
                  <LabelList
                    dataKey="resolved_closed_label"
                    position="top"
                    fontSize={10}
                    formatter={(value) => formatNumber(Number(value))}
                  />
                </Bar>
              </BarChart>
            </div>
          </div>
        </div>
      ) : null}

      {copyMessage ? <p className="chart-copy-status">{copyMessage}</p> : null}
    </section>
  );
}

function priorityDataForChart(data: DashboardVolumetricsPriorityDistribution) {
  const series = data.priorities.map((priority, index) => ({
    key: `priority_${index}`,
    label: priority,
    color: chartColors.priority[index % chartColors.priority.length],
  }));
  const points = data.points.map((point) => {
    const row: Record<string, string | number> = {
      period_label: point.period_label,
      total: point.total,
    };
    series.forEach((item) => {
      row[item.key] = point.values[item.label] ?? 0;
    });
    return row;
  });
  return { points, series };
}

function PriorityDistributionChart({
  data,
  error,
  onViewChange,
  status,
  timeGrain,
  view,
}: {
  data: DashboardVolumetricsPriorityDistribution;
  error: string | null;
  onViewChange: (value: PriorityDistributionView) => void;
  status: LoadStatus;
  timeGrain: VolumetricsTimeGrain;
  view: PriorityDistributionView;
}) {
  const title = "Priority-wise ticket distribution";
  const { chartRef, copyMessage, handleCopy, plotWidth } = useChartFrame(title);
  const hasRows = data.points.length > 0;
  const chartWidth = trendChartWidth(data.points.length, timeGrain, plotWidth);
  const canCopy = status !== "loading" && hasRows && view === "graph";
  const { points, series } = priorityDataForChart(data);

  return (
    <section className="chart-card volumetrics-chart-card" aria-label={title}>
      <div className="applications-chart-header">
        <div>
          <h3>{title}</h3>
          <p className="muted-text">Ticket priority mix by selected duration.</p>
        </div>
        <div className="volumetrics-chart-actions">
          <div className="segmented-control volumetrics-compact-toggle" aria-label="Priority view">
            <button
              className={view === "graph" ? "active" : ""}
              type="button"
              onClick={() => onViewChange("graph")}
            >
              Graph
            </button>
            <button
              className={view === "table" ? "active" : ""}
              type="button"
              onClick={() => onViewChange("table")}
            >
              Data table
            </button>
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
      </div>

      {status === "loading" ? <p className="muted-text chart-state-text">Loading chart...</p> : null}
      {status === "error" ? <p className="error-text">{error}</p> : null}
      {status !== "loading" && status !== "error" && !hasRows ? (
        <p className="muted-text chart-state-text">No priority data available.</p>
      ) : null}

      {status !== "loading" && status !== "error" && hasRows && view === "graph" ? (
        <div className="applications-chart-plot volumetrics-chart-plot" ref={chartRef}>
          <div className="applications-chart-scroll">
            <div className="applications-chart-stage">
              <BarChart
                data={points}
                width={chartWidth}
                height={360}
                margin={{ top: 36, right: 42, bottom: 82, left: 34 }}
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
                <YAxis hide />
                <Tooltip />
                <Legend />
                {series.map((item) => (
                  <Bar
                    dataKey={item.key}
                    fill={item.color}
                    key={item.key}
                    name={item.label}
                    stackId="priority"
                  />
                ))}
              </BarChart>
            </div>
          </div>
        </div>
      ) : null}

      {status !== "loading" && status !== "error" && hasRows && view === "table" ? (
        <PriorityDistributionTable data={data} />
      ) : null}

      {copyMessage ? <p className="chart-copy-status">{copyMessage}</p> : null}
    </section>
  );
}

function PriorityDistributionTable({ data }: { data: DashboardVolumetricsPriorityDistribution }) {
  return (
    <div className="applications-table-frame volumetrics-data-table-frame">
      <table className="applications-table volumetrics-data-table">
        <thead>
          <tr>
            <th>Period</th>
            {data.priorities.map((priority) => (
              <th key={priority}>{priority}</th>
            ))}
            <th>Total</th>
          </tr>
        </thead>
        <tbody>
          {data.points.map((point) => (
            <tr key={point.period_key}>
              <td>{point.period_label}</td>
              {data.priorities.map((priority) => (
                <td key={priority}>{formatNumber(point.values[priority] ?? 0)}</td>
              ))}
              <td>{formatNumber(point.total)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function OverallSlaTrends({
  data,
  error,
  status,
  ticketType,
  timeGrain,
}: {
  data: DashboardVolumetricsSlaTrends;
  error: string | null;
  status: LoadStatus;
  ticketType: VolumetricsTicketType;
  timeGrain: VolumetricsTimeGrain;
}) {
  if (ticketType === "sc_task" || data.not_applicable) {
    return (
      <section className="panel volumetrics-placeholder-panel">
        <p className="label">Overall SLA Trends</p>
        <h3>SLA trends are not applicable for SC Tasks.</h3>
      </section>
    );
  }

  return (
    <>
      {status === "error" ? <p className="error-text">{error}</p> : null}
      <SlaTrendSection
        title="Response SLA adherence trend"
        tableMetricLabel="Response SLA"
        data={data.response}
        status={status}
        timeGrain={timeGrain}
        color={chartColors.created}
      />
      <SlaTrendSection
        title="Resolution SLA adherence trend"
        tableMetricLabel="Resolution SLA"
        data={data.resolution}
        status={status}
        timeGrain={timeGrain}
        color={chartColors.resolved}
      />
    </>
  );
}

function SlaTrendSection({
  color,
  data,
  status,
  tableMetricLabel,
  timeGrain,
  title,
}: {
  color: string;
  data: DashboardVolumetricsSlaTrends["response"];
  status: LoadStatus;
  tableMetricLabel: string;
  timeGrain: VolumetricsTimeGrain;
  title: string;
}) {
  const { chartRef, copyMessage, handleCopy, plotWidth } = useChartFrame(title);
  const hasRows = data.length > 0;
  const chartWidth = trendChartWidth(data.length, timeGrain, plotWidth);
  const canCopy = status !== "loading" && hasRows;

  return (
    <section className="chart-card volumetrics-chart-card" aria-label={title}>
      <div className="applications-chart-header">
        <div>
          <h3>{title}</h3>
          <p className="muted-text">
            Adherence is calculated as SLA adhered count divided by SLA captured count.
          </p>
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
      {status !== "loading" && !hasRows ? (
        <p className="muted-text chart-state-text">No SLA trend data available.</p>
      ) : null}

      {status !== "loading" && hasRows ? (
        <>
          <div className="applications-chart-plot volumetrics-chart-plot" ref={chartRef}>
            <div className="applications-chart-scroll">
              <div className="applications-chart-stage">
                <ComposedChart
                  data={data}
                  width={chartWidth}
                  height={330}
                  margin={{ top: 34, right: 42, bottom: 82, left: 46 }}
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
                  <YAxis domain={[0, 100]} tickFormatter={(value) => `${value}%`} />
                  <Tooltip formatter={(value) => `${Number(value).toFixed(1)}%`} />
                  <Line
                    connectNulls
                    dataKey="sla_adherence_pct"
                    dot={{ r: 3 }}
                    name={`${tableMetricLabel} adherence %`}
                    stroke={color}
                    strokeWidth={2.5}
                    type="monotone"
                  >
                    <LabelList
                      dataKey="sla_adherence_pct"
                      position="top"
                      fontSize={11}
                      formatter={(value) => formatPercent(Number(value))}
                    />
                  </Line>
                </ComposedChart>
              </div>
            </div>
          </div>
          <SlaTrendTable data={data} metricLabel={tableMetricLabel} />
        </>
      ) : null}

      {copyMessage ? <p className="chart-copy-status">{copyMessage}</p> : null}
    </section>
  );
}

function SlaTrendTable({
  data,
  metricLabel,
}: {
  data: DashboardVolumetricsSlaTrends["response"];
  metricLabel: string;
}) {
  return (
    <div className="applications-table-frame volumetrics-data-table-frame">
      <table className="applications-table volumetrics-data-table">
        <thead>
          <tr>
            <th>Duration</th>
            <th>Total closed tickets</th>
            <th>{metricLabel} captured</th>
            <th>{metricLabel} adhered</th>
            <th>{metricLabel} adherence %</th>
          </tr>
        </thead>
        <tbody>
          {data.map((row) => (
            <tr key={row.period_key}>
              <td>{row.period_label}</td>
              <td>{formatNumber(row.total_closed_ticket_count)}</td>
              <td>{formatNumber(row.sla_captured_count)}</td>
              <td>{formatNumber(row.sla_adhered_count)}</td>
              <td>{formatPercent(row.sla_adherence_pct)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default VolumetricsDashboard;
