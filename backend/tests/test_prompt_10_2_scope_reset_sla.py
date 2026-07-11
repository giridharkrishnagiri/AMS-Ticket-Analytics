from __future__ import annotations

import os
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.main import app
from app.models import (
    ApplicationDimension,
    ApplicationInventoryItem,
    AssessmentOutOfScopeTicket,
    Client,
    IncidentSlaRow,
    IncidentSlaUpload,
    IngestionJob,
    InScopeAssignmentGroup,
    Project,
    SourceColumnMapping,
    Ticket,
    TicketRawRow,
    UploadBatch,
    UploadedFile,
)
from app.services.in_scope_assignment_groups import normalize_assignment_group_key
from app.services.mapping import apply_mapping_to_batch


def destructive_reset_test_is_enabled() -> bool:
    database_url = get_settings().database_url.lower()
    return (
        os.environ.get("AMS_ALLOW_DESTRUCTIVE_RESET_TEST") == "1"
        and "test" in database_url
    )


def create_project():
    db = SessionLocal()
    suffix = uuid4().hex[:12]
    client = Client(name=f"Scope Client {suffix}", code=f"SCOPE-C-{suffix}")
    db.add(client)
    db.flush()

    project_row = Project(
        client_id=client.id,
        name=f"Scope Project {suffix}",
        code=f"SCOPE-P-{suffix}",
    )
    db.add(project_row)
    db.flush()

    upload_batch = UploadBatch(
        project_id=project_row.id,
        month_key="2026-06",
        batch_name=f"Scope Batch {suffix}",
        status="INGESTED",
        file_count=1,
        total_size_bytes=1,
    )
    db.add(upload_batch)
    db.flush()

    uploaded_file = UploadedFile(
        upload_batch_id=upload_batch.id,
        project_id=project_row.id,
        ticket_type="INCIDENT",
        original_filename="scope.csv",
        saved_filename="scope.csv",
        storage_path="C:\\temp\\scope.csv",
        size_bytes=1,
        status="INGESTED",
    )
    db.add(uploaded_file)
    db.flush()
    db.commit()
    return db, client.id, project_row.id, upload_batch.id, uploaded_file.id


def add_upload_artifacts(
    db,
    project_id: UUID,
    *,
    ticket_type: str,
    batch_name: str,
    filename: str,
) -> tuple[UUID, UUID]:
    upload_batch = UploadBatch(
        project_id=project_id,
        month_key="2026-06",
        batch_name=batch_name,
        status="INGESTED",
        file_count=1,
        total_size_bytes=1,
    )
    db.add(upload_batch)
    db.flush()
    uploaded_file = UploadedFile(
        upload_batch_id=upload_batch.id,
        project_id=project_id,
        ticket_type=ticket_type,
        original_filename=filename,
        saved_filename=filename,
        storage_path=f"C:\\temp\\{filename}",
        size_bytes=1,
        status="INGESTED",
    )
    db.add(uploaded_file)
    db.flush()
    db.add(
        IngestionJob(
            upload_batch_id=upload_batch.id,
            uploaded_file_id=uploaded_file.id,
            job_type="FILE_INGESTION",
            status="COMPLETED",
            rows_total=1,
            rows_processed=1,
        )
    )
    add_raw_row(
        db,
        project_id,
        upload_batch.id,
        uploaded_file.id,
        1,
        {"number": f"{ticket_type}-RAW", "sys_created_on": "2026-06-01"},
        ticket_type=ticket_type,
    )
    db.flush()
    return upload_batch.id, uploaded_file.id


def cleanup_client(db, client_id: UUID) -> None:
    db.rollback()
    db.execute(delete(Client).where(Client.id == client_id))
    db.commit()
    db.close()


def add_inventory(
    db,
    project_id: UUID,
    *,
    assignment_group: str,
    business_service: str,
    vendor: str = "HCLTech",
    active: bool | None = True,
    row_number: int = 1,
) -> ApplicationInventoryItem:
    item = ApplicationInventoryItem(
        project_id=project_id,
        application_number_apm=f"APM-{row_number}",
        parent_application_name=f"Parent {business_service}",
        assignment_group=assignment_group,
        assignment_group_owner="Group Owner",
        application_owner="Application Owner",
        business_service_ci_name=business_service,
        support_lead="Support Lead",
        functional_track="Functional Track",
        ams_owner="AMS Owner",
        supported_by_vendor=vendor,
        scope_status="in_scope",
        active=active,
        source_filename="inventory.xlsx",
        source_row_number=row_number,
    )
    db.add(item)
    db.flush()
    return item


