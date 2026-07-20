import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    role: Mapped[str | None] = mapped_column(String(100), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class Engagement(Base):
    __tablename__ = "engagements"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    client_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    target_end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    revised_end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    actual_end_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    status: Mapped[str] = mapped_column(String(100), default="Not Started")
    progress_percent: Mapped[float] = mapped_column(Numeric(5, 2), default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    workstreams: Mapped[list["Workstream"]] = relationship(
        back_populates="engagement",
        cascade="all, delete-orphan",
    )


class Workstream(Base):
    __tablename__ = "workstreams"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    engagement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("engagements.id", ondelete="CASCADE"))

    external_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    objective: Mapped[str | None] = mapped_column(Text, nullable=True)
    scope: Mapped[str | None] = mapped_column(Text, nullable=True)

    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    target_completion_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    revised_completion_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    actual_completion_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    status: Mapped[str] = mapped_column(String(100), default="Not Started")
    progress_percent: Mapped[float] = mapped_column(Numeric(5, 2), default=0)

    risks: Mapped[str | None] = mapped_column(Text, nullable=True)
    dependencies: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    engagement: Mapped["Engagement"] = relationship(back_populates="workstreams")
    deliverables: Mapped[list["Deliverable"]] = relationship(
        back_populates="workstream",
        cascade="all, delete-orphan",
    )


class Deliverable(Base):
    __tablename__ = "deliverables"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workstream_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workstreams.id", ondelete="CASCADE"))

    external_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    deliverable_type: Mapped[str | None] = mapped_column(String(100), nullable=True)

    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    target_completion_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    revised_completion_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    actual_completion_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    submission_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    approval_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    status: Mapped[str] = mapped_column(String(100), default="Not Started")
    review_status: Mapped[str | None] = mapped_column(String(100), nullable=True)
    progress_percent: Mapped[float] = mapped_column(Numeric(5, 2), default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    workstream: Mapped["Workstream"] = relationship(back_populates="deliverables")
    tasks: Mapped[list["Task"]] = relationship(
        back_populates="deliverable",
        cascade="all, delete-orphan",
    )


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    deliverable_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("deliverables.id", ondelete="CASCADE"))

    external_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    priority: Mapped[str | None] = mapped_column(String(50), nullable=True)
    tracker_workstream_external_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    tracker_workstream_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    tracker_deliverable_external_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    tracker_deliverable_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    target_completion_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    revised_completion_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    actual_completion_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    status: Mapped[str] = mapped_column(String(100), default="Not Started")
    progress_percent: Mapped[float] = mapped_column(Numeric(5, 2), default=0)

    task_findings: Mapped[str | None] = mapped_column(Text, nullable=True)
    task_analysis: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    deliverable: Mapped["Deliverable"] = relationship(back_populates="tasks")
    subtasks: Mapped[list["Subtask"]] = relationship(
        back_populates="task",
        cascade="all, delete-orphan",
    )


class Subtask(Base):
    __tablename__ = "subtasks"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"))

    external_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    completion_criteria: Mapped[str | None] = mapped_column(Text, nullable=True)
    priority: Mapped[str | None] = mapped_column(String(50), nullable=True)

    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    target_completion_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    revised_completion_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    actual_completion_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    status: Mapped[str] = mapped_column(String(100), default="Not Started")
    findings: Mapped[str | None] = mapped_column(Text, nullable=True)
    analysis: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    task: Mapped["Task"] = relationship(back_populates="subtasks")
    data_points: Mapped[list["DataPoint"]] = relationship(
        back_populates="subtask",
        cascade="all, delete-orphan",
    )
    stakeholder_questions: Mapped[list["StakeholderQuestion"]] = relationship(
        back_populates="subtask",
        cascade="all, delete-orphan",
    )


class DataPoint(Base):
    __tablename__ = "data_points"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    subtask_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("subtasks.id", ondelete="CASCADE"))

    topic: Mapped[str] = mapped_column(String(255), nullable=False)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str | None] = mapped_column(String(255), nullable=True)

    requested_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    expected_received_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    actual_received_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    status: Mapped[str] = mapped_column(String(100), default="Needed")
    data_quality: Mapped[str | None] = mapped_column(String(100), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    used_in_finding: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    subtask: Mapped["Subtask"] = relationship(back_populates="data_points")


class StakeholderQuestion(Base):
    __tablename__ = "stakeholder_questions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    subtask_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("subtasks.id", ondelete="CASCADE"))

    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    question_category: Mapped[str | None] = mapped_column(String(100), nullable=True)

    stakeholder_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    stakeholder_role: Mapped[str | None] = mapped_column(String(255), nullable=True)
    stakeholder_email: Mapped[str | None] = mapped_column(String(255), nullable=True)

    raised_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    expected_response_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    actual_response_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    response_status: Mapped[str] = mapped_column(String(100), default="Draft")
    response_details: Mapped[str | None] = mapped_column(Text, nullable=True)

    follow_up_required: Mapped[bool] = mapped_column(Boolean, default=False)
    follow_up_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence_level: Mapped[str | None] = mapped_column(String(50), nullable=True)
    used_in_finding: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    subtask: Mapped["Subtask"] = relationship(back_populates="stakeholder_questions")


class DateRevisionHistory(Base):
    __tablename__ = "date_revision_history"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    parent_type: Mapped[str] = mapped_column(String(50), nullable=False)
    parent_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)

    original_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    previous_revised_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    new_revised_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    reason: Mapped[str] = mapped_column(Text, nullable=False, default="No reason provided")
    revised_by: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    revised_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Reminder(Base):
    __tablename__ = "reminders"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    parent_type: Mapped[str] = mapped_column(String(50), nullable=False)
    parent_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)

    parent_external_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    parent_title: Mapped[str] = mapped_column(String(255), nullable=False)

    reminder_type: Mapped[str] = mapped_column(String(100), nullable=False)
    reminder_status: Mapped[str] = mapped_column(String(100), nullable=False)
    severity: Mapped[str] = mapped_column(String(50), nullable=False)

    reminder_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    effective_due_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    snoozed_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    dismissed_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    from app.models.mvp5_findings import AnalysisOutput, EvidenceItem, Finding  # noqa: E402,F401


from app.models.workshop_chat import (  # noqa: E402,F401
    WorkshopChatMessage,
    WorkshopChatSession,
    WorkshopRagDocument,
    WorkshopRagLink,
)
