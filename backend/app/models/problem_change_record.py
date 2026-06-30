from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin, UuidPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.application_inventory_item import ApplicationInventoryItem
    from app.models.project import Project
    from app.models.ticket_raw_row import TicketRawRow
    from app.models.upload_batch import UploadBatch
    from app.models.uploaded_file import UploadedFile


class AssessmentProblemRecord(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "assessment_problem_records"
    __table_args__ = (
        Index("ix_problem_records_project_number", "project_id", "number"),
        Index("ix_problem_records_project_row_fingerprint", "project_id", "row_fingerprint"),
        Index("ix_problem_records_upload_batch", "upload_batch_id"),
        Index("ix_problem_records_uploaded_file", "uploaded_file_id"),
        Index("ix_problem_records_raw_row", "raw_row_id"),
        Index("ix_problem_records_assignment_group", "project_id", "assignment_group"),
        Index("ix_problem_records_functional_track", "project_id", "functional_track"),
        Index("ix_problem_records_ams_owner", "project_id", "ams_owner"),
        Index("ix_problem_records_sap_non_sap", "project_id", "sap_non_sap"),
        UniqueConstraint(
            "project_id",
            "row_fingerprint",
            name="uq_assessment_problem_records_project_row_fingerprint",
        ),
    )

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
    uploaded_file_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("uploaded_files.id", ondelete="SET NULL"),
        nullable=True,
    )
    raw_row_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("ticket_raw_rows.id", ondelete="SET NULL"),
        nullable=True,
        unique=True,
    )
    application_inventory_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("application_inventory_items.id", ondelete="SET NULL"),
        nullable=True,
    )

    source_row_number: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    row_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    number: Mapped[str] = mapped_column(String(255), nullable=False)
    state: Mapped[str | None] = mapped_column(String(120), nullable=True)
    problem_state: Mapped[str | None] = mapped_column(String(120), nullable=True)
    problem_statement: Mapped[str | None] = mapped_column(Text, nullable=True)
    short_description_or_statement: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    business_application: Mapped[str | None] = mapped_column(Text, nullable=True)
    business_service: Mapped[str | None] = mapped_column(Text, nullable=True)
    configuration_item: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str | None] = mapped_column(String(255), nullable=True)
    subcategory: Mapped[str | None] = mapped_column(String(255), nullable=True)
    assignment_group: Mapped[str | None] = mapped_column(Text, nullable=True)
    assigned_to: Mapped[str | None] = mapped_column(Text, nullable=True)
    urgency: Mapped[str | None] = mapped_column(String(80), nullable=True)
    priority: Mapped[str | None] = mapped_column(String(80), nullable=True)
    active: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    created_at_source: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    actual_start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    actual_end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    business_duration_seconds: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    made_sla: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    major_incident: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    major_problem: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    known_error: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    related_incidents: Mapped[str | None] = mapped_column(Text, nullable=True)
    linked_incident_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    change_request: Mapped[str | None] = mapped_column(Text, nullable=True)
    caused_by_change: Mapped[str | None] = mapped_column(Text, nullable=True)
    duplicate_of: Mapped[str | None] = mapped_column(Text, nullable=True)
    parent: Mapped[str | None] = mapped_column(Text, nullable=True)
    reassignment_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reopen_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    resolution_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    close_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    cause_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    fix_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    workaround: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str | None] = mapped_column(String(120), nullable=True)
    contact_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    company: Mapped[str | None] = mapped_column(Text, nullable=True)
    vendor_or_supplier_if_available: Mapped[str | None] = mapped_column(Text, nullable=True)

    functional_track: Mapped[str | None] = mapped_column(Text, nullable=True)
    ams_owner: Mapped[str | None] = mapped_column(Text, nullable=True)
    parent_business_application: Mapped[str | None] = mapped_column(Text, nullable=True)
    supported_by_vendor: Mapped[str | None] = mapped_column(Text, nullable=True)
    sap_non_sap: Mapped[str | None] = mapped_column(Text, nullable=True)
    architecture_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    install_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    application_inventory_match_status: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        default="unmatched",
    )
    normalized_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    project: Mapped[Project] = relationship()
    upload_batch: Mapped[UploadBatch] = relationship()
    uploaded_file: Mapped[UploadedFile | None] = relationship()
    raw_row: Mapped[TicketRawRow | None] = relationship()
    application_inventory_item: Mapped[ApplicationInventoryItem | None] = relationship()


