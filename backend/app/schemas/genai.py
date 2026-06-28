from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

GenAIProvider = Literal["openai", "azure", "anthropic", "ollama", "custom"]
GenAIResponseStyle = Literal["concise", "standard", "detailed"]


class GenAIConfigResponse(BaseModel):
    id: UUID
    is_enabled: bool
    provider: str
    model_name: str | None
    temperature: float
    top_p: float
    max_output_tokens: int
    timeout_seconds: int
    max_tool_calls: int
    allow_recommendations: bool
    allow_chart_generation: bool
    response_style: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class GenAIConfigUpdateRequest(BaseModel):
    is_enabled: bool | None = None
    provider: GenAIProvider | None = None
    model_name: str | None = Field(default=None, max_length=255)
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    top_p: float | None = Field(default=None, ge=0.0, le=1.0)
    max_output_tokens: int | None = Field(default=None, ge=100, le=8000)
    timeout_seconds: int | None = Field(default=None, ge=5, le=300)
    max_tool_calls: int | None = Field(default=None, ge=0, le=50)
    allow_recommendations: bool | None = None
    allow_chart_generation: bool | None = None
    response_style: GenAIResponseStyle | None = None


class GenAIPromptTemplateResponse(BaseModel):
    id: UUID
    prompt_key: str
    display_name: str
    description: str | None
    default_prompt: str
    custom_prompt: str | None
    is_custom_enabled: bool
    version: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class GenAIPromptTemplateUpdateRequest(BaseModel):
    custom_prompt: str | None = None
    is_custom_enabled: bool = False


class GenAIPromptReseedResponse(BaseModel):
    prompt_count: int
    prompt_keys: list[str]


class GenAISafetySettingsResponse(BaseModel):
    id: UUID
    allow_application_detail_rows: bool
    allow_ticket_detail_rows: bool
    allow_aggregate_ticket_data: bool
    allow_problem_change_data: bool
    allow_sla_ola_aggregate_data: bool
    max_rows_returned_to_llm: int
    max_chart_data_points: int
    enforce_complete_month_cutoff: bool
    mask_sensitive_fields: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class GenAISafetySettingsUpdateRequest(BaseModel):
    allow_application_detail_rows: bool | None = None
    allow_ticket_detail_rows: bool | None = None
    allow_aggregate_ticket_data: bool | None = None
    allow_problem_change_data: bool | None = None
    allow_sla_ola_aggregate_data: bool | None = None
    max_rows_returned_to_llm: int | None = Field(default=None, ge=1, le=10000)
    max_chart_data_points: int | None = Field(default=None, ge=1, le=10000)
    enforce_complete_month_cutoff: bool | None = None
    mask_sensitive_fields: bool | None = None


class GenAITestRequest(BaseModel):
    test_prompt: str | None = Field(default=None, max_length=2000)


class GenAIUsageSummary(BaseModel):
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    estimated_cost: float | None = None


class GenAITestResponse(BaseModel):
    ok: bool
    provider: str
    model_name: str | None
    response_text: str | None = None
    duration_ms: int | None = None
    usage: GenAIUsageSummary | None = None
    error_message: str | None = None


class GenAIUsageLogResponse(BaseModel):
    id: UUID
    customer_id: UUID | None
    project_id: UUID | None
    session_id: str | None
    message_id: str | None
    provider: str | None
    model_name: str | None
    operation: str
    question: str | None
    status: str
    tools_used_json: dict[str, Any] | list[Any] | None
    prompt_tokens: int | None
    completion_tokens: int | None
    estimated_cost: float | None
    duration_ms: int | None
    error_message: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class GenAIContextOptionResponse(BaseModel):
    id: UUID
    name: str
    code: str
    customer_id: UUID | None = None
    customer_name: str | None = None
    customer_code: str | None = None
    label: str


class GenAIChatSessionCreateRequest(BaseModel):
    customer_id: UUID | None = None
    project_id: UUID | None = None
    title: str | None = Field(default="New chat", max_length=255)
    metadata: dict[str, Any] = Field(default_factory=dict)


class GenAIChatSessionUpdateRequest(BaseModel):
    title: str | None = Field(default=None, max_length=255)
    metadata: dict[str, Any] | None = None


class GenAIChatSessionResponse(BaseModel):
    id: UUID
    customer_id: UUID | None
    project_id: UUID | None
    title: str
    created_at: datetime
    updated_at: datetime
    last_message_at: datetime | None
    is_archived: bool
    metadata: dict[str, Any] = Field(default_factory=dict, validation_alias="metadata_json")

    model_config = {"from_attributes": True}

    @field_validator("metadata", mode="before")
    @classmethod
    def default_metadata(cls, value: Any) -> dict[str, Any]:
        return value or {}


class GenAIChatSessionListResponse(BaseModel):
    items: list[GenAIChatSessionResponse]
    total: int


class GenAIChatMessageResponse(BaseModel):
    id: UUID
    session_id: UUID
    role: str
    content: str
    created_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict, validation_alias="metadata_json")

    model_config = {"from_attributes": True}

    @field_validator("metadata", mode="before")
    @classmethod
    def default_metadata(cls, value: Any) -> dict[str, Any]:
        return value or {}


class GenAIChatSessionDetailResponse(BaseModel):
    session: GenAIChatSessionResponse
    messages: list[GenAIChatMessageResponse]


class GenAIChatContext(BaseModel):
    customer_id: UUID | None = None
    project_id: UUID | None = None
    domain: str = Field(default="General", max_length=100)
    page: str = Field(default="Chat", max_length=100)
    filters: dict[str, Any] = Field(default_factory=dict)
    time_range: dict[str, Any] = Field(default_factory=dict)


class GenAIChatMessageCreateRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=8000)
    context: GenAIChatContext = Field(default_factory=GenAIChatContext)


class GenAIChatSendSessionSummary(BaseModel):
    id: UUID
    title: str
    last_message_at: datetime | None

    model_config = {"from_attributes": True}


class GenAIChatMessageCreateResponse(BaseModel):
    user_message: GenAIChatMessageResponse
    assistant_message: GenAIChatMessageResponse
    session: GenAIChatSendSessionSummary