def add_scope_reference(
    db,
    project_id: UUID,
    assignment_group: str,
    *,
    functional_track: str = "Functional Track",
) -> None:
    project = db.get(Project, project_id)
    db.add(
        InScopeAssignmentGroup(
            client_id=project.client_id if project is not None else None,
            project_id=project_id,
            assignment_group=assignment_group,
            assignment_group_key=normalize_assignment_group_key(assignment_group) or "",
            functional_track=functional_track,
            source_filename="in-scope-assignment-groups.xlsx",
            source_row_number=1,
            is_active=True,
        )
    )
    db.flush()


def add_raw_row(
    db,
    project_id: UUID,
    batch_id: UUID,
    file_id: UUID,
    row_number: int,
    raw_data: dict[str, object],
    ticket_type: str = "INCIDENT",
) -> None:
    db.add(
        TicketRawRow(
            project_id=project_id,
            upload_batch_id=batch_id,
            uploaded_file_id=file_id,
            ticket_type=ticket_type,
            row_number=row_number,
            source_filename="scope.csv",
            raw_ticket_number=str(raw_data.get("number")),
            raw_data=raw_data,
        )
    )


def add_ticket(
    db,
    project_id: UUID,
    batch_id: UUID,
    file_id: UUID,
    ticket_number: str,
    *,
    ticket_type: str = "INCIDENT",
    vendor: str | None = None,
    derived_vendor: str | None = None,
) -> Ticket:
    ticket = Ticket(
        project_id=project_id,
        upload_batch_id=batch_id,
        uploaded_file_id=file_id,
        ticket_number=ticket_number,
        ticket_type=ticket_type,
        month_key="2026-06",
        created_at=datetime(2026, 6, 1, tzinfo=UTC),
        short_description=f"{ticket_number} title",
        state="Closed",
        priority="P3",
        assignment_group="AMS In Scope",
        application="Claims Service",
        business_service="Claims Service",
        vendor=vendor,
        derived_vendor=derived_vendor,
        reopen_count=0,
    )
    db.add(ticket)
    db.flush()
    return ticket


