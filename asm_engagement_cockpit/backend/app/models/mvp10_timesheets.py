import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class TimesheetEntry(Base):
    __tablename__ = "timesheet_entries"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    entry_date: Mapped[date] = mapped_column(Date, nullable=False)
    person_name: Mapped[str] = mapped_column(String(255), nullable=False, default="Giridhar Krishnagiri")

    workstream_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("workstreams.id", ondelete="SET NULL"), nullable=True)
    deliverable_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("deliverables.id", ondelete="SET NULL"), nullable=True)
    task_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True)
    subtask_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("subtasks.id", ondelete="SET NULL"), nullable=True)

    activity_type: Mapped[str] = mapped_column(String(100), nullable=False, default="Delivery")
    accomplishments: Mapped[str] = mapped_column(Text, nullable=False)
    blockers: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_steps: Mapped[str | None] = mapped_column(Text, nullable=True)

    effort_hours: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    status: Mapped[str] = mapped_column(String(100), nullable=False, default="Draft")

    submitted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    submitted_by: Mapped[str | None] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class TimesheetSummary(Base):
    __tablename__ = "timesheet_summaries"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    person_name: Mapped[str] = mapped_column(String(255), nullable=False, default="Giridhar Krishnagiri")
    summary_type: Mapped[str] = mapped_column(String(100), nullable=False, default="Custom Date Range")
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)

    total_effort_hours: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    entry_count: Mapped[int] = mapped_column(default=0)

    summary_text: Mapped[str] = mapped_column(Text, nullable=False)
    accomplishments_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    blockers_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_steps_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    source_context: Mapped[str | None] = mapped_column(Text, nullable=True)
    llm_raw_output: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    trace_workflow_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())