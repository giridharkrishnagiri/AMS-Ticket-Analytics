from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin, UuidPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.client import Client
    from app.models.project import Project


class GenAIConfig(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "genai_config"

    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    provider: Mapped[str] = mapped_column(String(50), nullable=False, default="openai")
    model_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    temperature: Mapped[float] = mapped_column(Float, nullable=False, default=0.2)
    top_p: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    max_output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=1000)
    timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    max_tool_calls: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    allow_recommendations: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    allow_chart_generation: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    response_style: Mapped[str] = mapped_column(String(20), nullable=False, default="standard")


class GenAIPromptTemplate(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "genai_prompt_templates"

    prompt_key: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    default_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    custom_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_custom_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class GenAIUsageLog(UuidPrimaryKeyMixin, Base):
    __tablename__ = "genai_usage_logs"
    __table_args__ = (
        Index("ix_genai_usage_logs_operation_created_at", "operation", "created_at"),
        Index("ix_genai_usage_logs_status_created_at", "status", "created_at"),
    )

    customer_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("clients.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    project_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    session_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    operation: Mapped[str] = mapped_column(String(50), nullable=False)
    question: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    tools_used_json: Mapped[dict[str, Any] | list[Any] | None] = mapped_column(
        JSONB,
        nullable=True,
    )
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estimated_cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    customer: Mapped[Client | None] = relationship()
    project: Mapped[Project | None] = relationship()


class GenAISafetySettings(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "genai_safety_settings"

    allow_application_detail_rows: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )
    allow_ticket_detail_rows: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    allow_aggregate_ticket_data: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    allow_problem_change_data: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    allow_sla_ola_aggregate_data: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )
    max_rows_returned_to_llm: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    max_chart_data_points: Mapped[int] = mapped_column(Integer, nullable=False, default=500)
    enforce_complete_month_cutoff: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )
    mask_sensitive_fields: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class GenAIWorkbenchSetting(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "genai_workbench_settings"

    settings_key: Mapped[str] = mapped_column(
        String(80),
        nullable=False,
        unique=True,
        index=True,
        default="default",
    )
    settings_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class GenAIChatSession(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "genai_chat_sessions"
    __table_args__ = (
        Index("ix_genai_chat_sessions_last_message_at", "last_message_at"),
        Index("ix_genai_chat_sessions_archived_last_message", "is_archived", "last_message_at"),
    )

    customer_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("clients.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    project_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False, default="New chat")
    last_message_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    customer: Mapped[Client | None] = relationship()
    project: Mapped[Project | None] = relationship()
    messages: Mapped[list[GenAIChatMessage]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="GenAIChatMessage.created_at",
    )


class GenAIChatMessage(UuidPrimaryKeyMixin, Base):
    __tablename__ = "genai_chat_messages"
    __table_args__ = (Index("ix_genai_chat_messages_session_created", "session_id", "created_at"),)

    session_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("genai_chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    session: Mapped[GenAIChatSession] = relationship(back_populates="messages")


class GenAIToolRun(UuidPrimaryKeyMixin, Base):
    __tablename__ = "genai_tool_runs"
    __table_args__ = (
        Index("ix_genai_tool_runs_tool_created_at", "tool_name", "created_at"),
        Index("ix_genai_tool_runs_domain_created_at", "domain", "created_at"),
        Index("ix_genai_tool_runs_status_created_at", "status", "created_at"),
    )

    tool_name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    domain: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    customer_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("clients.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    project_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    parameters_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    filters_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    truncated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    execution_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    warnings_json: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    customer: Mapped[Client | None] = relationship()
    project: Mapped[Project | None] = relationship()


class GenAIGeneratedChart(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "genai_generated_charts"
    __table_args__ = (
        Index("ix_genai_generated_charts_archived_created", "is_archived", "created_at"),
    )

    customer_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("clients.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    project_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    session_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    message_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    subtitle: Mapped[str | None] = mapped_column(Text, nullable=True)
    chart_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    chart_library: Mapped[str] = mapped_column(String(50), nullable=False, default="plotly")
    chart_spec_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    source_tool_names_json: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    source_tool_results_summary_json: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSONB,
        nullable=True,
    )
    parameters_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    filters_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    data_notes_json: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    warnings_json: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    customer: Mapped[Client | None] = relationship()
    project: Mapped[Project | None] = relationship()


class GenAITicketClassification(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "genai_ticket_classifications"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "analysis_month",
            "ticket_number",
            name="uq_genai_ticket_classifications_project_month_ticket",
        ),
        Index(
            "ix_genai_ticket_classifications_project_month_status",
            "project_id",
            "analysis_month",
            "status",
        ),
        Index(
            "ix_genai_ticket_classifications_category",
            "project_id",
            "analysis_month",
            "genai_category",
            "genai_subcategory_1",
            "genai_subcategory_2",
        ),
    )

    customer_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("clients.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    project_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    ticket_number: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    ticket_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    analysis_month: Mapped[str] = mapped_column(String(7), nullable=False, index=True)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    prompt_key: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    model_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="success", index=True)
    category_quality: Mapped[str | None] = mapped_column(String(40), nullable=True)
    genai_category_cluster_id: Mapped[str | None] = mapped_column(
        String(80),
        nullable=True,
        index=True,
    )
    genai_category: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    genai_subcategory_1_cluster_id: Mapped[str | None] = mapped_column(
        String(80),
        nullable=True,
        index=True,
    )
    genai_subcategory_1: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    genai_subcategory_2_cluster_id: Mapped[str | None] = mapped_column(
        String(80),
        nullable=True,
        index=True,
    )
    genai_subcategory_2: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    customer: Mapped[Client | None] = relationship()
    project: Mapped[Project] = relationship()


class GenAITicketEmbedding(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "genai_ticket_embeddings"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "ticket_number",
            "input_hash",
            "embedding_model",
            name="uq_genai_ticket_embeddings_project_ticket_hash_model",
        ),
        Index("ix_genai_ticket_embeddings_project_ticket", "project_id", "ticket_number"),
        Index("ix_genai_ticket_embeddings_model_hash", "embedding_model", "input_hash"),
    )

    customer_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("clients.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    project_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    ticket_number: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    ticket_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    embedding_model: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    normalized_text_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    text_preview: Mapped[str | None] = mapped_column(Text, nullable=True)
    embedding_json: Mapped[list[float]] = mapped_column(JSONB, nullable=False)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    customer: Mapped[Client | None] = relationship()
    project: Mapped[Project] = relationship()


class GenAITicketClusterLabel(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "genai_ticket_cluster_labels"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "analysis_month",
            "run_id",
            "cluster_level",
            "cluster_key",
            name="uq_genai_ticket_cluster_labels_run_level_key",
        ),
        Index(
            "ix_genai_ticket_cluster_labels_project_month_run",
            "project_id",
            "analysis_month",
            "run_id",
        ),
        Index(
            "ix_genai_ticket_cluster_labels_level",
            "project_id",
            "analysis_month",
            "cluster_level",
        ),
    )

    customer_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("clients.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    project_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    analysis_month: Mapped[str] = mapped_column(String(7), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    cluster_level: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    cluster_key: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    parent_cluster_key: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    ticket_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    incident_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sc_task_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    representative_tickets_json: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSONB,
        nullable=True,
    )
    child_clusters_json: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    customer: Mapped[Client | None] = relationship()
    project: Mapped[Project] = relationship()


class GenAITicketAutomationAssessment(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "genai_ticket_automation_assessments"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "analysis_month",
            "analysis_month_to",
            "cluster_run_id",
            "cluster_key",
            name="uq_genai_ticket_automation_project_period_run_cluster",
        ),
        Index(
            "ix_genai_ticket_automation_project_period",
            "project_id",
            "analysis_month",
            "analysis_month_to",
        ),
        Index(
            "ix_genai_ticket_automation_potential",
            "project_id",
            "analysis_month",
            "automation_potential",
        ),
        Index(
            "ix_genai_ticket_automation_cluster_key",
            "project_id",
            "cluster_key",
        ),
    )

    customer_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("clients.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    project_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    analysis_month: Mapped[str] = mapped_column(String(7), nullable=False, index=True)
    analysis_month_to: Mapped[str] = mapped_column(String(7), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    cluster_run_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    cluster_key: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    cluster_label: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str | None] = mapped_column(String(255), nullable=True)
    subcategory_1: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ticket_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    ticket_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    incident_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sc_task_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    prompt_key: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    model_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="success", index=True)
    automation_potential: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    recommended_resolution_path: Mapped[str | None] = mapped_column(String(80), nullable=True)
    primary_automation_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    pattern_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    current_resolution_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    likely_root_cause: Mapped[str | None] = mapped_column(Text, nullable=True)
    automation_recommendation: Mapped[str | None] = mapped_column(Text, nullable=True)
    implementation_approach: Mapped[str | None] = mapped_column(Text, nullable=True)
    prerequisites: Mapped[str | None] = mapped_column(Text, nullable=True)
    expected_benefits: Mapped[str | None] = mapped_column(Text, nullable=True)
    risks_or_constraints: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    business_services_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    representative_tickets_json: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSONB,
        nullable=True,
    )
    evidence_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    customer: Mapped[Client | None] = relationship()
    project: Mapped[Project] = relationship()
