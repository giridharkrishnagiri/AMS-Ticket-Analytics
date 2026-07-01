"""make application scope binary

Revision ID: 20260702_0039
Revises: 20260702_0038
Create Date: 2026-07-02 00:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260702_0039"
down_revision: str | None = "20260702_0038"
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
    if not table_exists("application_inventory_items") or not column_exists(
        "application_inventory_items",
        "scope_status",
    ):
        return

    op.execute(
        sa.text(
            """
            UPDATE application_inventory_items
            SET scope_status = 'out_of_scope'
            WHERE scope_status IS NULL
               OR btrim(scope_status) = ''
               OR lower(btrim(scope_status)) = 'unknown'
            """
        )
    )
    if table_exists("dashboard_filter_facts") and column_exists("dashboard_filter_facts", "scope"):
        op.execute(
            sa.text(
                """
                UPDATE dashboard_filter_facts
                SET scope = 'out_of_scope'
                WHERE dashboard_area = 'applications'
                  AND (scope IS NULL OR btrim(scope) = '' OR lower(btrim(scope)) = 'unknown')
                """
            )
        )
    if table_exists("dashboard_filter_catalog"):
        op.execute(
            sa.text(
                """
                DELETE FROM dashboard_filter_catalog
                WHERE dashboard_area = 'applications'
                  AND filter_key = 'application_scope'
                """
            )
        )
    if table_exists("dashboard_filter_cache_status"):
        op.execute(
            sa.text(
                """
                UPDATE dashboard_filter_cache_status
                SET status = 'stale',
                    is_stale = true
                WHERE dashboard_area = 'applications'
                """
            )
        )
    op.alter_column(
        "application_inventory_items",
        "scope_status",
        server_default="out_of_scope",
        existing_type=sa.Text(),
        existing_nullable=False,
    )


def downgrade() -> None:
    if not table_exists("application_inventory_items") or not column_exists(
        "application_inventory_items",
        "scope_status",
    ):
        return

    op.alter_column(
        "application_inventory_items",
        "scope_status",
        server_default=None,
        existing_type=sa.Text(),
        existing_nullable=False,
    )
