from datetime import date
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select

from app.db.session import SessionLocal
from app.main import app
from app.models import (
    ApplicationInventoryItem,
    AssessmentOutOfScopeTicket,
    Client,
    DashboardFilterCacheStatus,
    InScopeAssignmentGroup,
    Project,
    Ticket,
    TicketRawRow,
    UploadBatch,
    UploadedFile,
)
from app.services.mapping import apply_mapping_to_batch, save_mapping_template


def create_project_fixture():
    db = SessionLocal()
    unique_suffix = uuid4().hex[:12]
    client = Client(
        name=f"Upload Lifecycle Client {unique_suffix}",
        code=f"ULC-{unique_suffix}",
    )
    db.add(client)
    db.flush()

    project = Project(
        client_id=client.id,
        name=f"Upload Lifecycle Project {unique_suffix}",
        code=f"ULP-{unique_suffix}",
    )
    db.add(project)
    db.flush()
    db.add(
        InScopeAssignmentGroup(
            client_id=client.id,
            project_id=project.id,
            assignment_group="AMS Support",
            assignment_group_key="ams support",
            functional_track="Lifecycle Track",
            source_filename="lifecycle-scope-reference.xlsx",
            source_row_number=1,
            is_active=True,
        )
    )
    db.add(
        ApplicationInventoryItem(
            project_id=project.id,
            application_number_apm="APM-LIFECYCLE",
            parent_application_name="Lifecycle Parent App",
            assignment_group="AMS Support",
            business_service_ci_name="Lifecycle Service",
            supported_by_vendor="HCLTech",
            active=True,
            source_filename="lifecycle-inventory.xlsx",
            source_row_number=1,
        )
    )
    db.commit()
    return db, client.id, project.id


def cleanup_client(db, client_id: UUID) -> None:
    db.rollback()
    db.execute(delete(Client).where(Client.id == client_id))
    db.commit()
    db.close()


def csv_upload(
    filename: str = "incidents.csv",
    body: bytes = (
        b"number,short_description,assignment_group,business_service,sys_created_on\n"
        b"INC-LC-001,Open incident,AMS Support,Lifecycle Service,2026-06-01\n"
    ),
) -> dict[str, tuple[str, bytes, str]]:
    return {"files": (filename, body, "text/csv")}


def upload_monthly_batch(
    client: TestClient,
    project_id: UUID,
    batch_name: str = "Lifecycle Batch",
    file_body: bytes = (
        b"number,short_description,assignment_group,business_service,sys_created_on\n"
        b"INC-LC-001,Open incident,AMS Support,Lifecycle Service,2026-06-01\n"
    ),
) -> tuple[str, str]:
    response = client.post(
        "/api/uploads",
        data={
            "project_id": str(project_id),
            "ticket_type": "INCIDENT",
            "period_type": "MONTHLY",
            "month_key": "2026-06",
            "batch_name": batch_name,
        },
        files=csv_upload(body=file_body),
    )
    assert response.status_code == 201
    payload = response.json()
    return payload["batch"]["id"], payload["files"][0]["id"]


