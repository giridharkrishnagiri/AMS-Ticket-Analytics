from __future__ import annotations

from datetime import UTC, datetime
from io import BytesIO
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from openpyxl import Workbook
from sqlalchemy import delete, event, func, select

from app.db.session import SessionLocal
from app.main import app
from app.models import (
    ApplicationInventoryItem,
    Client,
    Project,
    Ticket,
    UploadBatch,
    UploadedFile,
)
from app.services.application_inventory import update_application_inventory_active_users_from_file


def create_project():
    db = SessionLocal()
    suffix = uuid4().hex[:12]
    client = Client(name=f"Inventory Client {suffix}", code=f"INV-C-{suffix}")
    db.add(client)
    db.flush()

    project = Project(
        client_id=client.id,
        name=f"Inventory Project {suffix}",
        code=f"INV-P-{suffix}",
    )
    db.add(project)
    db.flush()

    upload_batch = UploadBatch(
        project_id=project.id,
        month_key="2026-06",
        batch_name=f"Inventory Batch {suffix}",
        status="NORMALIZED",
        file_count=1,
        total_size_bytes=1,
    )
    db.add(upload_batch)
    db.flush()

    uploaded_file = UploadedFile(
        upload_batch_id=upload_batch.id,
        project_id=project.id,
        ticket_type="INCIDENT",
        original_filename="inventory.csv",
        saved_filename="inventory.csv",
        storage_path="C:\\temp\\inventory.csv",
        size_bytes=1,
        status="NORMALIZED",
    )
    db.add(uploaded_file)
    db.flush()
    db.commit()
    return db, client.id, project.id, upload_batch.id, uploaded_file.id


def cleanup_client(db, client_id: UUID) -> None:
    db.rollback()
    db.execute(delete(Client).where(Client.id == client_id))
    db.commit()
    db.close()


def add_inventory_item(
    db,
    project_id: UUID,
    business_service: str,
    *,
    parent_application: str = "Claims Parent",
    assignment_group: str | None = "AMS Claims",
    application_owner: str = "App Owner",
    support_lead: str = "Support Lead",
    functional_track: str = "Claims",
    ams_owner: str = "AMS Owner",
    vendor: str = "Vendor A",
    row_number: int = 10,
    active: bool | None = True,
    active_users: int | None = None,
) -> ApplicationInventoryItem:
    item = ApplicationInventoryItem(
        project_id=project_id,
        application_number_apm=f"APM-{row_number}",
        parent_application_name=parent_application,
        assignment_group=assignment_group,
        assignment_group_owner="Group Owner",
        application_owner=application_owner,
        business_service_ci_name=business_service,
        support_lead=support_lead,
        functional_track=functional_track,
        ams_owner=ams_owner,
        supported_by_vendor=vendor,
        active=active,
        active_users=active_users,
        cmdb_payload={"Application family": "Claims"},
        source_filename="inventory.csv",
        source_row_number=row_number,
    )
    db.add(item)
    db.flush()
    return item


def add_ticket(
    db,
    project_id: UUID,
    batch_id: UUID,
    file_id: UUID,
    ticket_number: str,
    *,
    business_service: str | None = None,
    application: str | None = None,
    assignment_group: str | None = "AMS Claims",
    application_inventory_id: UUID | None = None,
    support_lead: str | None = None,
    payload_size: int = 0,
) -> None:
    db.add(
        Ticket(
            project_id=project_id,
            upload_batch_id=batch_id,
            uploaded_file_id=file_id,
            ticket_number=ticket_number,
            ticket_type="INCIDENT",
            month_key="2026-06",
            created_at=datetime(2026, 6, 1, tzinfo=UTC),
            short_description=f"{ticket_number} title",
            state="Closed",
            priority="P3",
            assignment_group=assignment_group,
            application=application,
            business_service=business_service,
            application_inventory_id=application_inventory_id,
            support_lead=support_lead,
            reopen_count=0,
            normalized_payload={"large": "x" * payload_size},
        )
    )


