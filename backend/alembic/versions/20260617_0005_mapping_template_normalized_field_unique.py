"""allow mapping templates to reuse source columns

Revision ID: 20260617_0005
Revises: 20260616_0004
Create Date: 2026-06-17 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260617_0005"
down_revision: str | None = "20260616_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "uq_source_column_mappings_source_column",
        "source_column_mappings",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_source_column_mappings_normalized_field",
        "source_column_mappings",
        ["project_id", "ticket_type", "normalized_field_name"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_source_column_mappings_normalized_field",
        "source_column_mappings",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_source_column_mappings_source_column",
        "source_column_mappings",
        ["project_id", "ticket_type", "source_column_name"],
    )
