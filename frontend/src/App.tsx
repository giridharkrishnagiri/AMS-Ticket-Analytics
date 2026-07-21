import { useCallback, useState } from "react";

import Dashboard from "./Dashboard";
import GenAIWorkbench from "./GenAIWorkbench";
import Maintenance from "./Maintenance";
import UploadCenter from "./UploadCenter";
import { getBackendHealth } from "./api/health";
import type { BackendHealth } from "./api/health";
import { formatDisplayDateTime } from "./utils/dateFormat";

type AppView = "dashboard" | "maintenance" | "uploads" | "genai";
type HealthState = "unchecked" | "checking" | "healthy" | "degraded" | "offline";

function formatHealthStatus(value: string | null | undefined): string {
  if (!value) {
    return "Not available";
  }
  if (value.toLowerCase() === "ok") {
    return "Healthy";
  }
  return value.replace(/_/g, " ");
}

function healthClassForStatus(value: string | null | undefined): HealthState {
  const normalized = value?.toLowerCase();
  if (normalized === "ok" || normalized === "healthy") {
    return "healthy";
  }
  if (normalized === "error" || normalized === "offline") {
    return "offline";
  }
  if (normalized === "degraded" || normalized === "warning") {
    return "degraded";
  }
  return "unchecked";
}

function HealthIndicator({
  healthLabel,
  healthState,
  onOpen,
}: {
  healthLabel: string;
  healthState: HealthState;
  onOpen: () => void;
}) {
  return (
    <button
      className={`health-pill health-${healthState}`}
      aria-label={`Open system health details. Current status ${healthLabel}`}
      type="button"
      onClick={onOpen}
    >
      <span aria-hidden="true" />
      <strong>System Health:</strong> {healthLabel}
    </button>
  );
}

function HealthDetails({
  health,
  healthError,
  healthLabel,
  healthState,
  isRefreshing,
  onClose,
  onRefresh,
}: {
  health: BackendHealth | null;
  healthError: string | null;
  healthLabel: string;
  healthState: HealthState;
  isRefreshing: boolean;
  onClose: () => void;
  onRefresh: () => void;
}) {
  const checks = health?.checks ?? [];

  return (
    <section className="panel health-details-panel" aria-labelledby="health-details-heading">
      <div className="panel-heading">
        <div>
          <p className="label">Application Health</p>
          <h2 id="health-details-heading">Health Details</h2>
        </div>
        <div className="panel-actions">
          <button
            className="secondary-button"
            type="button"
            disabled={isRefreshing}
            onClick={onRefresh}
          >
            {isRefreshing ? "Checking..." : "Refresh Health"}
          </button>
          <button className="secondary-button" type="button" onClick={onClose}>
            Close
          </button>
        </div>
      </div>

      <div className="health-details-grid">
        <div>
          <p className="label">Backend API</p>
          <strong>{healthLabel}</strong>
          <span className={`health-inline health-${healthState}`}>{healthState}</span>
        </div>
        <div>
          <p className="label">API Status</p>
          <strong>{health?.status ?? "Not available"}</strong>
          <span className="helper-text">Endpoint: /api/health</span>
        </div>
        <div>
          <p className="label">Database</p>
          <strong>{formatHealthStatus(String(health?.database?.status ?? "Not checked"))}</strong>
          <span className="helper-text">Connectivity, session, lock, and tablespace checks.</span>
        </div>
        <div>
          <p className="label">Service</p>
          <strong>{health?.service ?? "AMS Applications & Volumetrics Analytics"}</strong>
          <span className="helper-text">Version: {health?.version ?? "Not available"}</span>
        </div>
        <div>
          <p className="label">Environment</p>
          <strong>{health?.environment ?? "Not available"}</strong>
          <span className="helper-text">Frontend app: Loaded</span>
        </div>
        <div>
          <p className="label">Last Checked</p>
          <strong>{formatDisplayDateTime(health?.checked_at)}</strong>
        </div>
      </div>
      {health?.storage_root ? (
        <p className="muted-text summary-block mono-text">Storage root: {health.storage_root}</p>
      ) : null}
      {checks.length > 0 ? (
        <div className="health-check-list" aria-label="Health check results">
          {checks.map((check) => (
            <article
              className={`health-check-card health-${healthClassForStatus(check.status)}`}
              key={check.name}
            >
              <div>
                <p className="label">{check.name.replace(/_/g, " ")}</p>
                <strong>{formatHealthStatus(check.status)}</strong>
              </div>
              <p>{check.message}</p>
              {check.duration_ms !== null && check.duration_ms !== undefined ? (
                <span className="helper-text">{check.duration_ms} ms</span>
              ) : null}
            </article>
          ))}
        </div>
      ) : (
        <p className="muted-text summary-block">Click Refresh Health to run diagnostics.</p>
      )}
      {healthError ? <p className="error-text">{healthError}</p> : null}
    </section>
  );
}

