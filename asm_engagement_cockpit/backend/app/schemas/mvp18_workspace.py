import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


ScopeType = Literal["task", "subtask"]


class BlankToNoneMixin(BaseModel):
    @field_validator("*", mode="before")
    @classmethod
    def blank_to_none(cls, value: Any) -> Any:
        if isinstance(value, str) and value.strip() == "":
            return None
        return value


class DeleteResponse(BaseModel):
    deleted: bool
    entity_type: str
    entity_id: uuid.UUID
    message: str


class StatusBucket(BaseModel):
    total: int = 0
    not_started: int = 0
    in_progress: int = 0
    on_hold: int = 0
    completed: int = 0
    other: int = 0


class DashboardStatusSummary(BaseModel):
    engagements: StatusBucket
    workstreams: StatusBucket
    deliverables: StatusBucket
    tasks: StatusBucket
    subtasks: StatusBucket


class ReminderIndicator(BaseModel):
    total_active: int
    overdue: int
    due_within_2_days: int
    other_active: int
    color: str
    label: str


class EntitySummary(BaseModel):
    id: uuid.UUID
    external_id: str | None = None
    name: str | None = None
    title: str | None = None
    description: str | None = None
    status: str | None = None
    priority: str | None = None
    progress_percent: Decimal | None = None
    owner_name: str | None = None
    secondary_owner_name: str | None = None
    ownership_rank: int | None = None
    start_date: date | None = None
    target_date: date | None = None
    revised_date: date | None = None
    actual_date: date | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class BreadcrumbItem(BaseModel):
    entity_type: str
    entity_id: uuid.UUID
    label: str


class EngagementWorkspace(BaseModel):
    engagement: EntitySummary
    workstreams: list[EntitySummary]
    breadcrumb: list[BreadcrumbItem]


class WorkstreamWorkspace(BaseModel):
    engagement: EntitySummary
    workstream: EntitySummary
    deliverables: list[EntitySummary]
    breadcrumb: list[BreadcrumbItem]


class DeliverableWorkspace(BaseModel):
    engagement: EntitySummary
    workstream: EntitySummary
    deliverable: EntitySummary
    tasks: list[EntitySummary]
    breadcrumb: list[BreadcrumbItem]


class WorkspaceRecordCounts(BaseModel):
    data_collections: int
    questions: int
    findings: int
    analysis: int
    evidence: int
    files: int
    recommendations: int
    reminders: int


class TaskWorkspace(BaseModel):
    engagement: EntitySummary
    workstream: EntitySummary
    deliverable: EntitySummary
    task: EntitySummary
    subtasks: list[EntitySummary]
    breadcrumb: list[BreadcrumbItem]
    record_counts: WorkspaceRecordCounts


class SubtaskWorkspace(BaseModel):
    engagement: EntitySummary
    workstream: EntitySummary
    deliverable: EntitySummary
    task: EntitySummary
    subtask: EntitySummary
    breadcrumb: list[BreadcrumbItem]
    record_counts: WorkspaceRecordCounts


class EngagementCreateUi(BlankToNoneMixin):
    name: str
    client_name: str | None = None
    description: str | None = None
    status: str = "Not Started"
    start_date: date | None = None
    target_end_date: date | None = None
    owner_name: str | None = None


class EngagementUpdateUi(BlankToNoneMixin):
    name: str | None = None
    client_name: str | None = None
    description: str | None = None
    status: str | None = None
    start_date: date | None = None
    target_end_date: date | None = None
    revised_end_date: date | None = None
    actual_end_date: date | None = None
    owner_name: str | None = None


class WorkstreamCreateUi(BlankToNoneMixin):
    external_id: str | None = None
    name: str
    description: str | None = None
    status: str = "Not Started"
    start_date: date | None = None
    target_completion_date: date | None = None
    owner_name: str | None = None


class WorkstreamUpdateUi(BlankToNoneMixin):
    external_id: str | None = None
    name: str | None = None
    description: str | None = None
    status: str | None = None
    start_date: date | None = None
    target_completion_date: date | None = None
    revised_completion_date: date | None = None
    actual_completion_date: date | None = None
    owner_name: str | None = None


class DeliverableCreateUi(BlankToNoneMixin):
    external_id: str | None = None
    name: str
    description: str | None = None
    status: str = "Not Started"
    start_date: date | None = None
    target_completion_date: date | None = None
    owner_name: str | None = None


