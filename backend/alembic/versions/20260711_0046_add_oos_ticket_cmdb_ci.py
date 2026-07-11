"""add cmdb ci to out of scope tickets

Revision ID: 20260711_0046
Revises: 20260710_0045
Create Date: 2026-07-11 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260711_0046"
down_revision: str | None = "20260710_0045"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def index_exists(index_name: str, table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return any(index["name"] == index_name for index in inspector.get_indexes(table_name))


def upgrade() -> None:
    table_name = "assessment_out_of_scope_tickets"
    if not column_exists(table_name, "cmdb_ci"):
        op.add_column(table_name, sa.Column("cmdb_ci", sa.String(length=255), nullable=True))
    if not index_exists("ix_oos_tickets_project_cmdb_ci", table_name):
        op.create_index(
            "ix_oos_tickets_project_cmdb_ci",
            table_name,
            ["project_id", "cmdb_ci"],
        )


def downgrade() -> None:
    table_name = "assessment_out_of_scope_tickets"
    if index_exists("ix_oos_tickets_project_cmdb_ci", table_name):
        op.drop_index("ix_oos_tickets_project_cmdb_ci", table_name=table_name)
    if column_exists(table_name, "cmdb_ci"):
        op.drop_column(table_name, "cmdb_ci")
