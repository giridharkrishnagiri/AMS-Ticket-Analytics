import { useCallback, useEffect, useMemo, useState } from "react";

import {
  getDashboardResourceDemand,
  updateDashboardResourceDemandServiceLevelSplits,
  updateDashboardResourceDemandUnitEfforts,
} from "./api/dashboard";
import type {
  ResourceDemandResponse,
  ResourceDemandServiceLevelSplitRow,
  ResourceDemandTechnologyView,
  ResourceDemandUnitEffortRow,
} from "./api/dashboard";

type LoadStatus = "idle" | "loading" | "success" | "error";
type SaveStatus = "idle" | "saving" | "success" | "error";
type UnitEffortField = "l1_5_hours" | "l2_hours" | "l3_hours";
type SplitPercentField = "l1_5_pct" | "l2_pct" | "l3_pct";
type DemandSplitField = "l1_5" | "l2" | "l3";

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

function formatHours(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value) || value === 0) {
    return "";
  }
  return value.toLocaleString(undefined, { maximumFractionDigits: 2 });
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

function numberInputValue(value: number | null | undefined): string {
  return value === null || value === undefined ? "" : String(value);
}

function technologyForDemandView(view: ResourceDemandTechnologyView | null): string {
  return view?.label === "Overall" ? "Generic" : view?.label ?? "Generic";
}

