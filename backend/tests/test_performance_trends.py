from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import delete

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


def dt(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=UTC)


def create_project():
    db = SessionLocal()
    suffix = uuid4().hex[:12]
    client = Client(name=f"Performance Client {suffix}", code=f"PC-{suffix}")
    db.add(client)
    db.flush()
    project = Project(
        client_id=client.id,
        name=f"Performance Project {suffix}",
        code=f"PP-{suffix}",
    )
    db.add(project)
    db.flush()
    batch = UploadBatch(
        project_id=project.id,
        month_key="2026-05",
        batch_name=f"Performance Batch {suffix}",
        status="COMPLETED",
        file_count=1,
        total_size_bytes=1,
    )
    db.add(batch)
    db.flush()
    uploaded_file = UploadedFile(
        upload_batch_id=batch.id,
        project_id=project.id,
        ticket_type="INCIDENT",
        original_filename="performance.csv",
        saved_filename="performance.csv",
        storage_path="C:\\temp\\performance.csv",
        size_bytes=1,
        status="INGESTED",
    )
    db.add(uploaded_file)
    db.flush()
    db.commit()
    return db, client.id, project.id, batch.id, uploaded_file.id


def cleanup(db, client_id: UUID) -> None:
    db.rollback()
    db.execute(delete(Client).where(Client.id == client_id))
    db.commit()
    db.close()


def add_inventory(
    db,
    project_id: UUID,
    assignment_group: str,
    functional_track: str,
    *,
    is_current: bool = True,
) -> None:
    db.add(
        ApplicationInventoryItem(
            project_id=project_id,
            assignment_group=assignment_group,
            functional_track=functional_track,
            scope_status="in_scope",
            is_current=is_current,
        ),
    )


def add_ticket(
    db,
    project_id: UUID,
    batch_id: UUID,
    file_id: UUID,
    number: str,
    *,
    ticket_type: str = "INCIDENT",
    assignment_group: str = "IT-GROUP-A",
    assigned_to: str | None = "Engineer A",
    created_at: datetime | None = None,
    resolved_at: datetime | None = None,
    closed_at: datetime | None = None,
    state: str = "Resolved",
    functional_track: str | None = None,
    business_duration_seconds: int | None = None,
) -> None:
    db.add(
        Ticket(
            project_id=project_id,
            upload_batch_id=batch_id,
            uploaded_file_id=file_id,
            ticket_number=number,
            ticket_type=ticket_type,
            month_key="2026-05",
            created_at=created_at or dt("2026-05-01T00:00:00"),
            resolved_at=resolved_at or dt("2026-05-02T00:00:00"),
            closed_at=closed_at,
            state=state,
            assignment_group=assignment_group,
            assigned_to=assigned_to,
            functional_track=functional_track,
            business_duration_seconds=business_duration_seconds,
            short_description=f"{number} title",
            normalized_payload={},
        ),
    )


def performance_request(project_id: UUID, *, lookback_months: int = 3) -> dict[str, object]:
    return {
        "project_id": str(project_id),
        "scope": "all",
        "ticket_type": "all",
        "time_grain": "monthly",
        "start_datetime": "2025-01-01T00:00:00+00:00",
        "end_datetime": "2025-01-31T23:59:59+00:00",
        "lookback_months": lookback_months,
        "filters": {},
    }


