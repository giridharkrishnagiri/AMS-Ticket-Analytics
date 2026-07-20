import { useMemo, useState } from "react";

import type {
  AnalysisOutput,
  DataPoint,
  Deliverable,
  DeliverableReviewActionItem,
  DeliverableReviewWorkflow,
  Finding,
  LlmRecommendation,
  LlmRecommendationActionItem,
  StakeholderQuestion,
  Subtask,
  Task,
  Workstream,
} from "./types";

type RoleView =
  | "engagement_lead"
  | "delivery_owner"
  | "reviewer_approver"
  | "data_gathering_owner"
  | "automation_ai_advisor";

type HealthFilter =
  | "all"
  | "overdue"
  | "due_soon"
  | "rework_required"
  | "pending_data"
  | "pending_responses"
  | "open_review_actions"
  | "open_recommendation_actions";

function todayIsoDate() {
  return new Date().toISOString().slice(0, 10);
}

function addDaysIso(days: number) {
  const date = new Date();
  date.setDate(date.getDate() + days);
  return date.toISOString().slice(0, 10);
}

function formatDate(value: string | null) {
  return value || "-";
}

function truncate(value: string | null, maxLength = 220) {
  if (!value) {
    return "";
  }

  if (value.length <= maxLength) {
    return value;
  }

  return `${value.slice(0, maxLength - 3)}...`;
}

function StatusBadge({ status }: { status: string }) {
  return <span className="status-badge">{status}</span>;
}

function isCompleted(status: string | null | undefined) {
  return (status || "").toLowerCase() === "completed";
}

function isOverdue(dateValue: string | null | undefined, status: string | null | undefined) {
  if (!dateValue || isCompleted(status)) {
    return false;
  }

  return dateValue < todayIsoDate();
}

function isDueSoon(dateValue: string | null | undefined, status: string | null | undefined) {
  if (!dateValue || isCompleted(status)) {
    return false;
  }

  const today = todayIsoDate();
  const soon = addDaysIso(7);

  return dateValue >= today && dateValue <= soon;
}

function getEffectiveDueDate(item: {
  revised_completion_date?: string | null;
  target_completion_date?: string | null;
  due_date?: string | null;
}) {
  return item.revised_completion_date || item.target_completion_date || item.due_date || null;
}

function getRoleLabel(role: RoleView) {
  const labels: Record<RoleView, string> = {
    engagement_lead: "Engagement Lead",
    delivery_owner: "Delivery Owner",
    reviewer_approver: "Reviewer / Approver",
    data_gathering_owner: "Data Gathering Owner",
    automation_ai_advisor: "Automation / AI Advisor",
  };

  return labels[role];
}

function getHealthFilterLabel(filter: HealthFilter) {
  const labels: Record<HealthFilter, string> = {
    all: "All",
    overdue: "Overdue",
    due_soon: "Due Soon",
    rework_required: "Rework Required",
    pending_data: "Pending Data",
    pending_responses: "Pending Responses",
    open_review_actions: "Open Review Actions",
    open_recommendation_actions: "Open Recommendation Actions",
  };

  return labels[filter];
}

function findWorkstreamName(workstreams: Workstream[], workstreamId: string) {
  const item = workstreams.find((workstream) => workstream.id === workstreamId);
  return item ? `${item.external_id ? `${item.external_id} - ` : ""}${item.name}` : "-";
}

function findDeliverableName(deliverables: Deliverable[], deliverableId: string | null) {
  if (!deliverableId) {
    return "-";
  }

  const item = deliverables.find((deliverable) => deliverable.id === deliverableId);
  return item ? `${item.external_id ? `${item.external_id} - ` : ""}${item.name}` : "-";
}

function findTaskName(tasks: Task[], taskId: string | null) {
  if (!taskId) {
    return "-";
  }

  const item = tasks.find((task) => task.id === taskId);
  return item ? `${item.external_id ? `${item.external_id} - ` : ""}${item.title}` : "-";
}

