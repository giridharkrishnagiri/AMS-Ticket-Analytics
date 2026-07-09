from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any
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
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.application_dimension import ApplicationDimension
    from app.models.application_inventory_item import ApplicationInventoryItem
    from app.models.project import Project
    from app.models.ticket_raw_row import TicketRawRow
    from app.models.upload_batch import UploadBatch
    from app.models.uploaded_file import UploadedFile


class Ticket(Base):
    __tablename__ = "tickets"
    __table_args__ = (
        Index("ix_tickets_project_type_created_at", "project_id", "ticket_type", "created_at"),
        Index("ix_tickets_project_type_resolved_at", "project_id", "ticket_type", "resolved_at"),
        Index("ix_tickets_project_type_closed_at", "project_id", "ticket_type", "closed_at"),
        Index("ix_tickets_project_type_priority", "project_id", "ticket_type", "priority"),
        Index(
            "ix_tickets_project_type_assignment_group",
            "project_id",
            "ticket_type",
            "assignment_group",
        ),
        Index("ix_tickets_project_type_application", "project_id", "ticket_type", "application"),
        Index("ix_tickets_project_application", "project_id", "application"),
        Index("ix_tickets_project_business_service", "project_id", "business_service"),
        Index("ix_tickets_project_cmdb_ci", "project_id", "cmdb_ci"),
        Index(
            "ix_tickets_project_application_dimension_id",
            "project_id",
            "application_dimension_id",
        ),
        Index("ix_tickets_project_customer_name", "project_id", "customer_name"),
        Index("ix_tickets_project_tower_name", "project_id", "tower_name"),
        Index("ix_tickets_project_cluster_name", "project_id", "cluster_name"),
        Index(
            "ix_tickets_project_application_group_name",
            "project_id",
            "application_group_name",
        ),
        Index("ix_tickets_project_application_name", "project_id", "application_name"),
        Index(
            "ix_tickets_project_application_inventory_id",
            "project_id",
            "application_inventory_id",
        ),
        Index(
            "ix_tickets_project_business_service_ci_name",
            "project_id",
            "business_service_ci_name",
        ),
        Index(
            "ix_tickets_project_parent_application_name",
            "project_id",
            "parent_application_name",
        ),
        Index("ix_tickets_project_application_owner", "project_id", "application_owner"),
        Index("ix_tickets_project_support_lead", "project_id", "support_lead"),
        Index("ix_tickets_project_functional_track", "project_id", "functional_track"),
        Index("ix_tickets_project_ams_owner", "project_id", "ams_owner"),
        Index("ix_tickets_project_supported_by_vendor", "project_id", "supported_by_vendor"),
        Index("ix_tickets_project_sap_non_sap", "project_id", "sap_non_sap"),
        Index("ix_tickets_project_architecture_type", "project_id", "architecture_type"),
        Index("ix_tickets_project_business_critical", "project_id", "business_critical"),
        Index("ix_tickets_project_install_type", "project_id", "install_type"),
        Index("ix_tickets_project_hosting_env", "project_id", "hosting_env"),
        Index("ix_tickets_project_is_batch_related", "project_id", "is_batch_related"),
        Index("ix_tickets_project_vendor", "project_id", "vendor"),
        Index("ix_tickets_project_derived_vendor", "project_id", "derived_vendor"),
        Index("ix_tickets_project_type_sla_breached", "project_id", "ticket_type", "sla_breached"),
        Index("ix_tickets_project_type_reopen_count", "project_id", "ticket_type", "reopen_count"),
        Index(
            "ix_tickets_project_type_reassignment_count",
            "project_id",
            "ticket_type",
            "reassignment_count",
        ),
        Index(
            "ix_tickets_project_type_is_system_created",
            "project_id",
            "ticket_type",
            "is_system_created",
        ),
        Index(
            "ix_tickets_project_type_technical_functional_type",
            "project_id",
            "ticket_type",
            "technical_functional_type",
        ),
        UniqueConstraint("project_id", "ticket_number", name="uq_tickets_project_ticket_number"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    upload_batch_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("upload_batches.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    uploaded_file_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("uploaded_files.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    raw_row_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("ticket_raw_rows.id", ondelete="SET NULL"),
        nullable=True,
        unique=True,
    )
    application_dimension_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("application_dimensions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    application_inventory_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("application_inventory_items.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    ticket_number: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    ticket_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    month_key: Mapped[str | None] = mapped_column(String(7), nullable=True, index=True)
    source_system: Mapped[str | None] = mapped_column(String(120), nullable=True)

    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    short_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    state: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    priority: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    urgency: Mapped[str | None] = mapped_column(String(80), nullable=True)
    impact: Mapped[str | None] = mapped_column(String(80), nullable=True)
    application: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    business_service: Mapped[str | None] = mapped_column(String(255), nullable=True)
    cmdb_ci: Mapped[str | None] = mapped_column(String(255), nullable=True)
    customer_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    tower_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    cluster_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    application_group_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    application_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    assignment_group: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    assigned_to: Mapped[str | None] = mapped_column(String(255), nullable=True)
    requester: Mapped[str | None] = mapped_column(String(255), nullable=True)
    opened_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    category: Mapped[str | None] = mapped_column(String(255), nullable=True)
    subcategory: Mapped[str | None] = mapped_column(String(255), nullable=True)
    catalog_item: Mapped[str | None] = mapped_column(String(255), nullable=True)
    catalog_item_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    catalog_knowledge_base: Mapped[str | None] = mapped_column(Text, nullable=True)
    service_offering: Mapped[str | None] = mapped_column(String(255), nullable=True)
    parent_application_number: Mapped[str | None] = mapped_column(Text, nullable=True)
    parent_application_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    business_service_ci_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    application_owner: Mapped[str | None] = mapped_column(Text, nullable=True)
    support_lead: Mapped[str | None] = mapped_column(Text, nullable=True)
    functional_track: Mapped[str | None] = mapped_column(Text, nullable=True)
    ams_owner: Mapped[str | None] = mapped_column(Text, nullable=True)
    supported_by_vendor: Mapped[str | None] = mapped_column(Text, nullable=True)
    service_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    service_entitlement: Mapped[str | None] = mapped_column(Text, nullable=True)
    assignment_group_owner: Mapped[str | None] = mapped_column(Text, nullable=True)
    sap_non_sap: Mapped[str | None] = mapped_column(Text, nullable=True)
    architecture_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    business_critical: Mapped[str | None] = mapped_column(Text, nullable=True)
    install_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    hosting_env: Mapped[str | None] = mapped_column(Text, nullable=True)
    vendor: Mapped[str | None] = mapped_column(Text, nullable=True)
    derived_vendor: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_batch_related: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    sla_breached: Mapped[bool | None] = mapped_column(Boolean, nullable=True, index=True)
    sla_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sla_elapsed_minutes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
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
    response_sla_selection_source: Mapped[str | None] = mapped_column(
        String(40),
        nullable=True,
    )
    resolution_sla_selection_source: Mapped[str | None] = mapped_column(
        String(40),
        nullable=True,
    )
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
    ola_response_sla_breached: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    ola_resolution_sla_breached: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    ola_response_sla_business_elapsed_seconds: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )
    ola_resolution_sla_business_elapsed_seconds: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )
    ola_response_sla_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    ola_resolution_sla_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    ola_response_sla_definition_name_used: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    ola_resolution_sla_definition_name_used: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    ola_response_sla_selection_source: Mapped[str | None] = mapped_column(
        String(40),
        nullable=True,
    )
    ola_resolution_sla_selection_source: Mapped[str | None] = mapped_column(
        String(40),
        nullable=True,
    )
    ola_response_sla_vendor_used: Mapped[str | None] = mapped_column(Text, nullable=True)
    ola_resolution_sla_vendor_used: Mapped[str | None] = mapped_column(Text, nullable=True)
    ola_response_sla_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    ola_resolution_sla_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    ola_enriched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sla_response_sla_breached: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    sla_resolution_sla_breached: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    sla_response_sla_business_elapsed_seconds: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )
    sla_resolution_sla_business_elapsed_seconds: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )
    sla_response_sla_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    sla_resolution_sla_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    sla_response_sla_definition_name_used: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    sla_resolution_sla_definition_name_used: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    sla_response_sla_selection_source: Mapped[str | None] = mapped_column(
        String(40),
        nullable=True,
    )
    sla_resolution_sla_selection_source: Mapped[str | None] = mapped_column(
        String(40),
        nullable=True,
    )
    sla_response_sla_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    sla_resolution_sla_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    end_to_end_sla_enriched_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    business_duration_seconds: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    reopen_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reassignment_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    is_system_created: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    system_creation_source: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_technical: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    technical_functional_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    technical_functional_confidence: Mapped[float | None] = mapped_column(
        Numeric(5, 4),
        nullable=True,
    )
    technical_functional_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    technical_functional_classified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    classification_level_1: Mapped[str | None] = mapped_column(String(255), nullable=True)
    classification_level_2: Mapped[str | None] = mapped_column(String(255), nullable=True)
    classification_level_3: Mapped[str | None] = mapped_column(String(255), nullable=True)
    classification_level_4: Mapped[str | None] = mapped_column(String(255), nullable=True)
    improvement_area: Mapped[str | None] = mapped_column(String(255), nullable=True)
    estimated_effort_hours: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)

    normalized_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
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

    project: Mapped[Project] = relationship(back_populates="tickets")
    application_dimension: Mapped[ApplicationDimension | None] = relationship(
        back_populates="tickets",
    )
    application_inventory_item: Mapped[ApplicationInventoryItem | None] = relationship(
        back_populates="tickets",
    )
    upload_batch: Mapped[UploadBatch] = relationship(back_populates="tickets")
    uploaded_file: Mapped[UploadedFile | None] = relationship(back_populates="tickets")
    raw_row: Mapped[TicketRawRow | None] = relationship(back_populates="ticket")
