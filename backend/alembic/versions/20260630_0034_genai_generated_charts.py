"""add genai generated charts

Revision ID: 20260630_0034
Revises: 20260629_0033
Create Date: 2026-06-30 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260630_0034"
down_revision: str | None = "20260629_0033"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    if not table_exists("genai_generated_charts"):
        op.create_table(
            "genai_generated_charts",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("session_id", sa.String(length=255), nullable=True),
            sa.Column("message_id", sa.String(length=255), nullable=True),
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column("subtitle", sa.Text(), nullable=True),
            sa.Column("chart_type", sa.String(length=50), nullable=False),
            sa.Column("chart_library", sa.String(length=50), nullable=False, server_default="plotly"),
            sa.Column("chart_spec_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
            sa.Column("source_tool_names_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column(
                "source_tool_results_summary_json",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=True,
            ),
            sa.Column("parameters_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("filters_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("data_notes_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("warnings_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["customer_id"], ["clients.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )

    op.create_index(
        "ix_genai_generated_charts_customer_id",
        "genai_generated_charts",
        ["customer_id"],
        unique=False,
        if_not_exists=True,
    )
    op.create_index(
        "ix_genai_generated_charts_project_id",
        "genai_generated_charts",
        ["project_id"],
        unique=False,
        if_not_exists=True,
    )
    op.create_index(
        "ix_genai_generated_charts_session_id",
        "genai_generated_charts",
        ["session_id"],
        unique=False,
        if_not_exists=True,
    )
    op.create_index(
        "ix_genai_generated_charts_message_id",
        "genai_generated_charts",
        ["message_id"],
        unique=False,
        if_not_exists=True,
    )
    op.create_index(
        "ix_genai_generated_charts_created_at",
        "genai_generated_charts",
        ["created_at"],
        unique=False,
        if_not_exists=True,
    )
    op.create_index(
        "ix_genai_generated_charts_chart_type",
        "genai_generated_charts",
        ["chart_type"],
        unique=False,
        if_not_exists=True,
    )
    op.create_index(
        "ix_genai_generated_charts_archived_created",
        "genai_generated_charts",
        ["is_archived", "created_at"],
        unique=False,
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_genai_generated_charts_archived_created",
        table_name="genai_generated_charts",
        if_exists=True,
    )
    op.drop_index(
        "ix_genai_generated_charts_chart_type",
        table_name="genai_generated_charts",
        if_exists=True,
    )
    op.drop_index(
        "ix_genai_generated_charts_created_at",
        table_name="genai_generated_charts",
        if_exists=True,
    )
    op.drop_index(
        "ix_genai_generated_charts_message_id",
        table_name="genai_generated_charts",
        if_exists=True,
    )
    op.drop_index(
        "ix_genai_generated_charts_session_id",
        table_name="genai_generated_charts",
        if_exists=True,
    )
    op.drop_index(
        "ix_genai_generated_charts_project_id",
        table_name="genai_generated_charts",
        if_exists=True,
    )
    op.drop_index(
        "ix_genai_generated_charts_customer_id",
        table_name="genai_generated_charts",
        if_exists=True,
    )
    op.drop_table("genai_generated_charts")
