"""add single-table ticket scope flags

Revision ID: 20260716_0047
Revises: 20260711_0046
Create Date: 2026-07-16 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260716_0047"
down_revision: str | None = "20260711_0046"
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
    if not column_exists("tickets", "is_in_scope"):
        op.add_column(
            "tickets",
            sa.Column(
                "is_in_scope",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            ),
        )
        op.execute("UPDATE tickets SET is_in_scope = true")
    if not index_exists("ix_tickets_is_in_scope", "tickets"):
        op.create_index("ix_tickets_is_in_scope", "tickets", ["is_in_scope"])
    if not index_exists("ix_tickets_project_type_is_in_scope", "tickets"):
        op.create_index(
            "ix_tickets_project_type_is_in_scope",
            "tickets",
            ["project_id", "ticket_type", "is_in_scope"],
        )

    if not column_exists("in_scope_assignment_groups", "is_in_scope"):
        op.add_column(
            "in_scope_assignment_groups",
            sa.Column(
                "is_in_scope",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            ),
        )
    if not index_exists(
        "ix_in_scope_assignment_groups_project_scope",
        "in_scope_assignment_groups",
    ):
        op.create_index(
            "ix_in_scope_assignment_groups_project_scope",
            "in_scope_assignment_groups",
            ["project_id", "is_in_scope"],
        )


def downgrade() -> None:
    if index_exists(
        "ix_in_scope_assignment_groups_project_scope",
        "in_scope_assignment_groups",
    ):
        op.drop_index(
            "ix_in_scope_assignment_groups_project_scope",
            table_name="in_scope_assignment_groups",
        )
    if column_exists("in_scope_assignment_groups", "is_in_scope"):
        op.drop_column("in_scope_assignment_groups", "is_in_scope")

    if index_exists("ix_tickets_project_type_is_in_scope", "tickets"):
        op.drop_index("ix_tickets_project_type_is_in_scope", table_name="tickets")
    if index_exists("ix_tickets_is_in_scope", "tickets"):
        op.drop_index("ix_tickets_is_in_scope", table_name="tickets")
    if column_exists("tickets", "is_in_scope"):
        op.drop_column("tickets", "is_in_scope")
