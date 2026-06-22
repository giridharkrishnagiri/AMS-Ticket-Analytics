import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ChangeEvent, FormEvent, ReactNode } from "react";

import ApplicationInventory from "./ApplicationInventory";
import CustomerSelector from "./CustomerSelector";
import {
  applyMappingForScope,
  getSourceColumnsForTicketType,
  getSuggestedMappingForTicketType,
  saveMappingTemplate,
} from "./api/mappings";
import type {
  ApplyScope,
  MappingSource,
  ScopedApplyMappingResponse,
  SourceColumn,
} from "./api/mappings";
import type { ProjectOption } from "./api/projects";
import {
  enrichIncidentSla,
  getIncidentSlaSummary,
  getIncidentSlaUploadHistory,
  uploadIncidentSlaFiles,
} from "./api/sla";
import type {
  IncidentSlaEnrichResponse,
  IncidentSlaMultiUploadResponse,
  IncidentSlaSummaryResponse,
  IncidentSlaUploadHistoryRow,
} from "./api/sla";
import {
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
  UploadBatch,
  UploadBatchIngestMultipleResponse,
  UploadBatchNormalizeMultipleResponse,
  UploadMultipleResponse,
  UploadedFile,
  ValidationSummary,
} from "./api/uploads";

type UploadCenterTab = "application-inventory" | "ticket-details";
type TicketUploadType = "INCIDENT" | "SERVICE_CATALOG_TASK" | "INCIDENT_SLA";
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
    label: "Incident SLAs",
    value: "INCIDENT_SLA",
    description: "Incident SLA dump files",
  },
];

const futureUploadTypes = [
  "Problem Tickets",
  "Change Tickets",
  "SC Task SLAs",
];

const workflowSteps: WorkflowStep[] = [
  { id: "upload", label: "Upload", helper: "Select type and files" },
  { id: "ingest", label: "Ingest", helper: "Stage source rows" },
  { id: "normalize", label: "Normalize", helper: "Split in-scope data" },
  { id: "mapping", label: "Column Mapping", helper: "Map source columns" },
  { id: "apply", label: "Apply / Enrich", helper: "Finalize processing" },
  { id: "summary", label: "Summary", helper: "Review results" },
];

