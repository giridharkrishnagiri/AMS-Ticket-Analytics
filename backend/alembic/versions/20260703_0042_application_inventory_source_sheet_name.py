"""add application inventory source sheet name

Revision ID: 20260703_0042
Revises: 20260703_0041
Create Date: 2026-07-03 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260703_0042"
down_revision: str | None = "20260703_0041"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def upgrade() -> None:
    if table_exists("application_inventory_items") and not column_exists(
        "application_inventory_items",
        "source_sheet_name",
    ):
        op.add_column(
            "application_inventory_items",
            sa.Column("source_sheet_name", sa.Text(), nullable=True),
        )


def downgrade() -> None:
    if table_exists("application_inventory_items") and column_exists(
        "application_inventory_items",
        "source_sheet_name",
    ):
        op.drop_column("application_inventory_items", "source_sheet_name")
