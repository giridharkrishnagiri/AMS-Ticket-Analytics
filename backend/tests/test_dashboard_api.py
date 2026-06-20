import inspect
from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.db.session import SessionLocal
from app.main import app
from app.models import ApplicationDimension, Client, Project, Ticket, UploadBatch, UploadedFile
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
