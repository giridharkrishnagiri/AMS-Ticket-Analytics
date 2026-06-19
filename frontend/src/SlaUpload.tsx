import { useState } from "react";
import type { ChangeEvent, FormEvent } from "react";

import {
  enrichIncidentSla,
  getIncidentSlaSummary,
  getUnmatchedIncidentSlaNumbers,
  uploadIncidentSlaFile,
} from "./api/sla";
import type {
  IncidentSlaEnrichResponse,
  IncidentSlaSummaryResponse,
  IncidentSlaUnmatchedResponse,
  IncidentSlaUploadResponse,
} from "./api/sla";

function formatNumber(value: number): string {
  return value.toLocaleString();
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

function SlaUpload() {
  const [projectId, setProjectId] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [uploadResult, setUploadResult] = useState<IncidentSlaUploadResponse | null>(null);
  const [enrichResult, setEnrichResult] = useState<IncidentSlaEnrichResponse | null>(null);
  const [summary, setSummary] = useState<IncidentSlaSummaryResponse | null>(null);
  const [unmatchedRows, setUnmatchedRows] = useState<IncidentSlaUnmatchedResponse | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [isEnriching, setIsEnriching] = useState(false);
  const [isLoadingSummary, setIsLoadingSummary] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  function handleFileSelection(event: ChangeEvent<HTMLInputElement>) {
    setFile(event.target.files?.[0] ?? null);
  }

  async function refreshSummary(nextProjectId = projectId) {
    if (!nextProjectId.trim()) {
      setError("Project ID is required.");
      return;
    }

    setIsLoadingSummary(true);
    setError(null);

    try {
      const [nextSummary, nextUnmatchedRows] = await Promise.all([
        getIncidentSlaSummary(nextProjectId),
        getUnmatchedIncidentSlaNumbers(nextProjectId, 50),
      ]);
      setSummary(nextSummary);
      setUnmatchedRows(nextUnmatchedRows);
      setMessage("Incident SLA summary refreshed.");
    } catch (requestError) {
      setError(
        requestError instanceof Error ? requestError.message : "Unable to load Incident SLA summary"
      );
    } finally {
      setIsLoadingSummary(false);
    }
  }

  async function handleUpload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!projectId.trim()) {
      setError("Project ID is required.");
      return;
    }
    if (!file) {
      setError("Select an Incident SLA CSV file first.");
      return;
    }

    setIsUploading(true);
    setError(null);
    setMessage(null);

    try {
      const result = await uploadIncidentSlaFile(projectId, file);
      setUploadResult(result);
      setMessage(`Uploaded ${formatNumber(result.inserted_rows)} Incident SLA rows.`);
      await refreshSummary(projectId);
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
      setError("Project ID is required.");
      return;
    }

    const confirmed = window.confirm(
      "This will replace existing Incident response/resolution SLA enrichment values. Legacy sla_breached and raw uploaded data will not be changed."
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
      setMessage(
        `Enriched ${formatNumber(result.response_sla_updated_count)} response SLA and ${formatNumber(
          result.resolution_sla_updated_count
        )} resolution SLA values.`
      );
      await refreshSummary(projectId);
    } catch (requestError) {
      setError(
        requestError instanceof Error ? requestError.message : "Incident SLA enrichment failed"
      );
    } finally {
      setIsEnriching(false);
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
              {isLoadingSummary ? "Refreshing..." : "Refresh Summary"}
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
            <label>
              <span>Project ID</span>
              <input
                type="text"
                value={projectId}
                onChange={(event) => setProjectId(event.target.value)}
                placeholder="Paste project UUID"
              />
            </label>
            <label>
              <span>Incident SLA CSV</span>
              <input type="file" accept=".csv,text/csv" onChange={handleFileSelection} />
            </label>
          </div>

          <div className="action-row">
            <button
              className="primary-button"
              type="submit"
              disabled={!projectId.trim() || !file || isUploading}
            >
              {isUploading ? "Uploading..." : "Upload Incident SLA CSV"}
            </button>
          </div>
        </form>

        <div className="message-stack" role="status" aria-live="polite">
          {message ? <p className="success-text">{message}</p> : null}
          {error ? <p className="error-text">{error}</p> : null}
          <p className="muted-text">
            SLA enrichment only updates Incident response/resolution SLA columns. SC Tasks and
            legacy ticket SLA flags are left unchanged.
          </p>
        </div>
      </div>

      {uploadResult ? (
        <div className="panel">
          <div className="panel-heading">
            <div>
              <p className="label">Latest Upload</p>
              <h2>{uploadResult.uploaded_file_name}</h2>
            </div>
          </div>
          <div className="summary-grid">
            <div>
              <p className="label">Rows read</p>
              <strong>{formatNumber(uploadResult.total_rows)}</strong>
            </div>
            <div>
              <p className="label">Inserted</p>
              <strong>{formatNumber(uploadResult.inserted_rows)}</strong>
            </div>
            <div>
              <p className="label">Failed</p>
              <strong>{formatNumber(uploadResult.failed_rows)}</strong>
            </div>
            <div>
              <p className="label">Warnings</p>
              <strong>{formatNumber(uploadResult.warnings.length)}</strong>
            </div>
          </div>
          <ResultList title="Warnings" values={uploadResult.warnings} />
          <ResultList title="Errors" values={uploadResult.errors} />
        </div>
      ) : null}

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
              <p className="label">Matched tickets</p>
              <strong>{formatNumber(enrichResult.matched_ticket_count)}</strong>
            </div>
            <div>
              <p className="label">Response SLA</p>
              <strong>{formatNumber(enrichResult.response_sla_updated_count)}</strong>
            </div>
            <div>
              <p className="label">Resolution SLA</p>
              <strong>{formatNumber(enrichResult.resolution_sla_updated_count)}</strong>
            </div>
            <div>
              <p className="label">Replace existing</p>
              <strong>{enrichResult.replace_existing ? "Yes" : "No"}</strong>
            </div>
          </div>
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
          <div className="summary-grid mapping-summary-grid">
            <div>
              <p className="label">Response Accenture</p>
              <strong>{formatNumber(summary.response_accenture_selected_count)}</strong>
            </div>
            <div>
              <p className="label">Response Default</p>
              <strong>{formatNumber(summary.response_default_selected_count)}</strong>
            </div>
            <div>
              <p className="label">Resolution Accenture</p>
              <strong>{formatNumber(summary.resolution_accenture_selected_count)}</strong>
            </div>
            <div>
              <p className="label">Resolution Default</p>
              <strong>{formatNumber(summary.resolution_default_selected_count)}</strong>
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