def add_ingested_raw_batch(
    db,
    project_id: UUID,
    *,
    batch_name: str,
    ticket_type: str,
    rows: list[dict[str, object]],
) -> UUID:
    upload_batch = UploadBatch(
        project_id=project_id,
        month_key=None,
        period_type="SNAPSHOT",
        snapshot_date=date(2026, 6, 20),
        batch_name=batch_name,
        status="INGESTED",
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

    for row_number, raw_data in enumerate(rows, start=2):
        db.add(
            TicketRawRow(
                project_id=project_id,
                upload_batch_id=upload_batch.id,
                uploaded_file_id=uploaded_file.id,
                ticket_type=ticket_type,
                row_number=row_number,
                source_filename=uploaded_file.original_filename,
                raw_ticket_number=str(raw_data.get("number") or ""),
                raw_data=raw_data,
                row_hash=uuid4().hex,
            )
        )

    db.commit()
    return upload_batch.id


def batch_ids(payload: list[dict[str, object]]) -> set[str]:
    return {str(row["id"]) for row in payload}


def test_upload_multiple_creates_one_batch_per_valid_file_and_reports_partial_failure() -> None:
    db, client_id, project_id = create_project_fixture()

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/uploads/upload-multiple",
                data={
                    "project_id": str(project_id),
                    "ticket_type": "INCIDENT",
                    "period_type": "MONTHLY",
                    "month_key": "2026-06",
                    "batch_name": "Multi Incident Upload",
                },
                files=[
                    (
                        "files",
                        (
                            "incidents-1.csv",
                            (
                                b"number,short_description,assignment_group,business_service,"
                                b"sys_created_on\n"
                                b"INC-MULTI-1,First,AMS Support,Lifecycle Service,2026-06-01\n"
                            ),
                            "text/csv",
                        ),
                    ),
                    ("files", ("notes.txt", b"not,a,ticket\n", "text/plain")),
                    (
                        "files",
                        (
                            "incidents-2.csv",
                            (
                                b"number,short_description,assignment_group,business_service,"
                                b"sys_created_on\n"
                                b"INC-MULTI-2,Second,AMS Support,Lifecycle Service,2026-06-02\n"
                            ),
                            "text/csv",
                        ),
                    ),
                ],
            )

        assert response.status_code == 201
        payload = response.json()
        assert payload["totals"] == {
            "files_selected": 3,
            "files_uploaded": 2,
            "files_failed": 1,
        }
        uploaded_files = [row for row in payload["files"] if row["status"] == "UPLOADED"]
        failed_files = [row for row in payload["files"] if row["status"] == "FAILED_UPLOAD"]
        assert len(uploaded_files) == 2
        assert len({row["upload_batch_id"] for row in uploaded_files}) == 2
        assert failed_files[0]["filename"] == "notes.txt"
        assert "Only .csv and .xlsx" in failed_files[0]["message"]
    finally:
        cleanup_client(db, client_id)


def test_ingest_multiple_batches_processes_uploaded_files_in_one_call() -> None:
    db, client_id, project_id = create_project_fixture()

    try:
        with TestClient(app) as client:
            upload_response = client.post(
                "/api/uploads/upload-multiple",
                data={
                    "project_id": str(project_id),
                    "ticket_type": "INCIDENT",
                    "period_type": "MONTHLY",
                    "month_key": "2026-06",
                    "batch_name": "Multi Ingest Upload",
                },
                files=[
                    (
                        "files",
                        (
                            "incidents-1.csv",
                            (
                                b"number,short_description,assignment_group,business_service,"
                                b"sys_created_on\n"
                                b"INC-INGEST-1,First,AMS Support,Lifecycle Service,2026-06-01\n"
                            ),
                            "text/csv",
                        ),
                    ),
                    (
                        "files",
                        (
                            "incidents-2.csv",
                            (
                                b"number,short_description,assignment_group,business_service,"
                                b"sys_created_on\n"
                                b"INC-INGEST-2,Second,AMS Support,Lifecycle Service,2026-06-02\n"
                            ),
                            "text/csv",
                        ),
                    ),
                ],
            )
            assert upload_response.status_code == 201
            upload_batch_ids = [
                row["upload_batch_id"]
                for row in upload_response.json()["files"]
                if row["upload_batch_id"]
            ]

            ingest_response = client.post(
                "/api/uploads/batches/ingest-multiple",
                json={
                    "project_id": str(project_id),
                    "upload_batch_ids": upload_batch_ids,
                },
            )

        assert ingest_response.status_code == 200
        payload = ingest_response.json()
        assert payload["totals"]["batches_requested"] == 2
        assert payload["totals"]["batches_ingested"] == 2
        assert payload["totals"]["batches_failed"] == 0
        assert payload["totals"]["raw_rows_inserted"] == 2
        assert {batch["status"] for batch in payload["batches"]} == {"INGESTED"}
    finally:
        cleanup_client(db, client_id)


