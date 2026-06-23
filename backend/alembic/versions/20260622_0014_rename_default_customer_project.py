"""rename default customer and project display names

Revision ID: 20260622_0014
Revises: 20260621_0013
Create Date: 2026-06-22 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260622_0014"
down_revision: str | None = "20260621_0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE clients
            SET name = 'Mondelez'
            WHERE code = 'DEFAULT'
              AND name = 'Default AMS Client'
            """,
        ),
    )
    op.execute(
        sa.text(
            """
            UPDATE projects
            SET name = 'AMS Apps & Volumetrics Analytics'
            WHERE code = 'AMS-TICKET-INTELLIGENCE'
              AND name IN (
                  'AMS Ticket Intelligence',
                  'Default AMS Project',
                  'Default Project'
              )
            """,
        ),
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE projects
            SET name = 'AMS Ticket Intelligence'
            WHERE code = 'AMS-TICKET-INTELLIGENCE'
              AND name = 'AMS Apps & Volumetrics Analytics'
            """,
        ),
    )
    op.execute(
        sa.text(
            """
            UPDATE clients
            SET name = 'Default AMS Client'
            WHERE code = 'DEFAULT'
              AND name = 'Mondelez'
            """,
        ),
    )
