from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models import (
    ApplicationDimension,
    ApplicationInventoryItem,
    AssessmentChangeRecord,
    AssessmentOutOfScopeTicket,
    AssessmentProblemRecord,
    Client,
    DashboardAggregate,
    ExportJob,
    IncidentSlaRow,
    IncidentSlaUpload,
    IngestionJob,
    Project,
    SourceColumnMapping,
    Ticket,
    TicketRawRow,
    UploadBatch,
    UploadedFile,
)

RESET_CONFIRMATION = "RESET OPERATIONAL DATA"
PROJECT_RESET_CONFIRMATION = "RESET PROJECT OPERATIONAL DATA"
PROJECT_DELETE_CONFIRMATION = "DELETE PROJECT"
PROJECT_DATA_RESET_CONFIRMATION = "RESET PROJECT DATA"
CLIENT_DELETE_CONFIRMATION = "DELETE CLIENT"
CUSTOMER_DATA_RESET_CONFIRMATION = "RESET CUSTOMER DATA"
PRESERVED_TABLES = [
    "clients",
    "projects",
    "source_column_mappings",
    "application_inventory_items",
    "alembic_version",
]


class AdminResetError(Exception):
    pass


@dataclass(frozen=True)
class OperationalResetResult:
    deleted_counts: dict[str, int]
    preserved: list[str]
    updated_counts: dict[str, int] | None = None
    reset_incidents: bool | None = None
    reset_sc_tasks: bool | None = None
    reset_problems: bool | None = None
    reset_changes: bool | None = None
    reset_incident_sla: bool | None = None
    incident_sla_reset_reason: str | None = None


SLA_ENRICHMENT_FIELDS = (
    "response_sla_breached",
    "resolution_sla_breached",
    "response_sla_business_elapsed_seconds",
    "resolution_sla_business_elapsed_seconds",
    "response_sla_name",
    "resolution_sla_name",
    "response_sla_definition_name_used",
    "resolution_sla_definition_name_used",
    "response_sla_selection_source",
    "resolution_sla_selection_source",
    "response_sla_vendor_used",
    "resolution_sla_vendor_used",
    "response_sla_updated_at",
    "resolution_sla_updated_at",
    "sla_enriched_at",
)


RESET_MODELS: tuple[tuple[str, Any], ...] = (
    ("dashboard_aggregates", DashboardAggregate),
    ("export_jobs", ExportJob),
    ("tickets", Ticket),
    ("assessment_out_of_scope_tickets", AssessmentOutOfScopeTicket),
    ("assessment_problem_records", AssessmentProblemRecord),
    ("assessment_change_records", AssessmentChangeRecord),
    ("incident_sla_rows", IncidentSlaRow),
    ("incident_sla_uploads", IncidentSlaUpload),
    ("ticket_raw_rows", TicketRawRow),
    ("ingestion_jobs", IngestionJob),
    ("uploaded_files", UploadedFile),
    ("upload_batches", UploadBatch),
    ("application_dimensions", ApplicationDimension),
)

PROJECT_OPERATIONAL_MODELS: tuple[tuple[str, Any], ...] = (
    ("dashboard_aggregates", DashboardAggregate),
    ("export_jobs", ExportJob),
    ("tickets", Ticket),
    ("assessment_out_of_scope_tickets", AssessmentOutOfScopeTicket),
    ("assessment_problem_records", AssessmentProblemRecord),
    ("assessment_change_records", AssessmentChangeRecord),
    ("incident_sla_rows", IncidentSlaRow),
    ("incident_sla_uploads", IncidentSlaUpload),
    ("ticket_raw_rows", TicketRawRow),
    ("uploaded_files", UploadedFile),
    ("upload_batches", UploadBatch),
    ("application_dimensions", ApplicationDimension),
)

PROJECT_CONFIGURATION_MODELS: tuple[tuple[str, Any], ...] = (
    ("source_column_mappings", SourceColumnMapping),
    ("application_inventory_items", ApplicationInventoryItem),
)

PROJECT_OPERATIONAL_PRESERVED_TABLES = [
    "clients",
    "projects",
    "source_column_mappings",
    "application_inventory_items",
    "alembic_version",
]

PROJECT_DELETE_PRESERVED_TABLES = [
    "other_clients",
    "other_projects",
    "alembic_version",
]


def count_rows(db: Session, model: Any) -> int:
    return int(db.scalar(select(func.count()).select_from(model)) or 0)


