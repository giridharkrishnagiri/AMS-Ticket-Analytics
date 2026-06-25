from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select

from app.db.session import SessionLocal
from app.main import app
from app.models import (
    ApplicationInventoryItem,
    AssessmentOutOfScopeTicket,
    Client,
    IngestionJob,
    Project,
    Ticket,
    TicketRawRow,
    UploadBatch,
    UploadedFile,
)
from app.services.batch_classification import derive_is_batch_related
from app.services.ingestion import build_validation_summary, recalculate_upload_batch_status
from app.services.mapping import (
    apply_mapping_to_batch,
    apply_mapping_with_scope,
    get_mapping_template,
    get_suggested_mapping_for_batch,
    get_suggested_mapping_result,
    infer_source_columns,
    mapping_rows_to_field_mapping,
    normalize_priority,
    parse_business_duration_seconds,
    parse_datetime_value,
    parse_sla_breached_value,
    save_mapping_template,
)

INCIDENT_SOURCE_COLUMNS = [
    "number",
    "caller_id",
    "opened_by",
    "made_sla",
    "state",
    "short_description",
    "description",
    "category",
    "subcategory",
    "business_service",
    "cmdb_ci",
    "impact",
    "urgency",
    "priority",
    "assignment_group",
    "assigned_to",
    "u_fcr",
    "comments",
    "u_affected_locations",
    "business_stc",
    "child_incidents",
    "closed_at",
    "sys_created_on",
    "u_follow_up_number",
    "u_knowledge_record",
    "hold_reason",
    "parent_incident",
    "reassignment_count",
    "reopen_count",
    "close_code",
    "close_notes",
    "resolved_at",
    "scr_vendor",
    "work_notes",
]

SC_TASK_SOURCE_COLUMNS = [
    "number",
    "priority",
    "state",
    "assignment_group",
    "short_description",
    "description",
    "comments",
    "assigned_to",
    "request.requested_for",
    "approval",
    "cmdb_ci_business_app",
    "business_duration",
    "business_service",
    "sc_catalog",
    "close_notes",
    "closed_at",
    "cmdb_ci",
    "contact_type",
    "sys_created_on",
    "sys_created_by",
    "work_notes",
    "made_sla",
    "reassignment_count",
    "u_rpt_difference2",
    "u_vendor",
]

IN_SCOPE_ASSIGNMENT_GROUP = "AMS Support"
IN_SCOPE_BUSINESS_SERVICE = "Mapping Service"


def create_raw_batch_fixture(
    rows: list[dict[str, object]],
    ticket_type: str = "INCIDENT",
):
    db = SessionLocal()
    unique_suffix = uuid4().hex[:12]
    client = Client(
        name=f"Mapping Test Client {unique_suffix}",
        code=f"MTC-{unique_suffix}",
    )
    db.add(client)
    db.flush()

    project = Project(
        client_id=client.id,
        name=f"Mapping Test Project {unique_suffix}",
        code=f"MTP-{unique_suffix}",
    )
    db.add(project)
    db.flush()

    upload_batch = UploadBatch(
        project_id=project.id,
        month_key="2026-06",
        batch_name=f"Mapping Test Batch {unique_suffix}",
        status="PENDING",
        file_count=1,
        total_size_bytes=128,
    )
    db.add(upload_batch)
    db.flush()

    uploaded_file = UploadedFile(
        upload_batch_id=upload_batch.id,
        project_id=project.id,
        ticket_type=ticket_type,
        original_filename=f"{ticket_type.lower()}-{unique_suffix}.csv",
        saved_filename=f"{ticket_type.lower()}-{unique_suffix}.csv",
        storage_path=f"C:\\temp\\{ticket_type.lower()}-{unique_suffix}.csv",
        size_bytes=128,
        status="INGESTED",
    )
    db.add(uploaded_file)
    db.flush()

    raw_rows = []
    for index, raw_data in enumerate(rows, start=2):
        raw_ticket_number = (
            raw_data.get("number")
            or raw_data.get("task_number")
            or raw_data.get("sc_task")
            or raw_data.get("sys_id")
        )
        raw_row = TicketRawRow(
            project_id=project.id,
            upload_batch_id=upload_batch.id,
            uploaded_file_id=uploaded_file.id,
            ticket_type=ticket_type,
            row_number=index,
            source_filename=uploaded_file.original_filename,
            raw_ticket_number=str(raw_ticket_number) if raw_ticket_number else None,
            raw_data=raw_data,
            row_hash=uuid4().hex,
        )
        db.add(raw_row)
        raw_rows.append(raw_row)

    db.commit()
    return db, client.id, project.id, upload_batch.id, uploaded_file.id, raw_rows


def cleanup_client(db, client_id: UUID) -> None:
    db.rollback()
    db.execute(delete(Client).where(Client.id == client_id))
    db.commit()
    db.close()


def add_application_inventory_scope(
    db,
    project_id: UUID,
    *,
    assignment_group: str = IN_SCOPE_ASSIGNMENT_GROUP,
    business_service: str = IN_SCOPE_BUSINESS_SERVICE,
) -> None:
    db.add(
        ApplicationInventoryItem(
            project_id=project_id,
            application_number_apm="APM-MAPPING",
            parent_application_name="Mapping Parent App",
            assignment_group=assignment_group,
            assignment_group_owner="Mapping Owner",
            application_owner="Mapping Application Owner",
            business_service_ci_name=business_service,
            support_lead="Mapping Support Lead",
            functional_track="Mapping Track",
            ams_owner="Mapping AMS Owner",
            supported_by_vendor="HCLTech",
            cmdb_payload={
                "Architecture type": "Vendor Managed",
                "Install type": "Cloud",
            },
            active=True,
            source_filename="mapping-inventory.xlsx",
            source_row_number=1,
        )
    )
    db.flush()


