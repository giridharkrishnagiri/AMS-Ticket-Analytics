"""add ticket classification cluster ids

Revision ID: 20260721_0050
Revises: 20260721_0049
Create Date: 2026-07-21 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260721_0050"
down_revision: str | None = "20260721_0049"
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
    if not table_exists("genai_ticket_classifications"):
        return

    for column_name in (
        "genai_category_cluster_id",
        "genai_subcategory_1_cluster_id",
        "genai_subcategory_2_cluster_id",
    ):
        if not column_exists("genai_ticket_classifications", column_name):
            op.add_column(
                "genai_ticket_classifications",
                sa.Column(column_name, sa.String(length=80), nullable=True),
            )
        index_name = f"ix_genai_ticket_classifications_{column_name}"
        if not index_exists(index_name, "genai_ticket_classifications"):
            op.create_index(index_name, "genai_ticket_classifications", [column_name])

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            """
            UPDATE genai_ticket_classifications
            SET
                genai_category_cluster_id = CASE
                    WHEN metadata_json ? 'cluster_level_1'
                         AND NULLIF(metadata_json->>'cluster_level_1', '') IS NOT NULL
                    THEN 'Category-' || lpad(
                        regexp_replace(metadata_json->>'cluster_level_1', '^.*?(\\d+)$', '\\1'),
                        4,
                        '0'
                    )
                    ELSE genai_category_cluster_id
                END,
                genai_subcategory_1_cluster_id = CASE
                    WHEN metadata_json ? 'cluster_level_2'
                         AND NULLIF(metadata_json->>'cluster_level_2', '') IS NOT NULL
                    THEN 'SubCategory-1-' || lpad(
                        regexp_replace(metadata_json->>'cluster_level_2', '^.*?(\\d+)$', '\\1'),
                        4,
                        '0'
                    )
                    ELSE genai_subcategory_1_cluster_id
                END,
                genai_subcategory_2_cluster_id = CASE
                    WHEN metadata_json ? 'cluster_level_3'
                         AND NULLIF(metadata_json->>'cluster_level_3', '') IS NOT NULL
                    THEN 'SubCategory-2-' || lpad(
                        regexp_replace(metadata_json->>'cluster_level_3', '^.*?(\\d+)$', '\\1'),
                        4,
                        '0'
                    )
                    ELSE genai_subcategory_2_cluster_id
                END
            WHERE metadata_json IS NOT NULL
            """
        )


def downgrade() -> None:
    if not table_exists("genai_ticket_classifications"):
        return
    for column_name in (
        "genai_subcategory_2_cluster_id",
        "genai_subcategory_1_cluster_id",
        "genai_category_cluster_id",
    ):
        index_name = f"ix_genai_ticket_classifications_{column_name}"
        if index_exists(index_name, "genai_ticket_classifications"):
            op.drop_index(index_name, table_name="genai_ticket_classifications")
        if column_exists("genai_ticket_classifications", column_name):
            op.drop_column("genai_ticket_classifications", column_name)
