import { useMemo, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { createTimesheet, generateTimesheetSummary, submitTimesheetWeek } from "./api";
import type {
  Deliverable,
  Subtask,
  Task,
  TimesheetEntry,
  TimesheetSummary,
  Workstream,
} from "./types";

function todayIsoDate() {
  return new Date().toISOString().slice(0, 10);
}

function formatDateTime(value: string | null) {
  if (!value) {
    return "-";
  }

  return value.replace("T", " ").slice(0, 19);
}

function truncate(value: string, maxLength = 220) {
  if (value.length <= maxLength) {
    return value;
  }

  return `${value.slice(0, maxLength - 3)}...`;
}

function StatusBadge({ status }: { status: string }) {
  return <span className="status-badge">{status}</span>;
}

function yesNo(value: boolean) {
  return value ? "Yes" : "No";
}

export function Mvp10TimesheetPanel({
  workstreams,
  deliverables,
  tasks,
  subtasks,
  timesheets,
  timesheetSummaries,
}: {
  workstreams: Workstream[];
  deliverables: Deliverable[];
  tasks: Task[];
  subtasks: Subtask[];
  timesheets: TimesheetEntry[];
  timesheetSummaries: TimesheetSummary[];
}) {
  const queryClient = useQueryClient();

  const [entryDate, setEntryDate] = useState(todayIsoDate());
  const [personName, setPersonName] = useState("Giridhar Krishnagiri");
  const [workstreamId, setWorkstreamId] = useState("");
  const [deliverableId, setDeliverableId] = useState("");
  const [taskId, setTaskId] = useState("");
  const [subtaskId, setSubtaskId] = useState("");
  const [activityType, setActivityType] = useState("Delivery");
  const [accomplishments, setAccomplishments] = useState("");
  const [blockers, setBlockers] = useState("");
  const [nextSteps, setNextSteps] = useState("");
  const [effortHours, setEffortHours] = useState("1");
  const [status, setStatus] = useState("Draft");

  const [weekStartDate, setWeekStartDate] = useState(todayIsoDate());
  const [weekEndDate, setWeekEndDate] = useState(todayIsoDate());
  const [summaryStartDate, setSummaryStartDate] = useState(todayIsoDate());
  const [summaryEndDate, setSummaryEndDate] = useState(todayIsoDate());
  const [summaryType, setSummaryType] = useState("Custom Date Range");
  const [message, setMessage] = useState("");

  const filteredDeliverables = useMemo(() => {
    if (!workstreamId) {
      return deliverables;
    }

    return deliverables.filter((item) => item.workstream_id === workstreamId);
  }, [deliverables, workstreamId]);

  const filteredTasks = useMemo(() => {
    if (!deliverableId) {
      return tasks;
    }

    return tasks.filter((item) => item.deliverable_id === deliverableId);
  }, [deliverableId, tasks]);

  const filteredSubtasks = useMemo(() => {
    if (!taskId) {
      return subtasks;
    }

    return subtasks.filter((item) => item.task_id === taskId);
  }, [subtasks, taskId]);

  const totalHours = timesheets.reduce((sum, item) => sum + item.effort_hours, 0);
  const submittedCount = timesheets.filter((item) => item.submitted).length;
  const draftCount = timesheets.length - submittedCount;

  const createMutation = useMutation({
    mutationFn: () =>
      createTimesheet({
        entry_date: entryDate,
        person_name: personName,
        workstream_id: workstreamId || null,
        deliverable_id: deliverableId || null,
        task_id: taskId || null,
        subtask_id: subtaskId || null,
        activity_type: activityType,
        accomplishments,
        blockers,
        next_steps: nextSteps,
        effort_hours: Number(effortHours),
        status,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["timesheets"] });
      setAccomplishments("");
      setBlockers("");
      setNextSteps("");
      setEffortHours("1");
      setStatus("Draft");
      setMessage("Timesheet entry saved successfully.");
    },
    onError: (error) => {
      setMessage(error instanceof Error ? error.message : "Failed to save timesheet entry.");
    },
  });

  const submitWeekMutation = useMutation({
    mutationFn: () =>
      submitTimesheetWeek({
        start_date: weekStartDate,
        end_date: weekEndDate,
        person_name: personName,
        submitted_by: personName,
      }),
    onSuccess: (response) => {
      queryClient.invalidateQueries({ queryKey: ["timesheets"] });
      setMessage(`Submitted ${response.submitted_count} timesheet entries for the selected week.`);
    },
    onError: (error) => {
      setMessage(error instanceof Error ? error.message : "Failed to submit week.");
    },
  });

  const generateSummaryMutation = useMutation({
    mutationFn: () =>
      generateTimesheetSummary({
        start_date: summaryStartDate,
        end_date: summaryEndDate,
        person_name: personName,
        summary_type: summaryType,
        created_by: personName,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["timesheet-summaries"] });
      setMessage("Timesheet summary generated and saved successfully.");
    },
    onError: (error) => {
      setMessage(error instanceof Error ? error.message : "Failed to generate timesheet summary.");
    },
  });

  function saveTimesheet() {
    if (!entryDate) {
      setMessage("Entry date is required.");
      return;
    }

    if (!accomplishments.trim()) {
      setMessage("Accomplishments are required.");
      return;
    }

    if (Number.isNaN(Number(effortHours)) || Number(effortHours) < 0) {
      setMessage("Effort hours must be a valid non-negative number.");
      return;
    }

    setMessage("");
    createMutation.mutate();
  }

  function clearEntryForm() {
    setEntryDate(todayIsoDate());
    setWorkstreamId("");
    setDeliverableId("");
    setTaskId("");
    setSubtaskId("");
    setActivityType("Delivery");
    setAccomplishments("");
    setBlockers("");
    setNextSteps("");
    setEffortHours("1");
    setStatus("Draft");
    setMessage("");
  }

  return (
    <section id="timesheets" className="content-section">
      <div className="section-header">
        <div>
          <h2>Daily Timesheets and Accomplishment Summaries</h2>
          <p>
            Capture daily accomplishments, link effort to work items, submit weekly time,
            and generate traced LLM accomplishment summaries.
          </p>
        </div>
      </div>

      <div className="report-summary-grid">
        <div className="report-card">
          <span>Total Timesheet Entries</span>
          <strong>{timesheets.length}</strong>
          <p>All captured entries</p>
        </div>
        <div className="report-card">
          <span>Total Effort Hours</span>
          <strong>{totalHours.toFixed(1)}</strong>
          <p>Across all entries</p>
        </div>
        <div className="report-card">
          <span>Submitted Entries</span>
          <strong>{submittedCount}</strong>
          <p>Included in weekly submission</p>
        </div>
        <div className="report-card">
          <span>Draft Entries</span>
          <strong>{draftCount}</strong>
          <p>Not submitted yet</p>
        </div>
        <div className="report-card">
          <span>Generated Summaries</span>
          <strong>{timesheetSummaries.length}</strong>
          <p>LLM summary outputs</p>
        </div>
      </div>

      <div className="timesheet-grid">
        <div className="timesheet-card">
          <h3>Add Daily Timesheet Entry</h3>
          <p>Capture what was done today and link it to the relevant ASM work item.</p>

          <div className="timesheet-form-grid">
            <label>
              Entry Date
              <input type="date" value={entryDate} onChange={(event) => setEntryDate(event.target.value)} />
            </label>

            <label>
              Person
              <input value={personName} onChange={(event) => setPersonName(event.target.value)} />
            </label>

            <label>
              Workstream
              <select
                value={workstreamId}
                onChange={(event) => {
                  setWorkstreamId(event.target.value);
                  setDeliverableId("");
                  setTaskId("");
                  setSubtaskId("");
                }}
              >
                <option value="">No workstream link</option>
                {workstreams.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.external_id ? `${item.external_id} - ` : ""}
                    {item.name}
                  </option>
                ))}
              </select>
            </label>

            <label>
              Deliverable
              <select
                value={deliverableId}
                onChange={(event) => {
                  setDeliverableId(event.target.value);
                  setTaskId("");
                  setSubtaskId("");
                }}
              >
                <option value="">No deliverable link</option>
                {filteredDeliverables.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.external_id ? `${item.external_id} - ` : ""}
                    {item.name}
                  </option>
                ))}
              </select>
            </label>

            <label>
              Task
              <select
                value={taskId}
                onChange={(event) => {
                  setTaskId(event.target.value);
                  setSubtaskId("");
                }}
              >
                <option value="">No task link</option>
                {filteredTasks.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.external_id ? `${item.external_id} - ` : ""}
                    {item.title}
                  </option>
                ))}
              </select>
            </label>

            <label>
              Sub-task
              <select value={subtaskId} onChange={(event) => setSubtaskId(event.target.value)}>
                <option value="">No sub-task link</option>
                {filteredSubtasks.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.external_id ? `${item.external_id} - ` : ""}
                    {item.title}
                  </option>
                ))}
              </select>
            </label>

            <label>
              Activity Type
              <select value={activityType} onChange={(event) => setActivityType(event.target.value)}>
                <option value="Delivery">Delivery</option>
                <option value="Analysis">Analysis</option>
                <option value="Stakeholder Discussion">Stakeholder Discussion</option>
                <option value="Data Gathering">Data Gathering</option>
                <option value="Documentation">Documentation</option>
                <option value="Review">Review</option>
                <option value="Planning">Planning</option>
                <option value="Other">Other</option>
              </select>
            </label>

            <label>
              Effort Hours
              <input value={effortHours} onChange={(event) => setEffortHours(event.target.value)} />
            </label>

            <label>
              Status
              <select value={status} onChange={(event) => setStatus(event.target.value)}>
                <option value="Draft">Draft</option>
                <option value="In Progress">In Progress</option>
                <option value="Submitted">Submitted</option>
              </select>
            </label>

            <label className="timesheet-full-width">
              Accomplishments
              <textarea
                value={accomplishments}
                onChange={(event) => setAccomplishments(event.target.value)}
                placeholder="Describe what you completed today."
              />
            </label>

            <label className="timesheet-full-width">
              Blockers
              <textarea
                value={blockers}
                onChange={(event) => setBlockers(event.target.value)}
                placeholder="Describe blockers, dependencies, or waiting items."
              />
            </label>

            <label className="timesheet-full-width">
              Next Steps
              <textarea
                value={nextSteps}
                onChange={(event) => setNextSteps(event.target.value)}
                placeholder="Describe planned next steps."
              />
            </label>
          </div>

          <div className="dictation-actions">
            <button className="primary-button" onClick={saveTimesheet} disabled={createMutation.isPending}>
              {createMutation.isPending ? "Saving..." : "Save Timesheet Entry"}
            </button>
            <button className="secondary-button" onClick={clearEntryForm}>
              Clear
            </button>
          </div>
        </div>

        <div className="timesheet-card">
          <h3>Weekly Submission and Summary</h3>
          <p>Submit a date range as weekly timesheet and generate LLM-ready summaries.</p>

          <div className="timesheet-form-grid">
            <label>
              Week Start Date
              <input type="date" value={weekStartDate} onChange={(event) => setWeekStartDate(event.target.value)} />
            </label>

            <label>
              Week End Date
              <input type="date" value={weekEndDate} onChange={(event) => setWeekEndDate(event.target.value)} />
            </label>
          </div>

          <button
            className="primary-button"
            onClick={() => submitWeekMutation.mutate()}
            disabled={submitWeekMutation.isPending}
          >
            {submitWeekMutation.isPending ? "Submitting..." : "Submit Week"}
          </button>

          <div className="timesheet-divider" />

          <div className="timesheet-form-grid">
            <label>
              Summary Start Date
              <input
                type="date"
                value={summaryStartDate}
                onChange={(event) => setSummaryStartDate(event.target.value)}
              />
            </label>

            <label>
              Summary End Date
              <input
                type="date"
                value={summaryEndDate}
                onChange={(event) => setSummaryEndDate(event.target.value)}
              />
            </label>

            <label className="timesheet-full-width">
              Summary Type
              <select value={summaryType} onChange={(event) => setSummaryType(event.target.value)}>
                <option value="Daily Summary">Daily Summary</option>
                <option value="Weekly Summary">Weekly Summary</option>
                <option value="Custom Date Range">Custom Date Range</option>
                <option value="Client Status Summary">Client Status Summary</option>
                <option value="Internal Delivery Summary">Internal Delivery Summary</option>
              </select>
            </label>
          </div>

          <button
            className="primary-button"
            onClick={() => generateSummaryMutation.mutate()}
            disabled={generateSummaryMutation.isPending}
          >
            {generateSummaryMutation.isPending ? "Generating Summary..." : "Generate LLM Summary"}
          </button>
        </div>
      </div>

      {message ? <div className="dictation-message">{message}</div> : null}

      <div className="content-section">
        <h2>Timesheet Entries</h2>
        <div className="table-card wide-table">
          {timesheets.length === 0 ? (
            <p className="empty-state">No timesheet entries yet.</p>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Activity</th>
                  <th>Accomplishments</th>
                  <th>Hours</th>
                  <th>Status</th>
                  <th>Submitted</th>
                  <th>Submitted At</th>
                </tr>
              </thead>
              <tbody>
                {timesheets.map((item) => (
                  <tr key={item.id}>
                    <td>{item.entry_date}</td>
                    <td>{item.activity_type}</td>
                    <td>
                      <strong>{truncate(item.accomplishments, 320)}</strong>
                      {item.blockers ? <div className="small-note">Blockers: {truncate(item.blockers, 220)}</div> : null}
                      {item.next_steps ? <div className="small-note">Next: {truncate(item.next_steps, 220)}</div> : null}
                    </td>
                    <td>{item.effort_hours}</td>
                    <td>
                      <StatusBadge status={item.status} />
                    </td>
                    <td>{yesNo(item.submitted)}</td>
                    <td>{formatDateTime(item.submitted_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      <div className="content-section">
        <h2>Timesheet Summaries</h2>
        <div className="table-card wide-table">
          {timesheetSummaries.length === 0 ? (
            <p className="empty-state">No timesheet summaries yet.</p>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>Summary</th>
                  <th>Range</th>
                  <th>Hours</th>
                  <th>Entries</th>
                  <th>Model</th>
                  <th>Trace Workflow</th>
                  <th>Created</th>
                </tr>
              </thead>
              <tbody>
                {timesheetSummaries.map((item) => (
                  <tr key={item.id}>
                    <td>
                      <strong>{item.summary_type}</strong>
                      <div className="small-note">{truncate(item.summary_text, 450)}</div>
                      {item.accomplishments_summary ? (
                        <div className="small-note">
                          Accomplishments: {truncate(item.accomplishments_summary, 300)}
                        </div>
                      ) : null}
                      {item.blockers_summary ? (
                        <div className="small-note">Blockers: {truncate(item.blockers_summary, 300)}</div>
                      ) : null}
                      {item.next_steps_summary ? (
                        <div className="small-note">Next: {truncate(item.next_steps_summary, 300)}</div>
                      ) : null}
                    </td>
                    <td>
                      {item.start_date} to {item.end_date}
                    </td>
                    <td>{item.total_effort_hours}</td>
                    <td>{item.entry_count}</td>
                    <td>{item.model_name ?? "-"}</td>
                    <td>{item.trace_workflow_name ?? "-"}</td>
                    <td>{formatDateTime(item.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </section>
  );
}