def test_normalize_multiple_handles_sc_task_open_snapshot_duplicate_replacement() -> None:
    db, client_id, project_id = create_project_fixture()

    try:
        save_mapping_template(
            db,
            project_id,
            "SERVICE_CATALOG_TASK",
            {
                "ticket_id": "number",
                "title": "short_description",
                "status": "state",
                "assignment_group": "assignment_group",
                "business_service": "business_service",
                "created_at": "sys_created_on",
                "closed_at": "closed_at",
                "business_duration_seconds": "business_duration",
                "vendor": "u_vendor",
            },
        )
        closed_batch_id = add_ingested_raw_batch(
            db,
            project_id,
            batch_name="SC Tasks Closed",
            ticket_type="SERVICE_CATALOG_TASK",
            rows=[
                {
                    "number": "SCTASK-OPEN-DUP",
                    "short_description": "Closed extract copy",
                    "state": "Closed",
                    "assignment_group": "AMS Support",
                    "business_service": "Lifecycle Service",
                    "sys_created_on": "2026-06-01",
                    "closed_at": "2026-06-02",
                    "business_duration": "3600",
                    "u_vendor": "Accenture",
                }
            ],
        )
        open_batch_id = add_ingested_raw_batch(
            db,
            project_id,
            batch_name="SC Tasks Open",
            ticket_type="SERVICE_CATALOG_TASK",
            rows=[
                {
                    "number": "SCTASK-OPEN-DUP",
                    "short_description": "Open snapshot copy",
                    "state": "Open",
                    "assignment_group": "AMS Support",
                    "business_service": "Lifecycle Service",
                    "sys_created_on": "2026-06-01",
                    "closed_at": "",
                    "business_duration": "",
                    "u_vendor": "",
                }
            ],
        )

        with TestClient(app) as client:
            response = client.post(
                "/api/uploads/batches/normalize-multiple",
                json={
                    "project_id": str(project_id),
                    "ticket_type": "SERVICE_CATALOG_TASK",
                    "upload_batch_ids": [str(closed_batch_id), str(open_batch_id)],
                    "delete_existing": True,
                },
            )

        assert response.status_code == 200
        payload = response.json()
        assert payload["totals"]["failed_batches"] == 0
        assert [batch["status"] for batch in payload["batches"]] == [
            "NORMALIZED",
            "NORMALIZED",
        ]

        ticket = db.scalar(select(Ticket).where(Ticket.ticket_number == "SCTASK-OPEN-DUP"))
        assert ticket is not None
        assert ticket.upload_batch_id == open_batch_id
        assert ticket.state == "Open"
        assert ticket.closed_at is None
        assert ticket.business_duration_seconds is None
    finally:
        cleanup_client(db, client_id)


