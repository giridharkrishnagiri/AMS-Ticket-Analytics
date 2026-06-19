from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Numeric, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin, UuidPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.project import Project
    from app.models.upload_batch import UploadBatch


class DashboardAggregate(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "dashboard_aggregates"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "upload_batch_id",
            "month_key",
            "ticket_type",
            "metric_name",
            "dimension_name",
            "dimension_value",
            name="uq_dashboard_aggregates_metric_dimension",
        ),
    )

    project_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    upload_batch_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("upload_batches.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    month_key: Mapped[str] = mapped_column(String(7), nullable=False, index=True)
    ticket_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    metric_name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    dimension_name: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    dimension_value: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    value_numeric: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    value_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    calculated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    project: Mapped[Project] = relationship(back_populates="dashboard_aggregates")
    upload_batch: Mapped[UploadBatch | None] = relationship(
        back_populates="dashboard_aggregates"
    )
