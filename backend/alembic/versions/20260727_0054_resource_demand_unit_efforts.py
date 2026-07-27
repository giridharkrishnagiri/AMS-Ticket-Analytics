"""add resource demand unit effort master

Revision ID: 20260727_0054
Revises: 20260724_0053
Create Date: 2026-07-27 10:30:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20260727_0054"
down_revision = "20260724_0053"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "resource_demand_unit_efforts",
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("ticket_type", sa.String(length=40), nullable=False),
        sa.Column("incident_source", sa.String(length=40), nullable=False),
        sa.Column("technology", sa.String(length=120), nullable=False),
        sa.Column("l1_5_hours", sa.Numeric(10, 2), nullable=True),
        sa.Column("l2_hours", sa.Numeric(10, 2), nullable=True),
        sa.Column("l3_hours", sa.Numeric(10, 2), nullable=True),
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
            name="uq_resource_demand_unit_efforts_project_basis",
        ),
    )
    op.create_index(
        "ix_resource_demand_unit_efforts_project",
        "resource_demand_unit_efforts",
        ["project_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_resource_demand_unit_efforts_project",
        table_name="resource_demand_unit_efforts",
    )
    op.drop_table("resource_demand_unit_efforts")