def add_out_of_scope_ticket(
    db,
    project_id: UUID,
    batch_id: UUID,
    ticket_number: str,
    *,
    ticket_type: str = "INCIDENT",
    vendor: str | None = None,
    derived_vendor: str | None = None,
) -> AssessmentOutOfScopeTicket:
    ticket = AssessmentOutOfScopeTicket(
        project_id=project_id,
        upload_batch_id=batch_id,
        ticket_number=ticket_number,
        ticket_type=ticket_type,
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
    db.flush()
    return ticket


def add_sla_row(
    db,
    project_id: UUID,
    inc_number: str,
    target: str,
    name: str,
    *,
    breached: bool = False,
    seconds: int = 3600,
    row_number: int = 1,
) -> None:
    db.add(
        IncidentSlaRow(
            project_id=project_id,
            uploaded_file_name="sla.csv",
            source_row_number=row_number,
            inc_number=inc_number,
            taskslatable_stage="Completed",
            taskslatable_business_duration_seconds=seconds,
            taskslatable_has_breached=breached,
            taskslatable_sla_name=name,
            taskslatable_sla_target=target,
        )
    )


def add_sla_upload(db, project_id: UUID, filename: str = "sla.csv") -> None:
    db.add(
        IncidentSlaUpload(
            project_id=project_id,
            filename=filename,
            total_rows_read=1,
            inserted_rows=1,
            duplicate_rows_skipped=0,
            error_rows=0,
            status="UPLOADED",
        )
    )


def mark_ticket_sla_enriched(ticket: Ticket | AssessmentOutOfScopeTicket) -> None:
    ticket.response_sla_breached = False
    ticket.resolution_sla_breached = True
    ticket.response_sla_business_elapsed_seconds = 3600
    ticket.resolution_sla_business_elapsed_seconds = 7200
    ticket.response_sla_name = "Default Response"
    ticket.resolution_sla_name = "Default Resolution"
    ticket.response_sla_definition_name_used = "Default Response"
    ticket.resolution_sla_definition_name_used = "Default Resolution"
    ticket.response_sla_selection_source = "default"
    ticket.resolution_sla_selection_source = "default"
    ticket.response_sla_vendor_used = "Accenture"
    ticket.resolution_sla_vendor_used = "Accenture"
    ticket.response_sla_updated_at = datetime(2026, 6, 2, tzinfo=UTC)
    ticket.resolution_sla_updated_at = datetime(2026, 6, 2, tzinfo=UTC)
    ticket.sla_enriched_at = datetime(2026, 6, 2, tzinfo=UTC)


def test_scope_split_and_vendor_derivation_use_application_inventory_only() -> None:
    db, client_id, project_id, batch_id, file_id = create_project()
    try:
        add_inventory(
            db,
            project_id,
            assignment_group="AMS In Scope",
            business_service="Claims Service",
            vendor="HCLTech",
        )
        add_inventory(
            db,
            project_id,
            assignment_group="Inactive Group",
            business_service="Inactive Service",
            vendor="Inactive Vendor",
            active=False,
            row_number=2,
        )
        add_scope_reference(db, project_id, "AMS In Scope")
        db.add(
            ApplicationDimension(
                project_id=project_id,
                customer_name="Should Not Use",
                application_name="Old Dimension",
                application_alias="Old",
                business_service_alias="Missing Service",
                is_active=True,
            )
        )

        add_raw_row(
            db,
            project_id,
            batch_id,
            file_id,
            1,
            {
                "number": "INC-IN",
                "short_description": "in scope",
                "assignment_group": " ams in scope ",
                "business_service": "Claims Service",
                "scr_vendor": "Accenture",
                "sys_created_on": "2026-06-01",
            },
        )
        add_raw_row(
            db,
            project_id,
            batch_id,
            file_id,
            2,
            {
                "number": "INC-OUT",
                "short_description": "out scope",
                "assignment_group": "Missing Group",
                "business_service": "Claims Service",
                "scr_vendor": "Accenture",
                "sys_created_on": "2026-06-01",
            },
        )
        add_raw_row(
            db,
            project_id,
            batch_id,
            file_id,
            3,
            {
                "number": "INC-BLANK",
                "short_description": "blank scope",
                "assignment_group": "",
                "business_service": "Claims Service",
                "scr_vendor": "Accenture",
                "sys_created_on": "2026-06-01",
            },
        )
        add_raw_row(
            db,
            project_id,
            batch_id,
            file_id,
            4,
            {
                "number": "INC-INACTIVE",
                "short_description": "inactive scope",
                "assignment_group": "Inactive Group",
                "business_service": "Inactive Service",
                "scr_vendor": "Accenture",
                "sys_created_on": "2026-06-01",
            },
        )
        db.commit()

        result = apply_mapping_to_batch(
            db,
            batch_id,
            mapping={
                "ticket_id": "number",
                "title": "short_description",
                "assignment_group": "assignment_group",
                "business_service": "business_service",
                "application": "business_service",
                "created_at": "sys_created_on",
                "vendor": "scr_vendor",
            },
        )

        assert result.total_raw_rows == 4
        assert result.normalized_ticket_count == 1
        assert result.out_of_scope_ticket_count == 3
        assert result.blank_assignment_group_count == 1
        assert result.assignment_group_not_in_inventory_count == 2

        in_scope_ticket = db.scalar(select(Ticket).where(Ticket.ticket_number == "INC-IN"))
        assert in_scope_ticket is not None
        assert in_scope_ticket.vendor == "Accenture"
        assert in_scope_ticket.derived_vendor == "HCLTech"
        assert in_scope_ticket.support_lead == "Support Lead"
        assert in_scope_ticket.functional_track == "Functional Track"
        out_tickets = {
            row.ticket_number: row
            for row in db.scalars(
                select(AssessmentOutOfScopeTicket).where(
                    AssessmentOutOfScopeTicket.project_id == project_id
                )
            ).all()
        }
        assert set(out_tickets) == {"INC-OUT", "INC-BLANK", "INC-INACTIVE"}
        assert out_tickets["INC-OUT"].out_of_scope_reason == (
            "assignment_group_not_in_scope_reference"
        )
        assert out_tickets["INC-BLANK"].out_of_scope_reason == "blank_assignment_group"
        assert out_tickets["INC-INACTIVE"].out_of_scope_reason == (
            "assignment_group_not_in_scope_reference"
        )
        assert out_tickets["INC-OUT"].derived_vendor is None
        assert out_tickets["INC-INACTIVE"].derived_vendor is None
    finally:
        cleanup_client(db, client_id)


def test_service_catalog_vendor_maps_from_u_vendor() -> None:
    db, client_id, project_id, batch_id, file_id = create_project()
    try:
        add_inventory(
            db,
            project_id,
            assignment_group="AMS In Scope",
            business_service="Request Service",
            vendor="HCLTech",
        )
        add_scope_reference(db, project_id, "AMS In Scope")
        add_raw_row(
            db,
            project_id,
            batch_id,
            file_id,
            1,
                {
                    "number": "SCTASK-IN",
                    "short_description": "request",
                    "assignment_group": "AMS In Scope",
                    "business_service": "",
                    "cmdb_ci": "Request Service",
                    "u_vendor": "Infosys",
                    "sys_created_on": "2026-06-01",
                },
            ticket_type="SERVICE_CATALOG_TASK",
        )
        db.commit()

        result = apply_mapping_to_batch(
            db,
            batch_id,
            mapping={
                "ticket_id": "number",
                "title": "short_description",
                "assignment_group": "assignment_group",
                "business_service": "business_service",
                "configuration_item": "cmdb_ci",
                "application": "business_service",
                "created_at": "sys_created_on",
                "vendor": "u_vendor",
            },
        )

        assert result.normalized_ticket_count == 1
        ticket = db.scalar(select(Ticket).where(Ticket.ticket_number == "SCTASK-IN"))
        assert ticket is not None
        assert ticket.vendor == "Infosys"
        assert ticket.derived_vendor == "HCLTech"
    finally:
        cleanup_client(db, client_id)


def test_vendor_aware_sla_enriches_in_scope_and_out_of_scope_incidents_only() -> None:
    db, client_id, project_id, batch_id, file_id = create_project()
    try:
        add_ticket(
            db,
            project_id,
            batch_id,
            file_id,
            "INC-VENDOR",
            vendor="Accenture",
            derived_vendor="HCLTech",
        )
        add_out_of_scope_ticket(
            db,
            project_id,
            batch_id,
            "INC-DERIVED",
            vendor=None,
            derived_vendor="HCLTech",
        )
        add_ticket(
            db,
            project_id,
            batch_id,
            file_id,
            "INC-DEFAULT",
            vendor=None,
            derived_vendor=None,
        )
        add_ticket(
            db,
            project_id,
            batch_id,
            file_id,
            "SCTASK-NO-SLA",
            ticket_type="SERVICE_CATALOG_TASK",
            vendor="Accenture",
            derived_vendor="HCLTech",
        )

        add_sla_row(
            db,
            project_id,
            "INC-VENDOR",
            "Response",
            "Accenture Response SLA - P3",
            row_number=1,
        )
        add_sla_row(
            db,
            project_id,
            "INC-VENDOR",
            "Resolution",
            "Default Resolution SLA - P3",
            row_number=2,
        )
        add_sla_row(
            db,
            project_id,
            "INC-DERIVED",
            "Response",
            "HCLTech Response SLA - P3",
            row_number=3,
        )
        add_sla_row(
            db,
            project_id,
            "INC-DERIVED",
            "Resolution",
            "Default Resolution SLA - P3",
            row_number=4,
        )
        add_sla_row(
            db,
            project_id,
            "INC-DEFAULT",
            "Response",
            "Default Response SLA - P3",
            row_number=5,
        )
        add_sla_row(
            db,
            project_id,
            "INC-DEFAULT",
            "Resolution",
            "Default Resolution SLA - P3",
            row_number=6,
        )
        add_sla_row(
            db,
            project_id,
            "SCTASK-NO-SLA",
            "Response",
            "Accenture Response SLA - P3",
            row_number=7,
        )
        db.commit()

        with TestClient(app) as client:
            response = client.post(
                "/api/sla/incidents/enrich",
                json={"project_id": str(project_id), "replace_existing": True},
            )

        assert response.status_code == 200
        payload = response.json()
        assert payload["in_scope_incidents_considered"] == 2
        assert payload["out_of_scope_incidents_considered"] == 1
        assert payload["response_vendor_specific_count"] == 2
        assert payload["response_default_count"] == 1
        assert payload["resolution_vendor_specific_count"] == 0
        assert payload["resolution_default_count"] == 3
        assert payload["sla_rows"]["total_rows"] == 7
        assert payload["sla_rows"]["distinct_ticket_numbers_in_sla_rows"] == 4
        assert payload["in_scope"]["incident_tickets_considered"] == 2
        assert payload["in_scope"]["incident_tickets_matched_to_sla_rows"] == 2
        assert payload["in_scope"]["incident_tickets_enriched"] == 2
        assert payload["out_of_scope"]["incident_tickets_considered"] == 1
        assert payload["out_of_scope"]["incident_tickets_matched_to_sla_rows"] == 1
        assert payload["out_of_scope"]["incident_tickets_enriched"] == 1
        assert (
            payload["unmatched"]["sla_ticket_numbers_not_found_in_scope_or_out_of_scope"]
            == 1
        )
        assert payload["unmatched"]["in_scope_incidents_without_sla_rows"] == 0
        assert payload["unmatched"]["out_of_scope_incidents_without_sla_rows"] == 0

        vendor_ticket = db.scalar(select(Ticket).where(Ticket.ticket_number == "INC-VENDOR"))
        default_ticket = db.scalar(select(Ticket).where(Ticket.ticket_number == "INC-DEFAULT"))
        sc_task = db.scalar(select(Ticket).where(Ticket.ticket_number == "SCTASK-NO-SLA"))
        out_ticket = db.scalar(
            select(AssessmentOutOfScopeTicket).where(
                AssessmentOutOfScopeTicket.ticket_number == "INC-DERIVED"
            )
        )
        assert vendor_ticket is not None
        assert default_ticket is not None
        assert sc_task is not None
        assert out_ticket is not None
        assert vendor_ticket.response_sla_name == "Accenture Response SLA - P3"
        assert vendor_ticket.response_sla_selection_source == "ticket_vendor"
        assert vendor_ticket.response_sla_vendor_used == "Accenture"
        assert vendor_ticket.resolution_sla_name == "Default Resolution SLA - P3"
        assert vendor_ticket.resolution_sla_selection_source == "fallback_default"
        assert vendor_ticket.resolution_sla_vendor_used == "Accenture"
        assert out_ticket.response_sla_name == "HCLTech Response SLA - P3"
        assert out_ticket.response_sla_selection_source == "derived_vendor"
        assert out_ticket.resolution_sla_selection_source == "fallback_default"
        assert default_ticket.response_sla_selection_source == "default"
        assert default_ticket.resolution_sla_selection_source == "default"
        assert sc_task.response_sla_name is None
        assert sc_task.response_sla_selection_source is None
    finally:
        cleanup_client(db, client_id)


@pytest.mark.skipif(
    not destructive_reset_test_is_enabled(),
    reason=(
        "The operational reset endpoint clears global operational tables. "
        "Run only against a dedicated test database with "
        "AMS_ALLOW_DESTRUCTIVE_RESET_TEST=1."
    ),
)
def test_reset_operational_data_preserves_inventory_projects_and_mappings() -> None:
    db, client_id, project_id, batch_id, file_id = create_project()
    try:
        inventory = add_inventory(
            db,
            project_id,
            assignment_group="AMS In Scope",
            business_service="Claims Service",
        )
        db.add(
            SourceColumnMapping(
                project_id=project_id,
                ticket_type="INCIDENT",
                source_column_name="number",
                normalized_field_name="ticket_id",
                is_required=True,
            )
        )
        db.add(
            ApplicationDimension(
                project_id=project_id,
                application_name="Old Dimension",
                application_alias="Old",
                is_active=True,
            )
        )
        add_ticket(db, project_id, batch_id, file_id, "INC-RESET")
        add_out_of_scope_ticket(db, project_id, batch_id, "INC-RESET-OOS")
        add_sla_row(db, project_id, "INC-RESET", "Response", "Default Response")
        db.commit()

        with TestClient(app) as client:
            wrong_response = client.post(
                "/api/admin/reset-operational-data",
                json={"confirmation": "reset"},
            )
            ok_response = client.post(
                "/api/admin/reset-operational-data",
                json={"confirmation": "RESET OPERATIONAL DATA"},
            )

        assert wrong_response.status_code == 400
        assert ok_response.status_code == 200
        payload = ok_response.json()
        assert payload["deleted_counts"]["tickets"] >= 1
        assert payload["deleted_counts"]["assessment_out_of_scope_tickets"] >= 1
        assert payload["deleted_counts"]["incident_sla_rows"] >= 1
        assert payload["deleted_counts"]["upload_batches"] >= 1
        assert payload["deleted_counts"]["application_dimensions"] >= 1

        assert db.get(Client, client_id) is not None
        assert db.get(ApplicationInventoryItem, inventory.id) is not None
        assert db.scalar(
            select(SourceColumnMapping).where(SourceColumnMapping.project_id == project_id)
        ) is not None
        assert db.scalar(select(Ticket)) is None
        assert db.scalar(select(AssessmentOutOfScopeTicket)) is None
        assert db.scalar(select(IncidentSlaRow)) is None
        assert db.scalar(select(ApplicationDimension)) is None
    finally:
        cleanup_client(db, client_id)


def test_project_operational_reset_preserves_project_inventory_and_mappings() -> None:
    db, client_id, project_id, batch_id, file_id = create_project()
    try:
        inventory = add_inventory(
            db,
            project_id,
            assignment_group="AMS In Scope",
            business_service="Claims Service",
        )
        db.add(
            SourceColumnMapping(
                project_id=project_id,
                ticket_type="INCIDENT",
                source_column_name="number",
                normalized_field_name="ticket_id",
                is_required=True,
            )
        )
        add_ticket(db, project_id, batch_id, file_id, "INC-PROJECT-RESET")
        add_out_of_scope_ticket(db, project_id, batch_id, "INC-PROJECT-RESET-OOS")
        add_sla_row(db, project_id, "INC-PROJECT-RESET", "Response", "Default Response")
        db.commit()

        with TestClient(app) as client:
            wrong_response = client.post(
                "/api/admin/projects/reset-operational-data",
                json={
                    "project_id": str(project_id),
                    "confirmation": "reset",
                },
            )
            ok_response = client.post(
                "/api/admin/projects/reset-operational-data",
                json={
                    "project_id": str(project_id),
                    "confirmation": "RESET OPERATIONAL DATA",
                    "reset_incidents": True,
                    "reset_sc_tasks": True,
                    "reset_incident_sla": True,
                },
            )

        assert wrong_response.status_code == 400
        assert ok_response.status_code == 200
        payload = ok_response.json()
        assert payload["deleted_counts"]["tickets"] == 1
        assert payload["deleted_counts"]["assessment_out_of_scope_tickets"] == 1
        assert payload["deleted_counts"]["incident_sla_rows"] == 1
        assert payload["deleted_counts"]["upload_batches"] == 1
        assert payload["reset_incidents"] is True
        assert payload["reset_sc_tasks"] is True
        assert payload["reset_incident_sla"] is True

        assert db.get(Client, client_id) is not None
        assert db.get(Project, project_id) is not None
        assert db.get(ApplicationInventoryItem, inventory.id) is not None
        assert db.scalar(
            select(SourceColumnMapping).where(SourceColumnMapping.project_id == project_id)
        ) is not None
        assert db.scalar(select(Ticket).where(Ticket.project_id == project_id)) is None
        assert (
            db.scalar(
                select(AssessmentOutOfScopeTicket).where(
                    AssessmentOutOfScopeTicket.project_id == project_id
                )
            )
            is None
        )
        assert db.scalar(select(UploadBatch).where(UploadBatch.project_id == project_id)) is None
    finally:
        cleanup_client(db, client_id)


def test_project_selective_reset_rejects_no_selected_category() -> None:
    db, client_id, project_id, _, _ = create_project()
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/admin/projects/reset-operational-data",
                json={
                    "project_id": str(project_id),
                    "confirmation": "RESET OPERATIONAL DATA",
                },
            )
            missing_project_response = client.post(
                "/api/admin/projects/reset-operational-data",
                json={
                    "project_id": str(uuid4()),
                    "confirmation": "RESET OPERATIONAL DATA",
                    "reset_incident_sla": True,
                },
            )

        assert response.status_code == 400
        assert "Select at least one" in response.json()["detail"]
        assert missing_project_response.status_code == 400
        assert "was not found" in missing_project_response.json()["detail"]
    finally:
        cleanup_client(db, client_id)