def in_scope_raw(row: dict[str, object]) -> dict[str, object]:
    return {
        "assignment_group": IN_SCOPE_ASSIGNMENT_GROUP,
        "business_service": IN_SCOPE_BUSINESS_SERVICE,
        **row,
    }


def add_uploaded_file_with_raw_rows(
    db,
    project_id: UUID,
    upload_batch_id: UUID,
    rows: list[dict[str, object]],
    filename: str,
    ticket_type: str = "INCIDENT",
) -> UUID:
    uploaded_file = UploadedFile(
        upload_batch_id=upload_batch_id,
        project_id=project_id,
        ticket_type=ticket_type,
        original_filename=filename,
        saved_filename=filename,
        storage_path=f"C:\\temp\\{filename}",
        size_bytes=128,
        status="INGESTED",
    )
    db.add(uploaded_file)
    db.flush()

    for index, raw_data in enumerate(rows, start=2):
        db.add(
            TicketRawRow(
                project_id=project_id,
                upload_batch_id=upload_batch_id,
                uploaded_file_id=uploaded_file.id,
                ticket_type=ticket_type,
                row_number=index,
                source_filename=filename,
                raw_ticket_number=str(raw_data.get("number") or ""),
                raw_data=raw_data,
                row_hash=uuid4().hex,
            )
        )

    db.commit()
    return uploaded_file.id


def add_upload_batch_with_raw_rows(
    db,
    project_id: UUID,
    rows: list[dict[str, object]],
    ticket_type: str,
    batch_name: str,
    month_key: str = "2026-07",
) -> UUID:
    upload_batch = UploadBatch(
        project_id=project_id,
        month_key=month_key,
        batch_name=batch_name,
        status="COMPLETED",
        file_count=1,
        total_size_bytes=128,
    )
    db.add(upload_batch)
    db.flush()

    uploaded_file = UploadedFile(
        upload_batch_id=upload_batch.id,
        project_id=project_id,
        ticket_type=ticket_type,
        original_filename=f"{batch_name}.csv",
        saved_filename=f"{batch_name}.csv",
        storage_path=f"C:\\temp\\{batch_name}.csv",
        size_bytes=128,
        status="INGESTED",
    )
    db.add(uploaded_file)
    db.flush()

    for index, raw_data in enumerate(rows, start=2):
        db.add(
            TicketRawRow(
                project_id=project_id,
                upload_batch_id=upload_batch.id,
                uploaded_file_id=uploaded_file.id,
                ticket_type=ticket_type,
                row_number=index,
                source_filename=uploaded_file.original_filename,
                raw_ticket_number=str(raw_data.get("number") or ""),
                raw_data=raw_data,
                row_hash=uuid4().hex,
            )
        )

    db.commit()
    return upload_batch.id


def test_validation_summary_reports_raw_rows_and_duplicate_ticket_ids() -> None:
    rows = [
        {"number": "INC001", "sys_created_on": "2026-06-01 09:00:00"},
        {"number": "INC001", "sys_created_on": "2026-06-01 10:00:00"},
        {"number": "", "short_description": "Missing created date"},
    ]
    db, client_id, _, upload_batch_id, _, _ = create_raw_batch_fixture(rows)

    try:
        summary = build_validation_summary(db, upload_batch_id)

        assert summary.total_raw_rows == 3
        assert summary.missing_ticket_id_count == 1
        assert summary.missing_created_date_count == 1
        assert summary.duplicate_ticket_id_count == 1
        assert summary.duplicate_ticket_ids == {"INC001": 2}
        assert "sys_created_on" in summary.detected_source_columns
        assert summary.message is None
    finally:
        cleanup_client(db, client_id)


def test_validation_summary_endpoint_serializes_incident_rows_by_uploaded_file() -> None:
    rows = [
        {"number": "INC001", "sys_created_on": "2026-06-01 09:00:00"},
    ]
    db, client_id, project_id, upload_batch_id, _, _ = create_raw_batch_fixture(rows)

    try:
        add_uploaded_file_with_raw_rows(
            db,
            project_id,
            upload_batch_id,
            [{"number": "INC002", "sys_created_on": "2026-06-02 09:00:00"}],
            "incidents-2.csv",
        )

        with TestClient(app) as client:
            response = client.get(f"/api/uploads/batches/{upload_batch_id}/validation-summary")

        assert response.status_code == 200
        payload = response.json()
        assert payload["total_raw_rows"] == 2
        assert payload["message"] is None
        assert len(payload["rows_by_uploaded_file"]) == 2
        assert payload["rows_by_uploaded_file"][0]["uploaded_file_id"]
        assert payload["rows_by_uploaded_file"][0]["row_count"] == 1
    finally:
        cleanup_client(db, client_id)


def test_validation_summary_endpoint_serializes_sc_task_rows() -> None:
    rows = [
        {
            "number": "SCTASK001",
            "request.requested_for": "A User",
            "sys_created_on": "2026-06-01 09:00:00",
        }
    ]
    db, client_id, _, upload_batch_id, _, _ = create_raw_batch_fixture(
        rows,
        ticket_type="SERVICE_CATALOG_TASK",
    )

    try:
        with TestClient(app) as client:
            response = client.get(f"/api/uploads/batches/{upload_batch_id}/validation-summary")

        assert response.status_code == 200
        payload = response.json()
        assert payload["total_raw_rows"] == 1
        assert payload["rows_by_uploaded_file"][0]["row_count"] == 1
        assert "request.requested_for" in payload["detected_source_columns"]
    finally:
        cleanup_client(db, client_id)


