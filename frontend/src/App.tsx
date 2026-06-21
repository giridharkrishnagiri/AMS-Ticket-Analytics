import { useState } from "react";

import ApplicationInventory from "./ApplicationInventory";
import Dashboard from "./Dashboard";
import HealthDashboard from "./HealthDashboard";
import Maintenance from "./Maintenance";
import MappingWizard from "./MappingWizard";
import SlaUpload from "./SlaUpload";
import UploadCenter from "./UploadCenter";

type AppView =
  | "application-inventory"
  | "dashboard"
  | "health"
  | "maintenance"
  | "mapping"
  | "sla"
  | "uploads";

function App() {
  const [activeView, setActiveView] = useState<AppView>("dashboard");

  return (
    <main className="app-shell">
      <section className="workspace-panel" aria-labelledby="page-title">
        <div className="page-heading">
          <div>
            <p className="eyebrow">AMS Consulting</p>
            <h1 id="page-title">AMS Ticket Intelligence</h1>
          </div>
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
              className={activeView === "mapping" ? "tab-button active" : "tab-button"}
              type="button"
              onClick={() => setActiveView("mapping")}
            >
              Mapping Wizard
            </button>
            <button
              className={activeView === "sla" ? "tab-button active" : "tab-button"}
              type="button"
              onClick={() => setActiveView("sla")}
            >
              SLA Upload
            </button>
            <button
              className={
                activeView === "application-inventory" ? "tab-button active" : "tab-button"
              }
              type="button"
              onClick={() => setActiveView("application-inventory")}
            >
              Application Inventory
            </button>
            <button
              className={activeView === "health" ? "tab-button active" : "tab-button"}
              type="button"
              onClick={() => setActiveView("health")}
            >
              Health
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

        {activeView === "dashboard" ? <Dashboard /> : null}
        {activeView === "uploads" ? <UploadCenter /> : null}
        {activeView === "mapping" ? <MappingWizard /> : null}
        {activeView === "sla" ? <SlaUpload /> : null}
        {activeView === "application-inventory" ? <ApplicationInventory /> : null}
        {activeView === "health" ? <HealthDashboard /> : null}
        {activeView === "maintenance" ? <Maintenance /> : null}
      </section>
    </main>
  );
}

export default App;
