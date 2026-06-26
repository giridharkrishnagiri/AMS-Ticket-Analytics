from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin, UuidPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.client import Client
    from app.models.project import Project


class DashboardCommentary(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "dashboard_commentaries"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "dashboard_area",
            "tab_name",
            "sub_tab_name",
            "section_key",
            "chart_key",
            "scope_filter",
            "ticket_type_filter",
            "functional_track_ams_owner",
            name="uq_dashboard_commentary_context",
        ),
    )

    client_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("clients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    project_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    dashboard_area: Mapped[str] = mapped_column(String(100), nullable=False)
    tab_name: Mapped[str] = mapped_column(String(100), nullable=False)
    sub_tab_name: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    section_key: Mapped[str] = mapped_column(String(150), nullable=False)
    chart_key: Mapped[str] = mapped_column(String(150), nullable=False, default="")
    scope_filter: Mapped[str] = mapped_column(String(50), nullable=False)
    ticket_type_filter: Mapped[str] = mapped_column(String(50), nullable=False)
    functional_track_ams_owner: Mapped[str] = mapped_column(String(255), nullable=False)
    commentary_html: Mapped[str | None] = mapped_column(Text, nullable=True)
    commentary_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(255), nullable=True)

    client: Mapped[Client] = relationship()
    project: Mapped[Project] = relationship()