class AssessmentOutOfScopeProblemRecord(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "assessment_out_of_scope_problem_records"
    __table_args__ = (
        Index("ix_oos_problem_records_project_number", "project_id", "number"),
        Index(
            "ix_oos_problem_records_project_row_fingerprint",
            "project_id",
            "row_fingerprint",
        ),
        Index("ix_oos_problem_records_upload_batch", "upload_batch_id"),
        Index("ix_oos_problem_records_uploaded_file", "uploaded_file_id"),
        Index("ix_oos_problem_records_raw_row", "raw_row_id"),
        Index("ix_oos_problem_records_assignment_group", "project_id", "assignment_group"),
        Index("ix_oos_problem_records_functional_track", "project_id", "functional_track"),
        Index("ix_oos_problem_records_ams_owner", "project_id", "ams_owner"),
        Index("ix_oos_problem_records_sap_non_sap", "project_id", "sap_non_sap"),
        Index(
            "ix_oos_problem_records_created_at_source",
            "project_id",
            "created_at_source",
        ),
        Index("ix_oos_problem_records_closed_at", "project_id", "closed_at"),
        Index(
            "ix_oos_problem_records_project_linked_incident_count",
            "project_id",
            "linked_incident_count",
        ),
        UniqueConstraint(
            "project_id",
            "row_fingerprint",
            name="uq_oos_problem_records_project_row_fingerprint",
        ),
    )

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
    uploaded_file_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("uploaded_files.id", ondelete="SET NULL"),
        nullable=True,
    )
    raw_row_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("ticket_raw_rows.id", ondelete="SET NULL"),
        nullable=True,
        unique=True,
    )
    application_inventory_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("application_inventory_items.id", ondelete="SET NULL"),
        nullable=True,
    )

    source_row_number: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    row_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    number: Mapped[str] = mapped_column(String(255), nullable=False)
    state: Mapped[str | None] = mapped_column(String(120), nullable=True)
    problem_state: Mapped[str | None] = mapped_column(String(120), nullable=True)
    problem_statement: Mapped[str | None] = mapped_column(Text, nullable=True)
    short_description_or_statement: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    business_application: Mapped[str | None] = mapped_column(Text, nullable=True)
    business_service: Mapped[str | None] = mapped_column(Text, nullable=True)
    configuration_item: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str | None] = mapped_column(String(255), nullable=True)
    subcategory: Mapped[str | None] = mapped_column(String(255), nullable=True)
    assignment_group: Mapped[str | None] = mapped_column(Text, nullable=True)
    assigned_to: Mapped[str | None] = mapped_column(Text, nullable=True)
    urgency: Mapped[str | None] = mapped_column(String(80), nullable=True)
    priority: Mapped[str | None] = mapped_column(String(80), nullable=True)
    active: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    created_at_source: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    actual_start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    actual_end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    business_duration_seconds: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    made_sla: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    major_incident: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    major_problem: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    known_error: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    related_incidents: Mapped[str | None] = mapped_column(Text, nullable=True)
    linked_incident_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    change_request: Mapped[str | None] = mapped_column(Text, nullable=True)
    caused_by_change: Mapped[str | None] = mapped_column(Text, nullable=True)
    duplicate_of: Mapped[str | None] = mapped_column(Text, nullable=True)
    parent: Mapped[str | None] = mapped_column(Text, nullable=True)
    reassignment_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reopen_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    resolution_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    close_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    cause_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    fix_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    workaround: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str | None] = mapped_column(String(120), nullable=True)
    contact_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    company: Mapped[str | None] = mapped_column(Text, nullable=True)
    vendor_or_supplier_if_available: Mapped[str | None] = mapped_column(Text, nullable=True)

    functional_track: Mapped[str | None] = mapped_column(Text, nullable=True)
    ams_owner: Mapped[str | None] = mapped_column(Text, nullable=True)
    parent_business_application: Mapped[str | None] = mapped_column(Text, nullable=True)
    supported_by_vendor: Mapped[str | None] = mapped_column(Text, nullable=True)
    sap_non_sap: Mapped[str | None] = mapped_column(Text, nullable=True)
    architecture_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    install_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    application_inventory_match_status: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        default="unmatched",
    )
    out_of_scope_reason: Mapped[str] = mapped_column(String(120), nullable=False)
    normalized_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    project: Mapped[Project] = relationship()
    upload_batch: Mapped[UploadBatch] = relationship()
    uploaded_file: Mapped[UploadedFile | None] = relationship()
    raw_row: Mapped[TicketRawRow | None] = relationship()
    application_inventory_item: Mapped[ApplicationInventoryItem | None] = relationship()


