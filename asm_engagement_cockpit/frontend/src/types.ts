export type DashboardSummary = {
  engagements: number;
  workstreams: number;
  deliverables: number;
  tasks: number;
  subtasks: number;
  data_points: number;
  stakeholder_questions: number;
  active_reminders: number;
  overdue_reminders: number;
  due_today_reminders: number;
  due_soon_reminders: number;
};

export type Engagement = {
  id: string;
  name: string;
  client_name: string | null;
  description: string | null;
  status: string;
  progress_percent: number;
  start_date: string | null;
  target_end_date: string | null;
  revised_end_date: string | null;
  actual_end_date: string | null;
  created_at: string;
  updated_at: string;
};

export type Workstream = {
  id: string;
  engagement_id: string;
  external_id: string | null;
  name: string;
  objective: string | null;
  scope: string | null;
  status: string;
  progress_percent: number;
  start_date: string | null;
  target_completion_date: string | null;
  revised_completion_date: string | null;
  actual_completion_date: string | null;
  created_at: string;
  updated_at: string;
};

export type Deliverable = {
  id: string;
  workstream_id: string;
  external_id: string | null;
  name: string;
  description: string | null;
  deliverable_type: string | null;
  status: string;
  review_status: string | null;
  progress_percent: number;
  start_date: string | null;
  target_completion_date: string | null;
  revised_completion_date: string | null;
  actual_completion_date: string | null;
  submission_date: string | null;
  approval_date: string | null;
  created_at: string;
  updated_at: string;
};

export type Task = {
  id: string;
  deliverable_id: string;
  external_id: string | null;
  title: string;
  description: string | null;
  priority: string | null;
  status: string;
  progress_percent: number;
  start_date: string | null;
  target_completion_date: string | null;
  revised_completion_date: string | null;
  actual_completion_date: string | null;
  created_at: string;
  updated_at: string;
};

export type Subtask = {
  id: string;
  task_id: string;
  external_id: string | null;
  title: string;
  description: string | null;
  completion_criteria: string | null;
  priority: string | null;
  status: string;
  start_date: string | null;
  target_completion_date: string | null;
  revised_completion_date: string | null;
  actual_completion_date: string | null;
  created_at: string;
  updated_at: string;
};

export type DataPoint = {
  id: string;
  subtask_id: string;
  topic: string;
  details: string | null;
  source: string | null;
  requested_date: string | null;
  expected_received_date: string | null;
  actual_received_date: string | null;
  status: string;
  data_quality: string | null;
  notes: string | null;
  used_in_finding: boolean;
  created_at: string;
  updated_at: string;
};

export type StakeholderQuestion = {
  id: string;
  subtask_id: string;
  question_text: string;
  question_category: string | null;
  stakeholder_name: string | null;
  stakeholder_role: string | null;
  stakeholder_email: string | null;
  raised_date: string | null;
  expected_response_date: string | null;
  actual_response_date: string | null;
  response_status: string;
  response_details: string | null;
  follow_up_required: boolean;
  follow_up_notes: string | null;
  confidence_level: string | null;
  used_in_finding: boolean;
  created_at: string;
  updated_at: string;
};

export type Finding = {
  id: string;
  subtask_id: string;
  task_id: string | null;
  deliverable_id: string | null;
  title: string;
  finding_type: string | null;
  severity: string | null;
  finding_text: string;
  business_impact: string | null;
  recommendation: string | null;
  status: string;
  confidence_level: string | null;
  is_validated: boolean;
  validated_by: string | null;
  validated_date: string | null;
  created_at: string;
  updated_at: string;
};

export type AnalysisOutput = {
  id: string;
  subtask_id: string;
  task_id: string | null;
  deliverable_id: string | null;
  analysis_title: string;
  analysis_type: string | null;
  analysis_text: string;
  methodology: string | null;
  assumptions: string | null;
  limitations: string | null;
  status: string;
  confidence_level: string | null;
  reviewed_by: string | null;
  reviewed_date: string | null;
  created_at: string;
  updated_at: string;
};

export type EvidenceItem = {
  id: string;
  subtask_id: string | null;
  finding_id: string | null;
  analysis_output_id: string | null;
  data_point_id: string | null;
  stakeholder_question_id: string | null;
  evidence_type: string;
  title: string;
  description: string | null;
  source_name: string | null;
  source_reference: string | null;
  evidence_date: string | null;
  confidence_level: string | null;
  is_primary_evidence: boolean;
  notes: string | null;
  created_at: string;
  updated_at: string;
};

export type UploadedFile = {
  id: string;
  original_filename: string;
  stored_filename: string;
  storage_path: string;
  content_type: string | null;
  file_size_bytes: number;
  description: string | null;
  upload_category: string | null;
  subtask_id: string | null;
  data_point_id: string | null;
  stakeholder_question_id: string | null;
  finding_id: string | null;
  analysis_output_id: string | null;
  evidence_item_id: string | null;
  uploaded_by: string | null;
  created_at: string;
  updated_at: string;
};

