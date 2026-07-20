import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class LlmRecommendationGenerateRequest(BaseModel):
    deliverable_id: uuid.UUID | None = None
    task_id: uuid.UUID | None = None
    subtask_id: uuid.UUID | None = None
    finding_id: uuid.UUID | None = None
    analysis_output_id: uuid.UUID | None = None

    recommendation_type: str = "ASM Improvement Recommendation"
    focus_area: str = "Application Support and Maintenance consulting"
    created_by: str | None = "Giridhar Krishnagiri"


class LlmRecommendationRead(BaseModel):
    id: uuid.UUID

    recommendation_type: str
    category: str | None
    priority: str | None

    title: str
    recommendation_text: str
    rationale: str | None
    expected_benefit: str | None
    implementation_notes: str | None

    source_context: str | None
    llm_raw_output: str | None

    status: str
    model_name: str | None
    trace_workflow_name: str | None

    deliverable_id: uuid.UUID | None
    task_id: uuid.UUID | None
    subtask_id: uuid.UUID | None
    finding_id: uuid.UUID | None
    analysis_output_id: uuid.UUID | None

    created_by: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DeliverableReviewGenerateRequest(BaseModel):
    deliverable_id: uuid.UUID
    review_type: str = "LLM Deliverable Review"
    created_by: str | None = "Giridhar Krishnagiri"


class DeliverableReviewRead(BaseModel):
    id: uuid.UUID
    deliverable_id: uuid.UUID

    review_title: str
    review_type: str
    review_status: str

    review_summary: str
    strengths: str | None
    gaps: str | None
    risks: str | None
    recommended_actions: str | None
    readiness_assessment: str | None

    source_context: str | None
    llm_raw_output: str | None

    model_name: str | None
    trace_workflow_name: str | None

    created_by: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)