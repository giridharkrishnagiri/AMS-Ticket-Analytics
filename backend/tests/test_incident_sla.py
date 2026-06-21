from __future__ import annotations

import inspect
from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import delete, event, func, select

from app.db.session import SessionLocal
from app.main import app
from app.models import (
    AssessmentOutOfScopeTicket,
    Client,
    IncidentSlaRow,
    IncidentSlaUpload,
    Project,
    Ticket,
    UploadBatch,
    UploadedFile,
)
from app.services import sla as sla_service


def create_sla_project():
    db = SessionLocal()
    suffix = uuid4().hex[:12]
    client = Client(name=f"SLA Client {suffix}", code=f"SLA-C-{suffix}")
    db.add(client)
    db.flush()

    project = Project(
        client_id=client.id,
        name=f"SLA Project {suffix}",
        code=f"SLA-P-{suffix}",
    )
    db.add(project)
    db.flush()

    upload_batch = UploadBatch(
        project_id=project.id,
        month_key="2026-06",
        batch_name=f"SLA Ticket Batch {suffix}",
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
    ticket_type: str = "INCIDENT",
    sla_breached: bool | None = None,
    vendor: str | None = None,
    derived_vendor: str | None = None,
) -> Ticket:
    ticket = Ticket(
        project_id=project_id,
        upload_batch_id=upload_batch_id,
        uploaded_file_id=uploaded_file_id,
        ticket_number=ticket_number,
        ticket_type=ticket_type,
        month_key="2026-06",
        created_at=datetime(2026, 6, 1, tzinfo=UTC),
        short_description=f"{ticket_number} title",
        state="Closed",
        priority="P3",
        sla_breached=sla_breached,
        vendor=vendor,
        derived_vendor=derived_vendor,
        reopen_count=0,
        normalized_payload={"raw_payload_json": {"number": ticket_number}},
    )
    db.add(ticket)
    return ticket


def add_out_of_scope_ticket(
    db,
    project_id: UUID,
    upload_batch_id: UUID,
    ticket_number: str,
    *,
    vendor: str | None = None,
    derived_vendor: str | None = None,
) -> AssessmentOutOfScopeTicket:
    ticket = AssessmentOutOfScopeTicket(
        project_id=project_id,
        upload_batch_id=upload_batch_id,
        ticket_number=ticket_number,
        ticket_type="INCIDENT",
        month_key="2026-06",
        created_at=datetime(2026, 6, 1, tzinfo=UTC),
        short_description=f"{ticket_number} title",
        state="Closed",
        priority="P3",
        assignment_group="Out Group",
        application="Claims Service",
        business_service="Claims Service",
        vendor=vendor,
        derived_vendor=derived_vendor,
        reopen_count=0,
        out_of_scope_reason="assignment_group_not_in_application_inventory",
    )
    db.add(ticket)
    return ticket


def add_sla_row(
    db,
    project_id: UUID,
    inc_number: str,
    target: str,
    sla_name: str,
    *,
    breached: bool = False,
    business_seconds: int = 3600,
    row_number: int,
    stage: str = "Completed",
) -> IncidentSlaRow:
    sla_row = IncidentSlaRow(
        project_id=project_id,
        uploaded_file_name="incident_sla.csv",
        source_row_number=row_number,
        inc_number=inc_number,
        inc_priority="P3",
        taskslatable_stage=stage,
        assignment_group_name="AMS",
        taskslatable_duration_seconds=business_seconds + 10,
        taskslatable_business_duration_seconds=business_seconds,
        taskslatable_has_breached=breached,
        taskslatable_sla_sys_name=sla_name,
        taskslatable_sla_name=sla_name,
        taskslatable_sla_type="SLA",
        taskslatable_sla_target=target,
        raw_data={
            "inc_number": inc_number,
            "taskslatable_sla.name": sla_name,
            "taskslatable_sla.target": target,
        },
    )
    db.add(sla_row)
    return sla_row


