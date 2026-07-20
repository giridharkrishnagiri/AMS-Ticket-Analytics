import { useMemo, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { generateDeliverableReview, generateLlmRecommendation } from "./api";
import type {
  AnalysisOutput,
  Deliverable,
  DeliverableReview,
  Finding,
  LlmRecommendation,
  Subtask,
  Task,
} from "./types";

type RecommendationTargetType =
  | "general"
  | "deliverable"
  | "task"
  | "subtask"
  | "finding"
  | "analysis_output";

type TargetOption = {
  id: string;
  label: string;
};

function truncate(value: string, maxLength = 180) {
  if (value.length <= maxLength) {
    return value;
  }

  return `${value.slice(0, maxLength - 3)}...`;
}

function formatDateTime(value: string) {
  return value.replace("T", " ").slice(0, 19);
}

function StatusBadge({ status }: { status: string }) {
  return <span className="status-badge">{status}</span>;
}

function getLinkedToLabel(item: LlmRecommendation) {
  if (item.analysis_output_id) {
    return "Analysis Output";
  }

  if (item.finding_id) {
    return "Finding";
  }

  if (item.subtask_id) {
    return "Sub-task";
  }

  if (item.task_id) {
    return "Task";
  }

  if (item.deliverable_id) {
    return "Deliverable";
  }

  return "General";
}

export function Mvp8LlmPanel({
  deliverables,
  tasks,
  subtasks,
  findings,
  analysisOutputs,
  recommendations,
  deliverableReviews,
}: {
  deliverables: Deliverable[];
  tasks: Task[];
  subtasks: Subtask[];
  findings: Finding[];
  analysisOutputs: AnalysisOutput[];
  recommendations: LlmRecommendation[];
  deliverableReviews: DeliverableReview[];
}) {
  const queryClient = useQueryClient();

  const [recommendationTargetType, setRecommendationTargetType] =
    useState<RecommendationTargetType>("general");
  const [recommendationTargetId, setRecommendationTargetId] = useState("");
  const [recommendationType, setRecommendationType] = useState("ASM Improvement Recommendation");
  const [focusArea, setFocusArea] = useState(
    "Application support operating model, automation, demand, capacity, risk, and delivery improvement",
  );
  const [reviewDeliverableId, setReviewDeliverableId] = useState("");
  const [createdBy, setCreatedBy] = useState("Giridhar Krishnagiri");
  const [message, setMessage] = useState("");

  const recommendationTargetOptions = useMemo<TargetOption[]>(() => {
    if (recommendationTargetType === "deliverable") {
      return deliverables.map((item) => ({
        id: item.id,
        label: `${item.external_id ? `${item.external_id} - ` : ""}${item.name}`,
      }));
    }

    if (recommendationTargetType === "task") {
      return tasks.map((item) => ({
        id: item.id,
        label: `${item.external_id ? `${item.external_id} - ` : ""}${item.title}`,
      }));
    }

    if (recommendationTargetType === "subtask") {
      return subtasks.map((item) => ({
        id: item.id,
        label: `${item.external_id ? `${item.external_id} - ` : ""}${item.title}`,
      }));
    }

    if (recommendationTargetType === "finding") {
      return findings.map((item) => ({
        id: item.id,
        label: item.title,
      }));
    }

    if (recommendationTargetType === "analysis_output") {
      return analysisOutputs.map((item) => ({
        id: item.id,
        label: item.analysis_title,
      }));
    }

    return [];
  }, [analysisOutputs, deliverables, findings, recommendationTargetType, subtasks, tasks]);

  const generateRecommendationMutation = useMutation({
    mutationFn: () =>
      generateLlmRecommendation({
        recommendation_type: recommendationType,
        focus_area: focusArea,
        created_by: createdBy,
        deliverable_id:
          recommendationTargetType === "deliverable" ? recommendationTargetId : null,
        task_id: recommendationTargetType === "task" ? recommendationTargetId : null,
        subtask_id: recommendationTargetType === "subtask" ? recommendationTargetId : null,
        finding_id: recommendationTargetType === "finding" ? recommendationTargetId : null,
        analysis_output_id:
          recommendationTargetType === "analysis_output" ? recommendationTargetId : null,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["llm-recommendations"] });
      setMessage("LLM recommendation generated and saved successfully.");
    },
    onError: (error) => {
      setMessage(error instanceof Error ? error.message : "Recommendation generation failed.");
    },
  });

  const generateReviewMutation = useMutation({
    mutationFn: () =>
      generateDeliverableReview({
        deliverable_id: reviewDeliverableId,
        review_type: "LLM Deliverable Review",
        created_by: createdBy,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["deliverable-reviews"] });
      setMessage("Deliverable review generated and saved successfully.");
    },
    onError: (error) => {
      setMessage(error instanceof Error ? error.message : "Deliverable review generation failed.");
    },
  });

  function handleGenerateRecommendation() {
    if (recommendationTargetType !== "general" && !recommendationTargetId) {
      setMessage("Select a target record before generating the recommendation.");
      return;
    }

    setMessage("");
    generateRecommendationMutation.mutate();
  }

  function handleGenerateReview() {
    if (!reviewDeliverableId) {
      setMessage("Select a deliverable before generating a review.");
      return;
    }

    setMessage("");
    generateReviewMutation.mutate();
  }

  return (
    <section id="llm-recommendations" className="content-section">
      <div className="section-header">
        <div>
          <h2>LLM Recommendations and Deliverable Reviews</h2>
          <p>
            Generate traced LLM recommendations and deliverable reviews. Each backend LLM
            call is wrapped in an OpenAI trace workflow for monitoring.
          </p>
        </div>
      </div>

      <div className="llm-panel-grid">
        <div className="llm-generator-card">
          <h3>Generate Recommendation</h3>
          <p>
            Generate a recommendation for a specific work item, or keep it general for
            overall ASM engagement improvement ideas.
          </p>

          <div className="llm-form-grid">
            <label>
              Target Type
              <select
                value={recommendationTargetType}
                onChange={(event) => {
                  setRecommendationTargetType(event.target.value as RecommendationTargetType);
                  setRecommendationTargetId("");
                }}
              >
                <option value="general">General</option>
                <option value="deliverable">Deliverable</option>
                <option value="task">Task</option>
                <option value="subtask">Sub-task</option>
                <option value="finding">Finding</option>
                <option value="analysis_output">Analysis Output</option>
              </select>
            </label>

            <label>
              Target Record
              <select
                value={recommendationTargetId}
                onChange={(event) => setRecommendationTargetId(event.target.value)}
                disabled={recommendationTargetType === "general"}
              >
                <option value="">
                  {recommendationTargetType === "general" ? "No target needed" : "Select record"}
                </option>
                {recommendationTargetOptions.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.label}
                  </option>
                ))}
              </select>
            </label>

            <label>
              Recommendation Type
              <input
                value={recommendationType}
                onChange={(event) => setRecommendationType(event.target.value)}
              />
            </label>

            <label>
              Created By
              <input value={createdBy} onChange={(event) => setCreatedBy(event.target.value)} />
            </label>

            <label className="llm-full-width">
              Focus Area
              <textarea value={focusArea} onChange={(event) => setFocusArea(event.target.value)} />
            </label>
          </div>

          <button
            className="primary-button"
            onClick={handleGenerateRecommendation}
            disabled={generateRecommendationMutation.isPending}
          >
            {generateRecommendationMutation.isPending
              ? "Generating Recommendation..."
              : "Generate Recommendation"}
          </button>
        </div>

        <div className="llm-generator-card">
          <h3>Generate Deliverable Review</h3>
          <p>
            Select a deliverable and generate a quality review covering strengths, gaps,
            risks, readiness, and recommended actions.
          </p>

          <div className="llm-form-grid">
            <label className="llm-full-width">
              Deliverable
              <select
                value={reviewDeliverableId}
                onChange={(event) => setReviewDeliverableId(event.target.value)}
              >
                <option value="">Select deliverable</option>
                {deliverables.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.external_id ? `${item.external_id} - ` : ""}
                    {item.name}
                  </option>
                ))}
              </select>
            </label>

            <label className="llm-full-width">
              Created By
              <input value={createdBy} onChange={(event) => setCreatedBy(event.target.value)} />
            </label>
          </div>

          <button
            className="primary-button"
            onClick={handleGenerateReview}
            disabled={generateReviewMutation.isPending}
          >
            {generateReviewMutation.isPending
              ? "Generating Review..."
              : "Generate Deliverable Review"}
          </button>
        </div>
      </div>

      {message ? <div className="dictation-message">{message}</div> : null}

      <div className="content-section">
        <h2>LLM Recommendations</h2>
        <div className="table-card wide-table">
          {recommendations.length === 0 ? (
            <p className="empty-state">No LLM recommendations yet.</p>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>Recommendation</th>
                  <th>Category</th>
                  <th>Priority</th>
                  <th>Status</th>
                  <th>Linked To</th>
                  <th>Model</th>
                  <th>Trace Workflow</th>
                  <th>Created</th>
                </tr>
              </thead>
              <tbody>
                {recommendations.map((item) => (
                  <tr key={item.id}>
                    <td>
                      <strong>{item.title}</strong>
                      <div className="small-note">{truncate(item.recommendation_text, 450)}</div>
                      {item.rationale ? (
                        <div className="small-note">Rationale: {truncate(item.rationale, 300)}</div>
                      ) : null}
                      {item.expected_benefit ? (
                        <div className="small-note">
                          Benefit: {truncate(item.expected_benefit, 300)}
                        </div>
                      ) : null}
                    </td>
                    <td>{item.category ?? "-"}</td>
                    <td>{item.priority ?? "-"}</td>
                    <td>
                      <StatusBadge status={item.status} />
                    </td>
                    <td>{getLinkedToLabel(item)}</td>
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

      <div className="content-section">
        <h2>Deliverable Reviews</h2>
        <div className="table-card wide-table">
          {deliverableReviews.length === 0 ? (
            <p className="empty-state">No deliverable reviews yet.</p>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>Review</th>
                  <th>Status</th>
                  <th>Readiness</th>
                  <th>Model</th>
                  <th>Trace Workflow</th>
                  <th>Created</th>
                </tr>
              </thead>
              <tbody>
                {deliverableReviews.map((item) => (
                  <tr key={item.id}>
                    <td>
                      <strong>{item.review_title}</strong>
                      <div className="small-note">{truncate(item.review_summary, 450)}</div>
                      {item.strengths ? (
                        <div className="small-note">Strengths: {truncate(item.strengths, 300)}</div>
                      ) : null}
                      {item.gaps ? (
                        <div className="small-note">Gaps: {truncate(item.gaps, 300)}</div>
                      ) : null}
                      {item.risks ? (
                        <div className="small-note">Risks: {truncate(item.risks, 300)}</div>
                      ) : null}
                      {item.recommended_actions ? (
                        <div className="small-note">
                          Actions: {truncate(item.recommended_actions, 300)}
                        </div>
                      ) : null}
                    </td>
                    <td>
                      <StatusBadge status={item.review_status} />
                    </td>
                    <td>{item.readiness_assessment ?? "-"}</td>
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