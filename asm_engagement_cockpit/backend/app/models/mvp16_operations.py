import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AppUser(Base):
    __tablename__ = "app_users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username: Mapped[str] = mapped_column(String(150), unique=True, index=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(250), nullable=False)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    role: Mapped[str] = mapped_column(String(100), nullable=False, default="Engagement Lead")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    source: Mapped[str] = mapped_column(String(100), nullable=False, default="local_config")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_type: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    event_category: Mapped[str] = mapped_column(String(120), nullable=False, default="General")
    entity_type: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    entity_title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    actor_name: Mapped[str | None] = mapped_column(String(250), nullable=True)
    actor_role: Mapped[str | None] = mapped_column(String(120), nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    details_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    severity: Mapped[str] = mapped_column(String(50), nullable=False, default="Info")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class NotificationItem(Base):
    __tablename__ = "notification_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    notification_type: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(String(50), nullable=False, default="Info")
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="Unread")
    target_role: Mapped[str | None] = mapped_column(String(120), nullable=True)
    target_user_name: Mapped[str | None] = mapped_column(String(250), nullable=True)
    source_type: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    source_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    due_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    dismissed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class ExecutiveSnapshot(Base):
    __tablename__ = "executive_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    snapshot_title: Mapped[str] = mapped_column(String(500), nullable=False)
    summary_text: Mapped[str] = mapped_column(Text, nullable=False)
    health_status: Mapped[str] = mapped_column(String(100), nullable=False, default="Unknown")
    total_workstreams: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_deliverables: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_tasks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_subtasks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    open_reminders: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    open_notifications: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    open_review_actions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    open_recommendation_actions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    generated_by: Mapped[str | None] = mapped_column(String(250), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)