const normalizedFields = [
  "ticket_id",
  "title",
  "description",
  "status",
  "priority",
  "urgency",
  "impact",
  "category",
  "subcategory",
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

const importantFields = ["ticket_id", "title", "created_at"];

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

function formatDate(value: string | null | undefined): string {
  if (!value) {
    return "Not available";
  }
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString();
}

function formatBatchPeriod(batch: UploadBatch): string {
  if (batch.period_type === "SNAPSHOT") {
    return `Snapshot ${batch.snapshot_date ?? "No date"}`;
  }
  return `Monthly ${batch.month_key ?? "No month"}`;
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
  const [applyResult, setApplyResult] = useState<ScopedApplyMappingResponse | null>(null);

  const [slaUploadResult, setSlaUploadResult] =
    useState<IncidentSlaMultiUploadResponse | null>(null);
  const [slaEnrichResult, setSlaEnrichResult] = useState<IncidentSlaEnrichResponse | null>(null);
  const [slaSummary, setSlaSummary] = useState<IncidentSlaSummaryResponse | null>(null);
  const [slaUploadHistory, setSlaUploadHistory] = useState<IncidentSlaUploadHistoryRow[]>([]);

  const [isUploading, setIsUploading] = useState(false);
  const [isIngesting, setIsIngesting] = useState(false);
  const [isNormalizing, setIsNormalizing] = useState(false);
  const [isLoadingBatches, setIsLoadingBatches] = useState(false);
  const [isLoadingFiles, setIsLoadingFiles] = useState(false);
  const [isLoadingColumns, setIsLoadingColumns] = useState(false);
  const [isLoadingSuggestion, setIsLoadingSuggestion] = useState(false);
  const [isSavingMapping, setIsSavingMapping] = useState(false);
  const [isApplyingMapping, setIsApplyingMapping] = useState(false);
  const [isSlaEnriching, setIsSlaEnriching] = useState(false);
  const [isLoadingSlaContext, setIsLoadingSlaContext] = useState(false);

  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const isSlaUpload = ticketType === "INCIDENT_SLA";

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
  const selectedBatch = useMemo(
    () => filteredBatches.find((batch) => batch.id === selectedBatchId) ?? null,
    [filteredBatches, selectedBatchId]
  );
  const uploadedActionBatchIds = useMemo(
    () =>
      (uploadResult?.files ?? [])
        .map((fileResult) => fileResult.upload_batch_id)
        .filter((batchId): batchId is string => Boolean(batchId)),
    [uploadResult]
  );
  const jobByUploadedFileId = useMemo(() => {
    const jobs = new Map<string, IngestionJob>();
    for (const job of trackedJobs) {
      if (job.uploaded_file_id) {
        jobs.set(job.uploaded_file_id, job);
      }
    }
    return jobs;
  }, [trackedJobs]);
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
    return selectedBatchId ? [selectedBatchId] : [];
  }, [selectedBatchId, uploadedActionBatchIds]);

  const mappingWarnings = useMemo(() => {
    if (isSlaUpload) {
      return [];
    }

    const warnings: string[] = [];
    if (!projectId.trim()) {
      warnings.push("Select a customer before loading or applying a mapping.");
    }
    if (targetBatchIds.length === 0) {
      warnings.push("Upload files or select an active batch before applying a mapping.");
    }
    for (const field of importantFields) {
      if (!mapping[field]) {
        warnings.push(`${field} is not mapped.`);
      }
    }
    return warnings;
  }, [isSlaUpload, mapping, projectId, targetBatchIds.length]);

  const hasUploaded = isSlaUpload
    ? Boolean(slaUploadResult || slaUploadHistory.length > 0)
    : Boolean(uploadResult || selectedBatchId);
  const hasIngested = isSlaUpload
    ? hasUploaded
    : Boolean(
        ingestResult?.totals.batches_ingested ||
          selectedBatch?.status === "INGESTED" ||
          selectedBatch?.status === "NORMALIZED" ||
          selectedBatch?.status === "COMPLETED" ||
          selectedBatchFiles.some((file) => file.status === "INGESTED")
      );
  const hasNormalized = isSlaUpload
    ? hasUploaded
    : Boolean(
        normalizeResult ||
          selectedBatch?.status === "NORMALIZED" ||
          selectedBatch?.status === "COMPLETED"
      );
  const hasMappingReady = isSlaUpload
    ? hasUploaded
    : sourceColumns.length > 0 || Object.keys(mapping).length > 0 || hasIngested;
  const hasApplyReady = isSlaUpload
    ? hasUploaded
    : Object.keys(cleanMapping(mapping)).length > 0 && targetBatchIds.length > 0;
  const hasSummary = isSlaUpload
    ? Boolean(slaUploadResult || slaEnrichResult || slaSummary)
    : Boolean(uploadResult || ingestResult || normalizeResult || applyResult);

  const enabledSteps: Record<WorkflowStepId, boolean> = {
    upload: true,
    ingest: hasUploaded,
    normalize: hasIngested,
    mapping: hasMappingReady,
    apply: hasApplyReady,
    summary: hasSummary,
  };

  const refreshBatches = useCallback(async () => {
    if (!projectId.trim() || isSlaUpload) {
      setBatches([]);
      setHistoricalBatches([]);
      return;
    }

    setIsLoadingBatches(true);
    setError(null);
    try {
      const [nextBatches, nextHistoricalBatches] = await Promise.all([
        listUploadBatches(projectId.trim(), "active"),
        listUploadBatches(projectId.trim(), "history"),
      ]);
      setBatches(nextBatches);
      setHistoricalBatches(nextHistoricalBatches);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Unable to load batches");
    } finally {
      setIsLoadingBatches(false);
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
          getIncidentSlaSummary(projectId.trim()),
          getIncidentSlaUploadHistory(projectId.trim()),
        ]);
        setSlaSummary(nextSummary);
        setSlaUploadHistory(nextHistory);
        if (showMessage) {
          setMessage("Incident SLA history and summary refreshed.");
        }
      } catch (requestError) {
        setError(
          requestError instanceof Error
            ? requestError.message
            : "Unable to load Incident SLA context"
        );
      } finally {
        setIsLoadingSlaContext(false);
      }
    },
    [isSlaUpload, projectId]
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
    setFiles([]);
    setUploadResult(null);
    setIngestResult(null);
    setNormalizeResult(null);
    setSelectedBatchId("");
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
        const result = await uploadIncidentSlaFiles(projectId.trim(), files);
        setSlaUploadResult(result);
        setSlaEnrichResult(null);
        setMessage(
          `Processed ${formatNumber(result.totals.total_files)} SLA file(s), inserted ${formatNumber(
            result.totals.inserted_rows
          )} row(s), skipped ${formatNumber(result.totals.duplicate_rows_skipped)} duplicate row(s).`
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
    if (targetBatchIds.length === 0) {
      setError("Upload files or select an active batch first.");
      return;
    }

    setIsIngesting(true);
    try {
      const result = await ingestUploadBatches(projectId.trim(), targetBatchIds);
      setIngestResult(result);
      setNormalizeResult(null);
      setMessage(
        `Ingested ${formatNumber(result.totals.batches_ingested)} batch(es), staging ${formatNumber(
          result.totals.raw_rows_inserted
        )} raw row(s).`
      );
      await refreshBatches();
      if (targetBatchIds[0]) {
        setSelectedBatchId(targetBatchIds[0]);
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
    if (targetBatchIds.length === 0) {
      setError("Upload files or select an active batch first.");
      return;
    }

    const confirmed = window.confirm(
      "This will normalize the selected/uploaded batch data. Raw uploaded files are preserved."
    );
    if (!confirmed) {
      return;
    }

    setIsNormalizing(true);
    try {
      const result = await normalizeUploadBatches(projectId.trim(), ticketType, targetBatchIds, true);
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
    if (targetBatchIds.length === 0) {
      setError("Upload files or select an active batch before applying mapping.");
      return;
    }

    const applyScope: ApplyScope = targetBatchIds.length === 1 ? "BATCH" : "TICKET_TYPE";
    setIsApplyingMapping(true);
    setError(null);
    setMessage(null);
    try {
      const result = await applyMappingForScope({
        projectId: projectId.trim(),
        ticketType,
        uploadBatchId: applyScope === "BATCH" ? targetBatchIds[0] : undefined,
        scope: applyScope,
        mapping: cleanMapping(mapping),
        deleteExisting: true,
        saveAsDefaultForTicketType: true,
      });
      setApplyResult(result);
      setMessage(
        `Applied mapping and created ${formatNumber(result.normalized_ticket_count)} in-scope ticket(s).`
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
      setError("Select a customer before enriching Incident SLAs.");
      return;
    }

    const confirmed = window.confirm(
      "This will enrich in-scope and out-of-scope Incident tickets with vendor-aware SLA selections. SC Tasks are excluded."
    );
    if (!confirmed) {
      return;
    }

    setIsSlaEnriching(true);
    setError(null);
    setMessage(null);
    try {
      const result = await enrichIncidentSla(projectId.trim(), true);
      setSlaEnrichResult(result);
      setMessage("Incident SLA enrichment completed.");
      await refreshSlaContext(false);
      setActiveStep("summary");
    } catch (requestError) {
      setError(
        requestError instanceof Error ? requestError.message : "Incident SLA enrichment failed"
      );
    } finally {
      setIsSlaEnriching(false);
    }
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
          <span>{isSlaUpload ? "Incident SLA Files" : "Ticket Files"}</span>
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
            {isUploading ? "Uploading..." : isSlaUpload ? "Upload SLA Files" : "Upload Files"}
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
              <MetricCard label="SLA Files" value={formatNumber(slaUploadResult.totals.total_files)} />
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
            Not required for Incident SLA files. SLA upload parses and loads staging rows during
            upload, then enrichment runs in the Apply / Enrich step.
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
            disabled={isIngesting || targetBatchIds.length === 0}
            type="button"
            onClick={() => void handleIngestFiles()}
          >
            {isIngesting ? "Ingesting..." : "Ingest Files"}
          </button>
        </div>

        <div className="scroll-frame">
          {selectedBatchFiles.length === 0 ? (
            <p className="muted-text">
              {isLoadingFiles ? "Loading uploaded files..." : "No uploaded files selected yet."}
            </p>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>File</th>
                  <th>Status</th>
                  <th>Rows</th>
                  <th>Updated</th>
                </tr>
              </thead>
              <tbody>
                {selectedBatchFiles.map((file) => {
                  const job = jobByUploadedFileId.get(file.id);
                  return (
                    <tr key={file.id}>
                      <td>{file.original_filename}</td>
                      <td>{job?.status ?? file.status}</td>
                      <td>
                        {job ? `${formatNumber(job.rows_processed)} / ${formatNumber(job.rows_total)}` : "Ready"}
                      </td>
                      <td>{formatDate(job?.updated_at ?? file.updated_at)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>

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
            Not required for Incident SLA files. SLA enrichment uses uploaded SLA staging rows and
            does not create SC Task SLA records.
          </p>
        </InfoPanel>
      );
    }

    return (
      <div className="workflow-step-panel">
        <div className="panel-heading compact-heading">
          <div>
            <p className="label">Normalize</p>
            <h2>Split In-Scope and Out-of-Scope Tickets</h2>
          </div>
          <button
            className="primary-button"
            disabled={isNormalizing || targetBatchIds.length === 0}
            type="button"
            onClick={() => void handleNormalizeFiles()}
          >
            {isNormalizing ? "Normalizing..." : "Normalize Files"}
          </button>
        </div>

        <div className="scroll-frame">
          {filteredBatches.length === 0 ? (
            <p className="muted-text">
              No active {ticketType === "INCIDENT" ? "Incident" : "SC Task"} batches found.
            </p>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>Batch</th>
                  <th>Status</th>
                  <th>Files</th>
                  <th>Period</th>
                </tr>
              </thead>
              <tbody>
                {filteredBatches.map((batch) => (
                  <tr
                    className={batch.id === selectedBatchId ? "selected-row" : ""}
                    key={batch.id}
                    onClick={() => handleSelectBatch(batch.id)}
                  >
                    <td>
                      <button className="link-button" type="button">
                        {batch.batch_name}
                      </button>
                    </td>
                    <td>{batch.status}</td>
                    <td>{batch.uploaded_file_count ?? batch.file_count}</td>
                    <td>{formatBatchPeriod(batch)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {normalizeResult ? (
          <div className="summary-grid summary-block">
            <MetricCard label="Raw Rows" value={formatNumber(normalizeResult.totals.raw_rows)} />
            <MetricCard label="In Scope" value={formatNumber(normalizeResult.totals.in_scope_inserted)} />
            <MetricCard
              label="Out of Scope"
              value={formatNumber(normalizeResult.totals.out_of_scope_inserted)}
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
            Column mapping is not required for Incident SLA files. SLA files use fixed SLA parsing
            and vendor-aware enrichment rules.
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
              <p className="label">Enrich SLAs</p>
              <h2>Vendor-Aware Incident SLA Enrichment</h2>
            </div>
            <button
              className="primary-button"
              disabled={!projectId.trim() || isSlaEnriching}
              type="button"
              onClick={() => void handleEnrichSla()}
            >
              {isSlaEnriching ? "Enriching..." : "Enrich Incident SLAs"}
            </button>
          </div>
          <p className="muted-text">
            Uses all uploaded SLA rows for the selected customer. In-scope and out-of-scope
            Incident tickets are enriched; SC Tasks are excluded.
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
            <h2>Finalize Normalized Ticket Data</h2>
          </div>
          <button
            className="primary-button"
            disabled={!hasApplyReady || isApplyingMapping}
            type="button"
            onClick={() => void handleApplyMapping()}
          >
            {isApplyingMapping ? "Applying..." : "Apply Mapping"}
          </button>
        </div>
        <p className="muted-text">
          Applies the saved/current mapping and re-normalizes the selected batch or ticket type
          using the Prompt 10.2 scope split rules.
        </p>
        {mappingSaved ? (
          <p className="success-text summary-block">A saved mapping is available for this ticket type.</p>
        ) : null}
        {applyResult ? (
          <div className="summary-grid summary-block">
            <MetricCard label="Raw Rows" value={formatNumber(applyResult.total_raw_rows)} />
            <MetricCard
              label="In Scope"
              value={formatNumber(applyResult.normalized_ticket_count)}
            />
            <MetricCard
              label="Out of Scope"
              value={formatNumber(applyResult.out_of_scope_ticket_count)}
            />
            <MetricCard label="Failed Rows" value={formatNumber(applyResult.failed_row_count)} />
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
              label="SLA Files Uploaded"
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
            label="Input Rows"
            value={formatNumber(
              applyResult?.total_raw_rows ??
                normalizeResult?.totals.raw_rows ??
                validationSummary?.total_raw_rows
            )}
          />
          <MetricCard
            label="In-Scope Output"
            value={formatNumber(
              applyResult?.normalized_ticket_count ?? normalizeResult?.totals.in_scope_inserted
            )}
          />
          <MetricCard
            label="Out-of-Scope Output"
            value={formatNumber(
              applyResult?.out_of_scope_ticket_count ?? normalizeResult?.totals.out_of_scope_inserted
            )}
          />
          <MetricCard
            label="Blank Assignment Group"
            value={formatNumber(applyResult?.blank_assignment_group_count)}
          />
          <MetricCard
            label="Not in Application Inventory"
            value={formatNumber(applyResult?.assignment_group_not_in_inventory_count)}
          />
          <MetricCard label="Vendor Populated" value="Covered" helper="Derived during mapping/enrichment." />
          <MetricCard label="Derived Vendor Populated" value="Covered" helper="Uses Application Inventory." />
          <MetricCard label="Functional Track Populated" value="Covered" helper="Uses Application Inventory." />
          <MetricCard label="AMS Owner Populated" value="Covered" helper="Uses Application Inventory." />
          <MetricCard
            label="Parent Business Application Populated"
            value="Covered"
            helper="Uses Application Inventory."
          />
        </div>

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
                : "Refresh SLA Context"
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
            </div>
          </div>
          <div className="split-grid">
            <div>
              <p className="label">Active Batches</p>
              <div className="scroll-frame compact-file-frame summary-block">
                {filteredBatches.length === 0 ? (
                  <p className="muted-text">No active batches for this upload type.</p>
                ) : (
                  <table>
                    <thead>
                      <tr>
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
                          onClick={() => handleSelectBatch(batch.id)}
                        >
                          <td>
                            <button className="link-button" type="button">
                              {batch.batch_name}
                            </button>
                          </td>
                          <td>{batch.status}</td>
                          <td>{batch.uploaded_file_count ?? batch.file_count}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            </div>
            <div>
              <p className="label">Historical Batches</p>
              <div className="scroll-frame compact-file-frame summary-block">
                {filteredHistoricalBatches.length === 0 ? (
                  <p className="muted-text">No historical batches for this upload type.</p>
                ) : (
                  <table>
                    <thead>
                      <tr>
                        <th>Batch</th>
                        <th>Status</th>
                        <th>Tickets</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredHistoricalBatches.map((batch) => (
                        <tr key={batch.id}>
                          <td>{batch.batch_name}</td>
                          <td>{batch.status}</td>
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

  return (
    <section className="upload-center-layout" aria-labelledby="upload-center-heading">
      <div className="panel upload-center-header">
        <div className="panel-heading">
          <div>
            <p className="label">Upload Center</p>
            <h2 id="upload-center-heading">Data Loading and Processing</h2>
          </div>
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

      {activeTab === "application-inventory" ? (
        <ApplicationInventory
          embedded
          projectId={projectId}
          selectedProject={selectedProject}
          onProjectIdChange={setProjectId}
          onProjectChange={setSelectedProject}
        />
      ) : (
        <TicketDetailsWorkflow projectId={projectId} selectedProject={selectedProject} />
      )}
    </section>
  );
}

export default UploadCenter;