def test_project_sla_only_reset_preserves_tickets_uploads_inventory_and_mappings() -> None:
    db, client_id, project_id, batch_id, file_id = create_project()
    other_db, other_client_id, other_project_id, _, _ = create_project()
    other_db.close()
    try:
        inventory = add_inventory(
            db,
            project_id,
            assignment_group="AMS In Scope",
            business_service="Claims Service",
        )
        db.add(
            SourceColumnMapping(
                project_id=project_id,
                ticket_type="INCIDENT",
                source_column_name="number",
                normalized_field_name="ticket_id",
                is_required=True,
            )
        )
        incident_ticket = add_ticket(db, project_id, batch_id, file_id, "INC-SLA-ONLY")
        out_of_scope_incident = add_out_of_scope_ticket(
            db,
            project_id,
            batch_id,
            "INC-SLA-ONLY-OOS",
        )
        sc_task_ticket = add_ticket(
            db,
            project_id,
            batch_id,
            file_id,
            "SCTASK-SLA-ONLY",
            ticket_type="SERVICE_CATALOG_TASK",
        )
        mark_ticket_sla_enriched(incident_ticket)
        mark_ticket_sla_enriched(out_of_scope_incident)
        add_sla_row(db, project_id, "INC-SLA-ONLY", "Response", "Default Response")
        add_sla_upload(db, project_id)
        add_sla_row(db, other_project_id, "INC-OTHER", "Response", "Default Response")
        add_sla_upload(db, other_project_id, "other-sla.csv")
        add_raw_row(
            db,
            project_id,
            batch_id,
            file_id,
            1,
            {"number": "INC-SLA-ONLY", "sys_created_on": "2026-06-01"},
        )
        db.commit()

        with TestClient(app) as client:
            response = client.post(
                "/api/admin/projects/reset-operational-data",
                json={
                    "project_id": str(project_id),
                    "confirmation": "RESET OPERATIONAL DATA",
                    "reset_incident_sla": True,
                },
            )

        assert response.status_code == 200
        payload = response.json()
        assert payload["deleted_counts"]["incident_sla_rows"] == 1
        assert payload["deleted_counts"]["incident_sla_uploads"] == 1
        assert payload["updated_counts"]["tickets_sla_fields_cleared"] == 1
        assert payload["updated_counts"]["out_of_scope_tickets_sla_fields_cleared"] == 1
        assert payload["reset_incidents"] is False
        assert payload["reset_sc_tasks"] is False
        assert payload["reset_incident_sla"] is True

        db.expire_all()
        assert db.get(Ticket, incident_ticket.id) is not None
        assert db.get(Ticket, sc_task_ticket.id) is not None
        assert db.get(AssessmentOutOfScopeTicket, out_of_scope_incident.id) is not None
        assert db.get(ApplicationInventoryItem, inventory.id) is not None
        assert db.scalar(
            select(SourceColumnMapping).where(SourceColumnMapping.project_id == project_id)
        )
        assert db.scalar(select(TicketRawRow).where(TicketRawRow.project_id == project_id))
        assert db.scalar(select(UploadBatch).where(UploadBatch.project_id == project_id))
        assert (
            db.scalar(select(IncidentSlaRow).where(IncidentSlaRow.project_id == project_id))
            is None
        )
        assert (
            db.scalar(
                select(IncidentSlaUpload).where(IncidentSlaUpload.project_id == project_id)
            )
            is None
        )
        assert (
            db.scalar(select(IncidentSlaRow).where(IncidentSlaRow.project_id == other_project_id))
            is not None
        )
        refreshed_incident = db.get(Ticket, incident_ticket.id)
        refreshed_out_of_scope = db.get(AssessmentOutOfScopeTicket, out_of_scope_incident.id)
        assert refreshed_incident is not None
        assert refreshed_out_of_scope is not None
        assert refreshed_incident.response_sla_name is None
        assert refreshed_incident.resolution_sla_definition_name_used is None
        assert refreshed_incident.sla_enriched_at is None
        assert refreshed_out_of_scope.response_sla_name is None
        assert refreshed_out_of_scope.resolution_sla_definition_name_used is None
        assert refreshed_out_of_scope.sla_enriched_at is None
    finally:
        cleanup_client(db, client_id)
        cleanup_client(SessionLocal(), other_client_id)


