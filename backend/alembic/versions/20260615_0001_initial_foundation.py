"""initial AMS ticket intelligence schema

Revision ID: 20260615_0001
Revises:
Create Date: 2026-06-15 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260615_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "clients",
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_index("ix_clients_code", "clients", ["code"])

    op.create_table(
        "projects",
        sa.Column("client_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("default_incident_source_path", sa.String(length=1024), nullable=True),
        sa.Column("default_service_catalog_source_path", sa.String(length=1024), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("client_id", "code", name="uq_projects_client_code"),
    )
    op.create_index("ix_projects_client_id", "projects", ["client_id"])

    op.create_table(
        "source_column_mappings",
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ticket_type", sa.String(length=40), nullable=False),
        sa.Column("source_column_name", sa.String(length=255), nullable=False),
        sa.Column("normalized_field_name", sa.String(length=255), nullable=True),
        sa.Column("data_type", sa.String(length=80), nullable=True),
        sa.Column("is_required", sa.Boolean(), nullable=False),
        sa.Column("transform_rule", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id",
            "ticket_type",
            "source_column_name",
            name="uq_source_column_mappings_source_column",
        ),
    )
    op.create_index(
        "ix_source_column_mappings_project_id",
        "source_column_mappings",
        ["project_id"],
    )
    op.create_index(
        "ix_source_column_mappings_ticket_type",
        "source_column_mappings",
        ["ticket_type"],
    )

    op.create_table(
        "upload_batches",
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("month_key", sa.String(length=7), nullable=False),
        sa.Column("batch_name", sa.String(length=255), nullable=False),
        sa.Column("source_system", sa.String(length=120), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("uploaded_by", sa.String(length=255), nullable=True),
        sa.Column("file_count", sa.Integer(), nullable=False),
        sa.Column("total_size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "month_key", "batch_name", name="uq_upload_batches_name"),
    )
    op.create_index("ix_upload_batches_month_key", "upload_batches", ["month_key"])
    op.create_index("ix_upload_batches_project_id", "upload_batches", ["project_id"])
    op.create_index("ix_upload_batches_status", "upload_batches", ["status"])

    op.create_table(
        "uploaded_files",
        sa.Column("upload_batch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ticket_type", sa.String(length=40), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("storage_path", sa.String(length=1024), nullable=False),
        sa.Column("source_path", sa.String(length=1024), nullable=True),
        sa.Column("content_type", sa.String(length=255), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("checksum_sha256", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["upload_batch_id"], ["upload_batches.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_uploaded_files_checksum_sha256", "uploaded_files", ["checksum_sha256"])
    op.create_index("ix_uploaded_files_project_id", "uploaded_files", ["project_id"])
    op.create_index("ix_uploaded_files_status", "uploaded_files", ["status"])
    op.create_index("ix_uploaded_files_ticket_type", "uploaded_files", ["ticket_type"])
    op.create_index("ix_uploaded_files_upload_batch_id", "uploaded_files", ["upload_batch_id"])

    op.create_table(
        "dashboard_aggregates",
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("upload_batch_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("month_key", sa.String(length=7), nullable=False),
        sa.Column("ticket_type", sa.String(length=40), nullable=False),
        sa.Column("metric_name", sa.String(length=120), nullable=False),
        sa.Column("dimension_name", sa.String(length=120), nullable=True),
        sa.Column("dimension_value", sa.String(length=255), nullable=True),
        sa.Column("value_numeric", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("value_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("calculated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["upload_batch_id"], ["upload_batches.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id",
            "upload_batch_id",
            "month_key",
            "ticket_type",
            "metric_name",
            "dimension_name",
            "dimension_value",
            name="uq_dashboard_aggregates_metric_dimension",
        ),
    )
    op.create_index("ix_dashboard_aggregates_dimension_name", "dashboard_aggregates", ["dimension_name"])
    op.create_index("ix_dashboard_aggregates_dimension_value", "dashboard_aggregates", ["dimension_value"])
    op.create_index("ix_dashboard_aggregates_metric_name", "dashboard_aggregates", ["metric_name"])
    op.create_index("ix_dashboard_aggregates_month_key", "dashboard_aggregates", ["month_key"])
    op.create_index("ix_dashboard_aggregates_project_id", "dashboard_aggregates", ["project_id"])
    op.create_index("ix_dashboard_aggregates_ticket_type", "dashboard_aggregates", ["ticket_type"])
    op.create_index("ix_dashboard_aggregates_upload_batch_id", "dashboard_aggregates", ["upload_batch_id"])

    op.create_table(
        "export_jobs",
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("upload_batch_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("export_type", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("requested_by", sa.String(length=255), nullable=True),
        sa.Column("file_name", sa.String(length=255), nullable=True),
        sa.Column("storage_path", sa.String(length=1024), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["upload_batch_id"], ["upload_batches.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_export_jobs_project_id", "export_jobs", ["project_id"])
    op.create_index("ix_export_jobs_status", "export_jobs", ["status"])
    op.create_index("ix_export_jobs_upload_batch_id", "export_jobs", ["upload_batch_id"])

    op.create_table(
        "ingestion_jobs",
        sa.Column("upload_batch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("uploaded_file_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("job_type", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("rows_total", sa.BigInteger(), nullable=False),
        sa.Column("rows_processed", sa.BigInteger(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["upload_batch_id"], ["upload_batches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["uploaded_file_id"], ["uploaded_files.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ingestion_jobs_status", "ingestion_jobs", ["status"])
    op.create_index("ix_ingestion_jobs_upload_batch_id", "ingestion_jobs", ["upload_batch_id"])
    op.create_index("ix_ingestion_jobs_uploaded_file_id", "ingestion_jobs", ["uploaded_file_id"])

    op.create_table(
        "ticket_raw_rows",
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("upload_batch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("uploaded_file_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ticket_type", sa.String(length=40), nullable=False),
        sa.Column("row_number", sa.BigInteger(), nullable=False),
        sa.Column("raw_ticket_number", sa.String(length=255), nullable=True),
        sa.Column("raw_data", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("row_hash", sa.String(length=64), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["upload_batch_id"], ["upload_batches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["uploaded_file_id"], ["uploaded_files.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("uploaded_file_id", "row_number", name="uq_ticket_raw_rows_file_row"),
    )
    op.create_index("ix_ticket_raw_rows_project_id", "ticket_raw_rows", ["project_id"])
    op.create_index("ix_ticket_raw_rows_raw_ticket_number", "ticket_raw_rows", ["raw_ticket_number"])
    op.create_index("ix_ticket_raw_rows_row_hash", "ticket_raw_rows", ["row_hash"])
    op.create_index("ix_ticket_raw_rows_ticket_type", "ticket_raw_rows", ["ticket_type"])
    op.create_index("ix_ticket_raw_rows_upload_batch_id", "ticket_raw_rows", ["upload_batch_id"])
    op.create_index("ix_ticket_raw_rows_uploaded_file_id", "ticket_raw_rows", ["uploaded_file_id"])

    op.create_table(
        "tickets",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("upload_batch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("uploaded_file_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("raw_row_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("ticket_number", sa.String(length=255), nullable=False),
        sa.Column("ticket_type", sa.String(length=40), nullable=False),
        sa.Column("month_key", sa.String(length=7), nullable=False),
        sa.Column("source_system", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("short_description", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("state", sa.String(length=120), nullable=True),
        sa.Column("priority", sa.String(length=80), nullable=True),
        sa.Column("urgency", sa.String(length=80), nullable=True),
        sa.Column("impact", sa.String(length=80), nullable=True),
        sa.Column("application", sa.String(length=255), nullable=True),
        sa.Column("business_service", sa.String(length=255), nullable=True),
        sa.Column("assignment_group", sa.String(length=255), nullable=True),
        sa.Column("assigned_to", sa.String(length=255), nullable=True),
        sa.Column("requester", sa.String(length=255), nullable=True),
        sa.Column("opened_by", sa.String(length=255), nullable=True),
        sa.Column("created_by", sa.String(length=255), nullable=True),
        sa.Column("category", sa.String(length=255), nullable=True),
        sa.Column("subcategory", sa.String(length=255), nullable=True),
        sa.Column("catalog_item", sa.String(length=255), nullable=True),
        sa.Column("service_offering", sa.String(length=255), nullable=True),
        sa.Column("sla_breached", sa.Boolean(), nullable=True),
        sa.Column("sla_due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sla_elapsed_minutes", sa.BigInteger(), nullable=True),
        sa.Column("reopen_count", sa.Integer(), nullable=False),
        sa.Column("is_system_created", sa.Boolean(), nullable=True),
        sa.Column("is_technical", sa.Boolean(), nullable=True),
        sa.Column("classification_level_1", sa.String(length=255), nullable=True),
        sa.Column("classification_level_2", sa.String(length=255), nullable=True),
        sa.Column("classification_level_3", sa.String(length=255), nullable=True),
        sa.Column("classification_level_4", sa.String(length=255), nullable=True),
        sa.Column("improvement_area", sa.String(length=255), nullable=True),
        sa.Column("estimated_effort_hours", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("normalized_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("ingested_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("record_updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["raw_row_id"], ["ticket_raw_rows.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["upload_batch_id"], ["upload_batches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["uploaded_file_id"], ["uploaded_files.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "ticket_number", name="uq_tickets_project_ticket_number"),
        sa.UniqueConstraint("raw_row_id"),
    )
    op.create_index("ix_tickets_application", "tickets", ["application"])
    op.create_index("ix_tickets_assignment_group", "tickets", ["assignment_group"])
    op.create_index("ix_tickets_created_at", "tickets", ["created_at"])
    op.create_index("ix_tickets_month_key", "tickets", ["month_key"])
    op.create_index("ix_tickets_priority", "tickets", ["priority"])
    op.create_index("ix_tickets_project_id", "tickets", ["project_id"])
    op.create_index("ix_tickets_sla_breached", "tickets", ["sla_breached"])
    op.create_index("ix_tickets_state", "tickets", ["state"])
    op.create_index("ix_tickets_ticket_number", "tickets", ["ticket_number"])
    op.create_index("ix_tickets_ticket_type", "tickets", ["ticket_type"])
    op.create_index("ix_tickets_upload_batch_id", "tickets", ["upload_batch_id"])
    op.create_index("ix_tickets_uploaded_file_id", "tickets", ["uploaded_file_id"])


def downgrade() -> None:
    op.drop_index("ix_tickets_uploaded_file_id", table_name="tickets")
    op.drop_index("ix_tickets_upload_batch_id", table_name="tickets")
    op.drop_index("ix_tickets_ticket_type", table_name="tickets")
    op.drop_index("ix_tickets_ticket_number", table_name="tickets")
    op.drop_index("ix_tickets_state", table_name="tickets")
    op.drop_index("ix_tickets_sla_breached", table_name="tickets")
    op.drop_index("ix_tickets_project_id", table_name="tickets")
    op.drop_index("ix_tickets_priority", table_name="tickets")
    op.drop_index("ix_tickets_month_key", table_name="tickets")
    op.drop_index("ix_tickets_created_at", table_name="tickets")
    op.drop_index("ix_tickets_assignment_group", table_name="tickets")
    op.drop_index("ix_tickets_application", table_name="tickets")
    op.drop_table("tickets")

    op.drop_index("ix_ticket_raw_rows_uploaded_file_id", table_name="ticket_raw_rows")
    op.drop_index("ix_ticket_raw_rows_upload_batch_id", table_name="ticket_raw_rows")
    op.drop_index("ix_ticket_raw_rows_ticket_type", table_name="ticket_raw_rows")
    op.drop_index("ix_ticket_raw_rows_row_hash", table_name="ticket_raw_rows")
    op.drop_index("ix_ticket_raw_rows_raw_ticket_number", table_name="ticket_raw_rows")
    op.drop_index("ix_ticket_raw_rows_project_id", table_name="ticket_raw_rows")
    op.drop_table("ticket_raw_rows")

    op.drop_index("ix_ingestion_jobs_uploaded_file_id", table_name="ingestion_jobs")
    op.drop_index("ix_ingestion_jobs_upload_batch_id", table_name="ingestion_jobs")
    op.drop_index("ix_ingestion_jobs_status", table_name="ingestion_jobs")
    op.drop_table("ingestion_jobs")

    op.drop_index("ix_export_jobs_upload_batch_id", table_name="export_jobs")
    op.drop_index("ix_export_jobs_status", table_name="export_jobs")
    op.drop_index("ix_export_jobs_project_id", table_name="export_jobs")
    op.drop_table("export_jobs")

    op.drop_index("ix_dashboard_aggregates_upload_batch_id", table_name="dashboard_aggregates")
    op.drop_index("ix_dashboard_aggregates_ticket_type", table_name="dashboard_aggregates")
    op.drop_index("ix_dashboard_aggregates_project_id", table_name="dashboard_aggregates")
    op.drop_index("ix_dashboard_aggregates_month_key", table_name="dashboard_aggregates")
    op.drop_index("ix_dashboard_aggregates_metric_name", table_name="dashboard_aggregates")
    op.drop_index("ix_dashboard_aggregates_dimension_value", table_name="dashboard_aggregates")
    op.drop_index("ix_dashboard_aggregates_dimension_name", table_name="dashboard_aggregates")
    op.drop_table("dashboard_aggregates")

    op.drop_index("ix_uploaded_files_upload_batch_id", table_name="uploaded_files")
    op.drop_index("ix_uploaded_files_ticket_type", table_name="uploaded_files")
    op.drop_index("ix_uploaded_files_status", table_name="uploaded_files")
    op.drop_index("ix_uploaded_files_project_id", table_name="uploaded_files")
    op.drop_index("ix_uploaded_files_checksum_sha256", table_name="uploaded_files")
    op.drop_table("uploaded_files")

    op.drop_index("ix_upload_batches_status", table_name="upload_batches")
    op.drop_index("ix_upload_batches_project_id", table_name="upload_batches")
    op.drop_index("ix_upload_batches_month_key", table_name="upload_batches")
    op.drop_table("upload_batches")

    op.drop_index("ix_source_column_mappings_ticket_type", table_name="source_column_mappings")
    op.drop_index("ix_source_column_mappings_project_id", table_name="source_column_mappings")
    op.drop_table("source_column_mappings")

    op.drop_index("ix_projects_client_id", table_name="projects")
    op.drop_table("projects")

    op.drop_index("ix_clients_code", table_name="clients")
    op.drop_table("clients")