def count_project_rows(db: Session, model: Any, project_ids: list[UUID]) -> int:
    if not project_ids:
        return 0
    return int(
        db.scalar(
            select(func.count())
            .select_from(model)
            .where(model.project_id.in_(project_ids))
        )
        or 0
    )


def delete_project_rows(db: Session, model: Any, project_ids: list[UUID]) -> None:
    if not project_ids:
        return
    db.execute(delete(model).where(model.project_id.in_(project_ids)))


def upload_batch_ids_for_projects(project_ids: list[UUID]):
    return select(UploadBatch.id).where(UploadBatch.project_id.in_(project_ids))


def count_ingestion_jobs_for_projects(db: Session, project_ids: list[UUID]) -> int:
    if not project_ids:
        return 0
    return int(
        db.scalar(
            select(func.count(IngestionJob.id)).where(
                IngestionJob.upload_batch_id.in_(upload_batch_ids_for_projects(project_ids))
            )
        )
        or 0
    )


def delete_ingestion_jobs_for_projects(db: Session, project_ids: list[UUID]) -> None:
    if not project_ids:
        return
    db.execute(
        delete(IngestionJob).where(
            IngestionJob.upload_batch_id.in_(upload_batch_ids_for_projects(project_ids))
        )
    )


def count_projects(db: Session, project_ids: list[UUID]) -> int:
    if not project_ids:
        return 0
    return int(
        db.scalar(select(func.count(Project.id)).where(Project.id.in_(project_ids))) or 0
    )


def count_ticket_type_rows(
    db: Session,
    model: Any,
    project_id: UUID,
    ticket_types: list[str],
) -> int:
    if not ticket_types:
        return 0
    return int(
        db.scalar(
            select(func.count())
            .select_from(model)
            .where(model.project_id == project_id, model.ticket_type.in_(ticket_types))
        )
        or 0
    )


def count_sla_populated_incident_rows(db: Session, model: Any, project_id: UUID) -> int:
    populated_clauses = [getattr(model, field).is_not(None) for field in SLA_ENRICHMENT_FIELDS]
    return int(
        db.scalar(
            select(func.count())
            .select_from(model)
            .where(
                model.project_id == project_id,
                model.ticket_type == "INCIDENT",
                or_(*populated_clauses),
            )
        )
        or 0
    )


def clear_incident_sla_data(
    db: Session,
    project_id: UUID,
) -> tuple[dict[str, int], dict[str, int]]:
    deleted_counts = {
        "incident_sla_rows": count_project_rows(db, IncidentSlaRow, [project_id]),
        "incident_sla_uploads": count_project_rows(db, IncidentSlaUpload, [project_id]),
    }
    updated_counts = {
        "tickets_sla_fields_cleared": count_sla_populated_incident_rows(
            db,
            Ticket,
            project_id,
        ),
        "out_of_scope_tickets_sla_fields_cleared": count_sla_populated_incident_rows(
            db,
            AssessmentOutOfScopeTicket,
            project_id,
        ),
    }

    db.execute(delete(IncidentSlaRow).where(IncidentSlaRow.project_id == project_id))
    db.execute(delete(IncidentSlaUpload).where(IncidentSlaUpload.project_id == project_id))

    clear_values = {field: None for field in SLA_ENRICHMENT_FIELDS}
    db.execute(
        update(Ticket)
        .where(Ticket.project_id == project_id, Ticket.ticket_type == "INCIDENT")
        .values(**clear_values)
    )
    db.execute(
        update(AssessmentOutOfScopeTicket)
        .where(
            AssessmentOutOfScopeTicket.project_id == project_id,
            AssessmentOutOfScopeTicket.ticket_type == "INCIDENT",
        )
        .values(**clear_values)
    )
    return deleted_counts, updated_counts


def upload_batch_ids_for_project_ticket_types(
    db: Session,
    project_id: UUID,
    ticket_types: list[str],
) -> list[UUID]:
    if not ticket_types:
        return []

    candidate_batch_ids = list(
        db.scalars(
            select(UploadedFile.upload_batch_id)
            .where(
                UploadedFile.project_id == project_id,
                UploadedFile.ticket_type.in_(ticket_types),
            )
            .distinct()
        )
    )
    if not candidate_batch_ids:
        return []

    deletable_batch_ids: list[UUID] = []
    for upload_batch_id in candidate_batch_ids:
        non_selected_file_count = int(
            db.scalar(
                select(func.count(UploadedFile.id)).where(
                    UploadedFile.upload_batch_id == upload_batch_id,
                    UploadedFile.ticket_type.not_in(ticket_types),
                )
            )
            or 0
        )
        if non_selected_file_count == 0:
            deletable_batch_ids.append(upload_batch_id)
    return deletable_batch_ids


