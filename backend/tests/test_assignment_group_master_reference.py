from __future__ import annotations

from pathlib import Path
from uuid import UUID, uuid4

from openpyxl import Workbook
from sqlalchemy import delete, select

from app.db.session import SessionLocal
from app.models import AssignmentGroupMasterReference, Client, Project
from app.services.assignment_group_master_reference import (
    assignment_group_master_reference_status,
    import_assignment_group_master_reference,
)


def create_project():
    db = SessionLocal()
    suffix = uuid4().hex[:12]
    client = Client(name=f"Master Ref Client {suffix}", code=f"MRC-{suffix}")
    db.add(client)
    db.flush()
    project = Project(
        client_id=client.id,
        name=f"Master Ref Project {suffix}",
        code=f"MRP-{suffix}",
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


def write_master_workbook(
    path: Path,
    rows: list[tuple[str | None, str | None, str | None]],
) -> None:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "Master"
    worksheet.append(["Name", "Description", "Manager"])
    for row in rows:
        worksheet.append(list(row))
    workbook.save(path)


def test_assignment_group_master_import_and_status(tmp_path: Path) -> None:
    db, client_id, project_id = create_project()
    first_path = tmp_path / "master.xlsx"
    second_path = tmp_path / "master-second.xlsx"
    write_master_workbook(
        first_path,
        [
            (" Team A ", "Description A", "Manager A"),
            ("Team B", "Description B", None),
            ("team a", "Corrected Description A", "Manager A2"),
            (None, "Skipped", "Skipped Manager"),
        ],
    )
    write_master_workbook(second_path, [("Team C", "Description C", "Manager C")])

    try:
        result = import_assignment_group_master_reference(
            db,
            project_id,
            first_path,
            first_path.name,
        )
        db.commit()
        team_a = db.scalar(
            select(AssignmentGroupMasterReference).where(
                AssignmentGroupMasterReference.project_id == project_id,
                AssignmentGroupMasterReference.assignment_group_key == "team a",
            )
        )
        status = assignment_group_master_reference_status(db, project_id)

        assert result.imported_count == 2
        assert result.manager_populated_count == 1
        assert result.skipped_count == 1
        assert result.duplicate_count == 1
        assert team_a is not None
        assert team_a.assignment_group == "team a"
        assert team_a.description == "Corrected Description A"
        assert team_a.manager_name == "Manager A2"
        assert status.active_count == 2
        assert status.manager_populated_count == 1

        second_result = import_assignment_group_master_reference(
            db,
            project_id,
            second_path,
            second_path.name,
        )
        db.commit()
        active_keys = {
            row.assignment_group_key
            for row in db.scalars(
                select(AssignmentGroupMasterReference).where(
                    AssignmentGroupMasterReference.project_id == project_id,
                    AssignmentGroupMasterReference.is_active.is_(True),
                )
            ).all()
        }

        assert second_result.imported_count == 1
        assert active_keys == {"team c"}
    finally:
        cleanup_client(db, client_id)
