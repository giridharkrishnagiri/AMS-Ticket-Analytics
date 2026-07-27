"""add resource demand service level split master

Revision ID: 20260727_0055
Revises: 20260727_0054
Create Date: 2026-07-27 17:30:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20260727_0055"
down_revision = "20260727_0054"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "resource_demand_service_level_splits",
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("ticket_type", sa.String(length=40), nullable=False),
        sa.Column("incident_source", sa.String(length=40), nullable=False),
        sa.Column("technology", sa.String(length=120), nullable=False),
        sa.Column("l1_5_pct", sa.Numeric(6, 2), nullable=True),
        sa.Column("l2_pct", sa.Numeric(6, 2), nullable=True),
        sa.Column("l3_pct", sa.Numeric(6, 2), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id",
            "ticket_type",
            "incident_source",
            "technology",
            name="uq_resource_demand_service_splits_project_basis",
        ),
    )
    op.create_index(
        "ix_resource_demand_service_splits_project",
        "resource_demand_service_level_splits",
        ["project_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_resource_demand_service_splits_project",
        table_name="resource_demand_service_level_splits",
    )
    op.drop_table("resource_demand_service_level_splits")