def test_project_incident_reset_deletes_incidents_and_auto_resets_sla_only() -> None:
    db, client_id, project_id, batch_id, file_id = create_project()
    try:
        sc_batch_id, sc_file_id = add_upload_artifacts(
            db,
            project_id,
            ticket_type="SERVICE_CATALOG_TASK",
            batch_name="SC Task Batch",
            filename="sc.csv",
        )
        incident_ticket = add_ticket(db, project_id, batch_id, file_id, "INC-ONLY")
        add_out_of_scope_ticket(db, project_id, batch_id, "INC-ONLY-OOS")
        sc_ticket = add_ticket(
            db,
            project_id,
            sc_batch_id,
            sc_file_id,
            "SCTASK-KEPT",
            ticket_type="SERVICE_CATALOG_TASK",
        )
        mark_ticket_sla_enriched(incident_ticket)
        add_sla_row(db, project_id, "INC-ONLY", "Response", "Default Response")
        add_sla_upload(db, project_id)
        db.commit()

        with TestClient(app) as client:
            response = client.post(
                "/api/admin/projects/reset-operational-data",
                json={
                    "project_id": str(project_id),
                    "confirmation": "RESET OPERATIONAL DATA",
                    "reset_incidents": True,
                },
            )

        assert response.status_code == 200
        payload = response.json()
        assert payload["reset_incidents"] is True
        assert payload["reset_sc_tasks"] is False
        assert payload["reset_incident_sla"] is True
        assert payload["incident_sla_reset_reason"]
        assert payload["deleted_counts"]["tickets"] == 1
        assert payload["deleted_counts"]["assessment_out_of_scope_tickets"] == 1
        assert payload["deleted_counts"]["incident_sla_rows"] == 1
        assert payload["deleted_counts"]["incident_sla_uploads"] == 1
        assert db.scalar(
            select(Ticket).where(Ticket.project_id == project_id, Ticket.ticket_type == "INCIDENT")
        ) is None
        assert db.get(Ticket, sc_ticket.id) is not None
        assert db.scalar(
            select(UploadBatch).where(UploadBatch.id == batch_id)
        ) is None
        assert db.scalar(
            select(UploadBatch).where(UploadBatch.id == sc_batch_id)
        ) is not None
    finally:
        cleanup_client(db, client_id)


