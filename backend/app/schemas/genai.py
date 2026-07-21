from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

GenAIProvider = Literal["openai", "azure", "anthropic", "ollama", "custom"]
GenAIResponseStyle = Literal["concise", "standard", "detailed"]
GenAIChartType = Literal[
    "bar",
    "horizontal_bar",
    "grouped_bar",
    "stacked_bar",
    "line",
    "multi_line",
    "pie",
    "donut",
    "scatter",
    "scatter_3d",
    "table",
]
GenAIChartOrientation = Literal["vertical", "horizontal"]
GenAIChartDisplayMode = Literal["2d", "3d"]
GenAIChartSortOrder = Literal["original", "ascending", "descending"]


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


class GenAITicketClassificationUsageSummary(GenAIUsageSummary):
    duration_ms: int | None = None


class GenAITicketClassificationUsageRunResponse(BaseModel):
    run_id: str
    project_id: UUID
    analysis_month: str
    model_name: str | None = None
    provider: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    estimated_cost: float | None = None
    embedding_model_name: str | None = None
    embedding_tokens: int | None = None
    embedding_cost: float | None = None
    embedding_batch_count: int | None = None
    llm_model_name: str | None = None
    llm_prompt_tokens: int | None = None
    llm_completion_tokens: int | None = None
    llm_total_tokens: int | None = None
    llm_cost: float | None = None
    llm_batch_count: int | None = None
    duration_ms: int | None = None
    ticket_count: int
    batch_count: int
    success_batch_count: int
    error_batch_count: int
    started_at: datetime | None = None
    completed_at: datetime | None = None


class GenAITicketClassificationUsageRunsResponse(BaseModel):
    project_id: UUID
    analysis_month: str
    runs: list[GenAITicketClassificationUsageRunResponse] = Field(default_factory=list)


class GenAITestResponse(BaseModel):
    ok: bool
    provider: str
    model_name: str | None
    response_text: str | None = None
    duration_ms: int | None = None
    usage: GenAIUsageSummary | None = None
    error_message: str | None = None


class GenAITicketClassificationSummaryResponse(BaseModel):
    project_id: UUID
    analysis_month: str
    eligible_ticket_count: int
    analyzed_ticket_count: int
    error_ticket_count: int
    category_count: int
    subcategory_1_count: int
    subcategory_2_count: int
    incident_count: int
    sc_task_count: int
    last_processed_at: datetime | None = None
    category_quality_counts: dict[str, int] = Field(default_factory=dict)


class GenAITicketClassificationPivotRow(BaseModel):
    genai_category: str | None
    genai_subcategory_1: str | None
    genai_subcategory_2: str | None
    incident_count: int
    sc_task_count: int
    total_count: int


class GenAITicketClassificationPivotResponse(BaseModel):
    project_id: UUID
    analysis_month: str
    rows: list[GenAITicketClassificationPivotRow] = Field(default_factory=list)


