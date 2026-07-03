from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from openpyxl import Workbook
from sqlalchemy import delete, select

from app.db.session import SessionLocal
from app.models import (
    ApplicationInventoryItem,
    AssessmentOutOfScopeTicket,
    AssignmentGroupMasterReference,
    Client,
    InScopeAssignmentGroup,
    Project,
    Ticket,
    TicketRawRow,
    UploadBatch,
    UploadedFile,
)
from app.services.admin_reset import prepare_operational_reprocessing
from app.services.application_inventory import upload_application_inventory_file
from app.services.in_scope_assignment_groups import (
    active_assignment_group_keys,
    import_in_scope_assignment_groups,
)
from app.services.mapping import apply_mapping_to_batch


def create_project():
    db = SessionLocal()
    suffix = uuid4().hex[:12]
    client = Client(name=f"Scope Ref Client {suffix}", code=f"SRC-{suffix}")
    db.add(client)
    db.flush()
    project = Project(
        client_id=client.id,
        name=f"Scope Ref Project {suffix}",
        code=f"SRP-{suffix}",
    )
    db.add(project)
    db.flush()
    db.commit()
    return db, client.id, project.id


def cleanup_client(db, client_id: UUID) -> None:
    db.rollback()
    db.execute(delete(Client).where(Client.id == client_id))
    db.commit()
    db.close()


def write_scope_workbook(path: Path, rows: list[tuple[str | None, str | None]]) -> None:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.append(["Assigment Groups", "Track"])
    for row in rows:
        worksheet.append(list(row))
    workbook.save(path)


def add_uploaded_raw_rows(
    db,
    project_id: UUID,
    ticket_type: str,
    rows: list[dict[str, object]],
) -> UUID:
    upload_batch = UploadBatch(
        project_id=project_id,
        month_key="2026-06",
        batch_name=f"Scope Batch {uuid4().hex[:8]}",
        status="INGESTED",
        file_count=1,
        total_size_bytes=128,
    )
    db.add(upload_batch)
    db.flush()
    uploaded_file = UploadedFile(
        upload_batch_id=upload_batch.id,
        project_id=project_id,
        ticket_type=ticket_type,
        original_filename="scope-test.csv",
        saved_filename="scope-test.csv",
        storage_path="C:\\temp\\scope-test.csv",
        size_bytes=128,
        status="INGESTED",
    )
    db.add(uploaded_file)
    db.flush()
    for index, raw_data in enumerate(rows, start=2):
        db.add(
            TicketRawRow(
                project_id=project_id,
                upload_batch_id=upload_batch.id,
                uploaded_file_id=uploaded_file.id,
                ticket_type=ticket_type,
                row_number=index,
                source_filename=uploaded_file.original_filename,
                raw_ticket_number=str(raw_data.get("number") or ""),
                raw_data=raw_data,
                row_hash=uuid4().hex,
            )
        )
    db.commit()
    return upload_batch.id


def test_scope_reference_import_supports_misspelled_header_and_keeps_last_duplicate(
    tmp_path: Path,
) -> None:
    db, client_id, project_id = create_project()
    path = tmp_path / "in_scope.xlsx"
    write_scope_workbook(
        path,
        [
            (" Team A ", "Track 1"),
            ("Team B", "Track 2"),
            ("team a", "Track 3"),
            (None, "Skipped"),
        ],
    )

    try:
        result = import_in_scope_assignment_groups(db, project_id, path, path.name)
        db.commit()
        keys = active_assignment_group_keys(db, project_id)
        row = db.scalar(
            select(InScopeAssignmentGroup).where(
                InScopeAssignmentGroup.project_id == project_id,
                InScopeAssignmentGroup.assignment_group_key == "team a",
            )
        )

        assert result.imported_count == 2
        assert result.skipped_count == 1
        assert result.duplicate_count == 1
        assert keys == {"team a", "team b"}
        assert row is not None
        assert row.functional_track == "Track 3"
    finally:
        cleanup_client(db, client_id)


