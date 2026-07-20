import { useMemo, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import {
  createDeliverableReviewActionItem,
  createDeliverableReviewWorkflow,
  recordDeliverableReviewDecision,
  updateDeliverableReviewActionItem,
} from "./api";
import type {
  Deliverable,
  DeliverableReviewActionItem,
  DeliverableReviewWorkflow,
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

function truncate(value: string | null, maxLength = 220) {
  if (!value) {
    return "";
  }

  if (value.length <= maxLength) {
    return value;
  }

  return `${value.slice(0, maxLength - 3)}...`;
}

function yesNo(value: boolean) {
  return value ? "Yes" : "No";
}

function StatusBadge({ status }: { status: string }) {
  return <span className="status-badge">{status}</span>;
}

function findDeliverableName(deliverables: Deliverable[], deliverableId: string) {
  const deliverable = deliverables.find((item) => item.id === deliverableId);

  if (!deliverable) {
    return deliverableId;
  }

  return `${deliverable.external_id ? `${deliverable.external_id} - ` : ""}${deliverable.name}`;
}

export function Mvp11ReviewWorkflowPanel({
  deliverables,
  reviewWorkflows,
  reviewActionItems,
}: {
  deliverables: Deliverable[];
  reviewWorkflows: DeliverableReviewWorkflow[];
  reviewActionItems: DeliverableReviewActionItem[];
}) {
  const queryClient = useQueryClient();

  const [deliverableId, setDeliverableId] = useState("");
  const [workflowTitle, setWorkflowTitle] = useState("Initial deliverable review");
  const [workflowStatus, setWorkflowStatus] = useState("Submitted for Review");
  const [reviewType, setReviewType] = useState("Internal Review");
  const [submittedBy, setSubmittedBy] = useState("Giridhar Krishnagiri");
  const [reviewerName, setReviewerName] = useState("");
  const [reviewerRole, setReviewerRole] = useState("");
  const [reviewDueDate, setReviewDueDate] = useState(todayIsoDate());
  const [reviewNotes, setReviewNotes] = useState("");

  const [decisionWorkflowId, setDecisionWorkflowId] = useState("");
  const [decision, setDecision] = useState("Approved");
  const [decisionBy, setDecisionBy] = useState("Giridhar Krishnagiri");
  const [decisionReviewNotes, setDecisionReviewNotes] = useState("");
  const [approvalNotes, setApprovalNotes] = useState("");
  const [reworkNotes, setReworkNotes] = useState("");

  const [actionWorkflowId, setActionWorkflowId] = useState("");
  const [actionTitle, setActionTitle] = useState("");
  const [actionDescription, setActionDescription] = useState("");
  const [actionOwner, setActionOwner] = useState("Giridhar Krishnagiri");
  const [actionPriority, setActionPriority] = useState("Medium");
  const [actionDueDate, setActionDueDate] = useState(todayIsoDate());

  const [message, setMessage] = useState("");

  const currentWorkflowOptions = useMemo(() => {
    return reviewWorkflows.filter((item) => item.is_current);
  }, [reviewWorkflows]);

  const openActionItems = reviewActionItems.filter((item) => item.status.toLowerCase() !== "completed");
  const completedActionItems = reviewActionItems.filter((item) => item.status.toLowerCase() === "completed");
  const approvedWorkflows = reviewWorkflows.filter((item) => item.workflow_status.toLowerCase() === "approved");
  const reworkWorkflows = reviewWorkflows.filter((item) => item.workflow_status.toLowerCase() === "rework required");

  const createWorkflowMutation = useMutation({
    mutationFn: () =>
      createDeliverableReviewWorkflow({
        deliverable_id: deliverableId,
        workflow_title: workflowTitle,
        workflow_status: workflowStatus,
        review_type: reviewType,
        submitted_by: submittedBy,
        reviewer_name: reviewerName || null,
        reviewer_role: reviewerRole || null,
        review_due_date: reviewDueDate || null,
        review_notes: reviewNotes || null,
        created_by: submittedBy,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["deliverable-review-workflows"] });
      queryClient.invalidateQueries({ queryKey: ["deliverables"] });
      setMessage("Deliverable submitted for review successfully.");
    },
    onError: (error) => {
      setMessage(error instanceof Error ? error.message : "Failed to create review workflow.");
    },
  });

  const decisionMutation = useMutation({
    mutationFn: () =>
      recordDeliverableReviewDecision({
        workflow_id: decisionWorkflowId,
        decision,
        decision_by: decisionBy,
        review_notes: decisionReviewNotes || null,
        approval_notes: approvalNotes || null,
        rework_notes: reworkNotes || null,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["deliverable-review-workflows"] });
      queryClient.invalidateQueries({ queryKey: ["deliverables"] });
      setMessage("Review decision recorded successfully.");
    },
    onError: (error) => {
      setMessage(error instanceof Error ? error.message : "Failed to record review decision.");
    },
  });

  const actionItemMutation = useMutation({
    mutationFn: () =>
      createDeliverableReviewActionItem({
        review_workflow_id: actionWorkflowId,
        action_title: actionTitle,
        action_description: actionDescription || null,
        owner_name: actionOwner || null,
        priority: actionPriority,
        status: "Open",
        due_date: actionDueDate || null,
        created_by: actionOwner || "Giridhar Krishnagiri",
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["deliverable-review-action-items"] });
      setActionTitle("");
      setActionDescription("");
      setMessage("Review action item created successfully.");
    },
    onError: (error) => {
      setMessage(error instanceof Error ? error.message : "Failed to create review action item.");
    },
  });

  const completeActionItemMutation = useMutation({
    mutationFn: (actionItemId: string) =>
      updateDeliverableReviewActionItem({
        action_item_id: actionItemId,
        status: "Completed",
        completion_notes: "Completed from review workflow UI.",
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["deliverable-review-action-items"] });
      setMessage("Review action item marked completed.");
    },
    onError: (error) => {
      setMessage(error instanceof Error ? error.message : "Failed to update review action item.");
    },
  });

  function submitForReview() {
    if (!deliverableId) {
      setMessage("Select a deliverable before submitting for review.");
      return;
    }

    if (!workflowTitle.trim()) {
      setMessage("Workflow title is required.");
      return;
    }

    setMessage("");
    createWorkflowMutation.mutate();
  }

  function recordDecision() {
    if (!decisionWorkflowId) {
      setMessage("Select a review workflow before recording a decision.");
      return;
    }

    setMessage("");
    decisionMutation.mutate();
  }

  function createActionItem() {
    if (!actionWorkflowId) {
      setMessage("Select a review workflow before creating an action item.");
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
    <section id="review-workflow" className="content-section">
      <div className="section-header">
        <div>
          <h2>Deliverable Review Workflow</h2>
          <p>
            Submit deliverables for review, record approval or rework decisions, and
            track review action items until closure.
          </p>
        </div>
      </div>

      <div className="report-summary-grid">
        <div className="report-card">
          <span>Review Workflows</span>
          <strong>{reviewWorkflows.length}</strong>
          <p>Total workflow records</p>
        </div>
        <div className="report-card">
          <span>Approved</span>
          <strong>{approvedWorkflows.length}</strong>
          <p>Approved review workflows</p>
        </div>
        <div className="report-card">
          <span>Rework Required</span>
          <strong>{reworkWorkflows.length}</strong>
          <p>Workflows requiring changes</p>
        </div>
        <div className="report-card">
          <span>Open Action Items</span>
          <strong>{openActionItems.length}</strong>
          <p>Pending review actions</p>
        </div>
        <div className="report-card">
          <span>Completed Actions</span>
          <strong>{completedActionItems.length}</strong>
          <p>Closed review actions</p>
        </div>
      </div>

      <div className="timesheet-grid">
        <div className="timesheet-card">
          <h3>Submit Deliverable for Review</h3>
          <p>Create a formal review workflow and update the deliverable review status.</p>

          <div className="timesheet-form-grid">
            <label className="timesheet-full-width">
              Deliverable
              <select value={deliverableId} onChange={(event) => setDeliverableId(event.target.value)}>
                <option value="">Select deliverable</option>
                {deliverables.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.external_id ? `${item.external_id} - ` : ""}
                    {item.name}
                  </option>
                ))}
              </select>
            </label>

            <label>
              Workflow Title
              <input value={workflowTitle} onChange={(event) => setWorkflowTitle(event.target.value)} />
            </label>

            <label>
              Workflow Status
              <select value={workflowStatus} onChange={(event) => setWorkflowStatus(event.target.value)}>
                <option value="Submitted for Review">Submitted for Review</option>
                <option value="In Review">In Review</option>
                <option value="Rework Required">Rework Required</option>
                <option value="Approved">Approved</option>
              </select>
            </label>

            <label>
              Review Type
              <select value={reviewType} onChange={(event) => setReviewType(event.target.value)}>
                <option value="Internal Review">Internal Review</option>
                <option value="Peer Review">Peer Review</option>
                <option value="Delivery Lead Review">Delivery Lead Review</option>
                <option value="Client Review">Client Review</option>
                <option value="Final Approval">Final Approval</option>
              </select>
            </label>

            <label>
              Submitted By
              <input value={submittedBy} onChange={(event) => setSubmittedBy(event.target.value)} />
            </label>

            <label>
              Reviewer Name
              <input value={reviewerName} onChange={(event) => setReviewerName(event.target.value)} />
            </label>

            <label>
              Reviewer Role
              <input value={reviewerRole} onChange={(event) => setReviewerRole(event.target.value)} />
            </label>

            <label>
              Review Due Date
              <input type="date" value={reviewDueDate} onChange={(event) => setReviewDueDate(event.target.value)} />
            </label>

            <label className="timesheet-full-width">
              Review Notes
              <textarea value={reviewNotes} onChange={(event) => setReviewNotes(event.target.value)} />
            </label>
          </div>

          <button className="primary-button" onClick={submitForReview} disabled={createWorkflowMutation.isPending}>
            {createWorkflowMutation.isPending ? "Submitting..." : "Submit for Review"}
          </button>
        </div>

        <div className="timesheet-card">
          <h3>Record Review Decision</h3>
          <p>Capture approval, rework, or rejection decision for a review workflow.</p>

          <div className="timesheet-form-grid">
            <label className="timesheet-full-width">
              Review Workflow
              <select value={decisionWorkflowId} onChange={(event) => setDecisionWorkflowId(event.target.value)}>
                <option value="">Select workflow</option>
                {reviewWorkflows.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.workflow_title} | {findDeliverableName(deliverables, item.deliverable_id)}
                  </option>
                ))}
              </select>
            </label>

            <label>
              Decision
              <select value={decision} onChange={(event) => setDecision(event.target.value)}>
                <option value="Approved">Approved</option>
                <option value="Rework Required">Rework Required</option>
                <option value="Rejected">Rejected</option>
                <option value="In Review">In Review</option>
              </select>
            </label>

            <label>
              Decision By
              <input value={decisionBy} onChange={(event) => setDecisionBy(event.target.value)} />
            </label>

            <label className="timesheet-full-width">
              Review Notes
              <textarea value={decisionReviewNotes} onChange={(event) => setDecisionReviewNotes(event.target.value)} />
            </label>

            <label className="timesheet-full-width">
              Approval Notes
              <textarea value={approvalNotes} onChange={(event) => setApprovalNotes(event.target.value)} />
            </label>

            <label className="timesheet-full-width">
              Rework Notes
              <textarea value={reworkNotes} onChange={(event) => setReworkNotes(event.target.value)} />
            </label>
          </div>

          <button className="primary-button" onClick={recordDecision} disabled={decisionMutation.isPending}>
            {decisionMutation.isPending ? "Recording..." : "Record Decision"}
          </button>
        </div>
      </div>

      <div className="timesheet-grid content-section">
        <div className="timesheet-card">
          <h3>Create Review Action Item</h3>
          <p>Add action items for gaps, rework, corrections, or approval follow-ups.</p>

          <div className="timesheet-form-grid">
            <label className="timesheet-full-width">
              Review Workflow
              <select value={actionWorkflowId} onChange={(event) => setActionWorkflowId(event.target.value)}>
                <option value="">Select workflow</option>
                {currentWorkflowOptions.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.workflow_title} | {findDeliverableName(deliverables, item.deliverable_id)}
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

        <div className="timesheet-card">
          <h3>Workflow Guidance</h3>
          <p>
            Suggested lifecycle:
          </p>
          <div className="small-note">
            Draft → Submitted for Review → In Review → Rework Required or Approved.
          </div>
          <div className="small-note">
            If rework is required, create action items, complete the action items, then record a new approval decision.
          </div>
          <div className="small-note">
            Approval automatically updates the deliverable review status and approval date.
          </div>
        </div>
      </div>

      {message ? <div className="dictation-message">{message}</div> : null}

      <div className="content-section">
        <h2>Review Workflows</h2>
        <div className="table-card wide-table">
          {reviewWorkflows.length === 0 ? (
            <p className="empty-state">No review workflows yet.</p>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>Workflow</th>
                  <th>Deliverable</th>
                  <th>Status</th>
                  <th>Reviewer</th>
                  <th>Due Date</th>
                  <th>Decision</th>
                  <th>Current</th>
                  <th>Submitted</th>
                </tr>
              </thead>
              <tbody>
                {reviewWorkflows.map((item) => (
                  <tr key={item.id}>
                    <td>
                      <strong>{item.workflow_title}</strong>
                      <div className="small-note">{item.review_type}</div>
                      {item.review_notes ? <div className="small-note">Notes: {truncate(item.review_notes, 220)}</div> : null}
                      {item.rework_notes ? <div className="small-note">Rework: {truncate(item.rework_notes, 220)}</div> : null}
                      {item.approval_notes ? <div className="small-note">Approval: {truncate(item.approval_notes, 220)}</div> : null}
                    </td>
                    <td>{findDeliverableName(deliverables, item.deliverable_id)}</td>
                    <td><StatusBadge status={item.workflow_status} /></td>
                    <td>
                      {item.reviewer_name ?? "-"}
                      {item.reviewer_role ? <div className="small-note">{item.reviewer_role}</div> : null}
                    </td>
                    <td>{item.review_due_date ?? "-"}</td>
                    <td>
                      {item.review_decision ?? "-"}
                      {item.decision_by ? <div className="small-note">By: {item.decision_by}</div> : null}
                      {item.decision_at ? <div className="small-note">{formatDateTime(item.decision_at)}</div> : null}
                    </td>
                    <td>{yesNo(item.is_current)}</td>
                    <td>{formatDateTime(item.submitted_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      <div className="content-section">
        <h2>Review Action Items</h2>
        <div className="table-card wide-table">
          {reviewActionItems.length === 0 ? (
            <p className="empty-state">No review action items yet.</p>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>Action</th>
                  <th>Deliverable</th>
                  <th>Owner</th>
                  <th>Priority</th>
                  <th>Status</th>
                  <th>Due Date</th>
                  <th>Completed</th>
                  <th>Update</th>
                </tr>
              </thead>
              <tbody>
                {reviewActionItems.map((item) => (
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
                    <td>{findDeliverableName(deliverables, item.deliverable_id)}</td>
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
    </section>
  );
}