def uploaded_file_ids_for_project_ticket_types(
    db: Session,
    project_id: UUID,
    ticket_types: list[str],
) -> list[UUID]:
    if not ticket_types:
        return []
    return list(
        db.scalars(
            select(UploadedFile.id).where(
                UploadedFile.project_id == project_id,
                UploadedFile.ticket_type.in_(ticket_types),
            )
        )
    )


def count_ingestion_jobs_for_file_or_batch_ids(
    db: Session,
    uploaded_file_ids: list[UUID],
    upload_batch_ids: list[UUID],
) -> int:
    clauses = []
    if uploaded_file_ids:
        clauses.append(IngestionJob.uploaded_file_id.in_(uploaded_file_ids))
    if upload_batch_ids:
        clauses.append(IngestionJob.upload_batch_id.in_(upload_batch_ids))
    if not clauses:
        return 0
    return int(
        db.scalar(select(func.count(IngestionJob.id)).where(or_(*clauses))) or 0
    )


def delete_ingestion_jobs_for_file_or_batch_ids(
    db: Session,
    uploaded_file_ids: list[UUID],
    upload_batch_ids: list[UUID],
) -> None:
    clauses = []
    if uploaded_file_ids:
        clauses.append(IngestionJob.uploaded_file_id.in_(uploaded_file_ids))
    if upload_batch_ids:
        clauses.append(IngestionJob.upload_batch_id.in_(upload_batch_ids))
    if clauses:
        db.execute(delete(IngestionJob).where(or_(*clauses)))


def clear_project_ticket_type_operational_data(
    db: Session,
    project_id: UUID,
    ticket_types: list[str],
) -> dict[str, int]:
    if not ticket_types:
        return {}

    uploaded_file_ids = uploaded_file_ids_for_project_ticket_types(db, project_id, ticket_types)
    upload_batch_ids = upload_batch_ids_for_project_ticket_types(db, project_id, ticket_types)
    deleted_counts = {
        "dashboard_aggregates": count_ticket_type_rows(
            db,
            DashboardAggregate,
            project_id,
            ticket_types,
        ),
        "tickets": count_ticket_type_rows(db, Ticket, project_id, ticket_types),
        "assessment_out_of_scope_tickets": count_ticket_type_rows(
            db,
            AssessmentOutOfScopeTicket,
            project_id,
            ticket_types,
        ),
        "ticket_raw_rows": count_ticket_type_rows(db, TicketRawRow, project_id, ticket_types),
        "ingestion_jobs": count_ingestion_jobs_for_file_or_batch_ids(
            db,
            uploaded_file_ids,
            upload_batch_ids,
        ),
        "uploaded_files": len(uploaded_file_ids),
        "upload_batches": len(upload_batch_ids),
    }

    db.execute(
        delete(DashboardAggregate).where(
            DashboardAggregate.project_id == project_id,
            DashboardAggregate.ticket_type.in_(ticket_types),
        )
    )
    db.execute(
        delete(Ticket).where(Ticket.project_id == project_id, Ticket.ticket_type.in_(ticket_types))
    )
    db.execute(
        delete(AssessmentOutOfScopeTicket).where(
            AssessmentOutOfScopeTicket.project_id == project_id,
            AssessmentOutOfScopeTicket.ticket_type.in_(ticket_types),
        )
    )
    delete_ingestion_jobs_for_file_or_batch_ids(db, uploaded_file_ids, upload_batch_ids)
    db.execute(
        delete(TicketRawRow).where(
            TicketRawRow.project_id == project_id,
            TicketRawRow.ticket_type.in_(ticket_types),
        )
    )
    if uploaded_file_ids:
        db.execute(delete(UploadedFile).where(UploadedFile.id.in_(uploaded_file_ids)))
    if upload_batch_ids:
        db.execute(delete(UploadBatch).where(UploadBatch.id.in_(upload_batch_ids)))
    return deleted_counts


