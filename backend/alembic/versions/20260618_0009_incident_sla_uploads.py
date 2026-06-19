"""add incident SLA upload staging and enrichment columns

Revision ID: 20260618_0009
Revises: 20260618_0008
Create Date: 2026-06-18 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260618_0009"
down_revision: str | None = "20260618_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("tickets", sa.Column("response_sla_breached", sa.Boolean(), nullable=True))
    op.add_column("tickets", sa.Column("resolution_sla_breached", sa.Boolean(), nullable=True))
    op.add_column(
        "tickets",
        sa.Column("response_sla_business_elapsed_seconds", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "tickets",
        sa.Column("resolution_sla_business_elapsed_seconds", sa.BigInteger(), nullable=True),
    )
    op.add_column("tickets", sa.Column("response_sla_name", sa.Text(), nullable=True))
    op.add_column("tickets", sa.Column("resolution_sla_name", sa.Text(), nullable=True))
    op.add_column(
        "tickets",
        sa.Column("response_sla_updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "tickets",
        sa.Column("resolution_sla_updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("tickets", sa.Column("sla_enriched_at", sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        "incident_sla_rows",
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("uploaded_file_name", sa.Text(), nullable=True),
        sa.Column("source_row_number", sa.Integer(), nullable=False),
        sa.Column("inc_number", sa.Text(), nullable=False),
        sa.Column("inc_priority", sa.Text(), nullable=True),
        sa.Column("taskslatable_stage", sa.Text(), nullable=True),
        sa.Column("assignment_group_name", sa.Text(), nullable=True),
        sa.Column("taskslatable_duration_seconds", sa.Integer(), nullable=True),
        sa.Column("taskslatable_business_duration_seconds", sa.Integer(), nullable=True),
        sa.Column("taskslatable_has_breached", sa.Boolean(), nullable=True),
        sa.Column("taskslatable_sla_sys_name", sa.Text(), nullable=True),
        sa.Column("taskslatable_sla_name", sa.Text(), nullable=True),
        sa.Column("taskslatable_sla_type", sa.Text(), nullable=True),
        sa.Column("taskslatable_sla_target", sa.Text(), nullable=True),
        sa.Column("raw_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "ingested_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_incident_sla_rows_project_id", "incident_sla_rows", ["project_id"])
    op.create_index(
        "ix_incident_sla_rows_project_inc_number",
        "incident_sla_rows",
        ["project_id", "inc_number"],
    )
    op.create_index(
        "ix_incident_sla_rows_project_inc_target",
        "incident_sla_rows",
        ["project_id", "inc_number", "taskslatable_sla_target"],
    )
    op.create_index(
        "ix_incident_sla_rows_project_sla_name",
        "incident_sla_rows",
        ["project_id", "taskslatable_sla_name"],
    )


def downgrade() -> None:
    op.drop_index("ix_incident_sla_rows_project_sla_name", table_name="incident_sla_rows")
    op.drop_index("ix_incident_sla_rows_project_inc_target", table_name="incident_sla_rows")
    op.drop_index("ix_incident_sla_rows_project_inc_number", table_name="incident_sla_rows")
    op.drop_index("ix_incident_sla_rows_project_id", table_name="incident_sla_rows")
    op.drop_table("incident_sla_rows")

    op.drop_column("tickets", "sla_enriched_at")
    op.drop_column("tickets", "resolution_sla_updated_at")
    op.drop_column("tickets", "response_sla_updated_at")
    op.drop_column("tickets", "resolution_sla_name")
    op.drop_column("tickets", "response_sla_name")
    op.drop_column("tickets", "resolution_sla_business_elapsed_seconds")
    op.drop_column("tickets", "response_sla_business_elapsed_seconds")
    op.drop_column("tickets", "resolution_sla_breached")
    op.drop_column("tickets", "response_sla_breached")
