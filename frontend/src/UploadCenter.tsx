import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ChangeEvent, FormEvent } from "react";

import {
  deleteUploadBatch,
  getRawRowsPreview,
  getValidationSummary,
  getIngestionJob,
  ingestUploadBatches,
  ingestUploadedFile,
  listUploadBatches,
  listUploadedFiles,
  normalizeUploadBatches,
  uploadTicketFilesMultiple,
} from "./api/uploads";
import type {
  IngestionJob,
  RawRowsPreviewResponse,
  UploadedFile,
  UploadBatch,
  UploadBatchIngestMultipleResponse,
  UploadBatchNormalizeMultipleResponse,
  UploadMultipleResponse,
  ValidationSummary,
} from "./api/uploads";
import CustomerSelector from "./CustomerSelector";

const ticketTypeOptions = [
  { label: "Incident", value: "INCIDENT" },
  { label: "Service Catalog Task", value: "SERVICE_CATALOG_TASK" },
];

const periodTypeOptions = [
  { label: "Monthly Extract", value: "MONTHLY" },
  { label: "Snapshot Extract", value: "SNAPSHOT" },
];

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

function formatBatchPeriod(batch: UploadBatch): string {
  if (batch.period_type === "SNAPSHOT") {
    return `SNAPSHOT - ${batch.snapshot_date ?? "No date"}`;
  }

  return `MONTHLY - ${batch.month_key ?? "No month"}`;
}

