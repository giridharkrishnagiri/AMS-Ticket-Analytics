import { useEffect, useState } from "react";
import type { ChangeEvent, FormEvent } from "react";

import {
  deduplicateIncidentSlaRows,
  enrichIncidentSla,
  getIncidentSlaSummary,
  getIncidentSlaUploadHistory,
  getUnmatchedIncidentSlaNumbers,
  uploadIncidentSlaFiles,
} from "./api/sla";
import type {
  IncidentSlaDeduplicateResponse,
  IncidentSlaEnrichResponse,
  IncidentSlaMultiUploadResponse,
  IncidentSlaScopeStats,
  IncidentSlaSummaryResponse,
  IncidentSlaUnmatchedResponse,
  IncidentSlaUploadHistoryRow,
  IncidentSlaUploadResponse,
} from "./api/sla";
import CustomerSelector from "./CustomerSelector";
import { formatDisplayDateTime } from "./utils/dateFormat";

const deduplicateConfirmation = "DEDUPLICATE SLA ROWS";

function formatNumber(value: number): string {
  return value.toLocaleString();
}

function formatDate(value: string): string {
  return formatDisplayDateTime(value);
}

function ResultList({ title, values }: { title: string; values: string[] }) {
  if (values.length === 0) {
    return null;
  }

  return (
    <div className="summary-block">
      <p className="label">{title}</p>
      <ul className="selected-files">
        {values.map((value) => (
          <li key={value}>{value}</li>
        ))}
      </ul>
    </div>
  );
}

