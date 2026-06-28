"""genai foundation

Revision ID: 20260628_0029
Revises: 20260628_0028
Create Date: 2026-06-28 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260628_0029"
down_revision: str | None = "20260628_0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "genai_config",
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("provider", sa.String(length=50), nullable=False, server_default="openai"),
        sa.Column("model_name", sa.String(length=255), nullable=True),
        sa.Column("temperature", sa.Float(), nullable=False, server_default="0.2"),
        sa.Column("top_p", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("max_output_tokens", sa.Integer(), nullable=False, server_default="1000"),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("max_tool_calls", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("allow_recommendations", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "allow_chart_generation",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("response_style", sa.String(length=20), nullable=False, server_default="standard"),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "genai_prompt_templates",
        sa.Column("prompt_key", sa.String(length=100), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("default_prompt", sa.Text(), nullable=False),
        sa.Column("custom_prompt", sa.Text(), nullable=True),
        sa.Column("is_custom_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("prompt_key"),
    )
    op.create_index(
        "ix_genai_prompt_templates_prompt_key",
        "genai_prompt_templates",
        ["prompt_key"],
    )

    op.create_table(
        "genai_safety_settings",
        sa.Column(
            "allow_application_detail_rows",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "allow_ticket_detail_rows",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "allow_aggregate_ticket_data",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "allow_problem_change_data",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "allow_sla_ola_aggregate_data",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column("max_rows_returned_to_llm", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("max_chart_data_points", sa.Integer(), nullable=False, server_default="500"),
        sa.Column(
            "enforce_complete_month_cutoff",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column("mask_sensitive_fields", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "genai_usage_logs",
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("session_id", sa.String(length=255), nullable=True),
        sa.Column("message_id", sa.String(length=255), nullable=True),
        sa.Column("provider", sa.String(length=50), nullable=True),
        sa.Column("model_name", sa.String(length=255), nullable=True),
        sa.Column("operation", sa.String(length=50), nullable=False),
        sa.Column("question", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("tools_used_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("completion_tokens", sa.Integer(), nullable=True),
        sa.Column("estimated_cost", sa.Float(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["customer_id"], ["clients.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_genai_usage_logs_customer_id", "genai_usage_logs", ["customer_id"])
    op.create_index("ix_genai_usage_logs_project_id", "genai_usage_logs", ["project_id"])
    op.create_index(
        "ix_genai_usage_logs_operation_created_at",
        "genai_usage_logs",
        ["operation", "created_at"],
    )
    op.create_index(
        "ix_genai_usage_logs_status_created_at",
        "genai_usage_logs",
        ["status", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_genai_usage_logs_status_created_at", table_name="genai_usage_logs")
    op.drop_index("ix_genai_usage_logs_operation_created_at", table_name="genai_usage_logs")
    op.drop_index("ix_genai_usage_logs_project_id", table_name="genai_usage_logs")
    op.drop_index("ix_genai_usage_logs_customer_id", table_name="genai_usage_logs")
    op.drop_table("genai_usage_logs")
    op.drop_table("genai_safety_settings")
    op.drop_index("ix_genai_prompt_templates_prompt_key", table_name="genai_prompt_templates")
    op.drop_table("genai_prompt_templates")
    op.drop_table("genai_config")
