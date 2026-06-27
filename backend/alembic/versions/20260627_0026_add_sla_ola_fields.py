"""add end-to-end SLA and vendor OLA fields

Revision ID: 20260627_0026
Revises: 20260626_0025
Create Date: 2026-06-27 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260627_0026"
down_revision: str | None = "20260626_0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


AGREEMENT_COLUMNS = (
    ("ola_response_sla_breached", sa.Boolean()),
    ("ola_resolution_sla_breached", sa.Boolean()),
    ("ola_response_sla_business_elapsed_seconds", sa.BigInteger()),
    ("ola_resolution_sla_business_elapsed_seconds", sa.BigInteger()),
    ("ola_response_sla_name", sa.Text()),
    ("ola_resolution_sla_name", sa.Text()),
    ("ola_response_sla_definition_name_used", sa.Text()),
    ("ola_resolution_sla_definition_name_used", sa.Text()),
    ("ola_response_sla_selection_source", sa.String(length=40)),
    ("ola_resolution_sla_selection_source", sa.String(length=40)),
    ("ola_response_sla_vendor_used", sa.Text()),
    ("ola_resolution_sla_vendor_used", sa.Text()),
    ("ola_response_sla_updated_at", sa.DateTime(timezone=True)),
    ("ola_resolution_sla_updated_at", sa.DateTime(timezone=True)),
    ("ola_enriched_at", sa.DateTime(timezone=True)),
    ("sla_response_sla_breached", sa.Boolean()),
    ("sla_resolution_sla_breached", sa.Boolean()),
    ("sla_response_sla_business_elapsed_seconds", sa.BigInteger()),
    ("sla_resolution_sla_business_elapsed_seconds", sa.BigInteger()),
    ("sla_response_sla_name", sa.Text()),
    ("sla_resolution_sla_name", sa.Text()),
    ("sla_response_sla_definition_name_used", sa.Text()),
    ("sla_resolution_sla_definition_name_used", sa.Text()),
    ("sla_response_sla_selection_source", sa.String(length=40)),
    ("sla_resolution_sla_selection_source", sa.String(length=40)),
    ("sla_response_sla_updated_at", sa.DateTime(timezone=True)),
    ("sla_resolution_sla_updated_at", sa.DateTime(timezone=True)),
    ("end_to_end_sla_enriched_at", sa.DateTime(timezone=True)),
)

TICKET_TABLES = ("tickets", "assessment_out_of_scope_tickets")
LEGACY_TO_OLA_COLUMNS = {
    "ola_response_sla_breached": "response_sla_breached",
    "ola_resolution_sla_breached": "resolution_sla_breached",
    "ola_response_sla_business_elapsed_seconds": "response_sla_business_elapsed_seconds",
    "ola_resolution_sla_business_elapsed_seconds": "resolution_sla_business_elapsed_seconds",
    "ola_response_sla_name": "response_sla_name",
    "ola_resolution_sla_name": "resolution_sla_name",
    "ola_response_sla_definition_name_used": "response_sla_definition_name_used",
    "ola_resolution_sla_definition_name_used": "resolution_sla_definition_name_used",
    "ola_response_sla_selection_source": "response_sla_selection_source",
    "ola_resolution_sla_selection_source": "resolution_sla_selection_source",
    "ola_response_sla_vendor_used": "response_sla_vendor_used",
    "ola_resolution_sla_vendor_used": "resolution_sla_vendor_used",
    "ola_response_sla_updated_at": "response_sla_updated_at",
    "ola_resolution_sla_updated_at": "resolution_sla_updated_at",
    "ola_enriched_at": "sla_enriched_at",
}


def table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def index_exists(table_name: str, index_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return any(index["name"] == index_name for index in inspector.get_indexes(table_name))


def upgrade() -> None:
    for table_name in TICKET_TABLES:
        if not table_exists(table_name):
            continue
        for column_name, column_type in AGREEMENT_COLUMNS:
            if not column_exists(table_name, column_name):
                op.add_column(table_name, sa.Column(column_name, column_type, nullable=True))

        assignments = ",\n                ".join(
            f"{ola_column} = COALESCE({ola_column}, {legacy_column})"
            for ola_column, legacy_column in LEGACY_TO_OLA_COLUMNS.items()
            if column_exists(table_name, legacy_column)
        )
        if assignments:
            op.execute(sa.text(f"UPDATE {table_name} SET {assignments}"))

    if table_exists("incident_sla_rows"):
        if not column_exists("incident_sla_rows", "agreement_type"):
            op.add_column(
                "incident_sla_rows",
                sa.Column(
                    "agreement_type",
                    sa.String(length=10),
                    nullable=False,
                    server_default="ola",
                ),
            )
        op.execute(
            sa.text(
                "UPDATE incident_sla_rows SET agreement_type = 'ola' "
                "WHERE agreement_type IS NULL OR btrim(agreement_type) = ''"
            )
        )
        if not index_exists("incident_sla_rows", "ix_incident_sla_rows_project_agreement"):
            op.create_index(
                "ix_incident_sla_rows_project_agreement",
                "incident_sla_rows",
                ["project_id", "agreement_type"],
            )

    if table_exists("incident_sla_uploads"):
        if not column_exists("incident_sla_uploads", "agreement_type"):
            op.add_column(
                "incident_sla_uploads",
                sa.Column(
                    "agreement_type",
                    sa.String(length=10),
                    nullable=False,
                    server_default="ola",
                ),
            )
        op.execute(
            sa.text(
                "UPDATE incident_sla_uploads SET agreement_type = 'ola' "
                "WHERE agreement_type IS NULL OR btrim(agreement_type) = ''"
            )
        )
        if not index_exists("incident_sla_uploads", "ix_incident_sla_uploads_project_agreement"):
            op.create_index(
                "ix_incident_sla_uploads_project_agreement",
                "incident_sla_uploads",
                ["project_id", "agreement_type"],
            )


def downgrade() -> None:
    if table_exists("incident_sla_uploads"):
        if index_exists("incident_sla_uploads", "ix_incident_sla_uploads_project_agreement"):
            op.drop_index(
                "ix_incident_sla_uploads_project_agreement",
                table_name="incident_sla_uploads",
            )
        if column_exists("incident_sla_uploads", "agreement_type"):
            op.drop_column("incident_sla_uploads", "agreement_type")

    if table_exists("incident_sla_rows"):
        if index_exists("incident_sla_rows", "ix_incident_sla_rows_project_agreement"):
            op.drop_index(
                "ix_incident_sla_rows_project_agreement",
                table_name="incident_sla_rows",
            )
        if column_exists("incident_sla_rows", "agreement_type"):
            op.drop_column("incident_sla_rows", "agreement_type")

    for table_name in TICKET_TABLES:
        if not table_exists(table_name):
            continue
        for column_name, _column_type in reversed(AGREEMENT_COLUMNS):
            if column_exists(table_name, column_name):
                op.drop_column(table_name, column_name)
