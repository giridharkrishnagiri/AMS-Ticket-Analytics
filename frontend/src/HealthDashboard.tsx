import { useCallback, useMemo, useState } from "react";

import { getBackendHealth } from "./api/health";
import type { BackendHealth } from "./api/health";
import { formatDisplayDateTime } from "./utils/dateFormat";

type StatusState = "unchecked" | "checking" | "online" | "degraded" | "offline";

function HealthDashboard() {
  const [health, setHealth] = useState<BackendHealth | null>(null);
  const [status, setStatus] = useState<StatusState>("unchecked");
  const [error, setError] = useState<string | null>(null);
  const [lastCheckedAt, setLastCheckedAt] = useState<Date | null>(null);

  const loadHealth = useCallback(async (signal?: AbortSignal) => {
    setStatus("checking");
    setError(null);

    try {
      const backendHealth = await getBackendHealth(signal);
      const backendStatus = backendHealth.status.toLowerCase();
      setHealth(backendHealth);
      setStatus(backendStatus === "ok" ? "online" : "degraded");
      setLastCheckedAt(new Date());
    } catch (requestError) {
      if (requestError instanceof DOMException && requestError.name === "AbortError") {
        return;
      }

      setHealth(null);
      setStatus("offline");
      setLastCheckedAt(new Date());
      setError(requestError instanceof Error ? requestError.message : "Unable to reach backend");
    }
  }, []);

  const statusText = useMemo(() => {
    if (status === "online") {
      return "Online";
    }

    if (status === "degraded") {
      return "Degraded";
    }

    if (status === "offline") {
      return "Offline";
    }

    return status === "checking" ? "Checking" : "Not checked";
  }, [status]);

  return (
    <>
      <div className="status-grid">
        <article className="status-card status-card-main">
          <div className="status-card-header">
            <span className={`status-dot status-${status}`} aria-hidden="true" />
            <div>
              <p className="label">Backend API</p>
              <h2>{statusText}</h2>
            </div>
          </div>
          <p className="status-message">
            {status === "online"
              ? "FastAPI and diagnostics are responding."
              : status === "offline"
                ? "The frontend could not reach the FastAPI health endpoint."
                : status === "degraded"
                  ? "One or more diagnostics returned a degraded result."
                  : status === "checking"
                    ? "Contacting the backend health endpoint..."
                    : "Click Run Health Check to inspect backend, database, locks, and frontends."}
          </p>
          {error ? <p className="error-text">{error}</p> : null}
        </article>

        <article className="status-card">
          <p className="label">Service</p>
          <strong>{health?.service ?? "Not available"}</strong>
        </article>

        <article className="status-card">
          <p className="label">Version</p>
          <strong>{health?.version ?? "Not available"}</strong>
        </article>

        <article className="status-card">
          <p className="label">Environment</p>
          <strong>{health?.environment ?? "Not available"}</strong>
        </article>
      </div>

      <section className="detail-panel" aria-label="Backend details">
        <div>
          <p className="label">Backend checked at</p>
          <p>{health?.checked_at ? formatDisplayDateTime(health.checked_at) : "Pending"}</p>
        </div>
        <div>
          <p className="label">Frontend checked at</p>
          <p>{lastCheckedAt ? formatDisplayDateTime(lastCheckedAt) : "Pending"}</p>
        </div>
        <div>
          <p className="label">Storage root</p>
          <p className="path-text">{health?.storage_root ?? "Pending"}</p>
        </div>
      </section>

      <div className="action-row">
        <button className="primary-button" type="button" onClick={() => void loadHealth()}>
          {status === "checking" ? "Checking..." : "Run Health Check"}
        </button>
      </div>
    </>
  );
}

export default HealthDashboard;