def test_empty_validation_summary_returns_clear_message() -> None:
    db, client_id, _, upload_batch_id, _, _ = create_raw_batch_fixture([])

    try:
        summary = build_validation_summary(db, upload_batch_id)

        assert summary.total_raw_rows == 0
        assert summary.message == "No raw rows found. Ingest files first."
    finally:
        cleanup_client(db, client_id)


def test_empty_validation_summary_endpoint_returns_clear_message() -> None:
    db, client_id, _, upload_batch_id, _, _ = create_raw_batch_fixture([])

    try:
        with TestClient(app) as client:
            response = client.get(f"/api/uploads/batches/{upload_batch_id}/validation-summary")

        assert response.status_code == 200
        payload = response.json()
        assert payload["total_raw_rows"] == 0
        assert payload["message"] == "No raw rows found. Ingest files first."
        assert payload["rows_by_uploaded_file"][0]["row_count"] == 0
    finally:
        cleanup_client(db, client_id)


def test_batch_status_recalculation_handles_running_partial_and_completed() -> None:
    db, client_id, project_id, upload_batch_id, first_file_id, _ = create_raw_batch_fixture(
        [{"number": "INC010"}]
    )

    try:
        second_file = UploadedFile(
            upload_batch_id=upload_batch_id,
            project_id=project_id,
            ticket_type="INCIDENT",
            original_filename="second.csv",
            saved_filename="second.csv",
            storage_path="C:\\temp\\second.csv",
            size_bytes=128,
            status="STORED",
        )
        db.add(second_file)
        db.flush()
        upload_batch = db.get(UploadBatch, upload_batch_id)
        assert upload_batch is not None
        upload_batch.file_count = 2

        first_job = IngestionJob(
            upload_batch_id=upload_batch_id,
            uploaded_file_id=first_file_id,
            job_type="FILE_INGESTION",
            status="RUNNING",
        )
        second_job = IngestionJob(
            upload_batch_id=upload_batch_id,
            uploaded_file_id=second_file.id,
            job_type="FILE_INGESTION",
            status="PENDING",
        )
        db.add_all([first_job, second_job])
        db.flush()

        recalculate_upload_batch_status(db, upload_batch_id)
        assert upload_batch.status == "INGESTING"

        first_job.status = "COMPLETED"
        recalculate_upload_batch_status(db, upload_batch_id)
        assert upload_batch.status == "INGESTING"

        second_job.status = "COMPLETED"
        recalculate_upload_batch_status(db, upload_batch_id)
        assert upload_batch.status == "INGESTED"
    finally:
        cleanup_client(db, client_id)


def test_source_column_detection_and_suggested_mapping() -> None:
    rows = [
        {
            "number": "INC001",
            "short_description": "Email issue",
            "sys_created_on": "2026-06-01",
        }
    ]
    db, client_id, _, upload_batch_id, _, _ = create_raw_batch_fixture(rows)

    try:
        source_columns = infer_source_columns(db, upload_batch_id)
        suggested_mapping = get_suggested_mapping_for_batch(db, upload_batch_id)

        assert {column.name for column in source_columns} == {
            "number",
            "short_description",
            "sys_created_on",
        }
        assert suggested_mapping["ticket_id"] == "number"
        assert suggested_mapping["title"] == "short_description"
        assert suggested_mapping["created_at"] == "sys_created_on"
    finally:
        cleanup_client(db, client_id)


def test_incident_suggested_mapping_matches_real_servicenow_columns() -> None:
    rows = [{column: f"value-{column}" for column in INCIDENT_SOURCE_COLUMNS}]
    db, client_id, _, upload_batch_id, _, _ = create_raw_batch_fixture(rows)

    try:
        suggested_mapping = get_suggested_mapping_for_batch(db, upload_batch_id)

        assert suggested_mapping["ticket_id"] == "number"
        assert suggested_mapping["title"] == "short_description"
        assert suggested_mapping["description"] == "description"
        assert suggested_mapping["status"] == "state"
        assert suggested_mapping["priority"] == "priority"
        assert suggested_mapping["urgency"] == "urgency"
        assert suggested_mapping["impact"] == "impact"
        assert suggested_mapping["category"] == "category"
        assert suggested_mapping["subcategory"] == "subcategory"
        assert suggested_mapping["application"] == "business_service"
        assert suggested_mapping["configuration_item"] == "cmdb_ci"
        assert suggested_mapping["assignment_group"] == "assignment_group"
        assert suggested_mapping["assigned_to"] == "assigned_to"
        assert suggested_mapping["requester"] == "caller_id"
        assert suggested_mapping["created_by"] == "opened_by"
        assert suggested_mapping["created_at"] == "sys_created_on"
        assert suggested_mapping["resolved_at"] == "resolved_at"
        assert suggested_mapping["closed_at"] == "closed_at"
        assert suggested_mapping["sla_breached"] == "made_sla"
        assert suggested_mapping["reassignment_count"] == "reassignment_count"
        assert suggested_mapping["business_duration_seconds"] == "business_stc"
        assert suggested_mapping["reopen_count"] == "reopen_count"
        assert suggested_mapping["resolution_code"] == "close_code"
        assert suggested_mapping["resolution_notes"] == "close_notes"
    finally:
        cleanup_client(db, client_id)


