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
        "dashboard_commentaries",
        "dashboard_filter_facts",
        "export_jobs",
        "application_dimensions",
        "application_inventory_items",
        "assessment_out_of_scope_tickets",
        "assessment_out_of_scope_problem_records",
        "assessment_out_of_scope_change_records",
        "incident_sla_rows",
        "genai_config",
        "genai_prompt_templates",
        "genai_usage_logs",
        "genai_safety_settings",
        "genai_ticket_classifications",
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
    out_of_scope_columns = Base.metadata.tables["assessment_out_of_scope_tickets"].columns.keys()
    application_dimension_columns = Base.metadata.tables["application_dimensions"].columns.keys()

    assert "business_duration_seconds" in ticket_columns
    assert "reassignment_count" in ticket_columns
    assert "catalog_item_name" in ticket_columns
    assert "catalog_knowledge_base" in ticket_columns
    assert "catalog_item_name" in out_of_scope_columns
    assert "catalog_knowledge_base" in out_of_scope_columns
    assert "application_dimension_id" in ticket_columns
    assert "technical_functional_type" in ticket_columns
    assert "technical_functional_confidence" in ticket_columns
    assert "technical_functional_reason" in ticket_columns
    assert "technical_functional_classified_at" in ticket_columns
    assert "application_name" in application_dimension_columns


def test_problem_management_columns_exist() -> None:
    problem_columns = Base.metadata.tables["assessment_problem_records"].columns.keys()
    out_problem_columns = Base.metadata.tables[
        "assessment_out_of_scope_problem_records"
    ].columns.keys()

    assert "related_incidents" in problem_columns
    assert "linked_incident_count" in problem_columns
    assert "related_incidents" in out_problem_columns
    assert "linked_incident_count" in out_problem_columns
    assert "out_of_scope_reason" in out_problem_columns


def test_problem_change_scope_split_tables_exist() -> None:
    out_problem_columns = Base.metadata.tables[
        "assessment_out_of_scope_problem_records"
    ].columns.keys()
    out_change_columns = Base.metadata.tables[
        "assessment_out_of_scope_change_records"
    ].columns.keys()

    for columns in (out_problem_columns, out_change_columns):
        assert "project_id" in columns
        assert "upload_batch_id" in columns
        assert "raw_row_id" in columns
        assert "number" in columns
        assert "assignment_group" in columns
        assert "application_inventory_match_status" in columns
        assert "functional_track" in columns
        assert "ams_owner" in columns
        assert "parent_business_application" in columns
        assert "supported_by_vendor" in columns
        assert "sap_non_sap" in columns
        assert "architecture_type" in columns
        assert "install_type" in columns
        assert "out_of_scope_reason" in columns
        assert "normalized_payload" in columns


def test_application_dimension_enrichment_columns_exist() -> None:
    ticket_columns = Base.metadata.tables["tickets"].columns.keys()
    dimension_columns = Base.metadata.tables["application_dimensions"].columns.keys()

    assert "application_alias" in dimension_columns
    assert "business_service_alias" in dimension_columns
    assert "cmdb_ci_alias" in dimension_columns
    assert "notes" in dimension_columns
    assert "cmdb_ci" in ticket_columns
    assert "customer_name" in ticket_columns
    assert "tower_name" in ticket_columns
    assert "cluster_name" in ticket_columns
    assert "application_group_name" in ticket_columns
    assert "application_name" in ticket_columns


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


def test_application_inventory_columns_exist() -> None:
    ticket_columns = Base.metadata.tables["tickets"].columns.keys()
    inventory_columns = Base.metadata.tables["application_inventory_items"].columns.keys()

    assert "application_number_apm" in inventory_columns
    assert "parent_application_name" in inventory_columns
    assert "assignment_group" in inventory_columns
    assert "assignment_group_owner" in inventory_columns
    assert "application_owner" in inventory_columns
    assert "business_service_ci_name" in inventory_columns
    assert "support_lead" in inventory_columns
    assert "functional_track" in inventory_columns
    assert "ams_owner" in inventory_columns
    assert "supported_by_vendor" in inventory_columns
    assert "service_type" in inventory_columns
    assert "service_entitlement" in inventory_columns
    assert "hosting_env" in inventory_columns
    assert "global_application" in inventory_columns
    assert "active_users" in inventory_columns
    assert "is_current" in inventory_columns
    assert "replaced_at" in inventory_columns
    assert "cmdb_payload" in inventory_columns
    assert "application_inventory_id" in ticket_columns
    assert "parent_application_number" in ticket_columns
    assert "parent_application_name" in ticket_columns
    assert "business_service_ci_name" in ticket_columns
    assert "application_owner" in ticket_columns
    assert "support_lead" in ticket_columns
    assert "functional_track" in ticket_columns
    assert "ams_owner" in ticket_columns
    assert "supported_by_vendor" in ticket_columns
    assert "service_type" in ticket_columns
    assert "service_entitlement" in ticket_columns
    assert "assignment_group_owner" in ticket_columns
    assert "architecture_type" in ticket_columns
    assert "install_type" in ticket_columns
    assert "hosting_env" in ticket_columns


