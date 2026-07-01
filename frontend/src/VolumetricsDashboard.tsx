import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  Customized,
  LabelList,
  Legend,
  Line,
  Pie,
  PieChart,
  ReferenceLine,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import {
  getDashboardFilterCatalog,
  getDashboardFilterCounts,
  getDashboardVolumetricsBacklog,
  getDashboardVolumetricsCreatedPattern,
  getDashboardVolumetricsCreatedResolvedCanceled,
  getDashboardVolumetricsDataRange,
  getDashboardVolumetricsDetailedArchitectureInstallSplits,
  getDashboardVolumetricsDistributionSplits,
  getDashboardVolumetricsHourlyCreatedResolved,
  getDashboardVolumetricsIncidentBatchTrend,
  getDashboardVolumetricsKpiDurationBuckets,
  getDashboardVolumetricsKpiMttrTrends,
  getDashboardVolumetricsKpiProblemManagementTrend,
  getDashboardVolumetricsKpiReassignmentHopsTrend,
  getDashboardVolumetricsPriorityDistribution,
  getDashboardVolumetricsScTaskCatalogItemProportion,
  getDashboardVolumetricsSlaTrends,
  getDashboardVolumetricsSummary,
  getDashboardVolumetricsTicketsPerUser,
  getDashboardVolumetricsTopApplications,
  getDashboardVolumetricsTopIncidentBatchApplications,
} from "./api/dashboard";
import type {
  CreatedPatternType,
  DashboardVolumetricsBacklogOnly,
  DashboardVolumetricsCreatedPattern,
  DashboardVolumetricsCreatedResolvedCanceled,
  DashboardVolumetricsDataRange,
  DashboardVolumetricsDetailedArchitectureInstallSplits,
  DashboardVolumetricsDistributionSplits,
  DashboardVolumetricsDurationBucketRow,
  DashboardVolumetricsFilterValues,
  DashboardVolumetricsFilters,
  DashboardFilterCatalogResponse,
  DashboardFilterCountsResponse,
  DashboardVolumetricsHourlyCreatedResolved,
  DashboardVolumetricsIncidentBatchTrend,
  DashboardVolumetricsKpiDurationBuckets,
  DashboardVolumetricsKpiMttrPoint,
  DashboardVolumetricsKpiMttrPrioritySet,
  DashboardVolumetricsKpiMttrTrends,
  DashboardVolumetricsProblemManagementPoint,
  DashboardVolumetricsProblemManagementTrend,
  DashboardVolumetricsPriorityDistribution,
  DashboardVolumetricsPriorityDistributionPoint,
  DashboardVolumetricsRankingWindow,
  DashboardVolumetricsReassignmentHopsPoint,
  DashboardVolumetricsReassignmentHopsTrend,
  DashboardVolumetricsRequest,
  DashboardVolumetricsScTaskCatalogItemPeriod,
  DashboardVolumetricsScTaskCatalogItemProportion,
  DashboardVolumetricsScTaskCatalogItemRow,
  DashboardVolumetricsSlaTrends,
  DashboardVolumetricsSplitDatum,
  DashboardVolumetricsSummary,
  DashboardVolumetricsTicketsPerUser,
  DashboardVolumetricsTopApplications,
  DashboardVolumetricsTopIncidentBatchApplications,
  VolumetricsAgreementMode,
  VolumetricsDayType,
  VolumetricsScope,
  VolumetricsTicketType,
  VolumetricsTimeGrain,
} from "./api/dashboard";
import CommentaryEditor from "./components/CommentaryEditor";
import ExcelMultiSelectFilter from "./components/ExcelMultiSelectFilter";
import type { ExcelFilterOption } from "./components/ExcelMultiSelectFilter";

type LoadStatus = "idle" | "loading" | "success" | "error";

type LoadState<T> = {
  status: LoadStatus;
  data: T;
  error: string | null;
};