def test_incident_scope_uses_cmdb_inventory_not_old_reference(tmp_path: Path) -> None:
    db, client_id, project_id = create_project()
    path = tmp_path / "scope.xlsx"
    write_scope_workbook(path, [("Reference Support", "Run")])
    rows = [
        {
            "number": "INC-SCOPE-1",
            "short_description": "In scope by reference",
            "assignment_group": "Reference Support",
            "business_service": "Unmatched Service",
            "sys_created_on": "2026-06-10",
        },
        {
            "number": "INC-SCOPE-2",
            "short_description": "Out of scope by reference",
            "assignment_group": "Inventory Support",
            "business_service": "Inventory Service",
            "sys_created_on": "2026-06-11",
        },
    ]
    mapping = {
        "ticket_id": "number",
        "title": "short_description",
        "assignment_group": "assignment_group",
        "business_service": "business_service",
        "created_at": "sys_created_on",
    }

    try:
        import_in_scope_assignment_groups(db, project_id, path, path.name)
        db.add(
            ApplicationInventoryItem(
                project_id=project_id,
                assignment_group="Inventory Support",
                business_service_ci_name="Inventory Service",
                scope_status="in_scope",
                active=True,
            )
        )
        project = db.get(Project, project_id)
        assert project is not None
        db.add(
            AssignmentGroupMasterReference(
                client_id=project.client_id,
                project_id=project_id,
                assignment_group="Inventory Support",
                assignment_group_key="inventory support",
                description="Present in ServiceNow master list",
                manager_name="Master Manager",
                source_filename="master.xlsx",
                source_sheet_name="Master",
                source_row_number=2,
                is_active=True,
            )
        )
        db.commit()
        batch_id = add_uploaded_raw_rows(db, project_id, "INCIDENT", rows)
        result = apply_mapping_to_batch(db, batch_id, mapping)
        in_scope = db.scalar(select(Ticket).where(Ticket.ticket_number == "INC-SCOPE-2"))
        out_of_scope = db.scalar(
            select(AssessmentOutOfScopeTicket).where(
                AssessmentOutOfScopeTicket.ticket_number == "INC-SCOPE-1"
            )
        )

        assert result.normalized_ticket_count == 1
        assert result.out_of_scope_ticket_count == 1
        assert in_scope is not None
        assert out_of_scope is not None
        assert out_of_scope.out_of_scope_reason == "assignment_group_not_in_scope_reference"
    finally:
        cleanup_client(db, client_id)


def test_application_inventory_upload_treats_rows_as_in_scope(
    tmp_path: Path,
) -> None:
    db, client_id, project_id = create_project()
    inventory_path = tmp_path / "inventory.csv"
    inventory_path.write_text(
        "\n".join(
            [
                "Business Service CI Name,Support Group",
                "In Scope App,AMS Scope Team",
                "Out Scope App,External Team",
                "Blank Scope App,",
            ]
        ),
        encoding="utf-8",
    )

    try:
        upload_application_inventory_file(db, project_id, inventory_path, inventory_path.name)
        rows = {
            row.business_service_ci_name: row.scope_status
            for row in db.scalars(
                select(ApplicationInventoryItem).where(
                    ApplicationInventoryItem.project_id == project_id
                )
            ).all()
        }

        assert rows["In Scope App"] == "in_scope"
        assert rows["Out Scope App"] == "in_scope"
        assert rows["Blank Scope App"] == "in_scope"
    finally:
        cleanup_client(db, client_id)


def test_reapply_mapping_preparation_preserves_raw_uploads_and_clears_applied_rows() -> None:
    db, client_id, project_id = create_project()
    try:
        batch_id = add_uploaded_raw_rows(
            db,
            project_id,
            "SERVICE_CATALOG_TASK",
            [
                {
                    "number": "SCTASK-REPROCESS-1",
                    "assignment_group": "SC Team",
                    "sys_created_on": "2026-06-01",
                }
            ],
        )
        uploaded_file = db.scalar(
            select(UploadedFile).where(UploadedFile.upload_batch_id == batch_id)
        )
        assert uploaded_file is not None
        db.add(
            Ticket(
                project_id=project_id,
                upload_batch_id=batch_id,
                uploaded_file_id=uploaded_file.id,
                ticket_number="SCTASK-REPROCESS-1",
                ticket_type="SERVICE_CATALOG_TASK",
                month_key="2026-06",
                created_at=datetime(2026, 6, 1, tzinfo=UTC),
                state="Open",
                normalized_payload={},
            )
        )
        db.commit()

        result = prepare_operational_reprocessing(
            db,
            project_id,
            ["sc_tasks"],
            "reapply_mapping_only",
            "PREPARE REPROCESSING",
        )
        raw_count = db.scalar(
            select(TicketRawRow).where(TicketRawRow.upload_batch_id == batch_id).limit(1)
        )
        ticket = db.scalar(select(Ticket).where(Ticket.ticket_number == "SCTASK-REPROCESS-1"))
        updated_batch = db.get(UploadBatch, batch_id)

        assert result.cleared_counts["tickets"] == 1
        assert raw_count is not None
        assert ticket is None
        assert uploaded_file.status == "INGESTED"
        assert updated_batch is not None
        assert updated_batch.status == "INGESTED"
    finally:
        cleanup_client(db, client_id)