class AssessmentChangeRecord(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "assessment_change_records"
    __table_args__ = (
        Index("ix_change_records_project_number", "project_id", "number"),
        Index("ix_change_records_project_row_fingerprint", "project_id", "row_fingerprint"),
        Index("ix_change_records_upload_batch", "upload_batch_id"),
        Index("ix_change_records_uploaded_file", "uploaded_file_id"),
        Index("ix_change_records_raw_row", "raw_row_id"),
        Index("ix_change_records_assignment_group", "project_id", "assignment_group"),
        Index("ix_change_records_functional_track", "project_id", "functional_track"),
        Index("ix_change_records_ams_owner", "project_id", "ams_owner"),
        Index("ix_change_records_sap_non_sap", "project_id", "sap_non_sap"),
        UniqueConstraint(
            "project_id",
            "row_fingerprint",
            name="uq_assessment_change_records_project_row_fingerprint",
        ),
    )

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
    uploaded_file_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("uploaded_files.id", ondelete="SET NULL"),
        nullable=True,
    )
    raw_row_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("ticket_raw_rows.id", ondelete="SET NULL"),
        nullable=True,
        unique=True,
    )
    application_inventory_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("application_inventory_items.id", ondelete="SET NULL"),
        nullable=True,
    )

    source_row_number: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    row_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    number: Mapped[str] = mapped_column(String(255), nullable=False)
    short_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    state: Mapped[str | None] = mapped_column(String(120), nullable=True)
    phase: Mapped[str | None] = mapped_column(String(120), nullable=True)
    phase_state: Mapped[str | None] = mapped_column(String(120), nullable=True)
    business_application: Mapped[str | None] = mapped_column(Text, nullable=True)
    business_service: Mapped[str | None] = mapped_column(Text, nullable=True)
    application_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    affected_ci_service: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str | None] = mapped_column(String(255), nullable=True)
    assignment_group: Mapped[str | None] = mapped_column(Text, nullable=True)
    assigned_to: Mapped[str | None] = mapped_column(Text, nullable=True)
    priority: Mapped[str | None] = mapped_column(String(80), nullable=True)
    urgency: Mapped[str | None] = mapped_column(String(80), nullable=True)
    impact: Mapped[str | None] = mapped_column(String(80), nullable=True)
    risk: Mapped[str | None] = mapped_column(String(120), nullable=True)
    risk_value: Mapped[str | None] = mapped_column(String(120), nullable=True)
    vendor: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at_source: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    planned_start_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    planned_end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    actual_start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    actual_end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    business_duration_seconds: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    made_sla: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    unauthorized: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    outside_maintenance_schedule: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    cab_required: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    cab_approval: Mapped[str | None] = mapped_column(Text, nullable=True)
    cab_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    change_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    close_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    close_code_sub_category: Mapped[str | None] = mapped_column(Text, nullable=True)
    incident: Mapped[str | None] = mapped_column(Text, nullable=True)
    problem: Mapped[str | None] = mapped_column(Text, nullable=True)
    caused_by_change: Mapped[str | None] = mapped_column(Text, nullable=True)
    parent: Mapped[str | None] = mapped_column(Text, nullable=True)
    reassignment_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    service_outage_required: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    implementation_plan: Mapped[str | None] = mapped_column(Text, nullable=True)
    backout_plan: Mapped[str | None] = mapped_column(Text, nullable=True)
    test_plan: Mapped[str | None] = mapped_column(Text, nullable=True)
    communication_plan: Mapped[str | None] = mapped_column(Text, nullable=True)

    functional_track: Mapped[str | None] = mapped_column(Text, nullable=True)
    ams_owner: Mapped[str | None] = mapped_column(Text, nullable=True)
    parent_business_application: Mapped[str | None] = mapped_column(Text, nullable=True)
    supported_by_vendor: Mapped[str | None] = mapped_column(Text, nullable=True)
    sap_non_sap: Mapped[str | None] = mapped_column(Text, nullable=True)
    architecture_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    install_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    application_inventory_match_status: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        default="unmatched",
    )
    normalized_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    project: Mapped[Project] = relationship()
    upload_batch: Mapped[UploadBatch] = relationship()
    uploaded_file: Mapped[UploadedFile | None] = relationship()
    raw_row: Mapped[TicketRawRow | None] = relationship()
    application_inventory_item: Mapped[ApplicationInventoryItem | None] = relationship()


