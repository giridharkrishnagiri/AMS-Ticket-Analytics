import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ChangeEvent, FormEvent, ReactNode } from "react";

import ApplicationInventory from "./ApplicationInventory";
import CustomerSelector from "./CustomerSelector";
import {
  getSourceColumnsForTicketType,
  getSuggestedMappingForTicketType,
  saveMappingTemplate,
} from "./api/mappings";
import type { MappingSource, SourceColumn } from "./api/mappings";
import type { ProjectOption } from "./api/projects";
import {
  enrichIncidentSla,
  getIncidentSlaSummary,
  getIncidentSlaUploadHistory,
  uploadIncidentSlaFiles,
} from "./api/sla";
import type {
  IncidentSlaEnrichResponse,
  AgreementType,
  IncidentSlaMultiUploadResponse,
  IncidentSlaSummaryResponse,
  IncidentSlaUploadHistoryRow,
} from "./api/sla";
import {
  applyMappingToUploadBatches,
  getIngestionJob,
  getValidationSummary,
  ingestUploadBatches,
  listUploadBatches,
  listUploadedFiles,
  normalizeUploadBatches,
  uploadTicketFilesMultiple,
} from "./api/uploads";
import type {
  IngestionJob,
  UploadBatchApplyMappingMultipleResponse,
  UploadBatch,
  UploadBatchIngestMultipleResponse,
  UploadBatchNormalizeMultipleResponse,
  UploadMultipleResponse,
  UploadedFile,
  ValidationSummary,
} from "./api/uploads";

type UploadCenterTab = "application-inventory" | "ticket-details";
type TicketUploadType =
  | "INCIDENT"
  | "SERVICE_CATALOG_TASK"
  | "PROBLEM"
  | "CHANGE"
  | "INCIDENT_OLA"
  | "INCIDENT_SLA";
type WorkflowStepId = "upload" | "ingest" | "normalize" | "mapping" | "apply" | "summary";

type WorkflowStep = {
  id: WorkflowStepId;
  label: string;
  helper: string;
};

const ticketUploadTypes: Array<{
  label: string;
  value: TicketUploadType;
  description: string;
}> = [
  {
    label: "Incidents",
    value: "INCIDENT",
    description: "ServiceNow Incident extracts",
  },
  {
    label: "SC Tasks",
    value: "SERVICE_CATALOG_TASK",
    description: "Service Catalog Task extracts",
  },
  {
    label: "Problems",
    value: "PROBLEM",
    description: "Problem Register extracts",
  },
  {
    label: "Changes",
    value: "CHANGE",
    description: "Change Register extracts",
  },
  {
    label: "Incident OLA",
    value: "INCIDENT_OLA",
    description: "Vendor-specific Incident OLA files",
  },
  {
    label: "Incident SLA",
    value: "INCIDENT_SLA",
    description: "End-to-end IT / business Incident SLA files",
  },
];

const futureUploadTypes = ["Problem SLAs", "Change SLAs", "SC Task SLAs"];

const workflowSteps: WorkflowStep[] = [
  { id: "upload", label: "Upload", helper: "Select type and files" },
  { id: "ingest", label: "Ingest", helper: "Stage source rows" },
  { id: "normalize", label: "Normalize", helper: "Scope and enrich tickets" },
  { id: "mapping", label: "Column Mapping", helper: "Map source columns" },
  { id: "apply", label: "Apply / Enrich", helper: "Finalize processing" },
  { id: "summary", label: "Summary", helper: "Review results" },
];

const ticketNormalizedFields = [
  "ticket_id",
  "title",
  "description",
  "status",
  "priority",
  "urgency",
  "impact",
  "category",
  "subcategory",
  "catalog_item_name",
  "catalog_knowledge_base",
  "application",
  "business_service",
  "configuration_item",
  "assignment_group",
  "assigned_to",
  "requester",
  "created_by",
  "created_channel",
  "created_at",
  "resolved_at",
  "closed_at",
  "sla_breached",
  "reopen_count",
  "reassignment_count",
  "business_duration_seconds",
  "resolution_code",
  "resolution_notes",
];

const problemNormalizedFields = [
  "number",
  "state",
  "problem_statement",
  "business_application",
  "business_service",
  "configuration_item",
  "category",
  "subcategory",
  "assignment_group",
  "assigned_to",
  "urgency",
  "priority",
  "active",
  "created_at_source",
  "opened_at",
  "actual_start_at",
  "actual_end_at",
  "closed_at",
  "resolved_at",
  "business_duration_seconds",
  "duration_seconds",
  "made_sla",
  "major_incident",
  "major_problem",
  "known_error",
  "related_incidents",
  "linked_incident_count",
  "change_request",
  "caused_by_change",
  "problem_state",
  "close_notes",
  "cause_notes",
  "fix_notes",
  "workaround",
  "description",
];

const changeNormalizedFields = [
  "number",
  "short_description",
  "type",
  "state",
  "phase",
  "phase_state",
  "business_application",
  "business_service",
  "application_name",
  "affected_ci_service",
  "category",
  "assignment_group",
  "assigned_to",
  "priority",
  "urgency",
  "impact",
  "risk",
  "risk_value",
  "vendor",
  "created_at_source",
  "opened_at",
  "planned_start_at",
  "planned_end_at",
  "actual_start_at",
  "actual_end_at",
  "closed_at",
  "business_duration_seconds",
  "duration_seconds",
  "made_sla",
  "unauthorized",
  "outside_maintenance_schedule",
  "cab_required",
  "cab_approval",
  "cab_date",
  "change_reason",
  "close_code",
  "close_code_sub_category",
  "incident",
  "problem",
  "caused_by_change",
  "implementation_plan",
  "backout_plan",
  "test_plan",
  "communication_plan",
];

function normalizedFieldsForUploadType(ticketType: TicketUploadType): string[] {
  if (ticketType === "PROBLEM") {
    return problemNormalizedFields;
  }
  if (ticketType === "CHANGE") {
    return changeNormalizedFields;
  }
  return ticketNormalizedFields;
}

function importantFieldsForUploadType(ticketType: TicketUploadType): string[] {
  if (ticketType === "PROBLEM" || ticketType === "CHANGE") {
    return ["number"];
  }
  return ["ticket_id", "title", "created_at"];
}

function getTodayDateInputValue(): string {
  return new Date().toISOString().slice(0, 10);
}

function formatBytes(sizeBytes: number): string {
  if (sizeBytes < 1024) {
    return `${sizeBytes} B`;
  }

  if (sizeBytes < 1024 * 1024) {
    return `${(sizeBytes / 1024).toFixed(1)} KB`;
  }

  return `${(sizeBytes / 1024 / 1024).toFixed(1)} MB`;
}

function formatNumber(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "Not available";
  }
  return value.toLocaleString();
}

function formatBatchStatus(status: string | null | undefined): string {
  if (!status) {
    return "Not available";
  }
  const statusLabels: Record<string, string> = {
    PENDING: "Pending",
    STORED: "Uploaded",
    UPLOADED: "Uploaded",
    INGESTING: "Processing ...",
    INGESTED: "Ingested",
    INGESTION_FAILED: "Failed",
    NORMALIZING: "Processing ...",
    NORMALIZED: "Normalized",
    NORMALIZATION_FAILED: "Failed",
    ARCHIVED: "Archived",
    DELETED: "Deleted",
    COMPLETED: "Completed",
    PARTIAL: "Partial",
    FAILED: "Failed",
    RUNNING: "Processing ...",
  };
  return statusLabels[status] ?? status.replace(/_/g, " ");
}

function formatApplyStatus(status: string | null | undefined): string {
  if (!status) {
    return "Pending";
  }
  const statusLabels: Record<string, string> = {
    APPLIED: "Mapping Applied",
    SKIPPED_ALREADY_APPLIED: "Already Applied",
    FAILED_PARTIAL_OUTPUT: "Failed - Partial Output",
    FAILED: "Failed",
    NORMALIZED: "Mapping Applied",
  };
  return statusLabels[status] ?? formatBatchStatus(status);
}

function normalizeStatusValue(status: string | null | undefined): string {
  return (status ?? "").trim().toUpperCase();
}

function deriveUploadStageStatus(batchStatus: string | null | undefined): string {
  const status = normalizeStatusValue(batchStatus);
  if (status === "DELETED") {
    return "DELETED";
  }
  if (status === "ARCHIVED") {
    return "ARCHIVED";
  }
  if (status === "FAILED") {
    return "FAILED";
  }
  return status ? "UPLOADED" : "PENDING";
}

function deriveIngestStageStatus({
  batchStatus,
  ingestStatus,
  jobStatus,
}: {
  batchStatus: string | null | undefined;
  ingestStatus: string | null | undefined;
  jobStatus: string | null | undefined;
}): string {
  const explicitStatus = normalizeStatusValue(ingestStatus);
  if (explicitStatus) {
    if (explicitStatus === "COMPLETED") {
      return "INGESTED";
    }
    if (explicitStatus === "RUNNING" || explicitStatus === "INGESTING") {
      return "INGESTING";
    }
    if (explicitStatus === "FAILED" || explicitStatus === "INGESTION_FAILED") {
      return "FAILED";
    }
    return explicitStatus;
  }

  const currentJobStatus = normalizeStatusValue(jobStatus);
  if (currentJobStatus === "COMPLETED") {
    return "INGESTED";
  }
  if (currentJobStatus === "RUNNING" || currentJobStatus === "PENDING") {
    return "INGESTING";
  }
  if (currentJobStatus === "FAILED") {
    return "FAILED";
  }

  const status = normalizeStatusValue(batchStatus);
  if (["INGESTED", "NORMALIZING", "NORMALIZED", "COMPLETED", "ARCHIVED"].includes(status)) {
    return "INGESTED";
  }
  if (status === "INGESTING") {
    return "INGESTING";
  }
  if (status === "INGESTION_FAILED") {
    return "FAILED";
  }
  return "PENDING";
}

