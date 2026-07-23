"""add genai ticket automation assessments

Revision ID: 20260723_0051
Revises: 20260721_0050
Create Date: 2026-07-23 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260723_0051"
down_revision: str | None = "20260721_0050"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def index_exists(index_name: str, table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return any(index["name"] == index_name for index in inspector.get_indexes(table_name))


def upgrade() -> None:
    if not table_exists("genai_ticket_automation_assessments"):
        op.create_table(
            "genai_ticket_automation_assessments",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("analysis_month", sa.String(length=7), nullable=False),
            sa.Column("analysis_month_to", sa.String(length=7), nullable=False),
            sa.Column("run_id", sa.String(length=80), nullable=False),
            sa.Column("cluster_run_id", sa.String(length=80), nullable=False),
            sa.Column("cluster_key", sa.String(length=80), nullable=False),
            sa.Column("cluster_label", sa.String(length=255), nullable=False),
            sa.Column("category", sa.String(length=255), nullable=True),
            sa.Column("subcategory_1", sa.String(length=255), nullable=True),
            sa.Column("ticket_type", sa.String(length=40), nullable=False),
            sa.Column("ticket_count", sa.Integer(), nullable=False),
            sa.Column("incident_count", sa.Integer(), nullable=False),
            sa.Column("sc_task_count", sa.Integer(), nullable=False),
            sa.Column("input_hash", sa.String(length=64), nullable=False),
            sa.Column("prompt_key", sa.String(length=100), nullable=False),
            sa.Column("prompt_version", sa.Integer(), nullable=False),
            sa.Column("model_name", sa.String(length=255), nullable=True),
            sa.Column("status", sa.String(length=40), nullable=False),
            sa.Column("automation_potential", sa.String(length=40), nullable=True),
            sa.Column("recommended_resolution_path", sa.String(length=80), nullable=True),
            sa.Column("primary_automation_type", sa.String(length=120), nullable=True),
            sa.Column("pattern_summary", sa.Text(), nullable=True),
            sa.Column("current_resolution_summary", sa.Text(), nullable=True),
            sa.Column("likely_root_cause", sa.Text(), nullable=True),
            sa.Column("automation_recommendation", sa.Text(), nullable=True),
            sa.Column("implementation_approach", sa.Text(), nullable=True),
            sa.Column("prerequisites", sa.Text(), nullable=True),
            sa.Column("expected_benefits", sa.Text(), nullable=True),
            sa.Column("risks_or_constraints", sa.Text(), nullable=True),
            sa.Column("confidence", sa.Float(), nullable=True),
            sa.Column("business_services_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column(
                "representative_tickets_json",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=True,
            ),
            sa.Column("evidence_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(["customer_id"], ["clients.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "project_id",
                "analysis_month",
                "analysis_month_to",
                "cluster_run_id",
                "cluster_key",
                name="uq_genai_ticket_automation_project_period_run_cluster",
            ),
        )

    for index_name, columns in (
        ("ix_genai_ticket_automation_customer_id", ["customer_id"]),
        ("ix_genai_ticket_automation_project_id", ["project_id"]),
        ("ix_genai_ticket_automation_analysis_month", ["analysis_month"]),
        ("ix_genai_ticket_automation_analysis_month_to", ["analysis_month_to"]),
        ("ix_genai_ticket_automation_run_id", ["run_id"]),
        ("ix_genai_ticket_automation_cluster_run_id", ["cluster_run_id"]),
        ("ix_genai_ticket_automation_cluster_key", ["cluster_key"]),
        ("ix_genai_ticket_automation_ticket_type", ["ticket_type"]),
        ("ix_genai_ticket_automation_input_hash", ["input_hash"]),
        ("ix_genai_ticket_automation_status", ["status"]),
        ("ix_genai_ticket_automation_automation_potential", ["automation_potential"]),
        (
            "ix_genai_ticket_automation_project_period",
            ["project_id", "analysis_month", "analysis_month_to"],
        ),
        (
            "ix_genai_ticket_automation_potential",
            ["project_id", "analysis_month", "automation_potential"],
        ),
        (
            "ix_genai_ticket_automation_cluster_key",
            ["project_id", "cluster_key"],
        ),
    ):
        if not index_exists(index_name, "genai_ticket_automation_assessments"):
            op.create_index(index_name, "genai_ticket_automation_assessments", columns)


def downgrade() -> None:
    if table_exists("genai_ticket_automation_assessments"):
        op.drop_table("genai_ticket_automation_assessments")
