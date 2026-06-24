import { useCallback, useEffect, useState } from "react";

import Dashboard from "./Dashboard";
import Maintenance from "./Maintenance";
import UploadCenter from "./UploadCenter";
import { getBackendHealth } from "./api/health";
import type { BackendHealth } from "./api/health";
import { formatDisplayDateTime } from "./utils/dateFormat";

type AppView = "dashboard" | "maintenance" | "uploads";
type HealthState = "checking" | "healthy" | "degraded" | "offline";

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
          <strong>{healthState === "offline" ? "Unknown" : "Healthy / Unknown"}</strong>
          <span className="helper-text">No separate database probe is exposed.</span>
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
      {healthError ? <p className="error-text">{healthError}</p> : null}
    </section>
  );
}

function App() {
  const [activeView, setActiveView] = useState<AppView>("dashboard");
  const [healthState, setHealthState] = useState<HealthState>("checking");
  const [healthLabel, setHealthLabel] = useState("Checking");
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
      const isHealthy = nextHealth.status.toLowerCase() === "ok";
      setHealth(nextHealth);
      setHealthState(isHealthy ? "healthy" : "degraded");
      setHealthLabel(isHealthy ? "Healthy" : "Degraded");
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

  useEffect(() => {
    void refreshHealth();
  }, [refreshHealth]);

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
              onOpen={() => setIsHealthOpen(true)}
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
        <div className="app-view" hidden={activeView !== "maintenance"}>
          <Maintenance />
        </div>
      </section>
    </main>
  );
}

export default App;