def test_dashboard_commentary_columns_exist() -> None:
    commentary_columns = Base.metadata.tables["dashboard_commentaries"].columns.keys()

    assert "client_id" in commentary_columns
    assert "project_id" in commentary_columns
    assert "dashboard_area" in commentary_columns
    assert "tab_name" in commentary_columns
    assert "sub_tab_name" in commentary_columns
    assert "section_key" in commentary_columns
    assert "chart_key" in commentary_columns
    assert "scope_filter" in commentary_columns
    assert "ticket_type_filter" in commentary_columns
    assert "functional_track_ams_owner" in commentary_columns
    assert "commentary_html" in commentary_columns
    assert "commentary_text" in commentary_columns


def test_dashboard_filter_fact_columns_and_indexes_exist() -> None:
    fact_table = Base.metadata.tables["dashboard_filter_facts"]
    fact_columns = fact_table.columns.keys()
    fact_indexes = {index.name for index in fact_table.indexes}

    assert "customer_id" in fact_columns
    assert "project_id" in fact_columns
    assert "record_source" in fact_columns
    assert "record_type" in fact_columns
    assert "scope" in fact_columns
    assert "record_id" in fact_columns
    assert "record_number" in fact_columns
    assert "created_at_source" in fact_columns
    assert "completed_at_source" in fact_columns
    assert "created_month" in fact_columns
    assert "completed_month" in fact_columns
    assert "functional_track_ams_owner" in fact_columns
    assert "assignment_group_support_owner" in fact_columns
    assert "parent_business_application" in fact_columns
    assert "application_owner" in fact_columns
    assert "supported_by_vendor" in fact_columns
    assert "sap_non_sap" in fact_columns
    assert "architecture_type" in fact_columns
    assert "install_type" in fact_columns
    assert "hosting_env" in fact_columns
    assert "service_entitlement" in fact_columns
    assert "service_type" in fact_columns

    assert "ix_dashboard_filter_facts_project_scope_type" in fact_indexes
    assert "ix_dashboard_filter_facts_project_functional" in fact_indexes
    assert "ix_dashboard_filter_facts_project_assignment" in fact_indexes
    assert "ix_dashboard_filter_facts_project_parent_app" in fact_indexes
    assert "ix_dashboard_filter_facts_project_sap" in fact_indexes
    assert "ix_dashboard_filter_facts_project_service_entitlement" in fact_indexes
    assert "ix_dashboard_filter_facts_project_service_type" in fact_indexes


def test_scope_split_vendor_sla_columns_exist() -> None:
    ticket_columns = Base.metadata.tables["tickets"].columns.keys()
    out_of_scope_columns = Base.metadata.tables["assessment_out_of_scope_tickets"].columns.keys()

    assert "vendor" in ticket_columns
    assert "derived_vendor" in ticket_columns
    assert "response_sla_definition_name_used" in ticket_columns
    assert "resolution_sla_definition_name_used" in ticket_columns
    assert "response_sla_selection_source" in ticket_columns
    assert "resolution_sla_selection_source" in ticket_columns
    assert "response_sla_vendor_used" in ticket_columns
    assert "resolution_sla_vendor_used" in ticket_columns
    assert "source_raw_row_id" in out_of_scope_columns
    assert "out_of_scope_reason" in out_of_scope_columns
    assert "vendor" in out_of_scope_columns
    assert "derived_vendor" in out_of_scope_columns
    assert "cmdb_ci" in out_of_scope_columns
    assert "functional_track" in out_of_scope_columns
    assert "ams_owner" in out_of_scope_columns
    assert "business_service_ci_name" in out_of_scope_columns
    assert "service_type" in out_of_scope_columns
    assert "service_entitlement" in out_of_scope_columns
    assert "architecture_type" in out_of_scope_columns
    assert "install_type" in out_of_scope_columns
    assert "hosting_env" in out_of_scope_columns
    assert "response_sla_selection_source" in out_of_scope_columns
    assert "resolution_sla_selection_source" in out_of_scope_columns


def test_incident_batch_classification_columns_exist() -> None:
    ticket_columns = Base.metadata.tables["tickets"].columns.keys()
    out_of_scope_columns = Base.metadata.tables["assessment_out_of_scope_tickets"].columns.keys()

    assert "is_batch_related" in ticket_columns
    assert "is_batch_related" in out_of_scope_columns
