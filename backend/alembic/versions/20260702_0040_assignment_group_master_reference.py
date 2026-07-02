"""add assignment group master reference

Revision ID: 20260702_0040
Revises: 20260702_0039
Create Date: 2026-07-02 01:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260702_0040"
down_revision: str | None = "20260702_0039"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def index_exists(table_name: str, index_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return any(index["name"] == index_name for index in inspector.get_indexes(table_name))


def upgrade() -> None:
    if not table_exists("assignment_group_master_reference"):
        op.create_table(
            "assignment_group_master_reference",
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
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("manager_name", sa.Text(), nullable=True),
            sa.Column("source_filename", sa.Text(), nullable=True),
            sa.Column("source_sheet_name", sa.Text(), nullable=True),
            sa.Column("source_row_number", sa.Integer(), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "project_id",
                "assignment_group_key",
                name="uq_assignment_group_master_reference_project_key",
            ),
        )

    for index_name, columns in (
        ("ix_assignment_group_master_reference_project_id", ["project_id"]),
        ("ix_assignment_group_master_reference_client_id", ["client_id"]),
        (
            "ix_assignment_group_master_reference_assignment_group_key",
            ["assignment_group_key"],
        ),
        ("ix_assignment_group_master_reference_project_active", ["project_id", "is_active"]),
    ):
        if not index_exists("assignment_group_master_reference", index_name):
            op.create_index(index_name, "assignment_group_master_reference", columns)


def downgrade() -> None:
    if not table_exists("assignment_group_master_reference"):
        return

    for index_name in (
        "ix_assignment_group_master_reference_project_active",
        "ix_assignment_group_master_reference_assignment_group_key",
        "ix_assignment_group_master_reference_client_id",
        "ix_assignment_group_master_reference_project_id",
    ):
        if index_exists("assignment_group_master_reference", index_name):
            op.drop_index(index_name, table_name="assignment_group_master_reference")
    op.drop_table("assignment_group_master_reference")
