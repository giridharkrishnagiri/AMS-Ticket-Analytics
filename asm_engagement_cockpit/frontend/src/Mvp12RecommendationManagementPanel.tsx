import { useMemo, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import {
  createLlmRecommendationActionItem,
  markLlmRecommendationCompleted,
  recordLlmRecommendationDecision,
  reviseLlmRecommendation,
  updateLlmRecommendationActionItem,
} from "./api";
import type {
  LlmRecommendation,
  LlmRecommendationActionItem,
  LlmRecommendationDecision,
  LlmRecommendationRevision,
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

function truncate(value: string | null, maxLength = 260) {
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

function getRecommendationLabel(recommendations: LlmRecommendation[], recommendationId: string) {
  const recommendation = recommendations.find((item) => item.id === recommendationId);

  if (!recommendation) {
    return recommendationId;
  }

  return recommendation.title;
}

export function Mvp12RecommendationManagementPanel({
  recommendations,
  decisions,
  revisions,
  actionItems,
}: {
  recommendations: LlmRecommendation[];
  decisions: LlmRecommendationDecision[];
  revisions: LlmRecommendationRevision[];
  actionItems: LlmRecommendationActionItem[];
}) {
  const queryClient = useQueryClient();

  const [selectedRecommendationId, setSelectedRecommendationId] = useState("");
  const [decision, setDecision] = useState("Accepted");
  const [decisionNotes, setDecisionNotes] = useState("");
  const [decidedBy, setDecidedBy] = useState("Giridhar Krishnagiri");

  const [revisionRecommendationId, setRevisionRecommendationId] = useState("");
  const [revisionTitle, setRevisionTitle] = useState("");
  const [revisionText, setRevisionText] = useState("");
  const [revisionRationale, setRevisionRationale] = useState("");
  const [revisionBenefit, setRevisionBenefit] = useState("");
  const [revisionImplementationNotes, setRevisionImplementationNotes] = useState("");
  const [revisionNotes, setRevisionNotes] = useState("");
  const [revisedBy, setRevisedBy] = useState("Giridhar Krishnagiri");

  const [actionRecommendationId, setActionRecommendationId] = useState("");
  const [actionTitle, setActionTitle] = useState("");
  const [actionDescription, setActionDescription] = useState("");
  const [actionOwner, setActionOwner] = useState("Giridhar Krishnagiri");
  const [actionPriority, setActionPriority] = useState("Medium");
  const [actionDueDate, setActionDueDate] = useState(todayIsoDate());

  const [message, setMessage] = useState("");

  const selectedRevisionRecommendation = useMemo(() => {
    return recommendations.find((item) => item.id === revisionRecommendationId);
  }, [recommendations, revisionRecommendationId]);

  const acceptedRecommendations = recommendations.filter((item) => item.status.toLowerCase() === "accepted");
  const inProgressRecommendations = recommendations.filter((item) => item.status.toLowerCase() === "in progress");
  const rejectedRecommendations = recommendations.filter((item) => item.status.toLowerCase() === "rejected");
  const completedRecommendations = recommendations.filter((item) => item.status.toLowerCase() === "completed");
  const openActionItems = actionItems.filter((item) => item.status.toLowerCase() !== "completed");
  const completedActionItems = actionItems.filter((item) => item.status.toLowerCase() === "completed");

  const decisionMutation = useMutation({
    mutationFn: () =>
      recordLlmRecommendationDecision({
        recommendation_id: selectedRecommendationId,
        decision,
        decision_notes: decisionNotes || null,
        decided_by: decidedBy,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["llm-recommendations"] });
      queryClient.invalidateQueries({ queryKey: ["llm-recommendation-decisions"] });
      setDecisionNotes("");
      setMessage("Recommendation decision recorded successfully.");
    },
    onError: (error) => {
      setMessage(error instanceof Error ? error.message : "Failed to record recommendation decision.");
    },
  });

  const revisionMutation = useMutation({
    mutationFn: () =>
      reviseLlmRecommendation({
        recommendation_id: revisionRecommendationId,
        title: revisionTitle || null,
        recommendation_text: revisionText || null,
        rationale: revisionRationale || null,
        expected_benefit: revisionBenefit || null,
        implementation_notes: revisionImplementationNotes || null,
        revision_notes: revisionNotes || null,
        revised_by: revisedBy,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["llm-recommendations"] });
      queryClient.invalidateQueries({ queryKey: ["llm-recommendation-revisions"] });
      setRevisionNotes("");
      setMessage("Recommendation revised successfully.");
    },
    onError: (error) => {
      setMessage(error instanceof Error ? error.message : "Failed to revise recommendation.");
    },
  });

  const actionItemMutation = useMutation({
    mutationFn: () =>
      createLlmRecommendationActionItem({
        recommendation_id: actionRecommendationId,
        action_title: actionTitle,
        action_description: actionDescription || null,
        owner_name: actionOwner || null,
        priority: actionPriority,
        status: "Open",
        due_date: actionDueDate || null,
        created_by: actionOwner || "Giridhar Krishnagiri",
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["llm-recommendations"] });
      queryClient.invalidateQueries({ queryKey: ["llm-recommendation-action-items"] });
      setActionTitle("");
      setActionDescription("");
      setMessage("Recommendation action item created successfully.");
    },
    onError: (error) => {
      setMessage(error instanceof Error ? error.message : "Failed to create recommendation action item.");
    },
  });

  const completeActionItemMutation = useMutation({
    mutationFn: (actionItemId: string) =>
      updateLlmRecommendationActionItem({
        action_item_id: actionItemId,
        status: "Completed",
        completion_notes: "Completed from recommendation management UI.",
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["llm-recommendations"] });
      queryClient.invalidateQueries({ queryKey: ["llm-recommendation-action-items"] });
      setMessage("Recommendation action item marked completed.");
    },
    onError: (error) => {
      setMessage(error instanceof Error ? error.message : "Failed to complete action item.");
    },
  });

  const markCompletedMutation = useMutation({
    mutationFn: (recommendationId: string) =>
      markLlmRecommendationCompleted({
        recommendation_id: recommendationId,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["llm-recommendations"] });
      setMessage("Recommendation marked completed.");
    },
    onError: (error) => {
      setMessage(error instanceof Error ? error.message : "Failed to mark recommendation completed.");
    },
  });

  function recordDecision() {
    if (!selectedRecommendationId) {
      setMessage("Select a recommendation before recording a decision.");
      return;
    }

    setMessage("");
    decisionMutation.mutate();
  }

  function loadRecommendationForRevision(recommendationId: string) {
    const recommendation = recommendations.find((item) => item.id === recommendationId);
    setRevisionRecommendationId(recommendationId);

    if (recommendation) {
      setRevisionTitle(recommendation.title);
      setRevisionText(recommendation.recommendation_text);
      setRevisionRationale(recommendation.rationale ?? "");
      setRevisionBenefit(recommendation.expected_benefit ?? "");
      setRevisionImplementationNotes(recommendation.implementation_notes ?? "");
    }
  }

  function saveRevision() {
    if (!revisionRecommendationId) {
      setMessage("Select a recommendation before revising it.");
      return;
    }

    if (!revisionTitle.trim() && !revisionText.trim()) {
      setMessage("Provide at least a revised title or revised recommendation text.");
      return;
    }

    setMessage("");
    revisionMutation.mutate();
  }

  function createActionItem() {
    if (!actionRecommendationId) {
      setMessage("Select a recommendation before creating an action item.");
      return;
    }

    if (!actionTitle.trim()) {
      setMessage("Action title is required.");
      return;
    }

    setMessage("");
    actionItemMutation.mutate();
  }

  return (
    <section id="recommendation-management" className="content-section">
      <div className="section-header">
        <div>
          <h2>Recommendation Management</h2>
          <p>
            Accept, reject, revise, and operationalize LLM recommendations through
            action items and lifecycle decisions.
          </p>
        </div>
      </div>

      <div className="report-summary-grid">
        <div className="report-card">
          <span>Total Recommendations</span>
          <strong>{recommendations.length}</strong>
          <p>Generated LLM recommendations</p>
        </div>
        <div className="report-card">
          <span>Accepted</span>
          <strong>{acceptedRecommendations.length}</strong>
          <p>Accepted for action</p>
        </div>
        <div className="report-card">
          <span>In Progress</span>
          <strong>{inProgressRecommendations.length}</strong>
          <p>Currently being implemented</p>
        </div>
        <div className="report-card">
          <span>Rejected</span>
          <strong>{rejectedRecommendations.length}</strong>
          <p>Not moving forward</p>
        </div>
        <div className="report-card">
          <span>Completed</span>
          <strong>{completedRecommendations.length}</strong>
          <p>Fully implemented</p>
        </div>
        <div className="report-card">
          <span>Open Actions</span>
          <strong>{openActionItems.length}</strong>
          <p>Recommendation action items</p>
        </div>
        <div className="report-card">
          <span>Completed Actions</span>
          <strong>{completedActionItems.length}</strong>
          <p>Closed action items</p>
        </div>
      </div>

      <div className="timesheet-grid">
        <div className="timesheet-card">
          <h3>Record Recommendation Decision</h3>
          <p>Accept, reject, defer, or start implementation for a recommendation.</p>

          <div className="timesheet-form-grid">
            <label className="timesheet-full-width">
              Recommendation
              <select
                value={selectedRecommendationId}
                onChange={(event) => setSelectedRecommendationId(event.target.value)}
              >
                <option value="">Select recommendation</option>
                {recommendations.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.title} | {item.status}
                  </option>
                ))}
              </select>
            </label>

            <label>
              Decision
              <select value={decision} onChange={(event) => setDecision(event.target.value)}>
                <option value="Accepted">Accepted</option>
                <option value="Rejected">Rejected</option>
                <option value="Deferred">Deferred</option>
                <option value="In Progress">In Progress</option>
                <option value="Needs Revision">Needs Revision</option>
              </select>
            </label>

            <label>
              Decided By
              <input value={decidedBy} onChange={(event) => setDecidedBy(event.target.value)} />
            </label>

            <label className="timesheet-full-width">
              Decision Notes
              <textarea value={decisionNotes} onChange={(event) => setDecisionNotes(event.target.value)} />
            </label>
          </div>

          <button className="primary-button" onClick={recordDecision} disabled={decisionMutation.isPending}>
            {decisionMutation.isPending ? "Recording..." : "Record Decision"}
          </button>
        </div>

        <div className="timesheet-card">
          <h3>Create Recommendation Action Item</h3>
          <p>Turn an accepted or useful recommendation into trackable delivery action.</p>

          <div className="timesheet-form-grid">
            <label className="timesheet-full-width">
              Recommendation
              <select
                value={actionRecommendationId}
                onChange={(event) => setActionRecommendationId(event.target.value)}
              >
                <option value="">Select recommendation</option>
                {recommendations.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.title} | {item.status}
                  </option>
                ))}
              </select>
            </label>

            <label>
              Action Title
              <input value={actionTitle} onChange={(event) => setActionTitle(event.target.value)} />
            </label>

            <label>
              Owner
              <input value={actionOwner} onChange={(event) => setActionOwner(event.target.value)} />
            </label>

            <label>
              Priority
              <select value={actionPriority} onChange={(event) => setActionPriority(event.target.value)}>
                <option value="High">High</option>
                <option value="Medium">Medium</option>
                <option value="Low">Low</option>
              </select>
            </label>

            <label>
              Due Date
              <input type="date" value={actionDueDate} onChange={(event) => setActionDueDate(event.target.value)} />
            </label>

            <label className="timesheet-full-width">
              Action Description
              <textarea value={actionDescription} onChange={(event) => setActionDescription(event.target.value)} />
            </label>
          </div>

          <button className="primary-button" onClick={createActionItem} disabled={actionItemMutation.isPending}>
            {actionItemMutation.isPending ? "Creating..." : "Create Action Item"}
          </button>
        </div>
      </div>

      <div className="timesheet-card content-section">
        <h3>Revise Recommendation</h3>
        <p>
          Preserve the original LLM output in history while updating the operational recommendation text.
        </p>

        <div className="timesheet-form-grid">
          <label className="timesheet-full-width">
            Recommendation
            <select
              value={revisionRecommendationId}
              onChange={(event) => loadRecommendationForRevision(event.target.value)}
            >
              <option value="">Select recommendation</option>
              {recommendations.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.title} | {item.status}
                </option>
              ))}
            </select>
          </label>

          <label className="timesheet-full-width">
            Revised Title
            <input value={revisionTitle} onChange={(event) => setRevisionTitle(event.target.value)} />
          </label>

          <label className="timesheet-full-width">
            Revised Recommendation Text
            <textarea value={revisionText} onChange={(event) => setRevisionText(event.target.value)} />
          </label>

          <label className="timesheet-full-width">
            Revised Rationale
            <textarea value={revisionRationale} onChange={(event) => setRevisionRationale(event.target.value)} />
          </label>

          <label className="timesheet-full-width">
            Revised Expected Benefit
            <textarea value={revisionBenefit} onChange={(event) => setRevisionBenefit(event.target.value)} />
          </label>

          <label className="timesheet-full-width">
            Revised Implementation Notes
            <textarea
              value={revisionImplementationNotes}
              onChange={(event) => setRevisionImplementationNotes(event.target.value)}
            />
          </label>

          <label>
            Revised By
            <input value={revisedBy} onChange={(event) => setRevisedBy(event.target.value)} />
          </label>

          <label className="timesheet-full-width">
            Revision Notes
            <textarea value={revisionNotes} onChange={(event) => setRevisionNotes(event.target.value)} />
          </label>
        </div>

        {selectedRevisionRecommendation ? (
          <div className="selected-context">
            Current status: {selectedRevisionRecommendation.status}
          </div>
        ) : null}

        <button className="primary-button" onClick={saveRevision} disabled={revisionMutation.isPending}>
          {revisionMutation.isPending ? "Saving Revision..." : "Save Revision"}
        </button>
      </div>

      {message ? <div className="dictation-message">{message}</div> : null}

      <div className="content-section">
        <h2>Managed Recommendations</h2>
        <div className="table-card wide-table">
          {recommendations.length === 0 ? (
            <p className="empty-state">No recommendations yet.</p>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>Recommendation</th>
                  <th>Category</th>
                  <th>Priority</th>
                  <th>Status</th>
                  <th>Model</th>
                  <th>Created</th>
                  <th>Complete</th>
                </tr>
              </thead>
              <tbody>
                {recommendations.map((item) => (
                  <tr key={item.id}>
                    <td>
                      <strong>{item.title}</strong>
                      <div className="small-note">{truncate(item.recommendation_text, 420)}</div>
                      {item.expected_benefit ? (
                        <div className="small-note">Benefit: {truncate(item.expected_benefit, 260)}</div>
                      ) : null}
                    </td>
                    <td>{item.category ?? "-"}</td>
                    <td>{item.priority ?? "-"}</td>
                    <td><StatusBadge status={item.status} /></td>
                    <td>{item.model_name ?? "-"}</td>
                    <td>{formatDateTime(item.created_at)}</td>
                    <td>
                      {item.status.toLowerCase() === "completed" ? (
                        <span className="small-note">Completed</span>
                      ) : (
                        <button
                          className="secondary-button"
                          onClick={() => markCompletedMutation.mutate(item.id)}
                          disabled={markCompletedMutation.isPending}
                        >
                          Mark Complete
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      <div className="content-section">
        <h2>Recommendation Action Items</h2>
        <div className="table-card wide-table">
          {actionItems.length === 0 ? (
            <p className="empty-state">No recommendation action items yet.</p>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>Action</th>
                  <th>Recommendation</th>
                  <th>Owner</th>
                  <th>Priority</th>
                  <th>Status</th>
                  <th>Due Date</th>
                  <th>Completed</th>
                  <th>Update</th>
                </tr>
              </thead>
              <tbody>
                {actionItems.map((item) => (
                  <tr key={item.id}>
                    <td>
                      <strong>{item.action_title}</strong>
                      {item.action_description ? (
                        <div className="small-note">{truncate(item.action_description, 260)}</div>
                      ) : null}
                      {item.completion_notes ? (
                        <div className="small-note">Completion: {truncate(item.completion_notes, 220)}</div>
                      ) : null}
                    </td>
                    <td>{getRecommendationLabel(recommendations, item.recommendation_id)}</td>
                    <td>{item.owner_name ?? "-"}</td>
                    <td>{item.priority ?? "-"}</td>
                    <td><StatusBadge status={item.status} /></td>
                    <td>{item.due_date ?? "-"}</td>
                    <td>{formatDateTime(item.completed_at)}</td>
                    <td>
                      {item.status.toLowerCase() === "completed" ? (
                        <span className="small-note">Closed</span>
                      ) : (
                        <button
                          className="secondary-button"
                          onClick={() => completeActionItemMutation.mutate(item.id)}
                          disabled={completeActionItemMutation.isPending}
                        >
                          Mark Complete
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      <div className="content-section">
        <h2>Recommendation Decisions</h2>
        <div className="table-card wide-table">
          {decisions.length === 0 ? (
            <p className="empty-state">No recommendation decisions yet.</p>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>Recommendation</th>
                  <th>Decision</th>
                  <th>Status Change</th>
                  <th>Notes</th>
                  <th>Decided By</th>
                  <th>Decided At</th>
                </tr>
              </thead>
              <tbody>
                {decisions.map((item) => (
                  <tr key={item.id}>
                    <td>{getRecommendationLabel(recommendations, item.recommendation_id)}</td>
                    <td>{item.decision}</td>
                    <td>
                      {item.previous_status ?? "-"} → {item.new_status}
                    </td>
                    <td>{truncate(item.decision_notes, 260) || "-"}</td>
                    <td>{item.decided_by ?? "-"}</td>
                    <td>{formatDateTime(item.decided_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      <div className="content-section">
        <h2>Recommendation Revisions</h2>
        <div className="table-card wide-table">
          {revisions.length === 0 ? (
            <p className="empty-state">No recommendation revisions yet.</p>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>Recommendation</th>
                  <th>Previous Title</th>
                  <th>Revised Title</th>
                  <th>Revision Notes</th>
                  <th>Revised By</th>
                  <th>Revised At</th>
                </tr>
              </thead>
              <tbody>
                {revisions.map((item) => (
                  <tr key={item.id}>
                    <td>{getRecommendationLabel(recommendations, item.recommendation_id)}</td>
                    <td>{truncate(item.previous_title, 220) || "-"}</td>
                    <td>{truncate(item.revised_title, 220) || "-"}</td>
                    <td>{truncate(item.revision_notes, 260) || "-"}</td>
                    <td>{item.revised_by ?? "-"}</td>
                    <td>{formatDateTime(item.revised_at)}</td>
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