function UploadResultTable({ files }: { files: IncidentSlaUploadResponse[] }) {
  if (files.length === 0) {
    return null;
  }

  return (
    <div className="table-wrap summary-block">
      <table>
        <thead>
          <tr>
            <th>File</th>
            <th>Status</th>
            <th>Rows read</th>
            <th>Inserted</th>
            <th>Duplicates skipped</th>
            <th>Errors</th>
          </tr>
        </thead>
        <tbody>
          {files.map((file) => (
            <tr key={`${file.uploaded_file_name}-${file.upload_id ?? file.status}`}>
              <td>{file.uploaded_file_name}</td>
              <td>{file.status}</td>
              <td>{formatNumber(file.total_rows)}</td>
              <td>{formatNumber(file.inserted_rows)}</td>
              <td>{formatNumber(file.duplicate_rows_skipped)}</td>
              <td>{formatNumber(file.failed_rows)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ScopeStatsCard({ title, stats }: { title: string; stats: IncidentSlaScopeStats }) {
  return (
    <div className="summary-block">
      <p className="label">{title}</p>
      <div className="summary-grid mapping-summary-grid">
        <div>
          <p className="label">Considered</p>
          <strong>{formatNumber(stats.incident_tickets_considered)}</strong>
        </div>
        <div>
          <p className="label">Matched to SLA rows</p>
          <strong>{formatNumber(stats.incident_tickets_matched_to_sla_rows)}</strong>
        </div>
        <div>
          <p className="label">Enriched</p>
          <strong>{formatNumber(stats.incident_tickets_enriched)}</strong>
        </div>
        <div>
          <p className="label">Response enriched</p>
          <strong>{formatNumber(stats.response_sla_enriched)}</strong>
        </div>
        <div>
          <p className="label">Resolution enriched</p>
          <strong>{formatNumber(stats.resolution_sla_enriched)}</strong>
        </div>
        <div>
          <p className="label">Response vendor-specific</p>
          <strong>{formatNumber(stats.response_vendor_specific)}</strong>
        </div>
        <div>
          <p className="label">Response default</p>
          <strong>{formatNumber(stats.response_default)}</strong>
        </div>
        <div>
          <p className="label">Response fallback</p>
          <strong>{formatNumber(stats.response_fallback_default)}</strong>
        </div>
        <div>
          <p className="label">Response not found</p>
          <strong>{formatNumber(stats.response_not_found)}</strong>
        </div>
        <div>
          <p className="label">Resolution vendor-specific</p>
          <strong>{formatNumber(stats.resolution_vendor_specific)}</strong>
        </div>
        <div>
          <p className="label">Resolution default</p>
          <strong>{formatNumber(stats.resolution_default)}</strong>
        </div>
        <div>
          <p className="label">Resolution fallback</p>
          <strong>{formatNumber(stats.resolution_fallback_default)}</strong>
        </div>
        <div>
          <p className="label">Resolution not found</p>
          <strong>{formatNumber(stats.resolution_not_found)}</strong>
        </div>
      </div>
    </div>
  );
}

function SlaUpload() {
  const [projectId, setProjectId] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [uploadResult, setUploadResult] = useState<IncidentSlaMultiUploadResponse | null>(null);
  const [uploadHistory, setUploadHistory] = useState<IncidentSlaUploadHistoryRow[]>([]);
  const [enrichResult, setEnrichResult] = useState<IncidentSlaEnrichResponse | null>(null);
  const [deduplicateResult, setDeduplicateResult] =
    useState<IncidentSlaDeduplicateResponse | null>(null);
  const [summary, setSummary] = useState<IncidentSlaSummaryResponse | null>(null);
  const [unmatchedRows, setUnmatchedRows] = useState<IncidentSlaUnmatchedResponse | null>(null);
  const [deduplicateText, setDeduplicateText] = useState("");
  const [isUploading, setIsUploading] = useState(false);
  const [isEnriching, setIsEnriching] = useState(false);
  const [isDeduplicating, setIsDeduplicating] = useState(false);
  const [isLoadingSummary, setIsLoadingSummary] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  function handleFileSelection(event: ChangeEvent<HTMLInputElement>) {
    setFiles(Array.from(event.target.files ?? []));
  }

  async function refreshSummary(nextProjectId = projectId, showMessage = true) {
    if (!nextProjectId.trim()) {
      setError("Customer is required.");
      return;
    }

    setIsLoadingSummary(true);
    setError(null);

    try {
      const [nextSummary, nextUnmatchedRows, nextUploadHistory] = await Promise.all([
        getIncidentSlaSummary(nextProjectId),
        getUnmatchedIncidentSlaNumbers(nextProjectId, 50),
        getIncidentSlaUploadHistory(nextProjectId),
      ]);
      setSummary(nextSummary);
      setUnmatchedRows(nextUnmatchedRows);
      setUploadHistory(nextUploadHistory);
      if (showMessage) {
        setMessage("Incident SLA history and summary refreshed.");
      }
    } catch (requestError) {
      setError(
        requestError instanceof Error ? requestError.message : "Unable to load Incident SLA summary"
      );
    } finally {
      setIsLoadingSummary(false);
    }
  }

  useEffect(() => {
    setUploadResult(null);
    setEnrichResult(null);
    setDeduplicateResult(null);
    setMessage(null);
    setError(null);
    if (projectId.trim()) {
      void refreshSummary(projectId, false);
    } else {
      setSummary(null);
      setUnmatchedRows(null);
      setUploadHistory([]);
    }
  }, [projectId]);

  async function handleUpload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!projectId.trim()) {
      setError("Customer is required.");
      return;
    }
    if (files.length === 0) {
      setError("Select one or more Incident SLA CSV/XLSX files first.");
      return;
    }

    setIsUploading(true);
    setError(null);
    setMessage(null);

    try {
      const result = await uploadIncidentSlaFiles(projectId, files);
      setUploadResult(result);
      setMessage(
        `Processed ${formatNumber(result.totals.total_files)} files, inserted ${formatNumber(
          result.totals.inserted_rows
        )} rows, skipped ${formatNumber(result.totals.duplicate_rows_skipped)} duplicates.`
      );
      await refreshSummary(projectId, false);
    } catch (requestError) {
      setError(
        requestError instanceof Error ? requestError.message : "Incident SLA upload failed"
      );
    } finally {
      setIsUploading(false);
    }
  }

  async function handleEnrich() {
    if (!projectId.trim()) {
      setError("Customer is required.");
      return;
    }

    const confirmed = window.confirm(
      "This will replace existing Incident response/resolution SLA enrichment values for in-scope and out-of-scope Incident tickets. SC Tasks and raw uploaded data will not be changed."
    );
    if (!confirmed) {
      return;
    }

    setIsEnriching(true);
    setError(null);
    setMessage(null);

    try {
      const result = await enrichIncidentSla(projectId, true);
      setEnrichResult(result);
      setMessage("Incident SLA enrichment completed for all uploaded SLA rows.");
      await refreshSummary(projectId, false);
    } catch (requestError) {
      setError(
        requestError instanceof Error ? requestError.message : "Incident SLA enrichment failed"
      );
    } finally {
      setIsEnriching(false);
    }
  }

  async function handleDeduplicate() {
    if (!projectId.trim()) {
      setError("Customer is required.");
      return;
    }
    if (deduplicateText !== deduplicateConfirmation) {
      setError(`Confirmation text must match exactly: ${deduplicateConfirmation}`);
      return;
    }

    const confirmed = window.confirm(
      "This will remove duplicate Incident SLA rows for the selected project and keep the earliest copy. Tickets and Application Inventory will not be deleted."
    );
    if (!confirmed) {
      return;
    }

    setIsDeduplicating(true);
    setError(null);
    setMessage(null);
    try {
      const result = await deduplicateIncidentSlaRows(projectId, deduplicateText);
      setDeduplicateResult(result);
      setMessage(
        `Removed ${formatNumber(result.duplicate_rows_deleted)} duplicate SLA rows.`
      );
      await refreshSummary(projectId, false);
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Incident SLA deduplication failed"
      );
    } finally {
      setIsDeduplicating(false);
    }
  }

  return (
    <section className="upload-layout" aria-labelledby="sla-upload-heading">
      <div className="panel">
        <div className="panel-heading">
          <div>
            <p className="label">Incident SLA</p>
            <h2 id="sla-upload-heading">SLA Upload / Enrichment</h2>
          </div>
          <div className="panel-actions">
            <button
              className="secondary-button"
              type="button"
              onClick={() => void refreshSummary()}
              disabled={!projectId.trim() || isLoadingSummary}
            >
              {isLoadingSummary ? "Refreshing..." : "Refresh History"}
            </button>
            <button
              className="primary-button"
              type="button"
              onClick={() => void handleEnrich()}
              disabled={!projectId.trim() || isEnriching}
            >
              {isEnriching ? "Enriching..." : "Enrich Incident SLA"}
            </button>
          </div>
        </div>

        <form className="upload-form" onSubmit={(event) => void handleUpload(event)}>
          <div className="form-grid">
            <CustomerSelector projectId={projectId} onProjectIdChange={setProjectId} />
            <label>
              <span>Incident SLA Files</span>
              <input
                type="file"
                accept=".csv,.xlsx,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                multiple
                onChange={handleFileSelection}
              />
            </label>
          </div>

          {files.length ? (
            <div className="summary-block">
              <p className="label">Selected Files</p>
              <ul className="selected-files">
                {files.map((file) => (
                  <li key={`${file.name}-${file.size}`}>{file.name}</li>
                ))}
              </ul>
            </div>
          ) : null}

          <div className="action-row">
            <button
              className="primary-button"
              type="submit"
              disabled={!projectId.trim() || files.length === 0 || isUploading}
            >
              {isUploading ? "Uploading..." : "Upload Selected SLA Files"}
            </button>
          </div>
        </form>

        <div className="message-stack" role="status" aria-live="polite">
          {message ? <p className="success-text">{message}</p> : null}
          {error ? <p className="error-text">{error}</p> : null}
          <p className="muted-text">
            Upload stages SLA rows first. Click Enrich Incident SLA once after uploading one or
            more SLA files for the selected customer.
          </p>
        </div>
      </div>

      {uploadResult ? (
        <div className="panel">
          <div className="panel-heading">
            <div>
              <p className="label">Latest Upload</p>
              <h2>Multi-file Upload Result</h2>
            </div>
          </div>
          <div className="summary-grid">
            <div>
              <p className="label">Files</p>
              <strong>{formatNumber(uploadResult.totals.total_files)}</strong>
            </div>
            <div>
              <p className="label">Rows read</p>
              <strong>{formatNumber(uploadResult.totals.total_rows_read)}</strong>
            </div>
            <div>
              <p className="label">Inserted</p>
              <strong>{formatNumber(uploadResult.totals.inserted_rows)}</strong>
            </div>
            <div>
              <p className="label">Duplicates skipped</p>
              <strong>{formatNumber(uploadResult.totals.duplicate_rows_skipped)}</strong>
            </div>
            <div>
              <p className="label">Error rows</p>
              <strong>{formatNumber(uploadResult.totals.error_rows)}</strong>
            </div>
          </div>
          <UploadResultTable files={uploadResult.files} />
          {uploadResult.files.map((file) => (
            <div key={`${file.uploaded_file_name}-messages`}>
              <ResultList title={`${file.uploaded_file_name} warnings`} values={file.warnings} />
              <ResultList title={`${file.uploaded_file_name} errors`} values={file.errors} />
            </div>
          ))}
        </div>
      ) : null}

      <div className="panel">
        <div className="panel-heading">
          <div>
            <p className="label">Uploaded SLA Files</p>
            <h2>Persistent Upload History</h2>
          </div>
        </div>
        {uploadHistory.length === 0 ? (
          <p className="muted-text">No Incident SLA uploads found for this customer.</p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>File</th>
                  <th>Uploaded</th>
                  <th>Status</th>
                  <th>Rows read</th>
                  <th>Inserted</th>
                  <th>Duplicates skipped</th>
                  <th>Errors</th>
                </tr>
              </thead>
              <tbody>
                {uploadHistory.map((row) => (
                  <tr key={row.upload_id}>
                    <td>{row.filename}</td>
                    <td>{formatDate(row.uploaded_at)}</td>
                    <td>{row.status}</td>
                    <td>{formatNumber(row.total_rows_read)}</td>
                    <td>{formatNumber(row.inserted_rows)}</td>
                    <td>{formatNumber(row.duplicate_rows_skipped)}</td>
                    <td>{formatNumber(row.error_rows)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="panel">
        <div className="panel-heading">
          <div>
            <p className="label">Duplicate Cleanup</p>
            <h2>Remove Duplicate SLA Rows</h2>
          </div>
        </div>
        <div className="form-grid">
          <label>
            <span>Confirmation</span>
            <input
              value={deduplicateText}
              onChange={(event) => setDeduplicateText(event.target.value)}
              placeholder={deduplicateConfirmation}
            />
            <span className="helper-text">Required text: {deduplicateConfirmation}</span>
          </label>
        </div>
        <div className="action-row summary-block">
          <button
            className="secondary-button danger-button"
            type="button"
            onClick={() => void handleDeduplicate()}
            disabled={
              !projectId.trim() ||
              deduplicateText !== deduplicateConfirmation ||
              isDeduplicating
            }
          >
            {isDeduplicating ? "Removing..." : "Remove Duplicate SLA Rows"}
          </button>
        </div>
        {deduplicateResult ? (
          <div className="summary-grid summary-block">
            <div>
              <p className="label">Duplicate groups</p>
              <strong>{formatNumber(deduplicateResult.duplicate_groups_found)}</strong>
            </div>
            <div>
              <p className="label">Rows deleted</p>
              <strong>{formatNumber(deduplicateResult.duplicate_rows_deleted)}</strong>
            </div>
            <div>
              <p className="label">Remaining SLA rows</p>
              <strong>{formatNumber(deduplicateResult.remaining_sla_rows)}</strong>
            </div>
          </div>
        ) : null}
      </div>

      {enrichResult ? (
        <div className="panel">
          <div className="panel-heading">
            <div>
              <p className="label">Latest Enrichment</p>
              <h2>Incident SLA Result</h2>
            </div>
          </div>
          <div className="summary-grid">
            <div>
              <p className="label">SLA rows</p>
              <strong>{formatNumber(enrichResult.sla_rows.total_rows)}</strong>
            </div>
            <div>
              <p className="label">Distinct SLA ticket numbers</p>
              <strong>
                {formatNumber(enrichResult.sla_rows.distinct_ticket_numbers_in_sla_rows)}
              </strong>
            </div>
            <div>
              <p className="label">Duplicate rows skipped</p>
              <strong>
                {formatNumber(enrichResult.sla_rows.duplicate_rows_skipped_on_upload)}
              </strong>
            </div>
            <div>
              <p className="label">SLA numbers not found</p>
              <strong>
                {formatNumber(
                  enrichResult.unmatched.sla_ticket_numbers_not_found_in_scope_or_out_of_scope
                )}
              </strong>
            </div>
            <div>
              <p className="label">In-scope without SLA</p>
              <strong>
                {formatNumber(enrichResult.unmatched.in_scope_incidents_without_sla_rows)}
              </strong>
            </div>
            <div>
              <p className="label">Out-of-scope without SLA</p>
              <strong>
                {formatNumber(enrichResult.unmatched.out_of_scope_incidents_without_sla_rows)}
              </strong>
            </div>
          </div>
          <ScopeStatsCard title="In-Scope Incident SLA Stats" stats={enrichResult.in_scope} />
          <ScopeStatsCard
            title="Out-of-Scope Incident SLA Stats"
            stats={enrichResult.out_of_scope}
          />
          <ResultList title="Notes" values={enrichResult.warnings} />
        </div>
      ) : null}

      {summary ? (
        <div className="panel">
          <div className="panel-heading">
            <div>
              <p className="label">SLA Summary</p>
              <h2>Incident SLA Coverage</h2>
            </div>
          </div>
          <div className="summary-grid">
            <div>
              <p className="label">SLA rows</p>
              <strong>{formatNumber(summary.total_sla_rows)}</strong>
            </div>
            <div>
              <p className="label">Unique incidents</p>
              <strong>{formatNumber(summary.unique_incident_numbers)}</strong>
            </div>
            <div>
              <p className="label">Matched tickets</p>
              <strong>{formatNumber(summary.matched_tickets_count)}</strong>
            </div>
            <div>
              <p className="label">Unmatched incidents</p>
              <strong>{formatNumber(summary.unmatched_sla_incident_numbers_count)}</strong>
            </div>
            <div>
              <p className="label">Response selected</p>
              <strong>{formatNumber(summary.tickets_with_response_sla_selected)}</strong>
            </div>
            <div>
              <p className="label">Resolution selected</p>
              <strong>{formatNumber(summary.tickets_with_resolution_sla_selected)}</strong>
            </div>
            <div>
              <p className="label">Response breached</p>
              <strong>{formatNumber(summary.response_breached_count)}</strong>
            </div>
            <div>
              <p className="label">Resolution breached</p>
              <strong>{formatNumber(summary.resolution_breached_count)}</strong>
            </div>
          </div>
        </div>
      ) : null}

      {unmatchedRows?.rows.length ? (
        <div className="panel">
          <div className="panel-heading">
            <div>
              <p className="label">Mismatch Sample</p>
              <h2>Unmatched SLA Incident Numbers</h2>
            </div>
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Incident number</th>
                  <th>SLA rows</th>
                </tr>
              </thead>
              <tbody>
                {unmatchedRows.rows.map((row) => (
                  <tr key={row.inc_number}>
                    <td className="mono-text">{row.inc_number}</td>
                    <td>{formatNumber(row.row_count)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}
    </section>
  );
}

export default SlaUpload;
