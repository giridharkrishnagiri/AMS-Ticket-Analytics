import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class LlmRecommendation(Base):
    __tablename__ = "llm_recommendations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    recommendation_type: Mapped[str] = mapped_column(String(100), nullable=False)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    priority: Mapped[str | None] = mapped_column(String(50), nullable=True)

    title: Mapped[str] = mapped_column(String(500), nullable=False)
    recommendation_text: Mapped[str] = mapped_column(Text, nullable=False)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    expected_benefit: Mapped[str | None] = mapped_column(Text, nullable=True)
    implementation_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    source_context: Mapped[str | None] = mapped_column(Text, nullable=True)
    llm_raw_output: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[str] = mapped_column(String(100), default="Draft")
    model_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    trace_workflow_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    deliverable_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("deliverables.id", ondelete="SET NULL"), nullable=True)
    task_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True)
    subtask_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("subtasks.id", ondelete="SET NULL"), nullable=True)
    finding_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("findings.id", ondelete="SET NULL"), nullable=True)
    analysis_output_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("analysis_outputs.id", ondelete="SET NULL"), nullable=True)

    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class DeliverableReview(Base):
    __tablename__ = "deliverable_reviews"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    deliverable_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("deliverables.id", ondelete="CASCADE"), nullable=False)

    review_title: Mapped[str] = mapped_column(String(500), nullable=False)
    review_type: Mapped[str] = mapped_column(String(100), default="LLM Review")
    review_status: Mapped[str] = mapped_column(String(100), default="Draft")

    review_summary: Mapped[str] = mapped_column(Text, nullable=False)
    strengths: Mapped[str | None] = mapped_column(Text, nullable=True)
    gaps: Mapped[str | None] = mapped_column(Text, nullable=True)
    risks: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommended_actions: Mapped[str | None] = mapped_column(Text, nullable=True)
    readiness_assessment: Mapped[str | None] = mapped_column(Text, nullable=True)

    source_context: Mapped[str | None] = mapped_column(Text, nullable=True)
    llm_raw_output: Mapped[str | None] = mapped_column(Text, nullable=True)

    model_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    trace_workflow_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())