class GenAITicketClassificationRunRequest(BaseModel):
    project_id: UUID
    analysis_month: str = Field(default="2026-05", pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    force_reprocess: bool = False
    batch_size: int = Field(default=10, ge=1, le=25)
    batch_limit: int | None = Field(default=None, ge=1, le=50)
    run_id: str | None = Field(default=None, max_length=80)


class GenAITicketClassificationRunResponse(BaseModel):
    project_id: UUID
    analysis_month: str
    eligible_ticket_count: int
    processed_count: int
    skipped_cached_count: int
    skipped_error_count: int
    failed_count: int
    remaining_ticket_count: int
    processed_batch_count: int
    total_batch_count: int
    summary: GenAITicketClassificationSummaryResponse
    usage: GenAITicketClassificationUsageSummary
    usage_run: GenAITicketClassificationUsageRunResponse | None = None


class GenAITicketClassificationClearRequest(BaseModel):
    project_id: UUID
    analysis_month: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")


class GenAITicketClassificationClearResponse(BaseModel):
    project_id: UUID
    analysis_month: str
    deleted_count: int


class GenAIWorkbenchSettingsResponse(BaseModel):
    ticket_classification_button_enabled: bool
    ticket_cluster_analysis_button_enabled: bool
    cluster_embedding_model_name: str
    cluster_label_model_name: str | None = None
    cluster_level_1_count: int
    cluster_level_2_count: int
    cluster_level_3_count: int
    cluster_embedding_batch_size: int
    cluster_label_batch_size: int


class GenAITicketClusterRunRequest(BaseModel):
    project_id: UUID
    analysis_month: str = Field(default="2026-05", pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    force_reprocess: bool = False
    level_1_count: int | None = Field(default=None, ge=1, le=50)
    level_2_count: int | None = Field(default=None, ge=1, le=150)
    level_3_count: int | None = Field(default=None, ge=1, le=300)
    run_id: str | None = Field(default=None, max_length=80)


class GenAITicketClusterRunResponse(BaseModel):
    project_id: UUID
    analysis_month: str
    run_id: str
    eligible_ticket_count: int
    embedded_ticket_count: int
    cached_embedding_count: int
    new_embedding_count: int
    level_1_cluster_count: int
    level_2_cluster_count: int
    level_3_cluster_count: int
    labeled_cluster_count: int
    assigned_ticket_count: int
    failed_count: int
    summary: GenAITicketClassificationSummaryResponse
    usage_run: GenAITicketClassificationUsageRunResponse | None = None


class GenAITicketClusterClearRequest(BaseModel):
    project_id: UUID
    analysis_month: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")


class GenAITicketClusterClearResponse(BaseModel):
    project_id: UUID
    analysis_month: str
    deleted_classification_count: int
    deleted_cluster_label_count: int


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


class GenAIToolColumn(BaseModel):
    key: str
    label: str
    type: str = "string"


class GenAIToolSummary(BaseModel):
    title: str
    description: str | None = None


class GenAIToolCatalogItem(BaseModel):
    tool_name: str
    domain: str
    display_name: str
    description: str
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    allowed_dimensions: list[str] = Field(default_factory=list)
    allowed_metrics: list[str] = Field(default_factory=list)
    max_rows: int
    data_safety_level: str


class GenAIToolCatalogResponse(BaseModel):
    items: list[GenAIToolCatalogItem]


class GenAIToolExecuteRequest(BaseModel):
    tool_name: str = Field(..., min_length=1, max_length=120)
    customer_id: UUID | None = None
    project_id: UUID | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    filters: dict[str, Any] = Field(default_factory=dict)


class GenAIToolExecuteResponse(BaseModel):
    tool_name: str
    domain: str
    status: str
    summary: GenAIToolSummary
    columns: list[GenAIToolColumn] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)
    totals: dict[str, Any] = Field(default_factory=dict)
    applied_filters: dict[str, Any] = Field(default_factory=dict)
    data_notes: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    row_count: int = 0
    truncated: bool = False
    execution_ms: int | None = None


class GenAIToolRunResponse(BaseModel):
    id: UUID
    tool_name: str
    domain: str | None
    customer_id: UUID | None
    project_id: UUID | None
    status: str
    parameters_json: dict[str, Any] | None
    filters_json: dict[str, Any] | None
    row_count: int | None
    truncated: bool
    execution_ms: int | None
    warnings_json: list[str] | None
    error_message: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class GenAIChartTable(BaseModel):
    columns: list[GenAIToolColumn] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)


class GenAIGeneratedChartSummary(BaseModel):
    chart_id: UUID
    title: str
    chart_type: str
    chart_library: str = "plotly"


class GenAIGeneratedChartListItemResponse(BaseModel):
    id: UUID
    customer_id: UUID | None
    project_id: UUID | None
    session_id: str | None
    message_id: str | None
    title: str
    subtitle: str | None
    chart_type: str
    chart_library: str
    is_archived: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class GenAIGeneratedChartListResponse(BaseModel):
    items: list[GenAIGeneratedChartListItemResponse]
    total: int


class GenAIGeneratedChartResponse(BaseModel):
    id: UUID
    customer_id: UUID | None
    project_id: UUID | None
    session_id: str | None
    message_id: str | None
    title: str
    subtitle: str | None
    chart_type: str
    chart_library: str
    is_archived: bool
    chart_spec: dict[str, Any]
    table: GenAIChartTable
    source_tool_names: list[str]
    source_tool_results_summary: list[dict[str, Any]]
    parameters: dict[str, Any]
    filters: dict[str, Any]
    data_notes: list[str]
    warnings: list[str]
    created_at: datetime
    updated_at: datetime


class GenAIChartFromToolResultRequest(BaseModel):
    tool_result: dict[str, Any]
    customer_id: UUID | None = None
    project_id: UUID | None = None
    session_id: str | None = Field(default=None, max_length=255)
    message_id: str | None = Field(default=None, max_length=255)
    question: str | None = Field(default=None, max_length=1000)
    chart_type: GenAIChartType | None = None


class GenAIChartUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    subtitle: str | None = Field(default=None, max_length=1000)
    chart_type: GenAIChartType | None = None
    orientation: GenAIChartOrientation | None = None
    display_mode: GenAIChartDisplayMode | None = None
    show_labels: bool | None = None
    show_legend: bool | None = None
    sort_order: GenAIChartSortOrder | None = None
    top_n: int | None = Field(default=None, ge=1, le=10000)
    x_axis_title: str | None = Field(default=None, max_length=255)
    y_axis_title: str | None = Field(default=None, max_length=255)
    z_axis_title: str | None = Field(default=None, max_length=255)
    color_by: str | None = Field(default=None, max_length=120)

    model_config = {"extra": "forbid"}


class GenAIChartDuplicateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)

    model_config = {"extra": "forbid"}