def sla_csv(rows: list[str]) -> str:
    return "\n".join(
        [
            "inc_number,inc_priority,taskslatable_stage,inc_assignment_group.name,"
            "taskslatable_duration,taskslatable_business_duration,"
            "taskslatable_has_breached,taskslatable_sla.sys_name,"
            "taskslatable_sla.name,taskslatable_sla.type,taskslatable_sla.target",
            *rows,
        ]
    )


def test_incident_sla_upload_parses_rows_and_summary_is_compact() -> None:
    db, client_id, project_id, batch_id, file_id = create_sla_project()
    try:
        add_ticket(db, project_id, batch_id, file_id, "INC100")
        db.commit()

        csv_payload = "\n".join(
            [
                "inc_number,inc_priority,taskslatable_stage,inc_assignment_group.name,"
                "taskslatable_duration,taskslatable_business_duration,"
                "taskslatable_has_breached,taskslatable_sla.sys_name,"
                "taskslatable_sla.name,taskslatable_sla.type,taskslatable_sla.target",
                "INC100,P3,Completed,AMS,120,90,false,ACC-P3,"
                "Accenture-Gold Response P3-1hr,SLA,Response",
                "INC100,P3,Completed,AMS,3600,1800,true,DEF-P3,"
                "Default_Standard-Resolution-P3-8hr,SLA,Resolution",
                ",P3,Completed,AMS,10,10,false,NO-NUMBER,Default Response,SLA,Response",
                "INC-NO-MATCH,P4,Completed,AMS,\"12,345\",\"12,345\",no,DEF-P4,"
                "Default_Standard-Response-P4-4hr,SLA,Response",
            ]
        )

        with TestClient(app) as client:
            response = client.post(
                "/api/sla/incidents/upload",
                data={"project_id": str(project_id)},
                files={"file": ("incident_sla.csv", csv_payload.encode("utf-8"), "text/csv")},
            )

        assert response.status_code == 201
        payload = response.json()
        assert payload["total_rows"] == 4
        assert payload["inserted_rows"] == 3
        assert payload["failed_rows"] == 1
        assert "inc_number is required" in payload["errors"][0]

        rows = list(
            db.scalars(
                select(IncidentSlaRow)
                .where(IncidentSlaRow.project_id == project_id)
                .order_by(IncidentSlaRow.source_row_number.asc())
            )
        )
        assert len(rows) == 3
        assert rows[0].taskslatable_has_breached is False
        assert rows[0].taskslatable_business_duration_seconds == 90
        assert rows[-1].taskslatable_business_duration_seconds == 12345
        assert rows[0].raw_data["taskslatable_sla.name"] == "Accenture-Gold Response P3-1hr"

        captured_sql: list[str] = []

        def capture_sql(_conn, _cursor, statement, _parameters, _context, _executemany):
            captured_sql.append(str(statement).lower())

        event.listen(db.bind, "before_cursor_execute", capture_sql)
        try:
            with TestClient(app) as client:
                summary_response = client.get(
                    "/api/sla/incidents/summary",
                    params={"project_id": str(project_id)},
                )
        finally:
            event.remove(db.bind, "before_cursor_execute", capture_sql)

        assert summary_response.status_code == 200
        summary = summary_response.json()
        assert summary["total_sla_rows"] == 3
        assert summary["unique_incident_numbers"] == 2
        assert summary["matched_tickets_count"] == 1
        assert summary["unmatched_sla_incident_numbers_count"] == 1
        assert not any(
            "select" in statement
            and "raw_data" in statement.split("from", maxsplit=1)[0]
            for statement in captured_sql
        )
        assert "raw_data" not in inspect.getsource(sla_service.incident_sla_summary)
    finally:
        cleanup_client(db, client_id)


