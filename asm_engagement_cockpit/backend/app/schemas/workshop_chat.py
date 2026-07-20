import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


WorkshopChatScopeType = Literal["all", "workshop", "workstream", "deliverable", "task", "subtask"]


class WorkshopChatAskRequest(BaseModel):
    question: str = Field(min_length=1)
    session_id: uuid.UUID | None = None
    scope_type: WorkshopChatScopeType = "all"
    scope_id: uuid.UUID | None = None
    allow_external_knowledge: bool = False
    force_deep_context: bool = False


class WorkshopChatSource(BaseModel):
    id: uuid.UUID
    document_type: str
    title: str
    source_label: str
    score: float
    snippet: str
    workshop_id: uuid.UUID | None = None
    workstream_id: uuid.UUID | None = None
    deliverable_id: uuid.UUID | None = None
    task_id: uuid.UUID | None = None
    subtask_id: uuid.UUID | None = None
    chunk_index: int | None = None
    chunk_start_minute: int | None = None
    chunk_end_minute: int | None = None


class WorkshopChatMessageRead(BaseModel):
    id: uuid.UUID
    role: str
    content: str
    model_used: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class WorkshopChatResponse(BaseModel):
    session_id: uuid.UUID
    answer: str
    requires_external_knowledge: bool = False
    external_knowledge_reason: str | None = None
    model_used: str | None = None
    search_order: list[str]
    sources: list[WorkshopChatSource]
    linked_entities: list[WorkshopChatSource]
    messages: list[WorkshopChatMessageRead]


class WorkshopChatSessionRead(BaseModel):
    id: uuid.UUID
    title: str | None
    scope_type: str
    scope_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
    messages: list[WorkshopChatMessageRead]

    model_config = {"from_attributes": True}


class WorkshopChatIndexStatus(BaseModel):
    document_count: int
    transcript_chunk_count: int
    entity_document_count: int
    link_count: int
    last_indexed_at: datetime | None = None
    embedding_model: str


class WorkshopChatIndexRebuildResponse(WorkshopChatIndexStatus):
    rebuilt: bool
    message: str
