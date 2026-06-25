"""add application inventory ticket user metrics

Revision ID: 20260625_0021
Revises: 20260625_0020
Create Date: 2026-06-25 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260625_0021"
down_revision: str | None = "20260625_0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def upgrade() -> None:
    if not column_exists("application_inventory_items", "avg_monthly_ticket_volume_6m"):
        op.add_column(
            "application_inventory_items",
            sa.Column("avg_monthly_ticket_volume_6m", sa.Float(), nullable=True),
        )
    if not column_exists("application_inventory_items", "tickets_per_user_per_month"):
        op.add_column(
            "application_inventory_items",
            sa.Column("tickets_per_user_per_month", sa.Float(), nullable=True),
        )


def downgrade() -> None:
    if column_exists("application_inventory_items", "tickets_per_user_per_month"):
        op.drop_column("application_inventory_items", "tickets_per_user_per_month")
    if column_exists("application_inventory_items", "avg_monthly_ticket_volume_6m"):
        op.drop_column("application_inventory_items", "avg_monthly_ticket_volume_6m")
