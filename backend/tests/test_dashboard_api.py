import inspect
import json
import re
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.db.session import SessionLocal
from app.main import app
from app.models import (
    ApplicationDimension,
    ApplicationInventoryItem,
    AssessmentOutOfScopeTicket,
    Client,
    IncidentSlaRow,
    Project,
    Ticket,
    TicketRawRow,
    UploadBatch,
    UploadedFile,
)
from app.services import dashboard as dashboard_service
from app.services.batch_classification import derive_is_batch_related
from app.services.sap_classification import derive_sap_non_sap


def dt(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=UTC)


def create_dashboard_project():
    db = SessionLocal()
    suffix = uuid4().hex[:12]
    client = Client(name=f"Dashboard Client {suffix}", code=f"DC-{suffix}")
    db.add(client)
    db.flush()

    project = Project(
        client_id=client.id,
        name=f"Dashboard Project {suffix}",
        code=f"DP-{suffix}",
    )
    db.add(project)
    db.flush()

    upload_batch = UploadBatch(
        project_id=project.id,
        month_key="2026-01",
        batch_name=f"Dashboard Batch {suffix}",
        status="COMPLETED",
        file_count=1,
        total_size_bytes=1,
    )
    db.add(upload_batch)
    db.flush()

    uploaded_file = UploadedFile(
        upload_batch_id=upload_batch.id,
        project_id=project.id,
        ticket_type="INCIDENT",
        original_filename="dashboard.csv",
        saved_filename="dashboard.csv",
        storage_path="C:\\temp\\dashboard.csv",
        size_bytes=1,
        status="INGESTED",
    )
    db.add(uploaded_file)
    db.flush()

    app_dimension = ApplicationDimension(
        project_id=project.id,
        customer_name="Customer A",
        tower_name="Tower A",
        cluster_name="Cluster A",
        application_group_name="Group A",
        application_name="Payroll",
        application_aliases=["Payroll"],
        is_active=True,
    )
    db.add(app_dimension)
    db.flush()
    db.commit()
    return db, client.id, project.id, upload_batch.id, uploaded_file.id, app_dimension.id


def cleanup_client(db, client_id: UUID) -> None:
    db.rollback()
    db.execute(delete(Client).where(Client.id == client_id))
    db.commit()
    db.close()


def add_ticket(
    db,
    project_id: UUID,
    upload_batch_id: UUID,
    uploaded_file_id: UUID,
    number: str,
    ticket_type: str,
    created_at: datetime | None,
    state: str | None = "Open",
    resolved_at: datetime | None = None,
    closed_at: datetime | None = None,
    priority: str | None = "P1",
    assignment_group: str | None = "AMS",
    application: str | None = "Payroll",
    application_dimension_id: UUID | None = None,
    sla_breached: bool | None = None,
    raw_payload: dict[str, object] | None = None,
    reopen_count: int = 0,
    reassignment_count: int | None = None,
    business_duration_seconds: int | None = None,
    created_by: str | None = None,
    opened_by: str | None = None,
    is_system_created: bool | None = None,
    is_technical: bool | None = None,
    technical_functional_type: str | None = None,
    sap_non_sap: str | None = None,
    short_description: str | None = None,
    business_service_ci_name: str | None = None,
    architecture_type: str | None = None,
    install_type: str | None = None,
) -> Ticket:
    resolved_sap_non_sap = (
        sap_non_sap if sap_non_sap is not None else derive_sap_non_sap(assignment_group)
    )
    resolved_short_description = short_description or f"{number} title"
    ticket = Ticket(
        project_id=project_id,
        upload_batch_id=upload_batch_id,
        uploaded_file_id=uploaded_file_id,
        application_dimension_id=application_dimension_id,
        customer_name="Customer A" if application_dimension_id else None,
        tower_name="Tower A" if application_dimension_id else None,
        cluster_name="Cluster A" if application_dimension_id else None,
        application_group_name="Group A" if application_dimension_id else None,
        application_name="Payroll" if application_dimension_id else None,
        ticket_number=number,
        ticket_type=ticket_type,
        month_key="2026-01",
        created_at=created_at,
        resolved_at=resolved_at,
        closed_at=closed_at,
        short_description=resolved_short_description,
        state=state,
        priority=priority,
        assignment_group=assignment_group,
        sap_non_sap=resolved_sap_non_sap,
        architecture_type=architecture_type,
        install_type=install_type,
        application=application,
        business_service_ci_name=business_service_ci_name,
        sla_breached=sla_breached,
        is_batch_related=derive_is_batch_related(ticket_type, resolved_short_description),
        reopen_count=reopen_count,
        reassignment_count=reassignment_count,
        business_duration_seconds=business_duration_seconds,
        created_by=created_by,
        opened_by=opened_by,
        is_system_created=is_system_created,
        is_technical=is_technical,
        technical_functional_type=technical_functional_type,
        normalized_payload={"raw_payload_json": raw_payload or {}},
    )
    db.add(ticket)
    return ticket


def add_inventory_item(
    db,
    project_id: UUID,
    business_service_ci_name: str,
    *,
    supported_by_vendor: str,
    functional_track: str,
    ams_owner: str,
    assignment_group: str,
    application_owner: str,
    parent_application_name: str,
    active: bool | None = True,
    active_users: int | None = None,
    cmdb_payload: dict[str, object] | None = None,
) -> ApplicationInventoryItem:
    item = ApplicationInventoryItem(
        project_id=project_id,
        business_service_ci_name=business_service_ci_name,
        supported_by_vendor=supported_by_vendor,
        functional_track=functional_track,
        ams_owner=ams_owner,
        assignment_group=assignment_group,
        sap_non_sap=derive_sap_non_sap(assignment_group),
        application_owner=application_owner,
        parent_application_name=parent_application_name,
        active=active,
        active_users=active_users,
        cmdb_payload=cmdb_payload,
        source_filename="overview-inventory.csv",
    )
    db.add(item)
    return item


def add_raw_row(
    db,
    project_id: UUID,
    upload_batch_id: UUID,
    uploaded_file_id: UUID,
    ticket_type: str,
    row_number: int,
) -> TicketRawRow:
    raw_row = TicketRawRow(
        project_id=project_id,
        upload_batch_id=upload_batch_id,
        uploaded_file_id=uploaded_file_id,
        ticket_type=ticket_type,
        row_number=row_number,
        source_filename="overview.csv",
        raw_ticket_number=f"RAW-{row_number}",
        raw_data={"ticket_number": f"RAW-{row_number}"},
    )
    db.add(raw_row)
    return raw_row


def test_dashboard_overview_uses_inventory_counts_and_in_scope_ticket_counts() -> None:
    db, client_id, project_id, batch_id, file_id, _ = create_dashboard_project()
    try:
        add_inventory_item(
            db,
            project_id,
            "Inventory Service A",
            supported_by_vendor="Inventory Vendor A",
            functional_track="Finance",
            ams_owner="Owner A",
            assignment_group="Assignment A",
            application_owner="App Owner A",
            parent_application_name="Parent One",
            cmdb_payload={"Business criticality": "Very Critical"},
        )
        add_inventory_item(
            db,
            project_id,
            "Inventory Service B",
            supported_by_vendor="Inventory Vendor B",
            functional_track="Finance",
            ams_owner="Owner B",
            assignment_group="Assignment B",
            application_owner="App Owner B",
            parent_application_name="Parent One",
            cmdb_payload={"Business criticality": "Critical"},
        )
        add_inventory_item(
            db,
            project_id,
            "Inventory Service C",
            supported_by_vendor="Inventory Vendor C",
            functional_track="HR",
            ams_owner="Owner B",
            assignment_group="Assignment C",
            application_owner="App Owner B",
            parent_application_name="Parent Two",
            cmdb_payload={"Business criticality": "Low"},
        )
        add_inventory_item(
            db,
            project_id,
            "Inactive Inventory Service",
            supported_by_vendor="Inactive Vendor",
            functional_track="Inactive Track",
            ams_owner="Inactive Owner",
            assignment_group="Inactive Assignment",
            application_owner="Inactive App Owner",
            parent_application_name="Inactive Parent",
            active=False,
        )

        incident = add_ticket(
            db,
            project_id,
            batch_id,
            file_id,
            "INC-OVERVIEW",
            "INCIDENT",
            dt("2026-01-01T00:00:00"),
            state="Resolved",
            resolved_at=dt("2026-01-01T00:00:00"),
        )
        incident.business_service_ci_name = "Ticket Service Only"
        incident.supported_by_vendor = "Ticket Supported Vendor"
        incident.derived_vendor = "Ticket Derived Vendor"
        incident.vendor = "Ticket Vendor"

        sc_task = add_ticket(
            db,
            project_id,
            batch_id,
            file_id,
            "SCTASK-OVERVIEW",
            "SERVICE_CATALOG_TASK",
            dt("2026-01-02T00:00:00"),
            state="Closed",
            closed_at=dt("2026-01-31T00:00:00"),
        )
        sc_task.business_service_ci_name = "Another Ticket Service"
        sc_task.supported_by_vendor = "Another Ticket Vendor"

        add_raw_row(db, project_id, batch_id, file_id, "INCIDENT", 1)
        add_raw_row(db, project_id, batch_id, file_id, "INCIDENT", 2)
        add_raw_row(db, project_id, batch_id, file_id, "SERVICE_CATALOG_TASK", 3)
        db.add(
            IncidentSlaRow(
                project_id=project_id,
                uploaded_file_name="sla.csv",
                source_row_number=1,
                inc_number="INC-OVERVIEW",
                taskslatable_sla_name="Response SLA",
                taskslatable_sla_target="Response",
            ),
        )
        db.add(
            IncidentSlaRow(
                project_id=project_id,
                uploaded_file_name="sla.csv",
                source_row_number=2,
                inc_number="INC-OVERVIEW",
                taskslatable_sla_name="Resolution SLA",
                taskslatable_sla_target="Resolution",
            ),
        )

        db.add(
            AssessmentOutOfScopeTicket(
                project_id=project_id,
                upload_batch_id=batch_id,
                ticket_number="OOS-OVERVIEW",
                ticket_type="INCIDENT",
                created_at=dt("2026-01-02T00:00:00"),
                resolved_at=dt("2026-01-04T00:00:00"),
                out_of_scope_reason="assignment_group_not_in_application_inventory",
            ),
        )
        db.commit()

        with TestClient(app) as client:
            response = client.get(
                "/api/dashboard/overview",
                params={"project_id": str(project_id)},
            )

        assert response.status_code == 200
        payload = response.json()
        assert payload["project_id"] == str(project_id)
        assert payload["application_inventory"] == {
            "total_applications": 3,
            "functional_track_count": 2,
            "ams_owner_count": 2,
            "supported_vendor_count": 3,
            "assignment_group_count": 3,
            "application_owner_count": 2,
            "very_critical_application_count": 1,
            "critical_application_count": 1,
        }
        assert payload["ingested_volume"] == {
            "total_rows": 5,
            "incident_rows": 2,
            "sc_task_rows": 1,
            "incident_sla_rows": 2,
        }
        assert payload["tickets"]["total_in_scope_tickets"] == 2
        assert payload["tickets"]["incident_count"] == 1
        assert payload["tickets"]["sc_task_count"] == 1
        assert payload["tickets"]["completion_date_min"].startswith("2026-01-01")
        assert payload["tickets"]["completion_date_max"].startswith("2026-01-31")
        assert payload["tickets"]["applications_80pct_monthly_volume_count"] == 2
        assert "response_sla_adherence_pct" not in str(payload)
        assert "resolution_sla_adherence_pct" not in str(payload)
    finally:
        cleanup_client(db, client_id)


