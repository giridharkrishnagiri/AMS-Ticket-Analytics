"""add scope split vendor and vendor aware sla fields

Revision ID: 20260620_0012
Revises: 20260620_0011
Create Date: 2026-06-20 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260620_0012"
down_revision: str | None = "20260620_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("tickets", sa.Column("vendor", sa.Text(), nullable=True))
    op.add_column("tickets", sa.Column("derived_vendor", sa.Text(), nullable=True))
    op.add_column(
        "tickets",
        sa.Column("response_sla_definition_name_used", sa.Text(), nullable=True),
    )
    op.add_column(
        "tickets",
        sa.Column("resolution_sla_definition_name_used", sa.Text(), nullable=True),
    )
    op.add_column("tickets", sa.Column("response_sla_selection_source", sa.String(40), nullable=True))
    op.add_column("tickets", sa.Column("resolution_sla_selection_source", sa.String(40), nullable=True))
    op.add_column("tickets", sa.Column("response_sla_vendor_used", sa.Text(), nullable=True))
    op.add_column("tickets", sa.Column("resolution_sla_vendor_used", sa.Text(), nullable=True))
    op.create_index("ix_tickets_project_vendor", "tickets", ["project_id", "vendor"])
    op.create_index("ix_tickets_project_derived_vendor", "tickets", ["project_id", "derived_vendor"])

    op.create_table(
        "assessment_out_of_scope_tickets",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("upload_batch_id", sa.UUID(), nullable=False),
        sa.Column("source_raw_row_id", sa.UUID(), nullable=True),
        sa.Column("application_inventory_id", sa.UUID(), nullable=True),
        sa.Column("ticket_number", sa.String(255), nullable=False),
        sa.Column("ticket_type", sa.String(40), nullable=False),
        sa.Column("month_key", sa.String(7), nullable=True),
        sa.Column("source_system", sa.String(120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("short_description", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("state", sa.String(120), nullable=True),
        sa.Column("priority", sa.String(80), nullable=True),
        sa.Column("urgency", sa.String(80), nullable=True),
        sa.Column("impact", sa.String(80), nullable=True),
        sa.Column("application", sa.String(255), nullable=True),
        sa.Column("business_service", sa.String(255), nullable=True),
        sa.Column("assignment_group", sa.String(255), nullable=True),
        sa.Column("assigned_to", sa.String(255), nullable=True),
        sa.Column("requester", sa.String(255), nullable=True),
        sa.Column("opened_by", sa.String(255), nullable=True),
        sa.Column("created_by", sa.String(255), nullable=True),
        sa.Column("category", sa.String(255), nullable=True),
        sa.Column("subcategory", sa.String(255), nullable=True),
        sa.Column("catalog_item", sa.String(255), nullable=True),
        sa.Column("service_offering", sa.String(255), nullable=True),
        sa.Column("reopen_count", sa.Integer(), nullable=False),
        sa.Column("reassignment_count", sa.Integer(), nullable=True),
        sa.Column("business_duration_seconds", sa.BigInteger(), nullable=True),
        sa.Column("is_system_created", sa.Boolean(), nullable=True),
        sa.Column("system_creation_source", sa.String(255), nullable=True),
        sa.Column("is_technical", sa.Boolean(), nullable=True),
        sa.Column("technical_functional_type", sa.String(40), nullable=True),
        sa.Column("technical_functional_confidence", sa.Numeric(5, 4), nullable=True),
        sa.Column("technical_functional_reason", sa.Text(), nullable=True),
        sa.Column("classification_level_1", sa.String(255), nullable=True),
        sa.Column("classification_level_2", sa.String(255), nullable=True),
        sa.Column("classification_level_3", sa.String(255), nullable=True),
        sa.Column("classification_level_4", sa.String(255), nullable=True),
        sa.Column("improvement_area", sa.String(255), nullable=True),
        sa.Column("estimated_effort_hours", sa.Numeric(12, 2), nullable=True),
        sa.Column("vendor", sa.Text(), nullable=True),
        sa.Column("derived_vendor", sa.Text(), nullable=True),
        sa.Column("parent_application_number", sa.Text(), nullable=True),
        sa.Column("parent_application_name", sa.Text(), nullable=True),
        sa.Column("business_service_ci_name", sa.Text(), nullable=True),
        sa.Column("application_owner", sa.Text(), nullable=True),
        sa.Column("support_lead", sa.Text(), nullable=True),
        sa.Column("functional_track", sa.Text(), nullable=True),
        sa.Column("ams_owner", sa.Text(), nullable=True),
        sa.Column("supported_by_vendor", sa.Text(), nullable=True),
        sa.Column("assignment_group_owner", sa.Text(), nullable=True),
        sa.Column("response_sla_breached", sa.Boolean(), nullable=True),
        sa.Column("resolution_sla_breached", sa.Boolean(), nullable=True),
        sa.Column("response_sla_business_elapsed_seconds", sa.BigInteger(), nullable=True),
        sa.Column("resolution_sla_business_elapsed_seconds", sa.BigInteger(), nullable=True),
        sa.Column("response_sla_name", sa.Text(), nullable=True),
        sa.Column("resolution_sla_name", sa.Text(), nullable=True),
        sa.Column("response_sla_definition_name_used", sa.Text(), nullable=True),
        sa.Column("resolution_sla_definition_name_used", sa.Text(), nullable=True),
        sa.Column("response_sla_selection_source", sa.String(40), nullable=True),
        sa.Column("resolution_sla_selection_source", sa.String(40), nullable=True),
        sa.Column("response_sla_vendor_used", sa.Text(), nullable=True),
        sa.Column("resolution_sla_vendor_used", sa.Text(), nullable=True),
        sa.Column("response_sla_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution_sla_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sla_enriched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("out_of_scope_reason", sa.String(120), nullable=False),
        sa.Column(
            "ingested_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "record_updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["application_inventory_id"], ["application_inventory_items.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_raw_row_id"], ["ticket_raw_rows.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["upload_batch_id"], ["upload_batches.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    for name, columns in {
        "ix_oos_tickets_project_id": ["project_id"],
        "ix_oos_tickets_upload_batch_id": ["upload_batch_id"],
        "ix_oos_tickets_source_raw_row_id": ["source_raw_row_id"],
        "ix_oos_tickets_ticket_number": ["ticket_number"],
        "ix_oos_tickets_ticket_type": ["ticket_type"],
        "ix_oos_tickets_assignment_group": ["assignment_group"],
        "ix_oos_tickets_business_service": ["business_service"],
        "ix_oos_tickets_vendor": ["vendor"],
        "ix_oos_tickets_derived_vendor": ["derived_vendor"],
        "ix_oos_tickets_functional_track": ["functional_track"],
        "ix_oos_tickets_ams_owner": ["ams_owner"],
        "ix_oos_tickets_parent_application_name": ["parent_application_name"],
        "ix_oos_tickets_business_service_ci_name": ["business_service_ci_name"],
        "ix_oos_tickets_support_lead": ["support_lead"],
        "ix_oos_tickets_created_at": ["created_at"],
        "ix_oos_tickets_resolved_at": ["resolved_at"],
        "ix_oos_tickets_closed_at": ["closed_at"],
        "ix_oos_tickets_priority": ["priority"],
        "ix_oos_tickets_state": ["state"],
    }.items():
        op.create_index(name, "assessment_out_of_scope_tickets", columns)


def downgrade() -> None:
    for name in (
        "ix_oos_tickets_state",
        "ix_oos_tickets_priority",
        "ix_oos_tickets_closed_at",
        "ix_oos_tickets_resolved_at",
        "ix_oos_tickets_created_at",
        "ix_oos_tickets_support_lead",
        "ix_oos_tickets_business_service_ci_name",
        "ix_oos_tickets_parent_application_name",
        "ix_oos_tickets_ams_owner",
        "ix_oos_tickets_functional_track",
        "ix_oos_tickets_derived_vendor",
        "ix_oos_tickets_vendor",
        "ix_oos_tickets_business_service",
        "ix_oos_tickets_assignment_group",
        "ix_oos_tickets_ticket_type",
        "ix_oos_tickets_ticket_number",
        "ix_oos_tickets_source_raw_row_id",
        "ix_oos_tickets_upload_batch_id",
        "ix_oos_tickets_project_id",
    ):
        op.drop_index(name, table_name="assessment_out_of_scope_tickets")
    op.drop_table("assessment_out_of_scope_tickets")

    op.drop_index("ix_tickets_project_derived_vendor", table_name="tickets")
    op.drop_index("ix_tickets_project_vendor", table_name="tickets")
    op.drop_column("tickets", "resolution_sla_vendor_used")
    op.drop_column("tickets", "response_sla_vendor_used")
    op.drop_column("tickets", "resolution_sla_selection_source")
    op.drop_column("tickets", "response_sla_selection_source")
    op.drop_column("tickets", "resolution_sla_definition_name_used")
    op.drop_column("tickets", "response_sla_definition_name_used")
    op.drop_column("tickets", "derived_vendor")
    op.drop_column("tickets", "vendor")
