"""add dashboard filter cache

Revision ID: 20260629_0033
Revises: 20260629_0032
Create Date: 2026-06-29 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260629_0033"
down_revision: str | None = "20260629_0032"
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
    if table_exists("dashboard_filter_facts"):
        if not column_exists("dashboard_filter_facts", "dashboard_area"):
            op.add_column(
                "dashboard_filter_facts",
                sa.Column(
                    "dashboard_area",
                    sa.String(length=50),
                    nullable=False,
                    server_default="volumetrics",
                ),
            )
            op.alter_column("dashboard_filter_facts", "dashboard_area", server_default=None)
        if not column_exists("dashboard_filter_facts", "record_domain"):
            op.add_column(
                "dashboard_filter_facts",
                sa.Column(
                    "record_domain",
                    sa.String(length=50),
                    nullable=False,
                    server_default="ticket",
                ),
            )
            op.alter_column("dashboard_filter_facts", "record_domain", server_default=None)
        if not column_exists("dashboard_filter_facts", "global_flag"):
            op.add_column(
                "dashboard_filter_facts",
                sa.Column("global_flag", sa.String(length=50), nullable=True),
            )
        if not column_exists("dashboard_filter_facts", "life_cycle_stage"):
            op.add_column(
                "dashboard_filter_facts",
                sa.Column("life_cycle_stage", sa.String(length=255), nullable=True),
            )
        if not column_exists("dashboard_filter_facts", "life_cycle_stage_status"):
            op.add_column(
                "dashboard_filter_facts",
                sa.Column("life_cycle_stage_status", sa.String(length=255), nullable=True),
            )
        if not column_exists("dashboard_filter_facts", "data_version"):
            op.add_column(
                "dashboard_filter_facts",
                sa.Column("data_version", sa.String(length=50), nullable=True),
            )

        op.create_index(
            "ix_dashboard_filter_facts_project_area",
            "dashboard_filter_facts",
            ["project_id", "dashboard_area"],
        )
        op.create_index(
            "ix_dashboard_filter_facts_project_area_domain",
            "dashboard_filter_facts",
            ["project_id", "dashboard_area", "record_domain"],
        )
        op.create_index(
            "ix_dashboard_filter_facts_project_area_version",
            "dashboard_filter_facts",
            ["project_id", "dashboard_area", "data_version"],
        )

    if not table_exists("dashboard_filter_catalog"):
        op.create_table(
            "dashboard_filter_catalog",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("dashboard_area", sa.String(length=50), nullable=False),
            sa.Column("filter_key", sa.String(length=100), nullable=False),
            sa.Column("filter_value", sa.Text(), nullable=False),
            sa.Column("display_value", sa.Text(), nullable=False),
            sa.Column("baseline_count", sa.Integer(), nullable=False),
            sa.Column("sort_order", sa.Integer(), nullable=False),
            sa.Column("data_version", sa.String(length=50), nullable=False),
            sa.Column("refreshed_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["customer_id"], ["clients.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "customer_id",
                "project_id",
                "dashboard_area",
                "filter_key",
                "filter_value",
                "data_version",
                name="uq_dashboard_filter_catalog_value_version",
            ),
        )
        op.create_index(
            "ix_dashboard_filter_catalog_project_area",
            "dashboard_filter_catalog",
            ["customer_id", "project_id", "dashboard_area"],
        )
        op.create_index(
            "ix_dashboard_filter_catalog_project_area_key",
            "dashboard_filter_catalog",
            ["customer_id", "project_id", "dashboard_area", "filter_key"],
        )
        op.create_index(
            "ix_dashboard_filter_catalog_project_area_key_value",
            "dashboard_filter_catalog",
            ["customer_id", "project_id", "dashboard_area", "filter_key", "filter_value"],
        )
        op.create_index(
            "ix_dashboard_filter_catalog_data_version",
            "dashboard_filter_catalog",
            ["data_version"],
        )

    if not table_exists("dashboard_filter_cache_status"):
        op.create_table(
            "dashboard_filter_cache_status",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("dashboard_area", sa.String(length=50), nullable=False),
            sa.Column("status", sa.String(length=50), nullable=False),
            sa.Column("data_version", sa.String(length=50), nullable=True),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("is_stale", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["customer_id"], ["clients.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "customer_id",
                "project_id",
                "dashboard_area",
                name="uq_dashboard_filter_cache_status_area",
            ),
        )
        op.create_index(
            "ix_dashboard_filter_cache_status_project_area",
            "dashboard_filter_cache_status",
            ["customer_id", "project_id", "dashboard_area"],
        )


def downgrade() -> None:
    if table_exists("dashboard_filter_cache_status"):
        op.drop_table("dashboard_filter_cache_status")
    if table_exists("dashboard_filter_catalog"):
        op.drop_table("dashboard_filter_catalog")
    if table_exists("dashboard_filter_facts"):
        op.drop_index("ix_dashboard_filter_facts_project_area_version", table_name="dashboard_filter_facts")
        op.drop_index("ix_dashboard_filter_facts_project_area_domain", table_name="dashboard_filter_facts")
        op.drop_index("ix_dashboard_filter_facts_project_area", table_name="dashboard_filter_facts")
        for column_name in (
            "data_version",
            "life_cycle_stage_status",
            "life_cycle_stage",
            "global_flag",
            "record_domain",
            "dashboard_area",
        ):
            if column_exists("dashboard_filter_facts", column_name):
                op.drop_column("dashboard_filter_facts", column_name)

