"""split problem and change records by application scope

Revision ID: 20260701_0036
Revises: 20260701_0035
Create Date: 2026-07-01 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260701_0036"
down_revision: str | None = "20260701_0035"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


PROBLEM_COLUMNS = (
    "id",
    "project_id",
    "upload_batch_id",
    "uploaded_file_id",
    "raw_row_id",
    "application_inventory_id",
    "source_row_number",
    "row_fingerprint",
    "number",
    "state",
    "problem_state",
    "problem_statement",
    "short_description_or_statement",
    "description",
    "business_application",
    "business_service",
    "configuration_item",
    "category",
    "subcategory",
    "assignment_group",
    "assigned_to",
    "urgency",
    "priority",
    "active",
    "created_at_source",
    "opened_at",
    "actual_start_at",
    "actual_end_at",
    "closed_at",
    "resolved_at",
    "business_duration_seconds",
    "duration_seconds",
    "made_sla",
    "major_incident",
    "major_problem",
    "known_error",
    "related_incidents",
    "linked_incident_count",
    "change_request",
    "caused_by_change",
    "duplicate_of",
    "parent",
    "reassignment_count",
    "reopen_count",
    "resolution_code",
    "close_notes",
    "cause_notes",
    "fix_notes",
    "workaround",
    "source",
    "contact_type",
    "company",
    "vendor_or_supplier_if_available",
    "functional_track",
    "ams_owner",
    "parent_business_application",
    "supported_by_vendor",
    "sap_non_sap",
    "architecture_type",
    "install_type",
    "application_inventory_match_status",
    "normalized_payload",
    "created_at",
    "updated_at",
)

CHANGE_COLUMNS = (
    "id",
    "project_id",
    "upload_batch_id",
    "uploaded_file_id",
    "raw_row_id",
    "application_inventory_id",
    "source_row_number",
    "row_fingerprint",
    "number",
    "short_description",
    "type",
    "state",
    "phase",
    "phase_state",
    "business_application",
    "business_service",
    "application_name",
    "affected_ci_service",
    "category",
    "assignment_group",
    "assigned_to",
    "priority",
    "urgency",
    "impact",
    "risk",
    "risk_value",
    "vendor",
    "created_at_source",
    "opened_at",
    "planned_start_at",
    "planned_end_at",
    "actual_start_at",
    "actual_end_at",
    "closed_at",
    "business_duration_seconds",
    "duration_seconds",
    "made_sla",
    "unauthorized",
    "outside_maintenance_schedule",
    "cab_required",
    "cab_approval",
    "cab_date",
    "change_reason",
    "close_code",
    "close_code_sub_category",
    "incident",
    "problem",
    "caused_by_change",
    "parent",
    "reassignment_count",
    "service_outage_required",
    "implementation_plan",
    "backout_plan",
    "test_plan",
    "communication_plan",
    "functional_track",
    "ams_owner",
    "parent_business_application",
    "supported_by_vendor",
    "sap_non_sap",
    "architecture_type",
    "install_type",
    "application_inventory_match_status",
    "normalized_payload",
    "created_at",
    "updated_at",
)


def table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def quoted_columns(columns: tuple[str, ...]) -> str:
    return ", ".join(f'"{column}"' for column in columns)


def create_out_of_scope_table(source_table: str, target_table: str) -> None:
    if not table_exists(source_table) or table_exists(target_table):
        return
    op.execute(
        f"""
        CREATE TABLE {target_table}
        (LIKE {source_table} INCLUDING DEFAULTS INCLUDING CONSTRAINTS INCLUDING INDEXES)
        """,
    )
    op.add_column(
        target_table,
        sa.Column(
            "out_of_scope_reason",
            sa.String(length=120),
            nullable=False,
            server_default="assignment_group_not_in_application_inventory",
        ),
    )
    op.alter_column(target_table, "out_of_scope_reason", server_default=None)


def add_foreign_key_if_missing(
    table_name: str,
    constraint_name: str,
    column_name: str,
    referred_table: str,
    referred_column: str = "id",
    ondelete: str = "CASCADE",
) -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = '{constraint_name}'
            ) THEN
                ALTER TABLE {table_name}
                ADD CONSTRAINT {constraint_name}
                FOREIGN KEY ({column_name})
                REFERENCES {referred_table} ({referred_column})
                ON DELETE {ondelete};
            END IF;
        END $$;
        """,
    )