def test_dashboard_applications_tab_apis_use_application_inventory_only() -> None:
    db, client_id, project_id, _, _, _ = create_dashboard_project()
    try:
        add_inventory_item(
            db,
            project_id,
            "Service A",
            supported_by_vendor="Vendor A",
            functional_track="Data & Analytics",
            ams_owner="Seshu Avala",
            assignment_group="IT-SAP-Group A",
            application_owner="App Owner A",
            parent_application_name="Parent A",
            active_users=1200,
            cmdb_payload={
                "Application family": "Family A",
                "Business process": "Process A",
                "Application category": "Category A",
                "Organization Unit Level 1": "Org 1",
                "Organization Unit Level 2": "Org 2",
                "Organization Unit Level 3": "Org 3",
                "Application type": "Business",
                "Architecture type": "Cloud",
                "Business Capabilities": "Capability A",
                "Business Reason for Maintain Applications": "Regulatory",
                "Business Units": "Unit A",
                "Business criticality": "Very Critical",
                "Business owner": "Biz Owner A",
                "Company": "Company A",
                "Install Status": "Installed",
                "Install type": "Production",
                "Life Cycle Stage": "Active",
                "Life Cycle Stage Status": "In Production",
                "Operating System": "Windows",
                "SOX Audited - ever": "Yes",
                "SOX Scope": "In Scope",
                "Strategic": "Yes",
            },
        )
        add_inventory_item(
            db,
            project_id,
            "Service B",
            supported_by_vendor="",
            functional_track="Data & Analytics",
            ams_owner="Seshu Avala",
            assignment_group="IT-NSA-Group B",
            application_owner="App Owner B",
            parent_application_name="Parent A",
            active_users=0,
            cmdb_payload={
                "Application type": "Technical",
                "Architecture type": "On Premise",
                "Business criticality": "Critical",
                "Install Status": "Installed",
                "Install type": "Production",
                "Life Cycle Stage": "Active",
                "Life Cycle Stage Status": "In Production",
                "Operating System": "Linux",
                "SOX Scope": "Out of Scope",
                "Strategic": "No",
            },
        )
        add_inventory_item(
            db,
            project_id,
            "Service C",
            supported_by_vendor="Vendor C",
            functional_track="Run",
            ams_owner="Another Owner",
            assignment_group="Group C",
            application_owner="App Owner C",
            parent_application_name="Parent B",
            active_users=600,
            cmdb_payload={
                "Application type": "Business",
                "Architecture type": "Cloud",
                "Business criticality": "Low",
                "Install Status": "Retired",
                "Install type": "Non Production",
                "Life Cycle Stage": "Retired",
                "Life Cycle Stage Status": "Retired",
                "Operating System": "Linux",
                "SOX Scope": "In Scope",
                "Strategic": "Yes",
            },
        )
        db.commit()

        request_body = {
            "project_id": str(project_id),
            "filters": {},
            "sort": {"column": "business_service_ci_name", "direction": "desc"},
            "limit": 1,
            "offset": 0,
        }

        with TestClient(app) as client:
            filter_response = client.get(
                "/api/dashboard/applications/filter-values",
                params={"project_id": str(project_id)},
            )
            filter_count_response = client.post(
                "/api/dashboard/applications/filter-values",
                json={"project_id": str(project_id), "filters": {}},
            )
            filtered_filter_count_response = client.post(
                "/api/dashboard/applications/filter-values",
                json={
                    "project_id": str(project_id),
                    "filters": {"supported_by_vendor": ["Vendor C"]},
                },
            )
            retained_filter_count_response = client.post(
                "/api/dashboard/applications/filter-values",
                json={
                    "project_id": str(project_id),
                    "filters": {
                        "supported_by_vendor": ["Vendor C"],
                        "parent_application_name": ["Parent A"],
                    },
                },
            )
            summary_response = client.post("/api/dashboard/applications/summary", json=request_body)
            list_response = client.post("/api/dashboard/applications/list", json=request_body)
            blank_vendor_response = client.post(
                "/api/dashboard/applications/list",
                json={
                    **request_body,
                    "filters": {"supported_by_vendor": ["(blank)"]},
                    "limit": 10,
                },
            )
            sap_filtered_response = client.post(
                "/api/dashboard/applications/list",
                json={
                    **request_body,
                    "filters": {"sap_non_sap": ["SAP"]},
                    "limit": 10,
                },
            )
            filtered_summary_response = client.post(
                "/api/dashboard/applications/summary",
                json={
                    **request_body,
                    "filters": {
                        "functional_track_ams_owner": ["Data & Analytics - Seshu Avala"],
                        "parent_application_name": ["Parent A"],
                    },
                },
            )
            chart_response = client.post("/api/dashboard/applications/charts", json=request_body)
            top_active_users_response = client.post(
                "/api/dashboard/applications/top-active-users",
                json={**request_body, "top_n": 10},
            )
            filtered_top_active_users_response = client.post(
                "/api/dashboard/applications/top-active-users",
                json={**request_body, "filters": {"sap_non_sap": ["SAP"]}, "top_n": 10},
            )
            lifecycle_filtered_chart_response = client.post(
                "/api/dashboard/applications/charts",
                json={
                    **request_body,
                    "filters": {"lifecycle_status_stage": ["Active - In Production"]},
                },
            )
            bad_sort_response = client.post(
                "/api/dashboard/applications/list",
                json={
                    **request_body,
                    "sort": {"column": "cmdb_payload", "direction": "asc"},
                },
            )

        assert filter_response.status_code == 200
        filter_payload = filter_response.json()
        assert [row["label"] for row in filter_payload["functional_track_ams_owner"]] == [
            "Data & Analytics - Seshu Avala",
            "Run - Another Owner",
        ]
        assert [row["label"] for row in filter_payload["assignment_group_owner"]] == [
            "Group C - (blank)",
            "IT-NSA-Group B - (blank)",
            "IT-SAP-Group A - (blank)",
        ]
        assert filter_payload["sap_non_sap"] == ["(blank)", "Non-SAP", "SAP"]
        assert "(blank)" in filter_payload["supported_by_vendor"]
        assert filter_payload["lifecycle_status_stage"] == [
            {
                "label": "Active - In Production",
                "left_value": "Active",
                "right_value": "In Production",
            },
            {
                "label": "Retired - Retired",
                "left_value": "Retired",
                "right_value": "Retired",
            },
        ]
        assert filter_count_response.status_code == 200
        filter_count_payload = filter_count_response.json()
        assert filter_count_payload["functional_track_ams_owner"] == [
            {
                "label": "Data & Analytics - Seshu Avala",
                "left_value": "Data & Analytics",
                "right_value": "Seshu Avala",
                "count": 2,
            },
            {
                "label": "Run - Another Owner",
                "left_value": "Run",
                "right_value": "Another Owner",
                "count": 1,
            },
        ]
        assert filter_count_payload["supported_by_vendor"] == [
            {"label": "(blank)", "value": "(blank)", "count": 1},
            {"label": "Vendor A", "value": "Vendor A", "count": 1},
            {"label": "Vendor C", "value": "Vendor C", "count": 1},
        ]
        assert filter_count_payload["sap_non_sap"] == [
            {"label": "(blank)", "value": "(blank)", "count": 1},
            {"label": "Non-SAP", "value": "Non-SAP", "count": 1},
            {"label": "SAP", "value": "SAP", "count": 1},
        ]
        assert filtered_filter_count_response.status_code == 200
        filtered_filter_counts = filtered_filter_count_response.json()
        assert filtered_filter_counts["parent_application_name"] == [
            {"label": "Parent B", "value": "Parent B", "count": 1},
        ]
        assert filtered_filter_counts["supported_by_vendor"] == [
            {"label": "(blank)", "value": "(blank)", "count": 1},
            {"label": "Vendor A", "value": "Vendor A", "count": 1},
            {"label": "Vendor C", "value": "Vendor C", "count": 1},
        ]
        assert retained_filter_count_response.status_code == 200
        retained_parent_values = retained_filter_count_response.json()["parent_application_name"]
        assert retained_parent_values == [
            {"label": "Parent A", "value": "Parent A", "count": 0},
            {"label": "Parent B", "value": "Parent B", "count": 1},
        ]

        assert summary_response.status_code == 200
        assert summary_response.json() == {
            "applications": 3,
            "functional_groups": 2,
            "assignment_groups": 3,
            "parent_business_apps": 2,
            "business_applications": 2,
            "technical_applications": 1,
            "very_critical_applications": 1,
            "critical_applications": 1,
            "show_functional_groups": True,
            "show_assignment_groups": True,
            "show_parent_business_apps": True,
        }

        assert filtered_summary_response.status_code == 200
        filtered_summary = filtered_summary_response.json()
        assert filtered_summary["applications"] == 2
        assert filtered_summary["show_functional_groups"] is False
        assert filtered_summary["show_parent_business_apps"] is False

        assert list_response.status_code == 200
        list_payload = list_response.json()
        assert list_payload["total"] == 3
        assert len(list_payload["rows"]) == 1
        assert list_payload["rows"][0]["business_service_ci_name"] == "Service C"
        assert list_payload["rows"][0]["sap_non_sap"] == "(blank)"
        assert "cmdb_payload" not in list_payload["rows"][0]
        assert list_payload["rows"][0]["app_type"] == "Business"
        assert "active_users" in list_payload["rows"][0]

        assert blank_vendor_response.status_code == 200
        blank_vendor_rows = blank_vendor_response.json()["rows"]
        assert [row["business_service_ci_name"] for row in blank_vendor_rows] == ["Service B"]

        assert sap_filtered_response.status_code == 200
        sap_rows = sap_filtered_response.json()["rows"]
        assert [row["business_service_ci_name"] for row in sap_rows] == ["Service A"]
        assert sap_rows[0]["active_users"] == 1200

        assert chart_response.status_code == 200
        chart_payload = chart_response.json()
        assert "operating_system" not in chart_payload
        assert "sox_scope" not in chart_payload
        assert chart_payload["architecture_type"] == [
            {"label": "Cloud", "count": 2},
            {"label": "On Premise", "count": 1},
        ]
        assert chart_payload["install_type"] == [
            {"label": "Production", "count": 2},
            {"label": "Non Production", "count": 1},
        ]
        assert chart_payload["strategic"] == [
            {"label": "Yes", "count": 2},
            {"label": "No", "count": 1},
        ]
        assert top_active_users_response.status_code == 200
        top_active_payload = top_active_users_response.json()
        assert top_active_payload["top_n"] == 10
        assert top_active_payload["duplicate_parent_active_user_count"] == 0
        assert top_active_payload["points"] == [
            {
                "application_name": "Parent A",
                "parent_application_name": "Parent A",
                "active_users": 1200,
            },
            {
                "application_name": "Parent B",
                "parent_application_name": "Parent B",
                "active_users": 600,
            },
        ]
        assert filtered_top_active_users_response.status_code == 200
        assert filtered_top_active_users_response.json()["points"] == [
            {
                "application_name": "Parent A",
                "parent_application_name": "Parent A",
                "active_users": 1200,
            },
        ]
        assert lifecycle_filtered_chart_response.status_code == 200
        assert lifecycle_filtered_chart_response.json()["lifecycle_stage"] == []
        assert bad_sort_response.status_code == 400
    finally:
        cleanup_client(db, client_id)


