"""add upload batch period metadata

Revision ID: 20260617_0006
Revises: 20260617_0005
Create Date: 2026-06-17 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260617_0006"
down_revision: str | None = "20260617_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "upload_batches",
        sa.Column("period_type", sa.String(length=40), server_default="MONTHLY", nullable=False),
    )
    op.add_column("upload_batches", sa.Column("snapshot_date", sa.Date(), nullable=True))
    op.create_index("ix_upload_batches_period_type", "upload_batches", ["period_type"])
    op.create_index("ix_upload_batches_snapshot_date", "upload_batches", ["snapshot_date"])
    op.alter_column(
        "upload_batches",
        "month_key",
        existing_type=sa.String(length=7),
        nullable=True,
    )
    op.alter_column(
        "tickets",
        "month_key",
        existing_type=sa.String(length=7),
        nullable=True,
    )


def downgrade() -> None:
    op.execute("UPDATE tickets SET month_key = '1970-01' WHERE month_key IS NULL")
    op.execute("UPDATE upload_batches SET month_key = '1970-01' WHERE month_key IS NULL")
    op.alter_column(
        "tickets",
        "month_key",
        existing_type=sa.String(length=7),
        nullable=False,
    )
    op.alter_column(
        "upload_batches",
        "month_key",
        existing_type=sa.String(length=7),
        nullable=False,
    )
    op.drop_index("ix_upload_batches_snapshot_date", table_name="upload_batches")
    op.drop_index("ix_upload_batches_period_type", table_name="upload_batches")
    op.drop_column("upload_batches", "snapshot_date")
    op.drop_column("upload_batches", "period_type")