def add_common_foreign_keys(table_name: str, prefix: str) -> None:
    add_foreign_key_if_missing(table_name, f"fk_{prefix}_project", "project_id", "projects")
    add_foreign_key_if_missing(
        table_name,
        f"fk_{prefix}_upload_batch",
        "upload_batch_id",
        "upload_batches",
    )
    add_foreign_key_if_missing(
        table_name,
        f"fk_{prefix}_uploaded_file",
        "uploaded_file_id",
        "uploaded_files",
        ondelete="SET NULL",
    )
    add_foreign_key_if_missing(
        table_name,
        f"fk_{prefix}_raw_row",
        "raw_row_id",
        "ticket_raw_rows",
        ondelete="SET NULL",
    )
    add_foreign_key_if_missing(
        table_name,
        f"fk_{prefix}_application_inventory",
        "application_inventory_id",
        "application_inventory_items",
        ondelete="SET NULL",
    )


def scope_reason_sql(table_alias: str) -> str:
    return f"""
        CASE
            WHEN {table_alias}.assignment_group IS NULL
              OR btrim({table_alias}.assignment_group) = ''
                THEN 'blank_assignment_group'
            ELSE 'assignment_group_not_in_application_inventory'
        END
    """


def out_of_scope_condition(table_alias: str) -> str:
    return f"""
        (
            {table_alias}.assignment_group IS NULL
            OR btrim({table_alias}.assignment_group) = ''
            OR lower(btrim({table_alias}.assignment_group)) NOT IN (
                SELECT lower(btrim(ai.assignment_group))
                FROM application_inventory_items ai
                WHERE ai.project_id = {table_alias}.project_id
                  AND ai.active IS NOT FALSE
                  AND ai.assignment_group IS NOT NULL
                  AND btrim(ai.assignment_group) <> ''
            )
        )
    """


def split_existing_rows(
    source_table: str,
    target_table: str,
    columns: tuple[str, ...],
) -> None:
    if not table_exists(source_table) or not table_exists(target_table):
        return
    column_list = quoted_columns(columns)
    op.execute(
        f"""
        INSERT INTO {target_table} ({column_list}, out_of_scope_reason)
        SELECT {column_list}, {scope_reason_sql(source_table)}
        FROM {source_table}
        WHERE {out_of_scope_condition(source_table)}
        ON CONFLICT (project_id, row_fingerprint) DO NOTHING
        """,
    )
    op.execute(
        f"""
        DELETE FROM {source_table}
        WHERE id IN (
            SELECT id
            FROM {target_table}
        )
        """,
    )


def restore_split_rows(
    source_table: str,
    target_table: str,
    columns: tuple[str, ...],
) -> None:
    if not table_exists(source_table) or not table_exists(target_table):
        return
    column_list = quoted_columns(columns)
    op.execute(
        f"""
        INSERT INTO {source_table} ({column_list})
        SELECT {column_list}
        FROM {target_table}
        ON CONFLICT (project_id, row_fingerprint) DO NOTHING
        """,
    )


def upgrade() -> None:
    create_out_of_scope_table(
        "assessment_problem_records",
        "assessment_out_of_scope_problem_records",
    )
    create_out_of_scope_table(
        "assessment_change_records",
        "assessment_out_of_scope_change_records",
    )

    if table_exists("assessment_out_of_scope_problem_records"):
        add_common_foreign_keys(
            "assessment_out_of_scope_problem_records",
            "oos_problem_records",
        )
        if column_exists("assessment_out_of_scope_problem_records", "linked_incident_count"):
            op.create_index(
                "ix_oos_problem_records_project_linked_incident_count",
                "assessment_out_of_scope_problem_records",
                ["project_id", "linked_incident_count"],
                unique=False,
                if_not_exists=True,
            )
    if table_exists("assessment_out_of_scope_change_records"):
        add_common_foreign_keys(
            "assessment_out_of_scope_change_records",
            "oos_change_records",
        )

    split_existing_rows(
        "assessment_problem_records",
        "assessment_out_of_scope_problem_records",
        PROBLEM_COLUMNS,
    )
    split_existing_rows(
        "assessment_change_records",
        "assessment_out_of_scope_change_records",
        CHANGE_COLUMNS,
    )


def downgrade() -> None:
    restore_split_rows(
        "assessment_problem_records",
        "assessment_out_of_scope_problem_records",
        PROBLEM_COLUMNS,
    )
    restore_split_rows(
        "assessment_change_records",
        "assessment_out_of_scope_change_records",
        CHANGE_COLUMNS,
    )
    if table_exists("assessment_out_of_scope_change_records"):
        op.drop_table("assessment_out_of_scope_change_records")
    if table_exists("assessment_out_of_scope_problem_records"):
        op.drop_table("assessment_out_of_scope_problem_records")
