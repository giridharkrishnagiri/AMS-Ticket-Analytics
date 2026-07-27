from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import ForeignKey, Index, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin, UuidPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.project import Project


class ResourceDemandUnitEffort(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "resource_demand_unit_efforts"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "ticket_type",
            "incident_source",
            "technology",
            name="uq_resource_demand_unit_efforts_project_basis",
        ),
        Index("ix_resource_demand_unit_efforts_project", "project_id"),
    )

    project_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    ticket_type: Mapped[str] = mapped_column(String(40), nullable=False)
    incident_source: Mapped[str] = mapped_column(String(40), nullable=False, default="Any")
    technology: Mapped[str] = mapped_column(String(120), nullable=False, default="Generic")
    l1_5_hours: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    l2_hours: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    l3_hours: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    sort_order: Mapped[int] = mapped_column(default=0, nullable=False)

    project: Mapped[Project] = relationship()