def test_apply_mapping_multiple_uses_selected_batches_and_skips_existing_outputs() -> None:
    db, client_id, project_id = create_project_fixture()

    try:
        save_mapping_template(
            db,
            project_id,
            "INCIDENT",
            {
                "ticket_id": "number",
                "title": "short_description",
                "assignment_group": "assignment_group",
                "business_service": "business_service",
                "created_at": "sys_created_on",
            },
        )
        first_batch_id = add_ingested_raw_batch(
            db,
            project_id,
            batch_name="Apply Multi First",
            ticket_type="INCIDENT",
            rows=[
                {
                    "number": "INC-APPLY-MULTI-1",
                    "short_description": "Selected first",
                    "assignment_group": "AMS Support",
                    "business_service": "Lifecycle Service",
                    "sys_created_on": "2026-06-01",
                }
            ],
        )
        second_batch_id = add_ingested_raw_batch(
            db,
            project_id,
            batch_name="Apply Multi Second",
            ticket_type="INCIDENT",
            rows=[
                {
                    "number": "INC-APPLY-MULTI-2",
                    "short_description": "Selected second",
                    "assignment_group": "Not In Inventory",
                    "business_service": "Unknown Service",
                    "sys_created_on": "2026-06-02",
                }
            ],
        )
        third_batch_id = add_ingested_raw_batch(
            db,
            project_id,
            batch_name="Apply Multi Historical Unselected",
            ticket_type="INCIDENT",
            rows=[
                {
                    "number": "INC-APPLY-MULTI-3",
                    "short_description": "Should stay untouched",
                    "assignment_group": "AMS Support",
                    "business_service": "Lifecycle Service",
                    "sys_created_on": "2026-06-03",
                }
            ],
        )

        with TestClient(app) as client:
            first_response = client.post(
                "/api/uploads/batches/apply-mapping-multiple",
                json={
                    "project_id": str(project_id),
                    "ticket_type": "INCIDENT",
                    "upload_batch_ids": [str(first_batch_id), str(second_batch_id)],
                    "skip_already_applied": True,
                },
            )
            second_response = client.post(
                "/api/uploads/batches/apply-mapping-multiple",
                json={
                    "project_id": str(project_id),
                    "ticket_type": "INCIDENT",
                    "upload_batch_ids": [str(first_batch_id), str(second_batch_id)],
                    "skip_already_applied": True,
                },
            )

        assert first_response.status_code == 200
        first_payload = first_response.json()
        assert first_payload["totals"]["total_files"] == 2
        assert first_payload["totals"]["applied"] == 2
        assert first_payload["totals"]["skipped"] == 0
        assert first_payload["totals"]["in_scope_rows"] == 1
        assert first_payload["totals"]["out_of_scope_rows"] == 1

        assert second_response.status_code == 200
        second_payload = second_response.json()
        assert second_payload["totals"]["applied"] == 0
        assert second_payload["totals"]["skipped"] == 2
        assert {row["status"] for row in second_payload["files"]} == {
            "SKIPPED_ALREADY_APPLIED"
        }

        selected_ticket_count = db.scalar(
            select(func.count(Ticket.id)).where(Ticket.upload_batch_id == first_batch_id)
        )
        selected_out_of_scope_count = db.scalar(
            select(func.count(AssessmentOutOfScopeTicket.id)).where(
                AssessmentOutOfScopeTicket.upload_batch_id == second_batch_id
            )
        )
        unselected_ticket_count = db.scalar(
            select(func.count(Ticket.id)).where(Ticket.upload_batch_id == third_batch_id)
        )

        assert selected_ticket_count == 1
        assert selected_out_of_scope_count == 1
        assert unselected_ticket_count == 0
    finally:
        cleanup_client(db, client_id)


def test_apply_mapping_multiple_treats_cross_batch_duplicate_replacement_as_applied() -> None:
    db, client_id, project_id = create_project_fixture()

    try:
        first_batch_id = add_ingested_raw_batch(
            db,
            project_id,
            batch_name="Apply Multi Duplicate Earlier",
            ticket_type="INCIDENT",
            rows=[
                {
                    "number": "INC-APPLY-DUP",
                    "short_description": "Earlier duplicate",
                    "assignment_group": "AMS Support",
                    "business_service": "Lifecycle Service",
                    "sys_created_on": "2026-06-01",
                },
                {
                    "number": "INC-APPLY-UNIQUE-1",
                    "short_description": "Earlier unique",
                    "assignment_group": "AMS Support",
                    "business_service": "Lifecycle Service",
                    "sys_created_on": "2026-06-01",
                },
            ],
        )
        second_batch_id = add_ingested_raw_batch(
            db,
            project_id,
            batch_name="Apply Multi Duplicate Later",
            ticket_type="INCIDENT",
            rows=[
                {
                    "number": "INC-APPLY-DUP",
                    "short_description": "Later duplicate kept",
                    "assignment_group": "AMS Support",
                    "business_service": "Lifecycle Service",
                    "sys_created_on": "2026-06-02",
                },
                {
                    "number": "INC-APPLY-UNIQUE-2",
                    "short_description": "Later unique",
                    "assignment_group": "AMS Support",
                    "business_service": "Lifecycle Service",
                    "sys_created_on": "2026-06-02",
                },
            ],
        )

        with TestClient(app) as client:
            first_response = client.post(
                "/api/uploads/batches/apply-mapping-multiple",
                json={
                    "project_id": str(project_id),
                    "ticket_type": "INCIDENT",
                    "upload_batch_ids": [str(first_batch_id), str(second_batch_id)],
                    "skip_already_applied": True,
                },
            )
            second_response = client.post(
                "/api/uploads/batches/apply-mapping-multiple",
                json={
                    "project_id": str(project_id),
                    "ticket_type": "INCIDENT",
                    "upload_batch_ids": [str(first_batch_id), str(second_batch_id)],
                    "skip_already_applied": True,
                },
            )

        assert first_response.status_code == 200
        assert second_response.status_code == 200
        payload = second_response.json()
        assert payload["totals"]["failed"] == 0
        assert payload["totals"]["skipped"] == 2
        assert payload["totals"]["duplicate_skipped_rows"] == 1
        assert {row["status"] for row in payload["files"]} == {"SKIPPED_ALREADY_APPLIED"}

        earlier_row = next(
            row for row in payload["files"] if row["upload_batch_id"] == str(first_batch_id)
        )
        assert earlier_row["input_rows"] == 2
        assert earlier_row["in_scope_rows"] == 1
        assert earlier_row["duplicate_skipped_rows"] == 1
        assert earlier_row["failed_rows"] == 0
        assert earlier_row["error"] is None
        assert "duplicate/replaced" in earlier_row["warnings"][1]

        final_ticket_count = db.scalar(
            select(func.count(Ticket.id)).where(Ticket.project_id == project_id)
        )
        assert final_ticket_count == 3
    finally:
        cleanup_client(db, client_id)


