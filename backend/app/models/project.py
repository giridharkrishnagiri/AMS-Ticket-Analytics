from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin, UuidPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.application_dimension import ApplicationDimension
    from app.models.client import Client
    from app.models.dashboard_aggregate import DashboardAggregate
    from app.models.export_job import ExportJob
    from app.models.incident_sla_row import IncidentSlaRow
    from app.models.source_column_mapping import SourceColumnMapping
    from app.models.ticket import Ticket
    from app.models.upload_batch import UploadBatch


class Project(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "projects"
    __table_args__ = (UniqueConstraint("client_id", "code", name="uq_projects_client_code"),)

    client_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("clients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    default_incident_source_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    default_service_catalog_source_path: Mapped[str | None] = mapped_column(
        String(1024),
        nullable=True,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    client: Mapped[Client] = relationship(back_populates="projects")
    upload_batches: Mapped[list[UploadBatch]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
    )
    source_column_mappings: Mapped[list[SourceColumnMapping]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
    )
    application_dimensions: Mapped[list[ApplicationDimension]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
    )
    tickets: Mapped[list[Ticket]] = relationship(back_populates="project")
    incident_sla_rows: Mapped[list[IncidentSlaRow]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
    )
    dashboard_aggregates: Mapped[list[DashboardAggregate]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
    )
    export_jobs: Mapped[list[ExportJob]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
    )
