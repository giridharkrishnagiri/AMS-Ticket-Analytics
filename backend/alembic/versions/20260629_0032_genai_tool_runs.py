"""genai tool runs

Revision ID: 20260629_0032
Revises: 20260629_0031
Create Date: 2026-06-29 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260629_0032"
down_revision: str | None = "20260629_0031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "genai_tool_runs",
        sa.Column("tool_name", sa.String(length=120), nullable=False),
        sa.Column("domain", sa.String(length=80), nullable=True),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("parameters_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("filters_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("row_count", sa.Integer(), nullable=True),
        sa.Column("truncated", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("execution_ms", sa.Integer(), nullable=True),
        sa.Column("warnings_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["customer_id"], ["clients.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_genai_tool_runs_tool_name", "genai_tool_runs", ["tool_name"])
    op.create_index("ix_genai_tool_runs_domain", "genai_tool_runs", ["domain"])
    op.create_index("ix_genai_tool_runs_customer_id", "genai_tool_runs", ["customer_id"])
    op.create_index("ix_genai_tool_runs_project_id", "genai_tool_runs", ["project_id"])
    op.create_index(
        "ix_genai_tool_runs_tool_created_at",
        "genai_tool_runs",
        ["tool_name", "created_at"],
    )
    op.create_index(
        "ix_genai_tool_runs_domain_created_at",
        "genai_tool_runs",
        ["domain", "created_at"],
    )
    op.create_index(
        "ix_genai_tool_runs_status_created_at",
        "genai_tool_runs",
        ["status", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_genai_tool_runs_status_created_at", table_name="genai_tool_runs")
    op.drop_index("ix_genai_tool_runs_domain_created_at", table_name="genai_tool_runs")
    op.drop_index("ix_genai_tool_runs_tool_created_at", table_name="genai_tool_runs")
    op.drop_index("ix_genai_tool_runs_project_id", table_name="genai_tool_runs")
    op.drop_index("ix_genai_tool_runs_customer_id", table_name="genai_tool_runs")
    op.drop_index("ix_genai_tool_runs_domain", table_name="genai_tool_runs")
    op.drop_index("ix_genai_tool_runs_tool_name", table_name="genai_tool_runs")
    op.drop_table("genai_tool_runs")
