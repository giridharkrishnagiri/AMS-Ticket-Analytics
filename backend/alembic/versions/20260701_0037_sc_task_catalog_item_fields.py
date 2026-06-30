"""add sc task catalog item fields

Revision ID: 20260701_0037
Revises: 20260701_0036
Create Date: 2026-07-01 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260701_0037"
down_revision: str | None = "20260701_0036"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


TARGET_TABLES = ("tickets", "assessment_out_of_scope_tickets")
CATALOG_COLUMNS = ("catalog_item_name", "catalog_knowledge_base")


def table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def upgrade() -> None:
    for table_name in TARGET_TABLES:
        if not table_exists(table_name):
            continue
        for column_name in CATALOG_COLUMNS:
            if not column_exists(table_name, column_name):
                op.add_column(table_name, sa.Column(column_name, sa.Text(), nullable=True))


def downgrade() -> None:
    for table_name in TARGET_TABLES:
        if not table_exists(table_name):
            continue
        for column_name in reversed(CATALOG_COLUMNS):
            if column_exists(table_name, column_name):
                op.drop_column(table_name, column_name)