export function Mvp13RoleBasedViewsPanel({
  workstreams,
  deliverables,
  tasks,
  subtasks,
  dataPoints,
  stakeholderQuestions,
  findings,
  analysisOutputs,
  llmRecommendations,
  reviewWorkflows: _reviewWorkflows,
  reviewActionItems,
  recommendationActionItems,
}: {
  workstreams: Workstream[];
  deliverables: Deliverable[];
  tasks: Task[];
  subtasks: Subtask[];
  dataPoints: DataPoint[];
  stakeholderQuestions: StakeholderQuestion[];
  findings: Finding[];
  analysisOutputs: AnalysisOutput[];
  llmRecommendations: LlmRecommendation[];
  reviewWorkflows: DeliverableReviewWorkflow[];
  reviewActionItems: DeliverableReviewActionItem[];
  recommendationActionItems: LlmRecommendationActionItem[];
}) {
  const [roleView, setRoleView] = useState<RoleView>("engagement_lead");
  const [healthFilter, setHealthFilter] = useState<HealthFilter>("all");
  const [searchText, setSearchText] = useState("");

  const lowerSearch = searchText.trim().toLowerCase();

  const workstreamDeliverableIds = new Set(deliverables.map((item) => item.id));
  const taskIds = new Set(tasks.map((item) => item.id));
  const subtaskIds = new Set(subtasks.map((item) => item.id));

  const filteredDeliverables = useMemo(() => {
    let rows = deliverables;

    if (roleView === "reviewer_approver") {
      rows = rows.filter(
        (item) =>
          (item.review_status || "").toLowerCase().includes("review") ||
          (item.review_status || "").toLowerCase().includes("rework") ||
          (item.review_status || "").toLowerCase().includes("approved"),
      );
    }

    if (roleView === "data_gathering_owner") {
      rows = rows.filter((item) =>
        item.name.toLowerCase().includes("inventory") ||
        item.name.toLowerCase().includes("mapping") ||
        item.name.toLowerCase().includes("data") ||
        item.name.toLowerCase().includes("capacity"),
      );
    }

    if (roleView === "automation_ai_advisor") {
      rows = rows.filter((item) =>
        item.name.toLowerCase().includes("automation") ||
        item.name.toLowerCase().includes("ai") ||
        item.name.toLowerCase().includes("agentic") ||
        item.name.toLowerCase().includes("opportunity"),
      );
    }

    if (healthFilter === "overdue") {
      rows = rows.filter((item) => isOverdue(getEffectiveDueDate(item), item.status));
    }

    if (healthFilter === "due_soon") {
      rows = rows.filter((item) => isDueSoon(getEffectiveDueDate(item), item.status));
    }

    if (healthFilter === "rework_required") {
      rows = rows.filter((item) => (item.review_status || "").toLowerCase().includes("rework"));
    }

    if (lowerSearch) {
      rows = rows.filter(
        (item) =>
          item.name.toLowerCase().includes(lowerSearch) ||
          (item.external_id || "").toLowerCase().includes(lowerSearch) ||
          (item.description || "").toLowerCase().includes(lowerSearch),
      );
    }

    return rows;
  }, [deliverables, healthFilter, lowerSearch, roleView]);

  const filteredTasks = useMemo(() => {
    let rows = tasks;

    if (roleView === "reviewer_approver") {
      const filteredDeliverableIds = new Set(filteredDeliverables.map((item) => item.id));
      rows = rows.filter((item) => filteredDeliverableIds.has(item.deliverable_id));
    }

    if (healthFilter === "overdue") {
      rows = rows.filter((item) => isOverdue(getEffectiveDueDate(item), item.status));
    }

    if (healthFilter === "due_soon") {
      rows = rows.filter((item) => isDueSoon(getEffectiveDueDate(item), item.status));
    }

    if (lowerSearch) {
      rows = rows.filter(
        (item) =>
          item.title.toLowerCase().includes(lowerSearch) ||
          (item.external_id || "").toLowerCase().includes(lowerSearch) ||
          (item.description || "").toLowerCase().includes(lowerSearch),
      );
    }

    return rows;
  }, [filteredDeliverables, healthFilter, lowerSearch, roleView, tasks]);

  const filteredSubtasks = useMemo(() => {
    let rows = subtasks;

    if (roleView === "reviewer_approver") {
      const filteredTaskIds = new Set(filteredTasks.map((item) => item.id));
      rows = rows.filter((item) => filteredTaskIds.has(item.task_id));
    }

    if (healthFilter === "overdue") {
      rows = rows.filter((item) => isOverdue(getEffectiveDueDate(item), item.status));
    }

    if (healthFilter === "due_soon") {
      rows = rows.filter((item) => isDueSoon(getEffectiveDueDate(item), item.status));
    }

    if (lowerSearch) {
      rows = rows.filter(
        (item) =>
          item.title.toLowerCase().includes(lowerSearch) ||
          (item.external_id || "").toLowerCase().includes(lowerSearch) ||
          (item.description || "").toLowerCase().includes(lowerSearch),
      );
    }

    return rows;
  }, [filteredTasks, healthFilter, lowerSearch, roleView, subtasks]);

  const filteredDataPoints = useMemo(() => {
    let rows = dataPoints;

    if (roleView === "data_gathering_owner" || healthFilter === "pending_data") {
      rows = rows.filter((item) => item.status.toLowerCase() !== "received");
    }

    if (lowerSearch) {
      rows = rows.filter(
        (item) =>
          item.topic.toLowerCase().includes(lowerSearch) ||
          (item.details || "").toLowerCase().includes(lowerSearch) ||
          (item.source || "").toLowerCase().includes(lowerSearch),
      );
    }

    return rows;
  }, [dataPoints, healthFilter, lowerSearch, roleView]);

  const filteredQuestions = useMemo(() => {
    let rows = stakeholderQuestions;

    if (healthFilter === "pending_responses") {
      rows = rows.filter((item) => item.response_status.toLowerCase() !== "responded");
    }

    if (lowerSearch) {
      rows = rows.filter(
        (item) =>
          item.question_text.toLowerCase().includes(lowerSearch) ||
          (item.stakeholder_name || "").toLowerCase().includes(lowerSearch) ||
          (item.response_details || "").toLowerCase().includes(lowerSearch),
      );
    }

    return rows;
  }, [healthFilter, lowerSearch, stakeholderQuestions]);

  const filteredFindings = useMemo(() => {
    let rows = findings;

    if (roleView === "reviewer_approver") {
      rows = rows.filter((item) => !item.is_validated || item.status.toLowerCase().includes("review"));
    }

    if (lowerSearch) {
      rows = rows.filter(
        (item) =>
          item.title.toLowerCase().includes(lowerSearch) ||
          item.finding_text.toLowerCase().includes(lowerSearch) ||
          (item.recommendation || "").toLowerCase().includes(lowerSearch),
      );
    }

    return rows;
  }, [findings, lowerSearch, roleView]);

  const filteredAnalysisOutputs = useMemo(() => {
    let rows = analysisOutputs;

    if (roleView === "reviewer_approver") {
      rows = rows.filter((item) => !item.reviewed_by || item.status.toLowerCase().includes("review"));
    }

    if (lowerSearch) {
      rows = rows.filter(
        (item) =>
          item.analysis_title.toLowerCase().includes(lowerSearch) ||
          item.analysis_text.toLowerCase().includes(lowerSearch),
      );
    }

    return rows;
  }, [analysisOutputs, lowerSearch, roleView]);

  const filteredRecommendations = useMemo(() => {
    let rows = llmRecommendations;

    if (roleView === "automation_ai_advisor") {
      rows = rows.filter(
        (item) =>
          item.recommendation_text.toLowerCase().includes("automation") ||
          item.recommendation_text.toLowerCase().includes("ai") ||
          item.recommendation_text.toLowerCase().includes("agent") ||
          item.recommendation_type.toLowerCase().includes("automation"),
      );
    }

    if (lowerSearch) {
      rows = rows.filter(
        (item) =>
          item.title.toLowerCase().includes(lowerSearch) ||
          item.recommendation_text.toLowerCase().includes(lowerSearch) ||
          (item.category || "").toLowerCase().includes(lowerSearch),
      );
    }

    return rows;
  }, [llmRecommendations, lowerSearch, roleView]);

  const filteredReviewActions = useMemo(() => {
    let rows = reviewActionItems;

    if (healthFilter === "open_review_actions" || roleView === "reviewer_approver") {
      rows = rows.filter((item) => item.status.toLowerCase() !== "completed");
    }

    if (lowerSearch) {
      rows = rows.filter(
        (item) =>
          item.action_title.toLowerCase().includes(lowerSearch) ||
          (item.action_description || "").toLowerCase().includes(lowerSearch) ||
          (item.owner_name || "").toLowerCase().includes(lowerSearch),
      );
    }

    return rows;
  }, [healthFilter, lowerSearch, reviewActionItems, roleView]);

  const filteredRecommendationActions = useMemo(() => {
    let rows = recommendationActionItems;

    if (healthFilter === "open_recommendation_actions" || roleView === "automation_ai_advisor") {
      rows = rows.filter((item) => item.status.toLowerCase() !== "completed");
    }

    if (lowerSearch) {
      rows = rows.filter(
        (item) =>
          item.action_title.toLowerCase().includes(lowerSearch) ||
          (item.action_description || "").toLowerCase().includes(lowerSearch) ||
          (item.owner_name || "").toLowerCase().includes(lowerSearch),
      );
    }

    return rows;
  }, [healthFilter, lowerSearch, recommendationActionItems, roleView]);

  const overdueCount =
    deliverables.filter((item) => isOverdue(getEffectiveDueDate(item), item.status)).length +
    tasks.filter((item) => isOverdue(getEffectiveDueDate(item), item.status)).length +
    subtasks.filter((item) => isOverdue(getEffectiveDueDate(item), item.status)).length;

  const dueSoonCount =
    deliverables.filter((item) => isDueSoon(getEffectiveDueDate(item), item.status)).length +
    tasks.filter((item) => isDueSoon(getEffectiveDueDate(item), item.status)).length +
    subtasks.filter((item) => isDueSoon(getEffectiveDueDate(item), item.status)).length;

  const reworkCount = deliverables.filter((item) =>
    (item.review_status || "").toLowerCase().includes("rework"),
  ).length;

  const pendingDataCount = dataPoints.filter((item) => item.status.toLowerCase() !== "received").length;
  const pendingResponsesCount = stakeholderQuestions.filter(
    (item) => item.response_status.toLowerCase() !== "responded",
  ).length;

  const openReviewActionCount = reviewActionItems.filter(
    (item) => item.status.toLowerCase() !== "completed",
  ).length;
  const openRecommendationActionCount = recommendationActionItems.filter(
    (item) => item.status.toLowerCase() !== "completed",
  ).length;

  return (
    <section id="role-based-views" className="content-section">
      <div className="section-header">
        <div>
          <h2>Role-Based Views and Filters</h2>
          <p>
            Focus the cockpit by role, delivery health, and search text. These are
            frontend filters over the current project data.
          </p>
        </div>
      </div>

      <div className="filter-panel">
        <div className="timesheet-form-grid">
          <label>
            Role View
            <select value={roleView} onChange={(event) => setRoleView(event.target.value as RoleView)}>
              <option value="engagement_lead">Engagement Lead</option>
              <option value="delivery_owner">Delivery Owner</option>
              <option value="reviewer_approver">Reviewer / Approver</option>
              <option value="data_gathering_owner">Data Gathering Owner</option>
              <option value="automation_ai_advisor">Automation / AI Advisor</option>
            </select>
          </label>

          <label>
            Health Filter
            <select
              value={healthFilter}
              onChange={(event) => setHealthFilter(event.target.value as HealthFilter)}
            >
              <option value="all">All</option>
              <option value="overdue">Overdue</option>
              <option value="due_soon">Due Soon</option>
              <option value="rework_required">Rework Required</option>
              <option value="pending_data">Pending Data</option>
              <option value="pending_responses">Pending Responses</option>
              <option value="open_review_actions">Open Review Actions</option>
              <option value="open_recommendation_actions">Open Recommendation Actions</option>
            </select>
          </label>

          <label className="timesheet-full-width">
            Search
            <input
              value={searchText}
              onChange={(event) => setSearchText(event.target.value)}
              placeholder="Search by title, ID, stakeholder, action, finding, recommendation..."
            />
          </label>
        </div>

        <div className="selected-context">
          Current view: {getRoleLabel(roleView)} | Filter: {getHealthFilterLabel(healthFilter)}
        </div>
      </div>

      <div className="report-summary-grid">
        <div className="report-card">
          <span>Filtered Deliverables</span>
          <strong>{filteredDeliverables.length}</strong>
          <p>Deliverables in this view</p>
        </div>
        <div className="report-card">
          <span>Filtered Tasks</span>
          <strong>{filteredTasks.length}</strong>
          <p>Tasks in this view</p>
        </div>
        <div className="report-card">
          <span>Filtered Sub-tasks</span>
          <strong>{filteredSubtasks.length}</strong>
          <p>Sub-tasks in this view</p>
        </div>
        <div className="report-card">
          <span>Overdue</span>
          <strong>{overdueCount}</strong>
          <p>Across deliverables/tasks/sub-tasks</p>
        </div>
        <div className="report-card">
          <span>Due Soon</span>
          <strong>{dueSoonCount}</strong>
          <p>Due within 7 days</p>
        </div>
        <div className="report-card">
          <span>Rework Required</span>
          <strong>{reworkCount}</strong>
          <p>Deliverables needing changes</p>
        </div>
        <div className="report-card">
          <span>Pending Data</span>
          <strong>{pendingDataCount}</strong>
          <p>Data points not received</p>
        </div>
        <div className="report-card">
          <span>Pending Responses</span>
          <strong>{pendingResponsesCount}</strong>
          <p>Stakeholder responses open</p>
        </div>
        <div className="report-card">
          <span>Open Review Actions</span>
          <strong>{openReviewActionCount}</strong>
          <p>Review follow-ups open</p>
        </div>
        <div className="report-card">
          <span>Open Recommendation Actions</span>
          <strong>{openRecommendationActionCount}</strong>
          <p>LLM recommendation actions open</p>
        </div>
      </div>

      <div className="content-section">
        <h2>Filtered Deliverables</h2>
        <div className="table-card wide-table">
          {filteredDeliverables.length === 0 ? (
            <p className="empty-state">No deliverables match this view.</p>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>Deliverable</th>
                  <th>Workstream</th>
                  <th>Status</th>
                  <th>Review Status</th>
                  <th>Target</th>
                  <th>Revised</th>
                  <th>Approval</th>
                </tr>
              </thead>
              <tbody>
                {filteredDeliverables.map((item) => (
                  <tr key={item.id}>
                    <td>
                      <strong>{item.external_id ? `${item.external_id} - ` : ""}{item.name}</strong>
                      {item.description ? <div className="small-note">{truncate(item.description, 260)}</div> : null}
                    </td>
                    <td>{findWorkstreamName(workstreams, item.workstream_id)}</td>
                    <td><StatusBadge status={item.status} /></td>
                    <td>{item.review_status ?? "-"}</td>
                    <td>{formatDate(item.target_completion_date)}</td>
                    <td>{formatDate(item.revised_completion_date)}</td>
                    <td>{formatDate(item.approval_date)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      <div className="content-section">
        <h2>Filtered Tasks and Sub-tasks</h2>
        <div className="table-card wide-table">
          {filteredTasks.length === 0 && filteredSubtasks.length === 0 ? (
            <p className="empty-state">No tasks or sub-tasks match this view.</p>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>Type</th>
                  <th>Work Item</th>
                  <th>Parent</th>
                  <th>Status</th>
                  <th>Priority</th>
                  <th>Target</th>
                  <th>Revised</th>
                </tr>
              </thead>
              <tbody>
                {filteredTasks.map((item) => (
                  <tr key={`task-${item.id}`}>
                    <td>Task</td>
                    <td>
                      <strong>{item.external_id ? `${item.external_id} - ` : ""}{item.title}</strong>
                      {item.description ? <div className="small-note">{truncate(item.description, 260)}</div> : null}
                    </td>
                    <td>{findDeliverableName(deliverables, item.deliverable_id)}</td>
                    <td><StatusBadge status={item.status} /></td>
                    <td>{item.priority ?? "-"}</td>
                    <td>{formatDate(item.target_completion_date)}</td>
                    <td>{formatDate(item.revised_completion_date)}</td>
                  </tr>
                ))}
                {filteredSubtasks.map((item) => (
                  <tr key={`subtask-${item.id}`}>
                    <td>Sub-task</td>
                    <td>
                      <strong>{item.external_id ? `${item.external_id} - ` : ""}{item.title}</strong>
                      {item.description ? <div className="small-note">{truncate(item.description, 260)}</div> : null}
                    </td>
                    <td>{findTaskName(tasks, item.task_id)}</td>
                    <td><StatusBadge status={item.status} /></td>
                    <td>{item.priority ?? "-"}</td>
                    <td>{formatDate(item.target_completion_date)}</td>
                    <td>{formatDate(item.revised_completion_date)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      <div className="content-section">
        <h2>Filtered Data and Stakeholder Follow-ups</h2>
        <div className="table-card wide-table">
          {filteredDataPoints.length === 0 && filteredQuestions.length === 0 ? (
            <p className="empty-state">No data points or stakeholder questions match this view.</p>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>Type</th>
                  <th>Item</th>
                  <th>Owner / Source</th>
                  <th>Status</th>
                  <th>Expected</th>
                  <th>Actual</th>
                </tr>
              </thead>
              <tbody>
                {filteredDataPoints.map((item) => (
                  <tr key={`data-${item.id}`}>
                    <td>Data Point</td>
                    <td>
                      <strong>{item.topic}</strong>
                      {item.details ? <div className="small-note">{truncate(item.details, 260)}</div> : null}
                    </td>
                    <td>{item.source ?? "-"}</td>
                    <td><StatusBadge status={item.status} /></td>
                    <td>{formatDate(item.expected_received_date)}</td>
                    <td>{formatDate(item.actual_received_date)}</td>
                  </tr>
                ))}
                {filteredQuestions.map((item) => (
                  <tr key={`question-${item.id}`}>
                    <td>Stakeholder Question</td>
                    <td>
                      <strong>{item.question_text}</strong>
                      {item.response_details ? (
                        <div className="small-note">Response: {truncate(item.response_details, 260)}</div>
                      ) : null}
                    </td>
                    <td>{item.stakeholder_name ?? "-"}</td>
                    <td><StatusBadge status={item.response_status} /></td>
                    <td>{formatDate(item.expected_response_date)}</td>
                    <td>{formatDate(item.actual_response_date)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      <div className="content-section">
        <h2>Filtered Consulting Outputs</h2>
        <div className="table-card wide-table">
          {filteredFindings.length === 0 && filteredAnalysisOutputs.length === 0 && filteredRecommendations.length === 0 ? (
            <p className="empty-state">No findings, analysis outputs, or recommendations match this view.</p>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>Type</th>
                  <th>Output</th>
                  <th>Status</th>
                  <th>Confidence / Priority</th>
                  <th>Validated / Model</th>
                </tr>
              </thead>
              <tbody>
                {filteredFindings.map((item) => (
                  <tr key={`finding-${item.id}`}>
                    <td>Finding</td>
                    <td>
                      <strong>{item.title}</strong>
                      <div className="small-note">{truncate(item.finding_text, 320)}</div>
                    </td>
                    <td><StatusBadge status={item.status} /></td>
                    <td>{item.confidence_level ?? item.severity ?? "-"}</td>
                    <td>{item.is_validated ? "Validated" : "Not validated"}</td>
                  </tr>
                ))}
                {filteredAnalysisOutputs.map((item) => (
                  <tr key={`analysis-${item.id}`}>
                    <td>Analysis</td>
                    <td>
                      <strong>{item.analysis_title}</strong>
                      <div className="small-note">{truncate(item.analysis_text, 320)}</div>
                    </td>
                    <td><StatusBadge status={item.status} /></td>
                    <td>{item.confidence_level ?? "-"}</td>
                    <td>{item.reviewed_by ?? "-"}</td>
                  </tr>
                ))}
                {filteredRecommendations.map((item) => (
                  <tr key={`recommendation-${item.id}`}>
                    <td>LLM Recommendation</td>
                    <td>
                      <strong>{item.title}</strong>
                      <div className="small-note">{truncate(item.recommendation_text, 320)}</div>
                    </td>
                    <td><StatusBadge status={item.status} /></td>
                    <td>{item.priority ?? item.category ?? "-"}</td>
                    <td>{item.model_name ?? "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      <div className="content-section">
        <h2>Filtered Review and Recommendation Actions</h2>
        <div className="table-card wide-table">
          {filteredReviewActions.length === 0 && filteredRecommendationActions.length === 0 ? (
            <p className="empty-state">No action items match this view.</p>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>Type</th>
                  <th>Action</th>
                  <th>Owner</th>
                  <th>Priority</th>
                  <th>Status</th>
                  <th>Due Date</th>
                  <th>Completed</th>
                </tr>
              </thead>
              <tbody>
                {filteredReviewActions.map((item) => (
                  <tr key={`review-action-${item.id}`}>
                    <td>Review Action</td>
                    <td>
                      <strong>{item.action_title}</strong>
                      {item.action_description ? (
                        <div className="small-note">{truncate(item.action_description, 260)}</div>
                      ) : null}
                    </td>
                    <td>{item.owner_name ?? "-"}</td>
                    <td>{item.priority ?? "-"}</td>
                    <td><StatusBadge status={item.status} /></td>
                    <td>{formatDate(item.due_date)}</td>
                    <td>{formatDate(item.completed_at)}</td>
                  </tr>
                ))}
                {filteredRecommendationActions.map((item) => (
                  <tr key={`recommendation-action-${item.id}`}>
                    <td>Recommendation Action</td>
                    <td>
                      <strong>{item.action_title}</strong>
                      {item.action_description ? (
                        <div className="small-note">{truncate(item.action_description, 260)}</div>
                      ) : null}
                    </td>
                    <td>{item.owner_name ?? "-"}</td>
                    <td>{item.priority ?? "-"}</td>
                    <td><StatusBadge status={item.status} /></td>
                    <td>{formatDate(item.due_date)}</td>
                    <td>{formatDate(item.completed_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      <div className="selected-context content-section">
        Workstream IDs loaded: {workstreams.length}. Deliverable IDs loaded: {workstreamDeliverableIds.size}. Task IDs loaded: {taskIds.size}. Sub-task IDs loaded: {subtaskIds.size}.
      </div>
    </section>
  );
}