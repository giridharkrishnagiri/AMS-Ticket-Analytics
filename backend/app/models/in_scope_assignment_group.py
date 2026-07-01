from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, Index, Integer, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin, UuidPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.project import Project


class InScopeAssignmentGroup(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "in_scope_assignment_groups"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "assignment_group_key",
            name="uq_in_scope_assignment_groups_project_key",
        ),
        Index("ix_in_scope_assignment_groups_project_id", "project_id"),
        Index("ix_in_scope_assignment_groups_client_id", "client_id"),
        Index("ix_in_scope_assignment_groups_assignment_group_key", "assignment_group_key"),
        Index(
            "ix_in_scope_assignment_groups_project_active",
            "project_id",
            "is_active",
        ),
    )

    client_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("clients.id", ondelete="CASCADE"),
        nullable=False,
    )
    project_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    assignment_group: Mapped[str] = mapped_column(Text, nullable=False)
    assignment_group_key: Mapped[str] = mapped_column(Text, nullable=False)
    functional_track: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_filename: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_row_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    project: Mapped[Project] = relationship(back_populates="in_scope_assignment_groups")