def test_dashboard_top_active_users_groups_by_parent_business_application() -> None:
    db, client_id, project_id, _, _, _ = create_dashboard_project()
    try:
        add_inventory_item(
            db,
            project_id,
            "Service A1",
            supported_by_vendor="Vendor A",
            functional_track="Data",
            ams_owner="Owner A",
            assignment_group="IT-SAP-A",
            application_owner="App Owner A",
            parent_application_name="Parent A",
            active_users=1000,
        )
        add_inventory_item(
            db,
            project_id,
            "Service A2 Duplicate Pair",
            supported_by_vendor="Vendor A",
            functional_track="Data",
            ams_owner="Owner A",
            assignment_group="IT-SAP-A",
            application_owner="App Owner A",
            parent_application_name="Parent A",
            active_users=1000,
        )
        add_inventory_item(
            db,
            project_id,
            "Service A3 Lower Users",
            supported_by_vendor="Vendor A",
            functional_track="Data",
            ams_owner="Owner A",
            assignment_group="IT-SAP-A",
            application_owner="App Owner A",
            parent_application_name="Parent A",
            active_users=700,
        )
        add_inventory_item(
            db,
            project_id,
            "Service B",
            supported_by_vendor="Vendor B",
            functional_track="Run",
            ams_owner="Owner B",
            assignment_group="IT-NSA-B",
            application_owner="App Owner B",
            parent_application_name="Parent B",
            active_users=800,
        )
        add_inventory_item(
            db,
            project_id,
            "Service C Inactive",
            supported_by_vendor="Vendor C",
            functional_track="Run",
            ams_owner="Owner C",
            assignment_group="IT-NSA-C",
            application_owner="App Owner C",
            parent_application_name="Parent C",
            active=False,
            active_users=2000,
        )
        db.commit()

        request_body = {
            "project_id": str(project_id),
            "filters": {},
            "sort": {"column": "business_service_ci_name", "direction": "asc"},
            "top_n": 20,
        }

        with TestClient(app) as client:
            response = client.post(
                "/api/dashboard/applications/top-active-users",
                json=request_body,
            )
            filtered_response = client.post(
                "/api/dashboard/applications/top-active-users",
                json={
                    **request_body,
                    "filters": {"functional_track_ams_owner": ["Data - Owner A"]},
                    "top_n": 10,
                },
            )

        assert response.status_code == 200
        payload = response.json()
        assert payload["top_n"] == 20
        assert payload["duplicate_parent_active_user_count"] == 1
        assert payload["points"] == [
            {
                "application_name": "Parent A",
                "parent_application_name": "Parent A",
                "active_users": 1000,
            },
            {
                "application_name": "Parent B",
                "parent_application_name": "Parent B",
                "active_users": 800,
            },
        ]
        assert {point["application_name"] for point in payload["points"]} == {
            point["parent_application_name"] for point in payload["points"]
        }
        assert "Service A1" not in str(payload)
        assert "Service B" not in str(payload)

        assert filtered_response.status_code == 200
        assert filtered_response.json()["points"] == [
            {
                "application_name": "Parent A",
                "parent_application_name": "Parent A",
                "active_users": 1000,
            },
        ]
    finally:
        cleanup_client(db, client_id)


def test_dashboard_applications_filter_values_use_business_custom_sort_order() -> None:
    db, client_id, project_id, _, _, _ = create_dashboard_project()
    try:
        custom_rows = [
            ("Service Blank", {}, None),
            (
                "Service Very Critical",
                {
                    "Business criticality": "Very Critical",
                    "Install Status": "In production",
                    "Life Cycle Stage": "Operational",
                    "Life Cycle Stage Status": "Live",
                },
                "Very Critical",
            ),
            (
                "Service Critical",
                {
                    "Business criticality": "Critical",
                    "Install Status": "Retire in progress",
                    "Life Cycle Stage": "End of Life",
                    "Life Cycle Stage Status": "Retired",
                },
                "Critical",
            ),
            (
                "Service High",
                {
                    "Business criticality": "High",
                    "Install Status": "Archived",
                    "Life Cycle Stage": "Ideation",
                    "Life Cycle Stage Status": "Idea",
                },
                "High",
            ),
            (
                "Service Medium",
                {
                    "Business criticality": "Medium",
                    "Install Status": "Pilot",
                    "Life Cycle Stage": "Operational",
                    "Life Cycle Stage Status": "Pilot",
                },
                "Medium",
            ),
            (
                "Service Low",
                {
                    "Business criticality": "Low",
                    "Install Status": "In production",
                    "Life Cycle Stage": "Operational",
                    "Life Cycle Stage Status": "Production",
                },
                "Low",
            ),
        ]
        for index, (service_name, cmdb_payload, criticality) in enumerate(custom_rows, start=1):
            add_inventory_item(
                db,
                project_id,
                service_name,
                supported_by_vendor=f"Vendor {index}",
                functional_track="Track",
                ams_owner="Owner",
                assignment_group=f"Group {index}",
                application_owner=f"App Owner {index}",
                parent_application_name="Parent",
                cmdb_payload=cmdb_payload,
            )
            assert criticality is None or cmdb_payload["Business criticality"] == criticality
        db.commit()

        with TestClient(app) as client:
            legacy_response = client.get(
                "/api/dashboard/applications/filter-values",
                params={"project_id": str(project_id)},
            )
            count_response = client.post(
                "/api/dashboard/applications/filter-values",
                json={"project_id": str(project_id), "filters": {}},
            )

        assert legacy_response.status_code == 200
        legacy_payload = legacy_response.json()
        assert legacy_payload["business_critical"] == [
            "(blank)",
            "Very Critical",
            "Critical",
            "High",
            "Medium",
            "Low",
        ]
        assert legacy_payload["install_status"] == [
            "(blank)",
            "In production",
            "Retire in progress",
            "Archived",
            "Pilot",
        ]
        assert [row["left_value"] for row in legacy_payload["lifecycle_status_stage"]] == [
            "(blank)",
            "Operational",
            "Operational",
            "Operational",
            "End of Life",
            "Ideation",
        ]

        assert count_response.status_code == 200
        count_payload = count_response.json()
        assert [row["label"] for row in count_payload["business_critical"]] == [
            "(blank)",
            "Very Critical",
            "Critical",
            "High",
            "Medium",
            "Low",
        ]
        assert [row["label"] for row in count_payload["install_status"]] == [
            "(blank)",
            "In production",
            "Retire in progress",
            "Archived",
            "Pilot",
        ]
        assert [row["left_value"] for row in count_payload["lifecycle_status_stage"]] == [
            "(blank)",
            "Operational",
            "Operational",
            "Operational",
            "End of Life",
            "Ideation",
        ]
    finally:
        cleanup_client(db, client_id)