def test_csv_upload_preserves_extra_cmdb_payload_and_updates_duplicate() -> None:
    db, client_id, project_id, _batch_id, _file_id = create_project()
    try:
        csv_payload = "\n".join(
            [
                "Application Number (APM),Parent Business Application,Support group name,"
                "Support group's owner,Application Owner,Business Service CI Name,"
                "Support Lead (Managed by),Functional Track,AMS Owner,Supported By Vendor,"
                "Active,Active Users,Application family,Business criticality,Total USD$",
                " APM-1 , Parent App , IT-SAP-Claims , Group Owner , Owner One , "
                "Claims Service , Lead One , Claims , AMS Owner , Vendor A , true , "
                "100, Claims Family , High , #N/A",
                "APM-1,Parent App,IT-SAP-Claims,Group Owner,Owner Two,Claims Service,"
                "Lead Two,Claims,AMS Owner,Vendor A,true,250,Claims Family,#N/A,#N/A",
                "APM-2,Parent App,IT-SAP-Claims,Group Owner,Owner Missing,,Lead,Claims,"
                "AMS Owner,Vendor A,true,15,Family,Low,#N/A",
            ]
        )

        with TestClient(app) as client:
            response = client.post(
                "/api/application-inventory/upload",
                data={"project_id": str(project_id)},
                files={"file": ("inventory.csv", csv_payload.encode("utf-8"), "text/csv")},
            )

        assert response.status_code == 201
        payload = response.json()
        assert payload["total_rows"] == 3
        assert payload["inserted_count"] == 1
        assert payload["updated_count"] == 1
        assert payload["skipped_count"] == 1
        assert payload["distinct_business_service_count"] == 1
        assert payload["distinct_support_lead_count"] == 2
        assert payload["error_count"] == 1

        item = db.scalar(
            select(ApplicationInventoryItem).where(
                ApplicationInventoryItem.project_id == project_id
            )
        )
        assert item is not None
        assert item.application_owner == "Owner Two"
        assert item.assignment_group == "IT-SAP-Claims"
        assert item.sap_non_sap == "SAP"
        assert item.business_service_ci_name == "Claims Service"
        assert item.active is True
        assert item.active_users == 250
        assert item.cmdb_payload == {
            "Application family": "Claims Family",
            "Business criticality": None,
            "Total USD$": None,
        }
    finally:
        cleanup_client(db, client_id)


def test_xlsx_upload_detects_second_row_header() -> None:
    db, client_id, project_id, _batch_id, _file_id = create_project()
    try:
        workbook = Workbook()
        worksheet = workbook.active
        worksheet.title = "Group-App-BizService"
        worksheet.append([None, None, "helper"])
        worksheet.append(
            [
                "Application Number (APM)",
                "Parent Business Application",
                "Support group name",
                "Support group's owner",
                "Application Owner",
                "Business Service CI Name",
                "Support Lead (Managed by)",
                "Functional Track",
                "AMS Owner",
                "Supported By Vendor",
                "Active",
                "Active Users",
                "Application family",
            ]
        )
        worksheet.append(
            [
                "APM-3",
                "Parent Excel",
                "AMS Excel",
                "Owner Group",
                "Owner Excel",
                "Excel Service",
                "Lead Excel",
                "Excel Track",
                "AMS Excel Owner",
                "Vendor Excel",
                "Yes",
                1234,
                "Excel Family",
            ]
        )
        workbook_bytes = BytesIO()
        workbook.save(workbook_bytes)

        with TestClient(app) as client:
            response = client.post(
                "/api/application-inventory/upload",
                data={"project_id": str(project_id)},
                files={
                    "file": (
                        "inventory.xlsx",
                        workbook_bytes.getvalue(),
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )
                },
            )

        assert response.status_code == 201
        payload = response.json()
        assert payload["inserted_count"] == 1
        assert payload["distinct_business_service_count"] == 1

        item = db.scalar(
            select(ApplicationInventoryItem).where(
                ApplicationInventoryItem.business_service_ci_name == "Excel Service"
            )
        )
        assert item is not None
        assert item.source_row_number == 3
        assert item.active_users == 1234
        assert item.cmdb_payload == {"Application family": "Excel Family"}
    finally:
        cleanup_client(db, client_id)


