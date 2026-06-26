"""add dashboard commentaries

Revision ID: 20260626_0022
Revises: 20260625_0021
Create Date: 2026-06-26 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260626_0022"
down_revision: str | None = "20260625_0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    if table_exists("dashboard_commentaries"):
        return

    op.create_table(
        "dashboard_commentaries",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("dashboard_area", sa.String(length=100), nullable=False),
        sa.Column("tab_name", sa.String(length=100), nullable=False),
        sa.Column("sub_tab_name", sa.String(length=100), nullable=False, server_default=""),
        sa.Column("section_key", sa.String(length=150), nullable=False),
        sa.Column("chart_key", sa.String(length=150), nullable=False, server_default=""),
        sa.Column("scope_filter", sa.String(length=50), nullable=False),
        sa.Column("ticket_type_filter", sa.String(length=50), nullable=False),
        sa.Column("functional_track_ams_owner", sa.String(length=255), nullable=False),
        sa.Column("commentary_html", sa.Text(), nullable=True),
        sa.Column("commentary_text", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=255), nullable=True),
        sa.Column("updated_by", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id",
            "dashboard_area",
            "tab_name",
            "sub_tab_name",
            "section_key",
            "chart_key",
            "scope_filter",
            "ticket_type_filter",
            "functional_track_ams_owner",
            name="uq_dashboard_commentary_context",
        ),
    )
    op.create_index(
        "ix_dashboard_commentaries_client_id",
        "dashboard_commentaries",
        ["client_id"],
    )
    op.create_index(
        "ix_dashboard_commentaries_project_id",
        "dashboard_commentaries",
        ["project_id"],
    )


def downgrade() -> None:
    if table_exists("dashboard_commentaries"):
        op.drop_table("dashboard_commentaries")