def test_sc_task_suggested_mapping_matches_real_servicenow_columns() -> None:
    rows = [{column: f"value-{column}" for column in SC_TASK_SOURCE_COLUMNS}]
    db, client_id, _, upload_batch_id, _, _ = create_raw_batch_fixture(
        rows,
        ticket_type="SERVICE_CATALOG_TASK",
    )

    try:
        suggested_mapping = get_suggested_mapping_for_batch(db, upload_batch_id)

        assert suggested_mapping["ticket_id"] == "number"
        assert suggested_mapping["title"] == "short_description"
        assert suggested_mapping["description"] == "description"
        assert suggested_mapping["status"] == "state"
        assert suggested_mapping["priority"] == "priority"
        assert suggested_mapping["category"] == "sc_catalog"
        assert suggested_mapping["application"] == "cmdb_ci_business_app"
        assert suggested_mapping["configuration_item"] == "cmdb_ci"
        assert suggested_mapping["assignment_group"] == "assignment_group"
        assert suggested_mapping["assigned_to"] == "assigned_to"
        assert suggested_mapping["requester"] == "request.requested_for"
        assert suggested_mapping["created_by"] == "sys_created_by"
        assert suggested_mapping["created_channel"] == "contact_type"
        assert suggested_mapping["created_at"] == "sys_created_on"
        assert suggested_mapping["closed_at"] == "closed_at"
        assert suggested_mapping["sla_breached"] == "made_sla"
        assert suggested_mapping["business_duration_seconds"] == "business_duration"
        assert suggested_mapping["reassignment_count"] == "reassignment_count"
        assert suggested_mapping["resolution_notes"] == "close_notes"
    finally:
        cleanup_client(db, client_id)


def test_save_and_retrieve_mapping_template() -> None:
    db, client_id, project_id, _, _, _ = create_raw_batch_fixture([])
    mapping = {"ticket_id": "number", "created_at": "sys_created_on"}

    try:
        save_mapping_template(db, project_id, "incident", mapping, notes="test template")
        saved_rows = get_mapping_template(db, project_id, "INCIDENT")

        assert mapping_rows_to_field_mapping(saved_rows) == mapping
        assert all(row.ticket_type == "INCIDENT" for row in saved_rows)
    finally:
        cleanup_client(db, client_id)


def test_save_mapping_template_allows_source_column_reuse() -> None:
    db, client_id, project_id, _, _, _ = create_raw_batch_fixture([])
    mapping = {
        "ticket_id": "number",
        "application": "business_service",
        "business_service": "business_service",
        "created_at": "sys_created_on",
    }

    try:
        save_mapping_template(db, project_id, "INCIDENT", mapping)
        saved_rows = get_mapping_template(db, project_id, "INCIDENT")

        assert mapping_rows_to_field_mapping(saved_rows) == mapping
    finally:
        cleanup_client(db, client_id)


def test_suggested_mapping_prefers_saved_project_ticket_type_template() -> None:
    rows = [
        {
            "number": "INC050",
            "short_description": "Remember mapping",
            "sys_created_on": "2026-06-01",
            "business_stc": "3600",
            "reassignment_count": "1",
        }
    ]
    db, client_id, project_id, upload_batch_id, _, _ = create_raw_batch_fixture(rows)
    saved_mapping = {
        "ticket_id": "number",
        "title": "short_description",
        "created_at": "sys_created_on",
        "business_duration_seconds": "business_stc",
        "reassignment_count": "reassignment_count",
    }

    try:
        save_mapping_template(db, project_id, "INCIDENT", saved_mapping)
        suggested_mapping = get_suggested_mapping_result(
            db,
            project_id,
            "INCIDENT",
            upload_batch_id,
        )

        assert suggested_mapping.mapping_source == "SAVED_TEMPLATE"
        assert suggested_mapping.mapping == saved_mapping
        assert suggested_mapping.project_id == project_id
        assert suggested_mapping.ticket_type == "INCIDENT"
    finally:
        cleanup_client(db, client_id)


def test_suggested_mapping_uses_built_in_defaults_without_saved_template() -> None:
    incident_rows = [{column: f"value-{column}" for column in INCIDENT_SOURCE_COLUMNS}]
    db, client_id, project_id, incident_batch_id, _, _ = create_raw_batch_fixture(incident_rows)

    try:
        sc_task_batch_id = add_upload_batch_with_raw_rows(
            db,
            project_id,
            [{column: f"value-{column}" for column in SC_TASK_SOURCE_COLUMNS}],
            "SERVICE_CATALOG_TASK",
            "sc-task-built-in",
        )

        incident_suggestion = get_suggested_mapping_result(
            db,
            project_id,
            "INCIDENT",
            incident_batch_id,
        )
        sc_task_suggestion = get_suggested_mapping_result(
            db,
            project_id,
            "SERVICE_CATALOG_TASK",
            sc_task_batch_id,
        )

        assert incident_suggestion.mapping_source == "BUILT_IN_SUGGESTION"
        assert incident_suggestion.mapping["business_duration_seconds"] == "business_stc"
        assert incident_suggestion.mapping["reassignment_count"] == "reassignment_count"
        assert sc_task_suggestion.mapping_source == "BUILT_IN_SUGGESTION"
        assert sc_task_suggestion.mapping["business_duration_seconds"] == "business_duration"
        assert sc_task_suggestion.mapping["reassignment_count"] == "reassignment_count"
    finally:
        cleanup_client(db, client_id)


