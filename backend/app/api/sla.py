from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.sla import (
    IncidentSlaDeduplicateRequest,
    IncidentSlaDeduplicateResponse,
    IncidentSlaEnrichRequest,
    IncidentSlaEnrichResponse,
    IncidentSlaMultiUploadResponse,
    IncidentSlaScopeStatsResponse,
    IncidentSlaSummaryResponse,
    IncidentSlaUnmatchedResponse,
    IncidentSlaUnmatchedRow,
    IncidentSlaUploadFileResponse,
    IncidentSlaUploadHistoryRowResponse,
    IncidentSlaUploadResponse,
    IncidentSlaUploadTotalsResponse,
)
from app.services.sla import (
    IncidentSlaError,
    IncidentSlaUploadResult,
    build_multi_upload_totals,
    deduplicate_incident_sla_rows,
    enrich_incident_sla,
    incident_sla_summary,
    list_incident_sla_uploads,
    unmatched_incident_sla_numbers,
)
from app.services.sla import (
    upload_incident_sla_file as upload_incident_sla_file_service,
)

router = APIRouter(prefix="/sla", tags=["sla"])
DbSession = Annotated[Session, Depends(get_db)]
UPLOAD_COPY_CHUNK_SIZE = 1024 * 1024
SUPPORTED_SLA_UPLOAD_EXTENSIONS = {".csv", ".xlsx"}
DEDUPLICATE_CONFIRMATION = "DEDUPLICATE SLA ROWS"


async def copy_upload_to_temp_file(upload_file: UploadFile) -> Path:
    suffix = Path(upload_file.filename or "").suffix.lower()
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
        temp_path = Path(temp_file.name)
        while chunk := await upload_file.read(UPLOAD_COPY_CHUNK_SIZE):
            temp_file.write(chunk)
    return temp_path


def upload_response(result) -> IncidentSlaUploadResponse:
    return IncidentSlaUploadResponse(
        project_id=result.project_id,
        upload_id=result.upload_id,
        uploaded_file_name=result.uploaded_file_name,
        status=result.status,
        total_rows=result.total_rows,
        inserted_rows=result.inserted_rows,
        duplicate_rows_skipped=result.duplicate_rows_skipped,
        failed_rows=result.failed_rows,
        warnings=result.warnings,
        errors=result.errors,
    )


def failed_upload_result(
    project_id: UUID,
    uploaded_file_name: str,
    error_message: str,
) -> IncidentSlaUploadResult:
    return IncidentSlaUploadResult(
        project_id=project_id,
        uploaded_file_name=uploaded_file_name,
        status="FAILED",
        failed_rows=1,
        errors=[error_message],
    )


def scope_stats_response(stats) -> IncidentSlaScopeStatsResponse:
    return IncidentSlaScopeStatsResponse(
        incident_tickets_considered=stats.incident_tickets_considered,
        incident_tickets_matched_to_sla_rows=stats.incident_tickets_matched_to_sla_rows,
        incident_tickets_enriched=stats.incident_tickets_enriched,
        response_sla_enriched=stats.response_sla_enriched,
        resolution_sla_enriched=stats.resolution_sla_enriched,
        response_vendor_specific=stats.response_vendor_specific,
        response_default=stats.response_default,
        response_fallback_default=stats.response_fallback_default,
        response_not_found=stats.response_not_found,
        resolution_vendor_specific=stats.resolution_vendor_specific,
        resolution_default=stats.resolution_default,
        resolution_fallback_default=stats.resolution_fallback_default,
        resolution_not_found=stats.resolution_not_found,
    )