def test_incident_sla_upload_skips_duplicate_rows_and_keeps_history() -> None:
    db, client_id, project_id, _batch_id, _file_id = create_sla_project()
    try:
        csv_payload = sla_csv(
            [
                "INC-DUP-1,P3,Completed,AMS,120,90,false,ACC-P3,"
                "Accenture-Gold Response P3-1hr,SLA,Response",
                "INC-DUP-2,P3,Completed,AMS,3600,1800,true,DEF-P3,"
                "Default_Standard-Resolution-P3-8hr,SLA,Resolution",
            ]
        )

        with TestClient(app) as client:
            first_response = client.post(
                "/api/sla/incidents/upload",
                data={"project_id": str(project_id)},
                files={"file": ("incident_sla.csv", csv_payload.encode("utf-8"), "text/csv")},
            )
            second_response = client.post(
                "/api/sla/incidents/upload",
                data={"project_id": str(project_id)},
                files={"file": ("incident_sla.csv", csv_payload.encode("utf-8"), "text/csv")},
            )
            history_response = client.get(
                "/api/sla/incidents/uploads",
                params={"project_id": str(project_id)},
            )

        assert first_response.status_code == 201
        first_payload = first_response.json()
        assert first_payload["inserted_rows"] == 2
        assert first_payload["duplicate_rows_skipped"] == 0
        assert first_payload["upload_id"] is not None

        assert second_response.status_code == 201
        second_payload = second_response.json()
        assert second_payload["total_rows"] == 2
        assert second_payload["inserted_rows"] == 0
        assert second_payload["duplicate_rows_skipped"] == 2
        assert second_payload["failed_rows"] == 0

        assert db.scalar(
            select(IncidentSlaRow).where(
                IncidentSlaRow.project_id == project_id,
                IncidentSlaRow.row_fingerprint.is_(None),
            )
        ) is None
        rows = list(
            db.scalars(select(IncidentSlaRow).where(IncidentSlaRow.project_id == project_id))
        )
        assert len(rows) == 2

        assert history_response.status_code == 200
        history = history_response.json()
        assert len(history) == 2
        assert sum(row["inserted_rows"] for row in history) == 2
        assert sum(row["duplicate_rows_skipped"] for row in history) == 2

        upload_rows = list(
            db.scalars(
                select(IncidentSlaUpload).where(IncidentSlaUpload.project_id == project_id)
            )
        )
        assert len(upload_rows) == 2
    finally:
        cleanup_client(db, client_id)


def test_incident_sla_multi_file_upload_deduplicates_overlapping_rows() -> None:
    db, client_id, project_id, _batch_id, _file_id = create_sla_project()
    try:
        shared_row = (
            "INC-MULTI-2,P3,Completed,AMS,3600,1800,true,DEF-P3,"
            "Default_Standard-Resolution-P3-8hr,SLA,Resolution"
        )
        first_payload = sla_csv(
            [
                "INC-MULTI-1,P3,Completed,AMS,120,90,false,ACC-P3,"
                "Accenture-Gold Response P3-1hr,SLA,Response",
                shared_row,
            ]
        )
        second_payload = sla_csv(
            [
                shared_row,
                "INC-MULTI-3,P4,Completed,AMS,240,120,false,DEF-P4,"
                "Default_Standard-Response-P4-4hr,SLA,Response",
            ]
        )

        with TestClient(app) as client:
            response = client.post(
                "/api/sla/incidents/upload-multiple",
                data={"project_id": str(project_id)},
                files=[
                    ("files", ("sla_part_1.csv", first_payload.encode("utf-8"), "text/csv")),
                    ("files", ("sla_part_2.csv", second_payload.encode("utf-8"), "text/csv")),
                ],
            )

        assert response.status_code == 201
        payload = response.json()
        assert payload["totals"] == {
            "total_files": 2,
            "total_rows_read": 4,
            "inserted_rows": 3,
            "duplicate_rows_skipped": 1,
            "error_rows": 0,
        }
        assert payload["files"][0]["inserted_rows"] == 2
        assert payload["files"][1]["inserted_rows"] == 1
        assert payload["files"][1]["duplicate_rows_skipped"] == 1
        assert (
            db.scalar(
                select(func.count(IncidentSlaRow.id)).where(
                    IncidentSlaRow.project_id == project_id
                )
            )
            == 3
        )
    finally:
        cleanup_client(db, client_id)


