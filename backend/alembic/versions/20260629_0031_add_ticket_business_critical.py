"""add ticket business criticality fields

Revision ID: 20260629_0031
Revises: 20260629_0030
Create Date: 2026-06-29 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260629_0031"
down_revision: str | None = "20260629_0030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


TABLE_COLUMNS = (
    ("tickets", "business_critical", sa.Text()),
    ("assessment_out_of_scope_tickets", "business_critical", sa.Text()),
)
INDEXES = (
    ("ix_tickets_project_business_critical", "tickets", "business_critical"),
    (
        "ix_oos_tickets_project_business_critical",
        "assessment_out_of_scope_tickets",
        "business_critical",
    ),
)


def column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def index_exists(table_name: str, index_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return any(index["name"] == index_name for index in inspector.get_indexes(table_name))


def table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def business_critical_sql() -> str:
    keys = ("Business criticality", "Biz Criticality", "Business Criticality", "Business Critical")
    expressions = []
    for key in keys:
        escaped_key = key.replace("'", "''")
        expressions.append(f"NULLIF(btrim(ai.cmdb_payload ->> '{escaped_key}'), '')")
    return f"COALESCE({', '.join(expressions)})"


def upgrade() -> None:
    for table_name, column_name, column_type in TABLE_COLUMNS:
        if not column_exists(table_name, column_name):
            op.add_column(table_name, sa.Column(column_name, column_type, nullable=True))

    criticality_expression = business_critical_sql()
    for table_name, _column_name, _column_type in TABLE_COLUMNS:
        op.execute(
            sa.text(
                f"""
                UPDATE {table_name} AS t
                SET business_critical = {criticality_expression}
                FROM application_inventory_items AS ai
                WHERE t.application_inventory_id = ai.id
                  AND {criticality_expression} IS NOT NULL
                """,
            ),
        )

    for index_name, table_name, column_name in INDEXES:
        if not index_exists(table_name, index_name):
            op.create_index(index_name, table_name, ["project_id", column_name])

    if table_exists("dashboard_filter_facts"):
        op.execute(sa.text("DELETE FROM dashboard_filter_facts"))


def downgrade() -> None:
    for index_name, table_name, _column_name in reversed(INDEXES):
        if index_exists(table_name, index_name):
            op.drop_index(index_name, table_name=table_name)

    for table_name, column_name, _column_type in reversed(TABLE_COLUMNS):
        if column_exists(table_name, column_name):
            op.drop_column(table_name, column_name)