@router.post(
    "/incidents/upload",
    response_model=IncidentSlaUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_single_incident_sla_file(
    project_id: Annotated[UUID, Form(...)],
    file: Annotated[UploadFile, File(...)],
    db: DbSession,
) -> IncidentSlaUploadResponse:
    original_filename = file.filename or "incident_sla.csv"
    if Path(original_filename).suffix.lower() not in SUPPORTED_SLA_UPLOAD_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only Incident SLA CSV or XLSX files are supported.",
        )

    temp_path = await copy_upload_to_temp_file(file)
    try:
        result = upload_incident_sla_file_service(
            db=db,
            project_id=project_id,
            file_path=temp_path,
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

    return upload_response(result)


@router.post(
    "/incidents/upload-multiple",
    response_model=IncidentSlaMultiUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_multiple_incident_sla_files(
    project_id: Annotated[UUID, Form(...)],
    files: Annotated[list[UploadFile], File(...)],
    db: DbSession,
) -> IncidentSlaMultiUploadResponse:
    results = []
    for file in files:
        original_filename = file.filename or "incident_sla.csv"
        suffix = Path(original_filename).suffix.lower()
        if suffix not in SUPPORTED_SLA_UPLOAD_EXTENSIONS:
            results.append(
                failed_upload_result(
                    project_id,
                    original_filename,
                    "Only Incident SLA CSV or XLSX files are supported.",
                )
            )
            await file.close()
            continue

        temp_path = await copy_upload_to_temp_file(file)
        try:
            result = upload_incident_sla_file_service(
                db=db,
                project_id=project_id,
                file_path=temp_path,
                uploaded_file_name=original_filename,
            )
            results.append(result)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        except IncidentSlaError as exc:
            results.append(failed_upload_result(project_id, original_filename, str(exc)))
        finally:
            temp_path.unlink(missing_ok=True)
            await file.close()

    multi_result = build_multi_upload_totals(project_id, results)
    return IncidentSlaMultiUploadResponse(
        project_id=multi_result.project_id,
        files=[
            IncidentSlaUploadFileResponse(**upload_response(file).model_dump())
            for file in results
        ],
        totals=IncidentSlaUploadTotalsResponse(
            total_files=multi_result.totals.total_files,
            total_rows_read=multi_result.totals.total_rows_read,
            inserted_rows=multi_result.totals.inserted_rows,
            duplicate_rows_skipped=multi_result.totals.duplicate_rows_skipped,
            error_rows=multi_result.totals.error_rows,
        ),
    )


@router.get(
    "/incidents/uploads",
    response_model=list[IncidentSlaUploadHistoryRowResponse],
)
def get_incident_sla_upload_history(
    project_id: UUID,
    db: DbSession,
) -> list[IncidentSlaUploadHistoryRowResponse]:
    try:
        rows = list_incident_sla_uploads(db, project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return [
        IncidentSlaUploadHistoryRowResponse(
            upload_id=row.upload_id,
            filename=row.filename,
            uploaded_at=row.uploaded_at,
            total_rows_read=row.total_rows_read,
            inserted_rows=row.inserted_rows,
            duplicate_rows_skipped=row.duplicate_rows_skipped,
            error_rows=row.error_rows,
            status=row.status,
        )
        for row in rows
    ]


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
        in_scope_incidents_considered=result.in_scope_incidents_considered,
        in_scope_incidents_enriched=result.in_scope_incidents_enriched,
        out_of_scope_incidents_considered=result.out_of_scope_incidents_considered,
        out_of_scope_incidents_enriched=result.out_of_scope_incidents_enriched,
        response_vendor_specific_count=result.response_vendor_specific_count,
        response_default_count=result.response_default_count,
        resolution_vendor_specific_count=result.resolution_vendor_specific_count,
        resolution_default_count=result.resolution_default_count,
        missing_response_sla_count=result.missing_response_sla_count,
        missing_resolution_sla_count=result.missing_resolution_sla_count,
        sla_rows={
            "total_rows": result.sla_rows.total_rows,
            "distinct_ticket_numbers_in_sla_rows": (
                result.sla_rows.distinct_ticket_numbers_in_sla_rows
            ),
            "duplicate_rows_skipped_on_upload": (
                result.sla_rows.duplicate_rows_skipped_on_upload
            ),
        },
        in_scope=scope_stats_response(result.in_scope),
        out_of_scope=scope_stats_response(result.out_of_scope),
        unmatched={
            "sla_ticket_numbers_not_found_in_scope_or_out_of_scope": (
                result.unmatched.sla_ticket_numbers_not_found_in_scope_or_out_of_scope
            ),
            "in_scope_incidents_without_sla_rows": (
                result.unmatched.in_scope_incidents_without_sla_rows
            ),
            "out_of_scope_incidents_without_sla_rows": (
                result.unmatched.out_of_scope_incidents_without_sla_rows
            ),
        },
        warnings=result.warnings,
    )


@router.post("/deduplicate", response_model=IncidentSlaDeduplicateResponse)
def deduplicate_incident_sla_upload_rows(
    request: IncidentSlaDeduplicateRequest,
    db: DbSession,
) -> IncidentSlaDeduplicateResponse:
    if request.confirmation != DEDUPLICATE_CONFIRMATION:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Confirmation text must exactly match DEDUPLICATE SLA ROWS.",
        )
    try:
        result = deduplicate_incident_sla_rows(db, request.project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except IncidentSlaError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return IncidentSlaDeduplicateResponse(
        project_id=result.project_id,
        duplicate_groups_found=result.duplicate_groups_found,
        duplicate_rows_deleted=result.duplicate_rows_deleted,
        remaining_sla_rows=result.remaining_sla_rows,
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