def test_incident_sla_upload_backfills_existing_fingerprints_before_deduplication() -> None:
    db, client_id, project_id, _batch_id, _file_id = create_sla_project()
    try:
        raw_data = {
            "inc_number": "INC-OLD-FINGERPRINT",
            "inc_priority": "P3",
            "taskslatable_stage": "Completed",
            "inc_assignment_group.name": "AMS",
            "taskslatable_duration": "120",
            "taskslatable_business_duration": "90",
            "taskslatable_has_breached": "false",
            "taskslatable_sla.sys_name": "ACC-P3",
            "taskslatable_sla.name": "Accenture-Gold Response P3-1hr",
            "taskslatable_sla.type": "SLA",
            "taskslatable_sla.target": "Response",
        }
        db.add(
            IncidentSlaRow(
                project_id=project_id,
                uploaded_file_name="legacy_sla.csv",
                source_row_number=2,
                inc_number="INC-OLD-FINGERPRINT",
                inc_priority="P3",
                taskslatable_stage="Completed",
                assignment_group_name="AMS",
                taskslatable_duration_seconds=120,
                taskslatable_business_duration_seconds=90,
                taskslatable_has_breached=False,
                taskslatable_sla_sys_name="ACC-P3",
                taskslatable_sla_name="Accenture-Gold Response P3-1hr",
                taskslatable_sla_type="SLA",
                taskslatable_sla_target="Response",
                raw_data=raw_data,
            )
        )
        db.commit()

        csv_payload = sla_csv(
            [
                "INC-OLD-FINGERPRINT,P3,Completed,AMS,120,90,false,ACC-P3,"
                "Accenture-Gold Response P3-1hr,SLA,Response",
            ]
        )

        with TestClient(app) as client:
            response = client.post(
                "/api/sla/incidents/upload",
                data={"project_id": str(project_id)},
                files={"file": ("incident_sla.csv", csv_payload.encode("utf-8"), "text/csv")},
            )

        assert response.status_code == 201
        payload = response.json()
        assert payload["inserted_rows"] == 0
        assert payload["duplicate_rows_skipped"] == 1
        assert (
            db.scalar(
                select(func.count(IncidentSlaRow.id)).where(
                    IncidentSlaRow.project_id == project_id
                )
            )
            == 1
        )
        assert db.scalar(
            select(IncidentSlaRow.row_fingerprint).where(
                IncidentSlaRow.project_id == project_id
            )
        )
    finally:
        cleanup_client(db, client_id)


def test_incident_sla_duplicate_check_is_project_scoped() -> None:
    db, client_id, project_id, _batch_id, _file_id = create_sla_project()
    other_db, other_client_id, other_project_id, _other_batch_id, _other_file_id = (
        create_sla_project()
    )
    try:
        csv_payload = sla_csv(
            [
                "INC-PROJECT-SCOPE,P3,Completed,AMS,120,90,false,ACC-P3,"
                "Accenture-Gold Response P3-1hr,SLA,Response",
            ]
        )

        with TestClient(app) as client:
            first_response = client.post(
                "/api/sla/incidents/upload",
                data={"project_id": str(project_id)},
                files={"file": ("incident_sla.csv", csv_payload.encode("utf-8"), "text/csv")},
            )
            other_response = client.post(
                "/api/sla/incidents/upload",
                data={"project_id": str(other_project_id)},
                files={"file": ("incident_sla.csv", csv_payload.encode("utf-8"), "text/csv")},
            )

        assert first_response.status_code == 201
        assert first_response.json()["inserted_rows"] == 1
        assert other_response.status_code == 201
        assert other_response.json()["inserted_rows"] == 1
        assert other_response.json()["duplicate_rows_skipped"] == 0
    finally:
        cleanup_client(db, client_id)
        cleanup_client(other_db, other_client_id)


