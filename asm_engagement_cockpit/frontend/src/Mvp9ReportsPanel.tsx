import type {
  AnalysisOutput,
  DataPoint,
  Deliverable,
  DeliverableReview,
  Engagement,
  EvidenceItem,
  Finding,
  LlmRecommendation,
  StakeholderQuestion,
  Subtask,
  Task,
  UploadedFile,
  Workstream,
} from "./types";

type ReportRow = Record<string, string | number | boolean | null | undefined>;

function safeValue(value: string | number | boolean | null | undefined) {
  if (value === null || value === undefined) {
    return "";
  }

  return String(value);
}

function escapeCsv(value: string | number | boolean | null | undefined) {
  const text = safeValue(value);

  if (text.includes(",") || text.includes('"') || text.includes("\n") || text.includes("\r")) {
    return `"${text.replaceAll('"', '""')}"`;
  }

  return text;
}

function rowsToCsv(rows: ReportRow[]) {
  if (rows.length === 0) {
    return "No data available\n";
  }

  const headers = Object.keys(rows[0]);
  const headerLine = headers.map(escapeCsv).join(",");
  const dataLines = rows.map((row) => headers.map((header) => escapeCsv(row[header])).join(","));

  return [headerLine, ...dataLines].join("\n");
}

function downloadCsv(filename: string, rows: ReportRow[]) {
  const csv = rowsToCsv(rows);
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);

  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();

  URL.revokeObjectURL(url);
}

function formatDateTime(value: string | null | undefined) {
  if (!value) {
    return "";
  }

  return value.replace("T", " ").slice(0, 19);
}

function getStatusCounts(items: Array<{ status?: string | null }>) {
  const counts = new Map<string, number>();

  for (const item of items) {
    const status = item.status || "Unknown";
    counts.set(status, (counts.get(status) ?? 0) + 1);
  }

  return Array.from(counts.entries())
    .map(([status, count]) => ({ status, count }))
    .sort((a, b) => a.status.localeCompare(b.status));
}

function getResponseStatusCounts(items: StakeholderQuestion[]) {
  const counts = new Map<string, number>();

  for (const item of items) {
    const status = item.response_status || "Unknown";
    counts.set(status, (counts.get(status) ?? 0) + 1);
  }

  return Array.from(counts.entries())
    .map(([status, count]) => ({ status, count }))
    .sort((a, b) => a.status.localeCompare(b.status));
}

function getReviewStatusCounts(items: DeliverableReview[]) {
  const counts = new Map<string, number>();

  for (const item of items) {
    const status = item.review_status || "Unknown";
    counts.set(status, (counts.get(status) ?? 0) + 1);
  }

  return Array.from(counts.entries())
    .map(([status, count]) => ({ status, count }))
    .sort((a, b) => a.status.localeCompare(b.status));
}

function completionCount(items: Array<{ status?: string | null }>) {
  return items.filter((item) => (item.status || "").toLowerCase() === "completed").length;
}

function percent(part: number, total: number) {
  if (total === 0) {
    return "0%";
  }

  return `${Math.round((part / total) * 100)}%`;
}

