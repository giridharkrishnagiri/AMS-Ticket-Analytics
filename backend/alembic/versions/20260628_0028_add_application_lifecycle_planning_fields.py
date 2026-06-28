"""add application lifecycle planning fields

Revision ID: 20260628_0028
Revises: 20260628_0027
Create Date: 2026-06-28 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260628_0028"
down_revision: str | None = "20260628_0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


TABLE_NAME = "application_inventory_items"


def column_exists(table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def index_exists(table_name: str, index_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(index["name"] == index_name for index in inspector.get_indexes(table_name))


def add_text_column(column_name: str) -> None:
    if not column_exists(TABLE_NAME, column_name):
        op.add_column(TABLE_NAME, sa.Column(column_name, sa.Text(), nullable=True))


def create_project_index(index_name: str, column_name: str) -> None:
    if not index_exists(TABLE_NAME, index_name):
        op.create_index(index_name, TABLE_NAME, ["project_id", column_name])


def upgrade() -> None:
    add_text_column("lifecycle_stage_status")
    add_text_column("lifecycle_current")
    add_text_column("lifecycle_1_to_3_years")
    add_text_column("lifecycle_3_to_5_years")

    op.execute(
        sa.text(
            """
            UPDATE application_inventory_items AS ai
            SET
                lifecycle_stage_status = COALESCE(
                    ai.lifecycle_stage_status,
                    NULLIF(btrim(ai.cmdb_payload ->> 'Life Cycle Stage Status'), ''),
                    NULLIF(btrim(ai.cmdb_payload ->> 'Lifecycle Stage Status'), '')
                ),
                lifecycle_current = COALESCE(
                    ai.lifecycle_current,
                    NULLIF(btrim(ai.cmdb_payload ->> 'Lifecycle - Current'), ''),
                    NULLIF(btrim(ai.cmdb_payload ->> 'Lifecycle Current'), '')
                ),
                lifecycle_1_to_3_years = COALESCE(
                    ai.lifecycle_1_to_3_years,
                    NULLIF(btrim(ai.cmdb_payload ->> 'Lifecycle - 1 to 3 years'), ''),
                    NULLIF(btrim(ai.cmdb_payload ->> 'Lifecycle 1 to 3 years'), ''),
                    NULLIF(btrim(ai.cmdb_payload ->> 'Lifecycle - 1-3 years'), '')
                ),
                lifecycle_3_to_5_years = COALESCE(
                    ai.lifecycle_3_to_5_years,
                    NULLIF(btrim(ai.cmdb_payload ->> 'Lifecycle - 3 to 5 years'), ''),
                    NULLIF(btrim(ai.cmdb_payload ->> 'Lifecycle 3 to 5 years'), ''),
                    NULLIF(btrim(ai.cmdb_payload ->> 'Lifecycle - 3-5 years'), '')
                )
            WHERE ai.cmdb_payload IS NOT NULL
            """
        )
    )

    create_project_index(
        "ix_application_inventory_project_lifecycle_stage_status",
        "lifecycle_stage_status",
    )
    create_project_index(
        "ix_application_inventory_project_lifecycle_current",
        "lifecycle_current",
    )
    create_project_index(
        "ix_application_inventory_project_lifecycle_1_to_3_years",
        "lifecycle_1_to_3_years",
    )
    create_project_index(
        "ix_application_inventory_project_lifecycle_3_to_5_years",
        "lifecycle_3_to_5_years",
    )


def downgrade() -> None:
    for index_name in (
        "ix_application_inventory_project_lifecycle_3_to_5_years",
        "ix_application_inventory_project_lifecycle_1_to_3_years",
        "ix_application_inventory_project_lifecycle_current",
        "ix_application_inventory_project_lifecycle_stage_status",
    ):
        if index_exists(TABLE_NAME, index_name):
            op.drop_index(index_name, table_name=TABLE_NAME)

    for column_name in (
        "lifecycle_3_to_5_years",
        "lifecycle_1_to_3_years",
        "lifecycle_current",
        "lifecycle_stage_status",
    ):
        if column_exists(TABLE_NAME, column_name):
            op.drop_column(TABLE_NAME, column_name)