def test_project_sc_task_reset_preserves_incidents_and_sla_data() -> None:
    db, client_id, project_id, batch_id, file_id = create_project()
    try:
        sc_batch_id, sc_file_id = add_upload_artifacts(
            db,
            project_id,
            ticket_type="SERVICE_CATALOG_TASK",
            batch_name="SC Task Batch",
            filename="sc.csv",
        )
        incident_ticket = add_ticket(db, project_id, batch_id, file_id, "INC-KEPT")
        sc_ticket = add_ticket(
            db,
            project_id,
            sc_batch_id,
            sc_file_id,
            "SCTASK-RESET",
            ticket_type="SERVICE_CATALOG_TASK",
        )
        sc_ticket_id = sc_ticket.id
        add_out_of_scope_ticket(
            db,
            project_id,
            sc_batch_id,
            "SCTASK-RESET-OOS",
            ticket_type="SERVICE_CATALOG_TASK",
        )
        add_sla_row(db, project_id, "INC-KEPT", "Response", "Default Response")
        add_sla_upload(db, project_id)
        db.commit()

        with TestClient(app) as client:
            response = client.post(
                "/api/admin/projects/reset-operational-data",
                json={
                    "project_id": str(project_id),
                    "confirmation": "RESET OPERATIONAL DATA",
                    "reset_sc_tasks": True,
                },
            )

        assert response.status_code == 200
        payload = response.json()
        assert payload["reset_incidents"] is False
        assert payload["reset_sc_tasks"] is True
        assert payload["reset_incident_sla"] is False
        assert payload["deleted_counts"]["tickets"] == 1
        assert payload["deleted_counts"]["assessment_out_of_scope_tickets"] == 1
        assert db.get(Ticket, incident_ticket.id) is not None
        assert db.get(Ticket, sc_ticket_id) is None
        assert db.scalar(select(IncidentSlaRow).where(IncidentSlaRow.project_id == project_id))
        assert db.scalar(
            select(IncidentSlaUpload).where(IncidentSlaUpload.project_id == project_id)
        )
        assert db.scalar(select(UploadBatch).where(UploadBatch.id == batch_id)) is not None
        assert db.scalar(select(UploadBatch).where(UploadBatch.id == sc_batch_id)) is None
    finally:
        cleanup_client(db, client_id)