export function Mvp9ReportsPanel({
  engagements,
  workstreams,
  deliverables,
  tasks,
  subtasks,
  dataPoints,
  stakeholderQuestions,
  findings,
  analysisOutputs,
  evidenceItems,
  uploadedFiles,
  llmRecommendations,
  deliverableReviews,
}: {
  engagements: Engagement[];
  workstreams: Workstream[];
  deliverables: Deliverable[];
  tasks: Task[];
  subtasks: Subtask[];
  dataPoints: DataPoint[];
  stakeholderQuestions: StakeholderQuestion[];
  findings: Finding[];
  analysisOutputs: AnalysisOutput[];
  evidenceItems: EvidenceItem[];
  uploadedFiles: UploadedFile[];
  llmRecommendations: LlmRecommendation[];
  deliverableReviews: DeliverableReview[];
}) {
  const engagementRows: ReportRow[] = engagements.map((item) => ({
    id: item.id,
    name: item.name,
    client_name: item.client_name,
    status: item.status,
    progress_percent: item.progress_percent,
    start_date: item.start_date,
    target_end_date: item.target_end_date,
    revised_end_date: item.revised_end_date,
    actual_end_date: item.actual_end_date,
    created_at: formatDateTime(item.created_at),
    updated_at: formatDateTime(item.updated_at),
  }));

  const workstreamRows: ReportRow[] = workstreams.map((item) => ({
    id: item.id,
    engagement_id: item.engagement_id,
    external_id: item.external_id,
    name: item.name,
    status: item.status,
    progress_percent: item.progress_percent,
    start_date: item.start_date,
    target_completion_date: item.target_completion_date,
    revised_completion_date: item.revised_completion_date,
    actual_completion_date: item.actual_completion_date,
    created_at: formatDateTime(item.created_at),
    updated_at: formatDateTime(item.updated_at),
  }));

  const deliverableRows: ReportRow[] = deliverables.map((item) => ({
    id: item.id,
    workstream_id: item.workstream_id,
    external_id: item.external_id,
    name: item.name,
    deliverable_type: item.deliverable_type,
    status: item.status,
    review_status: item.review_status,
    progress_percent: item.progress_percent,
    target_completion_date: item.target_completion_date,
    revised_completion_date: item.revised_completion_date,
    actual_completion_date: item.actual_completion_date,
    submission_date: item.submission_date,
    approval_date: item.approval_date,
    created_at: formatDateTime(item.created_at),
    updated_at: formatDateTime(item.updated_at),
  }));

  const taskRows: ReportRow[] = tasks.map((item) => ({
    id: item.id,
    deliverable_id: item.deliverable_id,
    external_id: item.external_id,
    title: item.title,
    priority: item.priority,
    status: item.status,
    progress_percent: item.progress_percent,
    target_completion_date: item.target_completion_date,
    revised_completion_date: item.revised_completion_date,
    actual_completion_date: item.actual_completion_date,
    created_at: formatDateTime(item.created_at),
    updated_at: formatDateTime(item.updated_at),
  }));

  const subtaskRows: ReportRow[] = subtasks.map((item) => ({
    id: item.id,
    task_id: item.task_id,
    external_id: item.external_id,
    title: item.title,
    priority: item.priority,
    status: item.status,
    target_completion_date: item.target_completion_date,
    revised_completion_date: item.revised_completion_date,
    actual_completion_date: item.actual_completion_date,
    created_at: formatDateTime(item.created_at),
    updated_at: formatDateTime(item.updated_at),
  }));

  const dataPointRows: ReportRow[] = dataPoints.map((item) => ({
    id: item.id,
    subtask_id: item.subtask_id,
    topic: item.topic,
    source: item.source,
    status: item.status,
    requested_date: item.requested_date,
    expected_received_date: item.expected_received_date,
    actual_received_date: item.actual_received_date,
    data_quality: item.data_quality,
    used_in_finding: item.used_in_finding,
    created_at: formatDateTime(item.created_at),
    updated_at: formatDateTime(item.updated_at),
  }));

  const stakeholderQuestionRows: ReportRow[] = stakeholderQuestions.map((item) => ({
    id: item.id,
    subtask_id: item.subtask_id,
    question_text: item.question_text,
    question_category: item.question_category,
    stakeholder_name: item.stakeholder_name,
    stakeholder_role: item.stakeholder_role,
    stakeholder_email: item.stakeholder_email,
    response_status: item.response_status,
    raised_date: item.raised_date,
    expected_response_date: item.expected_response_date,
    actual_response_date: item.actual_response_date,
    follow_up_required: item.follow_up_required,
    confidence_level: item.confidence_level,
    used_in_finding: item.used_in_finding,
    created_at: formatDateTime(item.created_at),
    updated_at: formatDateTime(item.updated_at),
  }));

  const findingRows: ReportRow[] = findings.map((item) => ({
    id: item.id,
    subtask_id: item.subtask_id,
    task_id: item.task_id,
    deliverable_id: item.deliverable_id,
    title: item.title,
    finding_type: item.finding_type,
    severity: item.severity,
    status: item.status,
    confidence_level: item.confidence_level,
    is_validated: item.is_validated,
    validated_by: item.validated_by,
    validated_date: item.validated_date,
    finding_text: item.finding_text,
    business_impact: item.business_impact,
    recommendation: item.recommendation,
    created_at: formatDateTime(item.created_at),
    updated_at: formatDateTime(item.updated_at),
  }));

  const analysisRows: ReportRow[] = analysisOutputs.map((item) => ({
    id: item.id,
    subtask_id: item.subtask_id,
    task_id: item.task_id,
    deliverable_id: item.deliverable_id,
    analysis_title: item.analysis_title,
    analysis_type: item.analysis_type,
    status: item.status,
    confidence_level: item.confidence_level,
    reviewed_by: item.reviewed_by,
    reviewed_date: item.reviewed_date,
    analysis_text: item.analysis_text,
    methodology: item.methodology,
    assumptions: item.assumptions,
    limitations: item.limitations,
    created_at: formatDateTime(item.created_at),
    updated_at: formatDateTime(item.updated_at),
  }));

  const evidenceRows: ReportRow[] = evidenceItems.map((item) => ({
    id: item.id,
    subtask_id: item.subtask_id,
    finding_id: item.finding_id,
    analysis_output_id: item.analysis_output_id,
    data_point_id: item.data_point_id,
    stakeholder_question_id: item.stakeholder_question_id,
    evidence_type: item.evidence_type,
    title: item.title,
    source_name: item.source_name,
    source_reference: item.source_reference,
    evidence_date: item.evidence_date,
    confidence_level: item.confidence_level,
    is_primary_evidence: item.is_primary_evidence,
    description: item.description,
    notes: item.notes,
    created_at: formatDateTime(item.created_at),
    updated_at: formatDateTime(item.updated_at),
  }));

  const uploadedFileRows: ReportRow[] = uploadedFiles.map((item) => ({
    id: item.id,
    original_filename: item.original_filename,
    stored_filename: item.stored_filename,
    content_type: item.content_type,
    file_size_bytes: item.file_size_bytes,
    description: item.description,
    upload_category: item.upload_category,
    subtask_id: item.subtask_id,
    data_point_id: item.data_point_id,
    stakeholder_question_id: item.stakeholder_question_id,
    finding_id: item.finding_id,
    analysis_output_id: item.analysis_output_id,
    evidence_item_id: item.evidence_item_id,
    uploaded_by: item.uploaded_by,
    created_at: formatDateTime(item.created_at),
    updated_at: formatDateTime(item.updated_at),
  }));

  const recommendationRows: ReportRow[] = llmRecommendations.map((item) => ({
    id: item.id,
    recommendation_type: item.recommendation_type,
    category: item.category,
    priority: item.priority,
    title: item.title,
    status: item.status,
    model_name: item.model_name,
    trace_workflow_name: item.trace_workflow_name,
    deliverable_id: item.deliverable_id,
    task_id: item.task_id,
    subtask_id: item.subtask_id,
    finding_id: item.finding_id,
    analysis_output_id: item.analysis_output_id,
    recommendation_text: item.recommendation_text,
    rationale: item.rationale,
    expected_benefit: item.expected_benefit,
    implementation_notes: item.implementation_notes,
    created_by: item.created_by,
    created_at: formatDateTime(item.created_at),
    updated_at: formatDateTime(item.updated_at),
  }));

  const reviewRows: ReportRow[] = deliverableReviews.map((item) => ({
    id: item.id,
    deliverable_id: item.deliverable_id,
    review_title: item.review_title,
    review_type: item.review_type,
    review_status: item.review_status,
    model_name: item.model_name,
    trace_workflow_name: item.trace_workflow_name,
    review_summary: item.review_summary,
    strengths: item.strengths,
    gaps: item.gaps,
    risks: item.risks,
    recommended_actions: item.recommended_actions,
    readiness_assessment: item.readiness_assessment,
    created_by: item.created_by,
    created_at: formatDateTime(item.created_at),
    updated_at: formatDateTime(item.updated_at),
  }));

  const combinedRows: ReportRow[] = [
    ...engagementRows.map((row) => ({ record_type: "engagement", ...row })),
    ...workstreamRows.map((row) => ({ record_type: "workstream", ...row })),
    ...deliverableRows.map((row) => ({ record_type: "deliverable", ...row })),
    ...taskRows.map((row) => ({ record_type: "task", ...row })),
    ...subtaskRows.map((row) => ({ record_type: "subtask", ...row })),
    ...dataPointRows.map((row) => ({ record_type: "data_point", ...row })),
    ...stakeholderQuestionRows.map((row) => ({ record_type: "stakeholder_question", ...row })),
    ...findingRows.map((row) => ({ record_type: "finding", ...row })),
    ...analysisRows.map((row) => ({ record_type: "analysis_output", ...row })),
    ...evidenceRows.map((row) => ({ record_type: "evidence_item", ...row })),
    ...uploadedFileRows.map((row) => ({ record_type: "uploaded_file", ...row })),
    ...recommendationRows.map((row) => ({ record_type: "llm_recommendation", ...row })),
    ...reviewRows.map((row) => ({ record_type: "deliverable_review", ...row })),
  ];

  const statusRows: ReportRow[] = [
    ...getStatusCounts(deliverables).map((row) => ({ object_type: "deliverable", ...row })),
    ...getStatusCounts(tasks).map((row) => ({ object_type: "task", ...row })),
    ...getStatusCounts(subtasks).map((row) => ({ object_type: "subtask", ...row })),
    ...getStatusCounts(dataPoints).map((row) => ({ object_type: "data_point", ...row })),
    ...getResponseStatusCounts(stakeholderQuestions).map((row) => ({
      object_type: "stakeholder_question",
      ...row,
    })),
    ...getStatusCounts(findings).map((row) => ({ object_type: "finding", ...row })),
    ...getStatusCounts(analysisOutputs).map((row) => ({ object_type: "analysis_output", ...row })),
    ...getStatusCounts(llmRecommendations).map((row) => ({
      object_type: "llm_recommendation",
      ...row,
    })),
    ...getReviewStatusCounts(deliverableReviews).map((row) => ({
      object_type: "deliverable_review",
      ...row,
    })),
  ];

  const completedDeliverables = completionCount(deliverables);
  const completedTasks = completionCount(tasks);
  const completedSubtasks = completionCount(subtasks);
  const receivedDataPoints = dataPoints.filter((item) => item.status.toLowerCase() === "received").length;
  const respondedQuestions = stakeholderQuestions.filter(
    (item) => item.response_status.toLowerCase() === "responded",
  ).length;

  return (
    <section id="reports-exports" className="content-section">
      <div className="section-header">
        <div>
          <h2>Reports and Exports</h2>
          <p>
            Generate execution summaries and download CSV exports for project tracking,
            review meetings, and offline reporting.
          </p>
        </div>
      </div>

      <div className="report-summary-grid">
        <div className="report-card">
          <span>Deliverables Completed</span>
          <strong>{completedDeliverables}</strong>
          <p>{percent(completedDeliverables, deliverables.length)} of deliverables</p>
        </div>
        <div className="report-card">
          <span>Tasks Completed</span>
          <strong>{completedTasks}</strong>
          <p>{percent(completedTasks, tasks.length)} of tasks</p>
        </div>
        <div className="report-card">
          <span>Sub-tasks Completed</span>
          <strong>{completedSubtasks}</strong>
          <p>{percent(completedSubtasks, subtasks.length)} of sub-tasks</p>
        </div>
        <div className="report-card">
          <span>Data Points Received</span>
          <strong>{receivedDataPoints}</strong>
          <p>{percent(receivedDataPoints, dataPoints.length)} of data points</p>
        </div>
        <div className="report-card">
          <span>Questions Responded</span>
          <strong>{respondedQuestions}</strong>
          <p>{percent(respondedQuestions, stakeholderQuestions.length)} of questions</p>
        </div>
        <div className="report-card">
          <span>Consulting Outputs</span>
          <strong>{findings.length + analysisOutputs.length + evidenceItems.length}</strong>
          <p>Findings, analysis, and evidence</p>
        </div>
      </div>

      <div className="report-section-card">
        <h3>Status Distribution</h3>
        {statusRows.length === 0 ? (
          <p className="empty-state">No status data available.</p>
        ) : (
          <div className="table-card wide-table">
            <table>
              <thead>
                <tr>
                  <th>Object Type</th>
                  <th>Status</th>
                  <th>Count</th>
                </tr>
              </thead>
              <tbody>
                {statusRows.map((row, index) => (
                  <tr key={`${row.object_type}-${row.status}-${index}`}>
                    <td>{row.object_type}</td>
                    <td>{row.status}</td>
                    <td>{row.count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="report-section-card">
        <h3>CSV Exports</h3>
        <p>
          Download individual datasets or a combined export. CSV files can be opened in
          Excel, uploaded to SharePoint, or attached to status reports.
        </p>

        <div className="export-grid">
          <button className="secondary-button" onClick={() => downloadCsv("asm_engagements.csv", engagementRows)}>
            Export Engagements
          </button>
          <button className="secondary-button" onClick={() => downloadCsv("asm_workstreams.csv", workstreamRows)}>
            Export Workstreams
          </button>
          <button className="secondary-button" onClick={() => downloadCsv("asm_deliverables.csv", deliverableRows)}>
            Export Deliverables
          </button>
          <button className="secondary-button" onClick={() => downloadCsv("asm_tasks.csv", taskRows)}>
            Export Tasks
          </button>
          <button className="secondary-button" onClick={() => downloadCsv("asm_subtasks.csv", subtaskRows)}>
            Export Sub-tasks
          </button>
          <button className="secondary-button" onClick={() => downloadCsv("asm_data_points.csv", dataPointRows)}>
            Export Data Points
          </button>
          <button
            className="secondary-button"
            onClick={() => downloadCsv("asm_stakeholder_questions.csv", stakeholderQuestionRows)}
          >
            Export Stakeholder Questions
          </button>
          <button className="secondary-button" onClick={() => downloadCsv("asm_findings.csv", findingRows)}>
            Export Findings
          </button>
          <button className="secondary-button" onClick={() => downloadCsv("asm_analysis_outputs.csv", analysisRows)}>
            Export Analysis Outputs
          </button>
          <button className="secondary-button" onClick={() => downloadCsv("asm_evidence_items.csv", evidenceRows)}>
            Export Evidence Items
          </button>
          <button className="secondary-button" onClick={() => downloadCsv("asm_uploaded_files.csv", uploadedFileRows)}>
            Export Uploaded Files
          </button>
          <button
            className="secondary-button"
            onClick={() => downloadCsv("asm_llm_recommendations.csv", recommendationRows)}
          >
            Export LLM Recommendations
          </button>
          <button className="secondary-button" onClick={() => downloadCsv("asm_deliverable_reviews.csv", reviewRows)}>
            Export Deliverable Reviews
          </button>
          <button className="primary-button" onClick={() => downloadCsv("asm_full_combined_export.csv", combinedRows)}>
            Export Full Combined CSV
          </button>
          <button className="primary-button" onClick={() => downloadCsv("asm_status_distribution.csv", statusRows)}>
            Export Status Distribution
          </button>
        </div>
      </div>
    </section>
  );
}