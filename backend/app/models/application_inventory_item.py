from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import Boolean, Float, ForeignKey, Index, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin, UuidPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.project import Project
    from app.models.ticket import Ticket


class ApplicationInventoryItem(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "application_inventory_items"
    __table_args__ = (
        Index("ix_application_inventory_project_id", "project_id"),
        Index(
            "ix_application_inventory_project_business_service",
            "project_id",
            "business_service_ci_name",
        ),
        Index(
            "ix_application_inventory_project_business_service_group",
            "project_id",
            "business_service_ci_name",
            "assignment_group",
        ),
        Index(
            "ix_application_inventory_project_parent_app",
            "project_id",
            "parent_application_name",
        ),
        Index(
            "ix_application_inventory_project_assignment_group",
            "project_id",
            "assignment_group",
        ),
        Index(
            "ix_application_inventory_project_application_owner",
            "project_id",
            "application_owner",
        ),
        Index("ix_application_inventory_project_support_lead", "project_id", "support_lead"),
        Index(
            "ix_application_inventory_project_functional_track",
            "project_id",
            "functional_track",
        ),
        Index("ix_application_inventory_project_ams_owner", "project_id", "ams_owner"),
        Index("ix_application_inventory_project_vendor", "project_id", "supported_by_vendor"),
        Index("ix_application_inventory_project_sap_non_sap", "project_id", "sap_non_sap"),
        Index("ix_application_inventory_project_hosting_env", "project_id", "hosting_env"),
        Index("ix_application_inventory_project_global", "project_id", "global_application"),
        Index("ix_application_inventory_project_scope_status", "project_id", "scope_status"),
        Index(
            "ix_application_inventory_project_lifecycle_stage_status",
            "project_id",
            "lifecycle_stage_status",
        ),
        Index(
            "ix_application_inventory_project_lifecycle_current",
            "project_id",
            "lifecycle_current",
        ),
        Index(
            "ix_application_inventory_project_lifecycle_1_to_3_years",
            "project_id",
            "lifecycle_1_to_3_years",
        ),
        Index(
            "ix_application_inventory_project_lifecycle_3_to_5_years",
            "project_id",
            "lifecycle_3_to_5_years",
        ),
    )

    project_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    application_number_apm: Mapped[str | None] = mapped_column(Text, nullable=True)
    parent_application_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    assignment_group: Mapped[str | None] = mapped_column(Text, nullable=True)
    assignment_group_owner: Mapped[str | None] = mapped_column(Text, nullable=True)
    application_owner: Mapped[str | None] = mapped_column(Text, nullable=True)
    business_service_ci_name: Mapped[str] = mapped_column(Text, nullable=False)
    support_lead: Mapped[str | None] = mapped_column(Text, nullable=True)
    functional_track: Mapped[str | None] = mapped_column(Text, nullable=True)
    ams_owner: Mapped[str | None] = mapped_column(Text, nullable=True)
    supported_by_vendor: Mapped[str | None] = mapped_column(Text, nullable=True)
    sap_non_sap: Mapped[str | None] = mapped_column(Text, nullable=True)
    hosting_env: Mapped[str | None] = mapped_column(Text, nullable=True)
    global_application: Mapped[str | None] = mapped_column(Text, nullable=True)
    scope_status: Mapped[str] = mapped_column(Text, nullable=False, default="out_of_scope")
    lifecycle_stage_status: Mapped[str | None] = mapped_column(Text, nullable=True)
    lifecycle_current: Mapped[str | None] = mapped_column(Text, nullable=True)
    lifecycle_1_to_3_years: Mapped[str | None] = mapped_column(Text, nullable=True)
    lifecycle_3_to_5_years: Mapped[str | None] = mapped_column(Text, nullable=True)
    active: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    active_users: Mapped[int | None] = mapped_column(Integer, nullable=True)
    avg_monthly_ticket_volume_6m: Mapped[float | None] = mapped_column(Float, nullable=True)
    tickets_per_user_per_month: Mapped[float | None] = mapped_column(Float, nullable=True)
    cmdb_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    source_filename: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_row_number: Mapped[int | None] = mapped_column(Integer, nullable=True)

    project: Mapped[Project] = relationship(back_populates="application_inventory_items")
    tickets: Mapped[list[Ticket]] = relationship(back_populates="application_inventory_item")