def clear_project_problem_change_operational_data(
    db: Session,
    project_id: UUID,
    ticket_type: str,
) -> dict[str, int]:
    normalized_ticket_type = ticket_type.strip().upper()
    if normalized_ticket_type == "PROBLEM":
        table_name = "assessment_problem_records"
        model = AssessmentProblemRecord
    elif normalized_ticket_type == "CHANGE":
        table_name = "assessment_change_records"
        model = AssessmentChangeRecord
    else:
        return {}

    uploaded_file_ids = uploaded_file_ids_for_project_ticket_types(
        db,
        project_id,
        [normalized_ticket_type],
    )
    upload_batch_ids = upload_batch_ids_for_project_ticket_types(
        db,
        project_id,
        [normalized_ticket_type],
    )
    deleted_counts = {
        table_name: count_project_rows(db, model, [project_id]),
        "ticket_raw_rows": count_ticket_type_rows(
            db,
            TicketRawRow,
            project_id,
            [normalized_ticket_type],
        ),
        "ingestion_jobs": count_ingestion_jobs_for_file_or_batch_ids(
            db,
            uploaded_file_ids,
            upload_batch_ids,
        ),
        "uploaded_files": len(uploaded_file_ids),
        "upload_batches": len(upload_batch_ids),
    }

    db.execute(delete(model).where(model.project_id == project_id))
    delete_ingestion_jobs_for_file_or_batch_ids(db, uploaded_file_ids, upload_batch_ids)
    db.execute(
        delete(TicketRawRow).where(
            TicketRawRow.project_id == project_id,
            TicketRawRow.ticket_type == normalized_ticket_type,
        )
    )
    if uploaded_file_ids:
        db.execute(delete(UploadedFile).where(UploadedFile.id.in_(uploaded_file_ids)))
    if upload_batch_ids:
        db.execute(delete(UploadBatch).where(UploadBatch.id.in_(upload_batch_ids)))
    return deleted_counts


def clear_project_operational_tables(
    db: Session,
    project_ids: list[UUID],
) -> dict[str, int]:
    deleted_counts: dict[str, int] = {}
    deleted_counts["ingestion_jobs"] = count_ingestion_jobs_for_projects(db, project_ids)

    for table_name, model in PROJECT_OPERATIONAL_MODELS:
        deleted_counts[table_name] = count_project_rows(db, model, project_ids)

    delete_ingestion_jobs_for_projects(db, project_ids)
    for _, model in PROJECT_OPERATIONAL_MODELS:
        delete_project_rows(db, model, project_ids)

    return deleted_counts


def delete_project_configuration_tables(
    db: Session,
    project_ids: list[UUID],
) -> dict[str, int]:
    deleted_counts: dict[str, int] = {}
    for table_name, model in PROJECT_CONFIGURATION_MODELS:
        deleted_counts[table_name] = count_project_rows(db, model, project_ids)
    for _, model in PROJECT_CONFIGURATION_MODELS:
        delete_project_rows(db, model, project_ids)
    return deleted_counts


def project_ids_for_client(db: Session, client_id: UUID) -> list[UUID]:
    return list(db.scalars(select(Project.id).where(Project.client_id == client_id)).all())


def reset_operational_data(db: Session, confirmation: str) -> OperationalResetResult:
    if confirmation != RESET_CONFIRMATION:
        raise AdminResetError("Confirmation text must exactly match RESET OPERATIONAL DATA.")

    deleted_counts: dict[str, int] = {}
    try:
        for table_name, model in RESET_MODELS:
            deleted_counts[table_name] = count_rows(db, model)
            db.execute(delete(model))
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise AdminResetError(f"Operational data reset failed: {exc}") from exc

    return OperationalResetResult(
        deleted_counts=deleted_counts,
        preserved=PRESERVED_TABLES,
    )


