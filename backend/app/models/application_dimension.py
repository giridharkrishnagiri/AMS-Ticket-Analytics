from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin, UuidPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.project import Project
    from app.models.ticket import Ticket


class ApplicationDimension(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "application_dimensions"
    __table_args__ = (
        Index("ix_application_dimensions_project_active", "project_id", "is_active"),
        Index(
            "ix_application_dimensions_project_application_name",
            "project_id",
            "application_name",
        ),
        Index(
            "ix_application_dimensions_project_application_alias",
            "project_id",
            "application_alias",
        ),
        Index(
            "ix_application_dimensions_project_business_service_alias",
            "project_id",
            "business_service_alias",
        ),
        Index(
            "ix_application_dimensions_project_cmdb_ci_alias",
            "project_id",
            "cmdb_ci_alias",
        ),
    )

    project_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    customer_name: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    tower_name: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    cluster_name: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    application_group_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )
    application_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    application_alias: Mapped[str | None] = mapped_column(Text, nullable=True)
    business_service_alias: Mapped[str | None] = mapped_column(Text, nullable=True)
    cmdb_ci_alias: Mapped[str | None] = mapped_column(Text, nullable=True)
    application_aliases: Mapped[list[str] | dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
    )
    business_service_aliases: Mapped[list[str] | dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
    )
    cmdb_ci_aliases: Mapped[list[str] | dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    project: Mapped[Project] = relationship(back_populates="application_dimensions")
    tickets: Mapped[list[Ticket]] = relationship(back_populates="application_dimension")
