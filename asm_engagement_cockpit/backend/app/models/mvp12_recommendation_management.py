import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class LlmRecommendationDecision(Base):
    __tablename__ = "llm_recommendation_decisions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    recommendation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("llm_recommendations.id", ondelete="CASCADE"),
        nullable=False,
    )

    decision: Mapped[str] = mapped_column(String(100), nullable=False)
    decision_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    previous_status: Mapped[str | None] = mapped_column(String(100), nullable=True)
    new_status: Mapped[str] = mapped_column(String(100), nullable=False)

    decided_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    decided_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class LlmRecommendationRevision(Base):
    __tablename__ = "llm_recommendation_revisions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    recommendation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("llm_recommendations.id", ondelete="CASCADE"),
        nullable=False,
    )

    previous_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    revised_title: Mapped[str | None] = mapped_column(Text, nullable=True)

    previous_recommendation_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    revised_recommendation_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    previous_rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    revised_rationale: Mapped[str | None] = mapped_column(Text, nullable=True)

    previous_expected_benefit: Mapped[str | None] = mapped_column(Text, nullable=True)
    revised_expected_benefit: Mapped[str | None] = mapped_column(Text, nullable=True)

    previous_implementation_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    revised_implementation_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    revision_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    revised_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    revised_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class LlmRecommendationActionItem(Base):
    __tablename__ = "llm_recommendation_action_items"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    recommendation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("llm_recommendations.id", ondelete="CASCADE"),
        nullable=False,
    )

    deliverable_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("deliverables.id", ondelete="SET NULL"), nullable=True)
    task_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True)
    subtask_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("subtasks.id", ondelete="SET NULL"), nullable=True)
    finding_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("findings.id", ondelete="SET NULL"), nullable=True)
    analysis_output_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("analysis_outputs.id", ondelete="SET NULL"), nullable=True)

    action_title: Mapped[str] = mapped_column(String(500), nullable=False)
    action_description: Mapped[str | None] = mapped_column(Text, nullable=True)

    owner_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    priority: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(100), nullable=False, default="Open")

    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completion_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())