def test_apply_mapping_normalizes_incident_rows_and_is_idempotent() -> None:
    rows = [
        {
            "number": "INC100",
            "short_description": "Email unavailable",
            "state": "Resolved",
            "priority": "Critical",
            "assignment_group": IN_SCOPE_ASSIGNMENT_GROUP,
            "business_service": IN_SCOPE_BUSINESS_SERVICE,
            "sys_created_on": "2026-06-03 09:15:00",
            "resolved_at": "06/03/2026 10:30",
            "made_sla": "true",
            "reopen_count": "2",
            "comments": "User called back",
            "work_notes": "Restarted service",
        }
    ]
    db, client_id, project_id, upload_batch_id, _, _ = create_raw_batch_fixture(rows)
    mapping = {
        "ticket_id": "number",
        "title": "short_description",
        "status": "state",
        "priority": "priority",
        "assignment_group": "assignment_group",
        "business_service": "business_service",
        "created_at": "sys_created_on",
        "resolved_at": "resolved_at",
        "sla_breached": "made_sla",
        "reopen_count": "reopen_count",
    }

    try:
        add_application_inventory_scope(db, project_id)
        db.commit()
        first_result = apply_mapping_to_batch(db, upload_batch_id, mapping)
        second_result = apply_mapping_to_batch(db, upload_batch_id, mapping)

        assert first_result.normalized_ticket_count == 1
        assert first_result.failed_row_count == 0
        assert second_result.normalized_ticket_count == 1
        assert second_result.failed_row_count == 0

        ticket_count = db.scalar(
            select(func.count(Ticket.id)).where(Ticket.upload_batch_id == upload_batch_id)
        )
        ticket = db.scalar(select(Ticket).where(Ticket.upload_batch_id == upload_batch_id))

        assert ticket_count == 1
        assert ticket is not None
        assert ticket.ticket_number == "INC100"
        assert ticket.ticket_type == "INCIDENT"
        assert ticket.short_description == "Email unavailable"
        assert ticket.priority == "P1"
        assert ticket.architecture_type == "Vendor Managed"
        assert ticket.install_type == "Cloud"
        assert ticket.sla_breached is False
        assert ticket.reopen_count == 2
        assert ticket.normalized_payload is not None
        assert ticket.normalized_payload["raw_payload_json"]["number"] == "INC100"
        assert ticket.normalized_payload["raw_payload_json"]["comments"] == "User called back"
        assert ticket.normalized_payload["unmapped_fields"]["work_notes"] == "Restarted service"
    finally:
        cleanup_client(db, client_id)


def test_apply_mapping_normalizes_service_catalog_task_rows() -> None:
    rows = [
        {
            "task_number": "SCTASK100",
            "short_description": "Request laptop access",
            "state": "Open",
            "priority": "4 - Low",
            "assignment_group": IN_SCOPE_ASSIGNMENT_GROUP,
            "business_service": IN_SCOPE_BUSINESS_SERVICE,
            "requested_for": "A User",
            "sys_created_on": "06/12/2026 13:45",
            "has_breached": "No",
            "business_duration": "172800",
            "reassignment_count": "3",
        }
    ]
    db, client_id, project_id, upload_batch_id, _, _ = create_raw_batch_fixture(
        rows,
        ticket_type="SERVICE_CATALOG_TASK",
    )
    mapping = {
        "ticket_id": "task_number",
        "title": "short_description",
        "status": "state",
        "priority": "priority",
        "assignment_group": "assignment_group",
        "business_service": "business_service",
        "requester": "requested_for",
        "created_at": "sys_created_on",
        "sla_breached": "has_breached",
        "business_duration_seconds": "business_duration",
        "reassignment_count": "reassignment_count",
    }

    try:
        add_application_inventory_scope(db, project_id)
        db.commit()
        result = apply_mapping_to_batch(db, upload_batch_id, mapping)
        ticket = db.scalar(select(Ticket).where(Ticket.upload_batch_id == upload_batch_id))

        assert result.normalized_ticket_count == 1
        assert ticket is not None
        assert ticket.ticket_number == "SCTASK100"
        assert ticket.ticket_type == "SERVICE_CATALOG_TASK"
        assert ticket.priority == "P4"
        assert ticket.requester == "A User"
        assert ticket.sla_breached is False
        assert ticket.business_duration_seconds == 172800
        assert ticket.reassignment_count == 3
    finally:
        cleanup_client(db, client_id)


def test_apply_mapping_derives_sap_non_sap_for_in_scope_and_out_of_scope_rows() -> None:
    rows = [
        {
            "number": "INC-SAP",
            "short_description": "SAP application issue",
            "state": "Resolved",
            "priority": "High",
            "assignment_group": "IT-SAP-Mapping",
            "business_service": IN_SCOPE_BUSINESS_SERVICE,
            "sys_created_on": "2026-06-03 09:15:00",
            "resolved_at": "2026-06-03 10:30:00",
        },
        {
            "number": "INC-NSA-OOS",
            "short_description": "Non-SAP unmapped issue",
            "state": "Open",
            "priority": "Low",
            "assignment_group": "it-nsa-unmapped",
            "business_service": "Unknown Service",
            "sys_created_on": "2026-06-04 09:15:00",
        },
    ]
    db, client_id, project_id, upload_batch_id, _, _ = create_raw_batch_fixture(rows)
    mapping = {
        "ticket_id": "number",
        "title": "short_description",
        "status": "state",
        "priority": "priority",
        "assignment_group": "assignment_group",
        "business_service": "business_service",
        "created_at": "sys_created_on",
        "resolved_at": "resolved_at",
    }

    try:
        add_application_inventory_scope(
            db,
            project_id,
            assignment_group="IT-SAP-Mapping",
        )
        db.commit()
        result = apply_mapping_to_batch(db, upload_batch_id, mapping)
        in_scope_ticket = db.scalar(select(Ticket).where(Ticket.ticket_number == "INC-SAP"))
        out_of_scope_ticket = db.scalar(
            select(AssessmentOutOfScopeTicket).where(
                AssessmentOutOfScopeTicket.ticket_number == "INC-NSA-OOS",
            ),
        )

        assert result.normalized_ticket_count == 1
        assert result.out_of_scope_ticket_count == 1
        assert in_scope_ticket is not None
        assert in_scope_ticket.sap_non_sap == "SAP"
        assert in_scope_ticket.architecture_type == "Vendor Managed"
        assert in_scope_ticket.install_type == "Cloud"
        assert out_of_scope_ticket is not None
        assert out_of_scope_ticket.sap_non_sap == "Non-SAP"
        assert out_of_scope_ticket.architecture_type is None
        assert out_of_scope_ticket.install_type is None
    finally:
        cleanup_client(db, client_id)