export type LlmRecommendation = {
  id: string;
  recommendation_type: string;
  category: string | null;
  priority: string | null;
  title: string;
  recommendation_text: string;
  rationale: string | null;
  expected_benefit: string | null;
  implementation_notes: string | null;
  source_context: string | null;
  llm_raw_output: string | null;
  status: string;
  model_name: string | null;
  trace_workflow_name: string | null;
  deliverable_id: string | null;
  task_id: string | null;
  subtask_id: string | null;
  finding_id: string | null;
  analysis_output_id: string | null;
  created_by: string | null;
  created_at: string;
  updated_at: string;
};

export type LlmRecommendationDecision = {
  id: string;
  recommendation_id: string;
  decision: string;
  decision_notes: string | null;
  previous_status: string | null;
  new_status: string;
  decided_by: string | null;
  decided_at: string;
  created_at: string;
};

export type LlmRecommendationRevision = {
  id: string;
  recommendation_id: string;
  previous_title: string | null;
  revised_title: string | null;
  previous_recommendation_text: string | null;
  revised_recommendation_text: string | null;
  previous_rationale: string | null;
  revised_rationale: string | null;
  previous_expected_benefit: string | null;
  revised_expected_benefit: string | null;
  previous_implementation_notes: string | null;
  revised_implementation_notes: string | null;
  revision_notes: string | null;
  revised_by: string | null;
  revised_at: string;
  created_at: string;
};

export type LlmRecommendationActionItem = {
  id: string;
  recommendation_id: string;
  deliverable_id: string | null;
  task_id: string | null;
  subtask_id: string | null;
  finding_id: string | null;
  analysis_output_id: string | null;
  action_title: string;
  action_description: string | null;
  owner_name: string | null;
  priority: string | null;
  status: string;
  due_date: string | null;
  completed_at: string | null;
  completion_notes: string | null;
  created_by: string | null;
  created_at: string;
  updated_at: string;
};

export type DeliverableReview = {
  id: string;
  deliverable_id: string;
  review_title: string;
  review_type: string;
  review_status: string;
  review_summary: string;
  strengths: string | null;
  gaps: string | null;
  risks: string | null;
  recommended_actions: string | null;
  readiness_assessment: string | null;
  source_context: string | null;
  llm_raw_output: string | null;
  model_name: string | null;
  trace_workflow_name: string | null;
  created_by: string | null;
  created_at: string;
  updated_at: string;
};

export type DeliverableReviewWorkflow = {
  id: string;
  deliverable_id: string;
  workflow_title: string;
  workflow_status: string;
  review_type: string;
  submitted_by: string | null;
  submitted_at: string | null;
  reviewer_name: string | null;
  reviewer_role: string | null;
  review_due_date: string | null;
  review_decision: string | null;
  decision_by: string | null;
  decision_at: string | null;
  review_notes: string | null;
  approval_notes: string | null;
  rework_notes: string | null;
  is_current: boolean;
  created_by: string | null;
  created_at: string;
  updated_at: string;
};

export type DeliverableReviewActionItem = {
  id: string;
  review_workflow_id: string;
  deliverable_id: string;
  action_title: string;
  action_description: string | null;
  owner_name: string | null;
  priority: string | null;
  status: string;
  due_date: string | null;
  completed_at: string | null;
  completion_notes: string | null;
  created_by: string | null;
  created_at: string;
  updated_at: string;
};

export type TimesheetEntry = {
  id: string;
  entry_date: string;
  person_name: string;
  workstream_id: string | null;
  deliverable_id: string | null;
  task_id: string | null;
  subtask_id: string | null;
  activity_type: string;
  accomplishments: string;
  blockers: string | null;
  next_steps: string | null;
  effort_hours: number;
  status: string;
  submitted: boolean;
  submitted_at: string | null;
  submitted_by: string | null;
  created_at: string;
  updated_at: string;
};

export type TimesheetSummary = {
  id: string;
  person_name: string;
  summary_type: string;
  start_date: string;
  end_date: string;
  total_effort_hours: number;
  entry_count: number;
  summary_text: string;
  accomplishments_summary: string | null;
  blockers_summary: string | null;
  next_steps_summary: string | null;
  source_context: string | null;
  llm_raw_output: string | null;
  model_name: string | null;
  trace_workflow_name: string | null;
  created_by: string | null;
  created_at: string;
  updated_at: string;
};

export type Reminder = {
  id: string;
  parent_type: string;
  parent_id: string;
  parent_external_id: string | null;
  parent_title: string;
  reminder_type: string;
  reminder_status: string;
  severity: string;
  reminder_date: string | null;
  effective_due_date: string | null;
  title: string;
  message: string;
  is_active: boolean;
  snoozed_until: string | null;
  dismissed_reason: string | null;
  created_at: string;
  updated_at: string;
};

export type TextRefinementRequest = {
  raw_text: string;
  refinement_type: "finding" | "analysis" | "general";
  tone: string;
  output_format: string;
};

export type TextRefinementResponse = {
  raw_text: string;
  refined_text: string;
  refinement_type: string;
  tone: string;
  output_format: string;
};