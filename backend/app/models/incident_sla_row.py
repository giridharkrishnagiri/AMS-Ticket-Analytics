from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import UuidPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.project import Project


class IncidentSlaRow(UuidPrimaryKeyMixin, Base):
    __tablename__ = "incident_sla_rows"
    __table_args__ = (
        Index("ix_incident_sla_rows_project_inc_number", "project_id", "inc_number"),
        Index("ix_incident_sla_rows_project_fingerprint", "project_id", "row_fingerprint"),
        Index("ix_incident_sla_rows_project_agreement", "project_id", "agreement_type"),
        Index(
            "ix_incident_sla_rows_project_inc_target",
            "project_id",
            "inc_number",
            "taskslatable_sla_target",
        ),
        Index(
            "ix_incident_sla_rows_project_sla_name",
            "project_id",
            "taskslatable_sla_name",
        ),
    )

    project_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    uploaded_file_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    agreement_type: Mapped[str] = mapped_column(Text, nullable=False, default="ola")
    source_row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    inc_number: Mapped[str] = mapped_column(Text, nullable=False)
    inc_priority: Mapped[str | None] = mapped_column(Text, nullable=True)
    taskslatable_stage: Mapped[str | None] = mapped_column(Text, nullable=True)
    assignment_group_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    taskslatable_duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    taskslatable_business_duration_seconds: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    taskslatable_has_breached: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    taskslatable_sla_sys_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    taskslatable_sla_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    taskslatable_sla_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    taskslatable_sla_target: Mapped[str | None] = mapped_column(Text, nullable=True)
    row_fingerprint: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    project: Mapped[Project] = relationship(back_populates="incident_sla_rows")
