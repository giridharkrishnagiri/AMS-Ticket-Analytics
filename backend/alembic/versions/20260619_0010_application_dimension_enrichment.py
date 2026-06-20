"""add application dimension aliases and ticket enrichment columns

Revision ID: 20260619_0010
Revises: 20260618_0009
Create Date: 2026-06-19 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260619_0010"
down_revision: str | None = "20260618_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("application_dimensions", sa.Column("application_alias", sa.Text(), nullable=True))
    op.add_column(
        "application_dimensions",
        sa.Column("business_service_alias", sa.Text(), nullable=True),
    )
    op.add_column("application_dimensions", sa.Column("cmdb_ci_alias", sa.Text(), nullable=True))
    op.add_column("application_dimensions", sa.Column("notes", sa.Text(), nullable=True))

    op.add_column("tickets", sa.Column("cmdb_ci", sa.String(length=255), nullable=True))
    op.add_column("tickets", sa.Column("customer_name", sa.String(length=255), nullable=True))
    op.add_column("tickets", sa.Column("tower_name", sa.String(length=255), nullable=True))
    op.add_column("tickets", sa.Column("cluster_name", sa.String(length=255), nullable=True))
    op.add_column(
        "tickets",
        sa.Column("application_group_name", sa.String(length=255), nullable=True),
    )
    op.add_column("tickets", sa.Column("application_name", sa.String(length=255), nullable=True))

    op.create_index(
        "ix_application_dimensions_project_active",
        "application_dimensions",
        ["project_id", "is_active"],
    )
    op.create_index(
        "ix_application_dimensions_project_application_name",
        "application_dimensions",
        ["project_id", "application_name"],
    )
    op.create_index(
        "ix_application_dimensions_project_application_alias",
        "application_dimensions",
        ["project_id", "application_alias"],
    )
    op.create_index(
        "ix_application_dimensions_project_business_service_alias",
        "application_dimensions",
        ["project_id", "business_service_alias"],
    )
    op.create_index(
        "ix_application_dimensions_project_cmdb_ci_alias",
        "application_dimensions",
        ["project_id", "cmdb_ci_alias"],
    )

    op.create_index("ix_tickets_project_application", "tickets", ["project_id", "application"])
    op.create_index(
        "ix_tickets_project_business_service",
        "tickets",
        ["project_id", "business_service"],
    )
    op.create_index("ix_tickets_project_cmdb_ci", "tickets", ["project_id", "cmdb_ci"])
    op.create_index(
        "ix_tickets_project_application_dimension_id",
        "tickets",
        ["project_id", "application_dimension_id"],
    )
    op.create_index("ix_tickets_project_customer_name", "tickets", ["project_id", "customer_name"])
    op.create_index("ix_tickets_project_tower_name", "tickets", ["project_id", "tower_name"])
    op.create_index("ix_tickets_project_cluster_name", "tickets", ["project_id", "cluster_name"])
    op.create_index(
        "ix_tickets_project_application_group_name",
        "tickets",
        ["project_id", "application_group_name"],
    )
    op.create_index(
        "ix_tickets_project_application_name",
        "tickets",
        ["project_id", "application_name"],
    )


def downgrade() -> None:
    op.drop_index("ix_tickets_project_application_name", table_name="tickets")
    op.drop_index("ix_tickets_project_application_group_name", table_name="tickets")
    op.drop_index("ix_tickets_project_cluster_name", table_name="tickets")
    op.drop_index("ix_tickets_project_tower_name", table_name="tickets")
    op.drop_index("ix_tickets_project_customer_name", table_name="tickets")
    op.drop_index("ix_tickets_project_application_dimension_id", table_name="tickets")
    op.drop_index("ix_tickets_project_cmdb_ci", table_name="tickets")
    op.drop_index("ix_tickets_project_business_service", table_name="tickets")
    op.drop_index("ix_tickets_project_application", table_name="tickets")

    op.drop_index(
        "ix_application_dimensions_project_cmdb_ci_alias",
        table_name="application_dimensions",
    )
    op.drop_index(
        "ix_application_dimensions_project_business_service_alias",
        table_name="application_dimensions",
    )
    op.drop_index(
        "ix_application_dimensions_project_application_alias",
        table_name="application_dimensions",
    )
    op.drop_index(
        "ix_application_dimensions_project_application_name",
        table_name="application_dimensions",
    )
    op.drop_index("ix_application_dimensions_project_active", table_name="application_dimensions")

    op.drop_column("tickets", "application_name")
    op.drop_column("tickets", "application_group_name")
    op.drop_column("tickets", "cluster_name")
    op.drop_column("tickets", "tower_name")
    op.drop_column("tickets", "customer_name")
    op.drop_column("tickets", "cmdb_ci")

    op.drop_column("application_dimensions", "notes")
    op.drop_column("application_dimensions", "cmdb_ci_alias")
    op.drop_column("application_dimensions", "business_service_alias")
    op.drop_column("application_dimensions", "application_alias")