def test_batch_classification_rule_is_incident_short_description_only() -> None:
    assert derive_is_batch_related("INCIDENT", "Automic job failed") is True
    assert derive_is_batch_related("INCIDENT", "automic job failed") is True
    assert derive_is_batch_related("INCIDENT", "Manual ticket") is False
    assert derive_is_batch_related("SERVICE_CATALOG_TASK", "Automic request") is False
    assert derive_is_batch_related("INCIDENT", None) is False


def test_apply_mapping_populates_incident_batch_classification() -> None:
    rows = [
        {
            "number": "INC-BATCH",
            "caller_id": "End User",
            "short_description": "Automic batch failure",
            "state": "Resolved",
            "assignment_group": IN_SCOPE_ASSIGNMENT_GROUP,
            "business_service": IN_SCOPE_BUSINESS_SERVICE,
            "sys_created_on": "2026-06-03 09:15:00",
        },
        {
            "number": "INC-CALLER-ONLY",
            "caller_id": "ITSM - Automic INC integration",
            "short_description": "Manual incident without keyword",
            "state": "Resolved",
            "assignment_group": IN_SCOPE_ASSIGNMENT_GROUP,
            "business_service": IN_SCOPE_BUSINESS_SERVICE,
            "sys_created_on": "2026-06-04 09:15:00",
        },
        {
            "number": "INC-BATCH-OOS",
            "caller_id": "End User",
            "short_description": "AUTOMIC failed in unknown service",
            "state": "Open",
            "assignment_group": "Unmapped Group",
            "business_service": "Unknown Service",
            "sys_created_on": "2026-06-05 09:15:00",
        },
    ]
    db, client_id, project_id, upload_batch_id, _, _ = create_raw_batch_fixture(rows)
    mapping = {
        "ticket_id": "number",
        "title": "short_description",
        "status": "state",
        "assignment_group": "assignment_group",
        "business_service": "business_service",
        "created_at": "sys_created_on",
    }

    try:
        add_application_inventory_scope(db, project_id)
        db.commit()
        apply_mapping_to_batch(db, upload_batch_id, mapping)

        tickets = {
            ticket.ticket_number: ticket
            for ticket in db.scalars(
                select(Ticket).where(Ticket.upload_batch_id == upload_batch_id),
            )
        }
        out_of_scope_ticket = db.scalar(
            select(AssessmentOutOfScopeTicket).where(
                AssessmentOutOfScopeTicket.ticket_number == "INC-BATCH-OOS",
            ),
        )

        assert tickets["INC-BATCH"].is_batch_related is True
        assert tickets["INC-CALLER-ONLY"].is_batch_related is False
        assert out_of_scope_ticket is not None
        assert out_of_scope_ticket.is_batch_related is True
    finally:
        cleanup_client(db, client_id)


def test_apply_mapping_sets_sc_task_batch_classification_false() -> None:
    rows = [
        {
            "number": "SCTASK-BATCH",
            "short_description": "Automic request should not use Incident batch rule",
            "state": "Closed",
            "assignment_group": IN_SCOPE_ASSIGNMENT_GROUP,
            "business_service": IN_SCOPE_BUSINESS_SERVICE,
            "sys_created_on": "2026-06-03 09:15:00",
        },
    ]
    db, client_id, project_id, upload_batch_id, _, _ = create_raw_batch_fixture(
        rows,
        ticket_type="SERVICE_CATALOG_TASK",
    )
    mapping = {
        "ticket_id": "number",
        "title": "short_description",
        "status": "state",
        "assignment_group": "assignment_group",
        "business_service": "business_service",
        "created_at": "sys_created_on",
    }

    try:
        add_application_inventory_scope(db, project_id)
        db.commit()
        apply_mapping_to_batch(db, upload_batch_id, mapping)
        ticket = db.scalar(select(Ticket).where(Ticket.ticket_number == "SCTASK-BATCH"))

        assert ticket is not None
        assert ticket.ticket_type == "SERVICE_CATALOG_TASK"
        assert ticket.is_batch_related is False
    finally:
        cleanup_client(db, client_id)