def test_volumetrics_endpoints_use_scope_filters_sla_and_backlog() -> None:
    db, client_id, project_id, batch_id, file_id, _ = create_dashboard_project()
    try:
        incident = add_ticket(
            db,
            project_id,
            batch_id,
            file_id,
            "INC-VOL-OPEN-JAN",
            "INCIDENT",
            dt("2026-01-10T00:00:00"),
            state="Resolved",
            resolved_at=dt("2026-02-03T00:00:00"),
            assignment_group="IT-SAP-Group A",
        )
        incident.functional_track = "Data"
        incident.ams_owner = "Owner A"
        incident.support_lead = "Lead A"
        incident.parent_application_name = "Parent A"
        incident.application_owner = "App Owner A"
        incident.supported_by_vendor = "Vendor A"
        incident.response_sla_breached = False
        incident.resolution_sla_breached = True

        sc_task = add_ticket(
            db,
            project_id,
            batch_id,
            file_id,
            "SCTASK-VOL-CLOSED",
            "SERVICE_CATALOG_TASK",
            dt("2026-01-20T00:00:00"),
            state="Closed",
            closed_at=dt("2026-01-25T00:00:00"),
            assignment_group="IT-SAP-Group A",
        )
        sc_task.functional_track = "Data"
        sc_task.ams_owner = "Owner A"
        sc_task.support_lead = "Lead A"
        sc_task.parent_application_name = "Parent A"
        sc_task.application_owner = "App Owner A"
        sc_task.supported_by_vendor = "Vendor A"

        cancelled = add_ticket(
            db,
            project_id,
            batch_id,
            file_id,
            "INC-VOL-CANCELLED",
            "INCIDENT",
            dt("2026-01-15T00:00:00"),
            state="Cancelled",
            closed_at=dt("2026-01-18T00:00:00"),
            assignment_group="IT-NSA-Group B",
        )
        cancelled.functional_track = "Run"
        cancelled.ams_owner = "Owner B"
        cancelled.support_lead = "Lead B"
        cancelled.parent_application_name = "Parent B"
        cancelled.application_owner = "App Owner B"
        cancelled.supported_by_vendor = "Vendor B"

        add_ticket(
            db,
            project_id,
            batch_id,
            file_id,
            "INC-VOL-LATE-CANCELLED",
            "INCIDENT",
            dt("2026-03-20T00:00:00"),
            state="Cancelled",
            closed_at=dt("2026-03-23T00:00:00"),
            assignment_group="IT-NSA-Group B",
        )

        db.add(
            AssessmentOutOfScopeTicket(
                project_id=project_id,
                upload_batch_id=batch_id,
                ticket_number="INC-VOL-OOS",
                ticket_type="INCIDENT",
                created_at=dt("2026-01-05T00:00:00"),
                resolved_at=dt("2026-03-05T00:00:00"),
                state="Resolved",
                assignment_group="Group OOS",
                sap_non_sap=None,
                support_lead="Lead OOS",
                functional_track="Out",
                ams_owner="Owner OOS",
                parent_application_name="Parent OOS",
                application_owner="App Owner OOS",
                supported_by_vendor="Vendor OOS",
                response_sla_breached=False,
                resolution_sla_breached=False,
                out_of_scope_reason="assignment_group_not_in_application_inventory",
            ),
        )
        db.commit()

        request_body = {
            "project_id": str(project_id),
            "scope": "in_scope",
            "ticket_type": "all",
            "time_grain": "monthly",
            "start_datetime": "2026-01-01T00:00:00+00:00",
            "end_datetime": "2026-02-28T23:59:59+00:00",
            "filters": {},
        }

        with TestClient(app) as client:
            summary_response = client.post(
                "/api/dashboard/volumetrics/summary",
                json=request_body,
            )
            data_range_response = client.get(
                "/api/dashboard/volumetrics/data-range",
                params={"project_id": str(project_id)},
            )
            chart_response = client.post(
                "/api/dashboard/volumetrics/created-resolved-backlog",
                json=request_body,
            )
            created_resolved_cancelled_response = client.post(
                "/api/dashboard/volumetrics/created-resolved-canceled",
                json=request_body,
            )
            backlog_response = client.post(
                "/api/dashboard/volumetrics/backlog",
                json=request_body,
            )
            day_of_month_pattern_response = client.post(
                "/api/dashboard/volumetrics/created-pattern",
                json={**request_body, "pattern_type": "day_of_month"},
            )
            day_of_week_pattern_response = client.post(
                "/api/dashboard/volumetrics/created-pattern",
                json={**request_body, "pattern_type": "day_of_week"},
            )
            weekday_hour_pattern_response = client.post(
                "/api/dashboard/volumetrics/created-pattern",
                json={**request_body, "pattern_type": "hour_weekdays"},
            )
            weekend_hour_pattern_response = client.post(
                "/api/dashboard/volumetrics/created-pattern",
                json={**request_body, "pattern_type": "hour_weekends"},
            )
            sc_task_summary_response = client.post(
                "/api/dashboard/volumetrics/summary",
                json={**request_body, "ticket_type": "sc_task"},
            )
            filter_values_response = client.post(
                "/api/dashboard/volumetrics/filter-values",
                json={**request_body, "scope": "all"},
            )
            filtered_summary_response = client.post(
                "/api/dashboard/volumetrics/summary",
                json={
                    **request_body,
                    "filters": {"supported_by_vendor": ["Vendor A"]},
                },
            )
            sap_filtered_chart_response = client.post(
                "/api/dashboard/volumetrics/created-resolved-canceled",
                json={
                    **request_body,
                    "filters": {"sap_non_sap": ["SAP"]},
                },
            )
            hourly_weekday_response = client.post(
                "/api/dashboard/volumetrics/hourly-created-resolved",
                json={**request_body, "day_type": "weekdays"},
            )
            hourly_weekend_response = client.post(
                "/api/dashboard/volumetrics/hourly-created-resolved",
                json={**request_body, "day_type": "weekends"},
            )
            priority_response = client.post(
                "/api/dashboard/volumetrics/priority-distribution",
                json=request_body,
            )
            sla_trends_response = client.post(
                "/api/dashboard/volumetrics/sla-trends",
                json=request_body,
            )
            sc_task_sla_trends_response = client.post(
                "/api/dashboard/volumetrics/sla-trends",
                json={**request_body, "ticket_type": "sc_task"},
            )

        assert summary_response.status_code == 200
        summary = summary_response.json()
        assert summary["period_count"] == 2
        assert summary["created"]["total"] == 3
        assert summary["created"]["average_per_period"] == 1.5
        assert summary["resolved_closed"]["total"] == 2
        assert summary["cancelled"]["total"] == 1
        assert round(summary["cancelled"]["cancelled_pct_of_resolved_cancelled"], 1) == 33.3
        assert summary["response_sla"]["applicable_count"] == 1
        assert summary["response_sla"]["met_count"] == 1
        assert summary["response_sla"]["average_adherence_pct"] == 100
        assert summary["resolution_sla"]["average_adherence_pct"] == 0

        assert data_range_response.status_code == 200
        data_range = data_range_response.json()
        assert data_range["completion_date_min"].startswith("2026-02-01")
        assert data_range["completion_date_max"].startswith("2026-02-28")

        assert chart_response.status_code == 200
        chart_payload = chart_response.json()
        assert chart_payload["average_backlog_open"] == 0.5
        assert [row["period_label"] for row in chart_payload["rows"]] == ["Jan-26", "Feb-26"]
        assert chart_payload["rows"][0]["created_count"] == 3
        assert chart_payload["rows"][0]["resolved_closed_count"] == 1
        assert chart_payload["rows"][0]["backlog_open_count"] == 1
        assert chart_payload["rows"][1]["resolved_closed_count"] == 1
        assert chart_payload["rows"][1]["backlog_open_count"] == 0

        assert created_resolved_cancelled_response.status_code == 200
        created_resolved_cancelled_payload = created_resolved_cancelled_response.json()
        assert "average_backlog_open" not in created_resolved_cancelled_payload
        assert "backlog_open_count" not in created_resolved_cancelled_payload["points"][0]
        assert created_resolved_cancelled_payload["points"][0]["created_count"] == 3
        assert created_resolved_cancelled_payload["points"][0]["resolved_closed_count"] == 1
        assert (
            created_resolved_cancelled_payload["points"][0][
                "canceled_closed_incomplete_count"
            ]
            == 1
        )

        assert backlog_response.status_code == 200
        backlog_payload = backlog_response.json()
        assert backlog_payload["average_backlog"] == 0.5
        assert [point["backlog_open"] for point in backlog_payload["points"]] == [1, 0]

        assert day_of_month_pattern_response.status_code == 200
        day_of_month_points = day_of_month_pattern_response.json()["points"]
        assert [point["label"] for point in day_of_month_points] == [
            str(day) for day in range(1, 31)
        ]
        assert "31" not in {point["label"] for point in day_of_month_points}
        assert day_of_month_points[9]["total_created"] == 1
        assert day_of_month_points[14]["total_created"] == 1
        assert day_of_month_points[19]["total_created"] == 1

        assert day_of_week_pattern_response.status_code == 200
        assert [point["label"] for point in day_of_week_pattern_response.json()["points"]] == [
            "Mon",
            "Tue",
            "Wed",
            "Thu",
            "Fri",
            "Sat",
            "Sun",
        ]

        assert weekday_hour_pattern_response.status_code == 200
        assert [point["label"] for point in weekday_hour_pattern_response.json()["points"]] == [
            f"{hour:02d}" for hour in range(24)
        ]
        assert weekend_hour_pattern_response.status_code == 200
        assert [point["label"] for point in weekend_hour_pattern_response.json()["points"]] == [
            f"{hour:02d}" for hour in range(24)
        ]

        assert sc_task_summary_response.status_code == 200
        sc_task_summary = sc_task_summary_response.json()
        assert sc_task_summary["response_sla"]["average_adherence_pct"] is None
        assert sc_task_summary["resolution_sla"]["average_adherence_pct"] is None

        assert filter_values_response.status_code == 200
        filter_values = filter_values_response.json()
        assert filter_values["scope"] == [
            {"label": "All", "value": "all", "count": 4},
            {"label": "In-scope", "value": "in_scope", "count": 3},
            {"label": "Out-of-scope", "value": "out_of_scope", "count": 1},
        ]
        assert filter_values["ticket_type"] == [
            {"label": "All", "value": "all", "count": 4},
            {"label": "Incidents", "value": "incident", "count": 3},
            {"label": "SC Tasks", "value": "sc_task", "count": 1},
        ]
        assert {
            row["label"]: row["count"]
            for row in filter_values["functional_track_ams_owner"]
        } == {
            "Data - Owner A": 2,
            "Out - Owner OOS": 1,
            "Run - Owner B": 1,
        }
        assert {
            row["label"]: row["count"]
            for row in filter_values["assignment_group_support_lead"]
        } == {
            "Group OOS - Lead OOS": 1,
            "IT-NSA-Group B - Lead B": 1,
            "IT-SAP-Group A - Lead A": 2,
        }
        assert {
            row["label"]: row["count"] for row in filter_values["sap_non_sap"]
        } == {
            "(blank)": 1,
            "Non-SAP": 1,
            "SAP": 2,
        }

        assert filtered_summary_response.status_code == 200
        filtered_summary = filtered_summary_response.json()
        assert filtered_summary["created"]["total"] == 2
        assert filtered_summary["resolved_closed"]["total"] == 2

        assert sap_filtered_chart_response.status_code == 200
        sap_points = sap_filtered_chart_response.json()["points"]
        assert sap_points[0]["created_count"] == 2
        assert sap_points[0]["resolved_closed_count"] == 1
        assert sap_points[0]["canceled_closed_incomplete_count"] == 0

        assert hourly_weekday_response.status_code == 200
        weekday_hourly = hourly_weekday_response.json()
        assert weekday_hourly["day_type"] == "weekdays"
        assert [point["hour"] for point in weekday_hourly["points"]] == [
            f"{hour:02d}" for hour in range(24)
        ]
        assert sum(point["average_created"] for point in weekday_hourly["points"]) > 0
        assert sum(point["average_resolved_closed"] for point in weekday_hourly["points"]) > 0

        assert hourly_weekend_response.status_code == 200
        weekend_hourly = hourly_weekend_response.json()
        assert weekend_hourly["day_type"] == "weekends"
        assert len(weekend_hourly["points"]) == 24
        assert sum(point["average_created"] for point in weekend_hourly["points"]) > 0

        assert priority_response.status_code == 200
        priority_payload = priority_response.json()
        assert priority_payload["time_grain"] == "monthly"
        assert "P1" in priority_payload["priorities"]
        assert priority_payload["points"][0]["values"]["P1"] == 3
        assert priority_payload["points"][0]["total"] == 3

        assert sla_trends_response.status_code == 200
        sla_trends = sla_trends_response.json()
        assert sla_trends["not_applicable"] is False
        assert sla_trends["logic"]["captured_definition"] == "sla_breached IS NOT NULL"
        assert sla_trends["response"][1]["total_closed_ticket_count"] == 1
        assert sla_trends["response"][1]["sla_captured_count"] == 1
        assert sla_trends["response"][1]["sla_adhered_count"] == 1
        assert sla_trends["response"][1]["sla_adherence_pct"] == 100
        assert sla_trends["resolution"][1]["sla_captured_count"] == 1
        assert sla_trends["resolution"][1]["sla_adhered_count"] == 0
        assert sla_trends["resolution"][1]["sla_adherence_pct"] == 0

        assert sc_task_sla_trends_response.status_code == 200
        sc_task_sla_trends = sc_task_sla_trends_response.json()
        assert sc_task_sla_trends["not_applicable"] is True
        assert sc_task_sla_trends["response"] == []
        assert sc_task_sla_trends["resolution"] == []
    finally:
        cleanup_client(db, client_id)


