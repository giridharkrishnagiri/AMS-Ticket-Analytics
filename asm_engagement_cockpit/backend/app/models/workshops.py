import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class LlmPromptTemplate(Base):
    __tablename__ = "llm_prompt_templates"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    prompt_key: Mapped[str] = mapped_column(String(150), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(250), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    user_prompt_template: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class Workshop(Base):
    __tablename__ = "workshops"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    workshop_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    functional_track: Mapped[str | None] = mapped_column(String(250), nullable=True, index=True)
    participants_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    agenda: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_hours: Mapped[Decimal | None] = mapped_column(Numeric(4, 2), nullable=True)

    transcript_filename: Mapped[str | None] = mapped_column(String(500), nullable=True)
    transcript_content_type: Mapped[str | None] = mapped_column(String(250), nullable=True)
    transcript_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    transcript_uploaded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    recording_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    meeting_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    key_decisions: Mapped[str | None] = mapped_column(Text, nullable=True)
    llm_raw_output: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_system_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_user_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_analyzed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    created_by: Mapped[str | None] = mapped_column(String(250), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(250), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    actions: Mapped[list["WorkshopAction"]] = relationship(
        back_populates="workshop",
        cascade="all, delete-orphan",
        order_by="WorkshopAction.order_index.asc(), WorkshopAction.created_at.asc()",
    )


class WorkshopAction(Base):
    __tablename__ = "workshop_actions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workshop_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("workshops.id", ondelete="CASCADE"), nullable=False, index=True)

    action_text: Mapped[str] = mapped_column(Text, nullable=False)
    owner_name: Mapped[str | None] = mapped_column(String(250), nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(100), nullable=False, default="Open")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    order_index: Mapped[int] = mapped_column(nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    workshop: Mapped[Workshop] = relationship(back_populates="actions")
