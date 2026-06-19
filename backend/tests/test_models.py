import app.models  # noqa: F401
from app.db.base import Base


def test_expected_ams_tables_are_registered() -> None:
    expected_tables = {
        "clients",
        "projects",
        "upload_batches",
        "uploaded_files",
        "ingestion_jobs",
        "source_column_mappings",
        "ticket_raw_rows",
        "tickets",
        "dashboard_aggregates",
        "export_jobs",
        "application_dimensions",
        "incident_sla_rows",
    }

    assert expected_tables.issubset(Base.metadata.tables.keys())


def test_ticket_dashboard_indexes_exist() -> None:
    ticket_indexes = {
        tuple(column.name for column in index.columns)
        for index in Base.metadata.tables["tickets"].indexes
    }

    assert ("ticket_type",) in ticket_indexes
    assert ("created_at",) in ticket_indexes
    assert ("month_key",) in ticket_indexes
    assert ("application",) in ticket_indexes
    assert ("assignment_group",) in ticket_indexes
    assert ("priority",) in ticket_indexes
    assert ("sla_breached",) in ticket_indexes
    assert ("upload_batch_id",) in ticket_indexes


def test_raw_rows_keep_json_separate_from_dashboard_aggregates() -> None:
    raw_row_columns = Base.metadata.tables["ticket_raw_rows"].columns.keys()
    aggregate_columns = Base.metadata.tables["dashboard_aggregates"].columns.keys()

    assert "raw_data" in raw_row_columns
    assert "source_filename" in raw_row_columns
    assert "raw_data" not in aggregate_columns
    assert "value_numeric" in aggregate_columns


def test_uploaded_files_include_saved_filename_metadata() -> None:
    uploaded_file_columns = Base.metadata.tables["uploaded_files"].columns.keys()

    assert "saved_filename" in uploaded_file_columns


def test_upload_batches_include_period_metadata() -> None:
    upload_batch_columns = Base.metadata.tables["upload_batches"].columns.keys()

    assert "period_type" in upload_batch_columns
    assert "snapshot_date" in upload_batch_columns
    assert "normalized_at" in upload_batch_columns
    assert "archived_at" in upload_batch_columns
    assert "deleted_at" in upload_batch_columns


def test_dashboard_foundation_columns_exist() -> None:
    ticket_columns = Base.metadata.tables["tickets"].columns.keys()
    application_dimension_columns = Base.metadata.tables["application_dimensions"].columns.keys()

    assert "business_duration_seconds" in ticket_columns
    assert "reassignment_count" in ticket_columns
    assert "application_dimension_id" in ticket_columns
    assert "technical_functional_type" in ticket_columns
    assert "technical_functional_confidence" in ticket_columns
    assert "technical_functional_reason" in ticket_columns
    assert "technical_functional_classified_at" in ticket_columns
    assert "application_name" in application_dimension_columns


def test_incident_sla_columns_exist() -> None:
    ticket_columns = Base.metadata.tables["tickets"].columns.keys()
    sla_columns = Base.metadata.tables["incident_sla_rows"].columns.keys()

    assert "response_sla_breached" in ticket_columns
    assert "resolution_sla_breached" in ticket_columns
    assert "response_sla_business_elapsed_seconds" in ticket_columns
    assert "resolution_sla_business_elapsed_seconds" in ticket_columns
    assert "response_sla_name" in ticket_columns
    assert "resolution_sla_name" in ticket_columns
    assert "response_sla_updated_at" in ticket_columns
    assert "resolution_sla_updated_at" in ticket_columns
    assert "sla_enriched_at" in ticket_columns
    assert "inc_number" in sla_columns
    assert "taskslatable_sla_target" in sla_columns
    assert "raw_data" in sla_columns
