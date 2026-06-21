"""add incident sla upload history and row fingerprints

Revision ID: 20260621_0013
Revises: 20260620_0012
Create Date: 2026-06-21 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260621_0013"
down_revision: str | None = "20260620_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("incident_sla_rows", sa.Column("row_fingerprint", sa.Text(), nullable=True))
    op.create_index(
        "ix_incident_sla_rows_project_fingerprint",
        "incident_sla_rows",
        ["project_id", "row_fingerprint"],
    )

    op.create_table(
        "incident_sla_uploads",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("filename", sa.Text(), nullable=False),
        sa.Column("total_rows_read", sa.Integer(), nullable=False),
        sa.Column("inserted_rows", sa.Integer(), nullable=False),
        sa.Column("duplicate_rows_skipped", sa.Integer(), nullable=False),
        sa.Column("error_rows", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column(
            "uploaded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_incident_sla_uploads_project_id", "incident_sla_uploads", ["project_id"])
    op.create_index(
        "ix_incident_sla_uploads_project_uploaded_at",
        "incident_sla_uploads",
        ["project_id", "uploaded_at"],
    )
    op.create_index(
        "ix_incident_sla_uploads_project_filename",
        "incident_sla_uploads",
        ["project_id", "filename"],
    )


def downgrade() -> None:
    op.drop_index("ix_incident_sla_uploads_project_filename", table_name="incident_sla_uploads")
    op.drop_index(
        "ix_incident_sla_uploads_project_uploaded_at",
        table_name="incident_sla_uploads",
    )
    op.drop_index("ix_incident_sla_uploads_project_id", table_name="incident_sla_uploads")
    op.drop_table("incident_sla_uploads")

    op.drop_index("ix_incident_sla_rows_project_fingerprint", table_name="incident_sla_rows")
    op.drop_column("incident_sla_rows", "row_fingerprint")