def test_performance_trends_uses_latest_complete_months_and_eligible_tickets_only():
    db, client_id, project_id, batch_id, file_id = create_project()
    try:
        add_inventory(db, project_id, "IT-GROUP-A", "Old Track", is_current=False)
        add_inventory(db, project_id, "IT-GROUP-A", "Track A", is_current=True)
        add_inventory(db, project_id, "IT-GROUP-B", "Track B", is_current=True)

        add_ticket(
            db,
            project_id,
            batch_id,
            file_id,
            "INC-A-001",
            created_at=dt("2026-03-01T00:00:00"),
            resolved_at=dt("2026-03-01T12:00:00"),
            business_duration_seconds=12 * 3600,
        )
        add_ticket(
            db,
            project_id,
            batch_id,
            file_id,
            "INC-A-002",
            created_at=dt("2026-04-01T00:00:00"),
            resolved_at=dt("2026-04-03T00:00:00"),
            business_duration_seconds=2 * 86400,
        )
        add_ticket(
            db,
            project_id,
            batch_id,
            file_id,
            "INC-A-003",
            created_at=dt("2026-05-01T00:00:00"),
            resolved_at=dt("2026-05-06T00:00:00"),
            business_duration_seconds=5 * 86400,
        )
        add_ticket(
            db,
            project_id,
            batch_id,
            file_id,
            "SCT-A-004",
            ticket_type="SERVICE_CATALOG_TASK",
            created_at=dt("2026-05-01T00:00:00"),
            resolved_at=None,
            closed_at=dt("2026-05-13T00:00:00"),
            state="Closed Complete",
            business_duration_seconds=12 * 86400,
        )
        add_ticket(
            db,
            project_id,
            batch_id,
            file_id,
            "INC-B-001",
            assignment_group="IT-GROUP-B",
            assigned_to="Engineer B",
            created_at=dt("2026-05-01T00:00:00"),
            resolved_at=dt("2026-05-02T00:00:00"),
            functional_track="Ticket Track B",
        )
        add_ticket(
            db,
            project_id,
            batch_id,
            file_id,
            "INC-CANCEL",
            assigned_to="Engineer C",
            created_at=dt("2026-05-01T00:00:00"),
            resolved_at=dt("2026-05-02T00:00:00"),
            state="Canceled",
        )
        add_ticket(
            db,
            project_id,
            batch_id,
            file_id,
            "SCT-INCOMPLETE",
            ticket_type="SERVICE_CATALOG_TASK",
            assigned_to="Engineer D",
            created_at=dt("2026-05-01T00:00:00"),
            resolved_at=None,
            closed_at=dt("2026-05-02T00:00:00"),
            state="Closed Incomplete",
        )
        add_ticket(
            db,
            project_id,
            batch_id,
            file_id,
            "INC-NO-ASSIGNEE",
            assigned_to=None,
            created_at=dt("2026-05-01T00:00:00"),
            resolved_at=dt("2026-05-02T00:00:00"),
        )
        add_ticket(
            db,
            project_id,
            batch_id,
            file_id,
            "CHG-001",
            ticket_type="CHANGE",
            assigned_to="Engineer Change",
            created_at=dt("2026-05-01T00:00:00"),
            resolved_at=dt("2026-05-02T00:00:00"),
        )
        for index in range(21):
            add_ticket(
                db,
                project_id,
                batch_id,
                file_id,
                f"INC-Z-{index:02d}",
                assignment_group="IT-GROUP-B",
                assigned_to=f"Engineer Z {index:02d}",
                created_at=dt("2026-05-01T00:00:00"),
                resolved_at=dt(
                    "2026-05-31T00:00:00" if index == 20 else "2026-05-02T00:00:00",
                ),
            )
        db.commit()

        client = TestClient(app)
        response = client.post(
            "/api/dashboard/volumetrics/performance-trends",
            json=performance_request(project_id, lookback_months=3),
        )
        assert response.status_code == 200, response.text
        payload = response.json()

        assert payload["performance_period"]["from_month"] == "2026-03"
        assert payload["performance_period"]["to_month"] == "2026-05"
        assert payload["performance_period"]["months"] == 3
        assert payload["performance_period"]["working_days"] > 0

        engineer_rows = {
            row["support_engineer"]: row for row in payload["all_engineers"]
        }
        assert engineer_rows["Engineer A"]["resolved_ticket_count"] == 4
        assert engineer_rows["Engineer A"]["average_monthly_productivity"] == 1
        assert engineer_rows["Engineer A"]["primary_assignment_group"] == "IT-GROUP-A"
        assert engineer_rows["Engineer A"]["functional_track"] == "Track A"
        assert engineer_rows["Engineer B"]["functional_track"] == "Track B"
        assert "Engineer C" not in engineer_rows
        assert "Engineer D" not in engineer_rows
        assert "Engineer Change" not in engineer_rows

        breakdown = {
            row["support_engineer"]: row for row in payload["duration_breakdown"]
        }["Engineer A"]
        assert breakdown["resolved_0_1_day"] == 1
        assert breakdown["resolved_1_3_days"] == 1
        assert breakdown["resolved_3_10_days"] == 1
        assert breakdown["resolved_gt_10_days"] == 1
        assert (
            breakdown["resolved_0_1_day"]
            + breakdown["resolved_1_3_days"]
            + breakdown["resolved_3_10_days"]
            + breakdown["resolved_gt_10_days"]
        ) == breakdown["resolved_ticket_count"]

        assert len(payload["top_performers"]) == 20
        assert payload["top_performers"][-1]["cumulative_productivity_pct"] < 100
        assert len(payload["bottom_performers"]) == 20
        assert payload["bottom_performers"][-1]["bottom_up_cumulative_productivity_pct"] < 100

        response_one_month = client.post(
            "/api/dashboard/volumetrics/performance-trends",
            json=performance_request(project_id, lookback_months=1),
        )
        assert response_one_month.status_code == 200, response_one_month.text
        assert response_one_month.json()["performance_period"]["from_month"] == "2026-05"

        offline_response = client.post(
            "/api/dashboard/offline-export",
            json={"project_id": str(project_id), "format": "html"},
        )
        assert offline_response.status_code == 200, offline_response.text
        offline_document = offline_response.text
        assert "Performance Trends" in offline_document
        assert "Top 20 Performers" in offline_document
        assert "support_engineer_productivity_" in offline_document
        assert "normalized_payload" not in offline_document
        assert "cmdb_payload" not in offline_document
    finally:
        cleanup(db, client_id)
