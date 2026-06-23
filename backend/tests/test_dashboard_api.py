import inspect
from datetime import UTC, datetime
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
) -> Ticket:
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
        short_description=f"{number} title",
        state=state,
        priority=priority,
        assignment_group=assignment_group,
        application=application,
        sla_breached=sla_breached,
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
    cmdb_payload: dict[str, object] | None = None,
) -> ApplicationInventoryItem:
    item = ApplicationInventoryItem(
        project_id=project_id,
        business_service_ci_name=business_service_ci_name,
        supported_by_vendor=supported_by_vendor,
        functional_track=functional_track,
        ams_owner=ams_owner,
        assignment_group=assignment_group,
        application_owner=application_owner,
        parent_application_name=parent_application_name,
        active=active,
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
            resolved_at=dt("2026-01-03T00:00:00"),
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
            closed_at=dt("2026-01-05T00:00:00"),
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
        assert payload["tickets"]["completion_date_min"].startswith("2026-01-03")
        assert payload["tickets"]["completion_date_max"].startswith("2026-01-05")
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
            assignment_group="Group A",
            application_owner="App Owner A",
            parent_application_name="Parent A",
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
            assignment_group="Group B",
            application_owner="App Owner B",
            parent_application_name="Parent A",
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
            "Group A - (blank)",
            "Group B - (blank)",
            "Group C - (blank)",
        ]
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
        assert "cmdb_payload" not in list_payload["rows"][0]
        assert list_payload["rows"][0]["app_type"] == "Business"

        assert blank_vendor_response.status_code == 200
        blank_vendor_rows = blank_vendor_response.json()["rows"]
        assert [row["business_service_ci_name"] for row in blank_vendor_rows] == ["Service B"]

        assert chart_response.status_code == 200
        chart_payload = chart_response.json()
        assert chart_payload["operating_system"] == [
            {"label": "Linux", "count": 2},
            {"label": "Windows", "count": 1},
        ]
        assert chart_payload["sox_scope"] == [
            {"label": "In Scope", "count": 2},
            {"label": "Out of Scope", "count": 1},
        ]
        assert chart_payload["strategic"] == [
            {"label": "Yes", "count": 2},
            {"label": "No", "count": 1},
        ]
        assert lifecycle_filtered_chart_response.status_code == 200
        assert lifecycle_filtered_chart_response.json()["lifecycle_stage"] == []
        assert bad_sort_response.status_code == 400
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
        )
        incident.functional_track = "Data"
        incident.ams_owner = "Owner A"
        incident.assignment_group = "Group A"
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
        )
        sc_task.functional_track = "Data"
        sc_task.ams_owner = "Owner A"
        sc_task.assignment_group = "Group A"
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
        )
        cancelled.functional_track = "Run"
        cancelled.ams_owner = "Owner B"
        cancelled.assignment_group = "Group B"
        cancelled.support_lead = "Lead B"
        cancelled.parent_application_name = "Parent B"
        cancelled.application_owner = "App Owner B"
        cancelled.supported_by_vendor = "Vendor B"

        db.add(
            AssessmentOutOfScopeTicket(
                project_id=project_id,
                upload_batch_id=batch_id,
                ticket_number="INC-VOL-OOS",
                ticket_type="INCIDENT",
                created_at=dt("2026-01-05T00:00:00"),
                state="In Progress",
                assignment_group="Group OOS",
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
            chart_response = client.post(
                "/api/dashboard/volumetrics/created-resolved-backlog",
                json=request_body,
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

        assert chart_response.status_code == 200
        chart_payload = chart_response.json()
        assert chart_payload["average_backlog_open"] == 0.5
        assert [row["period_label"] for row in chart_payload["rows"]] == ["Jan-26", "Feb-26"]
        assert chart_payload["rows"][0]["created_count"] == 3
        assert chart_payload["rows"][0]["resolved_closed_count"] == 1
        assert chart_payload["rows"][0]["backlog_open_count"] == 1
        assert chart_payload["rows"][1]["resolved_closed_count"] == 1
        assert chart_payload["rows"][1]["backlog_open_count"] == 0

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
            "Group A - Lead A": 2,
            "Group B - Lead B": 1,
            "Group OOS - Lead OOS": 1,
        }

        assert filtered_summary_response.status_code == 200
        filtered_summary = filtered_summary_response.json()
        assert filtered_summary["created"]["total"] == 2
        assert filtered_summary["resolved_closed"]["total"] == 2
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

        assert response.status_code == 200
        summary = response.json()
        assert summary["created"]["total"] == 1
        assert summary["resolved_closed"]["total"] == 0
        assert summary["cancelled"]["total"] == 1
        assert summary["cancelled"]["cancelled_pct_of_resolved_cancelled"] == 100
        assert summary["response_sla"]["average_adherence_pct"] is None
        assert summary["resolution_sla"]["average_adherence_pct"] is None
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