def test_project_and_client_delete_remove_related_configuration() -> None:
    db, client_id, project_id, batch_id, file_id = create_project()
    try:
        add_inventory(
            db,
            project_id,
            assignment_group="AMS In Scope",
            business_service="Claims Service",
        )
        db.add(
            SourceColumnMapping(
                project_id=project_id,
                ticket_type="INCIDENT",
                source_column_name="number",
                normalized_field_name="ticket_id",
                is_required=True,
            )
        )
        add_ticket(db, project_id, batch_id, file_id, "INC-PROJECT-DELETE")
        db.commit()

        with TestClient(app) as client:
            response = client.post(
                "/api/admin/projects/delete",
                json={"project_id": str(project_id), "confirmation": "DELETE PROJECT"},
            )

        assert response.status_code == 200
        payload = response.json()
        assert payload["deleted_counts"]["tickets"] == 1
        assert payload["deleted_counts"]["application_inventory_items"] == 1
        assert payload["deleted_counts"]["source_column_mappings"] == 1
        assert payload["deleted_counts"]["projects"] == 1
        assert db.get(Project, project_id) is None
        assert db.get(Client, client_id) is not None
    finally:
        cleanup_client(db, client_id)

    db, client_id, project_id, batch_id, file_id = create_project()
    try:
        add_inventory(
            db,
            project_id,
            assignment_group="AMS In Scope",
            business_service="Claims Service",
        )
        add_ticket(db, project_id, batch_id, file_id, "INC-CLIENT-DELETE")
        db.commit()

        with TestClient(app) as client:
            response = client.post(
                "/api/admin/clients/delete",
                json={"client_id": str(client_id), "confirmation": "DELETE CLIENT"},
            )

        assert response.status_code == 200
        payload = response.json()
        assert payload["deleted_counts"]["tickets"] == 1
        assert payload["deleted_counts"]["application_inventory_items"] == 1
        assert payload["deleted_counts"]["projects"] == 1
        assert payload["deleted_counts"]["clients"] == 1
        assert db.get(Project, project_id) is None
        assert db.get(Client, client_id) is None
    finally:
        cleanup_client(db, client_id)
