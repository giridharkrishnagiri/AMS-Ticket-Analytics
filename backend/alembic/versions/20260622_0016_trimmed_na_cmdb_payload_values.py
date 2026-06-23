"""null trimmed application inventory cmdb payload #N/A values

Revision ID: 20260622_0016
Revises: 20260622_0015
Create Date: 2026-06-22 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260622_0016"
down_revision: str | None = "20260622_0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE application_inventory_items AS target
            SET cmdb_payload = cleaned.cleaned_payload
            FROM (
                SELECT
                    item.id,
                    jsonb_object_agg(
                        payload.key,
                        CASE
                            WHEN jsonb_typeof(payload.value) = 'string'
                             AND upper(btrim(payload.value #>> '{}')) = '#N/A'
                            THEN 'null'::jsonb
                            ELSE payload.value
                        END
                    ) AS cleaned_payload
                FROM application_inventory_items AS item
                CROSS JOIN LATERAL jsonb_each(item.cmdb_payload) AS payload(key, value)
                WHERE item.cmdb_payload IS NOT NULL
                GROUP BY item.id
            ) AS cleaned
            WHERE target.id = cleaned.id
              AND target.cmdb_payload IS DISTINCT FROM cleaned.cleaned_payload
            """,
        ),
    )


def downgrade() -> None:
    pass
