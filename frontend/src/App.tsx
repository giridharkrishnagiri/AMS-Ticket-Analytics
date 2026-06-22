import { useEffect, useState } from "react";

import Dashboard from "./Dashboard";
import Maintenance from "./Maintenance";
import UploadCenter from "./UploadCenter";
import { getBackendHealth } from "./api/health";

type AppView = "dashboard" | "maintenance" | "uploads";
type HealthState = "checking" | "healthy" | "offline";

function HealthIndicator() {
  const [healthState, setHealthState] = useState<HealthState>("checking");
  const [healthLabel, setHealthLabel] = useState("Checking");

  useEffect(() => {
    let isMounted = true;
    const controller = new AbortController();

    getBackendHealth(controller.signal)
      .then((health) => {
        if (!isMounted) {
          return;
        }
        const isHealthy = health.status.toLowerCase() === "ok";
        setHealthState(isHealthy ? "healthy" : "offline");
        setHealthLabel(isHealthy ? "Healthy" : "Degraded");
      })
      .catch(() => {
        if (isMounted) {
          setHealthState("offline");
          setHealthLabel("Offline");
        }
      });

    return () => {
      isMounted = false;
      controller.abort();
    };
  }, []);

  return (
    <div className={`health-pill health-${healthState}`} aria-label={`System health ${healthLabel}`}>
      <span aria-hidden="true" />
      <strong>System Health:</strong> {healthLabel}
    </div>
  );
}

function App() {
  const [activeView, setActiveView] = useState<AppView>("dashboard");

  return (
    <main className="app-shell">
      <section className={`workspace-panel workspace-${activeView}`} aria-labelledby="page-title">
        <div className="page-heading">
          <div>
            <p className="eyebrow">AMS Consulting</p>
            <h1 id="page-title">AMS Ticket Intelligence</h1>
            <p className="page-subtitle">Application Support &amp; Maintenance Analytics Cockpit</p>
          </div>
          <div className="shell-actions">
            <HealthIndicator />
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

        {activeView === "dashboard" ? <Dashboard /> : null}
        {activeView === "uploads" ? <UploadCenter /> : null}
        {activeView === "maintenance" ? <Maintenance /> : null}
      </section>
    </main>
  );
}

export default App;