function App() {
  const [activeView, setActiveView] = useState<AppView>("dashboard");
  const [healthState, setHealthState] = useState<HealthState>("unchecked");
  const [healthLabel, setHealthLabel] = useState("Not checked");
  const [health, setHealth] = useState<BackendHealth | null>(null);
  const [healthError, setHealthError] = useState<string | null>(null);
  const [isHealthOpen, setIsHealthOpen] = useState(false);
  const [isRefreshingHealth, setIsRefreshingHealth] = useState(false);

  const refreshHealth = useCallback(async () => {
    setIsRefreshingHealth(true);
    setHealthState("checking");
    setHealthLabel("Checking");
    setHealthError(null);
    try {
      const nextHealth = await getBackendHealth();
      const status = nextHealth.status.toLowerCase();
      setHealth(nextHealth);
      if (status === "ok") {
        setHealthState("healthy");
        setHealthLabel("Healthy");
      } else if (status === "error") {
        setHealthState("offline");
        setHealthLabel("Offline");
      } else {
        setHealthState("degraded");
        setHealthLabel("Degraded");
      }
    } catch (requestError) {
      setHealth(null);
      setHealthState("offline");
      setHealthLabel("Offline");
      setHealthError(
        requestError instanceof Error ? requestError.message : "Unable to reach backend health"
      );
    } finally {
      setIsRefreshingHealth(false);
    }
  }, []);

  return (
    <main className="app-shell">
      <section className={`workspace-panel workspace-${activeView}`} aria-labelledby="page-title">
        <div className="page-heading">
          <div>
            <h1 id="page-title">AMS Applications &amp; Volumetrics Analytics</h1>
            <p className="page-subtitle">Application Support &amp; Maintenance Analytics Cockpit</p>
          </div>
          <div className="shell-actions">
            <HealthIndicator
              healthLabel={healthLabel}
              healthState={healthState}
              onOpen={() => {
                setIsHealthOpen(true);
                if (healthState === "unchecked") {
                  void refreshHealth();
                }
              }}
            />
            <nav className="view-tabs" aria-label="Primary views">
              <button
                className={activeView === "dashboard" ? "tab-button active" : "tab-button"}
                type="button"
                onClick={() => setActiveView("dashboard")}
              >
                Dashboard
              </button>
              <button
                className={activeView === "uploads" ? "tab-button active" : "tab-button"}
                type="button"
                onClick={() => setActiveView("uploads")}
              >
                Upload Center
              </button>
              <button
                className={activeView === "genai" ? "tab-button active" : "tab-button"}
                type="button"
                onClick={() => setActiveView("genai")}
              >
                GenAI Workbench
              </button>
              <button
                className={activeView === "maintenance" ? "tab-button active" : "tab-button"}
                type="button"
                onClick={() => setActiveView("maintenance")}
              >
                Maintenance
              </button>
            </nav>
          </div>
        </div>

        {isHealthOpen ? (
          <HealthDetails
            health={health}
            healthError={healthError}
            healthLabel={healthLabel}
            healthState={healthState}
            isRefreshing={isRefreshingHealth}
            onClose={() => setIsHealthOpen(false)}
            onRefresh={() => void refreshHealth()}
          />
        ) : null}

        <div className="app-view" hidden={activeView !== "dashboard"}>
          <Dashboard />
        </div>
        <div className="app-view" hidden={activeView !== "uploads"}>
          <UploadCenter />
        </div>
        <div className="app-view" hidden={activeView !== "genai"}>
          <GenAIWorkbench />
        </div>
        <div className="app-view" hidden={activeView !== "maintenance"}>
          <Maintenance />
        </div>
      </section>
    </main>
  );
}

export default App;
