"""add source filename to ticket raw rows

Revision ID: 20260615_0003
Revises: 20260615_0002
Create Date: 2026-06-15 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260615_0003"
down_revision: str | None = "20260615_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "ticket_raw_rows",
        sa.Column("source_filename", sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("ticket_raw_rows", "source_filename")
