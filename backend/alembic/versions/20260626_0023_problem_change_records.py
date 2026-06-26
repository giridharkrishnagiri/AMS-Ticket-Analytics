"""add problem and change normalized records

Revision ID: 20260626_0023
Revises: 20260626_0022
Create Date: 2026-06-26 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260626_0023"
down_revision: str | None = "20260626_0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def common_columns() -> list[sa.Column]:
    return [
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("upload_batch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("uploaded_file_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("raw_row_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("application_inventory_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_row_number", sa.BigInteger(), nullable=True),
        sa.Column("row_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("number", sa.String(length=255), nullable=False),
    ]


def enrichment_columns() -> list[sa.Column]:
    return [
        sa.Column("functional_track", sa.Text(), nullable=True),
        sa.Column("ams_owner", sa.Text(), nullable=True),
        sa.Column("parent_business_application", sa.Text(), nullable=True),
        sa.Column("supported_by_vendor", sa.Text(), nullable=True),
        sa.Column("sap_non_sap", sa.Text(), nullable=True),
        sa.Column("architecture_type", sa.Text(), nullable=True),
        sa.Column("install_type", sa.Text(), nullable=True),
        sa.Column(
            "application_inventory_match_status",
            sa.String(length=40),
            nullable=False,
            server_default="unmatched",
        ),
        sa.Column("normalized_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def foreign_keys(table_name: str) -> list[sa.ForeignKeyConstraint]:
    return [
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["upload_batch_id"], ["upload_batches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["uploaded_file_id"], ["uploaded_files.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["raw_row_id"], ["ticket_raw_rows.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["application_inventory_id"],
            ["application_inventory_items.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("raw_row_id", name=f"uq_{table_name}_raw_row_id"),
        sa.UniqueConstraint(
            "project_id",
            "row_fingerprint",
            name=f"uq_{table_name}_project_row_fingerprint",
        ),
    ]


def create_problem_table() -> None:
    if table_exists("assessment_problem_records"):
        return
    op.create_table(
        "assessment_problem_records",
        *common_columns(),
        sa.Column("state", sa.String(length=120), nullable=True),
        sa.Column("problem_state", sa.String(length=120), nullable=True),
        sa.Column("problem_statement", sa.Text(), nullable=True),
        sa.Column("short_description_or_statement", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("business_application", sa.Text(), nullable=True),
        sa.Column("business_service", sa.Text(), nullable=True),
        sa.Column("configuration_item", sa.Text(), nullable=True),
        sa.Column("category", sa.String(length=255), nullable=True),
        sa.Column("subcategory", sa.String(length=255), nullable=True),
        sa.Column("assignment_group", sa.Text(), nullable=True),
        sa.Column("assigned_to", sa.Text(), nullable=True),
        sa.Column("urgency", sa.String(length=80), nullable=True),
        sa.Column("priority", sa.String(length=80), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=True),
        sa.Column("created_at_source", sa.DateTime(timezone=True), nullable=True),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actual_start_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actual_end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("business_duration_seconds", sa.BigInteger(), nullable=True),
        sa.Column("duration_seconds", sa.BigInteger(), nullable=True),
        sa.Column("made_sla", sa.Boolean(), nullable=True),
        sa.Column("major_incident", sa.Boolean(), nullable=True),
        sa.Column("major_problem", sa.Boolean(), nullable=True),
        sa.Column("known_error", sa.Boolean(), nullable=True),
        sa.Column("related_incidents", sa.Text(), nullable=True),
        sa.Column("change_request", sa.Text(), nullable=True),
        sa.Column("caused_by_change", sa.Text(), nullable=True),
        sa.Column("duplicate_of", sa.Text(), nullable=True),
        sa.Column("parent", sa.Text(), nullable=True),
        sa.Column("reassignment_count", sa.Integer(), nullable=True),
        sa.Column("reopen_count", sa.Integer(), nullable=True),
        sa.Column("resolution_code", sa.Text(), nullable=True),
        sa.Column("close_notes", sa.Text(), nullable=True),
        sa.Column("cause_notes", sa.Text(), nullable=True),
        sa.Column("fix_notes", sa.Text(), nullable=True),
        sa.Column("workaround", sa.Text(), nullable=True),
        sa.Column("source", sa.String(length=120), nullable=True),
        sa.Column("contact_type", sa.String(length=120), nullable=True),
        sa.Column("company", sa.Text(), nullable=True),
        sa.Column("vendor_or_supplier_if_available", sa.Text(), nullable=True),
        *enrichment_columns(),
        *foreign_keys("assessment_problem_records"),
    )
    create_common_indexes("assessment_problem_records", "problem_records")


def create_change_table() -> None:
    if table_exists("assessment_change_records"):
        return
    op.create_table(
        "assessment_change_records",
        *common_columns(),
        sa.Column("short_description", sa.Text(), nullable=True),
        sa.Column("type", sa.String(length=120), nullable=True),
        sa.Column("state", sa.String(length=120), nullable=True),
        sa.Column("phase", sa.String(length=120), nullable=True),
        sa.Column("phase_state", sa.String(length=120), nullable=True),
        sa.Column("business_application", sa.Text(), nullable=True),
        sa.Column("business_service", sa.Text(), nullable=True),
        sa.Column("application_name", sa.Text(), nullable=True),
        sa.Column("affected_ci_service", sa.Text(), nullable=True),
        sa.Column("category", sa.String(length=255), nullable=True),
        sa.Column("assignment_group", sa.Text(), nullable=True),
        sa.Column("assigned_to", sa.Text(), nullable=True),
        sa.Column("priority", sa.String(length=80), nullable=True),
        sa.Column("urgency", sa.String(length=80), nullable=True),
        sa.Column("impact", sa.String(length=80), nullable=True),
        sa.Column("risk", sa.String(length=120), nullable=True),
        sa.Column("risk_value", sa.String(length=120), nullable=True),
        sa.Column("vendor", sa.Text(), nullable=True),
        sa.Column("created_at_source", sa.DateTime(timezone=True), nullable=True),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("planned_start_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("planned_end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actual_start_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actual_end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("business_duration_seconds", sa.BigInteger(), nullable=True),
        sa.Column("duration_seconds", sa.BigInteger(), nullable=True),
        sa.Column("made_sla", sa.Boolean(), nullable=True),
        sa.Column("unauthorized", sa.Boolean(), nullable=True),
        sa.Column("outside_maintenance_schedule", sa.Boolean(), nullable=True),
        sa.Column("cab_required", sa.Boolean(), nullable=True),
        sa.Column("cab_approval", sa.Text(), nullable=True),
        sa.Column("cab_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("change_reason", sa.Text(), nullable=True),
        sa.Column("close_code", sa.Text(), nullable=True),
        sa.Column("close_code_sub_category", sa.Text(), nullable=True),
        sa.Column("incident", sa.Text(), nullable=True),
        sa.Column("problem", sa.Text(), nullable=True),
        sa.Column("caused_by_change", sa.Text(), nullable=True),
        sa.Column("parent", sa.Text(), nullable=True),
        sa.Column("reassignment_count", sa.Integer(), nullable=True),
        sa.Column("service_outage_required", sa.Boolean(), nullable=True),
        sa.Column("implementation_plan", sa.Text(), nullable=True),
        sa.Column("backout_plan", sa.Text(), nullable=True),
        sa.Column("test_plan", sa.Text(), nullable=True),
        sa.Column("communication_plan", sa.Text(), nullable=True),
        *enrichment_columns(),
        *foreign_keys("assessment_change_records"),
    )
    create_common_indexes("assessment_change_records", "change_records")


def create_common_indexes(table_name: str, index_token: str) -> None:
    op.create_index(f"ix_{index_token}_project_number", table_name, ["project_id", "number"])
    op.create_index(
        f"ix_{index_token}_project_row_fingerprint",
        table_name,
        ["project_id", "row_fingerprint"],
    )
    op.create_index(f"ix_{index_token}_upload_batch", table_name, ["upload_batch_id"])
    op.create_index(f"ix_{index_token}_uploaded_file", table_name, ["uploaded_file_id"])
    op.create_index(f"ix_{index_token}_raw_row", table_name, ["raw_row_id"])
    op.create_index(
        f"ix_{index_token}_assignment_group",
        table_name,
        ["project_id", "assignment_group"],
    )
    op.create_index(
        f"ix_{index_token}_functional_track",
        table_name,
        ["project_id", "functional_track"],
    )
    op.create_index(f"ix_{index_token}_ams_owner", table_name, ["project_id", "ams_owner"])
    op.create_index(f"ix_{index_token}_sap_non_sap", table_name, ["project_id", "sap_non_sap"])


def upgrade() -> None:
    create_problem_table()
    create_change_table()


def downgrade() -> None:
    if table_exists("assessment_change_records"):
        op.drop_table("assessment_change_records")
    if table_exists("assessment_problem_records"):
        op.drop_table("assessment_problem_records")
