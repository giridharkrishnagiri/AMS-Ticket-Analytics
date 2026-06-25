"""add ticket architecture and install fields

Revision ID: 20260625_0019
Revises: 20260624_0018
Create Date: 2026-06-25 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260625_0019"
down_revision: str | None = "20260624_0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


TABLES = ("tickets", "assessment_out_of_scope_tickets")
COLUMNS = ("architecture_type", "install_type")
INDEXES = (
    ("ix_tickets_project_architecture_type", "tickets", "architecture_type"),
    ("ix_tickets_project_install_type", "tickets", "install_type"),
    (
        "ix_oos_tickets_project_architecture_type",
        "assessment_out_of_scope_tickets",
        "architecture_type",
    ),
    ("ix_oos_tickets_project_install_type", "assessment_out_of_scope_tickets", "install_type"),
)


def column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def index_exists(table_name: str, index_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return any(index["name"] == index_name for index in inspector.get_indexes(table_name))


def cmdb_value_sql(*keys: str) -> str:
    expressions = []
    for key in keys:
        escaped_key = key.replace("'", "''")
        expressions.append(f"NULLIF(btrim(ai.cmdb_payload ->> '{escaped_key}'), '')")
    return f"COALESCE({', '.join(expressions)})"


def add_columns() -> None:
    for table_name in TABLES:
        for column_name in COLUMNS:
            if not column_exists(table_name, column_name):
                op.add_column(table_name, sa.Column(column_name, sa.Text(), nullable=True))


def backfill_table(table_name: str) -> None:
    architecture_expression = cmdb_value_sql("Architecture type", "Architecture Type")
    install_expression = cmdb_value_sql("Install type", "Install Type")
    op.execute(
        sa.text(
            f"""
            UPDATE {table_name} AS t
            SET
                architecture_type = {architecture_expression},
                install_type = {install_expression}
            FROM application_inventory_items AS ai
            WHERE t.application_inventory_id = ai.id
            """,
        ),
    )


def upgrade() -> None:
    add_columns()
    for table_name in TABLES:
        backfill_table(table_name)
    for index_name, table_name, column_name in INDEXES:
        if not index_exists(table_name, index_name):
            op.create_index(index_name, table_name, ["project_id", column_name])


def downgrade() -> None:
    for index_name, table_name, _column_name in reversed(INDEXES):
        if index_exists(table_name, index_name):
            op.drop_index(index_name, table_name=table_name)
    for table_name in reversed(TABLES):
        for column_name in reversed(COLUMNS):
            if column_exists(table_name, column_name):
                op.drop_column(table_name, column_name)
