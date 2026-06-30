"""add problem linked incident count

Revision ID: 20260701_0035
Revises: 20260630_0034
Create Date: 2026-07-01 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260701_0035"
down_revision: str | None = "20260630_0034"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def upgrade() -> None:
    if not table_exists("assessment_problem_records"):
        return

    if not column_exists("assessment_problem_records", "linked_incident_count"):
        op.add_column(
            "assessment_problem_records",
            sa.Column(
                "linked_incident_count",
                sa.Integer(),
                nullable=False,
                server_default="0",
            ),
        )

    op.execute(
        """
        UPDATE assessment_problem_records
        SET linked_incident_count = GREATEST(
            CASE
                WHEN related_incidents IS NULL OR btrim(related_incidents) = '' THEN 0
                WHEN btrim(related_incidents) ~ '^-?[0-9]+(\\.[0-9]+)?$'
                    THEN floor((btrim(related_incidents))::numeric)::integer
                ELSE COALESCE((
                    SELECT count(*)::integer
                    FROM regexp_matches(related_incidents, '(?i)\\mINC[0-9][0-9A-Z-]*\\M', 'g')
                ), 0)
            END,
            0
        )
        WHERE linked_incident_count = 0
        """,
    )

    op.alter_column(
        "assessment_problem_records",
        "linked_incident_count",
        server_default=None,
    )
    op.create_index(
        "ix_problem_records_project_linked_incident_count",
        "assessment_problem_records",
        ["project_id", "linked_incident_count"],
        unique=False,
        if_not_exists=True,
    )


def downgrade() -> None:
    if not table_exists("assessment_problem_records"):
        return

    op.drop_index(
        "ix_problem_records_project_linked_incident_count",
        table_name="assessment_problem_records",
        if_exists=True,
    )
    if column_exists("assessment_problem_records", "linked_incident_count"):
        op.drop_column("assessment_problem_records", "linked_incident_count")
