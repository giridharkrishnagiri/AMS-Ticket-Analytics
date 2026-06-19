from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin, UuidPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.dashboard_aggregate import DashboardAggregate
    from app.models.export_job import ExportJob
    from app.models.ingestion_job import IngestionJob
    from app.models.project import Project
    from app.models.ticket import Ticket
    from app.models.ticket_raw_row import TicketRawRow
    from app.models.uploaded_file import UploadedFile


class UploadBatch(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "upload_batches"
    __table_args__ = (
        UniqueConstraint("project_id", "month_key", "batch_name", name="uq_upload_batches_name"),
    )

    project_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    month_key: Mapped[str | None] = mapped_column(String(7), nullable=True, index=True)
    period_type: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        default="MONTHLY",
        server_default="MONTHLY",
        index=True,
    )
    snapshot_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    batch_name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_system: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="created", index=True)
    uploaded_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    normalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    project: Mapped[Project] = relationship(back_populates="upload_batches")
    uploaded_files: Mapped[list[UploadedFile]] = relationship(
        back_populates="upload_batch",
        cascade="all, delete-orphan",
    )
    ingestion_jobs: Mapped[list[IngestionJob]] = relationship(
        back_populates="upload_batch",
        cascade="all, delete-orphan",
    )
    raw_rows: Mapped[list[TicketRawRow]] = relationship(
        back_populates="upload_batch",
        cascade="all, delete-orphan",
    )
    tickets: Mapped[list[Ticket]] = relationship(back_populates="upload_batch")
    dashboard_aggregates: Mapped[list[DashboardAggregate]] = relationship(
        back_populates="upload_batch",
    )
    export_jobs: Mapped[list[ExportJob]] = relationship(back_populates="upload_batch")
