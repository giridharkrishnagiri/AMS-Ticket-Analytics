import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  LabelList,
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
  getDashboardApplicationsAssignmentGroupMapping,
  getDashboardApplicationsCharts,
  getDashboardFilterCatalog,
  getDashboardFilterCounts,
  getDashboardApplicationsLifecyclePlanning,
  getDashboardApplicationsList,
  getDashboardApplicationsSummary,
  getDashboardApplicationsTopActiveUsers,
} from "./api/dashboard";
import type {
  ApplicationsAssignmentGroupMappingScope,
  ApplicationsAssignmentGroupMappingSource,
  DashboardApplicationRow,
  DashboardApplicationsAssignmentGroupMapping,
  DashboardApplicationsAssignmentGroupMappingRow,
  DashboardApplicationsCharts,
  DashboardApplicationsFilters,
  DashboardApplicationsFilterValues,
  DashboardFilterCatalogResponse,
  DashboardFilterCountsResponse,
  DashboardApplicationsLifecycleApplication,
  DashboardApplicationsLifecyclePlan,
  DashboardApplicationsLifecyclePlanning,
  DashboardApplicationsList,
  DashboardApplicationsRequest,
  DashboardApplicationsSort,
  DashboardApplicationsSummary,
  DashboardApplicationsTopActiveUsers,
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

type ApplicationsDashboardProps = {
  customerId: string;
  projectId: string;
  isActive: boolean;
  onExportContextChange?: (context: { functionalTrackAmsOwners: string[] }) => void;
};

type TopNSelection = 10 | 20;
type FilterKey = keyof DashboardApplicationsFilters;
type TableColumnKey = keyof DashboardApplicationRow;
type ApplicationsSubTab = "overview" | "lifecycle_planning" | "assignment_group_mapping";
type AssignmentMappingSortKey =
  | keyof DashboardApplicationsAssignmentGroupMappingRow
  | "incident_count"
  | "sc_task_count"
  | "total_ticket_count";

const emptyFilters: DashboardApplicationsFilters = {
  application_scope: [],
  functional_track_ams_owner: [],
  assignment_group_owner: [],
  parent_application_name: [],
  application_owner: [],
  supported_by_vendor: [],
  sap_non_sap: [],
  architecture_type: [],
  application_type: [],
  business_critical: [],
  install_status: [],
  install_type: [],
  hosting_env: [],
  lifecycle_status_stage: [],
};

const emptyFilterValues: DashboardApplicationsFilterValues = {
  application_scope: [],
  functional_track_ams_owner: [],
  assignment_group_owner: [],
  parent_application_name: [],
  application_owner: [],
  supported_by_vendor: [],
  sap_non_sap: [],
  architecture_type: [],
  application_type: [],
  business_critical: [],
  install_status: [],
  install_type: [],
  hosting_env: [],
  lifecycle_status_stage: [],
};

const emptySummary: DashboardApplicationsSummary = {
  applications: 0,
  functional_groups: 0,
  assignment_groups: 0,
  parent_business_apps: 0,
  business_applications: 0,
  technical_applications: 0,
  very_critical_applications: 0,
  critical_applications: 0,
  show_functional_groups: true,
  show_assignment_groups: true,
  show_parent_business_apps: true,
};

const emptyList: DashboardApplicationsList = {
  total: 0,
  rows: [],
};

const emptyCharts: DashboardApplicationsCharts = {
  lifecycle_stage: [],
  architecture_type: [],
  install_type: [],
  hosting_env: [],
  strategic: [],
  global_local_applications: [],
  criticality_hosting_pivot: {
    rows: [],
    columns: [],
    values: [],
    column_totals: {},
    grand_total: 0,
  },
};

const emptyTopActiveUsers: DashboardApplicationsTopActiveUsers = {
  top_n: 10,
  duplicate_parent_active_user_count: 0,
  points: [],
};

const lifecyclePlans: DashboardApplicationsLifecyclePlan[] = [
  "Invest",
  "Disinvest",
  "Maintain",
  "Retired",
];

const lifecyclePlanLineColors: Record<DashboardApplicationsLifecyclePlan, string> = {
  Invest: "#0f766e",
  Disinvest: "#991b1b",
  Maintain: "#1d4ed8",
  Retired: "#581c87",
};

const emptyLifecyclePlanning: DashboardApplicationsLifecyclePlanning = {
  matrix: {
    plans: lifecyclePlans,
    horizons: ["Current", "1 to 3 years", "3 to 5 years"],
    rows: lifecyclePlans.map((plan) => ({
      plan,
      counts: {
        Current: 0,
        "1 to 3 years": 0,
        "3 to 5 years": 0,
      },
    })),
    in_use_application_count: 0,
  },
  selected_plan: {
    plan: "Invest",
    chart: [
      { horizon: "Current", count: 0 },
      { horizon: "1 to 3 years", count: 0 },
      { horizon: "3 to 5 years", count: 0 },
    ],
    applications: [],
    application_count: 0,
  },
};

const emptyAssignmentGroupMapping: DashboardApplicationsAssignmentGroupMapping = {
  source: "application_inventory",
  scope: "in_scope",
  functional_track: "all",
  available_functional_tracks: [],
  summary: {
    mapping_count: 0,
    assignment_group_count: 0,
    business_service_ci_count: 0,
    parent_business_application_count: 0,
    basis_security_mapping_count: 0,
    incident_count: null,
    sc_task_count: null,
    total_ticket_count: null,
  },
  rows: [],
  basis_security_rows: [],
  volume_period: null,
  data_notes: [],
  warnings: [],
};

const defaultSort: DashboardApplicationsSort = {
  column: "business_service_ci_name",
  direction: "asc",
};

const tableColumns: Array<{ key: TableColumnKey; label: string }> = [
  { key: "business_service_ci_name", label: "Business Service CI Name (Application)" },
  { key: "scope_status", label: "Application Scope" },
  { key: "parent_application_name", label: "Parent Business Application" },
  { key: "assignment_group", label: "Assignment Group" },
  { key: "sap_non_sap", label: "SAP / Non-SAP" },
  { key: "assignment_group_owner", label: "Group Owner" },
  { key: "application_owner", label: "App Owner" },
  { key: "support_lead", label: "Support Lead" },
  { key: "functional_track", label: "Functional Track" },
  { key: "ams_owner", label: "AMS Owner" },
  { key: "supported_by_vendor", label: "Supported By Vendor" },
  { key: "hosting_env", label: "Hosting Env" },
  { key: "global_application", label: "Global" },
  { key: "lifecycle_stage_status", label: "Lifecycle Stage Status" },
  { key: "lifecycle_current", label: "Lifecycle - Current" },
  { key: "lifecycle_1_to_3_years", label: "Lifecycle - 1 to 3 years" },
  { key: "lifecycle_3_to_5_years", label: "Lifecycle - 3 to 5 years" },
  { key: "active_users", label: "Active Users" },
  { key: "app_family", label: "App Family" },
  { key: "biz_process", label: "Biz Process" },
  { key: "app_category", label: "App Category" },
  { key: "org_unit_level_1", label: "Org Unit Level 1" },
  { key: "org_unit_level_2", label: "Org Unit Level 2" },
  { key: "org_unit_level_3", label: "Org Unit Level 3" },
  { key: "app_type", label: "App Type" },
  { key: "architecture_type", label: "Architecture Type" },
  { key: "biz_capabilities", label: "Biz Capabilities" },
  {
    key: "business_reason_for_maintain_applications",
    label: "Business Reason for Maintain Applications",
  },
  { key: "business_units", label: "Business Units" },
  { key: "biz_criticality", label: "Biz Criticality" },
  { key: "biz_owner", label: "Biz Owner" },
  { key: "company", label: "Company" },
  { key: "install_status", label: "Install Status" },
  { key: "install_type", label: "Install Type" },
  { key: "lifecycle_status", label: "Lifecycle Status" },
  { key: "operating_system", label: "Operating System" },
  { key: "sox_audited", label: "SOX Audited" },
  { key: "sox_scope", label: "SOX Scope" },
  { key: "strategic", label: "Strategic" },
];

const chartColors = [
  "#2563eb",
  "#16a34a",
  "#d97706",
  "#7c3aed",
  "#0891b2",
  "#dc2626",
  "#475569",
  "#0f766e",
];
const chartImagePadding = 18;
const chartImageHeaderMinHeight = 54;

function createLoadState<T>(data: T, status: LoadStatus = "idle"): LoadState<T> {
  return { status, data, error: null };
}

function summaryTileToneClass(index: number, columns: number): string {
  const row = Math.floor(index / columns);
  const column = index % columns;
  return (row + column) % 2 === 0 ? "summary-tile-dark" : "summary-tile-light";
}

function formatNumber(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "Not available";
  }
  return value.toLocaleString();
}

function formatTableValue(row: DashboardApplicationRow, column: TableColumnKey): string {
  const value = row[column];
  if (column === "scope_status") {
    if (value === "in_scope") {
      return "In Scope";
    }
    if (value === "out_of_scope") {
      return "Out of Scope";
    }
  }
  if (column === "active_users") {
    return typeof value === "number" ? value.toLocaleString() : "";
  }
  if (column === "avg_monthly_ticket_volume_6m") {
    return typeof value === "number" ? value.toLocaleString(undefined, { maximumFractionDigits: 1 }) : "";
  }
  if (column === "tickets_per_user_per_month") {
    return typeof value === "number" ? value.toLocaleString(undefined, { maximumFractionDigits: 2 }) : "";
  }
  return value === null || value === undefined ? "" : String(value);
}

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

