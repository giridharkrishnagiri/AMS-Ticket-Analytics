import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class DeliverableReviewWorkflow(Base):
    __tablename__ = "deliverable_review_workflows"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    deliverable_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("deliverables.id", ondelete="CASCADE"),
        nullable=False,
    )

    workflow_title: Mapped[str] = mapped_column(String(500), nullable=False)
    workflow_status: Mapped[str] = mapped_column(String(100), nullable=False, default="Draft")
    review_type: Mapped[str] = mapped_column(String(100), nullable=False, default="Internal Review")

    submitted_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    reviewer_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reviewer_role: Mapped[str | None] = mapped_column(String(255), nullable=True)
    review_due_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    review_decision: Mapped[str | None] = mapped_column(String(100), nullable=True)
    decision_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    decision_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    review_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    approval_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    rework_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class DeliverableReviewActionItem(Base):
    __tablename__ = "deliverable_review_action_items"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    review_workflow_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("deliverable_review_workflows.id", ondelete="CASCADE"),
        nullable=False,
    )

    deliverable_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("deliverables.id", ondelete="CASCADE"),
        nullable=False,
    )

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