def test_volumetrics_detailed_volume_trends_and_incident_batch_charts() -> None:
    db, client_id, project_id, batch_id, file_id, _ = create_dashboard_project()
    try:
        app_a = add_inventory_item(
            db,
            project_id,
            "Application A",
            supported_by_vendor="Vendor A",
            functional_track="Data",
            ams_owner="Owner A",
            assignment_group="IT-SAP-A",
            application_owner="App Owner A",
            parent_application_name="Parent A",
            active_users=60,
        )
        app_b = add_inventory_item(
            db,
            project_id,
            "Application B",
            supported_by_vendor="Vendor B",
            functional_track="Data",
            ams_owner="Owner A",
            assignment_group="IT-NSA-B",
            application_owner="App Owner B",
            parent_application_name="Parent B",
            active_users=30,
        )
        app_c = add_inventory_item(
            db,
            project_id,
            "Application C",
            supported_by_vendor="Vendor C",
            functional_track="Run",
            ams_owner="Owner C",
            assignment_group="IT-SAP-C",
            application_owner="App Owner C",
            parent_application_name="Parent C",
            active_users=10,
        )
        db.flush()
        window_start, window_end = dashboard_service.rolling_six_complete_month_window()
        current_month = window_start
        for month_index in range(6):
            completion_month = dashboard_service.last_moment_of_month(current_month)
            for ticket_index in range(3):
                is_batch = ticket_index < 2
                is_cancelled = ticket_index == 1
                ticket = add_ticket(
                    db,
                    project_id,
                    batch_id,
                    file_id,
                    f"INC-APP-A-{month_index}-{ticket_index}",
                    "INCIDENT",
                    current_month,
                    state="Cancelled" if is_cancelled else "Resolved",
                    resolved_at=None if is_cancelled else completion_month,
                    closed_at=completion_month if is_cancelled else None,
                    short_description=(
                        "Automic batch failure" if is_batch else "User-reported issue"
                    ),
                    business_service_ci_name="Application A",
                    sap_non_sap="SAP",
                    architecture_type="Cloud",
                    install_type="Production",
                )
                ticket.application_inventory_id = app_a.id
            for ticket_index in range(2):
                ticket = add_ticket(
                    db,
                    project_id,
                    batch_id,
                    file_id,
                    f"INC-APP-B-{month_index}-{ticket_index}",
                    "INCIDENT",
                    current_month,
                    state="Resolved",
                    resolved_at=completion_month,
                    short_description=(
                        "Automic downstream failure"
                        if ticket_index == 0
                        else "Manual incident"
                    ),
                    business_service_ci_name="Application B",
                    sap_non_sap="Non-SAP",
                    architecture_type="On Premise",
                    install_type="SaaS",
                )
                ticket.application_inventory_id = app_b.id
            ticket = add_ticket(
                db,
                project_id,
                batch_id,
                file_id,
                f"SCTASK-APP-C-{month_index}",
                "SERVICE_CATALOG_TASK",
                current_month,
                state="Closed",
                closed_at=completion_month,
                business_service_ci_name="Application C",
                sap_non_sap="SAP",
                architecture_type="Vendor Managed",
                install_type="Cloud",
            )
            ticket.application_inventory_id = app_c.id
            current_month = dashboard_service.add_month(current_month)
        db.commit()

        request_body = {
            "project_id": str(project_id),
            "scope": "in_scope",
            "ticket_type": "all",
            "time_grain": "monthly",
            "start_datetime": "2025-01-01T00:00:00+00:00",
            "end_datetime": "2025-01-31T23:59:59+00:00",
            "filters": {},
        }
        batch_trend_body = {
            **request_body,
            "start_datetime": window_start.isoformat(),
            "end_datetime": window_end.isoformat(),
        }

        with TestClient(app) as client:
            top_apps_response = client.post(
                "/api/dashboard/volumetrics/top-applications",
                json={**request_body, "top_n": 10},
            )
            batch_trend_response = client.post(
                "/api/dashboard/volumetrics/incident-batch-trend",
                json=batch_trend_body,
            )
            top_batch_response = client.post(
                "/api/dashboard/volumetrics/top-incident-batch-applications",
                json={**request_body, "top_n": 10},
            )
            tickets_per_user_response = client.post(
                "/api/dashboard/volumetrics/tickets-per-user",
                json={**request_body, "top_n": 10},
            )
            distribution_response = client.post(
                "/api/dashboard/volumetrics/distribution-splits",
                json=request_body,
            )
            recompute_response = client.post(
                "/api/application-inventory/recompute-ticket-user-metrics",
                json={"project_id": str(project_id)},
            )
            sc_task_batch_response = client.post(
                "/api/dashboard/volumetrics/incident-batch-trend",
                json={**batch_trend_body, "ticket_type": "sc_task"},
            )

        assert top_apps_response.status_code == 200
        top_apps = top_apps_response.json()
        assert top_apps["ranking_window"] == {
            "start_month": f"{window_start.year:04d}-{window_start.month:02d}",
            "end_month": f"{window_end.year:04d}-{window_end.month:02d}",
            "description": "Last 6 complete months excluding current month",
        }
        assert [point["application_name"] for point in top_apps["points"][:3]] == [
            "Application A",
            "Application B",
            "Application C",
        ]
        assert top_apps["points"][0]["average_created"] == 3
        assert top_apps["points"][0]["average_canceled_closed_incomplete"] == 1
        assert top_apps["overall_average_monthly_volume"] == 6
        assert round(top_apps["points"][0]["volume_pct"], 1) == 50.0
        assert top_apps["points"][0]["display_label"] == "3 (50.0%)"
        assert "pareto_cumulative_pct" not in top_apps["points"][0]

        assert batch_trend_response.status_code == 200
        batch_trend = batch_trend_response.json()
        assert batch_trend["applicable"] is True
        assert batch_trend["batch_rule"]["field"] == "short_description"
        assert [point["batch_created_count"] for point in batch_trend["points"]] == [
            3,
            3,
            3,
            3,
            3,
            3,
        ]

        assert top_batch_response.status_code == 200
        top_batch = top_batch_response.json()
        assert top_batch["applicable"] is True
        assert [point["application_name"] for point in top_batch["points"][:2]] == [
            "Application A",
            "Application B",
        ]
        assert top_batch["points"][0]["average_batch_created"] == 2
        assert top_batch["points"][0]["average_batch_canceled"] == 1
        assert round(top_batch["points"][0]["pareto_cumulative_pct"], 1) == 66.7

        assert tickets_per_user_response.status_code == 200
        tickets_per_user = tickets_per_user_response.json()
        assert [point["application_name"] for point in tickets_per_user["points"]] == [
            "Application C",
            "Application B",
            "Application A",
        ]
        assert tickets_per_user["points"][0]["average_monthly_ticket_volume"] == 1
        assert tickets_per_user["points"][0]["active_users"] == 10
        assert tickets_per_user["points"][0]["tickets_per_user_per_month"] == 0.1
        assert tickets_per_user["points"][0]["display_label"] == "0.10"

        assert distribution_response.status_code == 200
        distribution = distribution_response.json()
        sap_all = {
            point["label"]: point["average_monthly_count"]
            for point in distribution["sap_non_sap"]["all"]
        }
        assert sap_all == {"SAP": 4, "Non-SAP": 2}
        architecture_all = {
            point["label"]: point["average_monthly_count"]
            for point in distribution["architecture_type"]["all"]
        }
        assert architecture_all == {"Cloud": 3, "On Premise": 2, "Vendor Managed": 1}
        install_all = {
            point["label"]: point["average_monthly_count"]
            for point in distribution["install_type"]["all"]
        }
        assert install_all == {"Production": 3, "SaaS": 2, "Cloud": 1}
        assert distribution["sap_non_sap"]["incidents"][0]["average_monthly_count"] == 3
        assert distribution["sap_non_sap"]["sc_tasks"][0]["average_monthly_count"] == 1

        assert recompute_response.status_code == 200
        recompute_payload = recompute_response.json()
        assert recompute_payload["inventory_count"] == 3
        assert recompute_payload["active_users_count"] == 3
        assert recompute_payload["metrics_updated_count"] == 3
        db.expire_all()
        refreshed_app_a = db.get(ApplicationInventoryItem, app_a.id)
        refreshed_app_c = db.get(ApplicationInventoryItem, app_c.id)
        assert refreshed_app_a is not None
        assert refreshed_app_c is not None
        assert refreshed_app_a.avg_monthly_ticket_volume_6m == 3
        assert round(refreshed_app_a.tickets_per_user_per_month or 0, 2) == 0.05
        assert refreshed_app_c.avg_monthly_ticket_volume_6m == 1
        assert round(refreshed_app_c.tickets_per_user_per_month or 0, 2) == 0.10

        assert sc_task_batch_response.status_code == 200
        sc_task_batch = sc_task_batch_response.json()
        assert sc_task_batch["applicable"] is False
        assert sc_task_batch["points"] == []
        assert "SC Task catalog item charts" in sc_task_batch["message"]
    finally:
        cleanup_client(db, client_id)


def test_volumetrics_prompt17_detailed_splits_mttr_and_duration_buckets() -> None:
    db, client_id, project_id, batch_id, file_id, _ = create_dashboard_project()
    try:
        window_start, window_end = dashboard_service.rolling_six_complete_month_window()
        current_month = window_start
        for month_index in range(6):
            add_ticket(
                db,
                project_id,
                batch_id,
                file_id,
                f"INC-P17-VM-1-{month_index}",
                "INCIDENT",
                current_month,
                state="Resolved",
                resolved_at=current_month + timedelta(days=1),
                priority="1 - Critical",
                business_duration_seconds=86400,
                business_service_ci_name="Architecture App A",
                architecture_type="Vendor Managed",
                install_type="Cloud",
            )
            add_ticket(
                db,
                project_id,
                batch_id,
                file_id,
                f"INC-P17-VM-2-{month_index}",
                "INCIDENT",
                current_month,
                state="Resolved",
                resolved_at=current_month + timedelta(days=1),
                priority="1 - Critical",
                business_duration_seconds=86400,
                business_service_ci_name="Architecture App A",
                architecture_type="Vendor Managed",
                install_type="Cloud",
            )
            add_ticket(
                db,
                project_id,
                batch_id,
                file_id,
                f"INC-P17-COTS-{month_index}",
                "INCIDENT",
                current_month,
                state="Resolved",
                resolved_at=current_month + timedelta(days=2),
                priority="2 - High",
                business_duration_seconds=172800,
                business_service_ci_name="Architecture App B",
                architecture_type="COTS",
                install_type="On Premise",
            )
            add_ticket(
                db,
                project_id,
                batch_id,
                file_id,
                f"SCTASK-P17-COTS-{month_index}",
                "SERVICE_CATALOG_TASK",
                current_month,
                state="Closed",
                closed_at=current_month + timedelta(days=3),
                priority="3 - Moderate",
                business_duration_seconds=259200,
                business_service_ci_name="Task Architecture App",
                architecture_type="COTS",
                install_type="SaaS",
            )
            current_month = dashboard_service.add_month(current_month)

        may_start = dashboard_service.first_day_of_month(window_end)
        incident_bucket_specs = [
            ("INC-P17-BUCKET-1D", 1),
            ("INC-P17-BUCKET-3D", 3),
            ("INC-P17-BUCKET-10D", 10),
            ("INC-P17-BUCKET-11D", 11),
        ]
        for ticket_number, duration_days in incident_bucket_specs:
            add_ticket(
                db,
                project_id,
                batch_id,
                file_id,
                ticket_number,
                "INCIDENT",
                may_start,
                state="Resolved",
                resolved_at=may_start + timedelta(days=duration_days),
                priority="4 - Low",
                business_duration_seconds=duration_days * 86400,
                business_service_ci_name="Duration Bucket App",
                architecture_type="Bucket Architecture",
                install_type="Bucket Install",
            )
        sc_task_bucket_specs = [
            ("SCTASK-P17-BUCKET-1D", 1),
            ("SCTASK-P17-BUCKET-3D", 3),
            ("SCTASK-P17-BUCKET-10D", 10),
            ("SCTASK-P17-BUCKET-11D", 11),
        ]
        for ticket_number, duration_days in sc_task_bucket_specs:
            add_ticket(
                db,
                project_id,
                batch_id,
                file_id,
                ticket_number,
                "SERVICE_CATALOG_TASK",
                may_start,
                state="Closed",
                closed_at=may_start + timedelta(days=duration_days),
                priority="4 - Low",
                business_duration_seconds=duration_days * 86400,
                business_service_ci_name="Task Duration Bucket App",
                architecture_type="Bucket Architecture",
                install_type="Bucket Install",
            )

        partial_month_ticket = add_ticket(
            db,
            project_id,
            batch_id,
            file_id,
            "INC-P17-CURRENT-MONTH-EXCLUDED",
            "INCIDENT",
            dashboard_service.add_month(may_start),
            state="Resolved",
            resolved_at=dashboard_service.add_month(may_start) + timedelta(days=2),
            priority="1 - Critical",
            business_duration_seconds=86400,
            business_service_ci_name="Current Month App",
            architecture_type="Current Month Architecture",
            install_type="Current Month Install",
        )
        partial_month_ticket.functional_track = "Current Month"
        db.commit()

        request_body = {
            "project_id": str(project_id),
            "scope": "in_scope",
            "ticket_type": "all",
            "time_grain": "monthly",
            "start_datetime": window_start.isoformat(),
            "end_datetime": (
                dashboard_service.add_month(may_start) + timedelta(days=20)
            ).isoformat(),
            "filters": {},
        }

        with TestClient(app) as client:
            split_response = client.post(
                "/api/dashboard/volumetrics/detailed-architecture-install-splits",
                json=request_body,
            )
            mttr_response = client.post(
                "/api/dashboard/volumetrics/kpi-mttr-trends",
                json=request_body,
            )
            bucket_response = client.post(
                "/api/dashboard/volumetrics/kpi-duration-buckets",
                json=request_body,
            )

        assert split_response.status_code == 200
        split_payload = split_response.json()
        assert split_payload["rolling_window"] == {
            "start_month": f"{window_start.year:04d}-{window_start.month:02d}",
            "end_month": f"{window_end.year:04d}-{window_end.month:02d}",
            "description": "Latest complete 6 months",
        }
        incident_architecture = {
            row["label"]: row for row in split_payload["architecture_type"]["incidents"]
        }
        sc_task_install = {
            row["label"]: row for row in split_payload["install_type"]["sc_tasks"]
        }
        assert incident_architecture["Vendor Managed"]["average_monthly_count"] == 2
        assert incident_architecture["COTS"]["average_monthly_count"] == 1
        assert "Current Month Architecture" not in incident_architecture
        assert sc_task_install["SaaS"]["average_monthly_count"] == 1

        assert mttr_response.status_code == 200
        mttr_payload = mttr_response.json()
        assert mttr_payload["incident"]["P1"][-1]["period_key"] == "2026-05"
        assert all(
            point["period_key"] != "2026-06"
            for points in mttr_payload["incident"].values()
            for point in points
        )
        p1_december = mttr_payload["incident"]["P1"][0]
        p2_december = mttr_payload["incident"]["P2"][0]
        sc_task_p3_december = mttr_payload["sc_task"]["P3"][0]
        assert p1_december["average_mttr_days"] == 1
        assert p1_december["ticket_count"] == 2
        assert p1_december["show_label"] is True
        assert p1_december["label_text"] == "1.0d\nn=2"
        assert p2_december["average_mttr_days"] == 2
        assert p2_december["ticket_count"] == 1
        assert p2_december["show_label"] is False
        assert sc_task_p3_december["average_mttr_days"] == 3
        assert sc_task_p3_december["ticket_count"] == 1
        assert any(
            point["period_key"] == "2026-03" and point["show_label"]
            for point in mttr_payload["incident"]["P1"]
        )
        assert any(
            point["period_key"] == "2026-01" and point["show_label"]
            for point in mttr_payload["incident"]["P2"]
        )
        assert any(
            point["period_key"] == "2026-02" and point["show_label"]
            for point in mttr_payload["sc_task"]["P3"]
        )

        assert bucket_response.status_code == 200
        bucket_payload = bucket_response.json()
        assert bucket_payload["months"] == ["2026-03", "2026-04", "2026-05"]
        may_incident = next(
            row for row in bucket_payload["incident"] if row["period_key"] == "2026-05"
        )
        may_sc_task = next(
            row for row in bucket_payload["sc_task"] if row["period_key"] == "2026-05"
        )
        assert may_incident["buckets"] == {
            "0-1 day": 3,
            "1-3 days": 2,
            "3-10 days": 1,
            ">10 days": 1,
        }
        assert may_sc_task["buckets"] == {
            "0-1 day": 1,
            "1-3 days": 2,
            "3-10 days": 1,
            ">10 days": 1,
        }
    finally:
        cleanup_client(db, client_id)


