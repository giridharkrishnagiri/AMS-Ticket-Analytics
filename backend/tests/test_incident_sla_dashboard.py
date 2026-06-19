from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import delete, event

from app.db.session import SessionLocal
from app.main import app
from app.models import Client, Project, Ticket, UploadBatch, UploadedFile


def dt(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=UTC)


def create_project():
    db = SessionLocal()
    suffix = uuid4().hex[:12]
    client = Client(name=f"Incident SLA Client {suffix}", code=f"ISLA-C-{suffix}")
    db.add(client)
    db.flush()

    project = Project(
        client_id=client.id,
        name=f"Incident SLA Project {suffix}",
        code=f"ISLA-P-{suffix}",
    )
    db.add(project)
    db.flush()

    upload_batch = UploadBatch(
        project_id=project.id,
        month_key="2026-01",
        batch_name=f"Incident SLA Batch {suffix}",
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
        original_filename="incidents.csv",
        saved_filename="incidents.csv",
        storage_path="C:\\temp\\incidents.csv",
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


def add_ticket(
    db,
    project_id: UUID,
    upload_batch_id: UUID,
    uploaded_file_id: UUID,
    ticket_number: str,
    created_at: datetime,
    *,
    ticket_type: str = "INCIDENT",
    response_breached: bool | None = None,
    resolution_breached: bool | None = None,
    response_seconds: int | None = None,
    resolution_seconds: int | None = None,
    response_name: str | None = None,
    resolution_name: str | None = None,
    payload_size: int = 0,
) -> None:
    db.add(
        Ticket(
            project_id=project_id,
            upload_batch_id=upload_batch_id,
            uploaded_file_id=uploaded_file_id,
            ticket_number=ticket_number,
            ticket_type=ticket_type,
            month_key=f"{created_at:%Y-%m}",
            created_at=created_at,
            short_description=f"{ticket_number} title",
            state="Closed",
            priority="P3",
            assignment_group="AMS",
            application="Payroll",
            response_sla_breached=response_breached,
            resolution_sla_breached=resolution_breached,
            response_sla_business_elapsed_seconds=response_seconds,
            resolution_sla_business_elapsed_seconds=resolution_seconds,
            response_sla_name=response_name,
            resolution_sla_name=resolution_name,
            reopen_count=0,
            normalized_payload={"large": "x" * payload_size},
        )
    )


def seed_incident_sla_dashboard_rows(
    db,
    project_id: UUID,
    batch_id: UUID,
    file_id: UUID,
) -> None:
    add_ticket(
        db,
        project_id,
        batch_id,
        file_id,
        "INC-SLA-1",
        dt("2026-01-05T00:00:00"),
        response_breached=False,
        resolution_breached=True,
        response_seconds=3600,
        resolution_seconds=7200,
        response_name="Accenture-Gold Response P3-1hr",
        resolution_name="Default_Standard-Resolution-P3-8hr",
        payload_size=250_000,
    )
    add_ticket(
        db,
        project_id,
        batch_id,
        file_id,
        "INC-SLA-2",
        dt("2026-01-10T00:00:00"),
        response_breached=True,
        resolution_breached=False,
        response_seconds=1800,
        resolution_seconds=3600,
        response_name="Default_Standard-Response-P3-1hr",
        resolution_name="Accenture-Gold Resolution P3-8hr",
    )
    add_ticket(
        db,
        project_id,
        batch_id,
        file_id,
        "INC-SLA-3",
        dt("2026-02-02T00:00:00"),
        response_breached=False,
        resolution_breached=False,
        response_seconds=5400,
        resolution_seconds=10800,
        response_name="Accenture-Gold Response P3-1hr",
        resolution_name="Accenture-Gold Resolution P3-8hr",
    )
    add_ticket(
        db,
        project_id,
        batch_id,
        file_id,
        "INC-SLA-4",
        dt("2026-02-12T00:00:00"),
    )
    add_ticket(
        db,
        project_id,
        batch_id,
        file_id,
        "SCTASK-SLA-1",
        dt("2026-01-08T00:00:00"),
        ticket_type="SERVICE_CATALOG_TASK",
        response_breached=True,
        resolution_breached=True,
        response_seconds=10,
        resolution_seconds=20,
        response_name="SC Task Should Not Count",
        resolution_name="SC Task Should Not Count",
    )
    db.commit()


def assert_selects_do_not_include_payload(statements: list[str]) -> None:
    assert not any(
        "select" in statement
        and "normalized_payload" in statement.split("from", maxsplit=1)[0]
        for statement in statements
    )


def test_incident_sla_trend_summary_and_filter_values_are_incident_only() -> None:
    db, client_id, project_id, batch_id, file_id = create_project()
    try:
        seed_incident_sla_dashboard_rows(db, project_id, batch_id, file_id)
        captured_sql: list[str] = []

        def capture_sql(_conn, _cursor, statement, _parameters, _context, _executemany):
            captured_sql.append(str(statement).lower())

        event.listen(db.bind, "before_cursor_execute", capture_sql)
        try:
            with TestClient(app) as client:
                trend_response = client.get(
                    "/api/dashboard/trends/incident-sla",
                    params={
                        "project_id": str(project_id),
                        "time_grain": "MONTHLY",
                        "start_date": "2026-01-01",
                        "end_date": "2026-02-28",
                    },
                )
                summary_response = client.get(
                    "/api/dashboard/summary/incident-sla",
                    params={
                        "project_id": str(project_id),
                        "start_date": "2026-01-01",
                        "end_date": "2026-02-28",
                    },
                )
                filter_response = client.get(
                    "/api/dashboard/filter-values",
                    params={"project_id": str(project_id)},
                )
        finally:
            event.remove(db.bind, "before_cursor_execute", capture_sql)

        assert trend_response.status_code == 200
        trend_rows = trend_response.json()
        assert len(trend_rows) == 2
        january = trend_rows[0]
        assert january["period"] == "2026-01"
        assert january["incident_count"] == 2
        assert january["response_sla_applicable_count"] == 2
        assert january["response_sla_met_count"] == 1
        assert january["response_sla_breached_count"] == 1
        assert january["response_sla_adherence_pct"] == 50.0
        assert january["response_sla_breach_pct"] == 50.0
        assert january["response_sla_avg_business_elapsed_seconds"] == 2700.0
        assert january["response_sla_avg_business_elapsed_hours"] == 0.75
        assert january["resolution_sla_adherence_pct"] == 50.0

        february = trend_rows[1]
        assert february["incident_count"] == 2
        assert february["response_sla_applicable_count"] == 1
        assert february["resolution_sla_applicable_count"] == 1
        assert "overall_sla_adherence_pct" not in february

        assert summary_response.status_code == 200
        summary = summary_response.json()
        assert summary["incident_count"] == 4
        assert summary["response_sla_applicable_count"] == 3
        assert summary["response_sla_met_count"] == 2
        assert summary["response_sla_breached_count"] == 1
        assert round(summary["response_sla_adherence_pct"], 2) == 66.67
        assert summary["resolution_sla_applicable_count"] == 3
        assert summary["resolution_sla_met_count"] == 2
        assert summary["resolution_sla_breached_count"] == 1
        assert summary["response_accenture_count"] == 2
        assert summary["response_default_count"] == 1
        assert summary["resolution_accenture_count"] == 2
        assert summary["resolution_default_count"] == 1
        assert "overall_sla_adherence_pct" not in summary

        assert filter_response.status_code == 200
        filter_values = filter_response.json()
        assert "Accenture-Gold Response P3-1hr" in filter_values["response_sla_names"]
        assert "Default_Standard-Response-P3-1hr" in filter_values["response_sla_names"]
        assert "SC Task Should Not Count" not in filter_values["response_sla_names"]
        assert_selects_do_not_include_payload(captured_sql)
    finally:
        cleanup_client(db, client_id)


def test_incident_sla_name_breakdown_groups_response_and_resolution_names() -> None:
    db, client_id, project_id, batch_id, file_id = create_project()
    try:
        seed_incident_sla_dashboard_rows(db, project_id, batch_id, file_id)

        with TestClient(app) as client:
            response = client.get(
                "/api/dashboard/breakdowns/incident-sla-names",
                params={
                    "project_id": str(project_id),
                    "name_type": "BOTH",
                    "start_date": "2026-01-01",
                    "end_date": "2026-02-28",
                },
            )

        assert response.status_code == 200
        payload = response.json()
        response_rows = {
            row["sla_name"]: row for row in payload["response_sla_names"]
        }
        resolution_rows = {
            row["sla_name"]: row for row in payload["resolution_sla_names"]
        }
        accenture_response = response_rows["Accenture-Gold Response P3-1hr"]
        assert accenture_response["ticket_count"] == 2
        assert accenture_response["met_count"] == 2
        assert accenture_response["breached_count"] == 0
        assert accenture_response["adherence_pct"] == 100.0
        assert accenture_response["breach_pct"] == 0.0
        assert accenture_response["avg_business_elapsed_hours"] == 1.25

        default_resolution = resolution_rows["Default_Standard-Resolution-P3-8hr"]
        assert default_resolution["ticket_count"] == 1
        assert default_resolution["met_count"] == 0
        assert default_resolution["breached_count"] == 1
        assert default_resolution["adherence_pct"] == 0.0
        assert "overall_sla_adherence_pct" not in default_resolution
    finally:
        cleanup_client(db, client_id)