def test_focused_active_users_update_only_changes_active_users(tmp_path) -> None:
    db, client_id, project_id, _batch_id, _file_id = create_project()
    try:
        item = add_inventory_item(
            db,
            project_id,
            "Claims Service",
            parent_application="Claims Parent",
            assignment_group="AMS Claims",
            application_owner="Original Owner",
            active_users=None,
            row_number=88,
        )
        add_inventory_item(
            db,
            project_id,
            "Untouched Service",
            parent_application="Other Parent",
            assignment_group="Other Group",
            active_users=7,
            row_number=89,
        )
        db.commit()

        workbook = Workbook()
        worksheet = workbook.active
        worksheet.title = "Group-App-BizService"
        worksheet.append(["helper"])
        worksheet.append(
            [
                "Parent Business Application",
                "Support group name",
                "Business Service CI Name",
                "Active Users",
                "Application Owner",
            ]
        )
        worksheet.append(
            [
                "Claims Parent",
                "AMS Claims",
                "Claims Service",
                "3,210",
                "Should Not Be Used",
            ]
        )
        worksheet.append(["Missing Parent", "Missing Group", "Missing Service", 99, "Ignored"])
        worksheet.append(["Claims Parent", "AMS Claims", "Claims Service", "bad", "Ignored"])

        workbook_path = tmp_path / "inventory-active-users.xlsx"
        workbook.save(workbook_path)

        result = update_application_inventory_active_users_from_file(
            db,
            project_id,
            workbook_path,
        )

        assert result.total_rows == 3
        assert result.matched_count == 1
        assert result.updated_count == 1
        assert result.unmatched_count == 1
        assert result.invalid_count == 1
        assert result.skipped_count == 1

        db.refresh(item)
        assert item.active_users == 3210
        assert item.application_owner == "Original Owner"
        assert item.cmdb_payload == {"Application family": "Claims"}
        assert item.source_row_number == 88

        item_count = db.scalar(
            select(func.count(ApplicationInventoryItem.id))
            .where(ApplicationInventoryItem.project_id == project_id)
        )
        assert item_count == 2
    finally:
        cleanup_client(db, client_id)


def test_inventory_enrichment_priority_replace_and_dashboard_filters() -> None:
    db, client_id, project_id, batch_id, file_id = create_project()
    try:
        preserved_item = add_inventory_item(
            db,
            project_id,
            "Preserved Service",
            support_lead="Preserved Lead",
            row_number=1,
        )
        add_inventory_item(
            db,
            project_id,
            "Claims Service",
            assignment_group="AMS Claims",
            support_lead="Claims Lead One",
            row_number=10,
        )
        preferred_item = add_inventory_item(
            db,
            project_id,
            "Claims Service",
            assignment_group="AMS Priority",
            support_lead="Claims Lead Two",
            row_number=20,
        )
        add_inventory_item(
            db,
            project_id,
            "Fallback Service",
            assignment_group=None,
            support_lead="Fallback Lead",
            functional_track="Requests",
            row_number=30,
        )
        db.flush()

        add_ticket(
            db,
            project_id,
            batch_id,
            file_id,
            "INC-BUSINESS",
            business_service=" claims service ",
            assignment_group="AMS Priority",
            payload_size=200_000,
        )
        add_ticket(
            db,
            project_id,
            batch_id,
            file_id,
            "INC-FALLBACK",
            application="Fallback Service",
            business_service=None,
            assignment_group="Other",
        )
        add_ticket(
            db,
            project_id,
            batch_id,
            file_id,
            "INC-PRESERVED",
            business_service="Claims Service",
            application_inventory_id=preserved_item.id,
            support_lead="Do Not Replace",
        )
        add_ticket(
            db,
            project_id,
            batch_id,
            file_id,
            "INC-UNMATCHED",
            business_service="Missing Service",
            application="Missing App",
        )
        db.commit()

        captured_sql: list[str] = []

        def capture_sql(_conn, _cursor, statement, _parameters, _context, _executemany):
            captured_sql.append(str(statement).lower())

        event.listen(db.bind, "before_cursor_execute", capture_sql)
        try:
            with TestClient(app) as client:
                preserve_response = client.post(
                    "/api/application-inventory/enrich-tickets",
                    json={"project_id": str(project_id), "replace_existing": False},
                )
        finally:
            event.remove(db.bind, "before_cursor_execute", capture_sql)

        assert preserve_response.status_code == 200
        payload = preserve_response.json()
        assert payload["total_tickets"] == 4
        assert payload["updated_tickets"] == 2
        assert payload["matched_tickets"] == 3
        assert payload["matched_by_business_service_count"] == 1
        assert payload["matched_by_application_count"] == 1
        assert not any(
            "select" in statement
            and "normalized_payload" in statement.split("from", maxsplit=1)[0]
            for statement in captured_sql
        )

        business_ticket = db.scalar(select(Ticket).where(Ticket.ticket_number == "INC-BUSINESS"))
        fallback_ticket = db.scalar(select(Ticket).where(Ticket.ticket_number == "INC-FALLBACK"))
        preserved_ticket = db.scalar(select(Ticket).where(Ticket.ticket_number == "INC-PRESERVED"))
        assert business_ticket is not None
        assert fallback_ticket is not None
        assert preserved_ticket is not None
        assert business_ticket.application_inventory_id == preferred_item.id
        assert business_ticket.support_lead == "Claims Lead Two"
        assert fallback_ticket.business_service_ci_name == "Fallback Service"
        assert preserved_ticket.support_lead == "Do Not Replace"

        with TestClient(app) as client:
            replace_response = client.post(
                "/api/application-inventory/enrich-tickets",
                json={"project_id": str(project_id), "replace_existing": True},
            )
            values_response = client.get(
                "/api/dashboard/filter-values",
                params={"project_id": str(project_id)},
            )
            filtered_response = client.get(
                "/api/dashboard/trends/reopen-count",
                params={
                    "project_id": str(project_id),
                    "functional_track": "Claims",
                    "start_date": "2026-06-01",
                    "end_date": "2026-06-30",
                },
            )

        assert replace_response.status_code == 200
        assert replace_response.json()["updated_tickets"] == 3
        db.refresh(preserved_ticket)
        assert preserved_ticket.support_lead == "Claims Lead One"
        assert values_response.status_code == 200
        filter_values = values_response.json()
        assert "Claims" in filter_values["functional_tracks"]
        assert "AMS Owner" in filter_values["ams_owners"]
        assert "Vendor A" in filter_values["supported_by_vendors"]
        assert "Claims Lead Two" in filter_values["support_leads"]
        assert "App Owner" in filter_values["application_owners"]
        assert "Claims Service" in filter_values["business_service_ci_names"]
        assert "Claims Parent" in filter_values["parent_application_names"]
        assert filtered_response.status_code == 200
        assert filtered_response.json()[0]["total_tickets"] == 2
    finally:
        cleanup_client(db, client_id)


