import uuid
from datetime import date, datetime
from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, ConfigDict


def empty_string_to_none(value: Any) -> Any:
    if value == "":
        return None
    return value


OptionalDate = Annotated[date | None, BeforeValidator(empty_string_to_none)]


class HealthResponse(BaseModel):
    status: str
    app_name: str
    app_env: str


class EngagementBase(BaseModel):
    name: str
    client_name: str | None = None
    description: str | None = None
    start_date: OptionalDate = None
    target_end_date: OptionalDate = None
    revised_end_date: OptionalDate = None
    actual_end_date: OptionalDate = None
    status: str = "Not Started"


class EngagementCreate(EngagementBase):
    pass


class EngagementUpdate(BaseModel):
    name: str | None = None
    client_name: str | None = None
    description: str | None = None
    start_date: OptionalDate = None
    target_end_date: OptionalDate = None
    revised_end_date: OptionalDate = None
    actual_end_date: OptionalDate = None
    status: str | None = None
    date_revision_reason: str | None = None


class EngagementRead(EngagementBase):
    id: uuid.UUID
    progress_percent: float
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class WorkstreamBase(BaseModel):
    engagement_id: uuid.UUID
    external_id: str | None = None
    name: str
    objective: str | None = None
    scope: str | None = None
    start_date: OptionalDate = None
    target_completion_date: OptionalDate = None
    revised_completion_date: OptionalDate = None
    actual_completion_date: OptionalDate = None
    status: str = "Not Started"
    risks: str | None = None
    dependencies: str | None = None


class WorkstreamCreate(WorkstreamBase):
    pass


class WorkstreamUpdate(BaseModel):
    external_id: str | None = None
    name: str | None = None
    objective: str | None = None
    scope: str | None = None
    start_date: OptionalDate = None
    target_completion_date: OptionalDate = None
    revised_completion_date: OptionalDate = None
    actual_completion_date: OptionalDate = None
    status: str | None = None
    risks: str | None = None
    dependencies: str | None = None
    date_revision_reason: str | None = None


class WorkstreamRead(WorkstreamBase):
    id: uuid.UUID
    progress_percent: float
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DeliverableBase(BaseModel):
    workstream_id: uuid.UUID
    external_id: str | None = None
    name: str
    description: str | None = None
    deliverable_type: str | None = None
    start_date: OptionalDate = None
    target_completion_date: OptionalDate = None
    revised_completion_date: OptionalDate = None
    actual_completion_date: OptionalDate = None
    submission_date: OptionalDate = None
    approval_date: OptionalDate = None
    status: str = "Not Started"
    review_status: str | None = None


class DeliverableCreate(DeliverableBase):
    pass


class DeliverableUpdate(BaseModel):
    external_id: str | None = None
    name: str | None = None
    description: str | None = None
    deliverable_type: str | None = None
    start_date: OptionalDate = None
    target_completion_date: OptionalDate = None
    revised_completion_date: OptionalDate = None
    actual_completion_date: OptionalDate = None
    submission_date: OptionalDate = None
    approval_date: OptionalDate = None
    status: str | None = None
    review_status: str | None = None
    date_revision_reason: str | None = None


class DeliverableRead(DeliverableBase):
    id: uuid.UUID
    progress_percent: float
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TaskBase(BaseModel):
    deliverable_id: uuid.UUID
    external_id: str | None = None
    title: str
    description: str | None = None
    priority: str | None = None
    start_date: OptionalDate = None
    target_completion_date: OptionalDate = None
    revised_completion_date: OptionalDate = None
    actual_completion_date: OptionalDate = None
    status: str = "Not Started"
    task_findings: str | None = None
    task_analysis: str | None = None
    evidence_summary: str | None = None


class TaskCreate(TaskBase):
    pass


class TaskUpdate(BaseModel):
    external_id: str | None = None
    title: str | None = None
    description: str | None = None
    priority: str | None = None
    start_date: OptionalDate = None
    target_completion_date: OptionalDate = None
    revised_completion_date: OptionalDate = None
    actual_completion_date: OptionalDate = None
    status: str | None = None
    task_findings: str | None = None
    task_analysis: str | None = None
    evidence_summary: str | None = None
    date_revision_reason: str | None = None