def test_apply_mapping_multiple_sc_task_catalog_fields_and_filter_cache_stale() -> None:
    db, client_id, project_id = create_project_fixture()
    kb_column = (
        "cat_item.ref_sc_cat_item_content.kb_article."
        "ref_u_kb_template_global_communication.u_kb_kb_knowledge_base"
    )

    try:
        db.add(
            DashboardFilterCacheStatus(
                customer_id=client_id,
                project_id=project_id,
                dashboard_area="volumetrics",
                status="ready",
                is_stale=False,
            )
        )
        first_batch_id = add_ingested_raw_batch(
            db,
            project_id,
            batch_name="SC Catalog Multi First",
            ticket_type="SERVICE_CATALOG_TASK",
            rows=[
                {
                    "number": "SCTASK-CAT-MULTI-1",
                    "short_description": "Selected in-scope SC Task",
                    "assignment_group": "AMS Support",
                    "business_service": "Lifecycle Service",
                    "sys_created_on": "2026-06-01",
                    "cat_item.name": "  Laptop Access  ",
                    kb_column: "  End User KB  ",
                }
            ],
        )
        second_batch_id = add_ingested_raw_batch(
            db,
            project_id,
            batch_name="SC Catalog Multi Second",
            ticket_type="SERVICE_CATALOG_TASK",
            rows=[
                {
                    "number": "SCTASK-CAT-MULTI-2",
                    "short_description": "Selected out-of-scope SC Task",
                    "assignment_group": "External Support",
                    "business_service": "External Service",
                    "sys_created_on": "2026-06-02",
                    "cat_item.name": "  Mobile Device  ",
                    kb_column: "  Field Services KB  ",
                }
            ],
        )
        mapping = {
            "ticket_id": "number",
            "title": "short_description",
            "assignment_group": "assignment_group",
            "business_service": "business_service",
            "created_at": "sys_created_on",
            "catalog_item_name": "cat_item.name",
            "catalog_knowledge_base": kb_column,
        }

        with TestClient(app) as client:
            response = client.post(
                "/api/uploads/batches/apply-mapping-multiple",
                json={
                    "project_id": str(project_id),
                    "ticket_type": "SERVICE_CATALOG_TASK",
                    "upload_batch_ids": [str(first_batch_id), str(second_batch_id)],
                    "mapping": mapping,
                },
            )

        assert response.status_code == 200
        payload = response.json()
        assert payload["totals"]["total_files"] == 2
        assert payload["totals"]["applied"] == 2
        assert payload["totals"]["in_scope_rows"] == 1
        assert payload["totals"]["out_of_scope_rows"] == 1

        ticket = db.scalar(
            select(Ticket).where(Ticket.ticket_number == "SCTASK-CAT-MULTI-1")
        )
        out_of_scope_ticket = db.scalar(
            select(AssessmentOutOfScopeTicket).where(
                AssessmentOutOfScopeTicket.ticket_number == "SCTASK-CAT-MULTI-2"
            )
        )
        cache_status = db.scalar(
            select(DashboardFilterCacheStatus).where(
                DashboardFilterCacheStatus.project_id == project_id,
                DashboardFilterCacheStatus.dashboard_area == "volumetrics",
            )
        )

        assert ticket is not None
        assert ticket.catalog_item_name == "Laptop Access"
        assert ticket.catalog_knowledge_base == "End User KB"
        assert out_of_scope_ticket is not None
        assert out_of_scope_ticket.catalog_item_name == "Mobile Device"
        assert out_of_scope_ticket.catalog_knowledge_base == "Field Services KB"
        assert cache_status is not None
        assert cache_status.status == "stale"
        assert cache_status.is_stale is True
    finally:
        cleanup_client(db, client_id)


