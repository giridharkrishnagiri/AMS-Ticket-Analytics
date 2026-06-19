"""add dashboard foundation fields

Revision ID: 20260616_0004
Revises: 20260615_0003
Create Date: 2026-06-16 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260616_0004"
down_revision: str | None = "20260615_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "application_dimensions",
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("customer_name", sa.String(length=255), nullable=True),
        sa.Column("tower_name", sa.String(length=255), nullable=True),
        sa.Column("cluster_name", sa.String(length=255), nullable=True),
        sa.Column("application_group_name", sa.String(length=255), nullable=True),
        sa.Column("application_name", sa.String(length=255), nullable=False),
        sa.Column("application_aliases", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "business_service_aliases",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("cmdb_ci_aliases", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_application_dimensions_application_group_name",
        "application_dimensions",
        ["application_group_name"],
    )
    op.create_index(
        "ix_application_dimensions_application_name",
        "application_dimensions",
        ["application_name"],
    )
    op.create_index(
        "ix_application_dimensions_cluster_name",
        "application_dimensions",
        ["cluster_name"],
    )
    op.create_index(
        "ix_application_dimensions_customer_name",
        "application_dimensions",
        ["customer_name"],
    )
    op.create_index(
        "ix_application_dimensions_is_active",
        "application_dimensions",
        ["is_active"],
    )
    op.create_index(
        "ix_application_dimensions_project_id",
        "application_dimensions",
        ["project_id"],
    )
    op.create_index(
        "ix_application_dimensions_tower_name",
        "application_dimensions",
        ["tower_name"],
    )

    op.add_column(
        "tickets",
        sa.Column("application_dimension_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "tickets",
        sa.Column("business_duration_seconds", sa.BigInteger(), nullable=True),
    )
    op.add_column("tickets", sa.Column("reassignment_count", sa.Integer(), nullable=True))
    op.add_column(
        "tickets",
        sa.Column("system_creation_source", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "tickets",
        sa.Column("technical_functional_type", sa.String(length=40), nullable=True),
    )
    op.add_column(
        "tickets",
        sa.Column("technical_functional_confidence", sa.Numeric(precision=5, scale=4), nullable=True),
    )
    op.add_column(
        "tickets",
        sa.Column("technical_functional_reason", sa.Text(), nullable=True),
    )
    op.add_column(
        "tickets",
        sa.Column("technical_functional_classified_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_tickets_application_dimension_id_application_dimensions",
        "tickets",
        "application_dimensions",
        ["application_dimension_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_tickets_application_dimension_id",
        "tickets",
        ["application_dimension_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_tickets_application_dimension_id", table_name="tickets")
    op.drop_constraint(
        "fk_tickets_application_dimension_id_application_dimensions",
        "tickets",
        type_="foreignkey",
    )
    op.drop_column("tickets", "technical_functional_classified_at")
    op.drop_column("tickets", "technical_functional_reason")
    op.drop_column("tickets", "technical_functional_confidence")
    op.drop_column("tickets", "technical_functional_type")
    op.drop_column("tickets", "system_creation_source")
    op.drop_column("tickets", "reassignment_count")
    op.drop_column("tickets", "business_duration_seconds")
    op.drop_column("tickets", "application_dimension_id")

    op.drop_index("ix_application_dimensions_tower_name", table_name="application_dimensions")
    op.drop_index("ix_application_dimensions_project_id", table_name="application_dimensions")
    op.drop_index("ix_application_dimensions_is_active", table_name="application_dimensions")
    op.drop_index("ix_application_dimensions_customer_name", table_name="application_dimensions")
    op.drop_index("ix_application_dimensions_cluster_name", table_name="application_dimensions")
    op.drop_index("ix_application_dimensions_application_name", table_name="application_dimensions")
    op.drop_index(
        "ix_application_dimensions_application_group_name",
        table_name="application_dimensions",
    )
    op.drop_table("application_dimensions")
