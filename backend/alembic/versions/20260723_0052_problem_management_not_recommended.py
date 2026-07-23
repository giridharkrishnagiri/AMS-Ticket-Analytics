"""mark problem management as not recommended automation

Revision ID: 20260723_0052
Revises: 20260723_0051
Create Date: 2026-07-23 23:35:00.000000
"""

from __future__ import annotations

from alembic import op


revision = "20260723_0052"
down_revision = "20260723_0051"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE genai_ticket_automation_assessments
        SET automation_potential = 'Not Recommended'
        WHERE recommended_resolution_path = 'Problem Management'
          AND status = 'success'
        """,
    )


def downgrade() -> None:
    # Data correction is intentionally not reversible.
    pass
