import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class WorkshopActionBase(BaseModel):
    action_text: str
    owner_name: str | None = None
    due_date: date | None = None
    status: str = "Open"
    notes: str | None = None
    order_index: int = 0


class WorkshopActionCreate(WorkshopActionBase):
    pass


class WorkshopActionUpdate(BaseModel):
    action_text: str | None = None
    owner_name: str | None = None
    due_date: date | None = None
    status: str | None = None
    notes: str | None = None
    order_index: int | None = None


class WorkshopActionRead(WorkshopActionBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workshop_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class WorkshopRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workshop_date: date
    title: str
    functional_track: str | None
    participants_text: str | None
    agenda: str | None
    duration_hours: Decimal | None
    transcript_filename: str | None
    transcript_content_type: str | None
    transcript_text: str | None
    transcript_uploaded_at: datetime | None
    recording_path: str | None
    meeting_notes: str | None
    key_decisions: str | None
    llm_raw_output: str | None
    last_system_prompt: str | None
    last_user_prompt: str | None
    last_analyzed_at: datetime | None
    created_by: str | None
    updated_by: str | None
    created_at: datetime
    updated_at: datetime
    actions: list[WorkshopActionRead] = []


class WorkshopListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workshop_date: date
    title: str
    functional_track: str | None
    duration_hours: Decimal | None
    transcript_filename: str | None
    recording_path: str | None
    last_analyzed_at: datetime | None
    action_count: int = 0


class WorkshopAnalysisUpdate(BaseModel):
    meeting_notes: str | None = None
    key_decisions: str | None = None


class PromptPreview(BaseModel):
    prompt_key: str
    system_prompt: str
    user_prompt: str


class LlmPromptTemplateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    prompt_key: str
    name: str
    description: str | None
    system_prompt: str
    user_prompt_template: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class LlmPromptTemplateUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    system_prompt: str | None = None
    user_prompt_template: str | None = None
    is_active: bool | None = None