def test_offline_dashboard_export_returns_safe_interactive_html() -> None:
    db, client_id, project_id, batch_id, file_id, _ = create_dashboard_project()
    try:
        add_inventory_item(
            db,
            project_id,
            "Payroll Portal",
            supported_by_vendor="Vendor A",
            functional_track="Data",
            ams_owner="Owner A",
            assignment_group="IT-SAP-PAYROLL",
            application_owner="Application Owner A",
            parent_application_name="Parent Payroll",
            active_users=500,
            cmdb_payload={
                "Application type": "Business",
                "Architecture type": "Cloud",
                "Business criticality": "Critical",
                "Install Status": "In production",
                "Install type": "Production",
                "Life Cycle Stage": "Operational",
                "Life Cycle Stage Status": "In Use",
                "Operating System": "Windows",
                "SOX Scope": "In-Scope",
                "Strategic": "Yes",
            },
        )
        incident = add_ticket(
            db,
            project_id,
            batch_id,
            file_id,
            "INC-OFFLINE-RAW-SECRET",
            "INCIDENT",
            dt("2026-01-01T00:00:00"),
            state="Resolved",
            resolved_at=dt("2026-01-01T00:00:00"),
            assignment_group="IT-SAP-PAYROLL",
            business_duration_seconds=86400,
            architecture_type="Cloud",
            install_type="Production",
            raw_payload={"secret": "raw ticket payload should not be exported"},
        )
        incident.functional_track = "Data"
        incident.ams_owner = "Owner A"
        incident.support_lead = "Lead A"
        incident.business_service_ci_name = "Payroll Portal"
        incident.parent_application_name = "Parent Payroll"
        incident.application_owner = "Application Owner A"
        incident.supported_by_vendor = "Vendor A"
        incident.response_sla_breached = False
        incident.resolution_sla_breached = False

        sc_task = add_ticket(
            db,
            project_id,
            batch_id,
            file_id,
            "SCTASK-OFFLINE-RAW-SECRET",
            "SERVICE_CATALOG_TASK",
            dt("2026-01-12T00:00:00"),
            state="Closed",
            closed_at=dt("2026-01-18T00:00:00"),
            assignment_group="IT-NSA-PAYROLL",
            business_duration_seconds=172800,
            architecture_type="On Premise",
            install_type="Production",
            raw_payload={"secret": "raw sc task payload should not be exported"},
        )
        sc_task.functional_track = "Run"
        sc_task.ams_owner = "Owner B"
        sc_task.support_lead = "Lead B"
        sc_task.business_service_ci_name = "Payroll Portal"
        sc_task.parent_application_name = "Parent Payroll"
        sc_task.application_owner = "Application Owner B"
        sc_task.supported_by_vendor = "Vendor B"

        incomplete_month_incident = add_ticket(
            db,
            project_id,
            batch_id,
            file_id,
            "INC-OFFLINE-INCOMPLETE-MONTH",
            "INCIDENT",
            dt("2026-02-10T00:00:00"),
            state="Resolved",
            resolved_at=dt("2026-02-20T00:00:00"),
            assignment_group="IT-SAP-PAYROLL",
        )
        incomplete_month_incident.functional_track = "Data"
        incomplete_month_incident.ams_owner = "Owner A"
        incomplete_month_incident.support_lead = "Lead A"
        incomplete_month_incident.parent_application_name = "Parent Payroll"
        incomplete_month_incident.application_owner = "Application Owner A"
        incomplete_month_incident.supported_by_vendor = "Vendor A"

        db.add(
            AssessmentOutOfScopeTicket(
                project_id=project_id,
                upload_batch_id=batch_id,
                ticket_number="INC-OFFLINE-OOS-SECRET",
                ticket_type="INCIDENT",
                created_at=dt("2026-01-14T00:00:00"),
                resolved_at=dt("2026-01-20T00:00:00"),
                state="Resolved",
                assignment_group="IT-SAP-OOS",
                sap_non_sap="SAP",
                functional_track="Data",
                ams_owner="Owner A",
                support_lead="Lead A",
                parent_application_name="Parent Payroll",
                application_owner="Application Owner A",
                supported_by_vendor="Vendor A",
                business_duration_seconds=86400,
                architecture_type="Cloud",
                install_type="Production",
                response_sla_breached=False,
                resolution_sla_breached=False,
                out_of_scope_reason="assignment_group_not_in_application_inventory",
            ),
        )
        db.commit()

        with TestClient(app) as client:
            response = client.post(
                "/api/dashboard/offline-export",
                json={"project_id": str(project_id), "format": "html"},
            )

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/html")
        assert "AMS_Apps_Volumetrics_Dashboard_" in response.headers["content-disposition"]
        assert response.headers["content-disposition"].endswith('.html"')

        document = response.text
        assert "Overview" in document
        assert "Applications" in document
        assert "Volumetrics &amp; SLA" in document
        assert "Overall Volume Trends" in document
        assert "Overall SLA Trends" in document
        assert "Detailed Volume Trends" in document
        assert "KPI Trends" in document
        assert "Category-wise Trends" in document
        assert "Created vs Resolved by hour of the day" in document
        assert "Priority-wise ticket distribution" in document
        assert "Response SLA adherence trend" in document
        assert "Resolution SLA adherence trend" in document
        assert "Top High-Volume Applications" in document
        assert "Batch-related Incidents Created" in document
        assert "Incident Batch-Related Tickets Created Trend" not in document
        assert "Top Applications with Incident Batch-Related Tickets" in document
        assert "Average Monthly Incidents by Architecture Type" in document
        assert "Average Monthly SC Tasks by Architecture Type" in document
        assert "Average Monthly Incidents by Install Type" in document
        assert "Average Monthly SC Tasks by Install Type" in document
        assert "Incident MTTR by Priority" in document
        assert "SC Task MTTR by Priority" in document
        assert "P1 / P2 MTTR" in document
        assert "P3 / P4 MTTR" in document
        assert "Incident P1 MTTR</h3>" not in document
        assert "Incident P2 MTTR</h3>" not in document
        assert "Incident P3 MTTR</h3>" not in document
        assert "Incident P4 MTTR</h3>" not in document
        assert "SC Task P1 MTTR</h3>" not in document
        assert "SC Task P2 MTTR</h3>" not in document
        assert "SC Task P3 MTTR</h3>" not in document
        assert "SC Task P4 MTTR</h3>" not in document
        assert document.count("Average Monthly Incidents by Architecture Type") == 1
        assert document.count("Average Monthly SC Tasks by Architecture Type") == 1
        assert document.count("Average Monthly Incidents by Install Type") == 1
        assert document.count("Average Monthly SC Tasks by Install Type") == 1
        assert "Incident Resolved Volume by Resolution Duration" in document
        assert "SC Task Closed Volume by Closed Duration" in document
        assert "Top Parent Business Applications by Active Users" in document
        assert "Top Applications by Active Users" not in document
        assert "Tickets per User per Month by Application" in document
        assert "Average Monthly Tickets by SAP / Non-SAP" in document
        assert "Average Monthly Incidents by SAP / Non-SAP" in document
        assert "Average Monthly SC Tasks by SAP / Non-SAP" in document
        assert "Average Monthly Tickets by Architecture Type" in document
        assert "Average Monthly Tickets by Install Type" in document
        assert (
            '<meta name="viewport" content="width=device-width, initial-scale=1.0" />'
            in document
        )
        assert "AMS Applications & Volumetric Analysis" in document
        assert "AMS Ticket Intelligence" not in document
        assert "Offline Dashboard</p>" not in document
        assert "page-subtitle" not in document
        assert "overview-summary-grid" in document
        assert "grid-template-columns: repeat(4, minmax(0, 1fr))" in document
        assert "tile-dark" in document
        assert "tile-light" in document
        assert "const row = Math.floor(index / columnCount);" in document
        assert 'tile("Project", DASHBOARD.metadata.project_name, "", 0, 4)' not in document
        assert "Functional Tracks / AMS Owners" in document
        assert "Apps Driving 80% Volume" in document
        assert "Tickets data range:" in document
        assert (
            'tile("Applications", fmt(new Set(rows.map((row) => '
            'row.business_service_ci_name)).size), "", 0, 6)'
            in document
        )
        assert (
            'tile("Created", `Total: ${fmt(totalCreated)}`, '
            "`Avg monthly: ${fmt(totalCreated / Math.max(1, periods.length))}`, 0, 5)"
            in document
        )
        assert "Tickets Data Range" not in document
        assert "Completion Range" not in document
        assert 'tile("Customer"' not in document
        assert 'tile("Application Owners"' not in document
        assert "function renderCustomerLogo" in document
        assert "function dateTimeText" in document
        assert "Exported: ${dateTimeText(DASHBOARD.metadata.exported_at)}" in document
        assert "max-width: 100vw" in document
        assert "*::before" in document
        assert "*::after" in document
        assert "offline-dashboard" in document
        assert "dashboard-layout" in document
        assert "filter-pane" in document
        assert "main-content" in document
        assert "cards-grid" in document
        assert "max-height: 92px" in document
        assert "max-height: 34px" in document
        assert "max-height: none; min-height: 0;" in document
        assert "#applications .legend" in document
        assert "font-size: 0.82rem" in document
        assert "const dataLabelFontSize = isApplicationChart ? 14 : 10;" in document
        assert "const axisLabelFontSize = isApplicationChart ? 13 : 10;" in document
        assert "barWidth = Math.max(22" in document
        assert "applicationChart: true" in document
        assert "chart-stage" in document
        assert "chart-copy-toolbar" in document
        assert "copy-chart-button" in document
        assert "Copy Chart" in document
        assert "function copyOfflineChart" in document
        assert "function installChartCopyButtons" in document
        assert "function parseDashboardPayload" in document
        assert "function safeRenderSection" in document
        assert "function renderFatalDashboardError" in document
        assert "function inlineSvgComputedStyles" in document
        assert "function wrapExportText" in document
        assert "function chartExportText" in document
        assert "function downloadOfflineChartPng" in document
        assert (
            "Future offline charts only need the standard .chart-card + .chart-frame SVG pattern."
            in document
        )
        assert "ClipboardItem" in document
        assert '"image/png"' in document
        assert "XMLSerializer" in document
        assert "Copy blocked. PNG downloaded instead." in document
        assert "navigator.clipboard?.writeText" not in document
        assert 'split("\\n")' in document
        assert 'split("\n")' not in document
        assert 'installChartCopyButtons(document.getElementById("applications"))' in document
        assert 'installChartCopyButtons(document.getElementById("volumetrics"))' in document
        assert "table-card" in document
        assert "table-scroll" in document
        assert "applications-table" in document
        assert "@media (max-width: 1100px)" in document
        assert "grid-template-columns: minmax(220px, 260px) minmax(0, 1fr)" in document
        assert "width: 100%" in document
        assert (
            "#volumetrics .summary-grid { grid-template-columns: repeat(5, minmax(0, 1fr)); }"
            in document
        )
        assert "overflow-x: hidden" in document
        assert "overflow-x: auto" in document
        assert "position: sticky" in document
        assert "overflow-y: auto" in document
        assert "overflow-y: visible" in document
        assert "grid-template-rows: auto auto auto" in document
        assert "min-height: 420px" in document
        assert "min-height: 430px" in document
        assert "min-height: 440px" in document
        assert "min-height: 360px" in document
        assert "min-height: 300px" in document
        assert "max-height: 360px" in document
        assert "min-width: 1800px" in document
        assert "class=\"chart-svg pie-svg\"" in document
        assert "viewBox=\"0 0 520 320\"" in document
        assert "preserveAspectRatio=\"xMidYMid meet\"" in document
        assert "100dvh" not in document
        assert "overflow-y: hidden" not in document
        assert "max-height: calc(100vh" not in document
        assert "Math.max(options.width || 1180" not in document
        assert "data.length * 60" not in document
        assert "INC-OFFLINE-RAW-SECRET" not in document
        assert "INC-OFFLINE-INCOMPLETE-MONTH" not in document
        assert "SCTASK-OFFLINE-RAW-SECRET" not in document
        assert "INC-OFFLINE-OOS-SECRET" not in document
        assert "raw ticket payload should not be exported" not in document
        assert "raw sc task payload should not be exported" not in document
        assert "normalized_payload" not in document
        assert "cmdb_payload" not in document

        match = re.search(
            r'<script type="application/json" id="dashboard-data">(.*?)</script>',
            document,
            re.S,
        )
        assert match is not None
        payload = json.loads(match.group(1))
        assert payload["metadata"]["time_grain"] == "monthly"
        assert payload["metadata"]["customer_logo_data_url"] is None
        assert payload["metadata"]["offline_filters"] == [
            "scope",
            "ticket_type",
            "functional_track_ams_owner",
            "sap_non_sap",
        ]
        assert payload["metadata"]["data_available_to"].startswith("2026-01-31")
        assert payload["metadata"]["complete_month_from"].startswith("2026-01-01")
        assert payload["metadata"]["complete_month_to"].startswith("2026-01-31")
        assert payload["overview"]["application_inventory"]["total_applications"] == 1
        assert payload["overview"]["application_inventory"]["critical_application_count"] == 1
        assert payload["overview"]["application_inventory"]["very_critical_application_count"] == 0
        assert payload["overview"]["tickets"]["completion_date_max"].startswith("2026-01-31")
        assert payload["overview"]["tickets"]["applications_80pct_monthly_volume_count"] == 1
        assert payload["applications"]["rows"][0]["business_service_ci_name"] == "Payroll Portal"
        assert payload["applications"]["rows"][0]["active_users"] == 500
        assert "cmdb_payload" not in payload["applications"]["rows"][0]
        assert "architecture_type" in payload["applications"]["charts"]
        assert "install_type" in payload["applications"]["charts"]
        assert "operating_system" not in payload["applications"]["charts"]
        assert "sox_scope" not in payload["applications"]["charts"]
        assert payload["volumetrics"]["monthly_rows"]
        assert [row["period_key"] for row in payload["volumetrics"]["periods"]] == ["2026-01"]
        assert {
            row["period_key"] for row in payload["volumetrics"]["monthly_rows"]
        } == {"2026-01"}
        assert payload["volumetrics"]["sub_tabs"] == [
            "overall_volume_trends",
            "overall_sla_trends",
            "detailed_volume_trends",
            "kpi_trends",
            "category_wise_trends",
        ]
        assert payload["volumetrics"]["created_patterns"]["rows"]
        assert payload["volumetrics"]["overall_volume_trends"][
            "created_resolved_by_hour"
        ]["rows"]
        assert payload["volumetrics"]["overall_volume_trends"][
            "priority_distribution"
        ]["rows"]
        assert payload["volumetrics"]["overall_sla_trends"]["rows"]
        assert payload["volumetrics"]["detailed_volume_trends"]["application_rows"]
        assert payload["volumetrics"]["detailed_volume_trends"]["split_rows"]
        assert payload["volumetrics"]["detailed_volume_trends"]["split_window"][
            "description"
        ] == "Latest complete 6 months"
        assert payload["volumetrics"]["kpi_trends"]["mttr"]["rows"]
        assert payload["volumetrics"]["kpi_trends"]["duration_buckets"]["rows"]
        detailed_row = payload["volumetrics"]["detailed_volume_trends"]["application_rows"][0]
        assert "ticket_number" not in detailed_row
        assert "short_description" not in detailed_row
        assert "caller_id" not in detailed_row
        assert "normalized_payload" not in detailed_row
        assert "architecture_type" in detailed_row
        assert "install_type" in detailed_row
        kpi_row = payload["volumetrics"]["kpi_trends"]["mttr"]["rows"][0]
        assert "ticket_count" in kpi_row
        assert "ticket_number" not in kpi_row
        assert "short_description" not in kpi_row
        assert "caller_id" not in kpi_row
        assert "normalized_payload" not in kpi_row
        assert "ticket_number" not in payload["volumetrics"]["monthly_rows"][0]
        assert "normalized_payload" not in payload["volumetrics"]["monthly_rows"][0]
    finally:
        cleanup_client(db, client_id)


