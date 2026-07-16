from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select

from app.db.session import SessionLocal
from app.main import app
from app.models import (
    ApplicationInventoryItem,
    AssessmentOutOfScopeTicket,
    Client,
    InScopeAssignmentGroup,
    Project,
    Ticket,
    TicketRawRow,
    UploadBatch,
    UploadedFile,
)
from app.services.in_scope_assignment_groups import normalize_assignment_group_key
from app.services.mapping import apply_mapping_to_batch


def cleanup_client(db, client_id: UUID) -> None:
    db.rollback()
    db.execute(delete(Client).where(Client.id == client_id))
    db.commit()
    db.close()


def add_scope_row(
    db,
    *,
    client_id: UUID,
    project_id: UUID,
    assignment_group: str,
    functional_track: str,
    is_in_scope: bool,
) -> None:
    db.add(
        InScopeAssignmentGroup(
            client_id=client_id,
            project_id=project_id,
            assignment_group=assignment_group,
            assignment_group_key=normalize_assignment_group_key(assignment_group),
            functional_track=functional_track,
            is_in_scope=is_in_scope,
            source_filename="mvp1-scope.xlsx",
            source_row_number=1,
            is_active=True,
        )
    )


def create_project_with_batch():
    db = SessionLocal()
    suffix = uuid4().hex[:10]
    client = Client(name=f"MVP1 Test Client {suffix}", code=f"MVP1-{suffix}")
    db.add(client)
    db.flush()

    project = Project(
        client_id=client.id,
        name=f"MVP1 Test Project {suffix}",
        code=f"MVP1P-{suffix}",
    )
    db.add(project)
    db.flush()

    batch = UploadBatch(
        project_id=project.id,
        month_key="2026-07",
        batch_name=f"MVP1 Test Batch {suffix}",
        status="INGESTED",
        file_count=1,
        total_size_bytes=128,
    )
    db.add(batch)
    db.flush()

    uploaded_file = UploadedFile(
        upload_batch_id=batch.id,
        project_id=project.id,
        ticket_type="INCIDENT",
        original_filename="mvp1-incidents.csv",
        saved_filename="mvp1-incidents.csv",
        storage_path=f"C:/temp/mvp1-incidents-{suffix}.csv",
        size_bytes=128,
        status="INGESTED",
    )
    db.add(uploaded_file)
    db.flush()

    return db, client.id, project.id, batch.id, uploaded_file.id


def test_mvp1_single_table_scopes_enriches_and_deletes_selected_batch() -> None:
    db, client_id, project_id, upload_batch_id, uploaded_file_id = create_project_with_batch()
    try:
        add_scope_row(
            db,
            client_id=client_id,
            project_id=project_id,
            assignment_group="AMS Support",
            functional_track="Run Track",
            is_in_scope=True,
        )
        add_scope_row(
            db,
            client_id=client_id,
            project_id=project_id,
            assignment_group="External Support",
            functional_track="External Track",
            is_in_scope=False,
        )
        db.add(
            ApplicationInventoryItem(
                project_id=project_id,
                application_number_apm="APM-MVP1",
                parent_application_name="MVP1 Parent",
                assignment_group="AMS Support",
                business_service_ci_name="MVP1 Service",
                support_lead="MVP1 Lead",
                functional_track="Run Track",
                service_type="Managed",
                service_entitlement="Gold",
                supported_by_vendor="HCLTech",
                sap_non_sap="SAP",
                scope_status="in_scope",
                cmdb_payload={
                    "Architecture type": "Vendor Managed",
                    "Install type": "Cloud",
                },
                active=True,
                is_current=True,
                source_filename="mvp1-cmdb.xlsx",
                source_row_number=2,
            )
        )
        for row_number, raw_data in enumerate(
            [
                {
                    "number": "INC-MVP1-IN",
                    "short_description": "In scope incident",
                    "state": "Resolved",
                    "assignment_group": "AMS Support",
                    "business_service": "MVP1 Service",
                    "sys_created_on": "2026-07-01 10:00:00",
                    "resolved_at": "2026-07-01 12:00:00",
                },
                {
                    "number": "INC-MVP1-OUT",
                    "short_description": "Out of scope incident",
                    "state": "Open",
                    "assignment_group": "External Support",
                    "business_service": "MVP1 Service",
                    "sys_created_on": "2026-07-02 10:00:00",
                },
            ],
            start=2,
        ):
            db.add(
                TicketRawRow(
                    project_id=project_id,
                    upload_batch_id=upload_batch_id,
                    uploaded_file_id=uploaded_file_id,
                    ticket_type="INCIDENT",
                    row_number=row_number,
                    source_filename="mvp1-incidents.csv",
                    raw_ticket_number=str(raw_data["number"]),
                    raw_data=raw_data,
                    row_hash=uuid4().hex,
                )
            )
        db.commit()

        result = apply_mapping_to_batch(
            db,
            upload_batch_id,
            {
                "ticket_id": "number",
                "title": "short_description",
                "status": "state",
                "assignment_group": "assignment_group",
                "business_service": "business_service",
                "created_at": "sys_created_on",
                "resolved_at": "resolved_at",
            },
        )

        assert result.normalized_ticket_count == 1
        assert result.out_of_scope_ticket_count == 1
        assert (
            db.scalar(
                select(func.count(AssessmentOutOfScopeTicket.id)).where(
                    AssessmentOutOfScopeTicket.project_id == project_id
                )
            )
            == 0
        )

        tickets = {
            ticket.ticket_number: ticket
            for ticket in db.scalars(
                select(Ticket).where(Ticket.upload_batch_id == upload_batch_id)
            ).all()
        }
        assert tickets["INC-MVP1-IN"].is_in_scope is True
        assert tickets["INC-MVP1-OUT"].is_in_scope is False
        assert tickets["INC-MVP1-IN"].functional_track == "Run Track"
        assert tickets["INC-MVP1-OUT"].functional_track == "External Track"
        assert tickets["INC-MVP1-IN"].service_type == "Managed"
        assert tickets["INC-MVP1-IN"].service_entitlement == "Gold"
        assert tickets["INC-MVP1-IN"].ams_owner is None

        with TestClient(app) as client:
            response = client.delete(f"/api/uploads/batches/{upload_batch_id}")

        assert response.status_code == 200
        db.expire_all()
        deleted_ticket_count = db.scalar(
            select(func.count(Ticket.id)).where(Ticket.upload_batch_id == upload_batch_id)
        )
        assert deleted_ticket_count == 0
    finally:
        cleanup_client(db, client_id)
