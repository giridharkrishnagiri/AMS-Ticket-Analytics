import uuid
from datetime import date, datetime
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict


def empty_string_to_none(value):
    if value == "":
        return None
    return value


OptionalDate = Annotated[date | None, BeforeValidator(empty_string_to_none)]


class DeliverableReviewWorkflowCreate(BaseModel):
    deliverable_id: uuid.UUID
    workflow_title: str
    workflow_status: str = "Submitted for Review"
    review_type: str = "Internal Review"

    submitted_by: str | None = "Giridhar Krishnagiri"
    reviewer_name: str | None = None
    reviewer_role: str | None = None
    review_due_date: OptionalDate = None

    review_notes: str | None = None
    created_by: str | None = "Giridhar Krishnagiri"


class DeliverableReviewWorkflowUpdate(BaseModel):
    workflow_title: str | None = None
    workflow_status: str | None = None
    review_type: str | None = None

    submitted_by: str | None = None
    reviewer_name: str | None = None
    reviewer_role: str | None = None
    review_due_date: OptionalDate = None

    review_notes: str | None = None
    approval_notes: str | None = None
    rework_notes: str | None = None
    is_current: bool | None = None


class DeliverableReviewDecisionRequest(BaseModel):
    decision: str
    decision_by: str = "Giridhar Krishnagiri"
    approval_notes: str | None = None
    rework_notes: str | None = None
    review_notes: str | None = None


class DeliverableReviewWorkflowRead(BaseModel):
    id: uuid.UUID
    deliverable_id: uuid.UUID

    workflow_title: str
    workflow_status: str
    review_type: str

    submitted_by: str | None
    submitted_at: datetime | None

    reviewer_name: str | None
    reviewer_role: str | None
    review_due_date: date | None

    review_decision: str | None
    decision_by: str | None
    decision_at: datetime | None

    review_notes: str | None
    approval_notes: str | None
    rework_notes: str | None

    is_current: bool

    created_by: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DeliverableReviewActionItemCreate(BaseModel):
    review_workflow_id: uuid.UUID
    action_title: str
    action_description: str | None = None

    owner_name: str | None = "Giridhar Krishnagiri"
    priority: str | None = "Medium"
    status: str = "Open"

    due_date: OptionalDate = None
    created_by: str | None = "Giridhar Krishnagiri"


class DeliverableReviewActionItemUpdate(BaseModel):
    action_title: str | None = None
    action_description: str | None = None

    owner_name: str | None = None
    priority: str | None = None
    status: str | None = None

    due_date: OptionalDate = None
    completion_notes: str | None = None


class DeliverableReviewActionItemRead(BaseModel):
    id: uuid.UUID

    review_workflow_id: uuid.UUID
    deliverable_id: uuid.UUID

    action_title: str
    action_description: str | None

    owner_name: str | None
    priority: str | None
    status: str

    due_date: date | None
    completed_at: datetime | None
    completion_notes: str | None

    created_by: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)