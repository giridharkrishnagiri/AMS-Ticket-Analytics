"""add dashboard filter facts

Revision ID: 20260626_0024
Revises: 20260626_0023
Create Date: 2026-06-26 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260626_0024"
down_revision: str | None = "20260626_0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    if table_exists("dashboard_filter_facts"):
        return

    op.create_table(
        "dashboard_filter_facts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("record_source", sa.String(length=50), nullable=False),
        sa.Column("record_type", sa.String(length=50), nullable=False),
        sa.Column("scope", sa.String(length=50), nullable=False),
        sa.Column("record_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("record_number", sa.String(length=255), nullable=True),
        sa.Column("created_at_source", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at_source", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_month", sa.Date(), nullable=True),
        sa.Column("completed_month", sa.Date(), nullable=True),
        sa.Column("functional_track", sa.String(length=255), nullable=True),
        sa.Column("ams_owner", sa.String(length=255), nullable=True),
        sa.Column("functional_track_ams_owner", sa.String(length=512), nullable=True),
        sa.Column("assignment_group", sa.String(length=255), nullable=True),
        sa.Column("support_group_owner", sa.String(length=255), nullable=True),
        sa.Column("assignment_group_support_owner", sa.String(length=512), nullable=True),
        sa.Column("parent_business_application", sa.String(length=255), nullable=True),
        sa.Column("business_service_ci_name", sa.String(length=255), nullable=True),
        sa.Column("application_owner", sa.String(length=255), nullable=True),
        sa.Column("supported_by_vendor", sa.String(length=255), nullable=True),
        sa.Column("sap_non_sap", sa.String(length=50), nullable=True),
        sa.Column("architecture_type", sa.String(length=255), nullable=True),
        sa.Column("application_type", sa.String(length=255), nullable=True),
        sa.Column("business_critical", sa.String(length=255), nullable=True),
        sa.Column("install_status", sa.String(length=255), nullable=True),
        sa.Column("install_type", sa.String(length=255), nullable=True),
        sa.Column("priority", sa.String(length=50), nullable=True),
        sa.Column("state", sa.String(length=100), nullable=True),
        sa.Column("status_group", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["customer_id"], ["clients.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_dashboard_filter_facts_customer_id", "dashboard_filter_facts", ["customer_id"])
    op.create_index("ix_dashboard_filter_facts_project_id", "dashboard_filter_facts", ["project_id"])
    op.create_index(
        "ix_dashboard_filter_facts_project_scope_type",
        "dashboard_filter_facts",
        ["project_id", "scope", "record_type"],
    )
    op.create_index(
        "ix_dashboard_filter_facts_project_functional",
        "dashboard_filter_facts",
        ["project_id", "functional_track_ams_owner"],
    )
    op.create_index(
        "ix_dashboard_filter_facts_project_assignment",
        "dashboard_filter_facts",
        ["project_id", "assignment_group_support_owner"],
    )
    op.create_index(
        "ix_dashboard_filter_facts_project_parent_app",
        "dashboard_filter_facts",
        ["project_id", "parent_business_application"],
    )
    op.create_index(
        "ix_dashboard_filter_facts_project_app_owner",
        "dashboard_filter_facts",
        ["project_id", "application_owner"],
    )
    op.create_index(
        "ix_dashboard_filter_facts_project_vendor",
        "dashboard_filter_facts",
        ["project_id", "supported_by_vendor"],
    )
    op.create_index(
        "ix_dashboard_filter_facts_project_sap",
        "dashboard_filter_facts",
        ["project_id", "sap_non_sap"],
    )
    op.create_index(
        "ix_dashboard_filter_facts_project_arch",
        "dashboard_filter_facts",
        ["project_id", "architecture_type"],
    )
    op.create_index(
        "ix_dashboard_filter_facts_project_app_type",
        "dashboard_filter_facts",
        ["project_id", "application_type"],
    )
    op.create_index(
        "ix_dashboard_filter_facts_project_business_critical",
        "dashboard_filter_facts",
        ["project_id", "business_critical"],
    )
    op.create_index(
        "ix_dashboard_filter_facts_project_install_status",
        "dashboard_filter_facts",
        ["project_id", "install_status"],
    )
    op.create_index(
        "ix_dashboard_filter_facts_project_install_type",
        "dashboard_filter_facts",
        ["project_id", "install_type"],
    )
    op.create_index(
        "ix_dashboard_filter_facts_project_created_month",
        "dashboard_filter_facts",
        ["project_id", "created_month"],
    )
    op.create_index(
        "ix_dashboard_filter_facts_project_completed_month",
        "dashboard_filter_facts",
        ["project_id", "completed_month"],
    )


def downgrade() -> None:
    if table_exists("dashboard_filter_facts"):
        op.drop_table("dashboard_filter_facts")