def reset_project_operational_data(
    db: Session,
    project_id: UUID,
    confirmation: str,
    *,
    reset_incidents: bool = False,
    reset_sc_tasks: bool = False,
    reset_problems: bool = False,
    reset_changes: bool = False,
    reset_incident_sla: bool = False,
) -> OperationalResetResult:
    legacy_full_reset = (
        confirmation == PROJECT_RESET_CONFIRMATION
        and not reset_incidents
        and not reset_sc_tasks
        and not reset_problems
        and not reset_changes
        and not reset_incident_sla
    )
    if confirmation != RESET_CONFIRMATION and not legacy_full_reset:
        raise AdminResetError("Confirmation text must exactly match RESET OPERATIONAL DATA.")
    if db.get(Project, project_id) is None:
        raise AdminResetError(f"Project {project_id} was not found.")
    if legacy_full_reset:
        reset_incidents = True
        reset_sc_tasks = True
        reset_problems = True
        reset_changes = True
        reset_incident_sla = True
    if (
        not reset_incidents
        and not reset_sc_tasks
        and not reset_problems
        and not reset_changes
        and not reset_incident_sla
    ):
        raise AdminResetError("Select at least one operational data category to reset.")

    incident_sla_reset_reason = None
    if reset_incidents and not reset_incident_sla:
        reset_incident_sla = True
        incident_sla_reset_reason = (
            "Incident reset selected, so Incident SLA data was also reset to prevent "
            "stale SLA data."
        )

    try:
        deleted_counts: dict[str, int] = {}
        updated_counts: dict[str, int] = {}
        ticket_types: list[str] = []
        if reset_incidents:
            ticket_types.append("INCIDENT")
        if reset_sc_tasks:
            ticket_types.append("SERVICE_CATALOG_TASK")
        if ticket_types:
            deleted_counts.update(
                clear_project_ticket_type_operational_data(db, project_id, ticket_types)
            )
        if reset_problems:
            deleted_counts.update(
                clear_project_problem_change_operational_data(db, project_id, "PROBLEM")
            )
        if reset_changes:
            deleted_counts.update(
                clear_project_problem_change_operational_data(db, project_id, "CHANGE")
            )
        if reset_incident_sla:
            sla_deleted_counts, sla_updated_counts = clear_incident_sla_data(db, project_id)
            deleted_counts.update(sla_deleted_counts)
            updated_counts.update(sla_updated_counts)
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise AdminResetError(f"Project operational reset failed: {exc}") from exc

    return OperationalResetResult(
        deleted_counts=deleted_counts,
        updated_counts=updated_counts,
        preserved=PROJECT_OPERATIONAL_PRESERVED_TABLES,
        reset_incidents=reset_incidents,
        reset_sc_tasks=reset_sc_tasks,
        reset_problems=reset_problems,
        reset_changes=reset_changes,
        reset_incident_sla=reset_incident_sla,
        incident_sla_reset_reason=incident_sla_reset_reason,
    )


def delete_project_and_related_data(
    db: Session,
    project_id: UUID,
    confirmation: str,
) -> OperationalResetResult:
    if confirmation not in {PROJECT_DELETE_CONFIRMATION, PROJECT_DATA_RESET_CONFIRMATION}:
        raise AdminResetError(
            "Confirmation text must exactly match RESET PROJECT DATA."
        )
    project = db.get(Project, project_id)
    if project is None:
        raise AdminResetError(f"Project {project_id} was not found.")

    try:
        deleted_counts = clear_project_operational_tables(db, [project_id])
        deleted_counts.update(delete_project_configuration_tables(db, [project_id]))
        deleted_counts["projects"] = 1
        db.execute(delete(Project).where(Project.id == project_id))
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise AdminResetError(f"Project delete failed: {exc}") from exc

    return OperationalResetResult(
        deleted_counts=deleted_counts,
        preserved=PROJECT_DELETE_PRESERVED_TABLES,
    )


def delete_client_and_related_data(
    db: Session,
    client_id: UUID,
    confirmation: str,
) -> OperationalResetResult:
    if confirmation not in {CLIENT_DELETE_CONFIRMATION, CUSTOMER_DATA_RESET_CONFIRMATION}:
        raise AdminResetError(
            "Confirmation text must exactly match RESET CUSTOMER DATA."
        )
    client = db.get(Client, client_id)
    if client is None:
        raise AdminResetError(f"Client {client_id} was not found.")

    project_ids = project_ids_for_client(db, client_id)
    try:
        deleted_counts = clear_project_operational_tables(db, project_ids)
        deleted_counts.update(delete_project_configuration_tables(db, project_ids))
        deleted_counts["projects"] = count_projects(db, project_ids)
        deleted_counts["clients"] = 1
        if project_ids:
            db.execute(delete(Project).where(Project.id.in_(project_ids)))
        db.execute(delete(Client).where(Client.id == client_id))
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise AdminResetError(f"Client delete failed: {exc}") from exc

    return OperationalResetResult(
        deleted_counts=deleted_counts,
        preserved=["other_clients", "other_projects", "alembic_version"],
    )