def test_uploaded_batch_starts_active_and_can_be_deleted_before_normalization() -> None:
    db, client_id, project_id = create_project_fixture()

    try:
        with TestClient(app) as client:
            batch_id, _ = upload_monthly_batch(client, project_id, "Delete Staging Batch")

            active_response = client.get(
                "/api/uploads/batches",
                params={"project_id": str(project_id), "view": "active"},
            )
            history_response = client.get(
                "/api/uploads/batches",
                params={"project_id": str(project_id), "view": "history"},
            )

            assert active_response.status_code == 200
            assert history_response.status_code == 200
            active_payload = active_response.json()
            assert active_payload[0]["id"] == batch_id
            assert active_payload[0]["status"] == "UPLOADED"
            assert batch_id not in batch_ids(history_response.json())

            delete_response = client.delete(f"/api/uploads/batches/{batch_id}")
            assert delete_response.status_code == 200
            assert delete_response.json()["status"] == "DELETED"

            active_after_delete = client.get(
                "/api/uploads/batches",
                params={"project_id": str(project_id), "view": "active"},
            )
            history_after_delete = client.get(
                "/api/uploads/batches",
                params={"project_id": str(project_id), "view": "history"},
            )
            all_after_delete = client.get(
                "/api/uploads/batches",
                params={"project_id": str(project_id), "view": "all"},
            )

            assert batch_id not in batch_ids(active_after_delete.json())
            assert batch_id not in batch_ids(history_after_delete.json())
            assert batch_id not in batch_ids(all_after_delete.json())

        deleted_batch = db.get(UploadBatch, UUID(batch_id))
        assert deleted_batch is not None
        assert deleted_batch.status == "DELETED"
        assert deleted_batch.deleted_at is not None
    finally:
        cleanup_client(db, client_id)


def test_ingested_and_normalized_batches_move_from_active_to_history() -> None:
    db, client_id, project_id = create_project_fixture()

    try:
        with TestClient(app) as client:
            batch_id, uploaded_file_id = upload_monthly_batch(
                client,
                project_id,
                "Normalize Lifecycle Batch",
            )

            ingest_response = client.post(f"/api/uploads/files/{uploaded_file_id}/ingest")
            assert ingest_response.status_code == 200

            active_response = client.get(
                "/api/uploads/batches",
                params={"project_id": str(project_id), "view": "active"},
            )
            active_payload = active_response.json()
            assert active_payload[0]["status"] == "INGESTED"
            assert active_payload[0]["raw_row_count"] == 1

        result = apply_mapping_to_batch(
            db,
            UUID(batch_id),
            {
                "ticket_id": "number",
                "title": "short_description",
                "assignment_group": "assignment_group",
                "business_service": "business_service",
                "created_at": "sys_created_on",
            },
        )
        assert result.status == "NORMALIZED"

        with TestClient(app) as client:
            active_after_normalize = client.get(
                "/api/uploads/batches",
                params={"project_id": str(project_id), "view": "active"},
            )
            history_after_normalize = client.get(
                "/api/uploads/batches",
                params={"project_id": str(project_id), "view": "history"},
            )

            history_payload = history_after_normalize.json()
            assert batch_id not in batch_ids(active_after_normalize.json())
            assert history_payload[0]["id"] == batch_id
            assert history_payload[0]["status"] == "NORMALIZED"
            assert history_payload[0]["normalized_ticket_count"] == 1

        ticket = db.scalar(select(Ticket).where(Ticket.upload_batch_id == UUID(batch_id)))
        assert ticket is not None
    finally:
        cleanup_client(db, client_id)


