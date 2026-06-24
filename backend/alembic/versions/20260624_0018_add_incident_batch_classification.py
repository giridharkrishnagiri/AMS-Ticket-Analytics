"""add Incident batch classification

Revision ID: 20260624_0018
Revises: 20260623_0017
Create Date: 2026-06-24 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260624_0018"
down_revision: str | None = "20260623_0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


TABLES = ("tickets", "assessment_out_of_scope_tickets")

INDEXES = (
    ("ix_tickets_project_is_batch_related", "tickets"),
    ("ix_oos_tickets_project_is_batch_related", "assessment_out_of_scope_tickets"),
)


def column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def index_exists(table_name: str, index_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return any(index["name"] == index_name for index in inspector.get_indexes(table_name))


def add_is_batch_related_column(table_name: str) -> None:
    if not column_exists(table_name, "is_batch_related"):
        op.add_column(
            table_name,
            sa.Column(
                "is_batch_related",
                sa.Boolean(),
                server_default=sa.false(),
                nullable=False,
            ),
        )


def update_is_batch_related(table_name: str) -> None:
    op.execute(
        sa.text(
            f"""
            UPDATE {table_name}
            SET is_batch_related =
                CASE
                    WHEN upper(btrim(coalesce(ticket_type, ''))) = 'INCIDENT'
                     AND lower(coalesce(short_description, '')) LIKE '%automic%'
                    THEN true
                    ELSE false
                END
            """,
        ),
    )


def upgrade() -> None:
    for table_name in TABLES:
        add_is_batch_related_column(table_name)
        update_is_batch_related(table_name)

    for index_name, table_name in INDEXES:
        if not index_exists(table_name, index_name):
            op.create_index(index_name, table_name, ["project_id", "is_batch_related"])


def downgrade() -> None:
    for index_name, table_name in reversed(INDEXES):
        if index_exists(table_name, index_name):
            op.drop_index(index_name, table_name=table_name)

    for table_name in reversed(TABLES):
        if column_exists(table_name, "is_batch_related"):
            op.drop_column(table_name, "is_batch_related")