def test_volumetrics_weekly_buckets_start_on_monday() -> None:
    db, client_id, project_id, batch_id, file_id, _ = create_dashboard_project()
    try:
        add_ticket(
            db,
            project_id,
            batch_id,
            file_id,
            "INC-WEEKLY",
            "INCIDENT",
            dt("2026-01-07T00:00:00"),
            state="Resolved",
            resolved_at=dt("2026-01-14T00:00:00"),
        )
        db.commit()

        with TestClient(app) as client:
            response = client.post(
                "/api/dashboard/volumetrics/created-resolved-backlog",
                json={
                    "project_id": str(project_id),
                    "scope": "in_scope",
                    "ticket_type": "incident",
                    "time_grain": "weekly",
                    "start_datetime": "2026-01-07T00:00:00+00:00",
                    "end_datetime": "2026-01-18T23:59:59+00:00",
                    "filters": {},
                },
            )

        assert response.status_code == 200
        rows = response.json()["rows"]
        assert [row["period_label"] for row in rows] == ["05-Jan-26", "12-Jan-26"]
        assert rows[0]["created_count"] == 1
        assert rows[0]["backlog_open_count"] == 1
        assert rows[1]["resolved_closed_count"] == 1
        assert rows[1]["backlog_open_count"] == 0
    finally:
        cleanup_client(db, client_id)


def test_volumetrics_weekly_range_is_limited_to_fifteen_weeks() -> None:
    db, client_id, project_id, batch_id, file_id, _ = create_dashboard_project()
    try:
        add_ticket(
            db,
            project_id,
            batch_id,
            file_id,
            "INC-WEEKLY-LIMIT",
            "INCIDENT",
            dt("2026-01-07T00:00:00"),
            state="Resolved",
            resolved_at=dt("2026-01-14T00:00:00"),
        )
        db.commit()

        with TestClient(app) as client:
            response = client.post(
                "/api/dashboard/volumetrics/summary",
                json={
                    "project_id": str(project_id),
                    "scope": "in_scope",
                    "ticket_type": "incident",
                    "time_grain": "weekly",
                    "start_datetime": "2026-01-01T00:00:00+00:00",
                    "end_datetime": "2026-05-31T23:59:59+00:00",
                    "filters": {},
                },
            )

        assert response.status_code == 400
        assert "15 weeks" in response.json()["detail"]
    finally:
        cleanup_client(db, client_id)


def test_volumetrics_sc_task_closed_incomplete_counts_as_cancelled() -> None:
    db, client_id, project_id, batch_id, file_id, _ = create_dashboard_project()
    try:
        add_ticket(
            db,
            project_id,
            batch_id,
            file_id,
            "SCTASK-CLOSED-INCOMPLETE",
            "SERVICE_CATALOG_TASK",
            dt("2026-01-07T00:00:00"),
            state="Closed Incomplete",
            closed_at=dt("2026-01-12T00:00:00"),
        )
        db.commit()

        with TestClient(app) as client:
            response = client.post(
                "/api/dashboard/volumetrics/summary",
                json={
                    "project_id": str(project_id),
                    "scope": "in_scope",
                    "ticket_type": "sc_task",
                    "time_grain": "monthly",
                    "start_datetime": "2026-01-01T00:00:00+00:00",
                    "end_datetime": "2026-01-31T23:59:59+00:00",
                    "filters": {},
                },
            )
            chart_response = client.post(
                "/api/dashboard/volumetrics/created-resolved-canceled",
                json={
                    "project_id": str(project_id),
                    "scope": "in_scope",
                    "ticket_type": "sc_task",
                    "time_grain": "monthly",
                    "start_datetime": "2026-01-01T00:00:00+00:00",
                    "end_datetime": "2026-01-31T23:59:59+00:00",
                    "filters": {},
                },
            )

        assert response.status_code == 200
        summary = response.json()
        assert summary["created"]["total"] == 1
        assert summary["resolved_closed"]["total"] == 0
        assert summary["cancelled"]["total"] == 1
        assert summary["cancelled"]["cancelled_pct_of_resolved_cancelled"] == 100
        assert summary["response_sla"]["average_adherence_pct"] is None
        assert summary["resolution_sla"]["average_adherence_pct"] is None
        assert chart_response.status_code == 200
        chart_point = chart_response.json()["points"][0]
        assert chart_point["resolved_closed_count"] == 0
        assert chart_point["canceled_closed_incomplete_count"] == 1
    finally:
        cleanup_client(db, client_id)


def test_created_resolved_open_monthly_uses_count_a_plus_count_b() -> None:
    db, client_id, project_id, batch_id, file_id, app_dimension_id = create_dashboard_project()
    try:
        add_ticket(
            db,
            project_id,
            batch_id,
            file_id,
            "INC-COUNT-A",
            "INCIDENT",
            dt("2026-01-10T00:00:00"),
            state="Resolved",
            resolved_at=dt("2026-02-03T00:00:00"),
            application_dimension_id=app_dimension_id,
        )
        add_ticket(
            db,
            project_id,
            batch_id,
            file_id,
            "INC-COUNT-B",
            "INCIDENT",
            dt("2026-01-20T00:00:00"),
            state="In Progress",
            application_dimension_id=app_dimension_id,
        )
        db.commit()

        with TestClient(app) as client:
            response = client.get(
                "/api/dashboard/trends/created-resolved-open",
                params={
                    "project_id": str(project_id),
                    "start_date": "2026-01-01",
                    "end_date": "2026-02-28",
                    "time_grain": "MONTHLY",
                },
            )

        assert response.status_code == 200
        rows = response.json()
        assert rows[0]["period_label"] == "2026-01"
        assert rows[0]["created_count"] == 2
        assert rows[0]["resolved_count"] == 0
        assert rows[0]["open_end_count"] == 2
        assert rows[1]["period_label"] == "2026-02"
        assert rows[1]["resolved_count"] == 1
        assert rows[1]["open_end_count"] == 1
    finally:
        cleanup_client(db, client_id)


def test_incident_resolved_count_uses_resolved_at_only() -> None:
    db, client_id, project_id, batch_id, file_id, _ = create_dashboard_project()
    try:
        add_ticket(
            db,
            project_id,
            batch_id,
            file_id,
            "INC-RESOLVED-ONLY",
            "INCIDENT",
            dt("2026-01-01T00:00:00"),
            state="Closed",
            resolved_at=dt("2026-02-01T00:00:00"),
            closed_at=dt("2026-01-15T00:00:00"),
        )
        db.commit()

        with TestClient(app) as client:
            response = client.get(
                "/api/dashboard/trends/created-resolved-open",
                params={
                    "project_id": str(project_id),
                    "start_date": "2026-01-01",
                    "end_date": "2026-02-28",
                },
            )

        rows = response.json()
        assert rows[0]["resolved_count"] == 0
        assert rows[1]["resolved_count"] == 1
    finally:
        cleanup_client(db, client_id)


