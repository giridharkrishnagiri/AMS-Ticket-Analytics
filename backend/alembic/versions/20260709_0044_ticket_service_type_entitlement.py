"""add service type and entitlement enrichment columns

Revision ID: 20260709_0044
Revises: 20260704_0043
Create Date: 2026-07-09 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260709_0044"
down_revision: str | None = "20260704_0043"
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


def add_nullable_text_column(table_name: str, column_name: str) -> None:
    if table_exists(table_name) and not column_exists(table_name, column_name):
        op.add_column(table_name, sa.Column(column_name, sa.Text(), nullable=True))


def drop_column_if_exists(table_name: str, column_name: str) -> None:
    if table_exists(table_name) and column_exists(table_name, column_name):
        op.drop_column(table_name, column_name)


def upgrade() -> None:
    for table_name in (
        "application_inventory_items",
        "tickets",
        "assessment_out_of_scope_tickets",
    ):
        add_nullable_text_column(table_name, "service_type")
        add_nullable_text_column(table_name, "service_entitlement")


def downgrade() -> None:
    for table_name in (
        "assessment_out_of_scope_tickets",
        "tickets",
        "application_inventory_items",
    ):
        drop_column_if_exists(table_name, "service_entitlement")
        drop_column_if_exists(table_name, "service_type")