type EffortSummaryRow = {
  label: string;
  l1_5: number;
  l2: number;
  l3: number;
  total: number;
  personDays: number;
};

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
  const [demandViews, setDemandViews] = useState<ResourceDemandTechnologyView[]>([]);
  const [activeTechnology, setActiveTechnology] = useState("overall");
  const [activeUnitTechnology, setActiveUnitTechnology] = useState("Generic");
  const [activeSplitTechnology, setActiveSplitTechnology] = useState("Generic");
  const [unitEfforts, setUnitEfforts] = useState<ResourceDemandUnitEffortRow[]>([]);
  const [serviceLevelSplits, setServiceLevelSplits] = useState<
    ResourceDemandServiceLevelSplitRow[]
  >([]);
  const [unitSaveStatus, setUnitSaveStatus] = useState<SaveStatus>("idle");
  const [unitSaveMessage, setUnitSaveMessage] = useState<string | null>(null);
  const [splitSaveStatus, setSplitSaveStatus] = useState<SaveStatus>("idle");
  const [splitSaveMessage, setSplitSaveMessage] = useState<string | null>(null);

  const loadResourceDemand = useCallback(async () => {
    const cleanedProjectId = projectId.trim();
    if (!cleanedProjectId) {
      setStatus("idle");
      setData(null);
      setDemandViews([]);
      setUnitEfforts([]);
      setServiceLevelSplits([]);
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
      setDemandViews(response.demand_views);
      setUnitEfforts(response.unit_efforts);
      setServiceLevelSplits(response.service_level_splits);
      setActiveTechnology((current) =>
        response.demand_views.some((view) => view.key === current)
          ? current
          : response.demand_views[0]?.key ?? "overall"
      );
      const masterTechnologies = response.technologies.filter((technology) => technology !== "Overall");
      setActiveUnitTechnology((current) =>
        masterTechnologies.includes(current) ? current : masterTechnologies[0] ?? "Generic"
      );
      setActiveSplitTechnology((current) =>
        masterTechnologies.includes(current) ? current : masterTechnologies[0] ?? "Generic"
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
      demandViews.find((view) => view.key === activeTechnology) ??
      demandViews[0] ??
      null,
    [activeTechnology, demandViews]
  );

  const masterTechnologies = useMemo(() => {
    const configured = data?.technologies.filter((technology) => technology !== "Overall") ?? [];
    const fromRows = [
      ...unitEfforts.map((row) => row.technology),
      ...serviceLevelSplits.map((row) => row.technology),
    ].filter(Boolean);
    return [...new Set(configured.length > 0 ? configured : fromRows)];
  }, [data, serviceLevelSplits, unitEfforts]);

  const filteredUnitEfforts = useMemo(
    () =>
      unitEfforts
        .map((row, rowIndex) => ({ row, rowIndex }))
        .filter((item) => item.row.technology === activeUnitTechnology),
    [activeUnitTechnology, unitEfforts]
  );

  const filteredServiceLevelSplits = useMemo(
    () =>
      serviceLevelSplits
        .map((row, rowIndex) => ({ row, rowIndex }))
        .filter((item) => item.row.technology === activeSplitTechnology),
    [activeSplitTechnology, serviceLevelSplits]
  );

  const effortSummaryRows = useMemo<EffortSummaryRow[]>(() => {
    if (!activeDemandView) {
      return [];
    }
    const effortTechnology = technologyForDemandView(activeDemandView);
    return activeDemandView.rows
      .filter((row) => row.key !== "incident_total")
      .map((row) => {
        const split = row.service_level_split;
        if (row.ticket_type === "NON_TICKETED") {
          const l1_5 = split.l1_5 ?? 0;
          const l2 = split.l2 ?? 0;
          const l3 = split.l3 ?? 0;
          const total = l1_5 + l2 + l3;
          return {
            label: row.label,
            l1_5,
            l2,
            l3,
            total,
            personDays: total / 8,
          };
        }
        const unitEffort = unitEfforts.find(
          (unit) =>
            unit.ticket_type === row.ticket_type &&
            unit.incident_source === (row.incident_source ?? "Any") &&
            unit.technology === effortTechnology
        );
        const l1_5 = (split.l1_5 ?? 0) * (unitEffort?.l1_5_hours ?? 0);
        const l2 = (split.l2 ?? 0) * (unitEffort?.l2_hours ?? 0);
        const l3 = (split.l3 ?? 0) * (unitEffort?.l3_hours ?? 0);
        const total = l1_5 + l2 + l3;
        return {
          label: row.label,
          l1_5,
          l2,
          l3,
          total,
          personDays: total / 8,
        };
      });
  }, [activeDemandView, unitEfforts]);

  const overallEffortSummary = useMemo(
    () =>
      effortSummaryRows.reduce<EffortSummaryRow>(
        (accumulator, row) => ({
          label: "Overall resource demand",
          l1_5: accumulator.l1_5 + row.l1_5,
          l2: accumulator.l2 + row.l2,
          l3: accumulator.l3 + row.l3,
          total: accumulator.total + row.total,
          personDays: accumulator.personDays + row.personDays,
        }),
        { label: "Overall resource demand", l1_5: 0, l2: 0, l3: 0, total: 0, personDays: 0 }
      ),
    [effortSummaryRows]
  );

  function updateUnitEffort(rowIndex: number, field: UnitEffortField, value: string) {
    setUnitEfforts((currentRows) =>
      currentRows.map((row, index) =>
        index === rowIndex ? { ...row, [field]: parseNullableNumber(value) } : row
      )
    );
    setUnitSaveStatus("idle");
    setUnitSaveMessage(null);
  }

  function updateServiceLevelSplit(rowIndex: number, field: SplitPercentField, value: string) {
    setServiceLevelSplits((currentRows) =>
      currentRows.map((row, index) =>
        index === rowIndex ? { ...row, [field]: parseNullableNumber(value) } : row
      )
    );
    setSplitSaveStatus("idle");
    setSplitSaveMessage(null);
  }

  function updateDemandSplit(rowKey: string, field: DemandSplitField, value: string) {
    setDemandViews((currentViews) =>
      currentViews.map((view) =>
        view.key !== activeTechnology
          ? view
          : {
              ...view,
              rows: view.rows.map((row) =>
                row.key !== rowKey
                  ? row
                  : {
                      ...row,
                      service_level_split: {
                        ...row.service_level_split,
                        [field]: parseNullableNumber(value),
                      },
                    }
              ),
            }
      )
    );
  }

  async function saveUnitEfforts() {
    const cleanedProjectId = projectId.trim();
    if (!cleanedProjectId) {
      return;
    }
    setUnitSaveStatus("saving");
    setUnitSaveMessage(null);
    try {
      const response = await updateDashboardResourceDemandUnitEfforts({
        projectId: cleanedProjectId,
        rows: unitEfforts,
      });
      setData(response);
      setDemandViews(response.demand_views);
      setUnitEfforts(response.unit_efforts);
      setServiceLevelSplits(response.service_level_splits);
      setUnitSaveStatus("success");
      setUnitSaveMessage("Unit effort master saved.");
    } catch (nextError) {
      setUnitSaveStatus("error");
      setUnitSaveMessage(
        nextError instanceof Error ? nextError.message : "Unable to save unit effort master."
      );
    }
  }

  async function saveServiceLevelSplits() {
    const cleanedProjectId = projectId.trim();
    if (!cleanedProjectId) {
      return;
    }
    setSplitSaveStatus("saving");
    setSplitSaveMessage(null);
    try {
      const response = await updateDashboardResourceDemandServiceLevelSplits({
        projectId: cleanedProjectId,
        rows: serviceLevelSplits,
      });
      setData(response);
      setDemandViews(response.demand_views);
      setUnitEfforts(response.unit_efforts);
      setServiceLevelSplits(response.service_level_splits);
      setSplitSaveStatus("success");
      setSplitSaveMessage("Service level split master saved and demand inputs recalculated.");
    } catch (nextError) {
      setSplitSaveStatus("error");
      setSplitSaveMessage(
        nextError instanceof Error
          ? nextError.message
          : "Unable to save service level split master."
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
              {demandViews.map((view) => (
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
                      {(["l1_5", "l2", "l3"] as DemandSplitField[]).map((field) => (
                        <td key={field}>
                          <input
                            aria-label={`${row.label} ${field} volume`}
                            className="resource-demand-number-input"
                            min="0"
                            step={row.ticket_type === "NON_TICKETED" ? "0.25" : "1"}
                            type="number"
                            value={numberInputValue(row.service_level_split[field])}
                            onChange={(event) =>
                              updateDemandSplit(row.key, field, event.target.value)
                            }
                          />
                        </td>
                      ))}
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
              Calculated from editable demand inputs and saved unit effort assumptions.
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
                ...effortSummaryRows,
                { label: "Management efforts", l1_5: 0, l2: 0, l3: 0, total: 0, personDays: 0 },
                { label: "Contingency", l1_5: 0, l2: 0, l3: 0, total: 0, personDays: 0 },
                overallEffortSummary,
              ].map((row) => (
                <tr key={row.label}>
                  <td>
                    <strong>{row.label}</strong>
                  </td>
                  <td>{formatHours(row.l1_5)}</td>
                  <td>{formatHours(row.l2)}</td>
                  <td>{formatHours(row.l3)}</td>
                  <td>{formatHours(row.total)}</td>
                  <td>{formatHours(row.personDays)}</td>
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
            disabled={unitSaveStatus === "saving" || unitEfforts.length === 0}
            type="button"
            onClick={() => void saveUnitEfforts()}
          >
            {unitSaveStatus === "saving" ? "Saving..." : "Save Unit Efforts"}
          </button>
        </div>

        <div className="resource-demand-tech-tabs" role="tablist" aria-label="Unit effort technology">
          {masterTechnologies.map((technology) => (
            <button
              key={technology}
              className={activeUnitTechnology === technology ? "active" : ""}
              type="button"
              onClick={() => setActiveUnitTechnology(technology)}
            >
              {technology}
            </button>
          ))}
        </div>

        {unitSaveMessage ? (
          <p className={unitSaveStatus === "error" ? "error-text" : "success-text"}>
            {unitSaveMessage}
          </p>
        ) : null}

        <div className="table-wrap resource-demand-table-wrap">
          <table className="resource-demand-master-table">
            <thead>
              <tr>
                <th>Ticket type</th>
                <th>Incident source</th>
                <th>L1.5 hours</th>
                <th>L2 hours</th>
                <th>L3 hours</th>
              </tr>
            </thead>
            <tbody>
              {filteredUnitEfforts.map(({ row, rowIndex }) => (
                <tr key={row.id ?? `${row.ticket_type}-${row.incident_source}-${row.technology}`}>
                  <td>{ticketTypeLabel(row.ticket_type)}</td>
                  <td>{row.incident_source}</td>
                  {(["l1_5_hours", "l2_hours", "l3_hours"] as UnitEffortField[]).map((field) => (
                    <td key={field}>
                      <input
                        aria-label={`${row.ticket_type} ${row.incident_source} ${row.technology} ${field}`}
                        className="resource-demand-number-input"
                        min="0"
                        step="0.01"
                        type="number"
                        value={numberInputValue(row[field])}
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

      <section className="panel">
        <div className="panel-heading">
          <div>
            <p className="label">Resource Demand Master</p>
            <h2>Service Level Split Master</h2>
            <p className="muted-text">
              Maintain percentage split by service level. Saved percentages recalculate Demand Input
              split volumes.
            </p>
          </div>
          <button
            className="primary-button"
            disabled={splitSaveStatus === "saving" || serviceLevelSplits.length === 0}
            type="button"
            onClick={() => void saveServiceLevelSplits()}
          >
            {splitSaveStatus === "saving" ? "Saving..." : "Save Service Splits"}
          </button>
        </div>

        <div
          className="resource-demand-tech-tabs"
          role="tablist"
          aria-label="Service level split technology"
        >
          {masterTechnologies.map((technology) => (
            <button
              key={technology}
              className={activeSplitTechnology === technology ? "active" : ""}
              type="button"
              onClick={() => setActiveSplitTechnology(technology)}
            >
              {technology}
            </button>
          ))}
        </div>

        {splitSaveMessage ? (
          <p className={splitSaveStatus === "error" ? "error-text" : "success-text"}>
            {splitSaveMessage}
          </p>
        ) : null}

        <div className="table-wrap resource-demand-table-wrap">
          <table className="resource-demand-master-table">
            <thead>
              <tr>
                <th>Ticket type</th>
                <th>Incident source</th>
                <th>L1.5 %</th>
                <th>L2 %</th>
                <th>L3 %</th>
              </tr>
            </thead>
            <tbody>
              {filteredServiceLevelSplits.map(({ row, rowIndex }) => (
                <tr key={row.id ?? `${row.ticket_type}-${row.incident_source}-${row.technology}`}>
                  <td>{ticketTypeLabel(row.ticket_type)}</td>
                  <td>{row.incident_source}</td>
                  {(["l1_5_pct", "l2_pct", "l3_pct"] as SplitPercentField[]).map((field) => (
                    <td key={field}>
                      <input
                        aria-label={`${row.ticket_type} ${row.incident_source} ${row.technology} ${field}`}
                        className="resource-demand-number-input"
                        max="100"
                        min="0"
                        step="0.01"
                        type="number"
                        value={numberInputValue(row[field])}
                        onChange={(event) =>
                          updateServiceLevelSplit(rowIndex, field, event.target.value)
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
