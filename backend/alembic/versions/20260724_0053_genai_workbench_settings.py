"""add genai workbench settings

Revision ID: 20260724_0053
Revises: 20260723_0052
Create Date: 2026-07-24 10:30:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "20260724_0053"
down_revision = "20260723_0052"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "genai_workbench_settings",
        sa.Column("settings_key", sa.String(length=80), nullable=False),
        sa.Column("settings_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("settings_key"),
    )
    op.create_index(
        op.f("ix_genai_workbench_settings_settings_key"),
        "genai_workbench_settings",
        ["settings_key"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_genai_workbench_settings_settings_key"),
        table_name="genai_workbench_settings",
    )
    op.drop_table("genai_workbench_settings")
