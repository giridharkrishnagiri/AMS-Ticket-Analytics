import { useCallback, useEffect, useMemo, useState } from "react";

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
import { getValidationSummary, listUploadBatches, listUploadedFiles } from "./api/uploads";
import type { UploadedFile, UploadBatch, ValidationSummary } from "./api/uploads";
import { formatDisplayDate, formatDisplayMonth } from "./utils/dateFormat";

const ticketTypeOptions = [
  { label: "Incident", value: "INCIDENT" },
  { label: "Service Catalog Task", value: "SERVICE_CATALOG_TASK" },
  { label: "Problem", value: "PROBLEM" },
  { label: "Change", value: "CHANGE" },
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

function normalizedFieldsForTicketType(ticketType: string): string[] {
  if (ticketType === "PROBLEM") {
    return problemNormalizedFields;
  }
  if (ticketType === "CHANGE") {
    return changeNormalizedFields;
  }
  return ticketNormalizedFields;
}

function importantFieldsForTicketType(ticketType: string): string[] {
  if (ticketType === "PROBLEM" || ticketType === "CHANGE") {
    return ["number"];
  }
  return ["ticket_id", "title", "created_at"];
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

function formatBatchPeriod(batch: UploadBatch): string {
  if (batch.period_type === "SNAPSHOT") {
    return `SNAPSHOT - ${formatDisplayDate(batch.snapshot_date)}`;
  }

  return `MONTHLY - ${formatDisplayMonth(batch.month_key)}`;
}

function cleanMapping(mapping: Record<string, string>): Record<string, string> {
  return Object.fromEntries(
    Object.entries(mapping).filter(([, sourceColumn]) => sourceColumn.trim())
  );
}

function mappingSourceMessage(mappingSource: MappingSource): string {
  if (mappingSource === "SAVED_TEMPLATE") {
    return "Loaded saved mapping for this project and ticket type.";
  }
  return "Loaded built-in suggested mapping.";
}

function MappingWizard() {
  const [batches, setBatches] = useState<UploadBatch[]>([]);
  const [batchFilesById, setBatchFilesById] = useState<Record<string, UploadedFile[]>>({});
  const [projectId, setProjectId] = useState("");
  const [ticketType, setTicketType] = useState("INCIDENT");
  const [selectedBatchId, setSelectedBatchId] = useState("");
  const [applyScope, setApplyScope] = useState<ApplyScope>("BATCH");
  const [rememberMapping, setRememberMapping] = useState(true);
  const [sourceColumns, setSourceColumns] = useState<SourceColumn[]>([]);
  const [mapping, setMapping] = useState<Record<string, string>>({});
  const [suggestionSource, setSuggestionSource] = useState<MappingSource | null>(null);
  const [validationSummary, setValidationSummary] = useState<ValidationSummary | null>(null);
  const [applyResult, setApplyResult] = useState<ScopedApplyMappingResponse | null>(null);
  const [isLoadingBatches, setIsLoadingBatches] = useState(false);
  const [isLoadingColumns, setIsLoadingColumns] = useState(false);
  const [isLoadingSuggestion, setIsLoadingSuggestion] = useState(false);
  const [isSavingTemplate, setIsSavingTemplate] = useState(false);
  const [isApplyingMapping, setIsApplyingMapping] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const normalizedFields = useMemo(
    () => normalizedFieldsForTicketType(ticketType),
    [ticketType]
  );
  const importantFields = useMemo(
    () => importantFieldsForTicketType(ticketType),
    [ticketType]
  );
  const isProblemOrChange = ticketType === "PROBLEM" || ticketType === "CHANGE";

  const knownProjectIds = useMemo(
    () => Array.from(new Set(batches.map((batch) => batch.project_id))),
    [batches]
  );
  const selectedBatch = useMemo(
    () => batches.find((batch) => batch.id === selectedBatchId) ?? null,
    [batches, selectedBatchId]
  );
  const selectedBatchFiles = selectedBatchId ? batchFilesById[selectedBatchId] ?? [] : [];
  const selectedBatchTicketType = selectedBatchFiles[0]?.ticket_type ?? "";
  const batchTicketTypeLabels = useMemo(() => {
    const labels: Record<string, string> = {};
    for (const [batchId, uploadedFiles] of Object.entries(batchFilesById)) {
      labels[batchId] = Array.from(new Set(uploadedFiles.map((file) => file.ticket_type))).join(
        ", "
      );
    }
    return labels;
  }, [batchFilesById]);
  const filteredBatches = useMemo(
    () =>
      batches.filter((batch) => {
        if (projectId.trim() && batch.project_id !== projectId.trim()) {
          return false;
        }
        const batchTicketTypes = new Set(
          (batchFilesById[batch.id] ?? []).map((file) => file.ticket_type)
        );
        return batchTicketTypes.size === 0 || batchTicketTypes.has(ticketType);
      }),
    [batchFilesById, batches, projectId, ticketType]
  );
  const scopedBatches = useMemo(() => {
    if (applyScope === "TICKET_TYPE") {
      return filteredBatches;
    }
    return selectedBatch ? [selectedBatch] : [];
  }, [applyScope, filteredBatches, selectedBatch]);
  const scopedFileCount = useMemo(
    () =>
      scopedBatches.reduce((total, batch) => {
        const matchingFiles = (batchFilesById[batch.id] ?? []).filter(
          (uploadedFile) => uploadedFile.ticket_type === ticketType
        );
        return total + (matchingFiles.length || batch.file_count);
      }, 0),
    [batchFilesById, scopedBatches, ticketType]
  );
  const scopedSizeBytes = useMemo(
    () =>
      scopedBatches.reduce((total, batch) => {
        const matchingFiles = (batchFilesById[batch.id] ?? []).filter(
          (uploadedFile) => uploadedFile.ticket_type === ticketType
        );
        const matchingFileSize = matchingFiles.reduce(
          (fileTotal, uploadedFile) => fileTotal + uploadedFile.size_bytes,
          0
        );
        return total + (matchingFileSize || batch.total_size_bytes);
      }, 0),
    [batchFilesById, scopedBatches, ticketType]
  );
  const scopedStatusLabel = useMemo(() => {
    if (applyScope === "BATCH") {
      return selectedBatch?.status ?? "Not available";
    }

    const statusCounts = scopedBatches.reduce<Record<string, number>>((counts, batch) => {
      counts[batch.status] = (counts[batch.status] ?? 0) + 1;
      return counts;
    }, {});
    const statusLabels = Object.entries(statusCounts).map(
      ([status, count]) => `${status} ${count}`
    );
    return statusLabels.length > 0 ? statusLabels.join(", ") : "Not available";
  }, [applyScope, scopedBatches, selectedBatch]);
  const applyTargetLabel =
    applyScope === "TICKET_TYPE"
      ? `${scopedBatches.length} matching batch(es)`
      : selectedBatch?.batch_name ?? "None";
  const sourceColumnNames = useMemo(() => {
    const sourceNames = sourceColumns.map((sourceColumn) => sourceColumn.name);
    return Array.from(new Set([...sourceNames, ...Object.values(mapping).filter(Boolean)]));
  }, [mapping, sourceColumns]);
  const mappingWarnings = useMemo(() => {
    const warnings: string[] = [];
    if (!projectId.trim()) {
      warnings.push("Project ID is required.");
    }
    if (applyScope === "BATCH" && !selectedBatchId) {
      warnings.push("Select a batch for selected-batch apply scope.");
    }
    if (
      selectedBatch &&
      selectedBatchTicketType &&
      selectedBatchTicketType !== ticketType
    ) {
      warnings.push(`Selected batch is ${selectedBatchTicketType}, not ${ticketType}.`);
    }
    if (
      selectedBatch &&
      !["INGESTED", "NORMALIZED", "NORMALIZATION_FAILED", "COMPLETED", "PARTIAL"].includes(
        selectedBatch.status
      )
    ) {
      warnings.push("Selected batch is not ingested yet.");
    }
    if (validationSummary?.total_raw_rows === 0 && applyScope === "BATCH") {
      warnings.push("Ingest uploaded files before applying mapping.");
    }
    if (applyScope === "TICKET_TYPE") {
      warnings.push(
        `All ${ticketType} batches for this project will be re-normalized when applied.`
      );
    }
    for (const field of importantFields) {
      if (!mapping[field]) {
        warnings.push(`${field} is not mapped.`);
      }
    }
    return warnings;
  }, [
    applyScope,
    importantFields,
    mapping,
    projectId,
    selectedBatch,
    selectedBatchId,
    selectedBatchTicketType,
    ticketType,
    validationSummary,
  ]);

  const refreshBatches = useCallback(async () => {
    setIsLoadingBatches(true);
    setError(null);
    try {
      const nextBatches = await listUploadBatches(undefined, "all");
      const fileEntries = await Promise.all(
        nextBatches.map(async (batch) => {
          try {
            return [batch.id, await listUploadedFiles(batch.id)] as const;
          } catch {
            return [batch.id, [] as UploadedFile[]] as const;
          }
        })
      );
      setBatches(nextBatches);
      setBatchFilesById(Object.fromEntries(fileEntries));
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Unable to load batches");
    } finally {
      setIsLoadingBatches(false);
    }
  }, []);

  const refreshValidationSummary = useCallback(async (batchId: string) => {
    if (!batchId) {
      setValidationSummary(null);
      return;
    }

    try {
      setValidationSummary(await getValidationSummary(batchId));
    } catch (requestError) {
      setValidationSummary(null);
      setError(
        requestError instanceof Error ? requestError.message : "Unable to load validation summary"
      );
    }
  }, []);

  const handleLoadSourceColumns = useCallback(async () => {
    if (!projectId.trim()) {
      setError("Project ID is required.");
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
      setMessage(
        selectedBatchId
          ? `Loaded ${response.source_columns.length} source column(s) from selected batch.`
          : `Loaded ${response.source_columns.length} source column(s) from ${ticketType} batches.`
      );
    } catch (requestError) {
      setError(
        requestError instanceof Error ? requestError.message : "Unable to load source columns"
      );
    } finally {
      setIsLoadingColumns(false);
    }
  }, [projectId, selectedBatchId, ticketType]);

  const handleLoadSuggestedMapping = useCallback(async () => {
    if (!projectId.trim()) {
      setError("Project ID is required.");
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
      setSuggestionSource(response.mapping_source);
      setMessage(mappingSourceMessage(response.mapping_source));
    } catch (requestError) {
      setError(
        requestError instanceof Error ? requestError.message : "Unable to load suggested mapping"
      );
    } finally {
      setIsLoadingSuggestion(false);
    }
  }, [projectId, selectedBatchId, ticketType]);

  const handleSaveMappingTemplate = async () => {
    if (!projectId.trim()) {
      setError("Project ID is required.");
      return;
    }

    setIsSavingTemplate(true);
    setError(null);
    setMessage(null);
    try {
      await saveMappingTemplate({
        projectId: projectId.trim(),
        ticketType,
        mapping: cleanMapping(mapping),
      });
      setSuggestionSource("SAVED_TEMPLATE");
      setMessage("Mapping template saved for this project and ticket type.");
    } catch (requestError) {
      setError(
        requestError instanceof Error ? requestError.message : "Unable to save mapping template"
      );
    } finally {
      setIsSavingTemplate(false);
    }
  };

  const handleApplyMapping = async () => {
    if (!projectId.trim()) {
      setError("Project ID is required.");
      return;
    }
    if (applyScope === "BATCH" && !selectedBatchId) {
      setError("Select a batch before applying to selected batch only.");
      return;
    }

    setIsApplyingMapping(true);
    setError(null);
    setMessage(null);
    try {
      const result = await applyMappingForScope({
        projectId: projectId.trim(),
        ticketType,
        uploadBatchId: applyScope === "BATCH" ? selectedBatchId : undefined,
        scope: applyScope,
        mapping: cleanMapping(mapping),
        deleteExisting: true,
        saveAsDefaultForTicketType:
          applyScope === "TICKET_TYPE" ? true : rememberMapping,
      });
      setApplyResult(result);
      const outputNoun = isProblemOrChange ? "record(s)" : "ticket(s)";
      setMessage(
        applyScope === "TICKET_TYPE"
          ? `Normalized ${result.normalized_ticket_count} ${outputNoun} across ${result.batch_results.length} batch(es); skipped ${result.duplicate_skipped_count} duplicate row(s).`
          : `Normalized ${outputNoun} for the selected batch; skipped ${result.duplicate_skipped_count} duplicate row(s).`
      );
      await refreshBatches();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Unable to apply mapping");
    } finally {
      setIsApplyingMapping(false);
    }
  };

  const handleClearMapping = () => {
    setMapping({});
    setSuggestionSource(null);
    setApplyResult(null);
    setMessage("Mapping cleared.");
    setError(null);
  };

  useEffect(() => {
    void refreshBatches();
  }, [refreshBatches]);

  useEffect(() => {
    if (!selectedBatch) {
      void refreshValidationSummary("");
      return;
    }

    setProjectId(selectedBatch.project_id);
    if (selectedBatchTicketType) {
      setTicketType(selectedBatchTicketType);
    }
    void refreshValidationSummary(selectedBatch.id);
  }, [refreshValidationSummary, selectedBatch, selectedBatchTicketType]);

  useEffect(() => {
    if (
      selectedBatchId &&
      !filteredBatches.some((batch) => batch.id === selectedBatchId)
    ) {
      setSelectedBatchId("");
    }
  }, [filteredBatches, selectedBatchId]);

  useEffect(() => {
    setSourceColumns([]);
    setMapping({});
    setSuggestionSource(null);
    setApplyResult(null);
    setMessage(null);
    setError(null);
  }, [projectId, ticketType]);

  return (
    <div className="upload-layout">
      <section className="panel" aria-labelledby="mapping-template-heading">
        <div className="panel-heading">
          <div>
            <p className="label">Mapping Wizard</p>
            <h2 id="mapping-template-heading">Ticket Type Template</h2>
          </div>
          <button className="secondary-button" type="button" onClick={() => void refreshBatches()}>
            {isLoadingBatches ? "Refreshing..." : "Refresh Batches"}
          </button>
        </div>

        <div className="form-grid">
          <label>
            <span>Project ID</span>
            <input
              list="mapping-project-id-options"
              placeholder="Paste project UUID"
              value={projectId}
              onChange={(event) => setProjectId(event.target.value)}
            />
            <datalist id="mapping-project-id-options">
              {knownProjectIds.map((knownProjectId) => (
                <option key={knownProjectId} value={knownProjectId} />
              ))}
            </datalist>
          </label>

          <label>
            <span>Ticket Type</span>
            <select value={ticketType} onChange={(event) => setTicketType(event.target.value)}>
              {ticketTypeOptions.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>

          <label>
            <span>Representative Batch</span>
            <select
              value={selectedBatchId}
              onChange={(event) => setSelectedBatchId(event.target.value)}
            >
              <option value="">No batch selected</option>
              {filteredBatches.map((batch) => (
                <option key={batch.id} value={batch.id}>
                  {batch.batch_name} - {formatBatchPeriod(batch)} - {batch.status}
                  {batchTicketTypeLabels[batch.id] ? ` - ${batchTicketTypeLabels[batch.id]}` : ""}
                </option>
              ))}
            </select>
          </label>

          <label>
            <span>Apply Scope</span>
            <select
              value={applyScope}
              onChange={(event) => setApplyScope(event.target.value as ApplyScope)}
            >
              <option value="BATCH">Selected batch only</option>
              <option value="TICKET_TYPE">All batches of selected ticket type</option>
            </select>
          </label>
        </div>

        {applyScope === "BATCH" ? (
          <label className="checkbox-label">
            <input
              checked={rememberMapping}
              type="checkbox"
              onChange={(event) => setRememberMapping(event.target.checked)}
            />
            <span>Remember this mapping for this ticket type</span>
          </label>
        ) : (
          <p className="scope-note">
            Applying all batches saves this mapping as the default for {ticketType}.
          </p>
        )}

        <div className="summary-grid mapping-summary-grid">
          <div>
            <p className="label">Project</p>
            <strong className="mono-text">{projectId || "Not set"}</strong>
          </div>
          <div>
            <p className="label">Ticket Type</p>
            <strong>{ticketType}</strong>
          </div>
          <div>
            <p className="label">Matching Batches</p>
            <strong>{filteredBatches.length}</strong>
          </div>
          <div>
            <p className="label">Apply Target</p>
            <strong>{applyTargetLabel}</strong>
          </div>
          <div>
            <p className="label">Status</p>
            <strong>{scopedStatusLabel}</strong>
          </div>
          <div>
            <p className="label">Files</p>
            <strong>{scopedFileCount}</strong>
          </div>
          <div>
            <p className="label">Size</p>
            <strong>{formatBytes(scopedSizeBytes)}</strong>
          </div>
          <div>
            <p className="label">Mapping Source</p>
            <strong>{suggestionSource ?? "Not loaded"}</strong>
          </div>
        </div>

        {mappingWarnings.length > 0 ? (
          <div className="warning-list" role="status">
            {mappingWarnings.map((warning) => (
              <p key={warning}>{warning}</p>
            ))}
          </div>
        ) : null}

        <div className="message-stack">
          {message ? <p className="success-text">{message}</p> : null}
          {error ? <p className="error-text">{error}</p> : null}
        </div>
      </section>

      <section className="panel" aria-labelledby="mapping-table-heading">
        <div className="panel-heading">
          <div>
            <p className="label">Columns</p>
            <h2 id="mapping-table-heading">Field Mapping</h2>
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
              {isLoadingSuggestion ? "Loading..." : "Load Suggested Mapping"}
            </button>
            <button className="secondary-button" type="button" onClick={handleClearMapping}>
              Clear Mapping
            </button>
          </div>
        </div>

        {sourceColumns.length > 0 ? (
          <div className="chip-list mapping-chip-list">
            {sourceColumns.map((sourceColumn) => (
              <span className="chip" key={sourceColumn.name}>
                {sourceColumn.name}
              </span>
            ))}
          </div>
        ) : (
          <p className="muted-text">
            Load source columns from a representative batch or all batches for this ticket type.
          </p>
        )}

        <div className="table-wrap mapping-table-wrap">
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

        <div className="action-row">
          <button
            className="secondary-button"
            disabled={!projectId.trim() || isSavingTemplate}
            type="button"
            onClick={() => void handleSaveMappingTemplate()}
          >
            {isSavingTemplate ? "Saving..." : "Save Mapping Template"}
          </button>
          <button
            className="primary-button"
            disabled={!projectId.trim() || isApplyingMapping}
            type="button"
            onClick={() => void handleApplyMapping()}
          >
            {isApplyingMapping ? "Applying..." : "Apply Mapping"}
          </button>
        </div>
      </section>

      <section className="panel" aria-labelledby="apply-result-heading">
        <div className="panel-heading">
          <div>
            <p className="label">Normalize</p>
            <h2 id="apply-result-heading">Apply Result</h2>
          </div>
        </div>

        {!applyResult ? (
          <p className="muted-text">No mapping apply result yet.</p>
        ) : (
          <>
            <div className="summary-grid">
              <div>
                <p className="label">Scope</p>
                <strong>{applyResult.scope}</strong>
              </div>
              <div>
                <p className="label">Total Raw Rows</p>
                <strong>{applyResult.total_raw_rows}</strong>
              </div>
              <div>
                <p className="label">{isProblemOrChange ? "Records Created" : "Tickets Created"}</p>
                <strong>{applyResult.normalized_ticket_count}</strong>
              </div>
              <div>
                <p className="label">Duplicates Skipped</p>
                <strong>{applyResult.duplicate_skipped_count}</strong>
              </div>
              <div>
                <p className="label">Failed Rows</p>
                <strong>{applyResult.failed_row_count}</strong>
              </div>
              <div>
                <p className="label">Saved Default</p>
                <strong>{applyResult.saved_as_default_for_ticket_type ? "Yes" : "No"}</strong>
              </div>
              <div>
                <p className="label">Batches</p>
                <strong>{applyResult.batch_results.length}</strong>
              </div>
            </div>

            <div className="summary-block table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Batch</th>
                    <th>Status</th>
                    <th>Total Raw Rows</th>
                    <th>{isProblemOrChange ? "Records Created" : "Tickets Created"}</th>
                    <th>Duplicates Skipped</th>
                    <th>Failed Rows</th>
                    <th>Warnings</th>
                    <th>Errors</th>
                  </tr>
                </thead>
                <tbody>
                  {applyResult.batch_results.map((batchResult) => (
                    <tr key={batchResult.upload_batch_id}>
                      <td>
                        <strong>{batchResult.batch_name}</strong>
                        <p className="muted-text mono-text">{batchResult.upload_batch_id}</p>
                      </td>
                      <td>{batchResult.status ?? "Not available"}</td>
                      <td>{batchResult.total_raw_rows}</td>
                      <td>{batchResult.normalized_ticket_count}</td>
                      <td>{batchResult.duplicate_skipped_count}</td>
                      <td>{batchResult.failed_row_count}</td>
                      <td>{batchResult.warnings.length}</td>
                      <td>{batchResult.errors.length}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {applyResult.warnings.length > 0 ? (
              <div className="summary-block">
                <p className="label">Warnings</p>
                <div className="warning-list">
                  {applyResult.warnings.map((warning) => (
                    <p key={warning}>{warning}</p>
                  ))}
                </div>
              </div>
            ) : null}

            {applyResult.errors.length > 0 ? (
              <div className="summary-block table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Row</th>
                      <th>Raw Row ID</th>
                      <th>Error</th>
                    </tr>
                  </thead>
                  <tbody>
                    {applyResult.errors.map((rowError) => (
                      <tr key={rowError.raw_row_id}>
                        <td>{rowError.row_number}</td>
                        <td className="mono-text">{rowError.raw_row_id}</td>
                        <td>{rowError.message}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : null}
          </>
        )}
      </section>
    </div>
  );
}

export default MappingWizard;