def test_unmatched_business_services_returns_compact_coverage() -> None:
    db, client_id, project_id, batch_id, file_id = create_project()
    try:
        add_inventory_item(db, project_id, "Matched Service")
        add_ticket(
            db,
            project_id,
            batch_id,
            file_id,
            "INC-MATCHED",
            business_service="Matched Service",
            assignment_group="AMS A",
        )
        add_ticket(
            db,
            project_id,
            batch_id,
            file_id,
            "INC-UNMATCHED-1",
            business_service="Unmatched Service",
            assignment_group="AMS B",
        )
        add_ticket(
            db,
            project_id,
            batch_id,
            file_id,
            "INC-UNMATCHED-2",
            business_service="Unmatched Service",
            assignment_group="AMS C",
        )
        db.commit()

        with TestClient(app) as client:
            response = client.get(
                "/api/application-inventory/unmatched-business-services",
                params={"project_id": str(project_id)},
            )

        assert response.status_code == 200
        payload = response.json()
        assert payload["distinct_ticket_business_service_count"] == 2
        assert payload["distinct_inventory_business_service_count"] == 1
        assert payload["matched_business_service_count"] == 1
        assert payload["unmatched_business_service_count"] == 1
        assert payload["business_service_coverage_pct"] == 50.0
        assert payload["rows"][0]["business_service"] == "Unmatched Service"
        assert payload["rows"][0]["ticket_count"] == 2
        assert payload["rows"][0]["assignment_group_count"] == 2
    finally:
        cleanup_client(db, client_id)


def test_application_inventory_list_filter_values_and_projects_endpoint() -> None:
    db, client_id, project_id, _batch_id, _file_id = create_project()
    try:
        add_inventory_item(
            db,
            project_id,
            "Listed Service",
            parent_application="Listed Parent",
            support_lead="Listed Lead",
            functional_track="Listed Track",
        )
        db.commit()

        with TestClient(app) as client:
            list_response = client.get(
                "/api/application-inventory",
                params={"project_id": str(project_id)},
            )
            filter_response = client.get(
                "/api/application-inventory/filter-values",
                params={"project_id": str(project_id)},
            )
            projects_response = client.get("/api/projects")

        assert list_response.status_code == 200
        assert list_response.json()[0]["business_service_ci_name"] == "Listed Service"
        assert filter_response.status_code == 200
        assert "Listed Lead" in filter_response.json()["support_leads"]
        assert projects_response.status_code == 200
        project_options = projects_response.json()
        assert any(project["id"] == str(project_id) for project in project_options)
        assert any("Inventory Client" in project["customer_name"] for project in project_options)
    finally:
        cleanup_client(db, client_id)
