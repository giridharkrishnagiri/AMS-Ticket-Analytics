"""add current marker for application inventory reference sets

Revision ID: 20260704_0043
Revises: 20260703_0042
Create Date: 2026-07-04 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260704_0043"
down_revision: str | None = "20260703_0042"
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


def index_exists(table_name: str, index_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return any(index["name"] == index_name for index in inspector.get_indexes(table_name))


def upgrade() -> None:
    if not table_exists("application_inventory_items"):
        return

    if not column_exists("application_inventory_items", "is_current"):
        op.add_column(
            "application_inventory_items",
            sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.true()),
        )
        op.alter_column("application_inventory_items", "is_current", server_default=None)

    if not column_exists("application_inventory_items", "replaced_at"):
        op.add_column(
            "application_inventory_items",
            sa.Column("replaced_at", sa.DateTime(timezone=True), nullable=True),
        )

    if not index_exists(
        "application_inventory_items",
        "ix_application_inventory_project_is_current",
    ):
        op.create_index(
            "ix_application_inventory_project_is_current",
            "application_inventory_items",
            ["project_id", "is_current"],
        )


def downgrade() -> None:
    if not table_exists("application_inventory_items"):
        return

    if index_exists(
        "application_inventory_items",
        "ix_application_inventory_project_is_current",
    ):
        op.drop_index(
            "ix_application_inventory_project_is_current",
            table_name="application_inventory_items",
        )

    if column_exists("application_inventory_items", "replaced_at"):
        op.drop_column("application_inventory_items", "replaced_at")

    if column_exists("application_inventory_items", "is_current"):
        op.drop_column("application_inventory_items", "is_current")