def test_incident_sla_deduplicate_existing_rows_keeps_earliest_per_project() -> None:
    db, client_id, project_id, _batch_id, _file_id = create_sla_project()
    other_db, other_client_id, other_project_id, _other_batch_id, _other_file_id = (
        create_sla_project()
    )
    try:
        add_sla_row(
            db,
            project_id,
            "INC-DEDUP",
            "Response",
            "Default Response SLA - P3",
            row_number=1,
        )
        add_sla_row(
            db,
            project_id,
            "INC-DEDUP",
            "Response",
            "Default Response SLA - P3",
            row_number=2,
        )
        add_sla_row(
            other_db,
            other_project_id,
            "INC-DEDUP",
            "Response",
            "Default Response SLA - P3",
            row_number=1,
        )
        add_sla_row(
            other_db,
            other_project_id,
            "INC-DEDUP",
            "Response",
            "Default Response SLA - P3",
            row_number=2,
        )
        db.commit()
        other_db.commit()

        with TestClient(app) as client:
            wrong_response = client.post(
                "/api/sla/deduplicate",
                json={"project_id": str(project_id), "confirmation": "remove"},
            )
            ok_response = client.post(
                "/api/sla/deduplicate",
                json={
                    "project_id": str(project_id),
                    "confirmation": "DEDUPLICATE SLA ROWS",
                },
            )

        assert wrong_response.status_code == 400
        assert ok_response.status_code == 200
        payload = ok_response.json()
        assert payload["duplicate_groups_found"] == 1
        assert payload["duplicate_rows_deleted"] == 1
        assert payload["remaining_sla_rows"] == 1
        assert (
            db.scalar(
                select(func.count(IncidentSlaRow.id)).where(
                    IncidentSlaRow.project_id == project_id
                )
            )
            == 1
        )
        assert (
            other_db.scalar(
                select(func.count(IncidentSlaRow.id)).where(
                    IncidentSlaRow.project_id == other_project_id
                )
            )
            == 2
        )
    finally:
        cleanup_client(db, client_id)
        cleanup_client(other_db, other_client_id)


