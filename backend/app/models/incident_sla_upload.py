from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import UuidPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.project import Project


class IncidentSlaUpload(UuidPrimaryKeyMixin, Base):
    __tablename__ = "incident_sla_uploads"
    __table_args__ = (
        Index("ix_incident_sla_uploads_project_uploaded_at", "project_id", "uploaded_at"),
        Index("ix_incident_sla_uploads_project_filename", "project_id", "filename"),
        Index("ix_incident_sla_uploads_project_agreement", "project_id", "agreement_type"),
    )

    project_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    agreement_type: Mapped[str] = mapped_column(String(10), nullable=False, default="ola")
    total_rows_read: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    inserted_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duplicate_rows_skipped: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="UPLOADED")
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    project: Mapped[Project] = relationship(back_populates="incident_sla_uploads")
