from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.db.session import SessionLocal
from app.main import app
from app.models import Client, Project, Ticket
from app.services.mapping import apply_mapping_to_batch


def create_project_fixture():
    db = SessionLocal()
    unique_suffix = uuid4().hex[:12]
    client = Client(
        name=f"Upload Period Client {unique_suffix}",
        code=f"UPC-{unique_suffix}",
    )
    db.add(client)
    db.flush()

    project = Project(
        client_id=client.id,
        name=f"Upload Period Project {unique_suffix}",
        code=f"UPP-{unique_suffix}",
    )
    db.add(project)
    db.commit()
    return db, client.id, project.id


def cleanup_client(db, client_id: UUID) -> None:
    db.rollback()
    db.execute(delete(Client).where(Client.id == client_id))
    db.commit()
    db.close()


def csv_upload(filename: str = "incidents.csv") -> dict[str, tuple[str, bytes, str]]:
    return {
        "files": (
            filename,
            b"number,short_description,sys_created_on\nINC-SNAP-001,Open incident,2026-06-01\n",
            "text/csv",
        )
    }


def test_monthly_upload_requires_month_key() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/uploads",
            data={
                "project_id": str(uuid4()),
                "ticket_type": "INCIDENT",
                "period_type": "MONTHLY",
                "batch_name": "Missing Month Batch",
            },
            files=csv_upload(),
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "Month-Year is required for monthly uploads."


def test_monthly_upload_succeeds_with_month_key() -> None:
    db, client_id, project_id = create_project_fixture()

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/uploads",
                data={
                    "project_id": str(project_id),
                    "ticket_type": "INCIDENT",
                    "period_type": "MONTHLY",
                    "month_key": "2026-06",
                    "batch_name": "Incidents Closed June 2026",
                },
                files=csv_upload(),
            )

        assert response.status_code == 201
        payload = response.json()
        assert payload["batch"]["period_type"] == "MONTHLY"
        assert payload["batch"]["month_key"] == "2026-06"
        assert payload["batch"]["snapshot_date"] is None
    finally:
        cleanup_client(db, client_id)


def test_snapshot_upload_succeeds_without_month_key_and_defaults_snapshot_date() -> None:
    db, client_id, project_id = create_project_fixture()
    expected_snapshot_date = datetime.now(UTC).date().isoformat()

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/uploads",
                data={
                    "project_id": str(project_id),
                    "ticket_type": "INCIDENT",
                    "period_type": "SNAPSHOT",
                    "batch_name": f"Open Incidents Snapshot - {expected_snapshot_date}",
                },
                files=csv_upload("open-incidents.csv"),
            )

        assert response.status_code == 201
        payload = response.json()
        assert payload["batch"]["period_type"] == "SNAPSHOT"
        assert payload["batch"]["month_key"] is None
        assert payload["batch"]["snapshot_date"] == expected_snapshot_date
    finally:
        cleanup_client(db, client_id)


def test_snapshot_upload_ingestion_and_mapping_work_without_month_key() -> None:
    db, client_id, project_id = create_project_fixture()

    try:
        with TestClient(app) as client:
            upload_response = client.post(
                "/api/uploads",
                data={
                    "project_id": str(project_id),
                    "ticket_type": "INCIDENT",
                    "period_type": "SNAPSHOT",
                    "snapshot_date": "2026-06-17",
                    "batch_name": "Open Incidents Snapshot - 2026-06-17",
                },
                files=csv_upload("open-incidents.csv"),
            )
            assert upload_response.status_code == 201
            upload_payload = upload_response.json()
            batch_id = upload_payload["batch"]["id"]
            uploaded_file_id = upload_payload["files"][0]["id"]

            ingest_response = client.post(f"/api/uploads/files/{uploaded_file_id}/ingest")
            assert ingest_response.status_code == 200

            preview_response = client.get(f"/api/uploads/batches/{batch_id}/raw-rows/preview")
            assert preview_response.status_code == 200
            assert preview_response.json()["rows"]

            validation_response = client.get(
                f"/api/uploads/batches/{batch_id}/validation-summary"
            )
            assert validation_response.status_code == 200
            assert validation_response.json()["total_raw_rows"] == 1

        result = apply_mapping_to_batch(
            db,
            UUID(batch_id),
            {
                "ticket_id": "number",
                "title": "short_description",
                "created_at": "sys_created_on",
            },
        )
        ticket = db.scalar(select(Ticket).where(Ticket.upload_batch_id == UUID(batch_id)))

        assert result.normalized_ticket_count == 1
        assert ticket is not None
        assert ticket.ticket_number == "INC-SNAP-001"
        assert ticket.month_key is None
        assert ticket.normalized_payload is not None
        assert ticket.normalized_payload["raw_payload_json"]["number"] == "INC-SNAP-001"
    finally:
        cleanup_client(db, client_id)