class AssessmentOutOfScopeChangeRecord(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "assessment_out_of_scope_change_records"
    __table_args__ = (
        Index("ix_oos_change_records_project_number", "project_id", "number"),
        Index(
            "ix_oos_change_records_project_row_fingerprint",
            "project_id",
            "row_fingerprint",
        ),
        Index("ix_oos_change_records_upload_batch", "upload_batch_id"),
        Index("ix_oos_change_records_uploaded_file", "uploaded_file_id"),
        Index("ix_oos_change_records_raw_row", "raw_row_id"),
        Index("ix_oos_change_records_assignment_group", "project_id", "assignment_group"),
        Index("ix_oos_change_records_functional_track", "project_id", "functional_track"),
        Index("ix_oos_change_records_ams_owner", "project_id", "ams_owner"),
        Index("ix_oos_change_records_sap_non_sap", "project_id", "sap_non_sap"),
        Index(
            "ix_oos_change_records_created_at_source",
            "project_id",
            "created_at_source",
        ),
        Index("ix_oos_change_records_closed_at", "project_id", "closed_at"),
        UniqueConstraint(
            "project_id",
            "row_fingerprint",
            name="uq_oos_change_records_project_row_fingerprint",
        ),
    )

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
    uploaded_file_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("uploaded_files.id", ondelete="SET NULL"),
        nullable=True,
    )
    raw_row_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("ticket_raw_rows.id", ondelete="SET NULL"),
        nullable=True,
        unique=True,
    )
    application_inventory_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("application_inventory_items.id", ondelete="SET NULL"),
        nullable=True,
    )

    source_row_number: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    row_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    number: Mapped[str] = mapped_column(String(255), nullable=False)
    short_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    state: Mapped[str | None] = mapped_column(String(120), nullable=True)
    phase: Mapped[str | None] = mapped_column(String(120), nullable=True)
    phase_state: Mapped[str | None] = mapped_column(String(120), nullable=True)
    business_application: Mapped[str | None] = mapped_column(Text, nullable=True)
    business_service: Mapped[str | None] = mapped_column(Text, nullable=True)
    application_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    affected_ci_service: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str | None] = mapped_column(String(255), nullable=True)
    assignment_group: Mapped[str | None] = mapped_column(Text, nullable=True)
    assigned_to: Mapped[str | None] = mapped_column(Text, nullable=True)
    priority: Mapped[str | None] = mapped_column(String(80), nullable=True)
    urgency: Mapped[str | None] = mapped_column(String(80), nullable=True)
    impact: Mapped[str | None] = mapped_column(String(80), nullable=True)
    risk: Mapped[str | None] = mapped_column(String(120), nullable=True)
    risk_value: Mapped[str | None] = mapped_column(String(120), nullable=True)
    vendor: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at_source: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    planned_start_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    planned_end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    actual_start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    actual_end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    business_duration_seconds: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    made_sla: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    unauthorized: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    outside_maintenance_schedule: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    cab_required: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    cab_approval: Mapped[str | None] = mapped_column(Text, nullable=True)
    cab_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    change_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    close_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    close_code_sub_category: Mapped[str | None] = mapped_column(Text, nullable=True)
    incident: Mapped[str | None] = mapped_column(Text, nullable=True)
    problem: Mapped[str | None] = mapped_column(Text, nullable=True)
    caused_by_change: Mapped[str | None] = mapped_column(Text, nullable=True)
    parent: Mapped[str | None] = mapped_column(Text, nullable=True)
    reassignment_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    service_outage_required: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    implementation_plan: Mapped[str | None] = mapped_column(Text, nullable=True)
    backout_plan: Mapped[str | None] = mapped_column(Text, nullable=True)
    test_plan: Mapped[str | None] = mapped_column(Text, nullable=True)
    communication_plan: Mapped[str | None] = mapped_column(Text, nullable=True)

    functional_track: Mapped[str | None] = mapped_column(Text, nullable=True)
    ams_owner: Mapped[str | None] = mapped_column(Text, nullable=True)
    parent_business_application: Mapped[str | None] = mapped_column(Text, nullable=True)
    supported_by_vendor: Mapped[str | None] = mapped_column(Text, nullable=True)
    sap_non_sap: Mapped[str | None] = mapped_column(Text, nullable=True)
    architecture_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    install_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    application_inventory_match_status: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        default="unmatched",
    )
    out_of_scope_reason: Mapped[str] = mapped_column(String(120), nullable=False)
    normalized_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    project: Mapped[Project] = relationship()
    upload_batch: Mapped[UploadBatch] = relationship()
    uploaded_file: Mapped[UploadedFile | None] = relationship()
    raw_row: Mapped[TicketRawRow | None] = relationship()
    application_inventory_item: Mapped[ApplicationInventoryItem | None] = relationship()
