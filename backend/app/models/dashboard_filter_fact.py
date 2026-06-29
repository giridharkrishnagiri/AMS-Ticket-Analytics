from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Date, DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin, UuidPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.client import Client
    from app.models.project import Project


class DashboardFilterFact(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "dashboard_filter_facts"
    __table_args__ = (
        Index(
            "ix_dashboard_filter_facts_project_area",
            "project_id",
            "dashboard_area",
        ),
        Index(
            "ix_dashboard_filter_facts_project_area_domain",
            "project_id",
            "dashboard_area",
            "record_domain",
        ),
        Index(
            "ix_dashboard_filter_facts_project_area_version",
            "project_id",
            "dashboard_area",
            "data_version",
        ),
        Index("ix_dashboard_filter_facts_project_scope_type", "project_id", "scope", "record_type"),
        Index(
            "ix_dashboard_filter_facts_project_functional",
            "project_id",
            "functional_track_ams_owner",
        ),
        Index(
            "ix_dashboard_filter_facts_project_assignment",
            "project_id",
            "assignment_group_support_owner",
        ),
        Index(
            "ix_dashboard_filter_facts_project_parent_app",
            "project_id",
            "parent_business_application",
        ),
        Index("ix_dashboard_filter_facts_project_app_owner", "project_id", "application_owner"),
        Index("ix_dashboard_filter_facts_project_vendor", "project_id", "supported_by_vendor"),
        Index("ix_dashboard_filter_facts_project_sap", "project_id", "sap_non_sap"),
        Index("ix_dashboard_filter_facts_project_arch", "project_id", "architecture_type"),
        Index("ix_dashboard_filter_facts_project_app_type", "project_id", "application_type"),
        Index(
            "ix_dashboard_filter_facts_project_business_critical",
            "project_id",
            "business_critical",
        ),
        Index("ix_dashboard_filter_facts_project_install_status", "project_id", "install_status"),
        Index("ix_dashboard_filter_facts_project_install_type", "project_id", "install_type"),
        Index("ix_dashboard_filter_facts_project_hosting_env", "project_id", "hosting_env"),
        Index("ix_dashboard_filter_facts_project_created_month", "project_id", "created_month"),
        Index("ix_dashboard_filter_facts_project_completed_month", "project_id", "completed_month"),
    )

    customer_id: Mapped[UUID] = mapped_column(
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
    dashboard_area: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="volumetrics",
        server_default="volumetrics",
    )
    record_domain: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="ticket",
        server_default="ticket",
    )
    record_source: Mapped[str] = mapped_column(String(50), nullable=False)
    record_type: Mapped[str] = mapped_column(String(50), nullable=False)
    scope: Mapped[str] = mapped_column(String(50), nullable=False)
    record_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    record_number: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at_source: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    completed_at_source: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_month: Mapped[date | None] = mapped_column(Date, nullable=True)
    completed_month: Mapped[date | None] = mapped_column(Date, nullable=True)
    functional_track: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ams_owner: Mapped[str | None] = mapped_column(String(255), nullable=True)
    functional_track_ams_owner: Mapped[str | None] = mapped_column(String(512), nullable=True)
    assignment_group: Mapped[str | None] = mapped_column(String(255), nullable=True)
    support_group_owner: Mapped[str | None] = mapped_column(String(255), nullable=True)
    assignment_group_support_owner: Mapped[str | None] = mapped_column(String(512), nullable=True)
    parent_business_application: Mapped[str | None] = mapped_column(String(255), nullable=True)
    business_service_ci_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    application_owner: Mapped[str | None] = mapped_column(String(255), nullable=True)
    supported_by_vendor: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sap_non_sap: Mapped[str | None] = mapped_column(String(50), nullable=True)
    architecture_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    application_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    business_critical: Mapped[str | None] = mapped_column(String(255), nullable=True)
    install_status: Mapped[str | None] = mapped_column(String(255), nullable=True)
    install_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    hosting_env: Mapped[str | None] = mapped_column(String(255), nullable=True)
    global_flag: Mapped[str | None] = mapped_column(String(50), nullable=True)
    life_cycle_stage: Mapped[str | None] = mapped_column(String(255), nullable=True)
    life_cycle_stage_status: Mapped[str | None] = mapped_column(String(255), nullable=True)
    priority: Mapped[str | None] = mapped_column(String(50), nullable=True)
    state: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status_group: Mapped[str | None] = mapped_column(String(100), nullable=True)
    data_version: Mapped[str | None] = mapped_column(String(50), nullable=True)

    customer: Mapped[Client] = relationship()
    project: Mapped[Project] = relationship()