class DeliverableUpdateUi(BlankToNoneMixin):
    external_id: str | None = None
    name: str | None = None
    description: str | None = None
    status: str | None = None
    review_status: str | None = None
    start_date: date | None = None
    target_completion_date: date | None = None
    revised_completion_date: date | None = None
    actual_completion_date: date | None = None
    owner_name: str | None = None


class TaskCreateUi(BlankToNoneMixin):
    external_id: str | None = None
    title: str
    description: str | None = None
    status: str = "Not Started"
    priority: str | None = None
    start_date: date | None = None
    target_completion_date: date | None = None
    owner_name: str | None = None


class TaskUpdateUi(BlankToNoneMixin):
    external_id: str | None = None
    title: str | None = None
    description: str | None = None
    status: str | None = None
    priority: str | None = None
    start_date: date | None = None
    target_completion_date: date | None = None
    revised_completion_date: date | None = None
    actual_completion_date: date | None = None
    owner_name: str | None = None


class SubtaskCreateUi(BlankToNoneMixin):
    external_id: str | None = None
    title: str
    description: str | None = None
    status: str = "Not Started"
    priority: str | None = None
    start_date: date | None = None
    target_completion_date: date | None = None
    owner_name: str | None = None


class SubtaskUpdateUi(BlankToNoneMixin):
    external_id: str | None = None
    title: str | None = None
    description: str | None = None
    status: str | None = None
    priority: str | None = None
    start_date: date | None = None
    target_completion_date: date | None = None
    revised_completion_date: date | None = None
    actual_completion_date: date | None = None
    owner_name: str | None = None


class WorkspaceDataCollectionCreate(BlankToNoneMixin):
    topic: str
    source: str | None = None
    details: str | None = None
    status: str = "Requested"
    expected_received_date: date | None = None
    actual_received_date: date | None = None
    data_quality: str | None = None
    notes: str | None = None
    created_by: str | None = None


class WorkspaceDataCollectionUpdate(BlankToNoneMixin):
    topic: str | None = None
    source: str | None = None
    details: str | None = None
    status: str | None = None
    expected_received_date: date | None = None
    actual_received_date: date | None = None
    data_quality: str | None = None
    notes: str | None = None
    updated_by: str | None = None


class WorkspaceDataCollectionRead(WorkspaceDataCollectionCreate):
    id: uuid.UUID
    scope_type: str
    scope_id: uuid.UUID
    updated_by: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class WorkspaceQuestionCreate(BlankToNoneMixin):
    question_text: str
    question_category: str | None = None
    stakeholder_name: str | None = None
    stakeholder_role: str | None = None
    stakeholder_email: str | None = None
    response_status: str = "Pending"
    expected_response_date: date | None = None
    actual_response_date: date | None = None
    response_details: str | None = None
    follow_up_required: bool = False
    follow_up_notes: str | None = None
    created_by: str | None = None


class WorkspaceQuestionUpdate(BlankToNoneMixin):
    question_text: str | None = None
    question_category: str | None = None
    stakeholder_name: str | None = None
    stakeholder_role: str | None = None
    stakeholder_email: str | None = None
    response_status: str | None = None
    expected_response_date: date | None = None
    actual_response_date: date | None = None
    response_details: str | None = None
    follow_up_required: bool | None = None
    follow_up_notes: str | None = None
    updated_by: str | None = None


class WorkspaceQuestionRead(WorkspaceQuestionCreate):
    id: uuid.UUID
    scope_type: str
    scope_id: uuid.UUID
    updated_by: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class WorkspaceFindingCreate(BlankToNoneMixin):
    title: str
    finding_type: str | None = None
    severity: str | None = None
    raw_text: str | None = None
    refined_text: str | None = None
    finding_text: str
    business_impact: str | None = None
    recommendation: str | None = None
    status: str = "Draft"
    confidence_level: str | None = None
    is_validated: bool = False
    created_by: str | None = None


class WorkspaceFindingUpdate(BlankToNoneMixin):
    title: str | None = None
    finding_type: str | None = None
    severity: str | None = None
    raw_text: str | None = None
    refined_text: str | None = None
    finding_text: str | None = None
    business_impact: str | None = None
    recommendation: str | None = None
    status: str | None = None
    confidence_level: str | None = None
    is_validated: bool | None = None
    updated_by: str | None = None