class TaskRead(TaskBase):
    id: uuid.UUID
    progress_percent: float
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SubtaskBase(BaseModel):
    task_id: uuid.UUID
    external_id: str | None = None
    title: str
    description: str | None = None
    completion_criteria: str | None = None
    priority: str | None = None
    start_date: OptionalDate = None
    target_completion_date: OptionalDate = None
    revised_completion_date: OptionalDate = None
    actual_completion_date: OptionalDate = None
    status: str = "Not Started"
    findings: str | None = None
    analysis: str | None = None


class SubtaskCreate(SubtaskBase):
    pass


class SubtaskUpdate(BaseModel):
    external_id: str | None = None
    title: str | None = None
    description: str | None = None
    completion_criteria: str | None = None
    priority: str | None = None
    start_date: OptionalDate = None
    target_completion_date: OptionalDate = None
    revised_completion_date: OptionalDate = None
    actual_completion_date: OptionalDate = None
    status: str | None = None
    findings: str | None = None
    analysis: str | None = None
    date_revision_reason: str | None = None


class SubtaskRead(SubtaskBase):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DataPointBase(BaseModel):
    subtask_id: uuid.UUID
    topic: str
    details: str | None = None
    source: str | None = None
    requested_date: OptionalDate = None
    expected_received_date: OptionalDate = None
    actual_received_date: OptionalDate = None
    status: str = "Needed"
    data_quality: str | None = None
    notes: str | None = None
    used_in_finding: bool = False


class DataPointCreate(DataPointBase):
    pass


class DataPointUpdate(BaseModel):
    topic: str | None = None
    details: str | None = None
    source: str | None = None
    requested_date: OptionalDate = None
    expected_received_date: OptionalDate = None
    actual_received_date: OptionalDate = None
    status: str | None = None
    data_quality: str | None = None
    notes: str | None = None
    used_in_finding: bool | None = None


class DataPointRead(DataPointBase):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class StakeholderQuestionBase(BaseModel):
    subtask_id: uuid.UUID
    question_text: str
    question_category: str | None = None
    stakeholder_name: str | None = None
    stakeholder_role: str | None = None
    stakeholder_email: str | None = None
    raised_date: OptionalDate = None
    expected_response_date: OptionalDate = None
    actual_response_date: OptionalDate = None
    response_status: str = "Draft"
    response_details: str | None = None
    follow_up_required: bool = False
    follow_up_notes: str | None = None
    confidence_level: str | None = None
    used_in_finding: bool = False


class StakeholderQuestionCreate(StakeholderQuestionBase):
    pass


class StakeholderQuestionUpdate(BaseModel):
    question_text: str | None = None
    question_category: str | None = None
    stakeholder_name: str | None = None
    stakeholder_role: str | None = None
    stakeholder_email: str | None = None
    raised_date: OptionalDate = None
    expected_response_date: OptionalDate = None
    actual_response_date: OptionalDate = None
    response_status: str | None = None
    response_details: str | None = None
    follow_up_required: bool | None = None
    follow_up_notes: str | None = None
    confidence_level: str | None = None
    used_in_finding: bool | None = None


class StakeholderQuestionRead(StakeholderQuestionBase):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DateRevisionHistoryRead(BaseModel):
    id: uuid.UUID
    parent_type: str
    parent_id: uuid.UUID
    original_date: date | None
    previous_revised_date: date | None
    new_revised_date: date | None
    reason: str
    revised_by: uuid.UUID | None
    revised_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ReminderRead(BaseModel):
    id: uuid.UUID
    parent_type: str
    parent_id: uuid.UUID
    parent_external_id: str | None
    parent_title: str
    reminder_type: str
    reminder_status: str
    severity: str
    reminder_date: date | None
    effective_due_date: date | None
    title: str
    message: str
    is_active: bool
    snoozed_until: date | None
    dismissed_reason: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ReminderGenerateResponse(BaseModel):
    generated_or_updated: int
    active_reminders: int


class ReminderSnoozeRequest(BaseModel):
    snoozed_until: OptionalDate


class DashboardSummary(BaseModel):
    engagements: int
    workstreams: int
    deliverables: int
    tasks: int
    subtasks: int
    data_points: int = 0
    stakeholder_questions: int = 0
    active_reminders: int = 0
    overdue_reminders: int = 0
    due_today_reminders: int = 0
    due_soon_reminders: int = 0