function deriveNormalizeStageStatus({
  batchStatus,
  normalizeStatus,
}: {
  batchStatus: string | null | undefined;
  normalizeStatus: string | null | undefined;
}): string {
  const explicitStatus = normalizeStatusValue(normalizeStatus);
  if (explicitStatus) {
    if (explicitStatus === "NORMALIZED" || explicitStatus === "COMPLETED") {
      return "NORMALIZED";
    }
    if (explicitStatus === "NORMALIZING" || explicitStatus === "RUNNING") {
      return "NORMALIZING";
    }
    if (explicitStatus === "NORMALIZATION_FAILED" || explicitStatus === "FAILED") {
      return "FAILED";
    }
    return explicitStatus;
  }

  const status = normalizeStatusValue(batchStatus);
  if (["NORMALIZED", "COMPLETED", "ARCHIVED"].includes(status)) {
    return "NORMALIZED";
  }
  if (status === "NORMALIZING") {
    return "NORMALIZING";
  }
  if (status === "NORMALIZATION_FAILED") {
    return "FAILED";
  }
  return "PENDING";
}

function deriveApplyStageStatus({
  batchStatus,
  applyStatus,
}: {
  batchStatus: string | null | undefined;
  applyStatus: string | null | undefined;
}): string {
  const explicitStatus = normalizeStatusValue(applyStatus);
  if (explicitStatus) {
    return explicitStatus;
  }

  const status = normalizeStatusValue(batchStatus);
  if (status === "ARCHIVED") {
    return "APPLIED";
  }
  if (status === "NORMALIZATION_FAILED" || status === "FAILED") {
    return "FAILED";
  }
  return "PENDING";
}

function safeBatchNamePart(value: string): string {
  return value
    .replace(/\.[^.]+$/, "")
    .replace(/[^a-zA-Z0-9]+/g, " ")
    .trim()
    .replace(/\s+/g, " ");
}

function createAutoBatchName(
  projectLabel: string,
  ticketType: string,
  selectedFiles: File[]
): string {
  const customerPart = safeBatchNamePart(projectLabel || "Customer");
  const filePart = safeBatchNamePart(selectedFiles[0]?.name ?? ticketType);
  const timestamp = new Date().toISOString().slice(0, 19).replace("T", " ").replace(/:/g, "-");
  return `${customerPart} - ${filePart} - ${timestamp}`;
}

function cleanMapping(mapping: Record<string, string>): Record<string, string> {
  return Object.fromEntries(
    Object.entries(mapping).filter(([, sourceColumn]) => sourceColumn.trim())
  );
}

function mappingSourceMessage(mappingSource: MappingSource): string {
  if (mappingSource === "SAVED_TEMPLATE") {
    return "Loaded saved mapping for this customer and ticket type.";
  }
  return "Loaded built-in suggested mapping.";
}

function MetricCard({
  label,
  value,
  helper,
}: {
  label: string;
  value: string;
  helper?: string;
}) {
  return (
    <div>
      <p className="label">{label}</p>
      <strong>{value}</strong>
      {helper ? <span className="helper-text">{helper}</span> : null}
    </div>
  );
}

function InfoPanel({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <div className="info-panel">
      <p className="label">{title}</p>
      <div>{children}</div>
    </div>
  );
}

type WorkflowBatchRow = {
  batchId: string;
  batchName: string;
  filename: string | null;
  uploadStatus: string;
  ingestStatus: string;
  normalizeStatus: string;
  applyStatus: string;
  inputRows: number | null;
  inScopeRows: number | null;
  outOfScopeRows: number | null;
  duplicateSkippedRows: number | null;
  remarks: string | null;
};

function combineIngestResponses(
  projectId: string,
  responses: UploadBatchIngestMultipleResponse[]
): UploadBatchIngestMultipleResponse {
  const batches = responses.flatMap((response) => response.batches);
  return {
    project_id: projectId,
    batches,
    totals: {
      batches_requested: batches.length,
      batches_ingested: batches.filter((batch) =>
        ["INGESTED", "NORMALIZED"].includes(batch.status)
      ).length,
      batches_failed: batches.filter((batch) => batch.status === "FAILED").length,
      raw_rows_inserted: batches.reduce(
        (total, batch) => total + batch.raw_rows_inserted,
        0
      ),
    },
  };
}

function combineNormalizeResponses(
  projectId: string,
  ticketType: TicketUploadType,
  responses: UploadBatchNormalizeMultipleResponse[]
): UploadBatchNormalizeMultipleResponse {
  const batches = responses.flatMap((response) => response.batches);
  return {
    project_id: projectId,
    ticket_type: ticketType,
    batches,
    totals: {
      raw_rows: batches.reduce((total, batch) => total + batch.raw_rows, 0),
      in_scope_inserted: batches.reduce(
        (total, batch) => total + batch.in_scope_inserted,
        0
      ),
      out_of_scope_inserted: batches.reduce(
        (total, batch) => total + batch.out_of_scope_inserted,
        0
      ),
      assignment_group_not_in_inventory_rows: batches.reduce(
        (total, batch) => total + batch.assignment_group_not_in_inventory_rows,
        0
      ),
      duplicate_skipped_rows: batches.reduce(
        (total, batch) => total + batch.duplicate_skipped_rows,
        0
      ),
      failed_batches: batches.filter(
        (batch) => batch.status === "NORMALIZATION_FAILED" || batch.failed_rows > 0
      ).length,
    },
  };
}

function combineApplyResponses(
  projectId: string,
  ticketType: TicketUploadType,
  responses: UploadBatchApplyMappingMultipleResponse[]
): UploadBatchApplyMappingMultipleResponse {
  const files = responses.flatMap((response) => response.files);
  return {
    project_id: projectId,
    ticket_type: ticketType,
    files,
    totals: {
      total_files: files.length,
      applied: files.filter((file) => file.status === "APPLIED").length,
      skipped: files.filter((file) => file.status === "SKIPPED_ALREADY_APPLIED").length,
      failed: files.filter((file) =>
        ["FAILED", "FAILED_PARTIAL_OUTPUT"].includes(file.status)
      ).length,
      input_rows: files.reduce((total, file) => total + file.input_rows, 0),
      in_scope_rows: files.reduce((total, file) => total + file.in_scope_rows, 0),
      out_of_scope_rows: files.reduce((total, file) => total + file.out_of_scope_rows, 0),
      blank_assignment_group_rows: files.reduce(
        (total, file) => total + file.blank_assignment_group_rows,
        0
      ),
      assignment_group_not_in_inventory_rows: files.reduce(
        (total, file) => total + file.assignment_group_not_in_inventory_rows,
        0
      ),
      duplicate_skipped_rows: files.reduce(
        (total, file) => total + file.duplicate_skipped_rows,
        0
      ),
      failed_rows: files.reduce((total, file) => total + file.failed_rows, 0),
    },
  };
}