class WorkspaceFindingRead(WorkspaceFindingCreate):
    id: uuid.UUID
    scope_type: str
    scope_id: uuid.UUID
    updated_by: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class WorkspaceAnalysisCreate(BlankToNoneMixin):
    analysis_title: str
    analysis_type: str | None = None
    raw_text: str | None = None
    refined_text: str | None = None
    analysis_text: str
    methodology: str | None = None
    assumptions: str | None = None
    limitations: str | None = None
    status: str = "Draft"
    confidence_level: str | None = None
    reviewed_by: str | None = None
    reviewed_date: date | None = None
    created_by: str | None = None


class WorkspaceAnalysisUpdate(BlankToNoneMixin):
    analysis_title: str | None = None
    analysis_type: str | None = None
    raw_text: str | None = None
    refined_text: str | None = None
    analysis_text: str | None = None
    methodology: str | None = None
    assumptions: str | None = None
    limitations: str | None = None
    status: str | None = None
    confidence_level: str | None = None
    reviewed_by: str | None = None
    reviewed_date: date | None = None
    updated_by: str | None = None


class WorkspaceAnalysisRead(WorkspaceAnalysisCreate):
    id: uuid.UUID
    scope_type: str
    scope_id: uuid.UUID
    updated_by: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class WorkspaceEvidenceCreate(BlankToNoneMixin):
    title: str
    description: str | None = None
    evidence_type: str = "Document"
    source_name: str | None = None
    source_reference: str | None = None
    evidence_date: date | None = None
    confidence_level: str | None = None
    is_primary_evidence: bool = False
    created_by: str | None = None


class WorkspaceEvidenceUpdate(BlankToNoneMixin):
    title: str | None = None
    description: str | None = None
    evidence_type: str | None = None
    source_name: str | None = None
    source_reference: str | None = None
    evidence_date: date | None = None
    confidence_level: str | None = None
    is_primary_evidence: bool | None = None
    updated_by: str | None = None


class WorkspaceEvidenceRead(WorkspaceEvidenceCreate):
    id: uuid.UUID
    scope_type: str
    scope_id: uuid.UUID
    updated_by: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class WorkspaceFileRead(BaseModel):
    id: uuid.UUID
    scope_type: str
    scope_id: uuid.UUID
    linked_entity_type: str | None
    linked_entity_id: uuid.UUID | None
    original_filename: str
    stored_filename: str
    storage_path: str
    content_type: str | None
    file_size_bytes: int | None
    upload_category: str
    description: str | None
    uploaded_by: str | None
    uploaded_at: datetime

    model_config = ConfigDict(from_attributes=True)


class WorkspaceRecommendationRequest(BlankToNoneMixin):
    recommendation_type: str = "Workspace Advisory"
    focus_area: str = "Data gaps, questions, findings, risks, next steps"
    created_by: str | None = None


class WorkspaceRecommendationRead(BaseModel):
    id: uuid.UUID
    scope_type: str
    scope_id: uuid.UUID
    recommendation_type: str
    focus_area: str | None
    title: str
    ai_analysis: str | None
    recommendation_text: str
    additional_data_to_collect: str | None
    additional_questions_to_ask: str | None
    risks: str | None
    next_steps: str | None
    suggested_evidence: str | None
    automation_opportunities: str | None
    source_context_json: str | None
    status: str
    confidence_score: Decimal | None
    created_by: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class WorkspaceTextRefinementRequest(BaseModel):
    text: str = Field(min_length=1)
    refinement_goal: str = "Rewrite this as clear professional consulting analysis."
    context: str | None = None


class WorkspaceTextRefinementResponse(BaseModel):
    original_text: str
    refined_text: str
    refinement_goal: str


class WorkspaceFullRecords(BaseModel):
    data_collections: list[WorkspaceDataCollectionRead]
    questions: list[WorkspaceQuestionRead]
    findings: list[WorkspaceFindingRead]
    analysis: list[WorkspaceAnalysisRead]
    evidence: list[WorkspaceEvidenceRead]
    files: list[WorkspaceFileRead]
    recommendations: list[WorkspaceRecommendationRead]
