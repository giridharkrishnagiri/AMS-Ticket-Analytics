import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  LabelList,
  Legend,
  Pie,
  PieChart,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import {
  getDashboardApplicationsCharts,
  getDashboardApplicationsFilterValues,
  getDashboardApplicationsList,
  getDashboardApplicationsSummary,
  getDashboardApplicationsTopActiveUsers,
} from "./api/dashboard";
import type {
  DashboardApplicationRow,
  DashboardApplicationsCharts,
  DashboardApplicationsFilters,
  DashboardApplicationsFilterValues,
  DashboardApplicationsFilterValuesRequest,
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
  projectId: string;
  isActive: boolean;
  onExportContextChange?: (context: { functionalTrackAmsOwners: string[] }) => void;
};

type TopNSelection = 10 | 20;
type FilterKey = keyof DashboardApplicationsFilters;
type TableColumnKey = keyof DashboardApplicationRow;

const emptyFilters: DashboardApplicationsFilters = {
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
    rows: ["Very Critical", "Critical", "High", "Medium", "Low"],
    columns: ["Production", "Non-Prod", "Dev", "Test", "Historical & DR"],
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

const defaultSort: DashboardApplicationsSort = {
  column: "business_service_ci_name",
  direction: "asc",
};

const tableColumns: Array<{ key: TableColumnKey; label: string }> = [
  { key: "business_service_ci_name", label: "Business Service CI Name (Application)" },
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
  projectId,
  isActive,
  onExportContextChange,
}: ApplicationsDashboardProps) {
  const [filters, setFilters] = useState<DashboardApplicationsFilters>(emptyFilters);
  const [sort, setSort] = useState<DashboardApplicationsSort>(defaultSort);
  const [filterValues, setFilterValues] = useState<LoadState<DashboardApplicationsFilterValues>>(
    createLoadState(emptyFilterValues)
  );
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
  const [loadedProjectId, setLoadedProjectId] = useState("");

  const filterOptions = useMemo(
    () => ({
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
  const filterValuesRequest = useMemo<DashboardApplicationsFilterValuesRequest | null>(() => {
    const cleanedProjectId = projectId.trim();
    if (!cleanedProjectId) {
      return null;
    }
    return {
      project_id: cleanedProjectId,
      filters,
    };
  }, [filters, projectId]);
  const filterValuesSignature = useMemo(
    () => (filterValuesRequest ? JSON.stringify(filterValuesRequest) : ""),
    [filterValuesRequest]
  );
  const hasActiveProjectContext = Boolean(projectId.trim()) && projectId === loadedProjectId;

  useEffect(() => {
    onExportContextChange?.({
      functionalTrackAmsOwners: filters.functional_track_ams_owner,
    });
  }, [filters.functional_track_ams_owner, onExportContextChange]);

  const loadFilterValues = useCallback(async () => {
    if (!filterValuesRequest) {
      return;
    }
    setFilterValues(createLoadState(emptyFilterValues, "loading"));
    try {
      const values = await getDashboardApplicationsFilterValues(filterValuesRequest);
      setFilterValues({ status: "success", data: values, error: null });
    } catch (error) {
      setFilterValues({
        status: "error",
        data: emptyFilterValues,
        error: errorMessage(error, "Unable to load Application filters"),
      });
    }
  }, [filterValuesRequest]);

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

  useEffect(() => {
    if (projectId !== loadedProjectId) {
      setLoadedProjectId(projectId);
      setFilters(emptyFilters);
      setSort(defaultSort);
      setFilterValues(createLoadState(emptyFilterValues));
      setSummary(createLoadState(emptySummary));
      setApplicationList(createLoadState(emptyList));
      setCharts(createLoadState(emptyCharts));
      setTopActiveUsersN(10);
      setTopActiveUsers(createLoadState(emptyTopActiveUsers));
    }
  }, [loadedProjectId, projectId]);

  useEffect(() => {
    if (isActive && hasActiveProjectContext && filterValuesRequest) {
      void loadFilterValues();
    }
  }, [
    filterValuesRequest,
    filterValuesSignature,
    hasActiveProjectContext,
    isActive,
    loadFilterValues,
  ]);

  useEffect(() => {
    if (isActive && hasActiveProjectContext && requestBody) {
      void loadApplicationsData();
    }
  }, [hasActiveProjectContext, isActive, loadApplicationsData, requestBody, requestSignature]);

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
  const applicationCommentary = (sectionKey: string, chartKey?: string): ReactNode => (
    <CommentaryEditor
      project_id={projectId}
      dashboard_area="applications"
      tab_name="applications"
      section_key={sectionKey}
      chart_key={chartKey ?? null}
      scope_filter="all"
      ticket_type_filter="all"
      functional_track_ams_owner={commentaryFunctional}
    />
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
          <p className="muted-text">Loading filter values...</p>
        ) : null}
        {filterValues.status === "error" ? (
          <p className="error-text">{filterValues.error}</p>
        ) : null}

        <div className="applications-filter-stack">
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
      </div>
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
                <td className="numeric-cell grand-total-cell">{formatNumber(data.grand_total)}</td>
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
