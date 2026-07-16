from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select

from app.db.session import SessionLocal
from app.main import app
from app.models import (
    AssessmentChangeRecord,
    AssessmentProblemRecord,
    Client,
    DashboardFilterFact,
    Project,
    Ticket,
    UploadBatch,
    UploadedFile,
)
from app.services.dashboard_filter_facts import refresh_dashboard_filter_facts


def dt(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=UTC)


def create_project_fixture():
    db = SessionLocal()
    suffix = uuid4().hex[:12]
    client = Client(name=f"Filter Fact Client {suffix}", code=f"FFC-{suffix}")
    db.add(client)
    db.flush()

    project = Project(
        client_id=client.id,
        name=f"Filter Fact Project {suffix}",
        code=f"FFP-{suffix}",
    )
    db.add(project)
    db.flush()

    batch = UploadBatch(
        project_id=project.id,
        month_key="2026-01",
        batch_name=f"Filter Fact Batch {suffix}",
        status="NORMALIZED",
        file_count=1,
        total_size_bytes=1,
    )
    db.add(batch)
    db.flush()

    uploaded_file = UploadedFile(
        upload_batch_id=batch.id,
        project_id=project.id,
        ticket_type="INCIDENT",
        original_filename="filter-facts.csv",
        saved_filename="filter-facts.csv",
        storage_path="C:\\temp\\filter-facts.csv",
        size_bytes=1,
        status="INGESTED",
    )
    db.add(uploaded_file)
    db.flush()
    db.commit()
    return db, client.id, project.id, batch.id, uploaded_file.id


def cleanup_client(db, client_id: UUID) -> None:
    db.rollback()
    db.execute(delete(Client).where(Client.id == client_id))
    db.commit()
    db.close()


def add_ticket(
    db,
    project_id: UUID,
    batch_id: UUID,
    file_id: UUID,
    number: str,
    ticket_type: str,
    *,
    created_at: datetime,
    resolved_at: datetime | None = None,
    closed_at: datetime | None = None,
    scope: str = "in_scope",
    functional_track: str = "Track A",
    ams_owner: str = "Owner A",
    assignment_group: str = "AMS-A",
    support_lead: str = "Lead A",
    parent_application_name: str = "Parent App A",
    application_owner: str = "App Owner A",
    supported_by_vendor: str = "Vendor A",
    sap_non_sap: str = "SAP",
    architecture_type: str = "COTS",
    install_type: str = "Cloud",
    hosting_env: str = "Production",
    priority: str = "P3",
) -> None:
    common_values = {
        "project_id": project_id,
        "upload_batch_id": batch_id,
        "ticket_number": number,
        "ticket_type": ticket_type,
        "created_at": created_at,
        "resolved_at": resolved_at,
        "closed_at": closed_at,
        "state": "Closed",
        "priority": priority,
        "assignment_group": assignment_group,
        "support_lead": support_lead,
        "functional_track": functional_track,
        "ams_owner": ams_owner,
        "parent_application_name": parent_application_name,
        "application_owner": application_owner,
        "supported_by_vendor": supported_by_vendor,
        "sap_non_sap": sap_non_sap,
        "architecture_type": architecture_type,
        "install_type": install_type,
        "hosting_env": hosting_env,
    }
    db.add(
        Ticket(
            **common_values,
            uploaded_file_id=file_id,
            is_in_scope=scope != "out_of_scope",
        )
    )


def add_problem_and_change_records(db, project_id: UUID, batch_id: UUID) -> None:
    db.add(
        AssessmentProblemRecord(
            project_id=project_id,
            upload_batch_id=batch_id,
            row_fingerprint=f"problem-{uuid4().hex}",
            number=f"PRB{uuid4().hex[:8]}",
            created_at_source=dt("2026-01-10T00:00:00"),
            resolved_at=dt("2026-01-11T00:00:00"),
            functional_track="Problem Track",
            ams_owner="Problem Owner",
            sap_non_sap="SAP",
            normalized_payload={"number": "problem"},
        )
    )
    db.add(
        AssessmentChangeRecord(
            project_id=project_id,
            upload_batch_id=batch_id,
            row_fingerprint=f"change-{uuid4().hex}",
            number=f"CHG{uuid4().hex[:8]}",
            created_at_source=dt("2026-01-10T00:00:00"),
            closed_at=dt("2026-01-11T00:00:00"),
            functional_track="Change Track",
            ams_owner="Change Owner",
            sap_non_sap="Non-SAP",
            normalized_payload={"number": "change"},
        )
    )


def seed_filter_fact_records(db, project_id: UUID, batch_id: UUID, file_id: UUID) -> None:
    add_ticket(
        db,
        project_id,
        batch_id,
        file_id,
        "INC001",
        "INCIDENT",
        created_at=dt("2026-01-05T00:00:00"),
        resolved_at=dt("2026-01-06T00:00:00"),
        scope="in_scope",
        sap_non_sap="SAP",
    )
    add_ticket(
        db,
        project_id,
        batch_id,
        file_id,
        "SCT001",
        "SERVICE_CATALOG_TASK",
        created_at=dt("2026-01-06T00:00:00"),
        closed_at=dt("2026-01-07T00:00:00"),
        scope="in_scope",
        functional_track="Track B",
        ams_owner="Owner B",
        assignment_group="AMS-B",
        support_lead="Lead B",
        parent_application_name="Parent App B",
        supported_by_vendor="Vendor B",
        sap_non_sap="Non-SAP",
        hosting_env="Non-Production",
    )
    add_ticket(
        db,
        project_id,
        batch_id,
        file_id,
        "INC-OOS-001",
        "INCIDENT",
        created_at=dt("2026-01-07T00:00:00"),
        resolved_at=dt("2026-01-08T00:00:00"),
        scope="out_of_scope",
        sap_non_sap="SAP",
        hosting_env="Production",
    )
    add_ticket(
        db,
        project_id,
        batch_id,
        file_id,
        "SCT-OOS-001",
        "SERVICE_CATALOG_TASK",
        created_at=dt("2026-01-08T00:00:00"),
        closed_at=dt("2026-01-09T00:00:00"),
        scope="out_of_scope",
        functional_track="Track C",
        ams_owner="Owner C",
        assignment_group="AMS-C",
        support_lead="Lead C",
        parent_application_name="Parent App C",
        supported_by_vendor="Vendor C",
        sap_non_sap="Non-SAP",
        hosting_env="Non-Production",
    )
    add_problem_and_change_records(db, project_id, batch_id)
    db.commit()


