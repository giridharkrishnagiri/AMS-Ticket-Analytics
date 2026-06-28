"""add application inventory global field

Revision ID: 20260628_0027
Revises: 20260627_0026
Create Date: 2026-06-28 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260628_0027"
down_revision: str | None = "20260627_0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def index_exists(table_name: str, index_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return any(index["name"] == index_name for index in inspector.get_indexes(table_name))


def upgrade() -> None:
    if not column_exists("application_inventory_items", "global_application"):
        op.add_column(
            "application_inventory_items",
            sa.Column("global_application", sa.Text(), nullable=True),
        )

    op.execute(
        sa.text(
            """
            UPDATE application_inventory_items AS ai
            SET global_application = COALESCE(
                NULLIF(btrim(ai.cmdb_payload ->> 'Global'), ''),
                NULLIF(btrim(ai.cmdb_payload ->> 'Global Application'), '')
            )
            WHERE ai.global_application IS NULL
              AND ai.cmdb_payload IS NOT NULL
            """,
        ),
    )

    if not index_exists(
        "application_inventory_items",
        "ix_application_inventory_project_global",
    ):
        op.create_index(
            "ix_application_inventory_project_global",
            "application_inventory_items",
            ["project_id", "global_application"],
        )


def downgrade() -> None:
    if index_exists("application_inventory_items", "ix_application_inventory_project_global"):
        op.drop_index(
            "ix_application_inventory_project_global",
            table_name="application_inventory_items",
        )
    if column_exists("application_inventory_items", "global_application"):
        op.drop_column("application_inventory_items", "global_application")