function filtersEqual(left: DashboardApplicationsFilters, right: DashboardApplicationsFilters) {
  return JSON.stringify(left) === JSON.stringify(right);
}

function commentaryFunctionalContext(values: string[]): string {
  return values.length === 1 ? values[0] : "all";
}

function lifecyclePlanCommentaryKey(plan: DashboardApplicationsLifecyclePlan): string {
  return `applications_lifecycle_plan_${plan.toLowerCase()}`;
}

function lifecyclePlanTitle(plan: DashboardApplicationsLifecyclePlan): string {
  return plan === "Retired"
    ? "Applications Planned to Retire"
    : `Applications Planned to ${plan}`;
}

function formatCellValue(value: string | number | null | undefined): string {
  if (typeof value === "number") {
    return value.toLocaleString();
  }
  return value === null || value === undefined ? "" : String(value);
}

function tableCellText(value: string | number | null | undefined): string {
  if (typeof value === "number") {
    return String(value);
  }
  return value === null || value === undefined ? "" : String(value);
}

function csvCell(value: string | number | null | undefined): string {
  const text = tableCellText(value);
  return /[",\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

async function copyTextToClipboard(text: string): Promise<void> {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text);
    return;
  }
  const textArea = document.createElement("textarea");
  textArea.value = text;
  textArea.setAttribute("readonly", "");
  textArea.style.position = "fixed";
  textArea.style.left = "-9999px";
  document.body.append(textArea);
  textArea.select();
  document.execCommand("copy");
  textArea.remove();
}

function downloadCsv(filename: string, headers: string[], rows: Array<Array<string | number | null>>) {
  const csv = [headers, ...rows].map((row) => row.map(csvCell).join(",")).join("\r\n");
  downloadBlob(new Blob([csv], { type: "text/csv;charset=utf-8" }), filename);
}

function combinedFilterOptions(
  values: DashboardApplicationsFilterValues["functional_track_ams_owner"]
): ExcelFilterOption[] {
  return values.map((value) => ({
    value: value.label,
    label: value.label,
    count: value.count,
  }));
}

