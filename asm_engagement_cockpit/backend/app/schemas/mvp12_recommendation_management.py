import uuid
from datetime import date, datetime
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict


def empty_string_to_none(value):
    if value == "":
        return None
    return value


OptionalDate = Annotated[date | None, BeforeValidator(empty_string_to_none)]


class LlmRecommendationDecisionRequest(BaseModel):
    decision: str
    decision_notes: str | None = None
    decided_by: str | None = "Giridhar Krishnagiri"


class LlmRecommendationDecisionRead(BaseModel):
    id: uuid.UUID
    recommendation_id: uuid.UUID

    decision: str
    decision_notes: str | None

    previous_status: str | None
    new_status: str

    decided_by: str | None
    decided_at: datetime
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class LlmRecommendationRevisionRequest(BaseModel):
    title: str | None = None
    recommendation_text: str | None = None
    rationale: str | None = None
    expected_benefit: str | None = None
    implementation_notes: str | None = None
    revision_notes: str | None = None
    revised_by: str | None = "Giridhar Krishnagiri"


class LlmRecommendationRevisionRead(BaseModel):
    id: uuid.UUID
    recommendation_id: uuid.UUID

    previous_title: str | None
    revised_title: str | None

    previous_recommendation_text: str | None
    revised_recommendation_text: str | None

    previous_rationale: str | None
    revised_rationale: str | None

    previous_expected_benefit: str | None
    revised_expected_benefit: str | None

    previous_implementation_notes: str | None
    revised_implementation_notes: str | None

    revision_notes: str | None
    revised_by: str | None
    revised_at: datetime
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class LlmRecommendationActionItemCreate(BaseModel):
    recommendation_id: uuid.UUID

    action_title: str
    action_description: str | None = None

    owner_name: str | None = "Giridhar Krishnagiri"
    priority: str | None = "Medium"
    status: str = "Open"

    due_date: OptionalDate = None
    created_by: str | None = "Giridhar Krishnagiri"


class LlmRecommendationActionItemUpdate(BaseModel):
    action_title: str | None = None
    action_description: str | None = None

    owner_name: str | None = None
    priority: str | None = None
    status: str | None = None

    due_date: OptionalDate = None
    completion_notes: str | None = None


class LlmRecommendationActionItemRead(BaseModel):
    id: uuid.UUID

    recommendation_id: uuid.UUID

    deliverable_id: uuid.UUID | None
    task_id: uuid.UUID | None
    subtask_id: uuid.UUID | None
    finding_id: uuid.UUID | None
    analysis_output_id: uuid.UUID | None

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


class LlmRecommendationManagementResponse(BaseModel):
    recommendation_id: uuid.UUID
    status: str
    message: str