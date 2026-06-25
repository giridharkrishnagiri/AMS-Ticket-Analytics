from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.application_inventory_item import ApplicationInventoryItem
    from app.models.project import Project
    from app.models.ticket_raw_row import TicketRawRow
    from app.models.upload_batch import UploadBatch


class AssessmentOutOfScopeTicket(Base):
    __tablename__ = "assessment_out_of_scope_tickets"
    __table_args__ = (
        Index("ix_oos_tickets_project_id", "project_id"),
        Index("ix_oos_tickets_upload_batch_id", "upload_batch_id"),
        Index("ix_oos_tickets_source_raw_row_id", "source_raw_row_id"),
        Index("ix_oos_tickets_ticket_number", "ticket_number"),
        Index("ix_oos_tickets_ticket_type", "ticket_type"),
        Index("ix_oos_tickets_assignment_group", "assignment_group"),
        Index("ix_oos_tickets_business_service", "business_service"),
        Index("ix_oos_tickets_vendor", "vendor"),
        Index("ix_oos_tickets_derived_vendor", "derived_vendor"),
        Index("ix_oos_tickets_functional_track", "functional_track"),
        Index("ix_oos_tickets_ams_owner", "ams_owner"),
        Index("ix_oos_tickets_parent_application_name", "parent_application_name"),
        Index("ix_oos_tickets_business_service_ci_name", "business_service_ci_name"),
        Index("ix_oos_tickets_support_lead", "support_lead"),
        Index("ix_oos_tickets_project_sap_non_sap", "project_id", "sap_non_sap"),
        Index("ix_oos_tickets_project_architecture_type", "project_id", "architecture_type"),
        Index("ix_oos_tickets_project_install_type", "project_id", "install_type"),
        Index("ix_oos_tickets_project_is_batch_related", "project_id", "is_batch_related"),
        Index("ix_oos_tickets_created_at", "created_at"),
        Index("ix_oos_tickets_resolved_at", "resolved_at"),
        Index("ix_oos_tickets_closed_at", "closed_at"),
        Index("ix_oos_tickets_priority", "priority"),
        Index("ix_oos_tickets_state", "state"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    upload_batch_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("upload_batches.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_raw_row_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("ticket_raw_rows.id", ondelete="SET NULL"),
        nullable=True,
    )
    application_inventory_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("application_inventory_items.id", ondelete="SET NULL"),
        nullable=True,
    )

    ticket_number: Mapped[str] = mapped_column(String(255), nullable=False)
    ticket_type: Mapped[str] = mapped_column(String(40), nullable=False)
    month_key: Mapped[str | None] = mapped_column(String(7), nullable=True)
    source_system: Mapped[str | None] = mapped_column(String(120), nullable=True)

    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    short_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    state: Mapped[str | None] = mapped_column(String(120), nullable=True)
    priority: Mapped[str | None] = mapped_column(String(80), nullable=True)
    urgency: Mapped[str | None] = mapped_column(String(80), nullable=True)
    impact: Mapped[str | None] = mapped_column(String(80), nullable=True)
    application: Mapped[str | None] = mapped_column(String(255), nullable=True)
    business_service: Mapped[str | None] = mapped_column(String(255), nullable=True)
    assignment_group: Mapped[str | None] = mapped_column(String(255), nullable=True)
    assigned_to: Mapped[str | None] = mapped_column(String(255), nullable=True)
    requester: Mapped[str | None] = mapped_column(String(255), nullable=True)
    opened_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    category: Mapped[str | None] = mapped_column(String(255), nullable=True)
    subcategory: Mapped[str | None] = mapped_column(String(255), nullable=True)
    catalog_item: Mapped[str | None] = mapped_column(String(255), nullable=True)
    service_offering: Mapped[str | None] = mapped_column(String(255), nullable=True)

    reopen_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reassignment_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    business_duration_seconds: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    is_system_created: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    system_creation_source: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_technical: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    technical_functional_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    technical_functional_confidence: Mapped[float | None] = mapped_column(
        Numeric(5, 4),
        nullable=True,
    )
    technical_functional_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    classification_level_1: Mapped[str | None] = mapped_column(String(255), nullable=True)
    classification_level_2: Mapped[str | None] = mapped_column(String(255), nullable=True)
    classification_level_3: Mapped[str | None] = mapped_column(String(255), nullable=True)
    classification_level_4: Mapped[str | None] = mapped_column(String(255), nullable=True)
    improvement_area: Mapped[str | None] = mapped_column(String(255), nullable=True)
    estimated_effort_hours: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)

    vendor: Mapped[str | None] = mapped_column(Text, nullable=True)
    derived_vendor: Mapped[str | None] = mapped_column(Text, nullable=True)
    parent_application_number: Mapped[str | None] = mapped_column(Text, nullable=True)
    parent_application_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    business_service_ci_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    application_owner: Mapped[str | None] = mapped_column(Text, nullable=True)
    support_lead: Mapped[str | None] = mapped_column(Text, nullable=True)
    functional_track: Mapped[str | None] = mapped_column(Text, nullable=True)
    ams_owner: Mapped[str | None] = mapped_column(Text, nullable=True)
    supported_by_vendor: Mapped[str | None] = mapped_column(Text, nullable=True)
    assignment_group_owner: Mapped[str | None] = mapped_column(Text, nullable=True)
    sap_non_sap: Mapped[str | None] = mapped_column(Text, nullable=True)
    architecture_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    install_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_batch_related: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    response_sla_breached: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    resolution_sla_breached: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    response_sla_business_elapsed_seconds: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )
    resolution_sla_business_elapsed_seconds: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )
    response_sla_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolution_sla_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    response_sla_definition_name_used: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolution_sla_definition_name_used: Mapped[str | None] = mapped_column(Text, nullable=True)
    response_sla_selection_source: Mapped[str | None] = mapped_column(String(40), nullable=True)
    resolution_sla_selection_source: Mapped[str | None] = mapped_column(String(40), nullable=True)
    response_sla_vendor_used: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolution_sla_vendor_used: Mapped[str | None] = mapped_column(Text, nullable=True)
    response_sla_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    resolution_sla_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    sla_enriched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    out_of_scope_reason: Mapped[str] = mapped_column(String(120), nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    record_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    project: Mapped[Project] = relationship()
    upload_batch: Mapped[UploadBatch] = relationship()
    source_raw_row: Mapped[TicketRawRow | None] = relationship()
    application_inventory_item: Mapped[ApplicationInventoryItem | None] = relationship()