function singleFilterOptions(values: Array<{ label: string; value: string; count: number }>) {
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
  filterKey: keyof DashboardApplicationsFilterValues,
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
  filterKey: keyof DashboardApplicationsFilterValues,
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

function applicationFilterValuesFromCatalog(
  catalog: DashboardFilterCatalogResponse | null,
  counts: DashboardFilterCountsResponse | null,
  selectedFilters: DashboardApplicationsFilters
): DashboardApplicationsFilterValues {
  return {
    application_scope: catalogSingleRows(
      catalog,
      counts,
      "application_scope",
      selectedFilters.application_scope
    ),
    functional_track_ams_owner: catalogCombinedRows(
      catalog,
      counts,
      "functional_track_ams_owner",
      selectedFilters.functional_track_ams_owner
    ),
    assignment_group_owner: catalogCombinedRows(
      catalog,
      counts,
      "assignment_group_owner",
      selectedFilters.assignment_group_owner
    ),
    parent_application_name: catalogSingleRows(
      catalog,
      counts,
      "parent_application_name",
      selectedFilters.parent_application_name
    ),
    application_owner: catalogSingleRows(
      catalog,
      counts,
      "application_owner",
      selectedFilters.application_owner
    ),
    supported_by_vendor: catalogSingleRows(
      catalog,
      counts,
      "supported_by_vendor",
      selectedFilters.supported_by_vendor
    ),
    sap_non_sap: catalogSingleRows(catalog, counts, "sap_non_sap", selectedFilters.sap_non_sap),
    architecture_type: catalogSingleRows(
      catalog,
      counts,
      "architecture_type",
      selectedFilters.architecture_type
    ),
    application_type: catalogSingleRows(
      catalog,
      counts,
      "application_type",
      selectedFilters.application_type
    ),
    business_critical: catalogSingleRows(
      catalog,
      counts,
      "business_critical",
      selectedFilters.business_critical
    ),
    install_status: catalogSingleRows(
      catalog,
      counts,
      "install_status",
      selectedFilters.install_status
    ),
    install_type: catalogSingleRows(catalog, counts, "install_type", selectedFilters.install_type),
    hosting_env: catalogSingleRows(catalog, counts, "hosting_env", selectedFilters.hosting_env),
    lifecycle_status_stage: catalogCombinedRows(
      catalog,
      counts,
      "lifecycle_status_stage",
      selectedFilters.lifecycle_status_stage
    ),
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

function useChartCopy(title: string) {
  const chartRef = useRef<HTMLDivElement>(null);
  const [copyMessage, setCopyMessage] = useState<string | null>(null);
  const [plotWidth, setPlotWidth] = useState(0);

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
  });

  const handleCopy = useCallback(async () => {
    if (!chartRef.current) {
      return;
    }
    try {
      setCopyMessage(await copyChartToClipboard(chartRef.current, title));
    } catch (error) {
      setCopyMessage(errorMessage(error, "This browser could not copy the chart image."));
    }
  }, [title]);

  return { chartRef, copyMessage, handleCopy, plotWidth };
}

function ApplicationsDashboard({
  customerId,
  projectId,
  isActive,
  onExportContextChange,
}: ApplicationsDashboardProps) {
  const [filters, setFilters] = useState<DashboardApplicationsFilters>(emptyFilters);
  const [sort, setSort] = useState<DashboardApplicationsSort>(defaultSort);
  const [filterValues, setFilterValues] = useState<LoadState<DashboardApplicationsFilterValues>>(
    createLoadState(emptyFilterValues)
  );
  const [filterCatalog, setFilterCatalog] = useState<DashboardFilterCatalogResponse | null>(null);
  const [filterCounts, setFilterCounts] = useState<DashboardFilterCountsResponse | null>(null);
  const filterCountsRequestRef = useRef(0);
  const [summary, setSummary] = useState<LoadState<DashboardApplicationsSummary>>(
    createLoadState(emptySummary)
  );
  const [applicationList, setApplicationList] = useState<LoadState<DashboardApplicationsList>>(
    createLoadState(emptyList)
  );
  const [charts, setCharts] = useState<LoadState<DashboardApplicationsCharts>>(
    createLoadState(emptyCharts)
  );
  const [topActiveUsersN, setTopActiveUsersN] = useState<TopNSelection>(10);
  const [topActiveUsers, setTopActiveUsers] = useState<
    LoadState<DashboardApplicationsTopActiveUsers>
  >(createLoadState(emptyTopActiveUsers));
  const [activeSubTab, setActiveSubTab] = useState<ApplicationsSubTab>("overview");
  const [selectedLifecyclePlan, setSelectedLifecyclePlan] =
    useState<DashboardApplicationsLifecyclePlan>("Invest");
  const [lifecyclePlanning, setLifecyclePlanning] = useState<
    LoadState<DashboardApplicationsLifecyclePlanning>
  >(createLoadState(emptyLifecyclePlanning));
  const [assignmentMappingSource, setAssignmentMappingSource] =
    useState<ApplicationsAssignmentGroupMappingSource>("application_inventory");
  const [assignmentMappingScope, setAssignmentMappingScope] =
    useState<ApplicationsAssignmentGroupMappingScope>("in_scope");
  const [assignmentMappingTrack, setAssignmentMappingTrack] = useState("all");
  const [assignmentMappingSearch, setAssignmentMappingSearch] = useState("");
  const [assignmentMappingSort, setAssignmentMappingSort] = useState<{
    column: AssignmentMappingSortKey;
    direction: "asc" | "desc";
  }>({ column: "assignment_group", direction: "asc" });
  const [assignmentMapping, setAssignmentMapping] = useState<
    LoadState<DashboardApplicationsAssignmentGroupMapping>
  >(createLoadState(emptyAssignmentGroupMapping));
  const [loadedProjectId, setLoadedProjectId] = useState("");

  const filterOptions = useMemo(
    () => ({
      application_scope: singleFilterOptions(filterValues.data.application_scope),
      functional_track_ams_owner: combinedFilterOptions(
        filterValues.data.functional_track_ams_owner
      ),
      assignment_group_owner: combinedFilterOptions(filterValues.data.assignment_group_owner),
      parent_application_name: singleFilterOptions(filterValues.data.parent_application_name),
      application_owner: singleFilterOptions(filterValues.data.application_owner),
      supported_by_vendor: singleFilterOptions(filterValues.data.supported_by_vendor),
      sap_non_sap: singleFilterOptions(filterValues.data.sap_non_sap),
      architecture_type: singleFilterOptions(filterValues.data.architecture_type),
      application_type: singleFilterOptions(filterValues.data.application_type),
      business_critical: singleFilterOptions(filterValues.data.business_critical),
      install_status: singleFilterOptions(filterValues.data.install_status),
      install_type: singleFilterOptions(filterValues.data.install_type),
      hosting_env: singleFilterOptions(filterValues.data.hosting_env),
      lifecycle_status_stage: combinedFilterOptions(filterValues.data.lifecycle_status_stage),
    }),
    [filterValues.data]
  );

  const requestBody = useMemo<DashboardApplicationsRequest | null>(() => {
    const cleanedProjectId = projectId.trim();
    if (!cleanedProjectId) {
      return null;
    }
    return {
      project_id: cleanedProjectId,
      filters,
      sort,
      limit: 1000,
      offset: 0,
    };
  }, [filters, projectId, sort]);

  const requestSignature = useMemo(
    () => (requestBody ? JSON.stringify(requestBody) : ""),
    [requestBody]
  );
  const hasActiveProjectContext = Boolean(projectId.trim()) && projectId === loadedProjectId;
  const hasFilterCacheContext = Boolean(customerId.trim()) && Boolean(projectId.trim());

  useEffect(() => {
    onExportContextChange?.({
      functionalTrackAmsOwners: filters.functional_track_ams_owner,
    });
  }, [filters.functional_track_ams_owner, onExportContextChange]);

  const loadFilterCatalog = useCallback(async () => {
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
        "applications"
      );
      setFilterCatalog(catalog);
      setFilterCounts(null);
      setFilterValues({
        status: "success",
        data: applicationFilterValuesFromCatalog(catalog, null, filters),
        error: catalog.warnings[0] ?? null,
      });
    } catch (error) {
      setFilterValues((currentFilterValues) => ({
        status: "error",
        data: currentFilterValues.data,
        error: errorMessage(error, "Unable to load Application filters"),
      }));
    }
  }, [customerId, filters, projectId]);

  const loadFilterCounts = useCallback(async () => {
    const cleanedCustomerId = customerId.trim();
    const cleanedProjectId = projectId.trim();
    if (!cleanedCustomerId || !cleanedProjectId || !filterCatalog) {
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
        dashboard_area: "applications",
        selected_filters: filters,
      });
      if (filterCountsRequestRef.current !== requestId) {
        return;
      }
      setFilterCounts(counts);
      setFilterValues({
        status: "success",
        data: applicationFilterValuesFromCatalog(filterCatalog, counts, filters),
        error: null,
      });
    } catch (error) {
      if (filterCountsRequestRef.current !== requestId) {
        return;
      }
      setFilterValues((currentFilterValues) => ({
        status: "error",
        data: currentFilterValues.data,
        error: errorMessage(error, "Unable to update Application filter counts"),
      }));
    }
  }, [customerId, filterCatalog, filters, projectId]);

  const loadApplicationsData = useCallback(async () => {
    if (!requestBody) {
      return;
    }
    setSummary(createLoadState(emptySummary, "loading"));
    setApplicationList(createLoadState(emptyList, "loading"));
    setCharts(createLoadState(emptyCharts, "loading"));
    setTopActiveUsers(createLoadState(emptyTopActiveUsers, "loading"));
    try {
      const [nextSummary, nextList, nextCharts, nextTopActiveUsers] = await Promise.all([
        getDashboardApplicationsSummary(requestBody),
        getDashboardApplicationsList(requestBody),
        getDashboardApplicationsCharts(requestBody),
        getDashboardApplicationsTopActiveUsers(requestBody, topActiveUsersN),
      ]);
      setSummary({ status: "success", data: nextSummary, error: null });
      setApplicationList({ status: "success", data: nextList, error: null });
      setCharts({ status: "success", data: nextCharts, error: null });
      setTopActiveUsers({ status: "success", data: nextTopActiveUsers, error: null });
    } catch (error) {
      const message = errorMessage(error, "Unable to load Application dashboard data");
      setSummary({ status: "error", data: emptySummary, error: message });
      setApplicationList({ status: "error", data: emptyList, error: message });
      setCharts({ status: "error", data: emptyCharts, error: message });
      setTopActiveUsers({ status: "error", data: emptyTopActiveUsers, error: message });
    }
  }, [requestBody, topActiveUsersN]);

  const loadLifecyclePlanningData = useCallback(async () => {
    if (!requestBody) {
      return;
    }
    setLifecyclePlanning(createLoadState(emptyLifecyclePlanning, "loading"));
    try {
      const nextLifecyclePlanning = await getDashboardApplicationsLifecyclePlanning(
        requestBody,
        selectedLifecyclePlan
      );
      setLifecyclePlanning({
        status: "success",
        data: nextLifecyclePlanning,
        error: null,
      });
    } catch (error) {
      setLifecyclePlanning({
        status: "error",
        data: emptyLifecyclePlanning,
        error: errorMessage(error, "Unable to load lifecycle planning data"),
      });
    }
  }, [requestBody, selectedLifecyclePlan]);

  const loadAssignmentGroupMapping = useCallback(async () => {
    const cleanedProjectId = projectId.trim();
    if (!cleanedProjectId) {
      return;
    }
    setAssignmentMapping((current) => ({
      status: "loading",
      data: current.data,
      error: null,
    }));
    try {
      const nextMapping = await getDashboardApplicationsAssignmentGroupMapping({
        project_id: cleanedProjectId,
        source: assignmentMappingSource,
        scope: assignmentMappingScope,
        functional_track: assignmentMappingTrack,
        search: null,
      });
      setAssignmentMapping({
        status: "success",
        data: nextMapping,
        error: nextMapping.warnings[0] ?? null,
      });
      if (
        assignmentMappingTrack !== "all" &&
        !nextMapping.available_functional_tracks.includes(assignmentMappingTrack)
      ) {
        setAssignmentMappingTrack("all");
      }
    } catch (error) {
      setAssignmentMapping({
        status: "error",
        data: emptyAssignmentGroupMapping,
        error: errorMessage(error, "Unable to load assignment group mapping"),
      });
    }
  }, [
    assignmentMappingScope,
    assignmentMappingSource,
    assignmentMappingTrack,
    projectId,
  ]);

  useEffect(() => {
    if (projectId !== loadedProjectId) {
      setLoadedProjectId(projectId);
      setFilters(emptyFilters);
      setSort(defaultSort);
      setFilterValues(createLoadState(emptyFilterValues));
      setFilterCatalog(null);
      setFilterCounts(null);
      filterCountsRequestRef.current = 0;
      setSummary(createLoadState(emptySummary));
      setApplicationList(createLoadState(emptyList));
      setCharts(createLoadState(emptyCharts));
      setTopActiveUsersN(10);
      setTopActiveUsers(createLoadState(emptyTopActiveUsers));
      setActiveSubTab("overview");
      setSelectedLifecyclePlan("Invest");
      setLifecyclePlanning(createLoadState(emptyLifecyclePlanning));
      setAssignmentMappingSource("application_inventory");
      setAssignmentMappingScope("in_scope");
      setAssignmentMappingTrack("all");
      setAssignmentMappingSearch("");
      setAssignmentMappingSort({ column: "assignment_group", direction: "asc" });
      setAssignmentMapping(createLoadState(emptyAssignmentGroupMapping));
    }
  }, [loadedProjectId, projectId]);

  useEffect(() => {
    if (isActive && hasActiveProjectContext && hasFilterCacheContext && !filterCatalog) {
      void loadFilterCatalog();
    }
  }, [
    filterCatalog,
    hasActiveProjectContext,
    hasFilterCacheContext,
    isActive,
    loadFilterCatalog,
  ]);

  useEffect(() => {
    if (!isActive || !hasActiveProjectContext || !hasFilterCacheContext || !filterCatalog) {
      return;
    }
    setFilterValues((currentFilterValues) => ({
      status: currentFilterValues.status === "idle" ? "success" : currentFilterValues.status,
      data: applicationFilterValuesFromCatalog(filterCatalog, null, filters),
      error: null,
    }));
    const timeoutId = window.setTimeout(() => {
      void loadFilterCounts();
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
    loadFilterCounts,
  ]);

  useEffect(() => {
    if (isActive && hasActiveProjectContext && requestBody) {
      void loadApplicationsData();
    }
  }, [hasActiveProjectContext, isActive, loadApplicationsData, requestBody, requestSignature]);

  useEffect(() => {
    if (isActive && activeSubTab === "lifecycle_planning" && hasActiveProjectContext && requestBody) {
      void loadLifecyclePlanningData();
    }
  }, [
    activeSubTab,
    hasActiveProjectContext,
    isActive,
    loadLifecyclePlanningData,
    requestBody,
    requestSignature,
    selectedLifecyclePlan,
  ]);

  useEffect(() => {
    if (isActive && activeSubTab === "assignment_group_mapping" && hasActiveProjectContext) {
      void loadAssignmentGroupMapping();
    }
  }, [
    activeSubTab,
    hasActiveProjectContext,
    isActive,
    loadAssignmentGroupMapping,
  ]);

  function updateFilter(filterName: FilterKey, values: string[]) {
    setFilters((currentFilters) => ({
      ...currentFilters,
      [filterName]: values,
    }));
  }

  function resetFilters() {
    if (!filtersEqual(filters, emptyFilters)) {
      setFilters(emptyFilters);
    }
    setSort(defaultSort);
  }

  function handleSort(column: TableColumnKey) {
    setSort((currentSort) => ({
      column,
      direction:
        currentSort.column === column && currentSort.direction === "asc" ? "desc" : "asc",
    }));
  }

  function handleAssignmentMappingSort(column: AssignmentMappingSortKey) {
    setAssignmentMappingSort((currentSort) => ({
      column,
      direction:
        currentSort.column === column && currentSort.direction === "asc" ? "desc" : "asc",
    }));
  }

  const lifecycleFilterApplied = filters.lifecycle_status_stage.length > 0;
  const applicationSummaryTiles = [
    {
      key: "applications",
      content: (
        <>
          <p className="label">Applications</p>
          <strong>{formatNumber(summary.data.applications)}</strong>
        </>
      ),
    },
    ...(summary.data.show_functional_groups
      ? [
          {
            key: "functional-groups",
            content: (
              <>
                <p className="label">Functional Groups</p>
                <strong>{formatNumber(summary.data.functional_groups)}</strong>
              </>
            ),
          },
        ]
      : []),
    ...(summary.data.show_assignment_groups
      ? [
          {
            key: "assignment-groups",
            content: (
              <>
                <p className="label">Assignment Groups</p>
                <strong>{formatNumber(summary.data.assignment_groups)}</strong>
              </>
            ),
          },
        ]
      : []),
    ...(summary.data.show_parent_business_apps
      ? [
          {
            key: "parent-business-apps",
            content: (
              <>
                <p className="label">Parent Business Apps</p>
                <strong>{formatNumber(summary.data.parent_business_apps)}</strong>
              </>
            ),
          },
        ]
      : []),
    {
      key: "application-type",
      content: (
        <>
          <p className="label">Application Type</p>
          <div className="overview-ticket-details">
            <span>Business: {formatNumber(summary.data.business_applications)}</span>
            <span>Technical: {formatNumber(summary.data.technical_applications)}</span>
          </div>
        </>
      ),
    },
    {
      key: "criticality",
      content: (
        <>
          <p className="label">Criticality</p>
          <div className="overview-ticket-details">
            <span>Very Critical: {formatNumber(summary.data.very_critical_applications)}</span>
            <span>Critical: {formatNumber(summary.data.critical_applications)}</span>
          </div>
        </>
      ),
    },
  ];

  const commentaryFunctional = commentaryFunctionalContext(filters.functional_track_ams_owner);
  const applicationCommentary = (
    sectionKey: string,
    chartKey?: string,
    subTabName?: string
  ): ReactNode => (
    <CommentaryEditor
      project_id={projectId}
      dashboard_area="applications"
      tab_name="applications"
      sub_tab_name={subTabName ?? null}
      section_key={sectionKey}
      chart_key={chartKey ?? null}
      scope_filter="all"
      ticket_type_filter="all"
      functional_track_ams_owner={commentaryFunctional}
    />
  );
  const lifecyclePlanCommentary = applicationCommentary(
    "lifecycle_planning_selected_plan",
    lifecyclePlanCommentaryKey(selectedLifecyclePlan),
    "lifecycle_planning"
  );

  return (
    <section className="applications-dashboard-layout" aria-labelledby="applications-tab-heading">
      <aside className="applications-filter-pane panel" aria-label="Applications filters">
        <div className="applications-filter-heading">
          <div>
            <p className="label">Filters</p>
            <h2>Applications</h2>
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
            label="Application Scope"
            options={filterOptions.application_scope}
            selectedValues={filters.application_scope}
            onChange={(values) => updateFilter("application_scope", values)}
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
            label="Assignment Group - Support Group Owner"
            options={filterOptions.assignment_group_owner}
            selectedValues={filters.assignment_group_owner}
            onChange={(values) => updateFilter("assignment_group_owner", values)}
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
          <ExcelMultiSelectFilter
            label="Architecture Type"
            options={filterOptions.architecture_type}
            selectedValues={filters.architecture_type}
            onChange={(values) => updateFilter("architecture_type", values)}
          />
          <ExcelMultiSelectFilter
            label="Application Type"
            options={filterOptions.application_type}
            selectedValues={filters.application_type}
            onChange={(values) => updateFilter("application_type", values)}
          />
          <ExcelMultiSelectFilter
            label="Business Critical"
            options={filterOptions.business_critical}
            selectedValues={filters.business_critical}
            onChange={(values) => updateFilter("business_critical", values)}
          />
          <ExcelMultiSelectFilter
            label="Install Status"
            options={filterOptions.install_status}
            selectedValues={filters.install_status}
            onChange={(values) => updateFilter("install_status", values)}
          />
          <ExcelMultiSelectFilter
            label="Install Type"
            options={filterOptions.install_type}
            selectedValues={filters.install_type}
            onChange={(values) => updateFilter("install_type", values)}
          />
          <ExcelMultiSelectFilter
            label="Hosting Env"
            options={filterOptions.hosting_env}
            selectedValues={filters.hosting_env}
            onChange={(values) => updateFilter("hosting_env", values)}
          />
          <ExcelMultiSelectFilter
            label="Lifecycle Status - Lifecycle Stage Status"
            options={filterOptions.lifecycle_status_stage}
            selectedValues={filters.lifecycle_status_stage}
            onChange={(values) => updateFilter("lifecycle_status_stage", values)}
          />
        </div>
      </aside>

      <div className="applications-main-pane">
        <div className="applications-subtabs" role="tablist" aria-label="Applications sections">
          <button
            aria-selected={activeSubTab === "overview"}
            className={activeSubTab === "overview" ? "active" : ""}
            role="tab"
            type="button"
            onClick={() => setActiveSubTab("overview")}
          >
            Overview
          </button>
          <button
            aria-selected={activeSubTab === "lifecycle_planning"}
            className={activeSubTab === "lifecycle_planning" ? "active" : ""}
            role="tab"
            type="button"
            onClick={() => setActiveSubTab("lifecycle_planning")}
          >
            Lifecycle Planning
          </button>
          <button
            aria-selected={activeSubTab === "assignment_group_mapping"}
            className={activeSubTab === "assignment_group_mapping" ? "active" : ""}
            role="tab"
            type="button"
            onClick={() => setActiveSubTab("assignment_group_mapping")}
          >
            Assignment Group Mapping
          </button>
        </div>

        {activeSubTab === "overview" ? (
          <>
        <section className="panel" aria-labelledby="applications-tab-heading">
          <div className="panel-heading">
            <div>
              <p className="label">Applications</p>
              <h2 id="applications-tab-heading">Application Inventory Analytics</h2>
            </div>
          </div>

          <div className="summary-grid applications-summary-grid">
            {applicationSummaryTiles.map((tile, index) => (
              <div key={tile.key} className={summaryTileToneClass(index, 6)}>
                {tile.content}
              </div>
            ))}
          </div>

          {summary.status === "loading" ? <p className="muted-text">Loading summary...</p> : null}
          {summary.status === "error" ? <p className="error-text">{summary.error}</p> : null}
          {applicationCommentary("applications_summary")}
        </section>

        <section className="panel" aria-labelledby="application-list-heading">
          <div className="panel-heading">
            <div>
              <p className="label">Application List</p>
              <h2 id="application-list-heading">
                Filtered Applications ({formatNumber(applicationList.data.total)})
              </h2>
            </div>
          </div>
          {applicationList.status === "loading" ? (
            <p className="muted-text">Loading application list...</p>
          ) : null}
          {applicationList.status === "error" ? (
            <p className="error-text">{applicationList.error}</p>
          ) : null}
          <div className="applications-table-frame">
            <table className="applications-table">
              <thead>
                <tr>
                  {tableColumns.map((column) => (
                    <th key={column.key}>
                      <button
                        className="table-sort-button"
                        type="button"
                        onClick={() => handleSort(column.key)}
                      >
                        {column.label}
                        {sort.column === column.key ? (
                          <span>{sort.direction === "asc" ? " ▲" : " ▼"}</span>
                        ) : null}
                      </button>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {applicationList.data.rows.length === 0 ? (
                  <tr>
                    <td colSpan={tableColumns.length}>No applications match the selected filters.</td>
                  </tr>
                ) : (
                  applicationList.data.rows.map((row) => (
                    <tr key={row.business_service_ci_name}>
                      {tableColumns.map((column) => (
                        <td key={column.key}>{formatTableValue(row, column.key)}</td>
                      ))}
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
          {applicationCommentary("application_list", "application_list")}
        </section>

        <section className="applications-chart-grid">
          <PieApplicationChart
            title="Strategic"
            data={charts.data.strategic}
            status={charts.status}
            commentary={applicationCommentary("applications_charts", "strategic")}
          />
          <BarApplicationChart
            title="Lifecycle Stage"
            data={charts.data.lifecycle_stage}
            hiddenMessage={
              lifecycleFilterApplied
                ? "Lifecycle chart hidden because Lifecycle filter is applied."
                : null
            }
            status={charts.status}
            commentary={applicationCommentary("applications_charts", "lifecycle_stage")}
          />
          <BarApplicationChart
            title="Architecture Type"
            data={charts.data.architecture_type}
            status={charts.status}
            commentary={applicationCommentary("applications_charts", "architecture_type")}
          />
          <BarApplicationChart
            title="Install Type"
            data={charts.data.install_type}
            status={charts.status}
            commentary={applicationCommentary("applications_charts", "install_type")}
          />
          <BarApplicationChart
            title="Hosting Env"
            data={charts.data.hosting_env}
            status={charts.status}
            commentary={applicationCommentary("applications_charts", "hosting_env")}
          />
          <PieApplicationChart
            title="Global vs Local Applications"
            data={charts.data.global_local_applications}
            status={charts.status}
            commentary={applicationCommentary("applications_charts", "applications_global_local")}
          />
        </section>
        {charts.status === "error" ? <p className="error-text">{charts.error}</p> : null}

        <ApplicationsCriticalityHostingPivotTable
          data={charts.data.criticality_hosting_pivot}
          error={charts.error}
          status={charts.status}
          commentary={applicationCommentary(
            "applications_charts",
            "applications_criticality_hosting_pivot",
          )}
        />

        <TopActiveUsersChart
          data={topActiveUsers.data}
          error={topActiveUsers.error}
          onTopNChange={setTopActiveUsersN}
          status={topActiveUsers.status}
          topN={topActiveUsersN}
          commentary={applicationCommentary("applications_charts", "top_active_users")}
        />
          </>
        ) : null}
        {activeSubTab === "lifecycle_planning" ? (
          <LifecyclePlanningPanel
            commentary={lifecyclePlanCommentary}
            data={lifecyclePlanning.data}
            error={lifecyclePlanning.error}
            onPlanChange={setSelectedLifecyclePlan}
            selectedPlan={selectedLifecyclePlan}
            status={lifecyclePlanning.status}
          />
        ) : null}
        {activeSubTab === "assignment_group_mapping" ? (
          <AssignmentGroupMappingPanel
            commentary={applicationCommentary(
              "applications_assignment_group_mapping",
              "assignment_group_mapping",
              "assignment_group_mapping"
            )}
            data={assignmentMapping.data}
            error={assignmentMapping.error}
            onSearchChange={setAssignmentMappingSearch}
            onSort={handleAssignmentMappingSort}
            onSourceChange={(value) => {
              setAssignmentMappingSource(value);
              setAssignmentMappingTrack("all");
            }}
            onScopeChange={(value) => {
              setAssignmentMappingScope(value);
              setAssignmentMappingTrack("all");
            }}
            onTrackChange={setAssignmentMappingTrack}
            search={assignmentMappingSearch}
            selectedSource={assignmentMappingSource}
            selectedScope={assignmentMappingScope}
            selectedTrack={assignmentMappingTrack}
            sort={assignmentMappingSort}
            status={assignmentMapping.status}
          />
        ) : null}
      </div>
    </section>
  );
}

const assignmentMappingSourceOptions: Array<{
  value: ApplicationsAssignmentGroupMappingSource;
  label: string;
}> = [
  { value: "application_inventory", label: "Application Inventory" },
  { value: "tickets", label: "Tickets Data" },
];

const assignmentMappingScopeOptions: Array<{
  value: ApplicationsAssignmentGroupMappingScope;
  label: string;
}> = [
  { value: "in_scope", label: "In-Scope" },
  { value: "out_of_scope", label: "Out-of-Scope" },
  { value: "all", label: "All" },
];

const assignmentMappingColumns: Array<{
  key: AssignmentMappingSortKey;
  label: string;
  inventorySourceOnly?: boolean;
  ticketSourceOnly?: boolean;
}> = [
  { key: "assignment_group", label: "Assignment Group" },
  { key: "functional_track", label: "Functional Track" },
  { key: "ams_owner", label: "AMS Owner" },
  { key: "support_lead", label: "Support Lead" },
  { key: "parent_business_application", label: "Parent Business Application" },
  { key: "business_service_ci_name", label: "Business Service CI Name" },
  { key: "application_number", label: "Application Number", inventorySourceOnly: true },
  { key: "application_owner", label: "Application Owner", inventorySourceOnly: true },
  { key: "supported_by_vendor", label: "Supported By Vendor", inventorySourceOnly: true },
  { key: "scope", label: "Scope" },
  { key: "incident_count", label: "Incident Count", ticketSourceOnly: true },
  { key: "sc_task_count", label: "SC Task Count", ticketSourceOnly: true },
  { key: "total_ticket_count", label: "Total Ticket Count", ticketSourceOnly: true },
  { key: "avg_monthly_incidents", label: "Avg Monthly Incidents", ticketSourceOnly: true },
  { key: "avg_monthly_sc_tasks", label: "Avg Monthly SC Tasks", ticketSourceOnly: true },
  {
    key: "avg_monthly_total_tickets",
    label: "Avg Monthly Total Tickets",
    ticketSourceOnly: true,
  },
];

function displayScope(value: string): string {
  if (value === "in_scope") {
    return "In Scope";
  }
  if (value === "out_of_scope") {
    return "Out of Scope";
  }
  return value;
}

function assignmentMappingCell(
  row: DashboardApplicationsAssignmentGroupMappingRow,
  key: AssignmentMappingSortKey
): string {
  if (key === "scope") {
    return displayScope(row.scope);
  }
  const value = row[key];
  return typeof value === "number" ? value.toLocaleString() : tableCellText(value);
}

function assignmentMappingSortValue(
  row: DashboardApplicationsAssignmentGroupMappingRow,
  key: AssignmentMappingSortKey
) {
  const value = row[key];
  if (typeof value === "number") {
    return value;
  }
  return tableCellText(value).toLowerCase();
}

function MetricCard({
  index,
  label,
  primary,
  secondary,
}: {
  index: number;
  label: string;
  primary: string;
  secondary: string;
}) {
  return (
    <div className={summaryTileToneClass(index, 4)}>
      <p className="label">{label}</p>
      <strong>{primary}</strong>
      <div className="overview-ticket-details">
        <span>{secondary}</span>
      </div>
    </div>
  );
}

function AssignmentGroupMappingPanel({
  commentary,
  data,
  error,
  onSearchChange,
  onSort,
  onSourceChange,
  onScopeChange,
  onTrackChange,
  search,
  selectedSource,
  selectedScope,
  selectedTrack,
  sort,
  status,
}: {
  commentary?: ReactNode;
  data: DashboardApplicationsAssignmentGroupMapping;
  error: string | null;
  onSearchChange: (value: string) => void;
  onSort: (column: AssignmentMappingSortKey) => void;
  onSourceChange: (value: ApplicationsAssignmentGroupMappingSource) => void;
  onScopeChange: (value: ApplicationsAssignmentGroupMappingScope) => void;
  onTrackChange: (value: string) => void;
  search: string;
  selectedSource: ApplicationsAssignmentGroupMappingSource;
  selectedScope: ApplicationsAssignmentGroupMappingScope;
  selectedTrack: string;
  sort: { column: AssignmentMappingSortKey; direction: "asc" | "desc" };
  status: LoadStatus;
}) {
  const [copyMessage, setCopyMessage] = useState<string | null>(null);
  const columns = assignmentMappingColumns.filter(
    (column) =>
      (!column.ticketSourceOnly || selectedSource === "tickets") &&
      (!column.inventorySourceOnly || selectedSource === "application_inventory")
  );
  const searchTerm = search.trim().toLowerCase();
  const rows = useMemo(() => {
    const visibleRows = searchTerm
      ? data.rows.filter((row) =>
          columns.some((column) =>
            assignmentMappingCell(row, column.key).toLowerCase().includes(searchTerm)
          )
        )
      : data.rows;
    return [...visibleRows].sort((left, right) => {
      const leftValue = assignmentMappingSortValue(left, sort.column);
      const rightValue = assignmentMappingSortValue(right, sort.column);
      const direction = sort.direction === "asc" ? 1 : -1;
      if (typeof leftValue === "number" && typeof rightValue === "number") {
        return (leftValue - rightValue) * direction;
      }
      return String(leftValue).localeCompare(String(rightValue)) * direction;
    });
  }, [columns, data.rows, searchTerm, sort.column, sort.direction]);
  const basisSecurityRows = useMemo(() => {
    const visibleRows = searchTerm
      ? data.basis_security_rows.filter((row) =>
          columns.some((column) =>
            assignmentMappingCell(row, column.key).toLowerCase().includes(searchTerm)
          )
        )
      : data.basis_security_rows;
    return [...visibleRows].sort((left, right) => {
      const leftValue = assignmentMappingSortValue(left, sort.column);
      const rightValue = assignmentMappingSortValue(right, sort.column);
      const direction = sort.direction === "asc" ? 1 : -1;
      if (typeof leftValue === "number" && typeof rightValue === "number") {
        return (leftValue - rightValue) * direction;
      }
      return String(leftValue).localeCompare(String(rightValue)) * direction;
    });
  }, [columns, data.basis_security_rows, searchTerm, sort.column, sort.direction]);
  const tableHeaders = columns.map((column) => column.label);
  const tableRowsFor = (sourceRows: DashboardApplicationsAssignmentGroupMappingRow[]) =>
    sourceRows.map((row) => columns.map((column) => assignmentMappingCell(row, column.key)));
  const totalTicketSummary =
    selectedSource === "tickets" ? (
      <>
        <MetricCard
          index={4}
          label="Incidents"
          primary={formatNumber(data.summary.incident_count)}
          secondary="Tickets source only"
        />
        <MetricCard
          index={5}
          label="SC Tasks"
          primary={formatNumber(data.summary.sc_task_count)}
          secondary="Tickets source only"
        />
        <MetricCard
          index={6}
          label="Total Tickets"
          primary={formatNumber(data.summary.total_ticket_count)}
          secondary="Incidents + SC Tasks"
        />
      </>
    ) : null;

  async function handleCopyTable(
    sourceRows: DashboardApplicationsAssignmentGroupMappingRow[],
    label: string
  ) {
    const tsv = [tableHeaders, ...tableRowsFor(sourceRows)].map((row) => row.join("\t")).join("\n");
    try {
      await copyTextToClipboard(tsv);
      setCopyMessage(`Copied ${sourceRows.length.toLocaleString()} ${label} rows to clipboard.`);
    } catch (copyError) {
      setCopyMessage(errorMessage(copyError, "Unable to copy table."));
    }
  }

  function handleDownloadCsv(
    filename: string,
    sourceRows: DashboardApplicationsAssignmentGroupMappingRow[]
  ) {
    downloadCsv(filename, tableHeaders, tableRowsFor(sourceRows));
    setCopyMessage("CSV downloaded.");
  }

  function renderMappingTable(
    sourceRows: DashboardApplicationsAssignmentGroupMappingRow[],
    emptyMessage: string
  ) {
    return (
      <div className="applications-table-frame validation-table-frame">
        <table className="applications-table validation-table">
          <thead>
            <tr>
              {columns.map((column) => (
                <th key={column.key}>
                  <button
                    className="table-sort-button"
                    type="button"
                    onClick={() => onSort(column.key)}
                  >
                    {column.label}
                    {sort.column === column.key ? (
                      <span>{sort.direction === "asc" ? " ▲" : " ▼"}</span>
                    ) : null}
                  </button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {status !== "loading" && sourceRows.length === 0 ? (
              <tr>
                <td colSpan={columns.length}>{emptyMessage}</td>
              </tr>
            ) : (
              sourceRows.map((row, index) => (
                <tr key={`${row.assignment_group}-${row.business_service_ci_name}-${index}`}>
                  {columns.map((column) => (
                    <td
                      className={
                        column.key.endsWith("_count") ||
                        column.key === "total_ticket_count" ||
                        column.key.startsWith("avg_monthly_")
                          ? "numeric-cell"
                          : undefined
                      }
                      key={column.key}
                    >
                      {assignmentMappingCell(row, column.key)}
                    </td>
                  ))}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    );
  }

  return (
    <div className="validation-stack">
      <section className="panel validation-intro-panel">
        <div className="panel-heading">
          <div>
            <p className="label">Applications</p>
            <h2>{"Assignment Group \u2194 Application Mapping"}</h2>
            <p className="muted-text">
              Static validation view for Assignment Group mappings from Application Inventory or
              normalized Incident and SC Task ticket data.
            </p>
          </div>
        </div>
        <div className="validation-controls">
          <div>
            <span className="validation-control-label">Mapping Source</span>
            <div className="segmented-control" role="tablist" aria-label="Mapping source">
              {assignmentMappingSourceOptions.map((option) => (
                <button
                  className={selectedSource === option.value ? "active" : ""}
                  key={option.value}
                  type="button"
                  onClick={() => onSourceChange(option.value)}
                >
                  {option.label}
                </button>
              ))}
            </div>
          </div>
          <div>
            <span className="validation-control-label">Scope</span>
            <div className="segmented-control" role="tablist" aria-label="Mapping scope">
              {assignmentMappingScopeOptions.map((option) => (
                <button
                  className={selectedScope === option.value ? "active" : ""}
                  key={option.value}
                  type="button"
                  onClick={() => onScopeChange(option.value)}
                >
                  {option.label}
                </button>
              ))}
            </div>
          </div>
        </div>
        <div className="track-button-row" aria-label="Functional Track selector">
          <button
            className={selectedTrack === "all" ? "active" : ""}
            type="button"
            onClick={() => onTrackChange("all")}
          >
            All Tracks
          </button>
          {data.available_functional_tracks.map((track) => (
            <button
              className={selectedTrack === track ? "active" : ""}
              key={track}
              type="button"
              onClick={() => onTrackChange(track)}
            >
              {track}
            </button>
          ))}
        </div>
      </section>

      <section className="panel validation-table-panel">
        <div className="panel-heading">
          <div>
            <p className="label">Validation Table</p>
            <h2>{rows.length.toLocaleString()} Assignment Group Mappings</h2>
            <p className="muted-text">
              Showing {rows.length.toLocaleString()} of {data.rows.length.toLocaleString()} rows.
            </p>
            {selectedSource === "tickets" && data.volume_period ? (
              <p className="muted-text">
                Ticket counts and average monthly volumes are based on {data.volume_period.label}.
              </p>
            ) : null}
          </div>
        </div>
        <div className="summary-grid validation-summary-grid">
          <MetricCard
            index={0}
            label="Mapping Rows"
            primary={formatNumber(data.summary.mapping_count)}
            secondary={selectedSource === "tickets" ? "Ticket mappings" : "Inventory mappings"}
          />
          <MetricCard
            index={1}
            label="Assignment Groups"
            primary={formatNumber(data.summary.assignment_group_count)}
            secondary="Distinct groups"
          />
          <MetricCard
            index={2}
            label="Business Service CIs"
            primary={formatNumber(data.summary.business_service_ci_count)}
            secondary="Distinct CIs"
          />
          <MetricCard
            index={3}
            label="Parent Applications"
            primary={formatNumber(data.summary.parent_business_application_count)}
            secondary="Distinct parents"
          />
          <MetricCard
            index={4}
            label="BASIS / SECURITY"
            primary={formatNumber(data.summary.basis_security_mapping_count)}
            secondary="Shown separately"
          />
          {totalTicketSummary}
        </div>
        <div className="validation-table-toolbar">
          <label className="validation-search">
            <span>Search</span>
            <input
              type="search"
              value={search}
              placeholder="Search assignment group, application, or track"
              onChange={(event) => onSearchChange(event.target.value)}
            />
          </label>
          <div className="validation-actions">
            <button
              className="secondary-button"
              type="button"
              onClick={() => handleCopyTable(rows, "mapping")}
            >
              Copy Table
            </button>
            <button
              className="secondary-button"
              type="button"
              onClick={() => handleDownloadCsv("assignment_group_mapping.csv", rows)}
            >
              Download CSV
            </button>
          </div>
        </div>
        {status === "loading" ? <p className="muted-text chart-state-text">Loading mappings...</p> : null}
        {status === "error" ? <p className="error-text">{error}</p> : null}
        {data.warnings.length > 0 ? <p className="error-text">{data.warnings[0]}</p> : null}
        {copyMessage ? <p className="chart-copy-status">{copyMessage}</p> : null}
        <div className="applications-table-frame validation-table-frame">
          <table className="applications-table validation-table">
            <thead>
              <tr>
                {columns.map((column) => (
                  <th key={column.key}>
                    <button
                      className="table-sort-button"
                      type="button"
                      onClick={() => onSort(column.key)}
                    >
                      {column.label}
                      {sort.column === column.key ? (
                        <span>{sort.direction === "asc" ? " ▲" : " ▼"}</span>
                      ) : null}
                    </button>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {status !== "loading" && rows.length === 0 ? (
                <tr>
                  <td colSpan={columns.length}>No mappings match the selected controls.</td>
                </tr>
              ) : (
                rows.map((row, index) => (
                  <tr key={`${row.assignment_group}-${row.business_service_ci_name}-${index}`}>
                    {columns.map((column) => (
                      <td
                        className={
                          column.key.endsWith("_count") ||
                          column.key === "total_ticket_count" ||
                          column.key.startsWith("avg_monthly_")
                            ? "numeric-cell"
                            : undefined
                        }
                        key={column.key}
                      >
                        {assignmentMappingCell(row, column.key)}
                      </td>
                    ))}
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
        {basisSecurityRows.length > 0 || data.basis_security_rows.length > 0 ? (
          <section className="validation-subsection">
            <div className="panel-heading">
              <div>
                <p className="label">Confirmed Out-of-Scope</p>
                <h3>BASIS and SECURITY Assignment Group Mapping</h3>
                <p className="muted-text">
                  Confirmed out-of-scope assignment groups containing "Basis" or "Security".
                </p>
              </div>
              <div className="validation-actions">
                <button
                  className="secondary-button"
                  type="button"
                  onClick={() => handleCopyTable(basisSecurityRows, "BASIS/SECURITY mapping")}
                >
                  Copy Table
                </button>
                <button
                  className="secondary-button"
                  type="button"
                  onClick={() =>
                    handleDownloadCsv(
                      "basis_security_assignment_group_mapping.csv",
                      basisSecurityRows
                    )
                  }
                >
                  Download CSV
                </button>
              </div>
            </div>
            {renderMappingTable(
              basisSecurityRows,
              "No BASIS or SECURITY assignment groups found for the selected scope and filters."
            )}
          </section>
        ) : null}
        {data.data_notes.map((note) => (
          <p className="muted-text validation-note" key={note}>
            {note}
          </p>
        ))}
        {commentary}
      </section>
    </div>
  );
}

function LifecyclePlanningPanel({
  commentary,
  data,
  error,
  onPlanChange,
  selectedPlan,
  status,
}: {
  commentary?: ReactNode;
  data: DashboardApplicationsLifecyclePlanning;
  error: string | null;
  onPlanChange: (plan: DashboardApplicationsLifecyclePlan) => void;
  selectedPlan: DashboardApplicationsLifecyclePlan;
  status: LoadStatus;
}) {
  const hasLifecycleData = data.matrix.in_use_application_count > 0;

  return (
    <div className="lifecycle-planning-stack">
      <section className="panel lifecycle-planning-intro">
        <div className="panel-heading">
          <div>
            <p className="label">Applications</p>
            <h2>Lifecycle Planning</h2>
          </div>
        </div>
        <p className="muted-text">
          Lifecycle planning shows In Use applications across Current, 1 to 3 years, and 3 to 5
          years planning horizons.
        </p>
      </section>

      <LifecyclePlanningMatrixTable data={data} error={error} status={status} />

      <section className="panel lifecycle-plan-panel">
        <div className="panel-heading">
          <div>
            <p className="label">Plan Focus</p>
            <h2>{lifecyclePlanTitle(selectedPlan)}</h2>
          </div>
          <div className="segmented-control" role="tablist" aria-label="Lifecycle plan selector">
            {lifecyclePlans.map((plan) => (
              <button
                aria-selected={selectedPlan === plan}
                className={selectedPlan === plan ? "active" : ""}
                key={plan}
                role="tab"
                type="button"
                onClick={() => onPlanChange(plan)}
              >
                {plan}
              </button>
            ))}
          </div>
        </div>

        {status === "loading" ? (
          <p className="muted-text chart-state-text">Loading lifecycle planning...</p>
        ) : null}
        {status === "error" ? <p className="error-text">{error}</p> : null}
        {status !== "loading" && status !== "error" && !hasLifecycleData ? (
          <p className="muted-text chart-state-text">
            No In Use applications match the current filters for lifecycle planning.
          </p>
        ) : null}

        {commentary}
      </section>

      <LifecyclePlanLineChart data={data} selectedPlan={selectedPlan} status={status} />
      <LifecyclePlanDetailTable data={data} selectedPlan={selectedPlan} status={status} />
    </div>
  );
}

function LifecyclePlanningMatrixTable({
  data,
  error,
  status,
}: {
  data: DashboardApplicationsLifecyclePlanning;
  error: string | null;
  status: LoadStatus;
}) {
  const matrix = data.matrix;
  const hasRows = matrix.in_use_application_count > 0;

  return (
    <section className="panel lifecycle-matrix-panel" aria-label="Lifecycle planning matrix">
      <div className="panel-heading">
        <div>
          <p className="label">Lifecycle Planning Matrix</p>
          <h2>Application Lifecycle Planning Matrix</h2>
          <p className="muted-text">
            Counts represent distinct Business Service CI Names per planning horizon. The same
            application can appear in multiple horizons.
          </p>
        </div>
      </div>
      {status === "loading" ? <p className="muted-text chart-state-text">Loading matrix...</p> : null}
      {status === "error" ? <p className="error-text">{error}</p> : null}
      {status !== "loading" && status !== "error" && !hasRows ? (
        <p className="muted-text chart-state-text">
          No In Use applications match the current filters for lifecycle planning.
        </p>
      ) : null}
      {status !== "loading" && status !== "error" && hasRows ? (
        <div className="applications-pivot-table-frame">
          <table className="applications-pivot-table lifecycle-matrix-table">
            <thead>
              <tr>
                <th scope="col">Lifecycle Plan</th>
                {matrix.horizons.map((horizon) => (
                  <th className="numeric-cell" key={horizon} scope="col">
                    {horizon}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {matrix.rows.map((row) => (
                <tr key={row.plan}>
                  <th scope="row">{row.plan}</th>
                  {matrix.horizons.map((horizon) => (
                    <td className="numeric-cell" key={horizon}>
                      {formatNumber(row.counts[horizon] ?? 0)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
          <p className="lifecycle-matrix-note">
            Matrix is based on {formatNumber(matrix.in_use_application_count)} In Use applications.
          </p>
        </div>
      ) : null}
    </section>
  );
}

function LifecyclePlanLineChart({
  data,
  selectedPlan,
  status,
}: {
  data: DashboardApplicationsLifecyclePlanning;
  selectedPlan: DashboardApplicationsLifecyclePlan;
  status: LoadStatus;
}) {
  const title = lifecyclePlanTitle(selectedPlan);
  const { chartRef, copyMessage, handleCopy, plotWidth } = useChartCopy(title);
  const chartData = data.selected_plan.chart;
  const hasRows = chartData.some((entry) => entry.count > 0);
  const chartWidth = Math.max(620, plotWidth - 24, chartData.length * 150);
  const planLineColor = lifecyclePlanLineColors[selectedPlan];
  const canCopy = status !== "loading" && hasRows;

  return (
    <section className="chart-card applications-chart-card applications-wide-chart" aria-label={title}>
      <div className="applications-chart-header">
        <div>
          <h3>{title}</h3>
          <p className="muted-text">Count of unique Business Service CI Names by planning horizon.</p>
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
        <p className="muted-text chart-state-text">
          No applications found for the selected lifecycle plan.
        </p>
      ) : null}
      {status !== "loading" && hasRows ? (
        <div className="applications-chart-plot" ref={chartRef}>
          <div className="applications-chart-scroll">
            <div className="applications-chart-stage">
              <LineChart
                data={chartData}
                width={chartWidth}
                height={320}
                margin={{ top: 30, right: 52, bottom: 64, left: 48 }}
              >
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="horizon" interval={0} padding={{ left: 54, right: 54 }} />
                <YAxis allowDecimals={false} />
                <Tooltip formatter={(value) => formatNumber(Number(value))} />
                <Line
                  type="monotone"
                  dataKey="count"
                  name={`${selectedPlan} applications`}
                  stroke={planLineColor}
                  strokeWidth={3}
                  dot={{ r: 5, fill: "#ffffff", stroke: planLineColor, strokeWidth: 2 }}
                  activeDot={{ r: 7, fill: planLineColor, stroke: "#ffffff", strokeWidth: 2 }}
                >
                  <LabelList dataKey="count" formatter={(value) => formatNumber(Number(value))} position="top" />
                </Line>
              </LineChart>
            </div>
          </div>
        </div>
      ) : null}
      {copyMessage ? <p className="chart-copy-status">{copyMessage}</p> : null}
    </section>
  );
}

const lifecycleDetailColumns: Array<{
  key: keyof DashboardApplicationsLifecycleApplication;
  label: string;
}> = [
  { key: "business_service_ci_name", label: "Business Service CI Name" },
  { key: "parent_business_application", label: "Parent Business Application" },
  { key: "functional_track", label: "Functional Track" },
  { key: "ams_owner", label: "AMS Owner" },
  { key: "application_owner", label: "Application Owner" },
  { key: "supported_by_vendor", label: "Supported By Vendor" },
  { key: "install_type", label: "Install Type" },
  { key: "business_criticality", label: "Business Criticality" },
  { key: "architecture_type", label: "Architecture Type" },
  { key: "application_type", label: "Application Type" },
  { key: "hosting_env", label: "Hosting Env" },
  { key: "global_application", label: "Global" },
  { key: "active_users", label: "Active Users" },
  { key: "lifecycle_current", label: "Lifecycle - Current" },
  { key: "lifecycle_1_to_3_years", label: "Lifecycle - 1 to 3 years" },
  { key: "lifecycle_3_to_5_years", label: "Lifecycle - 3 to 5 years" },
  { key: "selected_plan_horizons", label: "Selected Plan Horizons" },
];

function LifecyclePlanDetailTable({
  data,
  selectedPlan,
  status,
}: {
  data: DashboardApplicationsLifecyclePlanning;
  selectedPlan: DashboardApplicationsLifecyclePlan;
  status: LoadStatus;
}) {
  const rows = data.selected_plan.applications;

  return (
    <section className="panel lifecycle-detail-panel" aria-label={`${selectedPlan} application details`}>
      <div className="panel-heading">
        <div>
          <p className="label">Selected Plan Details</p>
          <h2>{lifecyclePlanTitle(selectedPlan)} - Details</h2>
          <p className="muted-text">
            Showing {formatNumber(data.selected_plan.application_count)} applications with {selectedPlan}
            {" "}plan across one or more lifecycle horizons.
          </p>
        </div>
      </div>
      {status === "loading" ? <p className="muted-text chart-state-text">Loading details...</p> : null}
      {status !== "loading" && rows.length === 0 ? (
        <p className="muted-text chart-state-text">
          No applications found for the selected lifecycle plan.
        </p>
      ) : null}
      {status !== "loading" && rows.length > 0 ? (
        <div className="applications-table-frame">
          <table className="applications-table lifecycle-detail-table">
            <thead>
              <tr>
                {lifecycleDetailColumns.map((column) => (
                  <th key={column.key}>{column.label}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.business_service_ci_name}>
                  {lifecycleDetailColumns.map((column) => (
                    <td key={column.key}>
                      {Array.isArray(row[column.key])
                        ? (row[column.key] as string[]).join(", ")
                        : formatCellValue(row[column.key] as string | number | null)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </section>
  );
}

function ApplicationsCriticalityHostingPivotTable({
  commentary,
  data,
  error,
  status,
}: {
  commentary?: ReactNode;
  data: DashboardApplicationsCharts["criticality_hosting_pivot"];
  error: string | null;
  status: LoadStatus;
}) {
  const title = "Application Criticality by Hosting Environment";
  const hasRows = data.grand_total > 0;
  const rowsByCriticality = new Map(data.values.map((row) => [row.business_criticality, row]));

  return (
    <section className="chart-card applications-chart-card applications-wide-chart" aria-label={title}>
      <div className="applications-chart-header">
        <div>
          <h3>{title}</h3>
          <p className="muted-text">
            Count of unique Business Service CI Names with Lifecycle Stage/Status = In use.
          </p>
        </div>
      </div>
      {status === "loading" ? <p className="muted-text chart-state-text">Loading table...</p> : null}
      {status === "error" ? <p className="error-text">{error}</p> : null}
      {status !== "loading" && status !== "error" && !hasRows ? (
        <p className="muted-text chart-state-text">No in-use applications match the selected filters.</p>
      ) : null}
      {status !== "loading" && status !== "error" && hasRows ? (
        <div className="applications-pivot-table-frame">
          <table className="applications-pivot-table">
            <thead>
              <tr>
                <th scope="col">Business Criticality</th>
                {data.columns.map((column) => (
                  <th className="numeric-cell" key={column} scope="col">
                    {column}
                  </th>
                ))}
                <th className="numeric-cell total-cell" scope="col">
                  Total
                </th>
              </tr>
            </thead>
            <tbody>
              {data.rows.map((criticality) => {
                const row = rowsByCriticality.get(criticality);
                return (
                  <tr key={criticality}>
                    <th scope="row">{criticality}</th>
                    {data.columns.map((column) => (
                      <td className="numeric-cell" key={column}>
                        {formatNumber(row?.counts[column] ?? 0)}
                      </td>
                    ))}
                    <td className="numeric-cell total-cell">{formatNumber(row?.total ?? 0)}</td>
                  </tr>
                );
              })}
              <tr className="pivot-total-row">
                <th scope="row">Total</th>
                {data.columns.map((column) => (
                  <td className="numeric-cell total-cell" key={column}>
                    {formatNumber(data.column_totals[column] ?? 0)}
                  </td>
                ))}
                <td
                  aria-label={`Grand total ${formatNumber(data.grand_total)}`}
                  className="numeric-cell total-cell grand-total-cell"
                  title="Grand total"
                >
                  <span className="grand-total-label">Grand Total</span>
                  <strong>{formatNumber(data.grand_total)}</strong>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      ) : null}
      {commentary}
    </section>
  );
}

function TopActiveUsersChart({
  commentary,
  data,
  error,
  onTopNChange,
  status,
  topN,
}: {
  commentary?: ReactNode;
  data: DashboardApplicationsTopActiveUsers;
  error: string | null;
  onTopNChange: (value: TopNSelection) => void;
  status: LoadStatus;
  topN: TopNSelection;
}) {
  const title = "Top Parent Business Applications by Active Users";
  const { chartRef, copyMessage, handleCopy, plotWidth } = useChartCopy(title);
  const hasRows = data.points.length > 0;
  const chartWidth = Math.max(760, plotWidth - 24);
  const chartHeight = topN === 20 ? 700 : 460;
  const canCopy = status !== "loading" && hasRows;

  return (
    <section className="chart-card applications-chart-card applications-wide-chart" aria-label={title}>
      <div className="applications-chart-header">
        <div>
          <h3>{title}</h3>
          <p className="muted-text">
            Application Inventory only. One row per Parent Business Application, using the highest
            Active Users value when duplicates exist.
          </p>
        </div>
        <div className="volumetrics-chart-actions">
          <div className="segmented-control" aria-label="Top Active Users">
            {[10, 20].map((value) => (
              <button
                className={topN === value ? "active" : ""}
                key={value}
                type="button"
                onClick={() => onTopNChange(value as TopNSelection)}
              >
                Top {value}
              </button>
            ))}
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
        <p className="muted-text chart-state-text">Active Users data is not available yet.</p>
      ) : null}
      {status !== "loading" && status !== "error" && hasRows ? (
        <div className="applications-chart-plot applications-horizontal-chart-plot" ref={chartRef}>
          <div className="applications-chart-scroll">
            <div className="applications-chart-stage">
              <BarChart
                data={data.points}
                layout="vertical"
                width={chartWidth}
                height={chartHeight}
                margin={{ top: 22, right: 96, bottom: 24, left: 220 }}
              >
                <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                <XAxis type="number" tickFormatter={(value) => formatNumber(Number(value))} />
                <YAxis
                  dataKey="parent_application_name"
                  interval={0}
                  tick={{ fontSize: 12, fontWeight: 700 }}
                  type="category"
                  width={210}
                />
                <Tooltip formatter={(value) => formatNumber(Number(value))} />
                <Bar dataKey="active_users" fill="#0f766e" name="Active Users" radius={[0, 5, 5, 0]}>
                  <LabelList
                    dataKey="active_users"
                    formatter={(value) => formatNumber(Number(value))}
                    position="right"
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

function PieApplicationChart({
  commentary,
  data,
  hiddenMessage,
  status,
  title,
}: {
  commentary?: ReactNode;
  data: Array<{ label: string; count: number }>;
  hiddenMessage?: string | null;
  status: LoadStatus;
  title: string;
}) {
  const { chartRef, copyMessage, handleCopy, plotWidth } = useChartCopy(title);
  const chartData = data.filter((entry) => entry.count > 0);
  const total = chartData.reduce((sum, entry) => sum + entry.count, 0);
  const canCopy = !hiddenMessage && status !== "loading" && chartData.length > 0;
  const chartWidth = Math.max(500, plotWidth - 24);

  return (
    <section className="chart-card applications-chart-card" aria-label={title}>
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
      {hiddenMessage ? <p className="muted-text chart-state-text">{hiddenMessage}</p> : null}
      {!hiddenMessage && status === "loading" ? (
        <p className="muted-text chart-state-text">Loading chart...</p>
      ) : null}
      {!hiddenMessage && status !== "loading" && chartData.length === 0 ? (
        <p className="muted-text chart-state-text">No chart data available.</p>
      ) : null}
      {!hiddenMessage && status !== "loading" && chartData.length > 0 ? (
        <div className="applications-chart-plot" ref={chartRef}>
          <div className="applications-chart-scroll">
            <div className="applications-chart-stage">
              <PieChart width={chartWidth} height={320}>
                <Tooltip />
                <Legend />
                <Pie
                  data={chartData}
                  dataKey="count"
                  label={(props) => renderApplicationPieLabel(props, total)}
                  labelLine
                  nameKey="label"
                  outerRadius={104}
                >
                  {chartData.map((entry, index) => (
                    <Cell
                      fill={chartColors[index % chartColors.length]}
                      key={entry.label}
                      stroke="#ffffff"
                      strokeWidth={1.5}
                    />
                  ))}
                </Pie>
              </PieChart>
            </div>
          </div>
        </div>
      ) : null}
      {copyMessage ? <p className="chart-copy-status">{copyMessage}</p> : null}
      {commentary}
    </section>
  );
}

function renderApplicationPieLabel(
  props: { x?: number | string; y?: number | string; value?: number | string },
  total: number,
) {
  const x = Number(props.x);
  const y = Number(props.y);
  const value = Number(props.value);
  if (!Number.isFinite(x) || !Number.isFinite(y) || !Number.isFinite(value) || value <= 0) {
    return null;
  }
  const percentage = total > 0 ? Math.round((value / total) * 100) : 0;
  return (
    <text fill="#0f172a" fontSize={11} fontWeight={800} textAnchor="middle" x={x} y={y}>
      {`${formatNumber(value)} (${percentage}%)`}
    </text>
  );
}

function BarApplicationChart({
  commentary,
  data,
  hiddenMessage,
  status,
  title,
}: {
  commentary?: ReactNode;
  data: Array<{ label: string; count: number }>;
  hiddenMessage?: string | null;
  status: LoadStatus;
  title: string;
}) {
  const { chartRef, copyMessage, handleCopy, plotWidth } = useChartCopy(title);
  const chartWidth = Math.max(500, plotWidth - 24, data.length * 96);
  const canCopy = !hiddenMessage && status !== "loading" && data.length > 0;

  return (
    <section className="chart-card applications-chart-card" aria-label={title}>
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
      {hiddenMessage ? <p className="muted-text chart-state-text">{hiddenMessage}</p> : null}
      {!hiddenMessage && status === "loading" ? (
        <p className="muted-text chart-state-text">Loading chart...</p>
      ) : null}
      {!hiddenMessage && status !== "loading" && data.length === 0 ? (
        <p className="muted-text chart-state-text">No chart data available.</p>
      ) : null}
      {!hiddenMessage && status !== "loading" && data.length > 0 ? (
        <div className="applications-chart-plot" ref={chartRef}>
          <div className="applications-chart-scroll">
            <div className="applications-chart-stage">
              <BarChart
                data={data}
                width={chartWidth}
                height={320}
                margin={{ top: 30, right: 52, bottom: 92, left: 48 }}
              >
                <XAxis
                  dataKey="label"
                  angle={-35}
                  height={98}
                  interval={0}
                  textAnchor="end"
                  tickMargin={12}
                />
                <Tooltip />
                <Bar dataKey="count" name="Applications" radius={[4, 4, 0, 0]}>
                  {data.map((entry, index) => (
                    <Cell
                      fill={chartColors[index % chartColors.length]}
                      key={entry.label}
                      stroke="#ffffff"
                      strokeWidth={1}
                    />
                  ))}
                  <LabelList dataKey="count" position="top" />
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

export default ApplicationsDashboard;