def test_scoped_apply_can_target_one_incident_batch_only() -> None:
    rows = [
        {
            "number": "INC300",
            "short_description": "First incident batch",
            "assignment_group": IN_SCOPE_ASSIGNMENT_GROUP,
            "business_service": IN_SCOPE_BUSINESS_SERVICE,
            "sys_created_on": "2026-06-01",
            "business_stc": "86400",
            "reassignment_count": "2",
        }
    ]
    db, client_id, project_id, first_batch_id, _, _ = create_raw_batch_fixture(rows)
    second_batch_id = add_upload_batch_with_raw_rows(
        db,
        project_id,
        [
                {
                    "number": "INC301",
                    "short_description": "Second incident batch",
                    "assignment_group": IN_SCOPE_ASSIGNMENT_GROUP,
                    "business_service": IN_SCOPE_BUSINESS_SERVICE,
                    "sys_created_on": "2026-07-01",
                "business_stc": "172800",
                "reassignment_count": "3",
            }
        ],
        "INCIDENT",
        "incident-second-batch",
    )
    mapping = {
        "ticket_id": "number",
        "title": "short_description",
        "assignment_group": "assignment_group",
        "business_service": "business_service",
        "created_at": "sys_created_on",
        "business_duration_seconds": "business_stc",
        "reassignment_count": "reassignment_count",
    }

    try:
        add_application_inventory_scope(db, project_id)
        db.commit()
        result = apply_mapping_with_scope(
            db=db,
            project_id=project_id,
            ticket_type="INCIDENT",
            upload_batch_id=first_batch_id,
            scope="BATCH",
            mapping=mapping,
            save_as_default_for_ticket_type=True,
        )
        first_batch_ticket_count = db.scalar(
            select(func.count(Ticket.id)).where(Ticket.upload_batch_id == first_batch_id)
        )
        second_batch_ticket_count = db.scalar(
            select(func.count(Ticket.id)).where(Ticket.upload_batch_id == second_batch_id)
        )
        ticket = db.scalar(select(Ticket).where(Ticket.upload_batch_id == first_batch_id))

        assert result.scope == "BATCH"
        assert result.saved_as_default_for_ticket_type is True
        assert result.normalized_ticket_count == 1
        assert len(result.batch_results) == 1
        assert first_batch_ticket_count == 1
        assert second_batch_ticket_count == 0
        assert ticket is not None
        assert ticket.business_duration_seconds == 86400
        assert ticket.reassignment_count == 2
        assert ticket.normalized_payload is not None
        assert ticket.normalized_payload["raw_payload_json"]["business_stc"] == "86400"
        assert mapping_rows_to_field_mapping(get_mapping_template(db, project_id, "INCIDENT"))[
            "business_duration_seconds"
        ] == "business_stc"
    finally:
        cleanup_client(db, client_id)


def test_scoped_apply_targets_only_selected_ticket_type_batches() -> None:
    incident_rows = [
        {
            "number": "INC400",
            "short_description": "Incident first",
            "assignment_group": IN_SCOPE_ASSIGNMENT_GROUP,
            "business_service": IN_SCOPE_BUSINESS_SERVICE,
            "sys_created_on": "2026-06-01",
            "business_stc": "86400",
            "reassignment_count": "2",
        }
    ]
    db, client_id, project_id, first_incident_batch_id, _, _ = create_raw_batch_fixture(
        incident_rows
    )
    second_incident_batch_id = add_upload_batch_with_raw_rows(
        db,
        project_id,
        [
                {
                    "number": "INC401",
                    "short_description": "Incident second",
                    "assignment_group": IN_SCOPE_ASSIGNMENT_GROUP,
                    "business_service": IN_SCOPE_BUSINESS_SERVICE,
                    "sys_created_on": "2026-07-01",
                "business_stc": "172800",
                "reassignment_count": "3",
            }
        ],
        "INCIDENT",
        "incident-scope-second",
    )
    sc_task_batch_id = add_upload_batch_with_raw_rows(
        db,
        project_id,
        [
                {
                    "number": "SCTASK400",
                    "short_description": "SC Task first",
                    "assignment_group": IN_SCOPE_ASSIGNMENT_GROUP,
                    "business_service": IN_SCOPE_BUSINESS_SERVICE,
                    "sys_created_on": "2026-06-05",
                "business_duration": "259200",
                "reassignment_count": "4",
            }
        ],
        "SERVICE_CATALOG_TASK",
        "sc-task-scope-first",
    )
    incident_mapping = {
        "ticket_id": "number",
        "title": "short_description",
        "assignment_group": "assignment_group",
        "business_service": "business_service",
        "created_at": "sys_created_on",
        "business_duration_seconds": "business_stc",
        "reassignment_count": "reassignment_count",
    }
    sc_task_mapping = {
        "ticket_id": "number",
        "title": "short_description",
        "assignment_group": "assignment_group",
        "business_service": "business_service",
        "created_at": "sys_created_on",
        "business_duration_seconds": "business_duration",
        "reassignment_count": "reassignment_count",
    }

    try:
        add_application_inventory_scope(db, project_id)
        db.commit()
        incident_result = apply_mapping_with_scope(
            db=db,
            project_id=project_id,
            ticket_type="INCIDENT",
            scope="TICKET_TYPE",
            mapping=incident_mapping,
            save_as_default_for_ticket_type=True,
        )
        sc_task_ticket_count_before = db.scalar(
            select(func.count(Ticket.id)).where(Ticket.upload_batch_id == sc_task_batch_id)
        )

        assert incident_result.scope == "TICKET_TYPE"
        assert incident_result.saved_as_default_for_ticket_type is True
        assert len(incident_result.batch_results) == 2
        assert incident_result.normalized_ticket_count == 2
        assert sc_task_ticket_count_before == 0

        first_incident = db.scalar(
            select(Ticket).where(Ticket.upload_batch_id == first_incident_batch_id)
        )
        second_incident = db.scalar(
            select(Ticket).where(Ticket.upload_batch_id == second_incident_batch_id)
        )
        assert first_incident is not None
        assert second_incident is not None
        assert first_incident.business_duration_seconds == 86400
        assert second_incident.business_duration_seconds == 172800
        assert first_incident.reassignment_count == 2
        assert second_incident.reassignment_count == 3

        sc_task_result = apply_mapping_with_scope(
            db=db,
            project_id=project_id,
            ticket_type="SERVICE_CATALOG_TASK",
            scope="TICKET_TYPE",
            mapping=sc_task_mapping,
            save_as_default_for_ticket_type=True,
        )
        incident_ticket_count_after = db.scalar(
            select(func.count(Ticket.id)).where(
                Ticket.project_id == project_id,
                Ticket.ticket_type == "INCIDENT",
            )
        )
        sc_task = db.scalar(select(Ticket).where(Ticket.upload_batch_id == sc_task_batch_id))

        assert sc_task_result.scope == "TICKET_TYPE"
        assert len(sc_task_result.batch_results) == 1
        assert sc_task_result.normalized_ticket_count == 1
        assert incident_ticket_count_after == 2
        assert sc_task is not None
        assert sc_task.ticket_type == "SERVICE_CATALOG_TASK"
        assert sc_task.business_duration_seconds == 259200
        assert sc_task.reassignment_count == 4
        assert sc_task.normalized_payload is not None
        assert sc_task.normalized_payload["raw_payload_json"]["business_duration"] == "259200"
    finally:
        cleanup_client(db, client_id)


