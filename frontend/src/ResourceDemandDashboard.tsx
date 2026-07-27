import { useCallback, useEffect, useMemo, useState } from "react";

import {
  getDashboardResourceDemand,
  updateDashboardResourceDemandUnitEfforts,
} from "./api/dashboard";
import type {
  ResourceDemandResponse,
  ResourceDemandUnitEffortRow,
} from "./api/dashboard";

type LoadStatus = "idle" | "loading" | "success" | "error";
type SaveStatus = "idle" | "saving" | "success" | "error";
type UnitEffortField = "l1_5_hours" | "l2_hours" | "l3_hours";

const defaultFromMonth = "2026-03";
const defaultToMonth = "2026-05";

function formatMonthLabel(monthKey: string): string {
  const [yearText, monthText] = monthKey.split("-");
  const year = Number(yearText);
  const month = Number(monthText);
  if (!Number.isFinite(year) || !Number.isFinite(month)) {
    return monthKey;
  }
  return new Intl.DateTimeFormat(undefined, { month: "short", year: "numeric" }).format(
    new Date(Date.UTC(year, month - 1, 1))
  );
}

function formatVolume(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "";
  }
  return value.toLocaleString(undefined, { maximumFractionDigits: 0 });
}

function ticketTypeLabel(ticketType: string): string {
  if (ticketType === "INCIDENT") {
    return "Incident";
  }
  if (ticketType === "SERVICE_CATALOG_TASK") {
    return "SC Tasks";
  }
  if (ticketType === "PROBLEM") {
    return "Problem";
  }
  if (ticketType === "CHANGE") {
    return "Change";
  }
  return ticketType;
}

function parseNullableNumber(value: string): number | null {
  const cleaned = value.trim();
  if (!cleaned) {
    return null;
  }
  const parsed = Number(cleaned);
  return Number.isFinite(parsed) ? parsed : null;
}

function effortInputValue(value: number | null): string {
  return value === null || value === undefined ? "" : String(value);
}