def test_listing_upload_batches_does_not_mutate_batch_status_timestamps() -> None:
    db, client_id, project_id = create_project_fixture()

    try:
        with TestClient(app) as client:
            batch_id, uploaded_file_id = upload_monthly_batch(
                client,
                project_id,
                "Read Only Status Batch",
            )
            ingest_response = client.post(f"/api/uploads/files/{uploaded_file_id}/ingest")
            assert ingest_response.status_code == 200

        batch = db.get(UploadBatch, UUID(batch_id))
        assert batch is not None
        original_status = batch.status
        original_updated_at = batch.updated_at

        with TestClient(app) as client:
            response = client.get(
                "/api/uploads/batches",
                params={"project_id": str(project_id), "view": "active"},
            )

        assert response.status_code == 200
        db.refresh(batch)
        assert batch.status == original_status
        assert batch.updated_at == original_updated_at
    finally:
        cleanup_client(db, client_id)


def test_delete_normalized_batch_is_blocked_and_archive_preserves_history() -> None:
    db, client_id, project_id = create_project_fixture()

    try:
        with TestClient(app) as client:
            batch_id, uploaded_file_id = upload_monthly_batch(
                client,
                project_id,
                "Archive Lifecycle Batch",
            )
            ingest_response = client.post(f"/api/uploads/files/{uploaded_file_id}/ingest")
            assert ingest_response.status_code == 200

        apply_mapping_to_batch(
            db,
            UUID(batch_id),
            {
                "ticket_id": "number",
                "title": "short_description",
                "assignment_group": "assignment_group",
                "business_service": "business_service",
                "created_at": "sys_created_on",
            },
        )

        with TestClient(app) as client:
            delete_response = client.delete(f"/api/uploads/batches/{batch_id}")
            assert delete_response.status_code == 409
            assert (
                delete_response.json()["detail"]
                == "This batch has already been normalized. Delete normalized ticket data first "
                "or archive it instead."
            )

            archive_response = client.post(f"/api/uploads/batches/{batch_id}/archive")
            assert archive_response.status_code == 200
            assert archive_response.json()["status"] == "ARCHIVED"

            history_response = client.get(
                "/api/uploads/batches",
                params={"project_id": str(project_id), "view": "history"},
            )
            assert batch_id in batch_ids(history_response.json())
    finally:
        cleanup_client(db, client_id)


def test_failed_normalization_keeps_batch_active() -> None:
    db, client_id, project_id = create_project_fixture()

    try:
        with TestClient(app) as client:
            batch_id, uploaded_file_id = upload_monthly_batch(
                client,
                project_id,
                "Failed Normalization Batch",
                file_body=(
                    b"number,short_description,assignment_group,business_service,"
                    b"sys_created_on\n"
                    b",Missing number,AMS Support,Lifecycle Service,2026-06-01\n"
                ),
            )
            ingest_response = client.post(f"/api/uploads/files/{uploaded_file_id}/ingest")
            assert ingest_response.status_code == 200

        result = apply_mapping_to_batch(
            db,
            UUID(batch_id),
            {
                "ticket_id": "number",
                "title": "short_description",
                "assignment_group": "assignment_group",
                "business_service": "business_service",
                "created_at": "sys_created_on",
            },
        )
        assert result.failed_row_count == 1
        assert result.status == "NORMALIZATION_FAILED"

        with TestClient(app) as client:
            active_response = client.get(
                "/api/uploads/batches",
                params={"project_id": str(project_id), "view": "active"},
            )
            history_response = client.get(
                "/api/uploads/batches",
                params={"project_id": str(project_id), "view": "history"},
            )

            assert batch_id in batch_ids(active_response.json())
            assert batch_id not in batch_ids(history_response.json())
    finally:
        cleanup_client(db, client_id)
