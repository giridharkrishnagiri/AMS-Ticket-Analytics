"""add application inventory active users

Revision ID: 20260625_0020
Revises: 20260625_0019
Create Date: 2026-06-25 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260625_0020"
down_revision: str | None = "20260625_0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def upgrade() -> None:
    if not column_exists("application_inventory_items", "active_users"):
        op.add_column(
            "application_inventory_items",
            sa.Column("active_users", sa.Integer(), nullable=True),
        )


def downgrade() -> None:
    if column_exists("application_inventory_items", "active_users"):
        op.drop_column("application_inventory_items", "active_users")