def test_apply_mapping_handles_business_duration_variants_without_row_failures() -> None:
    rows = [
        in_scope_raw({
            "number": "SCTASK200",
            "short_description": "Numeric duration",
            "business_duration": 12345,
            "reassignment_count": "2",
        }),
        in_scope_raw({
            "number": "SCTASK201",
            "short_description": "Numeric string duration",
            "business_duration": "12345",
            "reassignment_count": "3",
        }),
        in_scope_raw({
            "number": "SCTASK202",
            "short_description": "Comma duration",
            "business_duration": "12,345",
            "reassignment_count": "1,234",
        }),
        in_scope_raw({
            "number": "SCTASK203",
            "short_description": "Blank duration",
            "business_duration": "",
            "reassignment_count": "",
        }),
        in_scope_raw({
            "number": "SCTASK204",
            "short_description": "Invalid duration",
            "business_duration": "not a duration",
            "reassignment_count": "not a count",
        }),
        in_scope_raw({
            "number": "SCTASK205",
            "short_description": "Null duration",
            "business_duration": None,
            "reassignment_count": None,
        }),
    ]
    db, client_id, project_id, upload_batch_id, _, _ = create_raw_batch_fixture(
        rows,
        ticket_type="SERVICE_CATALOG_TASK",
    )
    mapping = {
        "ticket_id": "number",
        "title": "short_description",
        "assignment_group": "assignment_group",
        "business_service": "business_service",
        "business_duration_seconds": "business_duration",
        "reassignment_count": "reassignment_count",
    }

    try:
        add_application_inventory_scope(db, project_id)
        db.commit()
        first_result = apply_mapping_to_batch(db, upload_batch_id, mapping)
        second_result = apply_mapping_to_batch(db, upload_batch_id, mapping)
        tickets = {
            ticket.ticket_number: ticket
            for ticket in db.scalars(
                select(Ticket).where(Ticket.upload_batch_id == upload_batch_id)
            )
        }

        assert first_result.normalized_ticket_count == 6
        assert first_result.failed_row_count == 0
        assert second_result.normalized_ticket_count == 6
        assert second_result.failed_row_count == 0
        assert len(tickets) == 6
        assert tickets["SCTASK200"].business_duration_seconds == 12345
        assert tickets["SCTASK201"].business_duration_seconds == 12345
        assert tickets["SCTASK202"].business_duration_seconds == 12345
        assert tickets["SCTASK202"].reassignment_count == 1234
        assert tickets["SCTASK203"].business_duration_seconds is None
        assert tickets["SCTASK203"].reassignment_count is None
        assert tickets["SCTASK204"].business_duration_seconds is None
        assert tickets["SCTASK204"].reassignment_count is None
        assert tickets["SCTASK205"].business_duration_seconds is None
        assert tickets["SCTASK205"].reassignment_count is None
        assert tickets["SCTASK202"].normalized_payload is not None
        assert (
            tickets["SCTASK202"].normalized_payload["raw_payload_json"]["business_duration"]
            == "12,345"
        )
    finally:
        cleanup_client(db, client_id)


def test_date_parsing_and_priority_normalization() -> None:
    assert parse_datetime_value("2026-06-01 09:30:00") is not None
    assert parse_datetime_value("06/01/2026 09:30") is not None
    assert parse_datetime_value("01-Jun-2026") is not None
    assert parse_datetime_value("") is None

    assert normalize_priority("P1") == "P1"
    assert normalize_priority("1") == "P1"
    assert normalize_priority("High") == "P2"
    assert normalize_priority("3 - Medium") == "P3"
    assert normalize_priority("Moderate") == "P3"
    assert normalize_priority("Low") == "P4"
    assert normalize_priority("Planning") == "P5"
    assert normalize_priority("Very Low") == "P5"


def test_made_sla_is_inverted_for_sla_breached() -> None:
    assert parse_sla_breached_value("true", "made_sla") is False
    assert parse_sla_breached_value("false", "made_sla") is True
    assert parse_sla_breached_value("yes", "sla_breached") is True


def test_business_duration_parsing() -> None:
    assert parse_business_duration_seconds("172800") == 172800
    assert parse_business_duration_seconds("12,345") == 12345
    assert parse_business_duration_seconds("") is None
    assert parse_business_duration_seconds(None) is None
    assert parse_business_duration_seconds("not a duration") is None
    assert parse_business_duration_seconds("2 days 3 hours") == 183600
    assert parse_business_duration_seconds("1 02:03:04") == 93784