function TicketDetailsWorkflow({
  projectId,
  selectedProject,
}: {
  projectId: string;
  selectedProject: ProjectOption | null;
}) {
  const [ticketType, setTicketType] = useState<TicketUploadType>("INCIDENT");
  const [activeStep, setActiveStep] = useState<WorkflowStepId>("upload");
  const [files, setFiles] = useState<File[]>([]);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const isRefreshingBatchesRef = useRef(false);

  const [batches, setBatches] = useState<UploadBatch[]>([]);
  const [historicalBatches, setHistoricalBatches] = useState<UploadBatch[]>([]);
  const [selectedBatchId, setSelectedBatchId] = useState("");
  const [selectedBatchFiles, setSelectedBatchFiles] = useState<UploadedFile[]>([]);
  const [trackedJobs, setTrackedJobs] = useState<IngestionJob[]>([]);
  const [validationSummary, setValidationSummary] = useState<ValidationSummary | null>(null);

  const [uploadResult, setUploadResult] = useState<UploadMultipleResponse | null>(null);
  const [ingestResult, setIngestResult] = useState<UploadBatchIngestMultipleResponse | null>(null);
  const [normalizeResult, setNormalizeResult] =
    useState<UploadBatchNormalizeMultipleResponse | null>(null);

  const [sourceColumns, setSourceColumns] = useState<SourceColumn[]>([]);
  const [mapping, setMapping] = useState<Record<string, string>>({});
  const [mappingSource, setMappingSource] = useState<MappingSource | null>(null);
  const [mappingSaved, setMappingSaved] = useState(false);
  const [applyResult, setApplyResult] =
    useState<UploadBatchApplyMappingMultipleResponse | null>(null);
  const [selectedActionBatchIds, setSelectedActionBatchIds] = useState<string[]>([]);

  const [slaUploadResult, setSlaUploadResult] =
    useState<IncidentSlaMultiUploadResponse | null>(null);
  const [slaEnrichResult, setSlaEnrichResult] = useState<IncidentSlaEnrichResponse | null>(null);
  const [slaSummary, setSlaSummary] = useState<IncidentSlaSummaryResponse | null>(null);
  const [slaUploadHistory, setSlaUploadHistory] = useState<IncidentSlaUploadHistoryRow[]>([]);

  const [isUploading, setIsUploading] = useState(false);
  const [isIngesting, setIsIngesting] = useState(false);
  const [isNormalizing, setIsNormalizing] = useState(false);
  const [isLoadingBatches, setIsLoadingBatches] = useState(false);
  const [, setIsLoadingFiles] = useState(false);
  const [isLoadingColumns, setIsLoadingColumns] = useState(false);
  const [isLoadingSuggestion, setIsLoadingSuggestion] = useState(false);
  const [isSavingMapping, setIsSavingMapping] = useState(false);
  const [isApplyingMapping, setIsApplyingMapping] = useState(false);
  const [isSlaEnriching, setIsSlaEnriching] = useState(false);
  const [isLoadingSlaContext, setIsLoadingSlaContext] = useState(false);

  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const isSlaUpload = ticketType === "INCIDENT_SLA" || ticketType === "INCIDENT_OLA";
  const agreementType: AgreementType = ticketType === "INCIDENT_SLA" ? "sla" : "ola";
  const agreementLabel = agreementType.toUpperCase();
  const normalizedFields = useMemo(
    () => normalizedFieldsForUploadType(ticketType),
    [ticketType]
  );
  const importantFields = useMemo(
    () => importantFieldsForUploadType(ticketType),
    [ticketType]
  );
  const recordLabelPlural =
    ticketType === "PROBLEM"
      ? "Problem records"
      : ticketType === "CHANGE"
        ? "Change records"
        : "tickets";
  const uploadFileLabel =
    ticketType === "PROBLEM"
      ? "Problem Register Files"
      : ticketType === "CHANGE"
        ? "Change Register Files"
        : isSlaUpload
          ? `Incident ${agreementLabel} Files`
          : "Ticket Files";
  const usesProblemChangeWorkflow = ticketType === "PROBLEM" || ticketType === "CHANGE";

  const filteredBatches = useMemo(
    () =>
      batches.filter((batch) => !batch.ticket_type || batch.ticket_type === ticketType),
    [batches, ticketType]
  );
  const filteredHistoricalBatches = useMemo(
    () =>
      historicalBatches.filter((batch) => !batch.ticket_type || batch.ticket_type === ticketType),
    [historicalBatches, ticketType]
  );
  const visibleBatches = useMemo(
    () => [...filteredBatches, ...filteredHistoricalBatches],
    [filteredBatches, filteredHistoricalBatches]
  );
  const visibleBatchIds = useMemo(
    () => visibleBatches.map((batch) => batch.id),
    [visibleBatches]
  );
  const selectedBatch = useMemo(
    () => visibleBatches.find((batch) => batch.id === selectedBatchId) ?? null,
    [selectedBatchId, visibleBatches]
  );
  const selectedVisibleBatches = useMemo(
    () => visibleBatches.filter((batch) => selectedActionBatchIds.includes(batch.id)),
    [selectedActionBatchIds, visibleBatches]
  );
  const uploadedActionBatchIds = useMemo(
    () =>
      (uploadResult?.files ?? [])
        .map((fileResult) => fileResult.upload_batch_id)
        .filter((batchId): batchId is string => Boolean(batchId)),
    [uploadResult]
  );
  const duplicateTicketEntries = useMemo(
    () => Object.entries(validationSummary?.duplicate_ticket_ids ?? {}),
    [validationSummary]
  );
  const sourceColumnNames = useMemo(() => {
    const sourceNames = sourceColumns.map((sourceColumn) => sourceColumn.name);
    const mappedNames = Object.values(mapping).filter((value): value is string =>
      Boolean(value)
    );
    return Array.from(new Set([...sourceNames, ...mappedNames]));
  }, [mapping, sourceColumns]);

  const targetBatchIds = useMemo(() => {
    if (uploadedActionBatchIds.length > 0) {
      return uploadedActionBatchIds;
    }
    return selectedActionBatchIds;
  }, [selectedActionBatchIds, uploadedActionBatchIds]);
  const targetBatchKey = targetBatchIds.join("|");
  const actionBatchIds = useMemo(
    () => selectedActionBatchIds.filter((batchId) => targetBatchIds.includes(batchId)),
    [selectedActionBatchIds, targetBatchIds]
  );
  const workflowRows = useMemo<WorkflowBatchRow[]>(() => {
    const batchById = new Map<string, UploadBatch>();
    for (const batch of [...filteredBatches, ...filteredHistoricalBatches]) {
      batchById.set(batch.id, batch);
    }
    if (selectedBatch) {
      batchById.set(selectedBatch.id, selectedBatch);
    }

    const uploadByBatchId = new Map(
      (uploadResult?.files ?? [])
        .filter((fileResult) => fileResult.upload_batch_id)
        .map((fileResult) => [fileResult.upload_batch_id as string, fileResult])
    );
    const ingestByBatchId = new Map(
      (ingestResult?.batches ?? []).map((batchResult) => [
        batchResult.upload_batch_id,
        batchResult,
      ])
    );
    const jobByBatchId = new Map(trackedJobs.map((job) => [job.upload_batch_id, job]));
    const normalizeByBatchId = new Map(
      (normalizeResult?.batches ?? []).map((batchResult) => [
        batchResult.upload_batch_id,
        batchResult,
      ])
    );
    const applyByBatchId = new Map(
      (applyResult?.files ?? []).map((fileResult) => [
        fileResult.upload_batch_id,
        fileResult,
      ])
    );
    const selectedBatchFilename =
      selectedBatchFiles.map((file) => file.original_filename).join(", ") || null;

    return targetBatchIds.map((batchId) => {
      const batch = batchById.get(batchId);
      const upload = uploadByBatchId.get(batchId);
      const ingest = ingestByBatchId.get(batchId);
      const job = jobByBatchId.get(batchId);
      const normalize = normalizeByBatchId.get(batchId);
      const apply = applyByBatchId.get(batchId);
      const batchStatus = batch?.status ?? upload?.status ?? null;
      const batchHasNormalizedOutput = (batch?.normalized_ticket_count ?? 0) > 0;

      return {
        batchId,
        batchName: batch?.batch_name ?? upload?.filename ?? "Selected batch",
        filename: upload?.filename ?? (batchId === selectedBatchId ? selectedBatchFilename : null),
        uploadStatus: deriveUploadStageStatus(batchStatus),
        ingestStatus: deriveIngestStageStatus({
          batchStatus,
          ingestStatus: ingest?.status,
          jobStatus: job?.status,
        }),
        normalizeStatus: deriveNormalizeStageStatus({
          batchStatus,
          normalizeStatus: normalize?.status,
        }),
        applyStatus: deriveApplyStageStatus({
          batchStatus,
          applyStatus: apply?.status,
        }),
        inputRows:
          apply?.input_rows ??
          normalize?.raw_rows ??
          ingest?.raw_rows_inserted ??
          job?.rows_processed ??
          batch?.raw_row_count ??
          null,
        inScopeRows:
          apply?.in_scope_rows ??
          normalize?.in_scope_inserted ??
          (batchHasNormalizedOutput ? batch?.in_scope_ticket_count : null) ??
          (usesProblemChangeWorkflow && batchHasNormalizedOutput
            ? batch?.normalized_ticket_count
            : null) ??
          null,
        outOfScopeRows:
          apply?.out_of_scope_rows ??
          normalize?.out_of_scope_inserted ??
          (batchHasNormalizedOutput ? batch?.out_of_scope_ticket_count : null) ??
          null,
        duplicateSkippedRows:
          apply?.duplicate_skipped_rows ?? normalize?.duplicate_skipped_rows ?? null,
        remarks:
          apply?.error ??
          apply?.warnings?.[0] ??
          normalize?.errors?.[0] ??
          normalize?.warnings?.[0] ??
          ingest?.error ??
          upload?.message ??
          null,
      };
    });
  }, [
    applyResult,
    filteredBatches,
    filteredHistoricalBatches,
    ingestResult,
    normalizeResult,
    selectedBatch,
    selectedBatchFiles,
    selectedBatchId,
    targetBatchIds,
    trackedJobs,
    uploadResult,
  ]);

  const mappingWarnings = useMemo(() => {
    if (isSlaUpload) {
      return [];
    }

    const warnings: string[] = [];
    if (!projectId.trim()) {
      warnings.push("Select a customer before loading or applying a mapping.");
    }
    if (targetBatchIds.length === 0) {
      warnings.push("Upload files or select one or more batches before applying a mapping.");
    }
    for (const field of importantFields) {
      if (!mapping[field]) {
        warnings.push(`${field} is not mapped.`);
      }
    }
    return warnings;
  }, [importantFields, isSlaUpload, mapping, projectId, targetBatchIds.length]);

  const hasUploaded = isSlaUpload
    ? Boolean(slaUploadResult || slaUploadHistory.length > 0)
    : Boolean(uploadResult || selectedActionBatchIds.length > 0);
  const hasIngested = isSlaUpload
    ? hasUploaded
    : Boolean(
        ingestResult?.totals.batches_ingested ||
          selectedVisibleBatches.some((batch) =>
            ["INGESTED", "NORMALIZED", "COMPLETED"].includes(batch.status)
          ) ||
          selectedBatchFiles.some((file) => file.status === "INGESTED")
      );
  const hasNormalized = isSlaUpload
    ? hasUploaded
    : Boolean(
        normalizeResult ||
          selectedVisibleBatches.some((batch) =>
            ["NORMALIZED", "COMPLETED"].includes(batch.status)
          )
      );
  const hasMappingReady = isSlaUpload
    ? hasUploaded
    : sourceColumns.length > 0 || Object.keys(mapping).length > 0 || hasIngested;
  const hasApplyReady = isSlaUpload
    ? hasUploaded
    : Object.keys(cleanMapping(mapping)).length > 0 && actionBatchIds.length > 0;
  const hasSummary = isSlaUpload
    ? Boolean(slaUploadResult || slaEnrichResult || slaSummary)
    : Boolean(uploadResult || ingestResult || normalizeResult || applyResult);
  const selectedBatchCount = selectedActionBatchIds.length;
  const allVisibleBatchesSelected =
    visibleBatchIds.length > 0 &&
    visibleBatchIds.every((batchId) => selectedActionBatchIds.includes(batchId));
  const allActiveBatchesSelected =
    filteredBatches.length > 0 &&
    filteredBatches.every((batch) => selectedActionBatchIds.includes(batch.id));
  const allHistoricalBatchesSelected =
    filteredHistoricalBatches.length > 0 &&
    filteredHistoricalBatches.every((batch) => selectedActionBatchIds.includes(batch.id));

  const enabledSteps: Record<WorkflowStepId, boolean> = {
    upload: true,
    ingest: hasUploaded,
    normalize: hasIngested,
    mapping: hasMappingReady,
    apply: hasApplyReady,
    summary: hasSummary,
  };

  const refreshBatches = useCallback(async (options: { silent?: boolean } = {}) => {
    if (!projectId.trim() || isSlaUpload) {
      setBatches([]);
      setHistoricalBatches([]);
      return;
    }

    if (isRefreshingBatchesRef.current) {
      return;
    }

    isRefreshingBatchesRef.current = true;
    if (!options.silent) {
      setIsLoadingBatches(true);
      setError(null);
    }
    try {
      const [nextBatches, nextHistoricalBatches] = await Promise.all([
        listUploadBatches(projectId.trim(), "active"),
        listUploadBatches(projectId.trim(), "history"),
      ]);
      setBatches(nextBatches);
      setHistoricalBatches(nextHistoricalBatches);
    } catch (requestError) {
      if (!options.silent) {
        setError(requestError instanceof Error ? requestError.message : "Unable to load batches");
      }
    } finally {
      isRefreshingBatchesRef.current = false;
      if (!options.silent) {
        setIsLoadingBatches(false);
      }
    }
  }, [isSlaUpload, projectId]);

  const refreshSelectedBatchContext = useCallback(async (batchId: string) => {
    if (!batchId) {
      setSelectedBatchFiles([]);
      setValidationSummary(null);
      return;
    }

    setIsLoadingFiles(true);
    setError(null);
    try {
      const [nextFiles, nextValidationSummary] = await Promise.all([
        listUploadedFiles(batchId),
        getValidationSummary(batchId).catch(() => null),
      ]);
      setSelectedBatchFiles(nextFiles);
      setValidationSummary(nextValidationSummary);
    } catch (requestError) {
      setError(
        requestError instanceof Error ? requestError.message : "Unable to load batch details"
      );
    } finally {
      setIsLoadingFiles(false);
    }
  }, []);

  const refreshSlaContext = useCallback(
    async (showMessage = false) => {
      if (!projectId.trim() || !isSlaUpload) {
        setSlaSummary(null);
        setSlaUploadHistory([]);
        return;
      }

      setIsLoadingSlaContext(true);
      setError(null);
      try {
        const [nextSummary, nextHistory] = await Promise.all([
          getIncidentSlaSummary(projectId.trim(), agreementType),
          getIncidentSlaUploadHistory(projectId.trim(), agreementType),
        ]);
        setSlaSummary(nextSummary);
        setSlaUploadHistory(nextHistory);
        if (showMessage) {
          setMessage(`Incident ${agreementLabel} history and summary refreshed.`);
        }
      } catch (requestError) {
        setError(
          requestError instanceof Error
            ? requestError.message
            : `Unable to load Incident ${agreementLabel} context`
        );
      } finally {
        setIsLoadingSlaContext(false);
      }
    },
    [agreementLabel, agreementType, isSlaUpload, projectId]
  );

  const refreshTrackedIngestionJobs = useCallback(async () => {
    const jobIds = (uploadResult?.files ?? [])
      .map((fileResult) => fileResult.ingestion_job_id)
      .filter((jobId): jobId is string => Boolean(jobId));
    if (jobIds.length === 0) {
      return;
    }

    try {
      const refreshedJobs = await Promise.all(jobIds.map((jobId) => getIngestionJob(jobId)));
      setTrackedJobs(refreshedJobs);
    } catch {
      // Progress refresh is best-effort; the main action will surface hard failures.
    }
  }, [uploadResult]);

  const withProcessingRefresh = useCallback(
    async <T,>(operation: Promise<T>): Promise<T> => {
      const intervalId = window.setInterval(() => {
        void refreshBatches({ silent: true });
        void refreshTrackedIngestionJobs();
      }, 2000);
      try {
        return await operation;
      } finally {
        window.clearInterval(intervalId);
        await refreshBatches({ silent: true });
        await refreshTrackedIngestionJobs();
      }
    },
    [refreshBatches, refreshTrackedIngestionJobs]
  );

  useEffect(() => {
    void refreshBatches();
  }, [refreshBatches]);

  useEffect(() => {
    void refreshSelectedBatchContext(selectedBatchId);
  }, [refreshSelectedBatchContext, selectedBatchId]);

  useEffect(() => {
    void refreshSlaContext(false);
  }, [refreshSlaContext]);

  useEffect(() => {
    if (!projectId.trim() || isSlaUpload || !(isIngesting || isNormalizing || isApplyingMapping)) {
      return;
    }

    void refreshBatches({ silent: true });
    void refreshTrackedIngestionJobs();
    const intervalId = window.setInterval(() => {
      void refreshBatches({ silent: true });
      void refreshTrackedIngestionJobs();
    }, 2000);

    return () => {
      window.clearInterval(intervalId);
    };
  }, [
    isApplyingMapping,
    isIngesting,
    isNormalizing,
    isSlaUpload,
    projectId,
    refreshBatches,
    refreshTrackedIngestionJobs,
  ]);

  useEffect(() => {
    setSelectedActionBatchIds(targetBatchIds);
  }, [targetBatchKey]);

  useEffect(() => {
    setFiles([]);
    setUploadResult(null);
    setIngestResult(null);
    setNormalizeResult(null);
    setSelectedBatchId("");
    setSelectedActionBatchIds([]);
    setSourceColumns([]);
    setMapping({});
    setMappingSource(null);
    setMappingSaved(false);
    setApplyResult(null);
    setSlaUploadResult(null);
    setSlaEnrichResult(null);
    setActiveStep("upload");
    setMessage(null);
    setError(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  }, [projectId, ticketType]);

  function handleFileSelection(event: ChangeEvent<HTMLInputElement>) {
    setFiles(Array.from(event.target.files ?? []));
  }

  function handleSelectBatch(batchId: string) {
    setSelectedBatchId(batchId);
    setSelectedActionBatchIds((currentBatchIds) =>
      currentBatchIds.length === 0 && batchId ? [batchId] : currentBatchIds
    );
    setUploadResult(null);
    setIngestResult(null);
    setNormalizeResult(null);
    setApplyResult(null);
  }

  function toggleActionBatch(batchId: string) {
    setSelectedActionBatchIds((currentBatchIds) => {
      if (currentBatchIds.includes(batchId)) {
        return currentBatchIds.filter((currentBatchId) => currentBatchId !== batchId);
      }
      if (!selectedBatchId) {
        setSelectedBatchId(batchId);
      }
      return [...currentBatchIds, batchId];
    });
    setUploadResult(null);
    setIngestResult(null);
    setNormalizeResult(null);
    setApplyResult(null);
  }

  function setAllActionBatches(selected: boolean, batchIds = visibleBatchIds) {
    setSelectedActionBatchIds((currentBatchIds) => {
      if (selected) {
        return Array.from(new Set([...currentBatchIds, ...batchIds]));
      }
      const removeBatchIds = new Set(batchIds);
      return currentBatchIds.filter((batchId) => !removeBatchIds.has(batchId));
    });
    if (selected && batchIds.length > 0 && !selectedBatchId) {
      setSelectedBatchId(batchIds[0]);
    }
    setUploadResult(null);
    setIngestResult(null);
    setNormalizeResult(null);
    setApplyResult(null);
  }

  async function handleUpload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMessage(null);
    setError(null);

    if (!projectId.trim()) {
      setError("Select a customer before uploading files.");
      return;
    }
    if (files.length === 0) {
      setError("Select one or more CSV/XLSX files.");
      return;
    }

    setIsUploading(true);
    try {
      if (isSlaUpload) {
        const result = await uploadIncidentSlaFiles(projectId.trim(), files, agreementType);
        setSlaUploadResult(result);
        setSlaEnrichResult(null);
        setMessage(
          `Processed ${formatNumber(
            result.totals.total_files
          )} ${agreementLabel} file(s), inserted ${formatNumber(
            result.totals.inserted_rows
          )} row(s), skipped ${formatNumber(
            result.totals.duplicate_rows_skipped
          )} duplicate row(s).`
        );
        setFiles([]);
        if (fileInputRef.current) {
          fileInputRef.current.value = "";
        }
        await refreshSlaContext(false);
        setActiveStep("apply");
        return;
      }

      const uploadResponse = await uploadTicketFilesMultiple({
        projectId: projectId.trim(),
        ticketType,
        periodType: "SNAPSHOT",
        snapshotDate: getTodayDateInputValue(),
        batchName: createAutoBatchName(
          selectedProject?.customer_name ?? selectedProject?.name ?? "Customer",
          ticketType,
          files
        ),
        files,
      });
      setUploadResult(uploadResponse);
      setIngestResult(null);
      setNormalizeResult(null);
      setApplyResult(null);
      const refreshedJobs = await Promise.all(
        uploadResponse.files
          .map((fileResult) => fileResult.ingestion_job_id)
          .filter((jobId): jobId is string => Boolean(jobId))
          .map((jobId) => getIngestionJob(jobId))
      );
      setTrackedJobs(refreshedJobs);
      const firstUploadedBatchId =
        uploadResponse.files.find((fileResult) => fileResult.upload_batch_id)
          ?.upload_batch_id ?? "";
      setSelectedBatchId(firstUploadedBatchId);
      setFiles([]);
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
      setMessage(
        `Uploaded ${formatNumber(uploadResponse.totals.files_uploaded)} of ${formatNumber(
          uploadResponse.totals.files_selected
        )} selected file(s).`
      );
      await refreshBatches();
      setActiveStep("ingest");
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Upload failed");
    } finally {
      setIsUploading(false);
    }
  }

  async function handleIngestFiles() {
    setMessage(null);
    setError(null);
    if (!projectId.trim()) {
      setError("Select a customer before ingesting files.");
      return;
    }
    if (actionBatchIds.length === 0) {
      setError("Select at least one uploaded batch before ingesting files.");
      return;
    }

    setIsIngesting(true);
    setMessage("Ingestion started. Files will process sequentially with progress refreshes.");
    try {
      const projectKey = projectId.trim();
      const responses: UploadBatchIngestMultipleResponse[] = [];
      for (const [index, batchId] of actionBatchIds.entries()) {
        const batch = visibleBatches.find((candidate) => candidate.id === batchId);
        setSelectedBatchId(batchId);
        setMessage(
          `Ingesting file ${formatNumber(index + 1)} of ${formatNumber(
            actionBatchIds.length
          )}: ${batch?.batch_name ?? "selected batch"}.`
        );
        const partialResult = await withProcessingRefresh(
          ingestUploadBatches(projectKey, [batchId])
        );
        responses.push(partialResult);
        const combinedResult = combineIngestResponses(projectKey, responses);
        setIngestResult(combinedResult);
        await refreshBatches({ silent: true });
      }
      const result = combineIngestResponses(projectKey, responses);
      setIngestResult(result);
      setNormalizeResult(null);
      setMessage(
        `Ingested ${formatNumber(result.totals.batches_ingested)} batch(es), staging ${formatNumber(
          result.totals.raw_rows_inserted
        )} raw row(s).`
      );
      await refreshBatches();
      if (actionBatchIds[0]) {
        setSelectedBatchId(actionBatchIds[0]);
      }
      setActiveStep("normalize");
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "File ingestion failed");
    } finally {
      setIsIngesting(false);
    }
  }

  async function handleNormalizeFiles() {
    setMessage(null);
    setError(null);
    if (!projectId.trim()) {
      setError("Select a customer before normalizing files.");
      return;
    }
    if (actionBatchIds.length === 0) {
      setError("Select at least one ingested batch before normalizing files.");
      return;
    }

    if (usesProblemChangeWorkflow) {
      setNormalizeResult(null);
      setMessage(
        `${recordLabelPlural} are staged. Review and save the column mapping, then apply mapping to create normalized ${recordLabelPlural.toLowerCase()}.`
      );
      setActiveStep("mapping");
      return;
    }

    const confirmed = window.confirm(
      "This will normalize the selected/uploaded batch data. Raw uploaded files are preserved."
    );
    if (!confirmed) {
      return;
    }

    setIsNormalizing(true);
    setMessage("Normalization started. Files will process sequentially with progress refreshes.");
    try {
      const projectKey = projectId.trim();
      const responses: UploadBatchNormalizeMultipleResponse[] = [];
      for (const [index, batchId] of actionBatchIds.entries()) {
        const batch = visibleBatches.find((candidate) => candidate.id === batchId);
        setSelectedBatchId(batchId);
        setMessage(
          `Normalizing file ${formatNumber(index + 1)} of ${formatNumber(
            actionBatchIds.length
          )}: ${batch?.batch_name ?? "selected batch"}.`
        );
        const partialResult = await withProcessingRefresh(
          normalizeUploadBatches(projectKey, ticketType, [batchId], true)
        );
        responses.push(partialResult);
        setNormalizeResult(combineNormalizeResponses(projectKey, ticketType, responses));
        await refreshBatches({ silent: true });
      }
      const result = combineNormalizeResponses(projectKey, ticketType, responses);
      setNormalizeResult(result);
      setMessage(
        `Normalized ${formatNumber(result.totals.in_scope_inserted)} in-scope and ${formatNumber(
          result.totals.out_of_scope_inserted
        )} out-of-scope ticket(s).`
      );
      await refreshBatches();
      setActiveStep("mapping");
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Normalization failed");
    } finally {
      setIsNormalizing(false);
    }
  }

  async function handleLoadSourceColumns() {
    if (!projectId.trim()) {
      setError("Select a customer before loading source columns.");
      return;
    }

    setIsLoadingColumns(true);
    setError(null);
    setMessage(null);
    try {
      const response = await getSourceColumnsForTicketType(
        projectId.trim(),
        ticketType,
        selectedBatchId || undefined
      );
      setSourceColumns(response.source_columns);
      setMessage(`Loaded ${formatNumber(response.source_columns.length)} source column(s).`);
    } catch (requestError) {
      setError(
        requestError instanceof Error ? requestError.message : "Unable to load source columns"
      );
    } finally {
      setIsLoadingColumns(false);
    }
  }

  async function handleLoadSuggestedMapping() {
    if (!projectId.trim()) {
      setError("Select a customer before loading a suggested mapping.");
      return;
    }

    setIsLoadingSuggestion(true);
    setError(null);
    setMessage(null);
    try {
      const response = await getSuggestedMappingForTicketType(
        projectId.trim(),
        ticketType,
        selectedBatchId || undefined
      );
      setSourceColumns(
        response.source_columns.map((sourceColumn) => ({
          name: sourceColumn,
          normalized_name: sourceColumn,
          occurrence_count: 0,
        }))
      );
      setMapping(response.mapping);
      setMappingSource(response.mapping_source);
      setMappingSaved(response.mapping_source === "SAVED_TEMPLATE");
      setMessage(mappingSourceMessage(response.mapping_source));
    } catch (requestError) {
      setError(
        requestError instanceof Error ? requestError.message : "Unable to load suggested mapping"
      );
    } finally {
      setIsLoadingSuggestion(false);
    }
  }

  async function handleSaveMappingTemplate() {
    if (!projectId.trim()) {
      setError("Select a customer before saving a mapping.");
      return;
    }

    setIsSavingMapping(true);
    setError(null);
    setMessage(null);
    try {
      await saveMappingTemplate({
        projectId: projectId.trim(),
        ticketType,
        mapping: cleanMapping(mapping),
      });
      setMappingSource("SAVED_TEMPLATE");
      setMappingSaved(true);
      setMessage("Mapping saved for this customer and ticket type.");
      setActiveStep("apply");
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Unable to save mapping");
    } finally {
      setIsSavingMapping(false);
    }
  }

  async function handleApplyMapping() {
    if (!projectId.trim()) {
      setError("Select a customer before applying mapping.");
      return;
    }
    if (actionBatchIds.length === 0) {
      setError("Select at least one normalized batch before applying mapping.");
      return;
    }

    setIsApplyingMapping(true);
    setError(null);
    setMessage("Apply mapping started. Files will process sequentially with progress refreshes.");
    try {
      const projectKey = projectId.trim();
      const cleanedMapping = cleanMapping(mapping);
      const responses: UploadBatchApplyMappingMultipleResponse[] = [];
      for (const [index, batchId] of actionBatchIds.entries()) {
        const batch = visibleBatches.find((candidate) => candidate.id === batchId);
        setSelectedBatchId(batchId);
        setMessage(
          `Applying mapping to file ${formatNumber(index + 1)} of ${formatNumber(
            actionBatchIds.length
          )}: ${batch?.batch_name ?? "selected batch"}.`
        );
        const partialResult = await withProcessingRefresh(
          applyMappingToUploadBatches(
            projectKey,
            ticketType,
            [batchId],
            cleanedMapping,
            true,
            true
          )
        );
        responses.push(partialResult);
        setApplyResult(combineApplyResponses(projectKey, ticketType, responses));
        await refreshBatches({ silent: true });
      }
      const result = combineApplyResponses(projectKey, ticketType, responses);
      setApplyResult(result);
      setMessage(
        `Applied mapping to ${formatNumber(result.totals.applied)} batch(es), skipped ${formatNumber(
          result.totals.skipped
        )} already-applied batch(es), produced ${formatNumber(
          result.totals.in_scope_rows
        )} in-scope and ${formatNumber(result.totals.out_of_scope_rows)} out-of-scope row(s).`
      );
      await refreshBatches();
      setActiveStep("summary");
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Unable to apply mapping");
    } finally {
      setIsApplyingMapping(false);
    }
  }

  async function handleEnrichSla() {
    if (!projectId.trim()) {
      setError(`Select a customer before enriching Incident ${agreementLabel}s.`);
      return;
    }

    const confirmed = window.confirm(
      agreementType === "ola"
        ? "This will enrich in-scope and out-of-scope Incident tickets with vendor-specific OLA selections. SC Tasks are excluded."
        : "This will enrich in-scope and out-of-scope Incident tickets with end-to-end SLA selections matched by Incident number. SC Tasks are excluded."
    );
    if (!confirmed) {
      return;
    }

    setIsSlaEnriching(true);
    setError(null);
    setMessage(null);
    try {
      const result = await enrichIncidentSla(projectId.trim(), true, agreementType);
      setSlaEnrichResult(result);
      setMessage(`Incident ${agreementLabel} enrichment completed.`);
      await refreshSlaContext(false);
      setActiveStep("summary");
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : `Incident ${agreementLabel} enrichment failed`
      );
    } finally {
      setIsSlaEnriching(false);
    }
  }

  function renderWorkflowFileTable({
    title,
    selectable = true,
  }: {
    title: string;
    selectable?: boolean;
  }) {
    const allSelected = targetBatchIds.length > 0 && actionBatchIds.length === targetBatchIds.length;
    return (
      <div className="summary-block">
        <div className="workflow-file-heading">
          <p className="label">{title}</p>
          {selectable && workflowRows.length > 0 ? (
            <label className="checkbox-row compact-checkbox-row">
              <input
                checked={allSelected}
                type="checkbox"
                onChange={(event) => setAllActionBatches(event.target.checked)}
              />
              Select all files
            </label>
          ) : null}
        </div>
        <div className="scroll-frame compact-file-frame">
          {workflowRows.length === 0 ? (
            <p className="muted-text">No workflow files selected.</p>
          ) : (
            <table>
              <thead>
                <tr>
                  {selectable ? <th>Select</th> : null}
                  <th>Filename</th>
                  <th>Batch Name</th>
                  <th>Upload</th>
                  <th>Ingest</th>
                  <th>Normalize</th>
                  <th>Apply Mapping</th>
                  <th>Input Rows</th>
                  <th>In-Scope</th>
                  <th>Out-of-Scope</th>
                  <th>Duplicates</th>
                  <th>Remarks</th>
                </tr>
              </thead>
              <tbody>
                {workflowRows.map((row) => (
                  <tr key={row.batchId}>
                    {selectable ? (
                      <td>
                        <input
                          checked={actionBatchIds.includes(row.batchId)}
                          type="checkbox"
                          onChange={() => toggleActionBatch(row.batchId)}
                        />
                      </td>
                    ) : null}
                    <td>{row.filename ?? "-"}</td>
                    <td>{row.batchName}</td>
                    <td>{formatBatchStatus(row.uploadStatus)}</td>
                    <td>{formatBatchStatus(row.ingestStatus)}</td>
                    <td>{formatBatchStatus(row.normalizeStatus)}</td>
                    <td>{formatApplyStatus(row.applyStatus)}</td>
                    <td>{formatNumber(row.inputRows)}</td>
                    <td>{formatNumber(row.inScopeRows)}</td>
                    <td>{formatNumber(row.outOfScopeRows)}</td>
                    <td>{formatNumber(row.duplicateSkippedRows)}</td>
                    <td>{row.remarks ?? "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    );
  }

  function renderUploadStep() {
    return (
      <form className="workflow-step-panel" onSubmit={(event) => void handleUpload(event)}>
        <div className="upload-type-grid" role="radiogroup" aria-label="Upload type">
          {ticketUploadTypes.map((option) => (
            <button
              className={
                ticketType === option.value ? "upload-type-card active" : "upload-type-card"
              }
              key={option.value}
              type="button"
              onClick={() => setTicketType(option.value)}
            >
              <strong>{option.label}</strong>
              <span>{option.description}</span>
            </button>
          ))}
          {futureUploadTypes.map((label) => (
            <button className="upload-type-card disabled" disabled key={label} type="button">
              <strong>{label}</strong>
              <span>Coming later</span>
            </button>
          ))}
        </div>

        <div className="form-grid summary-block">
          <div className="info-card compact-info-card">
            <p className="label">Customer</p>
            <strong>{selectedProject?.customer_name ?? "Select customer above"}</strong>
            <span>{selectedProject?.name ?? "Ticket uploads use the shared selector."}</span>
          </div>
          <div className="info-card compact-info-card">
            <p className="label">Batch Naming</p>
            <strong>Generated automatically</strong>
            <span>Customer + source file + upload date/time</span>
          </div>
        </div>

        <label className="file-input">
          <span>{uploadFileLabel}</span>
          <input
            accept=".csv,.xlsx,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            multiple
            ref={fileInputRef}
            type="file"
            onChange={handleFileSelection}
          />
        </label>

        {files.length > 0 ? (
          <div className="scroll-frame compact-file-frame">
            <ul className="selected-files" aria-label="Selected files">
              {files.map((file) => (
                <li key={`${file.name}-${file.size}`}>
                  <span>{file.name}</span>
                  <span>{formatBytes(file.size)}</span>
                </li>
              ))}
            </ul>
          </div>
        ) : (
          <p className="muted-text summary-block">No files selected.</p>
        )}

        <div className="action-row">
          <button
            className="primary-button"
            disabled={isUploading || !projectId.trim() || files.length === 0}
            type="submit"
          >
            {isUploading
              ? "Uploading..."
              : isSlaUpload
                ? `Upload ${agreementLabel} Files`
                : "Upload Files"}
          </button>
          <button
            className="secondary-button"
            disabled={files.length === 0}
            type="button"
            onClick={() => {
              setFiles([]);
              if (fileInputRef.current) {
                fileInputRef.current.value = "";
              }
            }}
          >
            Clear Selection
          </button>
        </div>

        {uploadResult ? (
          <div className="summary-block">
            <div className="summary-grid">
              <MetricCard label="Selected" value={formatNumber(uploadResult.totals.files_selected)} />
              <MetricCard label="Uploaded" value={formatNumber(uploadResult.totals.files_uploaded)} />
              <MetricCard label="Failed" value={formatNumber(uploadResult.totals.files_failed)} />
              <MetricCard label="Next Step" value="Ingest" helper="Use the Ingest Files step." />
            </div>
          </div>
        ) : null}

        {slaUploadResult ? (
          <div className="summary-block">
            <div className="summary-grid">
              <MetricCard
                label={`${agreementLabel} Files`}
                value={formatNumber(slaUploadResult.totals.total_files)}
              />
              <MetricCard
                label="Rows Read"
                value={formatNumber(slaUploadResult.totals.total_rows_read)}
              />
              <MetricCard label="Inserted" value={formatNumber(slaUploadResult.totals.inserted_rows)} />
              <MetricCard
                label="Duplicates Skipped"
                value={formatNumber(slaUploadResult.totals.duplicate_rows_skipped)}
              />
            </div>
          </div>
        ) : null}
      </form>
    );
  }

  function renderIngestStep() {
    if (isSlaUpload) {
      return (
        <InfoPanel title="Ingest">
          <p className="muted-text">
            Not required for Incident {agreementLabel} files. The upload parses and loads staging
            rows during upload, then enrichment runs in the Apply / Enrich step.
          </p>
        </InfoPanel>
      );
    }

    return (
      <div className="workflow-step-panel">
        <div className="panel-heading compact-heading">
          <div>
            <p className="label">Ingest</p>
            <h2>Stage Uploaded Files</h2>
          </div>
          <button
            className="primary-button"
            disabled={isIngesting || actionBatchIds.length === 0}
            type="button"
            onClick={() => void handleIngestFiles()}
          >
            {isIngesting ? "Ingesting..." : "Ingest Files"}
          </button>
        </div>

        {renderWorkflowFileTable({ title: "Files Ready for Ingest" })}

        {ingestResult ? (
          <div className="summary-grid summary-block">
            <MetricCard label="Requested" value={formatNumber(ingestResult.totals.batches_requested)} />
            <MetricCard label="Ingested" value={formatNumber(ingestResult.totals.batches_ingested)} />
            <MetricCard label="Failed" value={formatNumber(ingestResult.totals.batches_failed)} />
            <MetricCard label="Rows Staged" value={formatNumber(ingestResult.totals.raw_rows_inserted)} />
          </div>
        ) : null}
      </div>
    );
  }

  function renderNormalizeStep() {
    if (isSlaUpload) {
      return (
        <InfoPanel title="Normalize">
          <p className="muted-text">
            Not required for Incident {agreementLabel} files. Enrichment uses uploaded{" "}
            {agreementLabel} staging rows and does not create SC Task agreement records.
          </p>
        </InfoPanel>
      );
    }

    return (
      <div className="workflow-step-panel">
        <div className="panel-heading compact-heading">
          <div>
            <p className="label">Normalize</p>
            <h2>
              {usesProblemChangeWorkflow
                ? `Review ${recordLabelPlural} Mapping`
                : "Split In-Scope and Out-of-Scope Tickets"}
            </h2>
          </div>
          <button
            className="primary-button"
            disabled={isNormalizing || actionBatchIds.length === 0}
            type="button"
            onClick={() => void handleNormalizeFiles()}
          >
            {isNormalizing
              ? "Normalizing..."
              : usesProblemChangeWorkflow
                ? "Continue to Mapping"
                : "Normalize Files"}
          </button>
        </div>

        {renderWorkflowFileTable({
          title: usesProblemChangeWorkflow
            ? "Files Ready for Mapping"
            : "Files Ready for Normalize",
        })}

        {normalizeResult ? (
          <div className="summary-grid summary-block">
            <MetricCard label="Raw Rows" value={formatNumber(normalizeResult.totals.raw_rows)} />
            <MetricCard
              label="In Scope"
              value={formatNumber(normalizeResult.totals.in_scope_inserted)}
            />
            <MetricCard
              label="Out of Scope"
              value={formatNumber(normalizeResult.totals.out_of_scope_inserted)}
            />
            <MetricCard
              label="Not in Scope Reference"
              value={formatNumber(normalizeResult.totals.assignment_group_not_in_inventory_rows)}
            />
            <MetricCard
              label="Duplicates Skipped"
              value={formatNumber(normalizeResult.totals.duplicate_skipped_rows)}
            />
            <MetricCard label="Failed Batches" value={formatNumber(normalizeResult.totals.failed_batches)} />
          </div>
        ) : null}
      </div>
    );
  }

  function renderMappingStep() {
    if (isSlaUpload) {
      return (
        <InfoPanel title="Column Mapping">
          <p className="muted-text">
            Column mapping is not required for Incident {agreementLabel} files. Agreement files use
            fixed parsing and {agreementType === "ola" ? "vendor-specific OLA" : "end-to-end SLA"}{" "}
            enrichment rules.
          </p>
        </InfoPanel>
      );
    }

    return (
      <div className="workflow-step-panel">
        <div className="panel-heading compact-heading">
          <div>
            <p className="label">Column Mapping</p>
            <h2>Map Source Columns to Normalized Fields</h2>
          </div>
          <div className="panel-actions">
            <button
              className="secondary-button"
              disabled={!projectId.trim() || isLoadingColumns}
              type="button"
              onClick={() => void handleLoadSourceColumns()}
            >
              {isLoadingColumns ? "Loading..." : "Load Source Columns"}
            </button>
            <button
              className="secondary-button"
              disabled={!projectId.trim() || isLoadingSuggestion}
              type="button"
              onClick={() => void handleLoadSuggestedMapping()}
            >
              {isLoadingSuggestion ? "Loading..." : "Suggested Mapping"}
            </button>
            <button
              className="secondary-button"
              type="button"
              onClick={() => {
                setMapping({});
                setMappingSource(null);
                setMappingSaved(false);
                setApplyResult(null);
              }}
            >
              Clear Mapping
            </button>
            <button
              className="primary-button"
              disabled={!projectId.trim() || isSavingMapping}
              type="button"
              onClick={() => void handleSaveMappingTemplate()}
            >
              {isSavingMapping ? "Saving..." : "Save Mapping"}
            </button>
          </div>
        </div>

        <div className="summary-grid">
          <MetricCard
            label="Customer"
            value={selectedProject?.customer_name ?? "Not selected"}
            helper={selectedProject?.name}
          />
          <MetricCard label="Ticket Type" value={ticketType} />
          <MetricCard label="Source Columns" value={formatNumber(sourceColumns.length)} />
          <MetricCard label="Mapping Source" value={mappingSource ?? "Not loaded"} />
        </div>

        {renderWorkflowFileTable({ title: "Files in This Workflow", selectable: false })}
        <p className="muted-text summary-block">
          Source columns are loaded from the selected representative batch when one is selected.
          The saved mapping is applied to all checked ready files in the Apply Mapping step.
        </p>

        {mappingWarnings.length > 0 ? (
          <div className="warning-list">
            {mappingWarnings.map((warning) => (
              <p key={warning}>{warning}</p>
            ))}
          </div>
        ) : null}

        <div className="scroll-frame mapping-scroll-frame summary-block">
          <table>
            <thead>
              <tr>
                <th>Normalized Field</th>
                <th>Source Column</th>
              </tr>
            </thead>
            <tbody>
              {normalizedFields.map((field) => (
                <tr key={field}>
                  <td className="mono-text">{field}</td>
                  <td>
                    <select
                      value={mapping[field] ?? ""}
                      onChange={(event) =>
                        setMapping((currentMapping) => ({
                          ...currentMapping,
                          [field]: event.target.value,
                        }))
                      }
                    >
                      <option value="">Unmapped</option>
                      {sourceColumnNames.map((sourceColumn) => (
                        <option key={sourceColumn} value={sourceColumn}>
                          {sourceColumn}
                        </option>
                      ))}
                    </select>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    );
  }

  function renderApplyStep() {
    if (isSlaUpload) {
      return (
        <div className="workflow-step-panel">
          <div className="panel-heading compact-heading">
            <div>
              <p className="label">Enrich {agreementLabel}s</p>
              <h2>
                {agreementType === "ola"
                  ? "Vendor-Specific Incident OLA Enrichment"
                  : "End-to-End Incident SLA Enrichment"}
              </h2>
            </div>
            <button
              className="primary-button"
              disabled={!projectId.trim() || isSlaEnriching}
              type="button"
              onClick={() => void handleEnrichSla()}
            >
              {isSlaEnriching ? "Enriching..." : `Enrich Incident ${agreementLabel}s`}
            </button>
          </div>
          <p className="muted-text">
            Uses all uploaded {agreementLabel} rows for the selected customer. In-scope and
            out-of-scope Incident tickets are enriched; SC Tasks are excluded.
          </p>
          {slaEnrichResult ? (
            <div className="summary-grid summary-block">
              <MetricCard
                label="In-Scope Matched"
                value={formatNumber(slaEnrichResult.in_scope.incident_tickets_matched_to_sla_rows)}
              />
              <MetricCard
                label="In-Scope Enriched"
                value={formatNumber(slaEnrichResult.in_scope.incident_tickets_enriched)}
              />
              <MetricCard
                label="Out-of-Scope Matched"
                value={formatNumber(
                  slaEnrichResult.out_of_scope.incident_tickets_matched_to_sla_rows
                )}
              />
              <MetricCard
                label="Out-of-Scope Enriched"
                value={formatNumber(slaEnrichResult.out_of_scope.incident_tickets_enriched)}
              />
            </div>
          ) : null}
        </div>
      );
    }

    return (
      <div className="workflow-step-panel">
        <div className="panel-heading compact-heading">
          <div>
            <p className="label">Apply Mapping</p>
            <h2>
              {usesProblemChangeWorkflow
                ? `Finalize ${recordLabelPlural}`
                : "Finalize Normalized Ticket Data"}
            </h2>
          </div>
          <button
            className="primary-button"
            disabled={!hasApplyReady || isApplyingMapping}
            type="button"
            onClick={() => void handleApplyMapping()}
          >
            {isApplyingMapping ? "Applying..." : "Apply Mapping to Files"}
          </button>
        </div>
        <p className="muted-text">
          Applies the saved/current mapping only to the checked files below. Already-applied files
          are skipped so historical batches are not duplicated.
        </p>
        {renderWorkflowFileTable({ title: "Files Ready for Mapping" })}
        {mappingSaved ? (
          <p className="success-text summary-block">A saved mapping is available for this ticket type.</p>
        ) : null}
        {applyResult ? (
          <div className="summary-grid summary-block">
            <MetricCard label="Files Applied" value={formatNumber(applyResult.totals.applied)} />
            <MetricCard label="Already Applied" value={formatNumber(applyResult.totals.skipped)} />
            <MetricCard label="Failed" value={formatNumber(applyResult.totals.failed)} />
            <MetricCard label="Raw Rows" value={formatNumber(applyResult.totals.input_rows)} />
            <MetricCard
              label="In Scope"
              value={formatNumber(applyResult.totals.in_scope_rows)}
            />
            <MetricCard
              label="Out of Scope"
              value={formatNumber(applyResult.totals.out_of_scope_rows)}
            />
            <MetricCard
              label="Not in Scope Reference"
              value={formatNumber(applyResult.totals.assignment_group_not_in_inventory_rows)}
            />
            <MetricCard
              label="Duplicates Skipped"
              value={formatNumber(applyResult.totals.duplicate_skipped_rows)}
            />
            <MetricCard label="Failed Rows" value={formatNumber(applyResult.totals.failed_rows)} />
          </div>
        ) : null}
      </div>
    );
  }

  function renderSummaryStep() {
    if (isSlaUpload) {
      return (
        <div className="workflow-step-panel">
          <div className="summary-grid">
            <MetricCard
              label={`${agreementLabel} Files Uploaded`}
              value={formatNumber(slaUploadResult?.totals.total_files ?? slaUploadHistory.length)}
            />
            <MetricCard
              label="Rows Read"
              value={formatNumber(slaUploadResult?.totals.total_rows_read ?? slaSummary?.total_sla_rows)}
            />
            <MetricCard
              label="Rows Inserted"
              value={formatNumber(slaUploadResult?.totals.inserted_rows)}
            />
            <MetricCard
              label="Duplicates Skipped"
              value={formatNumber(slaUploadResult?.totals.duplicate_rows_skipped)}
            />
            <MetricCard
              label="In-Scope Matched"
              value={formatNumber(slaEnrichResult?.in_scope.incident_tickets_matched_to_sla_rows)}
            />
            <MetricCard
              label="In-Scope Enriched"
              value={formatNumber(slaEnrichResult?.in_scope.incident_tickets_enriched)}
            />
            <MetricCard
              label="Out-of-Scope Matched"
              value={formatNumber(
                slaEnrichResult?.out_of_scope.incident_tickets_matched_to_sla_rows
              )}
            />
            <MetricCard
              label="Out-of-Scope Enriched"
              value={formatNumber(slaEnrichResult?.out_of_scope.incident_tickets_enriched)}
            />
            <MetricCard
              label="Response Vendor / Default / Fallback / Not Found"
              value={
                slaEnrichResult
                  ? `${formatNumber(slaEnrichResult.in_scope.response_vendor_specific + slaEnrichResult.out_of_scope.response_vendor_specific)} / ${formatNumber(
                      slaEnrichResult.in_scope.response_default + slaEnrichResult.out_of_scope.response_default
                    )} / ${formatNumber(
                      slaEnrichResult.in_scope.response_fallback_default +
                        slaEnrichResult.out_of_scope.response_fallback_default
                    )} / ${formatNumber(
                      slaEnrichResult.in_scope.response_not_found + slaEnrichResult.out_of_scope.response_not_found
                    )}`
                  : "Not available"
              }
            />
            <MetricCard
              label="Resolution Vendor / Default / Fallback / Not Found"
              value={
                slaEnrichResult
                  ? `${formatNumber(slaEnrichResult.in_scope.resolution_vendor_specific + slaEnrichResult.out_of_scope.resolution_vendor_specific)} / ${formatNumber(
                      slaEnrichResult.in_scope.resolution_default + slaEnrichResult.out_of_scope.resolution_default
                    )} / ${formatNumber(
                      slaEnrichResult.in_scope.resolution_fallback_default +
                        slaEnrichResult.out_of_scope.resolution_fallback_default
                    )} / ${formatNumber(
                      slaEnrichResult.in_scope.resolution_not_found + slaEnrichResult.out_of_scope.resolution_not_found
                    )}`
                  : "Not available"
              }
            />
          </div>
        </div>
      );
    }

    return (
      <div className="workflow-step-panel">
        <div className="summary-grid">
          <MetricCard
            label="Files Uploaded"
            value={formatNumber(uploadResult?.totals.files_uploaded ?? selectedBatchFiles.length)}
          />
          <MetricCard
            label="Files Ingested"
            value={formatNumber(ingestResult?.totals.batches_ingested)}
          />
          <MetricCard
            label="Files Normalized"
            value={formatNumber(
              normalizeResult?.batches.filter((batch) => batch.status === "NORMALIZED").length
            )}
          />
          <MetricCard
            label="Files Mapping Applied"
            value={formatNumber(
              applyResult
                ? applyResult.totals.applied + applyResult.totals.skipped
                : undefined
            )}
          />
          <MetricCard
            label="Input Rows"
            value={formatNumber(
              applyResult?.totals.input_rows ??
                normalizeResult?.totals.raw_rows ??
                validationSummary?.total_raw_rows
            )}
          />
          <MetricCard
            label="In-Scope Output"
            value={formatNumber(
              applyResult?.totals.in_scope_rows ?? normalizeResult?.totals.in_scope_inserted
            )}
          />
          <MetricCard
            label="Out-of-Scope Output"
            value={formatNumber(
              applyResult?.totals.out_of_scope_rows ?? normalizeResult?.totals.out_of_scope_inserted
            )}
          />
          <MetricCard
            label="Duplicates Skipped"
            value={formatNumber(
              applyResult?.totals.duplicate_skipped_rows ??
                normalizeResult?.totals.duplicate_skipped_rows
            )}
          />
          <MetricCard
            label="Blank Assignment Group"
            value={formatNumber(applyResult?.totals.blank_assignment_group_rows)}
          />
          <MetricCard
            label="Not in Scope Reference"
            value={formatNumber(applyResult?.totals.assignment_group_not_in_inventory_rows)}
          />
          <MetricCard label="Vendor Populated" value="Covered" helper="Derived during mapping/enrichment." />
          <MetricCard label="Derived Vendor Populated" value="Covered" helper="Uses Application Inventory." />
          <MetricCard label="Functional Track Populated" value="Covered" helper="Uses Assignment Group Scope." />
          <MetricCard label="In Scope Flag Populated" value="Covered" helper="Uses Assignment Group Scope." />
          <MetricCard
            label="Parent Business Application Populated"
            value="Covered"
            helper="Uses Application Inventory."
          />
          <MetricCard label="Application Owner Populated" value="Covered" helper="Uses Application Inventory." />
          <MetricCard label="Support Lead Populated" value="Covered" helper="Uses Application Inventory." />
        </div>

        {renderWorkflowFileTable({ title: "Per-File Processing Summary", selectable: false })}

        {duplicateTicketEntries.length > 0 ? (
          <div className="summary-block">
            <p className="label">Duplicate Ticket ID Sample</p>
            <div className="chip-list">
              {duplicateTicketEntries.slice(0, 12).map(([ticketId, count]) => (
                <span className="chip" key={ticketId}>
                  {ticketId} ({count})
                </span>
              ))}
            </div>
          </div>
        ) : null}
      </div>
    );
  }

  function renderCurrentStep() {
    if (activeStep === "upload") {
      return renderUploadStep();
    }
    if (activeStep === "ingest") {
      return renderIngestStep();
    }
    if (activeStep === "normalize") {
      return renderNormalizeStep();
    }
    if (activeStep === "mapping") {
      return renderMappingStep();
    }
    if (activeStep === "apply") {
      return renderApplyStep();
    }
    return renderSummaryStep();
  }

  return (
    <div className="ticket-workflow">
      <section className="panel">
        <div className="panel-heading">
          <div>
            <p className="label">Ticket Details</p>
            <h2>Guided Upload and Processing Workflow</h2>
          </div>
          <button
            className="secondary-button"
            disabled={isSlaUpload ? isLoadingSlaContext : isLoadingBatches}
            type="button"
            onClick={() => {
              if (isSlaUpload) {
                void refreshSlaContext(true);
              } else {
                void refreshBatches();
              }
            }}
          >
            {isSlaUpload
              ? isLoadingSlaContext
                ? "Refreshing..."
                : `Refresh ${agreementLabel} Context`
              : isLoadingBatches
                ? "Refreshing..."
                : "Refresh Batches"}
          </button>
        </div>

        <div className="workflow-steps" aria-label="Ticket processing steps">
          {workflowSteps.map((step, index) => {
            const enabled = enabledSteps[step.id];
            const active = activeStep === step.id;
            return (
              <button
                className={active ? "workflow-step active" : "workflow-step"}
                disabled={!enabled}
                key={step.id}
                type="button"
                onClick={() => setActiveStep(step.id)}
              >
                <span>{index + 1}</span>
                <strong>{step.label}</strong>
                <small>{enabled ? step.helper : "Locked"}</small>
              </button>
            );
          })}
        </div>

        <div className="message-stack" role="status" aria-live="polite">
          {message ? <p className="success-text">{message}</p> : null}
          {error ? <p className="error-text">{error}</p> : null}
        </div>
      </section>

      <section className="panel workflow-content-panel">{renderCurrentStep()}</section>

      {!isSlaUpload ? (
        <section className="panel" aria-labelledby="batch-history-heading">
          <div className="panel-heading compact-heading">
            <div>
              <p className="label">Status History</p>
              <h2 id="batch-history-heading">Active and Historical Batches</h2>
              <p className="muted-text">
                Check one or more batches for the next ingest, normalize, or apply-mapping action.
                Click a batch name to use it as the representative file for source-column preview.
              </p>
            </div>
            <div className="panel-actions">
              <label className="checkbox-row compact-checkbox-row">
                <input
                  checked={allVisibleBatchesSelected}
                  disabled={visibleBatchIds.length === 0}
                  type="checkbox"
                  onChange={(event) =>
                    setAllActionBatches(event.target.checked, visibleBatchIds)
                  }
                />
                Select all visible
              </label>
              <button
                className="secondary-button"
                disabled={selectedBatchCount === 0}
                type="button"
                onClick={() => setAllActionBatches(false, visibleBatchIds)}
              >
                Deselect all
              </button>
              <span className="muted-text">{formatNumber(selectedBatchCount)} selected</span>
            </div>
          </div>
          <div className="split-grid">
            <div>
              <div className="workflow-file-heading">
                <p className="label">Active Batches</p>
                {filteredBatches.length > 0 ? (
                  <label className="checkbox-row compact-checkbox-row">
                    <input
                      checked={allActiveBatchesSelected}
                      type="checkbox"
                      onChange={(event) =>
                        setAllActionBatches(
                          event.target.checked,
                          filteredBatches.map((batch) => batch.id)
                        )
                      }
                    />
                    Select active
                  </label>
                ) : null}
              </div>
              <div className="scroll-frame compact-file-frame summary-block">
                {filteredBatches.length === 0 ? (
                  <p className="muted-text">No active batches for this upload type.</p>
                ) : (
                  <table>
                    <thead>
                      <tr>
                        <th>Select</th>
                        <th>Batch</th>
                        <th>Status</th>
                        <th>Files</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredBatches.map((batch) => (
                        <tr
                          className={batch.id === selectedBatchId ? "selected-row" : ""}
                          key={batch.id}
                        >
                          <td>
                            <input
                              aria-label={`Select ${batch.batch_name}`}
                              checked={selectedActionBatchIds.includes(batch.id)}
                              type="checkbox"
                              onChange={() => toggleActionBatch(batch.id)}
                            />
                          </td>
                          <td>
                            <button
                              className="link-button"
                              type="button"
                              onClick={() => handleSelectBatch(batch.id)}
                            >
                              {batch.batch_name}
                            </button>
                          </td>
                          <td>{formatBatchStatus(batch.status)}</td>
                          <td>{batch.uploaded_file_count ?? batch.file_count}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            </div>
            <div>
              <div className="workflow-file-heading">
                <p className="label">Historical Batches</p>
                {filteredHistoricalBatches.length > 0 ? (
                  <label className="checkbox-row compact-checkbox-row">
                    <input
                      checked={allHistoricalBatchesSelected}
                      type="checkbox"
                      onChange={(event) =>
                        setAllActionBatches(
                          event.target.checked,
                          filteredHistoricalBatches.map((batch) => batch.id)
                        )
                      }
                    />
                    Select historical
                  </label>
                ) : null}
              </div>
              <div className="scroll-frame compact-file-frame summary-block">
                {filteredHistoricalBatches.length === 0 ? (
                  <p className="muted-text">No historical batches for this upload type.</p>
                ) : (
                  <table>
                    <thead>
                      <tr>
                        <th>Select</th>
                        <th>Batch</th>
                        <th>Status</th>
                        <th>Output Rows</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredHistoricalBatches.map((batch) => (
                        <tr
                          className={batch.id === selectedBatchId ? "selected-row" : ""}
                          key={batch.id}
                        >
                          <td>
                            <input
                              aria-label={`Select ${batch.batch_name}`}
                              checked={selectedActionBatchIds.includes(batch.id)}
                              type="checkbox"
                              onChange={() => toggleActionBatch(batch.id)}
                            />
                          </td>
                          <td>
                            <button
                              className="link-button"
                              type="button"
                              onClick={() => handleSelectBatch(batch.id)}
                            >
                              {batch.batch_name}
                            </button>
                          </td>
                          <td>{formatBatchStatus(batch.status)}</td>
                          <td>{formatNumber(batch.normalized_ticket_count)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            </div>
          </div>
        </section>
      ) : null}
    </div>
  );
}

function UploadCenter() {
  const [activeTab, setActiveTab] = useState<UploadCenterTab>("application-inventory");
  const [projectId, setProjectId] = useState("");
  const [selectedProject, setSelectedProject] = useState<ProjectOption | null>(null);
  const [stateResetToken, setStateResetToken] = useState(0);

  function clearUploadCenterState() {
    setActiveTab("application-inventory");
    setProjectId("");
    setSelectedProject(null);
    setStateResetToken((currentToken) => currentToken + 1);
  }

  return (
    <section className="upload-center-layout" aria-labelledby="upload-center-heading">
      <div className="panel upload-center-header">
        <div className="panel-heading">
          <div>
            <p className="label">Upload Center</p>
            <h2 id="upload-center-heading">Data Loading and Processing</h2>
          </div>
          <button className="secondary-button" type="button" onClick={clearUploadCenterState}>
            Clear Upload Center State
          </button>
        </div>
        <div className="form-grid">
          <CustomerSelector
            projectId={projectId}
            onProjectIdChange={setProjectId}
            onProjectChange={setSelectedProject}
          />
          <div className="info-card compact-info-card">
            <p className="label">Selected Context</p>
            <strong>{selectedProject?.customer_name ?? "No customer selected"}</strong>
            <span>{selectedProject?.name ?? "Choose a customer/project to continue."}</span>
          </div>
        </div>
      </div>

      <div className="section-tabs" role="tablist" aria-label="Upload Center sections">
        <button
          className={activeTab === "application-inventory" ? "section-tab active" : "section-tab"}
          type="button"
          onClick={() => setActiveTab("application-inventory")}
        >
          Application Inventory
        </button>
        <button
          className={activeTab === "ticket-details" ? "section-tab active" : "section-tab"}
          type="button"
          onClick={() => setActiveTab("ticket-details")}
        >
          Ticket Details
        </button>
      </div>

      <div className="tab-panel" hidden={activeTab !== "application-inventory"}>
        <ApplicationInventory
          key={`application-inventory-${stateResetToken}`}
          embedded
          projectId={projectId}
          selectedProject={selectedProject}
          onProjectIdChange={setProjectId}
          onProjectChange={setSelectedProject}
        />
      </div>
      <div className="tab-panel" hidden={activeTab !== "ticket-details"}>
        <TicketDetailsWorkflow
          key={`ticket-details-${stateResetToken}`}
          projectId={projectId}
          selectedProject={selectedProject}
        />
      </div>
    </section>
  );
}

export default UploadCenter;