def test_dashboard_filter_fact_refresh_excludes_problem_and_change_records() -> None:
    db, client_id, project_id, batch_id, file_id = create_project_fixture()
    try:
        seed_filter_fact_records(db, project_id, batch_id, file_id)
        result = refresh_dashboard_filter_facts(db, project_id)
        db.commit()

        assert result.rows_inserted == 4
        assert result.in_scope_rows == 2
        assert result.out_of_scope_rows == 2

        facts = list(
            db.execute(
                select(
                    DashboardFilterFact.record_source,
                    DashboardFilterFact.record_type,
                    DashboardFilterFact.scope,
                    DashboardFilterFact.functional_track_ams_owner,
                    DashboardFilterFact.assignment_group_support_owner,
                    DashboardFilterFact.hosting_env,
                ).where(DashboardFilterFact.project_id == project_id)
            ).all()
        )
        assert len(facts) == 4
        assert {row.record_source for row in facts} == {"tickets"}
        assert {row.record_type for row in facts} == {"incident", "sc_task"}
        assert {row.scope for row in facts} == {"in_scope", "out_of_scope"}
        assert all("Problem" not in row.functional_track_ams_owner for row in facts)
        assert all("Change" not in row.functional_track_ams_owner for row in facts)
        assert "Track A - Owner A" in {row.functional_track_ams_owner for row in facts}
        assert "AMS-A - Lead A" in {row.assignment_group_support_owner for row in facts}
        assert {row.hosting_env for row in facts} == {"Production", "Non-Production"}
    finally:
        cleanup_client(db, client_id)


def test_volumetrics_filter_values_use_dashboard_filter_facts() -> None:
    db, client_id, project_id, batch_id, file_id = create_project_fixture()
    try:
        seed_filter_fact_records(db, project_id, batch_id, file_id)
        refresh_dashboard_filter_facts(db, project_id)
        db.commit()

        request_body = {
            "project_id": str(project_id),
            "scope": "all",
            "ticket_type": "all",
            "time_grain": "monthly",
            "start_datetime": "2026-01-01T00:00:00+00:00",
            "end_datetime": "2026-01-31T23:59:59+00:00",
            "filters": {
                "functional_track_ams_owner": [],
                "assignment_group_support_lead": [],
                "parent_application_name": [],
                "application_owner": [],
                "supported_by_vendor": [],
                "sap_non_sap": [],
            },
        }

        with TestClient(app) as client:
            response = client.post("/api/dashboard/volumetrics/filter-values", json=request_body)

        assert response.status_code == 200
        payload = response.json()
        assert payload["source"] == "dashboard_filter_facts"
        assert {row["value"]: row["count"] for row in payload["scope"]} == {
            "all": 4,
            "in_scope": 2,
            "out_of_scope": 2,
        }
        assert {row["value"]: row["count"] for row in payload["ticket_type"]} == {
            "all": 4,
            "incident": 2,
            "sc_task": 2,
        }
        assert {row["value"]: row["count"] for row in payload["sap_non_sap"]} == {
            "Non-SAP": 2,
            "SAP": 2,
        }

        request_body["filters"]["sap_non_sap"] = ["SAP"]
        with TestClient(app) as client:
            filtered_response = client.post(
                "/api/dashboard/volumetrics/filter-values",
                json=request_body,
            )

        assert filtered_response.status_code == 200
        filtered_payload = filtered_response.json()
        assert {row["value"]: row["count"] for row in filtered_payload["ticket_type"]} == {
            "all": 2,
            "incident": 2,
            "sc_task": 0,
        }
        functional_counts = {
            row["label"]: row["count"]
            for row in filtered_payload["functional_track_ams_owner"]
        }
        assert functional_counts == {"Track A - Owner A": 2}
    finally:
        cleanup_client(db, client_id)


def test_dashboard_filter_facts_admin_refresh_endpoint() -> None:
    db, client_id, project_id, batch_id, file_id = create_project_fixture()
    try:
        seed_filter_fact_records(db, project_id, batch_id, file_id)
        assert (
            db.scalar(
                select(func.count(DashboardFilterFact.id)).where(
                    DashboardFilterFact.project_id == project_id,
                )
            )
            == 0
        )

        with TestClient(app) as client:
            response = client.post(
                "/api/admin/dashboard-filter-facts/refresh",
                json={"project_id": str(project_id)},
            )

        assert response.status_code == 200
        payload = response.json()
        assert payload["rows_inserted"] == 4
        assert payload["in_scope_rows"] == 2
        assert payload["out_of_scope_rows"] == 2
    finally:
        cleanup_client(db, client_id)
