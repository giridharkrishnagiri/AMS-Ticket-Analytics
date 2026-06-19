"""add upload batch lifecycle timestamps

Revision ID: 20260617_0007
Revises: 20260617_0006
Create Date: 2026-06-17 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260617_0007"
down_revision: str | None = "20260617_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "upload_batches",
        sa.Column("normalized_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "upload_batches",
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "upload_batches",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("upload_batches", "deleted_at")
    op.drop_column("upload_batches", "archived_at")
    op.drop_column("upload_batches", "normalized_at")
