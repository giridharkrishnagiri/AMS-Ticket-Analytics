"""add service fields to dashboard filter facts

Revision ID: 20260710_0045
Revises: 20260709_0044
Create Date: 2026-07-10 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260710_0045"
down_revision: str | None = "20260709_0044"
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


def index_exists(index_name: str, table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return any(index["name"] == index_name for index in inspector.get_indexes(table_name))


def upgrade() -> None:
    table_name = "dashboard_filter_facts"
    if not table_exists(table_name):
        return
    if not column_exists(table_name, "service_entitlement"):
        op.add_column(table_name, sa.Column("service_entitlement", sa.String(length=255)))
    if not column_exists(table_name, "service_type"):
        op.add_column(table_name, sa.Column("service_type", sa.String(length=255)))
    if not index_exists("ix_dashboard_filter_facts_project_service_entitlement", table_name):
        op.create_index(
            "ix_dashboard_filter_facts_project_service_entitlement",
            table_name,
            ["project_id", "service_entitlement"],
        )
    if not index_exists("ix_dashboard_filter_facts_project_service_type", table_name):
        op.create_index(
            "ix_dashboard_filter_facts_project_service_type",
            table_name,
            ["project_id", "service_type"],
        )


def downgrade() -> None:
    table_name = "dashboard_filter_facts"
    if not table_exists(table_name):
        return
    if index_exists("ix_dashboard_filter_facts_project_service_type", table_name):
        op.drop_index("ix_dashboard_filter_facts_project_service_type", table_name=table_name)
    if index_exists("ix_dashboard_filter_facts_project_service_entitlement", table_name):
        op.drop_index(
            "ix_dashboard_filter_facts_project_service_entitlement",
            table_name=table_name,
        )
    if column_exists(table_name, "service_type"):
        op.drop_column(table_name, "service_type")
    if column_exists(table_name, "service_entitlement"):
        op.drop_column(table_name, "service_entitlement")