def test_incident_sla_enrichment_prefers_accenture_and_preserves_legacy_sla() -> None:
    db, client_id, project_id, batch_id, file_id = create_sla_project()
    try:
        add_ticket(
            db,
            project_id,
            batch_id,
            file_id,
            "INC-A",
            sla_breached=True,
            vendor="Accenture",
        )
        add_ticket(db, project_id, batch_id, file_id, "INC-B")
        add_ticket(db, project_id, batch_id, file_id, "INC-C", vendor="Accenture")
        sc_task = add_ticket(
            db,
            project_id,
            batch_id,
            file_id,
            "SCTASK1",
            ticket_type="SERVICE_CATALOG_TASK",
        )

        add_sla_row(
            db,
            project_id,
            "INC-A",
            "Response",
            "Default_Standard-Response-P3-1hr",
            breached=True,
            business_seconds=100,
            row_number=5,
        )
        add_sla_row(
            db,
            project_id,
            "INC-A",
            "Response",
            "Accenture-Gold Response P3-1hr",
            breached=False,
            business_seconds=60,
            row_number=10,
            stage="In Progress",
        )
        add_sla_row(
            db,
            project_id,
            "INC-A",
            "Resolution",
            "Default_Standard-Resolution-P3-8hr",
            breached=True,
            business_seconds=500,
            row_number=6,
        )
        add_sla_row(
            db,
            project_id,
            "INC-A",
            "Resolution",
            "Accenture-Gold Resolution P3-8hr",
            breached=False,
            business_seconds=400,
            row_number=7,
        )
        add_sla_row(
            db,
            project_id,
            "INC-B",
            "Response",
            "Default_Standard-Response-P4-4hr",
            breached=False,
            business_seconds=700,
            row_number=8,
        )
        add_sla_row(
            db,
            project_id,
            "INC-C",
            "Response",
            "Accenture-Gold Response P3-1hr",
            breached=False,
            business_seconds=20,
            row_number=20,
        )
        add_sla_row(
            db,
            project_id,
            "INC-C",
            "Response",
            "Accenture-Gold Response P3-1hr",
            breached=False,
            business_seconds=10,
            row_number=10,
        )
        add_sla_row(
            db,
            project_id,
            "SCTASK1",
            "Response",
            "Accenture-Gold Response P3-1hr",
            breached=True,
            business_seconds=30,
            row_number=1,
        )
        db.commit()

        with TestClient(app) as client:
            response = client.post(
                "/api/sla/incidents/enrich",
                json={
                    "project_id": str(project_id),
                    "ticket_type": "INCIDENT",
                    "replace_existing": True,
                },
            )

        assert response.status_code == 200
        payload = response.json()
        assert payload["matched_ticket_count"] == 3
        assert payload["response_sla_updated_count"] == 3
        assert payload["resolution_sla_updated_count"] == 1

        incident_a = db.scalar(
            select(Ticket).where(Ticket.project_id == project_id, Ticket.ticket_number == "INC-A")
        )
        incident_b = db.scalar(
            select(Ticket).where(Ticket.project_id == project_id, Ticket.ticket_number == "INC-B")
        )
        incident_c = db.scalar(
            select(Ticket).where(Ticket.project_id == project_id, Ticket.ticket_number == "INC-C")
        )
        db.refresh(sc_task)

        assert incident_a is not None
        assert incident_a.response_sla_name == "Accenture-Gold Response P3-1hr"
        assert incident_a.response_sla_breached is False
        assert incident_a.response_sla_business_elapsed_seconds == 60
        assert incident_a.resolution_sla_name == "Accenture-Gold Resolution P3-8hr"
        assert incident_a.resolution_sla_breached is False
        assert incident_a.resolution_sla_business_elapsed_seconds == 400
        assert incident_a.sla_breached is True

        assert incident_b is not None
        assert incident_b.response_sla_name == "Default_Standard-Response-P4-4hr"
        assert incident_b.response_sla_business_elapsed_seconds == 700

        assert incident_c is not None
        assert incident_c.response_sla_business_elapsed_seconds == 10

        assert sc_task.response_sla_name is None
        assert sc_task.response_sla_breached is None

        with TestClient(app) as client:
            summary_response = client.get(
                "/api/sla/incidents/summary",
                params={"project_id": str(project_id)},
            )
            unmatched_response = client.get(
                "/api/sla/incidents/unmatched",
                params={"project_id": str(project_id), "limit": 10},
            )

        assert summary_response.status_code == 200
        summary = summary_response.json()
        assert summary["tickets_with_response_sla_selected"] == 3
        assert summary["tickets_with_resolution_sla_selected"] == 1
        assert summary["response_accenture_selected_count"] == 2
        assert summary["response_default_selected_count"] == 1
        assert summary["resolution_accenture_selected_count"] == 1
        assert summary["response_breached_count"] == 0
        assert summary["resolution_breached_count"] == 0

        assert unmatched_response.status_code == 200
        unmatched_rows = unmatched_response.json()["rows"]
        assert unmatched_rows == [{"inc_number": "SCTASK1", "row_count": 1}]
    finally:
        cleanup_client(db, client_id)


def test_incident_sla_enrichment_rejects_sc_task_request() -> None:
    db, client_id, project_id, _batch_id, _file_id = create_sla_project()
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/sla/incidents/enrich",
                json={
                    "project_id": str(project_id),
                    "ticket_type": "SERVICE_CATALOG_TASK",
                    "replace_existing": True,
                },
            )

        assert response.status_code == 400
        assert "Only INCIDENT tickets" in response.json()["detail"]
    finally:
        cleanup_client(db, client_id)
