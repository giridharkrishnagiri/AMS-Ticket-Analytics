"""add genai ticket classification enrichment table

Revision ID: 20260721_0048
Revises: 20260716_0047
Create Date: 2026-07-21 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260721_0048"
down_revision: str | None = "20260716_0047"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def index_exists(index_name: str, table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return any(index["name"] == index_name for index in inspector.get_indexes(table_name))


def upgrade() -> None:
    if not table_exists("genai_ticket_classifications"):
        op.create_table(
            "genai_ticket_classifications",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("ticket_number", sa.String(length=255), nullable=False),
            sa.Column("ticket_type", sa.String(length=40), nullable=False),
            sa.Column("analysis_month", sa.String(length=7), nullable=False),
            sa.Column("input_hash", sa.String(length=64), nullable=False),
            sa.Column("prompt_key", sa.String(length=100), nullable=False),
            sa.Column("prompt_version", sa.Integer(), nullable=False),
            sa.Column("model_name", sa.String(length=255), nullable=True),
            sa.Column("status", sa.String(length=40), nullable=False),
            sa.Column("category_quality", sa.String(length=40), nullable=True),
            sa.Column("genai_category", sa.String(length=255), nullable=True),
            sa.Column("genai_subcategory_1", sa.String(length=255), nullable=True),
            sa.Column("genai_subcategory_2", sa.String(length=255), nullable=True),
            sa.Column("confidence", sa.Float(), nullable=True),
            sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
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
            sa.ForeignKeyConstraint(["customer_id"], ["clients.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "project_id",
                "analysis_month",
                "ticket_number",
                name="uq_genai_ticket_classifications_project_month_ticket",
            ),
        )
    for index_name, columns in (
        ("ix_genai_ticket_classifications_customer_id", ["customer_id"]),
        ("ix_genai_ticket_classifications_project_id", ["project_id"]),
        ("ix_genai_ticket_classifications_ticket_number", ["ticket_number"]),
        ("ix_genai_ticket_classifications_ticket_type", ["ticket_type"]),
        ("ix_genai_ticket_classifications_analysis_month", ["analysis_month"]),
        ("ix_genai_ticket_classifications_input_hash", ["input_hash"]),
        ("ix_genai_ticket_classifications_status", ["status"]),
        ("ix_genai_ticket_classifications_genai_category", ["genai_category"]),
        ("ix_genai_ticket_classifications_genai_subcategory_1", ["genai_subcategory_1"]),
        ("ix_genai_ticket_classifications_genai_subcategory_2", ["genai_subcategory_2"]),
    ):
        if not index_exists(index_name, "genai_ticket_classifications"):
            op.create_index(index_name, "genai_ticket_classifications", columns)
    if not index_exists(
        "ix_genai_ticket_classifications_project_month_status",
        "genai_ticket_classifications",
    ):
        op.create_index(
            "ix_genai_ticket_classifications_project_month_status",
            "genai_ticket_classifications",
            ["project_id", "analysis_month", "status"],
        )
    if not index_exists(
        "ix_genai_ticket_classifications_category",
        "genai_ticket_classifications",
    ):
        op.create_index(
            "ix_genai_ticket_classifications_category",
            "genai_ticket_classifications",
            [
                "project_id",
                "analysis_month",
                "genai_category",
                "genai_subcategory_1",
                "genai_subcategory_2",
            ],
        )


def downgrade() -> None:
    if table_exists("genai_ticket_classifications"):
        op.drop_table("genai_ticket_classifications")
