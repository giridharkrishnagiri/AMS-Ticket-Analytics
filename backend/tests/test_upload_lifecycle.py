from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.db.session import SessionLocal
from app.main import app
from app.models import Client, Project, Ticket, UploadBatch
from app.services.mapping import apply_mapping_to_batch


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
    db.commit()
    return db, client.id, project.id


def cleanup_client(db, client_id: UUID) -> None:
    db.rollback()
    db.execute(delete(Client).where(Client.id == client_id))
    db.commit()
    db.close()


def csv_upload(
    filename: str = "incidents.csv",
    body: bytes = b"number,short_description,sys_created_on\nINC-LC-001,Open incident,2026-06-01\n",
) -> dict[str, tuple[str, bytes, str]]:
    return {"files": (filename, body, "text/csv")}


def upload_monthly_batch(
    client: TestClient,
    project_id: UUID,
    batch_name: str = "Lifecycle Batch",
    file_body: bytes = (
        b"number,short_description,sys_created_on\n"
        b"INC-LC-001,Open incident,2026-06-01\n"
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


def batch_ids(payload: list[dict[str, object]]) -> set[str]:
    return {str(row["id"]) for row in payload}


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
                file_body=b"number,short_description,sys_created_on\n,Missing number,2026-06-01\n",
            )
            ingest_response = client.post(f"/api/uploads/files/{uploaded_file_id}/ingest")
            assert ingest_response.status_code == 200

        result = apply_mapping_to_batch(
            db,
            UUID(batch_id),
            {
                "ticket_id": "number",
                "title": "short_description",
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