type VolumetricsDashboardProps = {
  customerId: string;
  projectId: string;
  isActive: boolean;
  onExportContextChange?: (context: {
    functionalTrackAmsOwners: string[];
    scope: VolumetricsScope;
    ticketType: VolumetricsTicketType;
  }) => void;
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

const subTabCommentaryKeys: Record<VolumetricsSubTab, string> = {
  overall_volume: "overall_volume_trends",
  overall_sla: "overall_sla_trends",
  detailed_volume: "detailed_volume_trends",
  kpi: "kpi_trends",
  category: "category_wise_trends",
};

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
  architecture_type: [],
  business_critical: [],
  install_type: [],
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
  architecture_type: [],
  business_critical: [],
  install_type: [],
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
  agreement_mode: "sla",
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
  overall_average_monthly_volume: 0,
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

const emptyDetailedSplits: DashboardVolumetricsDetailedArchitectureInstallSplits = {
  rolling_window: {
    start_month: "",
    end_month: "",
    description: "Latest complete 6 months",
  },
  architecture_type: { incidents: [], sc_tasks: [] },
  install_type: { incidents: [], sc_tasks: [] },
};

const emptyTicketsPerUser: DashboardVolumetricsTicketsPerUser = {
  ranking_window: {
    start_month: "",
    end_month: "",
    description: "Latest complete 6 months",
  },
  top_n: 10,
  points: [],
};

const emptyDistributionGroup = { all: [], incidents: [], sc_tasks: [] };

const emptyDistributionSplits: DashboardVolumetricsDistributionSplits = {
  ranking_window: {
    start_month: "",
    end_month: "",
    description: "Latest complete 6 months",
  },
  sap_non_sap: emptyDistributionGroup,
  architecture_type: emptyDistributionGroup,
  install_type: emptyDistributionGroup,
  hosting_env: emptyDistributionGroup,
};

const emptyScTaskCatalogItemProportion: DashboardVolumetricsScTaskCatalogItemProportion = {
  periods: [],
  data_notes: [],
  warnings: [],
};

const emptyMttrPrioritySet: DashboardVolumetricsKpiMttrPrioritySet = {
  P1: [],
  P2: [],
  P3: [],
  P4: [],
};

const emptyKpiMttrTrends: DashboardVolumetricsKpiMttrTrends = {
  time_grain: "monthly",
  incident: emptyMttrPrioritySet,
  sc_task: emptyMttrPrioritySet,
};

const emptyDurationBuckets: DashboardVolumetricsKpiDurationBuckets = {
  months: [],
  incident: [],
  sc_task: [],
};

const emptyReassignmentHopsTrend: DashboardVolumetricsReassignmentHopsTrend = {
  time_grain: "monthly",
  date_range: {
    from_date: "",
    to_date: "",
    complete_month_cutoff_applied: true,
  },
  points: [],
  data_notes: [],
  warnings: [],
};

const emptyProblemManagementTrend: DashboardVolumetricsProblemManagementTrend = {
  time_grain: "monthly",
  scope: "in_scope",
  date_range: {
    from_date: "",
    to_date: "",
    complete_month_cutoff_applied: true,
  },
  points: [],
  axis: {
    use_secondary_axis_for_linked_incidents: false,
    reason: "",
  },
  data_notes: [],
  warnings: [],
};

const chartColors = {
  created: "#0f766e",
  resolved: "#2563eb",
  canceled: "#dc2626",
  backlog: "#d97706",
  average: "#7c3aed",
  reassignment: "#0f766e",
  reassignmentPct: "#7c3aed",
  problemCreated: "#0f766e",
  problemClosed: "#2563eb",
  linkedIncidents: "#d97706",
  pattern: "#0891b2",
  patternAlt: "#7c3aed",
  priority: ["#0f766e", "#2563eb", "#d97706", "#7c3aed", "#dc2626", "#64748b"],
  pie: [
    "#2563eb",
    "#16a34a",
    "#d97706",
    "#7c3aed",
    "#dc2626",
    "#64748b",
    "#0891b2",
    "#be123c",
    "#4f46e5",
    "#15803d",
    "#92400e",
  ],
};

const chartImagePadding = 18;
const chartImageHeaderMinHeight = 54;

function createLoadState<T>(data: T, status: LoadStatus = "idle"): LoadState<T> {
  return { status, data, error: null };
}

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

function commentaryFunctionalContext(values: string[]): string {
  return values.length === 1 ? values[0] : "all";
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

function splitCombinedFilterValue(label: string): { left_value: string; right_value: string } {
  const separator = " - ";
  const separatorIndex = label.indexOf(separator);
  if (separatorIndex < 0) {
    return { left_value: label, right_value: "(blank)" };
  }
  return {
    left_value: label.slice(0, separatorIndex) || "(blank)",
    right_value: label.slice(separatorIndex + separator.length) || "(blank)",
  };
}

function catalogSingleRows(
  catalog: DashboardFilterCatalogResponse | null,
  counts: DashboardFilterCountsResponse | null,
  filterKey: keyof DashboardVolumetricsFilterValues,
  selectedValues: string[]
) {
  const dynamicCounts = counts?.counts[filterKey] ?? {};
  const rows = (catalog?.filters[filterKey] ?? []).map((item) => ({
    label: item.label,
    value: item.value,
    count: dynamicCounts[item.value] ?? item.baseline_count,
  }));
  const existing = new Set(rows.map((row) => row.value));
  for (const selectedValue of selectedValues) {
    if (!existing.has(selectedValue)) {
      rows.push({
        label: selectedValue,
        value: selectedValue,
        count: dynamicCounts[selectedValue] ?? 0,
      });
      existing.add(selectedValue);
    }
  }
  return rows;
}

function catalogCombinedRows(
  catalog: DashboardFilterCatalogResponse | null,
  counts: DashboardFilterCountsResponse | null,
  filterKey: keyof DashboardVolumetricsFilterValues,
  selectedValues: string[]
) {
  const dynamicCounts = counts?.counts[filterKey] ?? {};
  const rows = (catalog?.filters[filterKey] ?? []).map((item) => {
    const splitValue = splitCombinedFilterValue(item.value);
    return {
      label: item.label,
      left_value: splitValue.left_value,
      right_value: splitValue.right_value,
      count: dynamicCounts[item.value] ?? item.baseline_count,
    };
  });
  const existing = new Set(rows.map((row) => row.label));
  for (const selectedValue of selectedValues) {
    if (!existing.has(selectedValue)) {
      const splitValue = splitCombinedFilterValue(selectedValue);
      rows.push({
        label: selectedValue,
        left_value: splitValue.left_value,
        right_value: splitValue.right_value,
        count: dynamicCounts[selectedValue] ?? 0,
      });
      existing.add(selectedValue);
    }
  }
  return rows;
}

function volumetricsFilterValuesFromCatalog(
  catalog: DashboardFilterCatalogResponse | null,
  counts: DashboardFilterCountsResponse | null,
  filters: DashboardVolumetricsFilters,
  scope: VolumetricsScope,
  ticketType: VolumetricsTicketType
): DashboardVolumetricsFilterValues {
  return {
    scope: catalogSingleRows(catalog, counts, "scope", [scope]),
    ticket_type: catalogSingleRows(catalog, counts, "ticket_type", [ticketType]),
    functional_track_ams_owner: catalogCombinedRows(
      catalog,
      counts,
      "functional_track_ams_owner",
      filters.functional_track_ams_owner
    ),
    assignment_group_support_lead: catalogCombinedRows(
      catalog,
      counts,
      "assignment_group_support_lead",
      filters.assignment_group_support_lead
    ),
    parent_application_name: catalogSingleRows(
      catalog,
      counts,
      "parent_application_name",
      filters.parent_application_name
    ),
    application_owner: catalogSingleRows(
      catalog,
      counts,
      "application_owner",
      filters.application_owner
    ),
    supported_by_vendor: catalogSingleRows(
      catalog,
      counts,
      "supported_by_vendor",
      filters.supported_by_vendor
    ),
    sap_non_sap: catalogSingleRows(catalog, counts, "sap_non_sap", filters.sap_non_sap),
    architecture_type: catalogSingleRows(
      catalog,
      counts,
      "architecture_type",
      filters.architecture_type
    ),
    business_critical: catalogSingleRows(
      catalog,
      counts,
      "business_critical",
      filters.business_critical
    ),
    install_type: catalogSingleRows(catalog, counts, "install_type", filters.install_type),
  };
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

const svgComputedStyleProperties = [
  "display",
  "visibility",
  "fill",
  "fill-opacity",
  "stroke",
  "stroke-width",
  "stroke-opacity",
  "stroke-dasharray",
  "stroke-linecap",
  "stroke-linejoin",
  "opacity",
  "font-family",
  "font-size",
  "font-weight",
  "text-anchor",
  "dominant-baseline",
  "paint-order",
];

function inlineSvgComputedStyles(source: Element, clone: Element) {
  const sourceElements = [source, ...Array.from(source.querySelectorAll("*"))];
  const cloneElements = [clone, ...Array.from(clone.querySelectorAll("*"))];
  sourceElements.forEach((sourceElement, index) => {
    const cloneElement = cloneElements[index];
    if (!(cloneElement instanceof SVGElement)) {
      return;
    }
    const computed = window.getComputedStyle(sourceElement);
    svgComputedStyleProperties.forEach((property) => {
      const value = computed.getPropertyValue(property);
      if (value) {
        cloneElement.style.setProperty(property, value);
      }
    });
  });
}

function chartSvgSize(sourceSvg: SVGSVGElement) {
  const rect = sourceSvg.getBoundingClientRect();
  const viewBox = sourceSvg.viewBox.baseVal;
  const attrWidth = Number(sourceSvg.getAttribute("width"));
  const attrHeight = Number(sourceSvg.getAttribute("height"));
  const chartWidth = Math.max(600, Math.ceil(rect.width || viewBox.width || attrWidth || 900));
  const chartHeight = Math.max(300, Math.ceil(rect.height || viewBox.height || attrHeight || 420));
  const viewBoxText =
    sourceSvg.getAttribute("viewBox") ||
    `0 0 ${Math.max(1, viewBox.width || attrWidth || chartWidth)} ${Math.max(
      1,
      viewBox.height || attrHeight || chartHeight
    )}`;
  return { chartWidth, chartHeight, viewBoxText };
}

function chartLegendItems(chartElement: HTMLElement): Array<{ color: string; name: string }> {
  const items = Array.from(chartElement.querySelectorAll(".recharts-legend-item"));
  return items
    .map((item) => {
      const text = item.textContent?.trim() ?? "";
      const icon = item.querySelector("path, rect, circle, line") as SVGElement | null;
      const color = icon
        ? icon.getAttribute("fill") ||
          icon.getAttribute("stroke") ||
          window.getComputedStyle(icon).fill ||
          window.getComputedStyle(icon).stroke
        : "#64748b";
      return { color: color || "#64748b", name: text };
    })
    .filter((item) => item.name);
}

function wrapExportText(value: string, maxLength = 128): string[] {
  const words = value.trim().split(/\s+/).filter(Boolean);
  const lines: string[] = [];
  let current = "";
  words.forEach((word) => {
    const next = current ? `${current} ${word}` : word;
    if (next.length > maxLength && current) {
      lines.push(current);
      current = word;
      return;
    }
    current = next;
  });
  if (current) {
    lines.push(current);
  }
  return lines.length ? lines : [value.trim()];
}

function chartExportText(chartElement: HTMLElement, fallbackTitle: string) {
  const card = chartElement.closest(".chart-card") as HTMLElement | null;
  const titleText = card?.querySelector("h3")?.textContent?.trim() || fallbackTitle;
  const subtitles = card
    ? Array.from(card.querySelectorAll(".muted-text"))
        .filter((element) => {
          const htmlElement = element as HTMLElement;
          const text = htmlElement.textContent?.trim();
          return (
            Boolean(text) &&
            !htmlElement.classList.contains("chart-state-text") &&
            !htmlElement.classList.contains("chart-copy-status") &&
            !htmlElement.closest(".commentary-box") &&
            !chartElement.contains(htmlElement)
          );
        })
        .flatMap((element) => wrapExportText(element.textContent?.trim() ?? ""))
        .slice(0, 3)
    : [];
  return { title: titleText, subtitles };
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

function safeChartFilename(title: string) {
  return `${title.replace(/[^A-Za-z0-9]+/g, "_").replace(/^_+|_+$/g, "") || "chart"}.png`;
}

async function copyChartToClipboard(chartElement: HTMLElement, title: string): Promise<string> {
  const exportText = chartExportText(chartElement, title);
  const sourceSvg = chartElement.querySelector("svg");
  if (!sourceSvg) {
    throw new Error("No chart image is available to copy.");
  }

  const { chartWidth, chartHeight, viewBoxText } = chartSvgSize(sourceSvg);
  const headerHeight = Math.max(
    chartImageHeaderMinHeight,
    42 + exportText.subtitles.length * 17
  );
  const outputWidth = chartWidth + chartImagePadding * 2;
  const outputHeight = chartHeight + headerHeight + chartImagePadding;
  const clonedSvg = sourceSvg.cloneNode(true) as SVGSVGElement;
  inlineSvgComputedStyles(sourceSvg, clonedSvg);
  clonedSvg.setAttribute("xmlns", "http://www.w3.org/2000/svg");
  clonedSvg.setAttribute("x", String(chartImagePadding));
  clonedSvg.setAttribute("y", String(headerHeight));
  clonedSvg.setAttribute("width", String(chartWidth));
  clonedSvg.setAttribute("height", String(chartHeight));
  clonedSvg.setAttribute("viewBox", viewBoxText);

  const svgMarkup = `
    <svg xmlns="http://www.w3.org/2000/svg" width="${outputWidth}" height="${outputHeight}" viewBox="0 0 ${outputWidth} ${outputHeight}">
      <rect x="0" y="0" width="${outputWidth}" height="${outputHeight}" rx="8" fill="#ffffff" stroke="#cbd5e1"/>
      <text x="${chartImagePadding}" y="27" fill="#111827" font-family="Inter, Arial, sans-serif" font-size="17" font-weight="700">${escapeXml(
        exportText.title
      )}</text>
      ${exportText.subtitles
        .map(
          (line, index) =>
            `<text x="${chartImagePadding}" y="${47 + index * 17}" fill="#475569" font-family="Inter, Arial, sans-serif" font-size="13" font-weight="500">${escapeXml(
              line
            )}</text>`
        )
        .join("")}
      ${new XMLSerializer().serializeToString(clonedSvg)}
    </svg>
  `;

  const image = await svgToImage(svgMarkup);
  const legendItems = chartLegendItems(chartElement);
  const legendHeight = legendItems.length ? 28 + Math.ceil(legendItems.length / 3) * 22 : 0;
  const canvas = document.createElement("canvas");
  const scale = Math.max(1, Math.min(window.devicePixelRatio || 1, 2));
  canvas.width = Math.ceil(outputWidth * scale);
  canvas.height = Math.ceil((outputHeight + legendHeight) * scale);
  const context = canvas.getContext("2d");
  if (!context) {
    throw new Error("Chart image could not be rendered.");
  }
  context.scale(scale, scale);
  context.fillStyle = "#ffffff";
  context.fillRect(0, 0, outputWidth, outputHeight + legendHeight);
  context.drawImage(image, 0, 0, outputWidth, outputHeight);
  if (legendItems.length) {
    context.font = "700 13px Inter, Arial, sans-serif";
    context.textBaseline = "middle";
    legendItems.forEach((item, index) => {
      const column = index % 3;
      const row = Math.floor(index / 3);
      const x = chartImagePadding + column * Math.max(180, (outputWidth - chartImagePadding * 2) / 3);
      const y = outputHeight + 18 + row * 22;
      context.fillStyle = item.color;
      context.fillRect(x, y - 5, 10, 10);
      context.fillStyle = "#334155";
      context.fillText(item.name, x + 16, y);
    });
  }

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
    if (!navigator.clipboard || typeof ClipboardItem === "undefined") {
      throw new Error("Image clipboard copy is not supported in this browser.");
    }
    await navigator.clipboard.write([new ClipboardItem({ "image/png": pngBlob })]);
    return "Copied chart image to clipboard.";
  } catch (error) {
    downloadBlob(pngBlob, safeChartFilename(exportText.title));
    const message = errorMessage(error, "This browser could not copy the chart image.");
    return `Copy blocked by browser. PNG downloaded instead. ${message}`;
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
      setCopyMessage(await copyChartToClipboard(chartElement, title));
    } catch (error) {
      setCopyMessage(errorMessage(error, "This browser could not copy the chart image."));
    }
  }, [chartElement, title]);

  return { chartRef, copyMessage, handleCopy, plotWidth };
}

function VolumetricsDashboard({
  customerId,
  projectId,
  isActive,
  onExportContextChange,
}: VolumetricsDashboardProps) {
  const [scope, setScope] = useState<VolumetricsScope>("in_scope");
  const [ticketType, setTicketType] = useState<VolumetricsTicketType>("all");
  const [timeGrain, setTimeGrain] = useState<VolumetricsTimeGrain>("monthly");
  const [agreementMode, setAgreementMode] = useState<VolumetricsAgreementMode>("sla");
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
  const [ticketsPerUserN, setTicketsPerUserN] = useState<TopNSelection>(10);
  const [filters, setFilters] = useState<DashboardVolumetricsFilters>(emptyFilters);
  const [filterValues, setFilterValues] = useState<LoadState<DashboardVolumetricsFilterValues>>(
    createLoadState(emptyFilterValues)
  );
  const [filterCatalog, setFilterCatalog] = useState<DashboardFilterCatalogResponse | null>(null);
  const [filterCounts, setFilterCounts] = useState<DashboardFilterCountsResponse | null>(null);
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
  const [detailedSplits, setDetailedSplits] = useState<
    LoadState<DashboardVolumetricsDetailedArchitectureInstallSplits>
  >(createLoadState(emptyDetailedSplits));
  const [ticketsPerUser, setTicketsPerUser] = useState<
    LoadState<DashboardVolumetricsTicketsPerUser>
  >(createLoadState(emptyTicketsPerUser));
  const [distributionSplits, setDistributionSplits] = useState<
    LoadState<DashboardVolumetricsDistributionSplits>
  >(createLoadState(emptyDistributionSplits));
  const [scTaskCatalogItemProportion, setScTaskCatalogItemProportion] = useState<
    LoadState<DashboardVolumetricsScTaskCatalogItemProportion>
  >(createLoadState(emptyScTaskCatalogItemProportion));
  const [kpiMttrTrends, setKpiMttrTrends] = useState<
    LoadState<DashboardVolumetricsKpiMttrTrends>
  >(createLoadState(emptyKpiMttrTrends));
  const [kpiDurationBuckets, setKpiDurationBuckets] = useState<
    LoadState<DashboardVolumetricsKpiDurationBuckets>
  >(createLoadState(emptyDurationBuckets));
  const [reassignmentHopsTrend, setReassignmentHopsTrend] = useState<
    LoadState<DashboardVolumetricsReassignmentHopsTrend>
  >(createLoadState(emptyReassignmentHopsTrend));
  const [problemManagementTrend, setProblemManagementTrend] = useState<
    LoadState<DashboardVolumetricsProblemManagementTrend>
  >(createLoadState(emptyProblemManagementTrend));
  const [loadedProjectId, setLoadedProjectId] = useState("");
  const [rangeInitializedProjectId, setRangeInitializedProjectId] = useState("");
  const filterCountsRequestRef = useRef(0);

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
      business_critical: singleOptions(filterValues.data.business_critical),
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
      agreement_mode: agreementMode,
      start_datetime: effectiveRange.startApi,
      end_datetime: effectiveRange.endApi,
      filters,
    };
  }, [
    agreementMode,
    effectiveRange.endApi,
    effectiveRange.startApi,
    filters,
    projectId,
    scope,
    ticketType,
    timeGrain,
  ]);

  const requestSignature = useMemo(
    () => (requestBody ? JSON.stringify(requestBody) : ""),
    [requestBody]
  );
  const hasActiveProjectContext = Boolean(projectId.trim()) && projectId === loadedProjectId;
  const hasFilterCacheContext = Boolean(customerId.trim()) && Boolean(projectId.trim());
  const isDateRangeReady = dataRange.status === "error" || rangeInitializedProjectId === projectId;

  useEffect(() => {
    onExportContextChange?.({
      functionalTrackAmsOwners: filters.functional_track_ams_owner,
      scope,
      ticketType,
    });
  }, [filters.functional_track_ams_owner, onExportContextChange, scope, ticketType]);

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

  const loadVolumetricsFilterCatalog = useCallback(async () => {
    const cleanedCustomerId = customerId.trim();
    const cleanedProjectId = projectId.trim();
    if (!cleanedCustomerId || !cleanedProjectId) {
      return;
    }
    setFilterValues((currentFilterValues) => ({
      status: "loading",
      data: currentFilterValues.data,
      error: null,
    }));
    try {
      const catalog = await getDashboardFilterCatalog(
        cleanedCustomerId,
        cleanedProjectId,
        "volumetrics"
      );
      setFilterCatalog(catalog);
      setFilterCounts(null);
      setFilterValues({
        status: "success",
        data: volumetricsFilterValuesFromCatalog(catalog, null, filters, scope, ticketType),
        error: catalog.warnings[0] ?? null,
      });
    } catch (error) {
      setFilterValues((currentFilterValues) => ({
        status: "error",
        data: currentFilterValues.data,
        error: errorMessage(error, "Unable to load Volumetrics filters"),
      }));
    }
  }, [customerId, filters, projectId, scope, ticketType]);

  const loadVolumetricsFilterCounts = useCallback(async () => {
    const cleanedCustomerId = customerId.trim();
    const cleanedProjectId = projectId.trim();
    if (!cleanedCustomerId || !cleanedProjectId || !filterCatalog || !requestBody) {
      return;
    }
    const requestId = filterCountsRequestRef.current + 1;
    filterCountsRequestRef.current = requestId;
    setFilterValues((currentFilterValues) => ({
      status: "loading",
      data: currentFilterValues.data,
      error: null,
    }));
    try {
      const counts = await getDashboardFilterCounts({
        customer_id: cleanedCustomerId,
        project_id: cleanedProjectId,
        dashboard_area: "volumetrics",
        selected_filters: filters,
        date_range: {
          from_date: requestBody.start_datetime,
          to_date: requestBody.end_datetime,
        },
        scope,
        ticket_type: ticketType,
      });
      if (filterCountsRequestRef.current !== requestId) {
        return;
      }
      setFilterCounts(counts);
      setFilterValues({
        status: "success",
        data: volumetricsFilterValuesFromCatalog(filterCatalog, counts, filters, scope, ticketType),
        error: null,
      });
    } catch (error) {
      if (filterCountsRequestRef.current !== requestId) {
        return;
      }
      setFilterValues((currentFilterValues) => ({
        status: "error",
        data: currentFilterValues.data,
        error: errorMessage(error, "Unable to update Volumetrics filter counts"),
      }));
    }
  }, [customerId, filterCatalog, filters, projectId, requestBody, scope, ticketType]);

  const loadVolumetricsData = useCallback(async () => {
    if (!requestBody) {
      return;
    }

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
    setDetailedSplits(createLoadState(emptyDetailedSplits, "loading"));
    setTicketsPerUser(createLoadState(emptyTicketsPerUser, "loading"));
    setDistributionSplits(createLoadState(emptyDistributionSplits, "loading"));
    setScTaskCatalogItemProportion(
      createLoadState(emptyScTaskCatalogItemProportion, "loading")
    );
    setKpiMttrTrends(createLoadState(emptyKpiMttrTrends, "loading"));
    setKpiDurationBuckets(createLoadState(emptyDurationBuckets, "loading"));
    setReassignmentHopsTrend(createLoadState(emptyReassignmentHopsTrend, "loading"));
    setProblemManagementTrend(createLoadState(emptyProblemManagementTrend, "loading"));

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

    void getDashboardVolumetricsDetailedArchitectureInstallSplits(requestBody)
      .then((nextDetailedSplits) => {
        setDetailedSplits({ status: "success", data: nextDetailedSplits, error: null });
      })
      .catch((error) => {
        setDetailedSplits({
          status: "error",
          data: emptyDetailedSplits,
          error: errorMessage(error, "Unable to load architecture/install split charts"),
        });
      });

    void getDashboardVolumetricsTicketsPerUser(requestBody, ticketsPerUserN)
      .then((nextTicketsPerUser) => {
        setTicketsPerUser({ status: "success", data: nextTicketsPerUser, error: null });
      })
      .catch((error) => {
        setTicketsPerUser({
          status: "error",
          data: emptyTicketsPerUser,
          error: errorMessage(error, "Unable to load tickets per user"),
        });
      });

    void getDashboardVolumetricsDistributionSplits(requestBody)
      .then((nextDistributionSplits) => {
        setDistributionSplits({ status: "success", data: nextDistributionSplits, error: null });
      })
      .catch((error) => {
        setDistributionSplits({
          status: "error",
          data: emptyDistributionSplits,
          error: errorMessage(error, "Unable to load distribution splits"),
        });
      });

    void getDashboardVolumetricsScTaskCatalogItemProportion(requestBody)
      .then((nextScTaskCatalogItemProportion) => {
        setScTaskCatalogItemProportion({
          status: "success",
          data: nextScTaskCatalogItemProportion,
          error: null,
        });
      })
      .catch((error) => {
        setScTaskCatalogItemProportion({
          status: "error",
          data: emptyScTaskCatalogItemProportion,
          error: errorMessage(error, "Unable to load SC Task catalog item proportions"),
        });
      });

    void getDashboardVolumetricsKpiMttrTrends(requestBody)
      .then((nextKpiMttrTrends) => {
        setKpiMttrTrends({ status: "success", data: nextKpiMttrTrends, error: null });
      })
      .catch((error) => {
        setKpiMttrTrends({
          status: "error",
          data: emptyKpiMttrTrends,
          error: errorMessage(error, "Unable to load KPI MTTR trends"),
        });
      });

    void getDashboardVolumetricsKpiDurationBuckets(requestBody)
      .then((nextKpiDurationBuckets) => {
        setKpiDurationBuckets({
          status: "success",
          data: nextKpiDurationBuckets,
          error: null,
        });
      })
      .catch((error) => {
        setKpiDurationBuckets({
          status: "error",
          data: emptyDurationBuckets,
          error: errorMessage(error, "Unable to load duration bucket charts"),
        });
      });

    void getDashboardVolumetricsKpiReassignmentHopsTrend(requestBody)
      .then((nextReassignmentHopsTrend) => {
        setReassignmentHopsTrend({
          status: "success",
          data: nextReassignmentHopsTrend,
          error: null,
        });
      })
      .catch((error) => {
        setReassignmentHopsTrend({
          status: "error",
          data: emptyReassignmentHopsTrend,
          error: errorMessage(error, "Unable to load reassignment hops trend"),
        });
      });

    void getDashboardVolumetricsKpiProblemManagementTrend(requestBody)
      .then((nextProblemManagementTrend) => {
        setProblemManagementTrend({
          status: "success",
          data: nextProblemManagementTrend,
          error: null,
        });
      })
      .catch((error) => {
        setProblemManagementTrend({
          status: "error",
          data: emptyProblemManagementTrend,
          error: errorMessage(error, "Unable to load Problem Management trend"),
        });
      });

  }, [
    createdPatternType,
    hourlyDayType,
    requestBody,
    ticketsPerUserN,
    topApplicationsN,
    topBatchApplicationsN,
  ]);

  useEffect(() => {
    if (projectId !== loadedProjectId) {
      filterCountsRequestRef.current = 0;
      setLoadedProjectId(projectId);
      setScope("in_scope");
      setTicketType("all");
      setFilters(emptyFilters);
      setActiveSubTab("overall_volume");
      setHourlyDayType("weekdays");
      setPriorityView("graph");
      setTopApplicationsN(10);
      setTopBatchApplicationsN(10);
      setTicketsPerUserN(10);
      setFilterValues(createLoadState(emptyFilterValues));
      setFilterCatalog(null);
      setFilterCounts(null);
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
      setDetailedSplits(createLoadState(emptyDetailedSplits));
      setTicketsPerUser(createLoadState(emptyTicketsPerUser));
      setDistributionSplits(createLoadState(emptyDistributionSplits));
      setScTaskCatalogItemProportion(createLoadState(emptyScTaskCatalogItemProportion));
      setKpiMttrTrends(createLoadState(emptyKpiMttrTrends));
      setKpiDurationBuckets(createLoadState(emptyDurationBuckets));
      setReassignmentHopsTrend(createLoadState(emptyReassignmentHopsTrend));
      setProblemManagementTrend(createLoadState(emptyProblemManagementTrend));
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

  useEffect(() => {
    if (isActive && hasActiveProjectContext && hasFilterCacheContext && !filterCatalog) {
      void loadVolumetricsFilterCatalog();
    }
  }, [
    filterCatalog,
    hasActiveProjectContext,
    hasFilterCacheContext,
    isActive,
    loadVolumetricsFilterCatalog,
  ]);

  useEffect(() => {
    if (
      !isActive ||
      !hasActiveProjectContext ||
      !hasFilterCacheContext ||
      !isDateRangeReady ||
      !requestBody ||
      !filterCatalog
    ) {
      return;
    }
    setFilterValues((currentFilterValues) => ({
      status: currentFilterValues.status === "idle" ? "success" : currentFilterValues.status,
      data: volumetricsFilterValuesFromCatalog(filterCatalog, null, filters, scope, ticketType),
      error: null,
    }));

    const timeoutId = window.setTimeout(() => {
      void loadVolumetricsFilterCounts();
    }, 400);

    return () => {
      window.clearTimeout(timeoutId);
    };
  }, [
    filterCatalog,
    filters,
    hasActiveProjectContext,
    hasFilterCacheContext,
    isActive,
    isDateRangeReady,
    loadVolumetricsFilterCounts,
    requestBody,
    requestSignature,
    scope,
    ticketType,
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
  const agreementModeLabel = agreementMode === "ola" ? "OLA" : "SLA";
  const commentaryFunctional = commentaryFunctionalContext(filters.functional_track_ams_owner);
  const volumetricsCommentary = (
    subTab: VolumetricsSubTab,
    sectionKey: string,
    chartKey?: string
  ): ReactNode => (
    <CommentaryEditor
      project_id={projectId}
      dashboard_area="volumetrics"
      tab_name="volumetrics_sla"
      sub_tab_name={subTabCommentaryKeys[subTab]}
      section_key={sectionKey}
      chart_key={chartKey ?? null}
      scope_filter={scope}
      ticket_type_filter={ticketType}
      functional_track_ams_owner={commentaryFunctional}
    />
  );

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
          <p className="muted-text">
            {filterCatalog ? "Updating counts..." : "Loading filter catalog..."}
          </p>
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
            label="Business Criticality"
            options={filterOptions.business_critical}
            selectedValues={filters.business_critical}
            onChange={(values) => updateFilter("business_critical", values)}
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
                  label={`Response ${agreementModeLabel}`}
                  primary={`${averageLabel} adherence: ${formatPercent(
                    summary.data.response_sla.average_adherence_pct
                  )}`}
                  secondary={`${formatNumber(
                    summary.data.response_sla.met_count
                  )} met / ${formatNumber(summary.data.response_sla.applicable_count)} applicable`}
                  index={3}
                />
                <MetricCard
                  label={`Resolution ${agreementModeLabel}`}
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
              {volumetricsCommentary("overall_volume", "overall_volume_summary")}
            </section>

            <CreatedResolvedCanceledChart
              data={volumeTrend.data}
              status={volumeTrend.status}
              error={volumeTrend.error}
              ticketType={ticketType}
              timeGrain={timeGrain}
              commentary={volumetricsCommentary(
                "overall_volume",
                "overall_volume_trends",
                "created_resolved_canceled"
              )}
            />

            <BacklogChart
              data={backlog.data}
              status={backlog.status}
              error={backlog.error}
              timeGrain={timeGrain}
              commentary={volumetricsCommentary(
                "overall_volume",
                "overall_volume_trends",
                "backlog"
              )}
            />

            <CreatedPatternChart
              data={createdPattern.data}
              status={createdPattern.status}
              error={createdPattern.error}
              patternType={createdPatternType}
              onPatternTypeChange={setCreatedPatternType}
              commentary={volumetricsCommentary(
                "overall_volume",
                "overall_volume_trends",
                "created_pattern"
              )}
            />

            <HourlyCreatedResolvedChart
              data={hourlyCreatedResolved.data}
              status={hourlyCreatedResolved.status}
              error={hourlyCreatedResolved.error}
              dayType={hourlyDayType}
              onDayTypeChange={setHourlyDayType}
              ticketType={ticketType}
              commentary={volumetricsCommentary(
                "overall_volume",
                "overall_volume_trends",
                "hourly_created_resolved"
              )}
            />

            <PriorityDistributionChart
              data={priorityDistribution.data}
              status={priorityDistribution.status}
              error={priorityDistribution.error}
              view={priorityView}
              onViewChange={setPriorityView}
              timeGrain={timeGrain}
              commentary={volumetricsCommentary(
                "overall_volume",
                "overall_volume_trends",
                "priority_distribution"
              )}
            />
          </>
        ) : null}

        {activeSubTab === "overall_sla" ? (
          <OverallSlaTrends
            data={slaTrends.data}
            status={slaTrends.status}
            error={slaTrends.error}
            agreementMode={agreementMode}
            onAgreementModeChange={setAgreementMode}
            ticketType={ticketType}
            timeGrain={timeGrain}
            commentaryForChart={(chartKey) =>
              volumetricsCommentary("overall_sla", "overall_sla_trends", chartKey)
            }
          />
        ) : null}

        {activeSubTab === "detailed_volume" ? (
          <DetailedVolumeTrends
            detailedSplits={detailedSplits.data}
            detailedSplitsError={detailedSplits.error}
            detailedSplitsStatus={detailedSplits.status}
            distributionSplits={distributionSplits.data}
            distributionSplitsError={distributionSplits.error}
            distributionSplitsStatus={distributionSplits.status}
            incidentBatchTrend={incidentBatchTrend.data}
            incidentBatchTrendError={incidentBatchTrend.error}
            incidentBatchTrendStatus={incidentBatchTrend.status}
            onTopApplicationsNChange={setTopApplicationsN}
            onTopBatchApplicationsNChange={setTopBatchApplicationsN}
            onTicketsPerUserNChange={setTicketsPerUserN}
            ticketType={ticketType}
            scTaskCatalogItemProportion={scTaskCatalogItemProportion.data}
            scTaskCatalogItemProportionError={scTaskCatalogItemProportion.error}
            scTaskCatalogItemProportionStatus={scTaskCatalogItemProportion.status}
            ticketsPerUser={ticketsPerUser.data}
            ticketsPerUserError={ticketsPerUser.error}
            ticketsPerUserN={ticketsPerUserN}
            ticketsPerUserStatus={ticketsPerUser.status}
            topApplications={topApplications.data}
            topApplicationsError={topApplications.error}
            topApplicationsN={topApplicationsN}
            topApplicationsStatus={topApplications.status}
            topIncidentBatchApplications={topIncidentBatchApplications.data}
            topIncidentBatchApplicationsError={topIncidentBatchApplications.error}
            topIncidentBatchApplicationsStatus={topIncidentBatchApplications.status}
            topBatchApplicationsN={topBatchApplicationsN}
            commentaryForChart={(chartKey) =>
              volumetricsCommentary("detailed_volume", "detailed_volume_trends", chartKey)
            }
          />
        ) : null}
        {activeSubTab === "kpi" ? (
          <KpiTrends
            durationBuckets={kpiDurationBuckets.data}
            durationBucketsError={kpiDurationBuckets.error}
            durationBucketsStatus={kpiDurationBuckets.status}
            mttr={kpiMttrTrends.data}
            mttrError={kpiMttrTrends.error}
            mttrStatus={kpiMttrTrends.status}
            reassignmentHops={reassignmentHopsTrend.data}
            reassignmentHopsError={reassignmentHopsTrend.error}
            reassignmentHopsStatus={reassignmentHopsTrend.status}
            problemManagement={problemManagementTrend.data}
            problemManagementError={problemManagementTrend.error}
            problemManagementStatus={problemManagementTrend.status}
            ticketType={ticketType}
            timeGrain={timeGrain}
            commentaryForChart={(chartKey) =>
              volumetricsCommentary("kpi", "kpi_trends", chartKey)
            }
          />
        ) : null}
        {activeSubTab === "category" ? (
          <VolumetricsPlaceholder
            title="Category-wise Trends"
            commentary={volumetricsCommentary("category", "category_wise_trends")}
          />
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

function VolumetricsPlaceholder({
  commentary,
  title,
}: {
  commentary?: ReactNode;
  title: string;
}) {
  return (
    <section className="panel volumetrics-placeholder-panel">
      <p className="label">{title}</p>
      <h3>Detailed requirements for this section will be added in the next prompts.</h3>
      {commentary}
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
  commentaryForChart,
  detailedSplits,
  detailedSplitsError,
  detailedSplitsStatus,
  distributionSplits,
  distributionSplitsError,
  distributionSplitsStatus,
  incidentBatchTrend,
  incidentBatchTrendError,
  incidentBatchTrendStatus,
  onTopApplicationsNChange,
  onTopBatchApplicationsNChange,
  onTicketsPerUserNChange,
  scTaskCatalogItemProportion,
  scTaskCatalogItemProportionError,
  scTaskCatalogItemProportionStatus,
  ticketType,
  ticketsPerUser,
  ticketsPerUserError,
  ticketsPerUserN,
  ticketsPerUserStatus,
  topApplications,
  topApplicationsError,
  topApplicationsN,
  topApplicationsStatus,
  topBatchApplicationsN,
  topIncidentBatchApplications,
  topIncidentBatchApplicationsError,
  topIncidentBatchApplicationsStatus,
}: {
  commentaryForChart: (chartKey: string) => ReactNode;
  detailedSplits: DashboardVolumetricsDetailedArchitectureInstallSplits;
  detailedSplitsError: string | null;
  detailedSplitsStatus: LoadStatus;
  distributionSplits: DashboardVolumetricsDistributionSplits;
  distributionSplitsError: string | null;
  distributionSplitsStatus: LoadStatus;
  incidentBatchTrend: DashboardVolumetricsIncidentBatchTrend;
  incidentBatchTrendError: string | null;
  incidentBatchTrendStatus: LoadStatus;
  onTopApplicationsNChange: (value: TopNSelection) => void;
  onTopBatchApplicationsNChange: (value: TopNSelection) => void;
  onTicketsPerUserNChange: (value: TopNSelection) => void;
  scTaskCatalogItemProportion: DashboardVolumetricsScTaskCatalogItemProportion;
  scTaskCatalogItemProportionError: string | null;
  scTaskCatalogItemProportionStatus: LoadStatus;
  ticketType: VolumetricsTicketType;
  ticketsPerUser: DashboardVolumetricsTicketsPerUser;
  ticketsPerUserError: string | null;
  ticketsPerUserN: TopNSelection;
  ticketsPerUserStatus: LoadStatus;
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
      <TopApplicationsHorizontalChart
        data={topApplications}
        description={rankingWindowText(topApplications.ranking_window)}
        error={topApplicationsError}
        onTopNChange={onTopApplicationsNChange}
        status={topApplicationsStatus}
        title="Top High-Volume Applications"
        topN={topApplicationsN}
        commentary={commentaryForChart("top_high_volume_applications")}
      />

      <IncidentBatchTrendChart
        data={incidentBatchTrend}
        error={incidentBatchTrendError}
        status={incidentBatchTrendStatus}
        commentary={commentaryForChart("batch_related_incidents_created")}
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
        commentary={commentaryForChart("top_incident_batch_applications")}
      />

      <TicketsPerUserChart
        data={ticketsPerUser}
        error={ticketsPerUserError}
        onTopNChange={onTicketsPerUserNChange}
        status={ticketsPerUserStatus}
        topN={ticketsPerUserN}
        commentary={commentaryForChart("tickets_per_user_application")}
      />

      <DistributionPieRow
        commentary={commentaryForChart("sap_non_sap_distribution_row")}
        data={distributionSplits.sap_non_sap}
        error={distributionSplitsError}
        status={distributionSplitsStatus}
        ticketType={ticketType}
        titles={{
          all: "Average Monthly Tickets by SAP / Non-SAP",
          incidents: "Average Monthly Incidents by SAP / Non-SAP",
          sc_tasks: "Average Monthly SC Tasks by SAP / Non-SAP",
        }}
        window={distributionSplits.ranking_window}
      />
      <DistributionPieRow
        commentary={commentaryForChart("architecture_type_distribution_row")}
        data={distributionSplits.architecture_type}
        error={distributionSplitsError}
        status={distributionSplitsStatus}
        ticketType={ticketType}
        titles={{
          all: "Average Monthly Tickets by Architecture Type",
          incidents: "Average Monthly Incidents by Architecture Type",
          sc_tasks: "Average Monthly SC Tasks by Architecture Type",
        }}
        window={distributionSplits.ranking_window}
      />
      <DistributionPieRow
        commentary={commentaryForChart("install_type_distribution_row")}
        data={distributionSplits.install_type}
        error={distributionSplitsError}
        status={distributionSplitsStatus}
        ticketType={ticketType}
        titles={{
          all: "Average Monthly Tickets by Install Type",
          incidents: "Average Monthly Incidents by Install Type",
          sc_tasks: "Average Monthly SC Tasks by Install Type",
        }}
        window={distributionSplits.ranking_window}
      />
      <DistributionPieRow
        commentary={commentaryForChart("hosting_env_distribution_row")}
        data={distributionSplits.hosting_env}
        error={distributionSplitsError}
        status={distributionSplitsStatus}
        ticketType={ticketType}
        titles={{
          all: "Average Monthly Tickets by Hosting Env",
          incidents: "Average Monthly Incidents by Hosting Env",
          sc_tasks: "Average Monthly SC Tasks by Hosting Env",
        }}
        window={distributionSplits.ranking_window}
      />

      <ScTaskCatalogItemProportionSection
        commentary={commentaryForChart("volumetrics_sc_task_catalog_item_proportion")}
        data={scTaskCatalogItemProportion}
        error={scTaskCatalogItemProportionError}
        status={scTaskCatalogItemProportionStatus}
        ticketType={ticketType}
      />
    </>
  );
}

function splitChartNotApplicable(
  selectedTicketType: VolumetricsTicketType,
  valueTicketType: Exclude<VolumetricsTicketType, "all">
): boolean {
  return selectedTicketType !== "all" && selectedTicketType !== valueTicketType;
}

function ScTaskCatalogTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: Array<{ payload: DashboardVolumetricsScTaskCatalogItemRow }>;
}) {
  if (!active || !payload?.length) {
    return null;
  }
  const row = payload[0].payload;
  return (
    <div className="chart-tooltip">
      <strong>{row.catalog_item_name}</strong>
      <span>SC Task Count: {formatNumber(row.sc_task_count)}</span>
      <span>Average Monthly Volume: {formatNumber(row.avg_monthly_volume, 1)}</span>
      <span>Proportion: {formatPercent(row.proportion_pct)}</span>
    </div>
  );
}

function ScTaskCatalogPie({
  period,
}: {
  period: DashboardVolumetricsScTaskCatalogItemPeriod;
}) {
  const chartTitle = `${period.period_label} Catalog Item Proportion`;
  const { chartRef, plotWidth } = useChartFrame(chartTitle);
  const hasRows = period.pie_rows.length > 0;
  const chartWidth = Math.max(320, plotWidth - 8);
  const outerRadius = Math.min(88, Math.max(64, Math.floor(chartWidth * 0.2)));
  return (
    <section className="sc-task-catalog-card">
      <h4>{period.period_label} Catalog Item Proportion</h4>
      <p className="muted-text">
        {period.from_date} to {period.to_date} · {formatNumber(period.total_sc_tasks)} SC Tasks
      </p>
      {hasRows ? (
        <div className="sc-task-catalog-pie-stage" ref={chartRef}>
          <PieChart
            width={chartWidth}
            height={340}
            margin={{ top: 10, right: 8, bottom: 112, left: 8 }}
          >
            <Pie
              data={period.pie_rows}
              cx="50%"
              cy="42%"
              dataKey="sc_task_count"
              isAnimationActive={false}
              minAngle={1}
              nameKey="catalog_item_name"
              outerRadius={outerRadius}
              paddingAngle={1}
              stroke="#ffffff"
              strokeWidth={2}
            >
              {period.pie_rows.map((entry, index) => (
                <Cell
                  fill={chartColors.pie[index % chartColors.pie.length]}
                  key={`${period.period_key}-${entry.catalog_item_name}`}
                />
              ))}
            </Pie>
            <Tooltip content={<ScTaskCatalogTooltip />} />
            <Legend
              align="center"
              height={110}
              iconSize={10}
              verticalAlign="bottom"
              wrapperStyle={{ fontSize: "0.72rem", fontWeight: 700, lineHeight: "1.15" }}
              formatter={(value) => {
                const row = period.pie_rows.find((item) => item.catalog_item_name === value);
                return `${value} (${formatPercent(row?.proportion_pct)})`;
              }}
            />
          </PieChart>
        </div>
      ) : (
        <p className="muted-text chart-state-text">
          {period.warnings[0] ?? "No data available for this period."}
        </p>
      )}
    </section>
  );
}

function ScTaskCatalogTable({
  period,
}: {
  period: DashboardVolumetricsScTaskCatalogItemPeriod;
}) {
  return (
    <section className="sc-task-catalog-card sc-task-catalog-table-card">
      <h4>{period.period_label} Top Catalog Items</h4>
      {period.top_10_rows.length ? (
        <div className="compact-table-wrapper">
          <table className="compact-data-table">
            <thead>
              <tr>
                <th>Rank</th>
                <th>Catalog Item</th>
                <th>SC Task Count</th>
                <th>Average Monthly Volume</th>
              </tr>
            </thead>
            <tbody>
              {period.top_10_rows.map((row) => (
                <tr key={`${period.period_key}-${row.rank}-${row.catalog_item_name}`}>
                  <td>{row.rank}</td>
                  <td>{row.catalog_item_name}</td>
                  <td>{formatNumber(row.sc_task_count)}</td>
                  <td>{row.avg_monthly_with_pct_label}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="muted-text chart-state-text">
          {period.warnings[0] ?? "No data available for this period."}
        </p>
      )}
    </section>
  );
}

function ScTaskCatalogItemProportionSection({
  commentary,
  data,
  error,
  status,
  ticketType,
}: {
  commentary?: ReactNode;
  data: DashboardVolumetricsScTaskCatalogItemProportion;
  error: string | null;
  status: LoadStatus;
  ticketType: VolumetricsTicketType;
}) {
  const ticketTypeNotApplicable = ticketType === "incident";
  const warningMessage = data.warnings[0];
  return (
    <section className="chart-card volumetrics-chart-card sc-task-catalog-section">
      <div className="applications-chart-header">
        <div>
          <h3>SC Task Catalog Item Proportion</h3>
          <p className="muted-text">
            Shows the proportion of SC Tasks by catalog item across selected half-year periods.
            Values are based on created SC Task volume.
          </p>
        </div>
      </div>

      {status === "loading" ? <p className="muted-text chart-state-text">Loading chart...</p> : null}
      {status === "error" ? <p className="error-text">{error}</p> : null}
      {ticketTypeNotApplicable && status !== "loading" ? (
        <p className="muted-text chart-state-text">
          {warningMessage ??
            "SC Task Catalog Item Proportion is available for SC Tasks only. Change Ticket Type to All or SC Tasks."}
        </p>
      ) : null}

      {status !== "loading" && status !== "error" && !ticketTypeNotApplicable ? (
        <>
          <div className="sc-task-catalog-grid">
            {data.periods.map((period) => (
              <ScTaskCatalogPie key={period.period_key} period={period} />
            ))}
          </div>
          <div className="sc-task-catalog-grid sc-task-catalog-table-grid">
            {data.periods.map((period) => (
              <ScTaskCatalogTable key={`${period.period_key}-table`} period={period} />
            ))}
          </div>
          {data.data_notes.length ? (
            <ul className="chart-data-notes">
              {data.data_notes.map((note) => (
                <li key={note}>{note}</li>
              ))}
            </ul>
          ) : null}
        </>
      ) : null}
      {commentary}
    </section>
  );
}

function splitWindowText(window: DashboardVolumetricsRankingWindow): string {
  if (!window.start_month || !window.end_month) {
    return "Uses the latest complete 6 months and excludes the current partial month.";
  }
  return `Uses average monthly created volume for ${window.start_month} to ${window.end_month}.`;
}

function SplitPieChart({
  commentary,
  data,
  error,
  status,
  ticketType,
  title,
  valueTicketType,
  window,
}: {
  commentary?: ReactNode;
  data: DashboardVolumetricsDetailedArchitectureInstallSplits["architecture_type"]["incidents"];
  error: string | null;
  status: LoadStatus;
  ticketType: VolumetricsTicketType;
  title: string;
  valueTicketType: Exclude<VolumetricsTicketType, "all">;
  window: DashboardVolumetricsRankingWindow;
}) {
  const { chartRef, copyMessage, handleCopy, plotWidth } = useChartFrame(title);
  const notApplicable = splitChartNotApplicable(ticketType, valueTicketType);
  const hasRows = data.length > 0;
  const chartWidth = Math.max(420, plotWidth - 24);
  const canCopy = status !== "loading" && hasRows && !notApplicable;
  const total = data.reduce((sum, item) => sum + item.average_monthly_count, 0);

  return (
    <section className="chart-card volumetrics-chart-card" aria-label={title}>
      <div className="applications-chart-header">
        <div>
          <h3>{title}</h3>
          <p className="muted-text">{splitWindowText(window)}</p>
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
      {notApplicable ? (
        <p className="muted-text chart-state-text">
          This split chart is not applicable for the selected ticket type.
        </p>
      ) : null}
      {status !== "loading" && status !== "error" && !notApplicable && !hasRows ? (
        <p className="muted-text chart-state-text">No chart data available.</p>
      ) : null}

      {status !== "loading" && status !== "error" && !notApplicable && hasRows ? (
        <div className="applications-chart-plot volumetrics-chart-plot" ref={chartRef}>
          <div className="applications-chart-stage">
            <PieChart width={chartWidth} height={330}>
              <Pie
                data={data}
                cx="50%"
                cy="45%"
                dataKey="average_monthly_count"
                nameKey="label"
                outerRadius={96}
              >
                {data.map((entry, index) => (
                  <Cell
                    fill={chartColors.pie[index % chartColors.pie.length]}
                    key={entry.label}
                  />
                ))}
              </Pie>
              <Tooltip formatter={(value) => formatNumber(Number(value), 1)} />
              <Legend
                formatter={(value) => {
                  const row = data.find((item) => item.label === value);
                  const share = row && total ? `, ${formatPercent(row.percentage)}` : "";
                  return `${value} (${formatNumber(row?.average_monthly_count, 1)} avg${share})`;
                }}
              />
            </PieChart>
          </div>
        </div>
      ) : null}

      {copyMessage ? <p className="chart-copy-status">{copyMessage}</p> : null}
      {commentary}
    </section>
  );
}

function TopApplicationsHorizontalChart({
  commentary,
  data,
  description,
  error,
  onTopNChange,
  status,
  title,
  topN,
}: {
  commentary?: ReactNode;
  data: DashboardVolumetricsTopApplications;
  description: string;
  error: string | null;
  onTopNChange: (value: TopNSelection) => void;
  status: LoadStatus;
  title: string;
  topN: TopNSelection;
}) {
  const { chartRef, copyMessage, handleCopy, plotWidth } = useChartFrame(title);
  const hasRows = data.points.length > 0;
  const chartWidth = Math.max(840, plotWidth - 24);
  const chartHeight = topN === 20 ? 800 : 500;
  const canCopy = status !== "loading" && hasRows;

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
      {status !== "loading" && status !== "error" && !hasRows ? (
        <p className="muted-text chart-state-text">No chart data available.</p>
      ) : null}
      {status !== "loading" && status !== "error" && hasRows ? (
        <div className="applications-chart-plot volumetrics-chart-plot" ref={chartRef}>
          <div className="applications-chart-scroll">
            <div className="applications-chart-stage">
              <BarChart
                data={data.points}
                height={chartHeight}
                layout="vertical"
                margin={{ top: 22, right: 116, bottom: 28, left: 260 }}
                width={chartWidth}
              >
                <CartesianGrid horizontal={false} strokeDasharray="3 3" />
                <XAxis type="number" />
                <YAxis
                  dataKey="application_name"
                  interval={0}
                  tick={{ fontSize: 12, fontWeight: 700 }}
                  type="category"
                  width={250}
                />
                <Tooltip
                  formatter={(value, name) =>
                    name === "Average monthly created tickets"
                      ? formatNumber(Number(value), 1)
                      : String(value)
                  }
                />
                <Bar
                  dataKey="average_created"
                  fill={chartColors.created}
                  name="Average monthly created tickets"
                  radius={[0, 5, 5, 0]}
                >
                  <LabelList dataKey="display_label" position="right" fontSize={12} />
                </Bar>
              </BarChart>
            </div>
          </div>
        </div>
      ) : null}

      {copyMessage ? <p className="chart-copy-status">{copyMessage}</p> : null}
      {commentary}
    </section>
  );
}

function TicketsPerUserChart({
  commentary,
  data,
  error,
  onTopNChange,
  status,
  topN,
}: {
  commentary?: ReactNode;
  data: DashboardVolumetricsTicketsPerUser;
  error: string | null;
  onTopNChange: (value: TopNSelection) => void;
  status: LoadStatus;
  topN: TopNSelection;
}) {
  const title = "Tickets per User per Month by Application";
  const { chartRef, copyMessage, handleCopy, plotWidth } = useChartFrame(title);
  const hasRows = data.points.length > 0;
  const chartWidth = Math.max(840, plotWidth - 24);
  const chartHeight = topN === 20 ? 760 : 480;
  const canCopy = status !== "loading" && hasRows;

  return (
    <section className="chart-card volumetrics-chart-card" aria-label={title}>
      <div className="applications-chart-header">
        <div>
          <h3>{title}</h3>
          <p className="muted-text">
            Calculated as latest complete 6-month average monthly ticket volume divided by
            Active Users.
          </p>
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
      {status !== "loading" && status !== "error" && !hasRows ? (
        <p className="muted-text chart-state-text">
          No applications with non-zero Active Users are available.
        </p>
      ) : null}
      {status !== "loading" && status !== "error" && hasRows ? (
        <div className="applications-chart-plot volumetrics-chart-plot" ref={chartRef}>
          <div className="applications-chart-scroll">
            <div className="applications-chart-stage">
              <BarChart
                data={data.points}
                height={chartHeight}
                layout="vertical"
                margin={{ top: 22, right: 96, bottom: 28, left: 260 }}
                width={chartWidth}
              >
                <CartesianGrid horizontal={false} strokeDasharray="3 3" />
                <XAxis type="number" />
                <YAxis
                  dataKey="application_name"
                  interval={0}
                  tick={{ fontSize: 12, fontWeight: 700 }}
                  type="category"
                  width={250}
                />
                <Tooltip
                  formatter={(value, name) =>
                    name === "Tickets per user per month"
                      ? formatNumber(Number(value), 2)
                      : formatNumber(Number(value), 1)
                  }
                />
                <Bar
                  dataKey="tickets_per_user_per_month"
                  fill={chartColors.patternAlt}
                  name="Tickets per user per month"
                  radius={[0, 5, 5, 0]}
                >
                  <LabelList dataKey="display_label" position="right" fontSize={12} />
                </Bar>
              </BarChart>
            </div>
          </div>
        </div>
      ) : null}

      {copyMessage ? <p className="chart-copy-status">{copyMessage}</p> : null}
      {commentary}
    </section>
  );
}

type DistributionTicketTypeKey = "all" | "incidents" | "sc_tasks";

function distributionChartNotApplicable(
  selectedTicketType: VolumetricsTicketType,
  valueTicketType: DistributionTicketTypeKey
): boolean {
  if (selectedTicketType === "all") {
    return false;
  }
  if (selectedTicketType === "incident") {
    return valueTicketType !== "incidents";
  }
  return valueTicketType !== "sc_tasks";
}

function DistributionPieRow({
  commentary,
  data,
  error,
  status,
  ticketType,
  titles,
  window,
}: {
  commentary: ReactNode;
  data: DashboardVolumetricsDistributionSplits["sap_non_sap"];
  error: string | null;
  status: LoadStatus;
  ticketType: VolumetricsTicketType;
  titles: Record<DistributionTicketTypeKey, string>;
  window: DashboardVolumetricsRankingWindow;
}) {
  const entries: Array<{ key: DistributionTicketTypeKey; points: typeof data.all }> = [
    { key: "all", points: data.all },
    { key: "incidents", points: data.incidents },
    { key: "sc_tasks", points: data.sc_tasks },
  ];
  return (
    <section className="volumetrics-row-group">
      <div className="volumetrics-three-column-grid">
        {entries.map((entry) => (
          <DistributionPieChart
            data={entry.points}
            error={error}
            key={entry.key}
            status={status}
            ticketType={ticketType}
            title={titles[entry.key]}
            valueTicketType={entry.key}
            window={window}
          />
        ))}
      </div>
      {commentary}
    </section>
  );
}

function DistributionPieChart({
  data,
  error,
  status,
  ticketType,
  title,
  valueTicketType,
  window,
}: {
  data: DashboardVolumetricsSplitDatum[];
  error: string | null;
  status: LoadStatus;
  ticketType: VolumetricsTicketType;
  title: string;
  valueTicketType: DistributionTicketTypeKey;
  window: DashboardVolumetricsRankingWindow;
}) {
  const { chartRef, copyMessage, handleCopy, plotWidth } = useChartFrame(title);
  const notApplicable = distributionChartNotApplicable(ticketType, valueTicketType);
  const hasRows = data.length > 0;
  const chartWidth = Math.max(360, plotWidth - 24);
  const canCopy = status !== "loading" && hasRows && !notApplicable;
  const total = data.reduce((sum, item) => sum + item.average_monthly_count, 0);

  return (
    <section className="chart-card volumetrics-chart-card" aria-label={title}>
      <div className="applications-chart-header">
        <div>
          <h3>{title}</h3>
          <p className="muted-text">{splitWindowText(window)}</p>
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
      {notApplicable ? (
        <p className="muted-text chart-state-text">
          This distribution chart is not applicable for the selected ticket type.
        </p>
      ) : null}
      {status !== "loading" && status !== "error" && !notApplicable && !hasRows ? (
        <p className="muted-text chart-state-text">No chart data available.</p>
      ) : null}
      {status !== "loading" && status !== "error" && !notApplicable && hasRows ? (
        <div className="applications-chart-plot volumetrics-chart-plot" ref={chartRef}>
          <div className="applications-chart-stage">
            <PieChart width={chartWidth} height={330}>
              <Pie
                data={data}
                cx="50%"
                cy="45%"
                dataKey="average_monthly_count"
                nameKey="label"
                outerRadius={92}
              >
                {data.map((entry, index) => (
                  <Cell
                    fill={chartColors.pie[index % chartColors.pie.length]}
                    key={entry.label}
                  />
                ))}
              </Pie>
              <Tooltip formatter={(value) => formatNumber(Number(value), 1)} />
              <Legend
                formatter={(value) => {
                  const row = data.find((item) => item.label === value);
                  const share = row && total ? `, ${formatPercent(row.percentage)}` : "";
                  return `${value} (${formatNumber(row?.average_monthly_count, 1)} avg${share})`;
                }}
              />
            </PieChart>
          </div>
        </div>
      ) : null}

      {copyMessage ? <p className="chart-copy-status">{copyMessage}</p> : null}
    </section>
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
  commentary,
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
  commentary?: ReactNode;
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
      {commentary}
    </section>
  );
}

function IncidentBatchTrendChart({
  commentary,
  data,
  error,
  status,
}: {
  commentary?: ReactNode;
  data: DashboardVolumetricsIncidentBatchTrend;
  error: string | null;
  status: LoadStatus;
}) {
  const title = "Batch-related Incidents Created";
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
      {commentary}
    </section>
  );
}

const mttrPriorityKeys: Array<keyof DashboardVolumetricsKpiMttrPrioritySet> = [
  "P1",
  "P2",
  "P3",
  "P4",
];
const mttrPriorityPairs: Array<Array<keyof DashboardVolumetricsKpiMttrPrioritySet>> = [
  ["P1", "P2"],
  ["P3", "P4"],
];

const durationBucketLabels = ["0-1 day", "1-3 days", "3-10 days", ">10 days"];

function KpiTrends({
  commentaryForChart,
  durationBuckets,
  durationBucketsError,
  durationBucketsStatus,
  mttr,
  mttrError,
  mttrStatus,
  problemManagement,
  problemManagementError,
  problemManagementStatus,
  reassignmentHops,
  reassignmentHopsError,
  reassignmentHopsStatus,
  ticketType,
  timeGrain,
}: {
  commentaryForChart: (chartKey: string) => ReactNode;
  durationBuckets: DashboardVolumetricsKpiDurationBuckets;
  durationBucketsError: string | null;
  durationBucketsStatus: LoadStatus;
  mttr: DashboardVolumetricsKpiMttrTrends;
  mttrError: string | null;
  mttrStatus: LoadStatus;
  problemManagement: DashboardVolumetricsProblemManagementTrend;
  problemManagementError: string | null;
  problemManagementStatus: LoadStatus;
  reassignmentHops: DashboardVolumetricsReassignmentHopsTrend;
  reassignmentHopsError: string | null;
  reassignmentHopsStatus: LoadStatus;
  ticketType: VolumetricsTicketType;
  timeGrain: VolumetricsTimeGrain;
}) {
  return (
    <>
      <MttrPriorityGroup
        data={mttr.incident}
        error={mttrError}
        selectedTicketType={ticketType}
        status={mttrStatus}
        title="Incident MTTR by Priority"
        valueTicketType="incident"
        timeGrain={timeGrain}
        commentaryForChart={commentaryForChart}
      />
      <MttrPriorityGroup
        data={mttr.sc_task}
        error={mttrError}
        selectedTicketType={ticketType}
        status={mttrStatus}
        title="SC Task MTTR by Priority"
        valueTicketType="sc_task"
        timeGrain={timeGrain}
        commentaryForChart={commentaryForChart}
      />
      <ReassignmentHopsTrendChart
        commentary={commentaryForChart("reassignment_hops_trend")}
        data={reassignmentHops}
        error={reassignmentHopsError}
        status={reassignmentHopsStatus}
      />
      <ProblemManagementTrendChart
        commentary={commentaryForChart("problem_management_trend")}
        data={problemManagement}
        error={problemManagementError}
        status={problemManagementStatus}
      />
      <DurationBucketGroup
        commentary={commentaryForChart("incident_duration_buckets_row")}
        data={durationBuckets.incident}
        error={durationBucketsError}
        selectedTicketType={ticketType}
        status={durationBucketsStatus}
        title="Incident Resolved Volume by Resolution Duration"
        valueTicketType="incident"
      />
      <DurationBucketGroup
        commentary={commentaryForChart("sc_task_duration_buckets_row")}
        data={durationBuckets.sc_task}
        error={durationBucketsError}
        selectedTicketType={ticketType}
        status={durationBucketsStatus}
        title="SC Task Closed Volume by Closed Duration"
        valueTicketType="sc_task"
      />
    </>
  );
}

function ReassignmentHopsTrendChart({
  commentary,
  data,
  error,
  status,
}: {
  commentary: ReactNode;
  data: DashboardVolumetricsReassignmentHopsTrend;
  error: string | null;
  status: LoadStatus;
}) {
  const title = "Reassignment / Hops Trend";
  const { chartRef, copyMessage, handleCopy, plotWidth } = useChartFrame(title);
  const rows = data.points.map((point) => ({
    ...point,
    tickets_label:
      point.tickets_with_2_plus_reassignments > 0
        ? String(point.tickets_with_2_plus_reassignments)
        : null,
    hops_pct_label:
      point.reassignment_hops_pct_of_created !== null
        ? formatPercent(point.reassignment_hops_pct_of_created)
        : null,
  }));
  const hasRows = rows.length > 0;
  const hasValues = rows.some(
    (row) =>
      row.total_created_tickets > 0 ||
      row.tickets_with_2_plus_reassignments > 0 ||
      row.total_reassignment_hops_ge_2 > 0
  );
  const chartWidth = trendChartWidth(rows.length, "monthly", plotWidth);
  const canCopy = status !== "loading" && hasRows && hasValues;

  return (
    <section className="panel kpi-trends-section">
      <div className="applications-chart-header">
        <div>
          <p className="label">KPI Trends</p>
          <h3>{title}</h3>
          <p className="muted-text">
            Monthly tickets with 2+ reassignments and reassignment hops as % of created volume.
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

      <p className="muted-text">
        Tickets with 2+ reassignments indicate handoffs between support teams. The percentage
        shows reassignment hops as a share of monthly created ticket volume.
      </p>

      {status === "loading" ? <p className="muted-text chart-state-text">Loading chart...</p> : null}
      {status === "error" ? <p className="error-text">{error}</p> : null}
      {status !== "loading" && status !== "error" && !hasRows ? (
        <p className="muted-text chart-state-text">No reassignment data available.</p>
      ) : null}

      {status !== "loading" && status !== "error" && hasRows ? (
        <>
          <div className="applications-chart-plot volumetrics-chart-plot" ref={chartRef}>
            <div className="applications-chart-scroll">
              <div className="applications-chart-stage">
                <ComposedChart
                  data={rows}
                  width={chartWidth}
                  height={380}
                  margin={{ top: 58, right: 72, bottom: 82, left: 58 }}
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
                  <YAxis
                    yAxisId="tickets"
                    label={{
                      value: "Tickets with 2+ reassignments",
                      angle: -90,
                      position: "insideLeft",
                    }}
                    tickFormatter={(value) => formatNumber(Number(value))}
                  />
                  <YAxis
                    yAxisId="percentage"
                    orientation="right"
                    label={{
                      value: "Hops % of created",
                      angle: 90,
                      position: "insideRight",
                    }}
                    tickFormatter={(value) => `${formatNumber(Number(value), 0)}%`}
                  />
                  <Tooltip
                    formatter={(value, name) => {
                      if (name === "Hops % of created") {
                        return [formatPercent(Number(value)), name];
                      }
                      return [formatNumber(Number(value)), name];
                    }}
                  />
                  <Legend />
                  <Line
                    connectNulls
                    dataKey="tickets_with_2_plus_reassignments"
                    dot={{ r: 3 }}
                    name="Tickets with 2+ reassignments"
                    stroke={chartColors.reassignment}
                    strokeWidth={2.5}
                    type="monotone"
                    yAxisId="tickets"
                  >
                    <LabelList
                      content={(props) =>
                        renderMttrPointLabel({
                          ...props,
                          verticalOffset: -16,
                        })
                      }
                      dataKey="tickets_label"
                    />
                  </Line>
                  <Line
                    connectNulls
                    dataKey="reassignment_hops_pct_of_created"
                    dot={{ r: 3 }}
                    name="Hops % of created"
                    stroke={chartColors.reassignmentPct}
                    strokeWidth={2.5}
                    type="monotone"
                    yAxisId="percentage"
                  >
                    <LabelList
                      content={(props) =>
                        renderMttrPointLabel({
                          ...props,
                          verticalOffset: 24,
                        })
                      }
                      dataKey="hops_pct_label"
                    />
                  </Line>
                </ComposedChart>
              </div>
            </div>
          </div>

          <p className="muted-text">
            Generic Tickets includes Incidents and SC Tasks only. Problems and Changes are
            excluded.
          </p>
          <ReassignmentHopsTable points={data.points} />
        </>
      ) : null}

      {copyMessage ? <p className="chart-copy-status">{copyMessage}</p> : null}
      {data.data_notes.length ? (
        <ul className="muted-text volumetrics-note-list">
          {data.data_notes.map((note) => (
            <li key={note}>{note}</li>
          ))}
        </ul>
      ) : null}
      {data.warnings.length ? (
        <ul className="error-text volumetrics-note-list">
          {data.warnings.map((warning) => (
            <li key={warning}>{warning}</li>
          ))}
        </ul>
      ) : null}
      {commentary}
    </section>
  );
}

function ReassignmentHopsTable({
  points,
}: {
  points: DashboardVolumetricsReassignmentHopsPoint[];
}) {
  return (
    <div className="applications-table-frame volumetrics-data-table-frame">
      <table className="applications-table volumetrics-data-table">
        <thead>
          <tr>
            <th>Month</th>
            <th>Total Created Tickets</th>
            <th>Tickets with 2+ Reassignments</th>
            <th>Total Reassignment Hops for 2+ Reassignment Tickets</th>
            <th>% Tickets with 2+ Reassignments</th>
            <th>% Reassignment Hops to Created Volume</th>
          </tr>
        </thead>
        <tbody>
          {points.map((point) => (
            <tr key={point.period_key}>
              <td>{point.period_label}</td>
              <td>{formatNumber(point.total_created_tickets)}</td>
              <td>{formatNumber(point.tickets_with_2_plus_reassignments)}</td>
              <td>{formatNumber(point.total_reassignment_hops_ge_2)}</td>
              <td>{formatPercent(point.pct_tickets_with_2_plus_reassignments)}</td>
              <td>{formatPercent(point.reassignment_hops_pct_of_created)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ProblemManagementTrendChart({
  commentary,
  data,
  error,
  status,
}: {
  commentary: ReactNode;
  data: DashboardVolumetricsProblemManagementTrend;
  error: string | null;
  status: LoadStatus;
}) {
  const title = "Problem Management Trend";
  const { chartRef, copyMessage, handleCopy, plotWidth } = useChartFrame(title);
  const useSecondaryAxis = data.axis.use_secondary_axis_for_linked_incidents;
  const linkedAxisId = useSecondaryAxis ? "linked" : "problems";
  const rows = data.points.map((point) => ({
    ...point,
    created_label:
      point.problem_tickets_created > 0 ? String(point.problem_tickets_created) : null,
    closed_label: point.problem_tickets_closed > 0 ? String(point.problem_tickets_closed) : null,
    linked_label:
      point.linked_incidents_resolved_permanently > 0
        ? String(point.linked_incidents_resolved_permanently)
        : null,
  }));
  const hasRows = rows.length > 0;
  const hasValues = rows.some(
    (row) =>
      row.problem_tickets_created > 0 ||
      row.problem_tickets_closed > 0 ||
      row.linked_incidents_resolved_permanently > 0
  );
  const chartWidth = trendChartWidth(rows.length, "monthly", plotWidth);
  const canCopy = status !== "loading" && hasRows && hasValues;

  return (
    <section className="panel kpi-trends-section">
      <div className="applications-chart-header">
        <div>
          <p className="label">KPI Trends</p>
          <h3>{title}</h3>
          <p className="muted-text">
            Problem tickets created/closed and linked incidents permanently resolved by closed
            month.
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

      <p className="muted-text">
        Shows Problem tickets created and closed by month, plus linked Incidents expected to be
        permanently resolved through closed Problems. The selected scope is applied to Problem
        records by Application Inventory assignment group.
      </p>

      {status === "loading" ? <p className="muted-text chart-state-text">Loading chart...</p> : null}
      {status === "error" ? <p className="error-text">{error}</p> : null}
      {status !== "loading" && status !== "error" && !hasRows ? (
        <p className="muted-text chart-state-text">No Problem Management data available.</p>
      ) : null}

      {status !== "loading" && status !== "error" && hasRows ? (
        <>
          <div className="applications-chart-plot volumetrics-chart-plot" ref={chartRef}>
            <div className="applications-chart-scroll">
              <div className="applications-chart-stage">
                <ComposedChart
                  data={rows}
                  width={chartWidth}
                  height={400}
                  margin={{ top: 58, right: useSecondaryAxis ? 82 : 48, bottom: 82, left: 58 }}
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
                  <YAxis
                    yAxisId="problems"
                    label={{
                      value: "Problem ticket count",
                      angle: -90,
                      position: "insideLeft",
                    }}
                    tickFormatter={(value) => formatNumber(Number(value))}
                  />
                  {useSecondaryAxis ? (
                    <YAxis
                      yAxisId="linked"
                      orientation="right"
                      label={{
                        value: "Linked incident count",
                        angle: 90,
                        position: "insideRight",
                      }}
                      tickFormatter={(value) => formatNumber(Number(value))}
                    />
                  ) : null}
                  <Tooltip
                    formatter={(value) => [formatNumber(Number(value)), ""]}
                    labelFormatter={(label) => `Month: ${label}`}
                  />
                  <Legend />
                  <Bar
                    dataKey="problem_tickets_created"
                    fill={chartColors.problemCreated}
                    name="Problem Tickets Created"
                    radius={[4, 4, 0, 0]}
                    yAxisId="problems"
                  >
                    <LabelList dataKey="created_label" position="top" fontSize={11} />
                  </Bar>
                  <Bar
                    dataKey="problem_tickets_closed"
                    fill={chartColors.problemClosed}
                    name="Problem Tickets Closed"
                    radius={[4, 4, 0, 0]}
                    yAxisId="problems"
                  >
                    <LabelList dataKey="closed_label" position="top" fontSize={11} />
                  </Bar>
                  <Line
                    connectNulls
                    dataKey="linked_incidents_resolved_permanently"
                    dot={{ r: 3 }}
                    name="Linked Incidents Resolved Permanently"
                    stroke={chartColors.linkedIncidents}
                    strokeWidth={2.5}
                    type="monotone"
                    yAxisId={linkedAxisId}
                  >
                    <LabelList
                      content={(props) =>
                        renderMttrPointLabel({
                          ...props,
                          verticalOffset: -18,
                        })
                      }
                      dataKey="linked_label"
                    />
                  </Line>
                </ComposedChart>
              </div>
            </div>
          </div>

          <p className="muted-text">
            Problem records are analyzed separately. Generic ticket totals continue to include
            Incidents and SC Tasks only.
          </p>
          <p className="muted-text">{data.axis.reason}</p>
          <ProblemManagementTable points={data.points} />
        </>
      ) : null}

      {copyMessage ? <p className="chart-copy-status">{copyMessage}</p> : null}
      {data.data_notes.length ? (
        <ul className="muted-text volumetrics-note-list">
          {data.data_notes.map((note) => (
            <li key={note}>{note}</li>
          ))}
        </ul>
      ) : null}
      {data.warnings.length ? (
        <ul className="error-text volumetrics-note-list">
          {data.warnings.map((warning) => (
            <li key={warning}>{warning}</li>
          ))}
        </ul>
      ) : null}
      {commentary}
    </section>
  );
}

function ProblemManagementTable({
  points,
}: {
  points: DashboardVolumetricsProblemManagementPoint[];
}) {
  return (
    <div className="applications-table-frame volumetrics-data-table-frame">
      <table className="applications-table volumetrics-data-table">
        <thead>
          <tr>
            <th>Month</th>
            <th>Problem Tickets Created</th>
            <th>Problem Tickets Closed</th>
            <th>Linked Incidents Resolved Permanently</th>
            <th>Avg Linked Incidents per Closed Problem</th>
          </tr>
        </thead>
        <tbody>
          {points.map((point) => (
            <tr key={point.period_key}>
              <td>{point.period_label}</td>
              <td>{formatNumber(point.problem_tickets_created)}</td>
              <td>{formatNumber(point.problem_tickets_closed)}</td>
              <td>{formatNumber(point.linked_incidents_resolved_permanently)}</td>
              <td>{formatNumber(point.avg_linked_incidents_per_closed_problem, 2)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function MttrPriorityGroup({
  commentaryForChart,
  data,
  error,
  selectedTicketType,
  status,
  timeGrain,
  title,
  valueTicketType,
}: {
  commentaryForChart: (chartKey: string) => ReactNode;
  data: DashboardVolumetricsKpiMttrPrioritySet;
  error: string | null;
  selectedTicketType: VolumetricsTicketType;
  status: LoadStatus;
  timeGrain: VolumetricsTimeGrain;
  title: string;
  valueTicketType: Exclude<VolumetricsTicketType, "all">;
}) {
  const notApplicable = splitChartNotApplicable(selectedTicketType, valueTicketType);
  return (
    <section className="panel kpi-trends-section">
      <div className="panel-heading">
        <div>
          <p className="label">KPI Trends</p>
          <h3>{title}</h3>
        </div>
      </div>
      {status === "error" ? <p className="error-text">{error}</p> : null}
      {notApplicable ? (
        <p className="muted-text chart-state-text">
          This MTTR group is not applicable for the selected ticket type.
        </p>
      ) : (
        <div className="kpi-mttr-stack">
          {mttrPriorityPairs.map((priorities) => (
            <MttrCombinedLineChart
              data={data}
              key={priorities.join("-")}
              priorities={priorities}
              status={status}
              timeGrain={timeGrain}
              title={`${valueTicketType === "incident" ? "Incident" : "SC Task"} ${priorities.join(
                " / "
              )} MTTR`}
              commentary={commentaryForChart(
                `${valueTicketType}_${priorities.join("_").toLowerCase()}_mttr`
              )}
            />
          ))}
        </div>
      )}
    </section>
  );
}

function mttrCombinedRows(
  data: DashboardVolumetricsKpiMttrPrioritySet,
  priorities: Array<keyof DashboardVolumetricsKpiMttrPrioritySet>
) {
  const baseRows = data[priorities[0]] ?? [];
  return baseRows.map((point, index) => {
    const row: Record<string, string | number | null> = {
      period_key: point.period_key,
      period_label: point.period_label,
    };
    priorities.forEach((priority) => {
      const priorityPoint = data[priority]?.[index];
      row[`${priority}_mttr`] = priorityPoint?.average_mttr_days ?? null;
      row[`${priority}_ticket_count`] = priorityPoint?.ticket_count ?? 0;
      row[`${priority}_label_text`] = priorityPoint?.show_label
        ? priorityPoint.label_text ?? null
        : null;
    });
    return row;
  });
}

function renderMttrPointLabel(props: {
  x?: number | string;
  y?: number | string;
  value?: unknown;
  verticalOffset: number;
}) {
  if (typeof props.value !== "string" && typeof props.value !== "number") {
    return null;
  }
  const x = Number(props.x ?? 0);
  const y = Number(props.y ?? 0) + props.verticalOffset;
  const lines = String(props.value).split("\n");
  return (
    <text
      x={x}
      y={y}
      textAnchor="middle"
      fontSize={10}
      fontWeight={800}
      fill="#334155"
      stroke="#ffffff"
      strokeWidth={3}
      paintOrder="stroke"
    >
      {lines.map((line, index) => (
        <tspan key={line} x={x} dy={index === 0 ? 0 : 12}>
          {line}
        </tspan>
      ))}
    </text>
  );
}

function MttrCombinedLineChart({
  commentary,
  data,
  priorities,
  status,
  timeGrain,
  title,
}: {
  commentary?: ReactNode;
  data: DashboardVolumetricsKpiMttrPrioritySet;
  priorities: Array<keyof DashboardVolumetricsKpiMttrPrioritySet>;
  status: LoadStatus;
  timeGrain: VolumetricsTimeGrain;
  title: string;
}) {
  const { chartRef, copyMessage, handleCopy, plotWidth } = useChartFrame(title);
  const rows = mttrCombinedRows(data, priorities);
  const hasValues = priorities.some((priority) =>
    data[priority].some((point) => point.average_mttr_days !== null)
  );
  const chartWidth = trendChartWidth(rows.length, timeGrain, plotWidth);
  const canCopy = status !== "loading" && hasValues;

  return (
    <section className="chart-card volumetrics-chart-card" aria-label={title}>
      <div className="applications-chart-header">
        <div>
          <h3>{title}</h3>
          <p className="muted-text">Average business duration in days.</p>
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
      {status !== "loading" && !hasValues ? (
        <p className="muted-text chart-state-text">No MTTR data available.</p>
      ) : null}

      {status !== "loading" && hasValues ? (
        <div className="applications-chart-plot volumetrics-chart-plot" ref={chartRef}>
          <div className="applications-chart-scroll">
            <div className="applications-chart-stage">
              <ComposedChart
                data={rows}
                width={chartWidth}
                height={320}
                margin={{ top: 46, right: 52, bottom: 76, left: 58 }}
              >
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis
                  dataKey="period_label"
                  angle={-35}
                  height={78}
                  interval={0}
                  textAnchor="end"
                  tickMargin={12}
                />
                <YAxis
                  label={{ value: "MTTR days", angle: -90, position: "insideLeft" }}
                  tickFormatter={(value) => formatNumber(Number(value), 1)}
                />
                <Tooltip
                  formatter={(value, name, item) => {
                    const priority = String(item.dataKey ?? "").replace("_mttr", "");
                    const count = item.payload?.[`${priority}_ticket_count`] ?? 0;
                    return [`${formatNumber(Number(value), 2)} days (n=${count})`, name];
                  }}
                />
                <Legend />
                {priorities.map((priority, index) => (
                  <Line
                    connectNulls
                    dataKey={`${priority}_mttr`}
                    dot={{ r: 3 }}
                    key={priority}
                    name={`${priority} MTTR`}
                    stroke={chartColors.priority[mttrPriorityKeys.indexOf(priority)]}
                    strokeWidth={2.5}
                    type="monotone"
                  >
                    <LabelList
                      content={(props) =>
                        renderMttrPointLabel({
                          ...props,
                          verticalOffset: index === 0 ? -14 : 24,
                        })
                      }
                      dataKey={`${priority}_label_text`}
                    />
                  </Line>
                ))}
              </ComposedChart>
            </div>
          </div>
        </div>
      ) : null}

      {copyMessage ? <p className="chart-copy-status">{copyMessage}</p> : null}
      {commentary}
    </section>
  );
}

function DurationBucketGroup({
  commentary,
  data,
  error,
  selectedTicketType,
  status,
  title,
  valueTicketType,
}: {
  commentary: ReactNode;
  data: DashboardVolumetricsDurationBucketRow[];
  error: string | null;
  selectedTicketType: VolumetricsTicketType;
  status: LoadStatus;
  title: string;
  valueTicketType: Exclude<VolumetricsTicketType, "all">;
}) {
  const notApplicable = splitChartNotApplicable(selectedTicketType, valueTicketType);
  return (
    <section className="panel kpi-trends-section">
      <div className="panel-heading">
        <div>
          <p className="label">Duration Buckets</p>
          <h3>{title}</h3>
        </div>
      </div>
      {status === "error" ? <p className="error-text">{error}</p> : null}
      {notApplicable ? (
        <p className="muted-text chart-state-text">
          This duration group is not applicable for the selected ticket type.
        </p>
      ) : (
        <>
          <div className="duration-bucket-grid">
            {data.map((row) => (
              <DurationBucketChart data={row} key={row.period_key} status={status} />
            ))}
          </div>
          {commentary}
        </>
      )}
    </section>
  );
}

function DurationBucketChart({
  data,
  status,
}: {
  data: DashboardVolumetricsDurationBucketRow;
  status: LoadStatus;
}) {
  const title = data.period_label;
  const { chartRef, copyMessage, handleCopy, plotWidth } = useChartFrame(title);
  const rows = durationBucketLabels.map((bucket) => ({
    bucket,
    count: data.buckets[bucket] ?? 0,
  }));
  const hasValues = rows.some((row) => row.count > 0);
  const chartWidth = Math.max(320, plotWidth - 24);
  const canCopy = status !== "loading" && hasValues;

  return (
    <section className="chart-card volumetrics-chart-card" aria-label={title}>
      <div className="applications-chart-header">
        <h3>{title}</h3>
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
      {status !== "loading" && !hasValues ? (
        <p className="muted-text chart-state-text">No duration data available.</p>
      ) : null}
      {status !== "loading" && hasValues ? (
        <div className="applications-chart-plot volumetrics-chart-plot" ref={chartRef}>
          <div className="applications-chart-stage">
            <BarChart
              data={rows}
              width={chartWidth}
              height={280}
              margin={{ top: 36, right: 24, bottom: 68, left: 24 }}
              barCategoryGap="18%"
            >
              <CartesianGrid strokeDasharray="3 3" vertical={false} />
              <XAxis
                dataKey="bucket"
                angle={-25}
                height={66}
                interval={0}
                textAnchor="end"
                tick={{ fontSize: 12, fontWeight: 700 }}
              />
              <YAxis hide />
              <Tooltip />
              <Bar
                barSize={44}
                dataKey="count"
                fill={chartColors.patternAlt}
                name="Tickets"
                radius={[4, 4, 0, 0]}
              >
                <LabelList dataKey="count" position="top" fontSize={13} fontWeight={800} />
              </Bar>
            </BarChart>
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
  commentary,
  data,
  error,
  status,
  ticketType,
  timeGrain,
}: {
  commentary?: ReactNode;
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
      {commentary}
    </section>
  );
}

function BacklogChart({
  commentary,
  data,
  error,
  status,
  timeGrain,
}: {
  commentary?: ReactNode;
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
      {commentary}
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
  commentary,
  data,
  error,
  onPatternTypeChange,
  patternType,
  status,
}: {
  commentary?: ReactNode;
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
      {commentary}
    </section>
  );
}

const hourlyDayTypeOptions: Array<{ value: VolumetricsDayType; label: string }> = [
  { value: "weekdays", label: "Weekdays" },
  { value: "weekends", label: "Weekends" },
];

function HourlyCreatedResolvedChart({
  commentary,
  data,
  dayType,
  error,
  onDayTypeChange,
  status,
  ticketType,
}: {
  commentary?: ReactNode;
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
      {commentary}
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
      const count = point.values[item.label] ?? 0;
      const percentage =
        point.percentages[item.label] ?? (point.total > 0 ? (count / point.total) * 100 : 0);
      row[item.key] = count;
      row[`${item.key}_pct`] = percentage;
      row[`${item.key}_label`] = priorityChartLabel(count, percentage);
    });
    return row;
  });
  return { points, series };
}

function priorityRank(label: string): number | null {
  const normalized = label.toLowerCase();
  const pMatch = normalized.match(/\bp\s*([1-4])\b/);
  if (pMatch) {
    return Number(pMatch[1]);
  }
  const digitMatch = normalized.match(/\b([1-4])\b/);
  if (digitMatch) {
    return Number(digitMatch[1]);
  }
  if (normalized.includes("moderate") || normalized.includes("medium")) {
    return 3;
  }
  if (normalized.includes("low")) {
    return 4;
  }
  if (normalized.includes("critical")) {
    return 1;
  }
  if (normalized.includes("high")) {
    return 2;
  }
  return null;
}

function priorityLabelRequired(label: string): boolean {
  const rank = priorityRank(label);
  return rank === 3 || rank === 4;
}

function priorityCountPercentageLabel(count: number, percentage: number | null | undefined): string {
  const pctValue = Number.isFinite(Number(percentage)) ? Number(percentage) : 0;
  return `${formatNumber(count)} (${pctValue.toFixed(1)}%)`;
}

function priorityChartLabel(count: number, percentage: number | null | undefined): string {
  const pctValue = Number.isFinite(Number(percentage)) ? Number(percentage) : 0;
  return `${formatNumber(count)}\n${Math.round(pctValue)}%`;
}

function renderPriorityStackLabel(props: {
  height?: number | string;
  value?: unknown;
  width?: number | string;
  x?: number | string;
  y?: number | string;
}) {
  if (typeof props.value !== "string" || !props.value.trim()) {
    return null;
  }
  const x = Number(props.x ?? 0);
  const y = Number(props.y ?? 0);
  const width = Number(props.width ?? 0);
  const height = Number(props.height ?? 0);
  if (width <= 0 || height <= 0) {
    return null;
  }
  const lines = props.value.split("\n").filter(Boolean).slice(0, 2);
  const labelFontSize = 9;
  const lineHeight = 10;
  const inside = height >= 28 && width >= 20;
  const labelY = inside
    ? y + height / 2 - (lines.length - 1) * (lineHeight / 2)
    : Math.max(24, y - 16);
  return (
    <text
      x={x + width / 2}
      y={labelY}
      textAnchor="middle"
      fontSize={labelFontSize}
      fontWeight={800}
      fill={inside ? "#ffffff" : "#334155"}
      stroke={inside ? "none" : "#ffffff"}
      strokeWidth={inside ? 0 : 3}
      paintOrder="stroke"
    >
      {lines.map((line, index) => (
        <tspan key={`${line}-${index}`} x={x + width / 2} dy={index === 0 ? 0 : lineHeight}>
          {line}
        </tspan>
      ))}
    </text>
  );
}

function PriorityDistributionChart({
  commentary,
  data,
  error,
  onViewChange,
  status,
  timeGrain,
  view,
}: {
  commentary?: ReactNode;
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
                  >
                    {priorityLabelRequired(item.label) ? (
                      <LabelList
                        content={renderPriorityStackLabel}
                        dataKey={`${item.key}_label`}
                      />
                    ) : null}
                  </Bar>
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
      {commentary}
    </section>
  );
}

function priorityCellText(
  point: DashboardVolumetricsPriorityDistributionPoint,
  priority: string
): string {
  const count = point.values[priority] ?? 0;
  const percentage =
    point.percentages[priority] ?? (point.total > 0 ? (count / point.total) * 100 : 0);
  return priorityCountPercentageLabel(count, percentage);
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
                <td key={priority}>{priorityCellText(point, priority)}</td>
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
  agreementMode,
  commentaryForChart,
  data,
  error,
  onAgreementModeChange,
  status,
  ticketType,
  timeGrain,
}: {
  agreementMode: VolumetricsAgreementMode;
  commentaryForChart: (chartKey: string) => ReactNode;
  data: DashboardVolumetricsSlaTrends;
  error: string | null;
  onAgreementModeChange: (value: VolumetricsAgreementMode) => void;
  status: LoadStatus;
  ticketType: VolumetricsTicketType;
  timeGrain: VolumetricsTimeGrain;
}) {
  const agreementLabel = agreementMode === "ola" ? "OLA" : "SLA";
  if (ticketType === "sc_task" || data.not_applicable) {
    return (
      <section className="panel volumetrics-placeholder-panel">
        <p className="label">Overall SLA Trends</p>
        <h3>{agreementLabel} trends are not applicable for SC Tasks.</h3>
      </section>
    );
  }

  return (
    <>
      {status === "error" ? <p className="error-text">{error}</p> : null}
      <section className="panel compact-panel">
        <div className="applications-chart-header">
          <div>
            <p className="label">Overall SLA Trends</p>
            <h3>Agreement Mode</h3>
          </div>
          <div className="segmented-control" role="group" aria-label="Agreement mode">
            {(["sla", "ola"] as VolumetricsAgreementMode[]).map((mode) => (
              <button
                className={agreementMode === mode ? "active" : ""}
                key={mode}
                type="button"
                onClick={() => onAgreementModeChange(mode)}
              >
                {mode.toUpperCase()}
              </button>
            ))}
          </div>
        </div>
      </section>
      <SlaTrendSection
        title={`Response ${agreementLabel} adherence trend`}
        tableMetricLabel={`Response ${agreementLabel}`}
        data={data.response}
        status={status}
        timeGrain={timeGrain}
        color={chartColors.created}
        commentary={commentaryForChart("response_sla_adherence")}
      />
      <SlaTrendSection
        title={`Resolution ${agreementLabel} adherence trend`}
        tableMetricLabel={`Resolution ${agreementLabel}`}
        data={data.resolution}
        status={status}
        timeGrain={timeGrain}
        color={chartColors.resolved}
        commentary={commentaryForChart("resolution_sla_adherence")}
      />
    </>
  );
}

function SlaTrendSection({
  commentary,
  color,
  data,
  status,
  tableMetricLabel,
  timeGrain,
  title,
}: {
  commentary?: ReactNode;
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
            Adherence is calculated as {tableMetricLabel} adhered count divided by{" "}
            {tableMetricLabel} captured count.
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
      {commentary}
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
