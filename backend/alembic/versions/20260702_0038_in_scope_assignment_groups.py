"""add in-scope assignment group reference

Revision ID: 20260702_0038
Revises: 20260701_0037
Create Date: 2026-07-02 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260702_0038"
down_revision: str | None = "20260701_0037"
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


def index_exists(table_name: str, index_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return any(index["name"] == index_name for index in inspector.get_indexes(table_name))


def upgrade() -> None:
    if not table_exists("in_scope_assignment_groups"):
        op.create_table(
            "in_scope_assignment_groups",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column("client_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("assignment_group", sa.Text(), nullable=False),
            sa.Column("assignment_group_key", sa.Text(), nullable=False),
            sa.Column("functional_track", sa.Text(), nullable=True),
            sa.Column("source_filename", sa.Text(), nullable=True),
            sa.Column("source_row_number", sa.Integer(), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "project_id",
                "assignment_group_key",
                name="uq_in_scope_assignment_groups_project_key",
            ),
        )
    for index_name, columns in (
        ("ix_in_scope_assignment_groups_project_id", ["project_id"]),
        ("ix_in_scope_assignment_groups_client_id", ["client_id"]),
        ("ix_in_scope_assignment_groups_assignment_group_key", ["assignment_group_key"]),
        ("ix_in_scope_assignment_groups_project_active", ["project_id", "is_active"]),
    ):
        if not index_exists("in_scope_assignment_groups", index_name):
            op.create_index(index_name, "in_scope_assignment_groups", columns)

    if table_exists("application_inventory_items") and not column_exists(
        "application_inventory_items",
        "scope_status",
    ):
        op.add_column(
            "application_inventory_items",
            sa.Column("scope_status", sa.Text(), nullable=False, server_default="unknown"),
        )
        op.alter_column("application_inventory_items", "scope_status", server_default=None)
    if table_exists("application_inventory_items") and not index_exists(
        "application_inventory_items",
        "ix_application_inventory_project_scope_status",
    ):
        op.create_index(
            "ix_application_inventory_project_scope_status",
            "application_inventory_items",
            ["project_id", "scope_status"],
        )


def downgrade() -> None:
    if table_exists("application_inventory_items") and index_exists(
        "application_inventory_items",
        "ix_application_inventory_project_scope_status",
    ):
        op.drop_index(
            "ix_application_inventory_project_scope_status",
            table_name="application_inventory_items",
        )
    if table_exists("application_inventory_items") and column_exists(
        "application_inventory_items",
        "scope_status",
    ):
        op.drop_column("application_inventory_items", "scope_status")

    if table_exists("in_scope_assignment_groups"):
        for index_name in (
            "ix_in_scope_assignment_groups_project_active",
            "ix_in_scope_assignment_groups_assignment_group_key",
            "ix_in_scope_assignment_groups_client_id",
            "ix_in_scope_assignment_groups_project_id",
        ):
            if index_exists("in_scope_assignment_groups", index_name):
                op.drop_index(index_name, table_name="in_scope_assignment_groups")
        op.drop_table("in_scope_assignment_groups")
