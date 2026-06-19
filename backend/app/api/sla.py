from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.sla import (
    IncidentSlaEnrichRequest,
    IncidentSlaEnrichResponse,
    IncidentSlaSummaryResponse,
    IncidentSlaUnmatchedResponse,
    IncidentSlaUnmatchedRow,
    IncidentSlaUploadResponse,
)
from app.services.sla import (
    IncidentSlaError,
    enrich_incident_sla,
    incident_sla_summary,
    unmatched_incident_sla_numbers,
    upload_incident_sla_csv,
)

router = APIRouter(prefix="/sla", tags=["sla"])
DbSession = Annotated[Session, Depends(get_db)]
UPLOAD_COPY_CHUNK_SIZE = 1024 * 1024


async def copy_upload_to_temp_file(upload_file: UploadFile) -> Path:
    suffix = Path(upload_file.filename or "").suffix.lower()
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
        temp_path = Path(temp_file.name)
        while chunk := await upload_file.read(UPLOAD_COPY_CHUNK_SIZE):
            temp_file.write(chunk)
    return temp_path


@router.post(
    "/incidents/upload",
    response_model=IncidentSlaUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_incident_sla_file(
    project_id: Annotated[UUID, Form(...)],
    file: Annotated[UploadFile, File(...)],
    db: DbSession,
) -> IncidentSlaUploadResponse:
    original_filename = file.filename or "incident_sla.csv"
    if Path(original_filename).suffix.lower() != ".csv":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only Incident SLA CSV files are supported in this MVP.",
        )

    temp_path = await copy_upload_to_temp_file(file)
    try:
        result = upload_incident_sla_csv(
            db=db,
            project_id=project_id,
            csv_path=temp_path,
            uploaded_file_name=original_filename,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except IncidentSlaError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    finally:
        temp_path.unlink(missing_ok=True)
        await file.close()

    return IncidentSlaUploadResponse(
        project_id=result.project_id,
        uploaded_file_name=result.uploaded_file_name,
        total_rows=result.total_rows,
        inserted_rows=result.inserted_rows,
        failed_rows=result.failed_rows,
        warnings=result.warnings,
        errors=result.errors,
    )


@router.post("/incidents/enrich", response_model=IncidentSlaEnrichResponse)
def enrich_incident_sla_tickets(
    request: IncidentSlaEnrichRequest,
    db: DbSession,
) -> IncidentSlaEnrichResponse:
    try:
        result = enrich_incident_sla(
            db=db,
            project_id=request.project_id,
            ticket_type=request.ticket_type,
            replace_existing=request.replace_existing,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except IncidentSlaError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return IncidentSlaEnrichResponse(
        project_id=result.project_id,
        ticket_type=result.ticket_type,
        replace_existing=result.replace_existing,
        matched_ticket_count=result.matched_ticket_count,
        response_sla_updated_count=result.response_sla_updated_count,
        resolution_sla_updated_count=result.resolution_sla_updated_count,
        warnings=result.warnings,
    )


@router.get("/incidents/summary", response_model=IncidentSlaSummaryResponse)
def get_incident_sla_summary(
    project_id: UUID,
    db: DbSession,
) -> IncidentSlaSummaryResponse:
    try:
        summary = incident_sla_summary(db, project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return IncidentSlaSummaryResponse(
        project_id=summary.project_id,
        total_sla_rows=summary.total_sla_rows,
        unique_incident_numbers=summary.unique_incident_numbers,
        matched_tickets_count=summary.matched_tickets_count,
        unmatched_sla_incident_numbers_count=summary.unmatched_sla_incident_numbers_count,
        tickets_with_response_sla_selected=summary.tickets_with_response_sla_selected,
        tickets_with_resolution_sla_selected=summary.tickets_with_resolution_sla_selected,
        response_accenture_selected_count=summary.response_accenture_selected_count,
        response_default_selected_count=summary.response_default_selected_count,
        resolution_accenture_selected_count=summary.resolution_accenture_selected_count,
        resolution_default_selected_count=summary.resolution_default_selected_count,
        response_breached_count=summary.response_breached_count,
        resolution_breached_count=summary.resolution_breached_count,
    )


@router.get("/incidents/unmatched", response_model=IncidentSlaUnmatchedResponse)
def get_unmatched_incident_sla_numbers(
    project_id: UUID,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> IncidentSlaUnmatchedResponse:
    try:
        rows = unmatched_incident_sla_numbers(
            db=db,
            project_id=project_id,
            limit=limit,
            offset=offset,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return IncidentSlaUnmatchedResponse(
        project_id=project_id,
        limit=limit,
        offset=offset,
        rows=[
            IncidentSlaUnmatchedRow(inc_number=row.inc_number, row_count=row.row_count)
            for row in rows
        ],
    )