export default function ResourceDemandDashboard({
  isActive,
  projectId,
}: {
  isActive: boolean;
  projectId: string;
}) {
  const [status, setStatus] = useState<LoadStatus>("idle");
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<ResourceDemandResponse | null>(null);
  const [activeTechnology, setActiveTechnology] = useState("overall");
  const [unitEfforts, setUnitEfforts] = useState<ResourceDemandUnitEffortRow[]>([]);
  const [saveStatus, setSaveStatus] = useState<SaveStatus>("idle");
  const [saveMessage, setSaveMessage] = useState<string | null>(null);

  const loadResourceDemand = useCallback(async () => {
    const cleanedProjectId = projectId.trim();
    if (!cleanedProjectId) {
      setStatus("idle");
      setData(null);
      setUnitEfforts([]);
      return;
    }

    setStatus("loading");
    setError(null);
    try {
      const response = await getDashboardResourceDemand({
        projectId: cleanedProjectId,
        fromMonth: defaultFromMonth,
        toMonth: defaultToMonth,
      });
      setData(response);
      setUnitEfforts(response.unit_efforts);
      setActiveTechnology((current) =>
        response.demand_views.some((view) => view.key === current)
          ? current
          : response.demand_views[0]?.key ?? "overall"
      );
      setStatus("success");
    } catch (nextError) {
      setStatus("error");
      setError(
        nextError instanceof Error ? nextError.message : "Unable to load Resource Demand data."
      );
    }
  }, [projectId]);

  useEffect(() => {
    if (isActive) {
      void loadResourceDemand();
    }
  }, [isActive, loadResourceDemand]);

  const activeDemandView = useMemo(
    () =>
      data?.demand_views.find((view) => view.key === activeTechnology) ??
      data?.demand_views[0] ??
      null,
    [activeTechnology, data]
  );

  function updateUnitEffort(
    rowIndex: number,
    field: UnitEffortField,
    value: string
  ) {
    setUnitEfforts((currentRows) =>
      currentRows.map((row, index) =>
        index === rowIndex ? { ...row, [field]: parseNullableNumber(value) } : row
      )
    );
    setSaveStatus("idle");
    setSaveMessage(null);
  }

  async function saveUnitEfforts() {
    const cleanedProjectId = projectId.trim();
    if (!cleanedProjectId) {
      return;
    }
    setSaveStatus("saving");
    setSaveMessage(null);
    try {
      const response = await updateDashboardResourceDemandUnitEfforts({
        projectId: cleanedProjectId,
        rows: unitEfforts,
      });
      setData(response);
      setUnitEfforts(response.unit_efforts);
      setSaveStatus("success");
      setSaveMessage("Unit effort master saved.");
    } catch (nextError) {
      setSaveStatus("error");
      setSaveMessage(
        nextError instanceof Error ? nextError.message : "Unable to save unit effort master."
      );
    }
  }

  if (!projectId.trim()) {
    return (
      <section className="panel resource-demand-layout" aria-labelledby="resource-demand-heading">
        <div className="panel-heading">
          <div>
            <p className="label">Resource Demand</p>
            <h2 id="resource-demand-heading">Resource Demand</h2>
          </div>
        </div>
        <p className="muted-text">Select a customer/project to view resource demand inputs.</p>
      </section>
    );
  }

  return (
    <section className="resource-demand-layout" aria-labelledby="resource-demand-heading">
      <section className="panel">
        <div className="panel-heading">
          <div>
            <p className="label">Resource Demand</p>
            <h2 id="resource-demand-heading">Demand Inputs</h2>
            <p className="muted-text">
              Average monthly closed/resolved volume for {formatMonthLabel(defaultFromMonth)} to{" "}
              {formatMonthLabel(defaultToMonth)}.
            </p>
          </div>
          <button
            className="secondary-button"
            disabled={status === "loading"}
            type="button"
            onClick={() => void loadResourceDemand()}
          >
            {status === "loading" ? "Refreshing..." : "Refresh Resource Demand"}
          </button>
        </div>

        {status === "error" ? <p className="error-text">{error}</p> : null}
        {status === "loading" ? <p className="muted-text">Loading resource demand data...</p> : null}

        {data && activeDemandView ? (
          <>
            <div
              className="resource-demand-tech-tabs"
              role="tablist"
              aria-label="Resource demand technology views"
            >
              {data.demand_views.map((view) => (
                <button
                  key={view.key}
                  className={activeTechnology === view.key ? "active" : ""}
                  type="button"
                  onClick={() => setActiveTechnology(view.key)}
                >
                  {view.label}
                </button>
              ))}
            </div>

            <div className="table-wrap resource-demand-table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Demand category</th>
                    <th>Avg monthly volume</th>
                    <th>L1.5</th>
                    <th>L2</th>
                    <th>L3</th>
                    <th>Notes</th>
                  </tr>
                </thead>
                <tbody>
                  {activeDemandView.rows.map((row) => (
                    <tr key={row.key}>
                      <td>
                        <strong>{row.label}</strong>
                      </td>
                      <td>{formatVolume(row.average_monthly_volume)}</td>
                      <td>{formatVolume(row.service_level_split.l1_5)}</td>
                      <td>{formatVolume(row.service_level_split.l2)}</td>
                      <td>{formatVolume(row.service_level_split.l3)}</td>
                      <td>{row.notes ?? ""}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {data.data_notes.length > 0 ? (
              <ul className="resource-demand-notes">
                {data.data_notes.map((note) => (
                  <li key={note}>{note}</li>
                ))}
              </ul>
            ) : null}
          </>
        ) : null}
      </section>

      <section className="panel">
        <div className="panel-heading">
          <div>
            <p className="label">Resource Demand</p>
            <h2>Effort Demand Summary</h2>
            <p className="muted-text">
              Computation will be enabled after service-level, incident-source, and technology split
              rules are finalized.
            </p>
          </div>
        </div>
        <div className="table-wrap resource-demand-table-wrap">
          <table>
            <thead>
              <tr>
                <th>Demand category</th>
                <th>L1.5 hours</th>
                <th>L2 hours</th>
                <th>L3 hours</th>
                <th>Total hours</th>
                <th>Person days</th>
              </tr>
            </thead>
            <tbody>
              {[
                "Incidents - User-generated",
                "Incidents - System-generated",
                "SC Tasks",
                "Problems",
                "Changes",
                "Non-ticketed activities",
                "Management efforts",
                "Contingency",
                "Overall resource demand",
              ].map((label) => (
                <tr key={label}>
                  <td>
                    <strong>{label}</strong>
                  </td>
                  <td />
                  <td />
                  <td />
                  <td />
                  <td />
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="panel">
        <div className="panel-heading">
          <div>
            <p className="label">Resource Demand Master</p>
            <h2>Unit Effort Master</h2>
            <p className="muted-text">
              Maintain hours per ticket by ticket type, incident source, technology, and service
              level.
            </p>
          </div>
          <button
            className="primary-button"
            disabled={saveStatus === "saving" || unitEfforts.length === 0}
            type="button"
            onClick={() => void saveUnitEfforts()}
          >
            {saveStatus === "saving" ? "Saving..." : "Save Unit Efforts"}
          </button>
        </div>

        {saveMessage ? (
          <p className={saveStatus === "error" ? "error-text" : "success-text"}>{saveMessage}</p>
        ) : null}

        <div className="table-wrap resource-demand-table-wrap">
          <table>
            <thead>
              <tr>
                <th>Ticket type</th>
                <th>Incident source</th>
                <th>Technology</th>
                <th>L1.5 hours</th>
                <th>L2 hours</th>
                <th>L3 hours</th>
              </tr>
            </thead>
            <tbody>
              {unitEfforts.map((row, rowIndex) => (
                <tr key={row.id ?? `${row.ticket_type}-${row.incident_source}-${row.technology}`}>
                  <td>{ticketTypeLabel(row.ticket_type)}</td>
                  <td>{row.incident_source}</td>
                  <td>{row.technology}</td>
                  {(["l1_5_hours", "l2_hours", "l3_hours"] as UnitEffortField[]).map((field) => (
                    <td key={field}>
                      <input
                        aria-label={`${row.ticket_type} ${row.incident_source} ${row.technology} ${field}`}
                        min="0"
                        step="0.01"
                        type="number"
                        value={effortInputValue(row[field])}
                        onChange={(event) =>
                          updateUnitEffort(rowIndex, field, event.target.value)
                        }
                      />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </section>
  );
}