def test_sc_task_resolved_count_uses_closed_at_only() -> None:
    db, client_id, project_id, batch_id, file_id, _ = create_dashboard_project()
    try:
        add_ticket(
            db,
            project_id,
            batch_id,
            file_id,
            "SCTASK-CLOSED-ONLY",
            "SERVICE_CATALOG_TASK",
            dt("2026-01-01T00:00:00"),
            state="Closed",
            resolved_at=dt("2026-01-10T00:00:00"),
            closed_at=dt("2026-02-02T00:00:00"),
        )
        db.commit()

        with TestClient(app) as client:
            response = client.get(
                "/api/dashboard/trends/created-resolved-open",
                params={
                    "project_id": str(project_id),
                    "start_date": "2026-01-01",
                    "end_date": "2026-02-28",
                },
            )

        rows = response.json()
        assert rows[0]["resolved_count"] == 0
        assert rows[1]["resolved_count"] == 1
    finally:
        cleanup_client(db, client_id)


def test_mttr_actual_days_for_incidents_and_business_days() -> None:
    db, client_id, project_id, batch_id, file_id, _ = create_dashboard_project()
    try:
        add_ticket(
            db,
            project_id,
            batch_id,
            file_id,
            "INC-MTTR",
            "INCIDENT",
            dt("2026-01-01T00:00:00"),
            resolved_at=dt("2026-01-03T00:00:00"),
            business_duration_seconds=86400,
        )
        db.commit()

        with TestClient(app) as client:
            response = client.get(
                "/api/dashboard/trends/mttr",
                params={"project_id": str(project_id), "month_key": "2026-01"},
            )

        row = response.json()[0]
        assert row["completed_ticket_count"] == 1
        assert row["mttr_actual_days"] == 2
        assert row["mttr_business_days"] == 1
    finally:
        cleanup_client(db, client_id)


def test_mttr_actual_days_for_sc_tasks_uses_closed_at() -> None:
    db, client_id, project_id, batch_id, file_id, _ = create_dashboard_project()
    try:
        add_ticket(
            db,
            project_id,
            batch_id,
            file_id,
            "SCTASK-MTTR",
            "SERVICE_CATALOG_TASK",
            dt("2026-01-01T00:00:00"),
            resolved_at=dt("2026-01-02T00:00:00"),
            closed_at=dt("2026-01-04T00:00:00"),
            business_duration_seconds=172800,
        )
        db.commit()

        with TestClient(app) as client:
            response = client.get(
                "/api/dashboard/trends/mttr",
                params={"project_id": str(project_id), "month_key": "2026-01"},
            )

        row = response.json()[0]
        assert row["completed_ticket_count"] == 1
        assert row["mttr_actual_days"] == 3
        assert row["mttr_business_days"] == 2
    finally:
        cleanup_client(db, client_id)


def test_sla_trend_uses_normalized_sla_breached_only() -> None:
    db, client_id, project_id, batch_id, file_id, _ = create_dashboard_project()
    try:
        add_ticket(
            db,
            project_id,
            batch_id,
            file_id,
            "INC-SLA-MET",
            "INCIDENT",
            dt("2026-01-05T00:00:00"),
            sla_breached=False,
        )
        add_ticket(
            db,
            project_id,
            batch_id,
            file_id,
            "INC-SLA-BREACHED",
            "INCIDENT",
            dt("2026-01-06T00:00:00"),
            sla_breached=True,
        )
        db.commit()

        with TestClient(app) as client:
            response = client.get(
                "/api/dashboard/trends/sla",
                params={"project_id": str(project_id), "month_key": "2026-01"},
            )

        row = response.json()[0]
        assert row["total_tickets_with_sla"] == 2
        assert row["sla_met_count"] == 1
        assert row["sla_breached_count"] == 1
    finally:
        cleanup_client(db, client_id)


def test_reopen_and_reassignment_trends() -> None:
    db, client_id, project_id, batch_id, file_id, _ = create_dashboard_project()
    try:
        add_ticket(
            db,
            project_id,
            batch_id,
            file_id,
            "INC-REOPEN",
            "INCIDENT",
            dt("2026-01-05T00:00:00"),
            reopen_count=2,
            reassignment_count=3,
        )
        db.commit()

        with TestClient(app) as client:
            reopen_response = client.get(
                "/api/dashboard/trends/reopen-count",
                params={"project_id": str(project_id), "month_key": "2026-01"},
            )
            reassignment_response = client.get(
                "/api/dashboard/trends/reassignment-count",
                params={"project_id": str(project_id), "month_key": "2026-01"},
            )

        reopen_row = reopen_response.json()[0]
        reassignment_row = reassignment_response.json()[0]
        assert reopen_row["reopened_ticket_count"] == 1
        assert reopen_row["total_reopen_count"] == 2
        assert reassignment_row["tickets_with_more_than_2_reassignments"] == 1
        assert reassignment_row["total_reassignment_count"] == 3
    finally:
        cleanup_client(db, client_id)


def test_creation_source_trend_without_llm() -> None:
    db, client_id, project_id, batch_id, file_id, _ = create_dashboard_project()
    try:
        add_ticket(
            db,
            project_id,
            batch_id,
            file_id,
            "INC-SYSTEM",
            "INCIDENT",
            dt("2026-01-05T00:00:00"),
            is_system_created=True,
        )
        add_ticket(
            db,
            project_id,
            batch_id,
            file_id,
            "INC-USER",
            "INCIDENT",
            dt("2026-01-06T00:00:00"),
            is_system_created=False,
        )
        add_ticket(
            db,
            project_id,
            batch_id,
            file_id,
            "INC-UNKNOWN",
            "INCIDENT",
            dt("2026-01-07T00:00:00"),
        )
        db.commit()

        with TestClient(app) as client:
            response = client.get(
                "/api/dashboard/trends/creation-source",
                params={"project_id": str(project_id), "month_key": "2026-01"},
            )

        row = response.json()[0]
        assert row["system_created_count"] == 1
        assert row["user_created_count"] == 1
        assert row["unknown_count"] == 1
    finally:
        cleanup_client(db, client_id)


def test_technical_functional_breakdown_for_incidents_only() -> None:
    db, client_id, project_id, batch_id, file_id, _ = create_dashboard_project()
    try:
        add_ticket(
            db,
            project_id,
            batch_id,
            file_id,
            "INC-TECH",
            "INCIDENT",
            dt("2026-01-05T00:00:00"),
            technical_functional_type="TECHNICAL",
        )
        add_ticket(
            db,
            project_id,
            batch_id,
            file_id,
            "INC-FUNC",
            "INCIDENT",
            dt("2026-01-06T00:00:00"),
            is_technical=False,
        )
        add_ticket(
            db,
            project_id,
            batch_id,
            file_id,
            "INC-UNKNOWN-TF",
            "INCIDENT",
            dt("2026-01-07T00:00:00"),
        )
        add_ticket(
            db,
            project_id,
            batch_id,
            file_id,
            "SCTASK-NOT-APPLICABLE",
            "SERVICE_CATALOG_TASK",
            dt("2026-01-07T00:00:00"),
        )
        db.commit()

        with TestClient(app) as client:
            response = client.get(
                "/api/dashboard/breakdowns/technical-functional",
                params={"project_id": str(project_id)},
            )

        payload = response.json()
        assert payload["technical_count"] == 1
        assert payload["functional_count"] == 1
        assert payload["unknown_count"] == 1
        assert payload["not_applicable_count"] == 1
    finally:
        cleanup_client(db, client_id)


def test_filter_values_endpoint_and_multi_select_filters() -> None:
    db, client_id, project_id, batch_id, file_id, app_dimension_id = create_dashboard_project()
    try:
        add_ticket(
            db,
            project_id,
            batch_id,
            file_id,
            "INC-P1",
            "INCIDENT",
            dt("2026-01-05T00:00:00"),
            priority="P1",
            state="Open",
            assignment_group="AMS",
            application="Payroll",
            application_dimension_id=app_dimension_id,
        )
        add_ticket(
            db,
            project_id,
            batch_id,
            file_id,
            "SCTASK-P2",
            "SERVICE_CATALOG_TASK",
            dt("2026-01-06T00:00:00"),
            priority="P2",
            state="Closed",
            assignment_group="Catalog",
            application="Payroll",
            application_dimension_id=app_dimension_id,
        )
        db.commit()

        with TestClient(app) as client:
            values_response = client.get(
                "/api/dashboard/filter-values",
                params={"project_id": str(project_id)},
            )
            filtered_response = client.get(
                "/api/dashboard/trends/reopen-count",
                params=[
                    ("project_id", str(project_id)),
                    ("month_key", "2026-01"),
                    ("ticket_type", "INCIDENT,SERVICE_CATALOG_TASK"),
                    ("priority", "P1"),
                    ("priority", "P2"),
                ],
            )

        values = values_response.json()
        assert values["ticket_types"] == ["INCIDENT", "SERVICE_CATALOG_TASK"]
        assert values["priorities"] == ["P1", "P2"]
        assert values["customers"] == ["Customer A"]
        assert values["application_names"] == ["Payroll"]
        assert filtered_response.json()[0]["total_tickets"] == 2
    finally:
        cleanup_client(db, client_id)


def test_filter_values_handles_large_raw_payload_without_loading_full_json() -> None:
    db, client_id, project_id, batch_id, file_id, app_dimension_id = create_dashboard_project()
    try:
        add_ticket(
            db,
            project_id,
            batch_id,
            file_id,
            "INC-LARGE-PAYLOAD",
            "INCIDENT",
            dt("2026-01-05T00:00:00"),
            resolved_at=dt("2026-01-06T00:00:00"),
            priority="P2",
            state="Resolved",
            assignment_group="AMS",
            application="Payroll",
            application_dimension_id=app_dimension_id,
            sla_breached=False,
            reopen_count=1,
            reassignment_count=3,
            business_duration_seconds=7200,
            is_system_created=True,
            technical_functional_type="TECHNICAL",
            raw_payload={
                "made_sla": "true",
                "work_notes": "large payload note " * 5_000,
            },
        )
        db.commit()

        with TestClient(app) as client:
            params = {
                "project_id": str(project_id),
                "ticket_type": "INCIDENT",
                "start_date": "2026-01-01",
                "end_date": "2026-01-31",
            }
            responses = {
                endpoint: client.get(endpoint, params=params)
                for endpoint in [
                    "/api/dashboard/filter-values",
                    "/api/dashboard/trends/created-resolved-open",
                    "/api/dashboard/trends/mttr",
                    "/api/dashboard/trends/sla",
                    "/api/dashboard/trends/reopen-count",
                    "/api/dashboard/trends/reassignment-count",
                    "/api/dashboard/trends/creation-source",
                    "/api/dashboard/breakdowns/technical-functional",
                ]
            }

        assert all(response.status_code == 200 for response in responses.values())
        payload = responses["/api/dashboard/filter-values"].json()
        assert payload["ticket_types"] == ["INCIDENT"]
        assert payload["priorities"] == ["P2"]
        assert payload["states"] == ["Resolved"]
        assert payload["assignment_groups"] == ["AMS"]
        assert len(responses["/api/dashboard/trends/created-resolved-open"].json()) == 1
        assert responses["/api/dashboard/trends/sla"].json()[0]["sla_met_count"] == 1
        assert (
            responses["/api/dashboard/breakdowns/technical-functional"].json()[
                "technical_count"
            ]
            == 1
        )
    finally:
        cleanup_client(db, client_id)


def test_dashboard_service_does_not_reference_normalized_payload() -> None:
    source = inspect.getsource(dashboard_service)
    assert "normalized_payload" not in source
    assert "load_dashboard_tickets" not in source


def test_zero_result_behavior() -> None:
    db, client_id, project_id, _, _, _ = create_dashboard_project()
    try:
        with TestClient(app) as client:
            response = client.get(
                "/api/dashboard/trends/mttr",
                params={
                    "project_id": str(project_id),
                    "ticket_type": "INCIDENT",
                    "priority": "P9",
                },
            )

        assert response.status_code == 200
        assert response.json() == []
    finally:
        cleanup_client(db, client_id)
