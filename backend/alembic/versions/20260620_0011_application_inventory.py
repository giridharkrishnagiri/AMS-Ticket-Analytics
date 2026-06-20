"""add application inventory upload and ticket enrichment fields

Revision ID: 20260620_0011
Revises: 20260619_0010
Create Date: 2026-06-20 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260620_0011"
down_revision: str | None = "20260619_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "application_inventory_items",
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("application_number_apm", sa.Text(), nullable=True),
        sa.Column("parent_application_name", sa.Text(), nullable=True),
        sa.Column("assignment_group", sa.Text(), nullable=True),
        sa.Column("assignment_group_owner", sa.Text(), nullable=True),
        sa.Column("application_owner", sa.Text(), nullable=True),
        sa.Column("business_service_ci_name", sa.Text(), nullable=False),
        sa.Column("support_lead", sa.Text(), nullable=True),
        sa.Column("functional_track", sa.Text(), nullable=True),
        sa.Column("ams_owner", sa.Text(), nullable=True),
        sa.Column("supported_by_vendor", sa.Text(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=True),
        sa.Column("cmdb_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("source_filename", sa.Text(), nullable=True),
        sa.Column("source_row_number", sa.Integer(), nullable=True),
        sa.Column(
            "id",
            sa.UUID(),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_application_inventory_project_id",
        "application_inventory_items",
        ["project_id"],
    )
    op.create_index(
        "ix_application_inventory_project_business_service",
        "application_inventory_items",
        ["project_id", "business_service_ci_name"],
    )
    op.create_index(
        "ix_application_inventory_project_business_service_group",
        "application_inventory_items",
        ["project_id", "business_service_ci_name", "assignment_group"],
    )
    op.create_index(
        "ix_application_inventory_project_parent_app",
        "application_inventory_items",
        ["project_id", "parent_application_name"],
    )
    op.create_index(
        "ix_application_inventory_project_assignment_group",
        "application_inventory_items",
        ["project_id", "assignment_group"],
    )
    op.create_index(
        "ix_application_inventory_project_application_owner",
        "application_inventory_items",
        ["project_id", "application_owner"],
    )
    op.create_index(
        "ix_application_inventory_project_support_lead",
        "application_inventory_items",
        ["project_id", "support_lead"],
    )
    op.create_index(
        "ix_application_inventory_project_functional_track",
        "application_inventory_items",
        ["project_id", "functional_track"],
    )
    op.create_index(
        "ix_application_inventory_project_ams_owner",
        "application_inventory_items",
        ["project_id", "ams_owner"],
    )
    op.create_index(
        "ix_application_inventory_project_vendor",
        "application_inventory_items",
        ["project_id", "supported_by_vendor"],
    )

    op.add_column("tickets", sa.Column("application_inventory_id", sa.UUID(), nullable=True))
    op.add_column("tickets", sa.Column("parent_application_number", sa.Text(), nullable=True))
    op.add_column("tickets", sa.Column("parent_application_name", sa.Text(), nullable=True))
    op.add_column("tickets", sa.Column("business_service_ci_name", sa.Text(), nullable=True))
    op.add_column("tickets", sa.Column("application_owner", sa.Text(), nullable=True))
    op.add_column("tickets", sa.Column("support_lead", sa.Text(), nullable=True))
    op.add_column("tickets", sa.Column("functional_track", sa.Text(), nullable=True))
    op.add_column("tickets", sa.Column("ams_owner", sa.Text(), nullable=True))
    op.add_column("tickets", sa.Column("supported_by_vendor", sa.Text(), nullable=True))
    op.add_column("tickets", sa.Column("assignment_group_owner", sa.Text(), nullable=True))
    op.create_foreign_key(
        "fk_tickets_application_inventory_id",
        "tickets",
        "application_inventory_items",
        ["application_inventory_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_tickets_project_application_inventory_id",
        "tickets",
        ["project_id", "application_inventory_id"],
    )
    op.create_index(
        "ix_tickets_project_business_service_ci_name",
        "tickets",
        ["project_id", "business_service_ci_name"],
    )
    op.create_index(
        "ix_tickets_project_parent_application_name",
        "tickets",
        ["project_id", "parent_application_name"],
    )
    op.create_index(
        "ix_tickets_project_application_owner",
        "tickets",
        ["project_id", "application_owner"],
    )
    op.create_index("ix_tickets_project_support_lead", "tickets", ["project_id", "support_lead"])
    op.create_index(
        "ix_tickets_project_functional_track",
        "tickets",
        ["project_id", "functional_track"],
    )
    op.create_index("ix_tickets_project_ams_owner", "tickets", ["project_id", "ams_owner"])
    op.create_index(
        "ix_tickets_project_supported_by_vendor",
        "tickets",
        ["project_id", "supported_by_vendor"],
    )


def downgrade() -> None:
    op.drop_index("ix_tickets_project_supported_by_vendor", table_name="tickets")
    op.drop_index("ix_tickets_project_ams_owner", table_name="tickets")
    op.drop_index("ix_tickets_project_functional_track", table_name="tickets")
    op.drop_index("ix_tickets_project_support_lead", table_name="tickets")
    op.drop_index("ix_tickets_project_application_owner", table_name="tickets")
    op.drop_index("ix_tickets_project_parent_application_name", table_name="tickets")
    op.drop_index("ix_tickets_project_business_service_ci_name", table_name="tickets")
    op.drop_index("ix_tickets_project_application_inventory_id", table_name="tickets")
    op.drop_constraint("fk_tickets_application_inventory_id", "tickets", type_="foreignkey")
    op.drop_column("tickets", "assignment_group_owner")
    op.drop_column("tickets", "supported_by_vendor")
    op.drop_column("tickets", "ams_owner")
    op.drop_column("tickets", "functional_track")
    op.drop_column("tickets", "support_lead")
    op.drop_column("tickets", "application_owner")
    op.drop_column("tickets", "business_service_ci_name")
    op.drop_column("tickets", "parent_application_name")
    op.drop_column("tickets", "parent_application_number")
    op.drop_column("tickets", "application_inventory_id")

    op.drop_index("ix_application_inventory_project_vendor", table_name="application_inventory_items")
    op.drop_index("ix_application_inventory_project_ams_owner", table_name="application_inventory_items")
    op.drop_index(
        "ix_application_inventory_project_functional_track",
        table_name="application_inventory_items",
    )
    op.drop_index(
        "ix_application_inventory_project_support_lead",
        table_name="application_inventory_items",
    )
    op.drop_index(
        "ix_application_inventory_project_application_owner",
        table_name="application_inventory_items",
    )
    op.drop_index(
        "ix_application_inventory_project_assignment_group",
        table_name="application_inventory_items",
    )
    op.drop_index(
        "ix_application_inventory_project_parent_app",
        table_name="application_inventory_items",
    )
    op.drop_index(
        "ix_application_inventory_project_business_service_group",
        table_name="application_inventory_items",
    )
    op.drop_index(
        "ix_application_inventory_project_business_service",
        table_name="application_inventory_items",
    )
    op.drop_index("ix_application_inventory_project_id", table_name="application_inventory_items")
    op.drop_table("application_inventory_items")