function UploadCenter() {
  const [projectId, setProjectId] = useState("");
  const [ticketType, setTicketType] = useState("INCIDENT");
  const [periodType, setPeriodType] = useState("MONTHLY");
  const [monthKey, setMonthKey] = useState("");
  const [snapshotDate, setSnapshotDate] = useState(getTodayDateInputValue);
  const [batchName, setBatchName] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [batches, setBatches] = useState<UploadBatch[]>([]);
  const [historicalBatches, setHistoricalBatches] = useState<UploadBatch[]>([]);
  const [selectedBatchId, setSelectedBatchId] = useState("");
  const [selectedBatchFiles, setSelectedBatchFiles] = useState<UploadedFile[]>([]);
  const [trackedJobs, setTrackedJobs] = useState<IngestionJob[]>([]);
  const [uploadResult, setUploadResult] = useState<UploadMultipleResponse | null>(null);
  const [ingestResult, setIngestResult] = useState<UploadBatchIngestMultipleResponse | null>(null);
  const [normalizeResult, setNormalizeResult] =
    useState<UploadBatchNormalizeMultipleResponse | null>(null);
  const [rawRowsPreview, setRawRowsPreview] = useState<RawRowsPreviewResponse | null>(null);
  const [validationSummary, setValidationSummary] = useState<ValidationSummary | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [isIngestingBatches, setIsIngestingBatches] = useState(false);
  const [isNormalizingBatches, setIsNormalizingBatches] = useState(false);
  const [isLoadingBatches, setIsLoadingBatches] = useState(false);
  const [isLoadingFiles, setIsLoadingFiles] = useState(false);
  const [isLoadingPreview, setIsLoadingPreview] = useState(false);
  const [isLoadingValidation, setIsLoadingValidation] = useState(false);
  const [ingestingFileIds, setIngestingFileIds] = useState<Set<string>>(new Set());
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

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
  const uploadedActionBatchIds = useMemo(
    () =>
      (uploadResult?.files ?? [])
        .map((fileResult) => fileResult.upload_batch_id)
        .filter((batchId): batchId is string => Boolean(batchId)),
    [uploadResult]
  );

  function getActionBatchIds(): string[] {
    if (uploadedActionBatchIds.length > 0) {
      return uploadedActionBatchIds;
    }

    return selectedBatchId ? [selectedBatchId] : [];
  }

  const hasActionBatchIds = uploadedActionBatchIds.length > 0 || Boolean(selectedBatchId);

  const selectedFileContext = `${
    ticketTypeOptions.find((option) => option.value === ticketType)?.label ?? ticketType
  } - ${
    periodType === "MONTHLY"
      ? `Monthly ${monthKey || "month not selected"}`
      : `Snapshot ${snapshotDate || "date not selected"}`
  }`;

  const handleProjectIdChange = useCallback((nextProjectId: string) => {
    setProjectId(nextProjectId);
    setSelectedBatchId("");
    setSelectedBatchFiles([]);
    setTrackedJobs([]);
    setUploadResult(null);
    setIngestResult(null);
    setNormalizeResult(null);
    setRawRowsPreview(null);
    setValidationSummary(null);
  }, []);

  function handleSelectBatch(batchId: string) {
    setSelectedBatchId(batchId);
    setUploadResult(null);
    setIngestResult(null);
    setNormalizeResult(null);
  }

  const refreshBatches = useCallback(async () => {
    setIsLoadingBatches(true);
    setError(null);

    try {
      const selectedProjectId = projectId.trim() || undefined;
      const [nextBatches, nextHistoricalBatches] = await Promise.all([
        listUploadBatches(selectedProjectId, "active"),
        listUploadBatches(selectedProjectId, "history"),
      ]);
      setBatches(nextBatches);
      setHistoricalBatches(nextHistoricalBatches);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Unable to load batches");
    } finally {
      setIsLoadingBatches(false);
    }
  }, [projectId]);

  const refreshSelectedBatchFiles = useCallback(
    async (batchId: string) => {
      if (!batchId) {
        setSelectedBatchFiles([]);
        return;
      }

      setIsLoadingFiles(true);
      setError(null);

      try {
        const nextFiles = await listUploadedFiles(batchId);
        setSelectedBatchFiles(nextFiles);
      } catch (requestError) {
        setError(requestError instanceof Error ? requestError.message : "Unable to load files");
      } finally {
        setIsLoadingFiles(false);
      }
    },
    []
  );

  const refreshRawRowsPreview = useCallback(async (batchId: string) => {
    if (!batchId) {
      setRawRowsPreview(null);
      return;
    }

    setIsLoadingPreview(true);
    setError(null);

    try {
      const nextPreview = await getRawRowsPreview(batchId, 5);
      setRawRowsPreview(nextPreview);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Unable to load raw rows");
      setRawRowsPreview(null);
    } finally {
      setIsLoadingPreview(false);
    }
  }, []);

  const refreshValidationSummary = useCallback(async (batchId: string) => {
    if (!batchId) {
      setValidationSummary(null);
      return;
    }

    setIsLoadingValidation(true);
    setError(null);

    try {
      const nextSummary = await getValidationSummary(batchId);
      setValidationSummary(nextSummary);
    } catch (requestError) {
      setError(
        requestError instanceof Error ? requestError.message : "Unable to load validation summary"
      );
      setValidationSummary(null);
    } finally {
      setIsLoadingValidation(false);
    }
  }, []);

  const refreshTrackedJobs = useCallback(async () => {
    if (trackedJobs.length === 0) {
      return;
    }

    setError(null);

    try {
      const nextJobs = await Promise.all(trackedJobs.map((job) => getIngestionJob(job.id)));
      setTrackedJobs(nextJobs);
    } catch (requestError) {
      setError(
        requestError instanceof Error ? requestError.message : "Unable to refresh ingestion jobs"
      );
    }
  }, [trackedJobs]);

  useEffect(() => {
    void refreshBatches();
  }, [refreshBatches]);

  useEffect(() => {
    void refreshSelectedBatchFiles(selectedBatchId);
  }, [refreshSelectedBatchFiles, selectedBatchId]);

  useEffect(() => {
    void refreshRawRowsPreview(selectedBatchId);
    void refreshValidationSummary(selectedBatchId);
  }, [refreshRawRowsPreview, refreshValidationSummary, selectedBatchId]);

  function handleFileSelection(event: ChangeEvent<HTMLInputElement>) {
    setFiles(Array.from(event.target.files ?? []));
  }

  function handleClearSelectedFiles() {
    setFiles([]);
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
    setMessage("Cleared selected files. No uploaded files or database records were deleted.");
  }

  function handleClearDetails() {
    setSelectedBatchId("");
    setSelectedBatchFiles([]);
    setTrackedJobs([]);
    setUploadResult(null);
    setIngestResult(null);
    setNormalizeResult(null);
    setRawRowsPreview(null);
    setValidationSummary(null);
    setMessage("Cleared displayed batch details. No uploaded files or database records were deleted.");
    setError(null);
  }

  function handleClearPreview() {
    setRawRowsPreview(null);
    setMessage("Cleared raw row preview display only.");
    setError(null);
  }

  function handleClearValidationSummary() {
    setValidationSummary(null);
    setMessage("Cleared validation summary display only.");
    setError(null);
  }

  function getBatchFileCount(batch: UploadBatch): number {
    return batch.uploaded_file_count ?? batch.file_count;
  }

  async function handleDeleteBatch(batch: UploadBatch) {
    const confirmed = window.confirm(
      `Delete staging data for "${batch.batch_name}"? This removes the batch from active worklists but will not delete normalized tickets.`
    );
    if (!confirmed) {
      return;
    }

    setMessage(null);
    setError(null);

    try {
      await deleteUploadBatch(batch.id);
      if (selectedBatchId === batch.id) {
        handleClearDetails();
      }
      setMessage(`Deleted staging batch "${batch.batch_name}".`);
      await refreshBatches();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Unable to delete batch");
    }
  }

  async function handleUpload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMessage(null);
    setError(null);

    if (!projectId.trim()) {
      setError("Project ID is required.");
      return;
    }

    if (periodType === "MONTHLY" && !monthKey) {
      setError("Month-Year is required for monthly uploads.");
      return;
    }

    if (periodType === "SNAPSHOT" && !snapshotDate) {
      setError("Snapshot date is required for snapshot uploads.");
      return;
    }

    if (!batchName.trim()) {
      setError("Batch name is required.");
      return;
    }

    if (files.length === 0) {
      setError("Select at least one CSV or XLSX file.");
      return;
    }

    setIsUploading(true);

    try {
      const uploadResponse = await uploadTicketFilesMultiple({
        projectId: projectId.trim(),
        ticketType,
        periodType,
        monthKey,
        snapshotDate,
        batchName,
        files,
      });

      setUploadResult(uploadResponse);
      setIngestResult(null);
      setNormalizeResult(null);
      const refreshedJobs = await Promise.all(
        uploadResponse.files
          .map((fileResult) => fileResult.ingestion_job_id)
          .filter((jobId): jobId is string => Boolean(jobId))
          .map((jobId) => getIngestionJob(jobId))
      );

      setMessage(
        `Uploaded ${uploadResponse.totals.files_uploaded} of ${
          uploadResponse.totals.files_selected
        } selected file(s).`
      );
      setTrackedJobs(refreshedJobs);
      const firstUploadedBatchId =
        uploadResponse.files.find((fileResult) => fileResult.upload_batch_id)
          ?.upload_batch_id ?? "";
      setSelectedBatchId(firstUploadedBatchId);
      setFiles([]);
      await refreshBatches();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Upload failed");
    } finally {
      setIsUploading(false);
    }
  }

  async function handleIngestFile(uploadedFile: UploadedFile) {
    setMessage(null);
    setError(null);
    setIngestingFileIds((current) => new Set(current).add(uploadedFile.id));

    try {
      const ingestionJob = await ingestUploadedFile(uploadedFile.id);
      setTrackedJobs((currentJobs) => {
        const nextJobs = currentJobs.filter((job) => job.id !== ingestionJob.id);
        return [ingestionJob, ...nextJobs];
      });
      setMessage(
        `Ingestion ${ingestionJob.status.toLowerCase()} for ${uploadedFile.original_filename}.`
      );
      await Promise.all([
        refreshSelectedBatchFiles(uploadedFile.upload_batch_id),
        refreshBatches(),
        refreshRawRowsPreview(uploadedFile.upload_batch_id),
        refreshValidationSummary(uploadedFile.upload_batch_id),
      ]);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "File ingestion failed");
    } finally {
      setIngestingFileIds((current) => {
        const next = new Set(current);
        next.delete(uploadedFile.id);
        return next;
      });
    }
  }

  async function handleIngestFiles() {
    setMessage(null);
    setError(null);

    if (!projectId.trim()) {
      setError("Customer is required.");
      return;
    }

    const targetBatchIds = getActionBatchIds();
    if (targetBatchIds.length === 0) {
      setError("Upload files or select a batch before ingesting.");
      return;
    }

    setIsIngestingBatches(true);
    try {
      const result = await ingestUploadBatches(projectId.trim(), targetBatchIds);
      setIngestResult(result);
      setNormalizeResult(null);
      setMessage(
        `Ingested ${result.totals.batches_ingested} of ${
          result.totals.batches_requested
        } batch(es), with ${result.totals.raw_rows_inserted} raw row(s) staged.`
      );
      await refreshBatches();
      const firstBatchId = targetBatchIds[0] ?? "";
      if (firstBatchId) {
        setSelectedBatchId(firstBatchId);
        await Promise.all([
          refreshSelectedBatchFiles(firstBatchId),
          refreshRawRowsPreview(firstBatchId),
          refreshValidationSummary(firstBatchId),
        ]);
      }
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "File ingestion failed");
    } finally {
      setIsIngestingBatches(false);
    }
  }

  async function handleNormalizeFiles() {
    setMessage(null);
    setError(null);

    if (!projectId.trim()) {
      setError("Customer is required.");
      return;
    }

    const targetBatchIds = getActionBatchIds();
    if (targetBatchIds.length === 0) {
      setError("Upload files or select a batch before normalizing.");
      return;
    }

    const confirmed = window.confirm(
      "This will delete and recreate normalized tickets for the selected/uploaded batch(es). Raw uploaded data will not be deleted."
    );
    if (!confirmed) {
      return;
    }

    setIsNormalizingBatches(true);
    try {
      const result = await normalizeUploadBatches(projectId.trim(), ticketType, targetBatchIds, true);
      setNormalizeResult(result);
      setMessage(
        `Normalized ${result.totals.in_scope_inserted} in-scope and ${
          result.totals.out_of_scope_inserted
        } out-of-scope ticket(s).`
      );
      await refreshBatches();
      const firstBatchId = targetBatchIds[0] ?? "";
      if (firstBatchId) {
        await Promise.all([
          refreshSelectedBatchFiles(firstBatchId),
          refreshRawRowsPreview(firstBatchId),
          refreshValidationSummary(firstBatchId),
        ]);
      }
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Normalization failed");
    } finally {
      setIsNormalizingBatches(false);
    }
  }

  function getIngestButtonText(uploadedFile: UploadedFile): string {
    const job = jobByUploadedFileId.get(uploadedFile.id);
    if (ingestingFileIds.has(uploadedFile.id)) {
      return "Ingesting...";
    }

    if (job?.status === "COMPLETED" || uploadedFile.status === "INGESTED") {
      return "Completed";
    }

    if (job?.status === "FAILED" || uploadedFile.status === "FAILED") {
      return "Retry Ingest";
    }

    return "Ingest File";
  }

  return (
    <div className="upload-layout">
      <form className="upload-form panel" onSubmit={(event) => void handleUpload(event)}>
        <div className="panel-heading">
          <div>
            <p className="label">Upload Center</p>
            <h2>Ticket Files</h2>
          </div>
        </div>

        <div className="form-grid">
          <CustomerSelector projectId={projectId} onProjectIdChange={handleProjectIdChange} />

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
            <span>Upload Period Type</span>
            <select value={periodType} onChange={(event) => setPeriodType(event.target.value)}>
              {periodTypeOptions.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>

          {periodType === "MONTHLY" ? (
            <label>
              <span>Month-Year</span>
              <input
                required
                type="month"
                value={monthKey}
                onChange={(event) => setMonthKey(event.target.value)}
              />
            </label>
          ) : (
            <label>
              <span>Snapshot Date</span>
              <input
                required
                type="date"
                value={snapshotDate}
                onChange={(event) => setSnapshotDate(event.target.value)}
              />
            </label>
          )}

          <label>
            <span>Batch Name</span>
            <input
              required
              placeholder={
                periodType === "SNAPSHOT"
                  ? `Open Incidents Snapshot - ${snapshotDate}`
                  : "Incidents Closed June 2026"
              }
              value={batchName}
              onChange={(event) => setBatchName(event.target.value)}
            />
          </label>
        </div>

        <label className="file-input">
          <span>Files</span>
          <input
            accept=".csv,.xlsx"
            multiple
            ref={fileInputRef}
            type="file"
            onChange={handleFileSelection}
          />
        </label>

        {files.length > 0 ? (
          <ul className="selected-files" aria-label="Selected files">
            {files.map((file) => (
              <li key={`${file.name}-${file.size}`}>
                <span>{file.name}</span>
                <span>{selectedFileContext}</span>
                <span>{formatBytes(file.size)}</span>
              </li>
            ))}
          </ul>
        ) : null}

        <div className="message-stack">
          {message ? <p className="success-text">{message}</p> : null}
          {error ? <p className="error-text">{error}</p> : null}
        </div>

        <div className="action-row">
          <button className="primary-button" disabled={isUploading} type="submit">
            {isUploading ? "Uploading..." : "Upload Files"}
          </button>
          <button
            className="secondary-button"
            disabled={!hasActionBatchIds || isIngestingBatches}
            type="button"
            onClick={() => void handleIngestFiles()}
          >
            {isIngestingBatches ? "Ingesting..." : "Ingest Files"}
          </button>
          <button
            className="secondary-button"
            disabled={!hasActionBatchIds || isNormalizingBatches}
            type="button"
            onClick={() => void handleNormalizeFiles()}
          >
            {isNormalizingBatches ? "Normalizing..." : "Normalize Ready Files"}
          </button>
          <button
            className="secondary-button"
            disabled={files.length === 0}
            type="button"
            onClick={handleClearSelectedFiles}
          >
            Clear Files
          </button>
          <button className="secondary-button" type="button" onClick={() => void refreshBatches()}>
            {isLoadingBatches ? "Refreshing..." : "Refresh Batches"}
          </button>
          <button className="secondary-button" type="button" onClick={handleClearDetails}>
            Clear Details
          </button>
        </div>

        {hasActionBatchIds ? (
          <p className="muted-text action-scope-text">
            Actions will use{" "}
            {uploadedActionBatchIds.length > 0
              ? `${uploadedActionBatchIds.length} batch(es) from the latest upload.`
              : "the selected batch."}
          </p>
        ) : null}

        {uploadResult ? (
          <div className="summary-block">
            <p className="label">Upload Results</p>
            <div className="summary-grid mapping-summary-grid">
              <div>
                <p className="label">Selected</p>
                <strong>{uploadResult.totals.files_selected}</strong>
              </div>
              <div>
                <p className="label">Uploaded</p>
                <strong>{uploadResult.totals.files_uploaded}</strong>
              </div>
              <div>
                <p className="label">Failed</p>
                <strong>{uploadResult.totals.files_failed}</strong>
              </div>
            </div>
            <div className="table-wrap summary-block">
              <table>
                <thead>
                  <tr>
                    <th>File</th>
                    <th>Status</th>
                    <th>Size</th>
                    <th>Batch ID</th>
                    <th>Message</th>
                  </tr>
                </thead>
                <tbody>
                  {uploadResult.files.map((fileResult) => (
                    <tr key={`${fileResult.filename}-${fileResult.upload_batch_id ?? fileResult.status}`}>
                      <td>{fileResult.filename}</td>
                      <td>{fileResult.status}</td>
                      <td>
                        {fileResult.size_bytes === null
                          ? "Not available"
                          : formatBytes(fileResult.size_bytes)}
                      </td>
                      <td className="mono-text">{fileResult.upload_batch_id ?? "Not available"}</td>
                      <td>
                        {fileResult.message ||
                          fileResult.warnings.join("; ") ||
                          "No issues reported"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ) : null}

        {ingestResult ? (
          <div className="summary-block">
            <p className="label">Ingest Results</p>
            <div className="summary-grid mapping-summary-grid">
              <div>
                <p className="label">Requested</p>
                <strong>{ingestResult.totals.batches_requested}</strong>
              </div>
              <div>
                <p className="label">Ingested</p>
                <strong>{ingestResult.totals.batches_ingested}</strong>
              </div>
              <div>
                <p className="label">Failed</p>
                <strong>{ingestResult.totals.batches_failed}</strong>
              </div>
              <div>
                <p className="label">Raw Rows</p>
                <strong>{ingestResult.totals.raw_rows_inserted.toLocaleString()}</strong>
              </div>
            </div>
            <div className="table-wrap summary-block">
              <table>
                <thead>
                  <tr>
                    <th>Batch</th>
                    <th>File</th>
                    <th>Status</th>
                    <th>Raw Rows</th>
                    <th>Error</th>
                  </tr>
                </thead>
                <tbody>
                  {ingestResult.batches.map((batchResult) => (
                    <tr key={batchResult.upload_batch_id}>
                      <td>{batchResult.batch_name}</td>
                      <td>{batchResult.filename ?? "Not available"}</td>
                      <td>{batchResult.status}</td>
                      <td>{batchResult.raw_rows_inserted.toLocaleString()}</td>
                      <td>{batchResult.error ?? "None"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ) : null}

        {normalizeResult ? (
          <div className="summary-block">
            <p className="label">Normalization Results</p>
            <div className="summary-grid mapping-summary-grid">
              <div>
                <p className="label">Raw Rows</p>
                <strong>{normalizeResult.totals.raw_rows.toLocaleString()}</strong>
              </div>
              <div>
                <p className="label">In Scope</p>
                <strong>{normalizeResult.totals.in_scope_inserted.toLocaleString()}</strong>
              </div>
              <div>
                <p className="label">Out of Scope</p>
                <strong>{normalizeResult.totals.out_of_scope_inserted.toLocaleString()}</strong>
              </div>
              <div>
                <p className="label">Failed Batches</p>
                <strong>{normalizeResult.totals.failed_batches}</strong>
              </div>
            </div>
            <div className="table-wrap summary-block">
              <table>
                <thead>
                  <tr>
                    <th>Batch</th>
                    <th>File</th>
                    <th>Status</th>
                    <th>Raw</th>
                    <th>In Scope</th>
                    <th>Out of Scope</th>
                    <th>Failed Rows</th>
                    <th>Messages</th>
                  </tr>
                </thead>
                <tbody>
                  {normalizeResult.batches.map((batchResult) => (
                    <tr key={batchResult.upload_batch_id}>
                      <td>{batchResult.batch_name}</td>
                      <td>{batchResult.filename ?? "Not available"}</td>
                      <td>{batchResult.status}</td>
                      <td>{batchResult.raw_rows.toLocaleString()}</td>
                      <td>{batchResult.in_scope_inserted.toLocaleString()}</td>
                      <td>{batchResult.out_of_scope_inserted.toLocaleString()}</td>
                      <td>{batchResult.failed_rows.toLocaleString()}</td>
                      <td>
                        {[...batchResult.warnings, ...batchResult.errors].join("; ") ||
                          "No issues reported"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ) : null}
      </form>

      <section className="panel" aria-labelledby="active-batch-list-heading">
        <div className="panel-heading">
          <div>
            <p className="label">Staging</p>
            <h2 id="active-batch-list-heading">Active Upload Batches</h2>
          </div>
        </div>

        {batches.length === 0 ? (
          <p className="muted-text">No active upload batches found.</p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Batch</th>
                  <th>Ticket Type</th>
                  <th>Period</th>
                  <th>Status</th>
                  <th>Files</th>
                  <th>Size</th>
                  <th>Created</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {batches.map((batch) => (
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
                    <td>{batch.ticket_type ?? "Not available"}</td>
                    <td>{formatBatchPeriod(batch)}</td>
                    <td>{batch.status}</td>
                    <td>{getBatchFileCount(batch)}</td>
                    <td>{formatBytes(batch.total_size_bytes)}</td>
                    <td>{new Date(batch.created_at).toLocaleString()}</td>
                    <td>
                      <button
                        className="secondary-button table-action-button danger-button"
                        type="button"
                        onClick={(event) => {
                          event.stopPropagation();
                          void handleDeleteBatch(batch);
                        }}
                      >
                        Delete Batch
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="panel" aria-labelledby="historical-batch-list-heading">
        <div className="panel-heading">
          <div>
            <p className="label">History</p>
            <h2 id="historical-batch-list-heading">Historical Batches</h2>
          </div>
        </div>

        {historicalBatches.length === 0 ? (
          <p className="muted-text">No historical batches found.</p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Batch</th>
                  <th>Ticket Type</th>
                  <th>Period</th>
                  <th>Status</th>
                  <th>Files</th>
                  <th>Raw Rows</th>
                  <th>Tickets</th>
                  <th>Normalized</th>
                </tr>
              </thead>
              <tbody>
                {historicalBatches.map((batch) => (
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
                    <td>{batch.ticket_type ?? "Not available"}</td>
                    <td>{formatBatchPeriod(batch)}</td>
                    <td>{batch.status}</td>
                    <td>{getBatchFileCount(batch)}</td>
                    <td>{batch.raw_row_count ?? "Not available"}</td>
                    <td>{batch.normalized_ticket_count ?? "Not available"}</td>
                    <td>
                      {batch.normalized_at
                        ? new Date(batch.normalized_at).toLocaleString()
                        : "Not available"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="panel" aria-labelledby="file-list-heading">
        <div className="panel-heading">
          <div>
            <p className="label">Batch Details</p>
            <h2 id="file-list-heading">Uploaded Files</h2>
          </div>
          <button
            className="secondary-button"
            disabled={!selectedBatchId}
            type="button"
            onClick={handleClearDetails}
          >
            Clear Details
          </button>
        </div>

        {!selectedBatchId ? (
          <p className="muted-text">No batch selected.</p>
        ) : isLoadingFiles ? (
          <p className="muted-text">Loading uploaded files...</p>
        ) : selectedBatchFiles.length === 0 ? (
          <p className="muted-text">No files found for this batch.</p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Original File</th>
                  <th>Saved File</th>
                  <th>Type</th>
                  <th>Status</th>
                  <th>Size</th>
                  <th>Error</th>
                  <th>Ingestion</th>
                </tr>
              </thead>
              <tbody>
                {selectedBatchFiles.map((uploadedFile) => (
                  <tr key={uploadedFile.id}>
                    <td>{uploadedFile.original_filename}</td>
                    <td>{uploadedFile.saved_filename ?? "Not available"}</td>
                    <td>{uploadedFile.ticket_type}</td>
                    <td>
                      {jobByUploadedFileId.get(uploadedFile.id)?.status ?? uploadedFile.status}
                    </td>
                    <td>{formatBytes(uploadedFile.size_bytes)}</td>
                    <td>{uploadedFile.error_message ?? "None"}</td>
                    <td>
                      <button
                        className="secondary-button table-action-button"
                        disabled={
                          ingestingFileIds.has(uploadedFile.id) ||
                          jobByUploadedFileId.get(uploadedFile.id)?.status === "COMPLETED" ||
                          uploadedFile.status === "INGESTED"
                        }
                        type="button"
                        onClick={() => void handleIngestFile(uploadedFile)}
                      >
                        {getIngestButtonText(uploadedFile)}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="panel" aria-labelledby="job-status-heading">
        <div className="panel-heading">
          <div>
            <p className="label">Ingestion</p>
            <h2 id="job-status-heading">Job Status</h2>
          </div>
          <button className="secondary-button" type="button" onClick={() => void refreshTrackedJobs()}>
            Refresh Jobs
          </button>
        </div>

        {trackedJobs.length === 0 ? (
          <p className="muted-text">No tracked ingestion jobs.</p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Job ID</th>
                  <th>File ID</th>
                  <th>Status</th>
                  <th>Rows</th>
                  <th>Error</th>
                  <th>Updated</th>
                </tr>
              </thead>
              <tbody>
                {trackedJobs.map((job) => (
                  <tr key={job.id}>
                    <td className="mono-text">{job.id}</td>
                    <td className="mono-text">{job.uploaded_file_id ?? "Not available"}</td>
                    <td>{job.status}</td>
                    <td>
                      {job.rows_processed} / {job.rows_total}
                    </td>
                    <td>{job.error_message ?? "None"}</td>
                    <td>{new Date(job.updated_at).toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="panel" aria-labelledby="raw-row-preview-heading">
        <div className="panel-heading">
          <div>
            <p className="label">Staging</p>
            <h2 id="raw-row-preview-heading">Raw Row Preview</h2>
          </div>
          <div className="panel-actions">
            <button
              className="secondary-button"
              disabled={!selectedBatchId}
              type="button"
              onClick={() => void refreshRawRowsPreview(selectedBatchId)}
            >
              {isLoadingPreview ? "Refreshing..." : "Refresh Preview"}
            </button>
            <button
              className="secondary-button"
              disabled={!rawRowsPreview}
              type="button"
              onClick={handleClearPreview}
            >
              Clear Preview
            </button>
          </div>
        </div>

        {!selectedBatchId ? (
          <p className="muted-text">No batch selected.</p>
        ) : isLoadingPreview ? (
          <p className="muted-text">Loading raw rows...</p>
        ) : !rawRowsPreview ? (
          <p className="muted-text">Raw row preview is cleared or not loaded.</p>
        ) : rawRowsPreview.rows.length === 0 ? (
          <p className="muted-text">
            {rawRowsPreview.message ?? "No raw rows found. Ingest the uploaded file first."}
          </p>
        ) : (
          <div className="raw-preview-list">
            {rawRowsPreview.rows.map((row) => (
              <article className="raw-preview-item" key={row.id}>
                <div className="raw-preview-meta">
                  <span>Row {row.row_number}</span>
                  <span>{row.source_filename ?? "Unknown source"}</span>
                  <span>{row.raw_ticket_number ?? "No ticket ID"}</span>
                </div>
                <pre>{JSON.stringify(row.raw_data, null, 2)}</pre>
              </article>
            ))}
          </div>
        )}
      </section>

      <section className="panel" aria-labelledby="validation-summary-heading">
        <div className="panel-heading">
          <div>
            <p className="label">Quality</p>
            <h2 id="validation-summary-heading">Validation Summary</h2>
          </div>
          <div className="panel-actions">
            <button
              className="secondary-button"
              disabled={!selectedBatchId}
              type="button"
              onClick={() => void refreshValidationSummary(selectedBatchId)}
            >
              {isLoadingValidation ? "Refreshing..." : "Refresh Summary"}
            </button>
            <button
              className="secondary-button"
              disabled={!validationSummary}
              type="button"
              onClick={handleClearValidationSummary}
            >
              Clear Summary
            </button>
          </div>
        </div>

        {!selectedBatchId ? (
          <p className="muted-text">No batch selected.</p>
        ) : isLoadingValidation ? (
          <p className="muted-text">Loading validation summary...</p>
        ) : !validationSummary ? (
          <p className="muted-text">Validation summary is cleared or not loaded.</p>
        ) : (
          <>
            {validationSummary.message ? (
              <p className="muted-text summary-message">{validationSummary.message}</p>
            ) : null}
            <div className="summary-grid">
              <div>
                <p className="label">Total Raw Rows</p>
                <strong>{validationSummary.total_raw_rows}</strong>
              </div>
              <div>
                <p className="label">Missing Ticket ID</p>
                <strong>{validationSummary.missing_ticket_id_count}</strong>
              </div>
              <div>
                <p className="label">Missing Created Date</p>
                <strong>{validationSummary.missing_created_date_count}</strong>
              </div>
              <div>
                <p className="label">Duplicate Ticket IDs</p>
                <strong>{validationSummary.duplicate_ticket_id_count}</strong>
              </div>
            </div>

            {duplicateTicketEntries.length > 0 ? (
              <div className="summary-block">
                <p className="label">Duplicate IDs</p>
                <div className="chip-list">
                  {duplicateTicketEntries.slice(0, 20).map(([ticketId, count]) => (
                    <span className="chip" key={ticketId}>
                      {ticketId} ({count})
                    </span>
                  ))}
                </div>
              </div>
            ) : null}

            <div className="summary-block">
              <p className="label">Detected Source Columns</p>
              <div className="chip-list">
                {validationSummary.detected_source_columns.map((column) => (
                  <span className="chip" key={column}>
                    {column}
                  </span>
                ))}
              </div>
            </div>

            <div className="summary-block table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Uploaded File</th>
                    <th>Rows</th>
                  </tr>
                </thead>
                <tbody>
                  {validationSummary.rows_by_uploaded_file.map((fileSummary) => (
                    <tr key={fileSummary.uploaded_file_id}>
                      <td>{fileSummary.original_filename}</td>
                      <td>{fileSummary.row_count}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </section>
    </div>
  );
}

export default UploadCenter;
