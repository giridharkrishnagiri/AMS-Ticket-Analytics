from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin, UuidPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.client import Client
    from app.models.project import Project


class DashboardFilterCatalog(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "dashboard_filter_catalog"
    __table_args__ = (
        UniqueConstraint(
            "customer_id",
            "project_id",
            "dashboard_area",
            "filter_key",
            "filter_value",
            "data_version",
            name="uq_dashboard_filter_catalog_value_version",
        ),
        Index(
            "ix_dashboard_filter_catalog_project_area",
            "customer_id",
            "project_id",
            "dashboard_area",
        ),
        Index(
            "ix_dashboard_filter_catalog_project_area_key",
            "customer_id",
            "project_id",
            "dashboard_area",
            "filter_key",
        ),
        Index(
            "ix_dashboard_filter_catalog_project_area_key_value",
            "customer_id",
            "project_id",
            "dashboard_area",
            "filter_key",
            "filter_value",
        ),
        Index("ix_dashboard_filter_catalog_data_version", "data_version"),
    )

    customer_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("clients.id", ondelete="CASCADE"),
        nullable=False,
    )
    project_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    dashboard_area: Mapped[str] = mapped_column(String(50), nullable=False)
    filter_key: Mapped[str] = mapped_column(String(100), nullable=False)
    filter_value: Mapped[str] = mapped_column(Text, nullable=False)
    display_value: Mapped[str] = mapped_column(Text, nullable=False)
    baseline_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    data_version: Mapped[str] = mapped_column(String(50), nullable=False)
    refreshed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    customer: Mapped[Client] = relationship()
    project: Mapped[Project] = relationship()

