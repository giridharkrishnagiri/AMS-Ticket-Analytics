"""add SAP / Non-SAP classification

Revision ID: 20260623_0017
Revises: 20260622_0016
Create Date: 2026-06-23 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260623_0017"
down_revision: str | None = "20260622_0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


TABLES = (
    "application_inventory_items",
    "tickets",
    "assessment_out_of_scope_tickets",
)

INDEXES = (
    (
        "ix_application_inventory_project_sap_non_sap",
        "application_inventory_items",
    ),
    ("ix_tickets_project_sap_non_sap", "tickets"),
    ("ix_oos_tickets_project_sap_non_sap", "assessment_out_of_scope_tickets"),
)


def column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def index_exists(table_name: str, index_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return any(index["name"] == index_name for index in inspector.get_indexes(table_name))


def add_sap_non_sap_column(table_name: str) -> None:
    if not column_exists(table_name, "sap_non_sap"):
        op.add_column(table_name, sa.Column("sap_non_sap", sa.Text(), nullable=True))


def update_sap_non_sap(table_name: str) -> None:
    op.execute(
        sa.text(
            f"""
            UPDATE {table_name}
            SET sap_non_sap =
                CASE
                    WHEN upper(btrim(coalesce(assignment_group, ''))) LIKE 'IT-SAP%'
                    THEN 'SAP'
                    WHEN upper(btrim(coalesce(assignment_group, ''))) LIKE 'IT-NSA%'
                    THEN 'Non-SAP'
                    ELSE NULL
                END
            """,
        ),
    )


def upgrade() -> None:
    for table_name in TABLES:
        add_sap_non_sap_column(table_name)
        update_sap_non_sap(table_name)

    for index_name, table_name in INDEXES:
        if not index_exists(table_name, index_name):
            op.create_index(index_name, table_name, ["project_id", "sap_non_sap"])


def downgrade() -> None:
    for index_name, table_name in reversed(INDEXES):
        if index_exists(table_name, index_name):
            op.drop_index(index_name, table_name=table_name)

    for table_name in reversed(TABLES):
        if column_exists(table_name, "sap_non_sap"):
            op.drop_column(table_name, "sap_non_sap")
