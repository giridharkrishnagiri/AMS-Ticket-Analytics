"""add hosting environment fields

Revision ID: 20260626_0025
Revises: 20260626_0024
Create Date: 2026-06-26 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260626_0025"
down_revision: str | None = "20260626_0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


TEXT_TABLE_COLUMNS = (
    ("application_inventory_items", "hosting_env", sa.Text()),
    ("tickets", "hosting_env", sa.Text()),
    ("assessment_out_of_scope_tickets", "hosting_env", sa.Text()),
)
FACT_TABLE_COLUMN = ("dashboard_filter_facts", "hosting_env", sa.String(length=255))
INDEXES = (
    ("ix_application_inventory_project_hosting_env", "application_inventory_items", "hosting_env"),
    ("ix_tickets_project_hosting_env", "tickets", "hosting_env"),
    ("ix_oos_tickets_project_hosting_env", "assessment_out_of_scope_tickets", "hosting_env"),
    ("ix_dashboard_filter_facts_project_hosting_env", "dashboard_filter_facts", "hosting_env"),
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


def cmdb_value_sql(*keys: str) -> str:
    expressions = []
    for key in keys:
        escaped_key = key.replace("'", "''")
        expressions.append(f"NULLIF(btrim(ai.cmdb_payload ->> '{escaped_key}'), '')")
    return f"COALESCE({', '.join(expressions)})"


def upgrade() -> None:
    for table_name, column_name, column_type in TEXT_TABLE_COLUMNS:
        if not column_exists(table_name, column_name):
            op.add_column(table_name, sa.Column(column_name, column_type, nullable=True))

    fact_table, fact_column, fact_type = FACT_TABLE_COLUMN
    if table_exists(fact_table) and not column_exists(fact_table, fact_column):
        op.add_column(fact_table, sa.Column(fact_column, fact_type, nullable=True))

    hosting_expression = cmdb_value_sql("Hosting Env", "Hosting Environment")
    op.execute(
        sa.text(
            f"""
            UPDATE application_inventory_items AS ai
            SET hosting_env = {hosting_expression}
            WHERE ai.hosting_env IS NULL
              AND ai.cmdb_payload IS NOT NULL
            """,
        ),
    )
    for table_name in ("tickets", "assessment_out_of_scope_tickets"):
        op.execute(
            sa.text(
                f"""
                UPDATE {table_name} AS t
                SET hosting_env = NULLIF(btrim(ai.hosting_env), '')
                FROM application_inventory_items AS ai
                WHERE t.application_inventory_id = ai.id
                  AND NULLIF(btrim(ai.hosting_env), '') IS NOT NULL
                """,
            ),
        )

    for index_name, table_name, column_name in INDEXES:
        if table_exists(table_name) and not index_exists(table_name, index_name):
            op.create_index(index_name, table_name, ["project_id", column_name])


def downgrade() -> None:
    for index_name, table_name, _column_name in reversed(INDEXES):
        if table_exists(table_name) and index_exists(table_name, index_name):
            op.drop_index(index_name, table_name=table_name)

    fact_table, fact_column, _fact_type = FACT_TABLE_COLUMN
    if table_exists(fact_table) and column_exists(fact_table, fact_column):
        op.drop_column(fact_table, fact_column)

    for table_name, column_name, _column_type in reversed(TEXT_TABLE_COLUMNS):
        if column_exists(table_name, column_name):
            op.drop_column(table_name, column_name)
