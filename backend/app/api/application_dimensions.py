from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.application_dimension import (
    ApplicationDimensionBulkUploadResponse,
    ApplicationDimensionCreateRequest,
    ApplicationDimensionEnrichmentSummaryResponse,
    ApplicationDimensionEnrichRequest,
    ApplicationDimensionResponse,
    ApplicationDimensionUpdateRequest,
    ValueCountResponse,
)
from app.services.application_dimensions import (
    ApplicationDimensionError,
    BulkUploadResult,
    EnrichmentSummary,
    build_enrichment_summary,
    create_application_dimension,
    deactivate_application_dimension,
    enrich_tickets_with_application_dimensions,
    list_application_dimensions,
    update_application_dimension,
    upload_application_dimensions_csv,
)

router = APIRouter(prefix="/application-dimensions", tags=["application-dimensions"])
DbSession = Annotated[Session, Depends(get_db)]
UPLOAD_COPY_CHUNK_SIZE = 1024 * 1024


async def copy_upload_to_temp_file(upload_file: UploadFile) -> Path:
    suffix = Path(upload_file.filename or "").suffix.lower()
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
        temp_path = Path(temp_file.name)
        while chunk := await upload_file.read(UPLOAD_COPY_CHUNK_SIZE):
            temp_file.write(chunk)
    return temp_path


def handle_not_found_or_bad_request(exc: Exception) -> None:
    if isinstance(exc, FileNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    if isinstance(exc, ApplicationDimensionError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


def bulk_upload_response(result: BulkUploadResult) -> ApplicationDimensionBulkUploadResponse:
    return ApplicationDimensionBulkUploadResponse(
        project_id=result.project_id,
        total_rows=result.total_rows,
        inserted_count=result.inserted_count,
        updated_count=result.updated_count,
        skipped_count=result.skipped_count,
        errors=result.errors,
        warnings=result.warnings,
    )


def enrichment_summary_response(
    summary: EnrichmentSummary,
) -> ApplicationDimensionEnrichmentSummaryResponse:
    return ApplicationDimensionEnrichmentSummaryResponse(
        project_id=summary.project_id,
        total_tickets=summary.total_tickets,
        matched_tickets=summary.matched_tickets,
        unmatched_tickets=summary.unmatched_tickets,
        updated_tickets=summary.updated_tickets,
        match_rate_pct=summary.match_rate_pct,
        match_counts_by_source=summary.match_counts_by_source,
        top_unmatched_applications=[
            ValueCountResponse(value=row.value, count=row.count)
            for row in summary.top_unmatched_applications
        ],
        top_unmatched_business_services=[
            ValueCountResponse(value=row.value, count=row.count)
            for row in summary.top_unmatched_business_services
        ],
        top_unmatched_cmdb_ci=[
            ValueCountResponse(value=row.value, count=row.count)
            for row in summary.top_unmatched_cmdb_ci
        ],
        top_unmatched_service_offerings=[
            ValueCountResponse(value=row.value, count=row.count)
            for row in summary.top_unmatched_service_offerings
        ],
        top_unmatched_catalog_items=[
            ValueCountResponse(value=row.value, count=row.count)
            for row in summary.top_unmatched_catalog_items
        ],
    )


@router.get("", response_model=list[ApplicationDimensionResponse])
def get_application_dimensions(
    project_id: UUID,
    db: DbSession,
) -> list[ApplicationDimensionResponse]:
    try:
        return list_application_dimensions(db, project_id)
    except (FileNotFoundError, ApplicationDimensionError) as exc:
        handle_not_found_or_bad_request(exc)
    return []


@router.post("", response_model=ApplicationDimensionResponse, status_code=status.HTTP_201_CREATED)
def post_application_dimension(
    request: ApplicationDimensionCreateRequest,
    db: DbSession,
) -> ApplicationDimensionResponse:
    try:
        return create_application_dimension(db, request.model_dump())
    except (FileNotFoundError, ApplicationDimensionError) as exc:
        handle_not_found_or_bad_request(exc)
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unable to create mapping.")


@router.put("/{dimension_id}", response_model=ApplicationDimensionResponse)
def put_application_dimension(
    dimension_id: UUID,
    request: ApplicationDimensionUpdateRequest,
    db: DbSession,
) -> ApplicationDimensionResponse:
    try:
        return update_application_dimension(
            db,
            dimension_id,
            request.model_dump(exclude_unset=True),
        )
    except (FileNotFoundError, ApplicationDimensionError) as exc:
        handle_not_found_or_bad_request(exc)
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unable to update mapping.")


@router.delete("/{dimension_id}", response_model=ApplicationDimensionResponse)
def delete_application_dimension(
    dimension_id: UUID,
    db: DbSession,
) -> ApplicationDimensionResponse:
    try:
        return deactivate_application_dimension(db, dimension_id)
    except (FileNotFoundError, ApplicationDimensionError) as exc:
        handle_not_found_or_bad_request(exc)
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Unable to deactivate mapping.",
    )


@router.post(
    "/bulk-upload",
    response_model=ApplicationDimensionBulkUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def bulk_upload_application_dimensions(
    project_id: Annotated[UUID, Form(...)],
    file: Annotated[UploadFile, File(...)],
    db: DbSession,
) -> ApplicationDimensionBulkUploadResponse:
    filename = file.filename or "application-dimensions.csv"
    if Path(filename).suffix.lower() != ".csv":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only CSV files are supported for application dimension bulk upload.",
        )

    temp_path = await copy_upload_to_temp_file(file)
    try:
        result = upload_application_dimensions_csv(db, project_id, temp_path)
    except (FileNotFoundError, ApplicationDimensionError) as exc:
        handle_not_found_or_bad_request(exc)
    finally:
        temp_path.unlink(missing_ok=True)
        await file.close()

    return bulk_upload_response(result)


@router.post("/enrich-tickets", response_model=ApplicationDimensionEnrichmentSummaryResponse)
def enrich_application_dimension_tickets(
    request: ApplicationDimensionEnrichRequest,
    db: DbSession,
) -> ApplicationDimensionEnrichmentSummaryResponse:
    try:
        summary = enrich_tickets_with_application_dimensions(
            db,
            request.project_id,
            request.replace_existing,
        )
    except (FileNotFoundError, ApplicationDimensionError) as exc:
        handle_not_found_or_bad_request(exc)
    return enrichment_summary_response(summary)


@router.get(
    "/enrichment-summary",
    response_model=ApplicationDimensionEnrichmentSummaryResponse,
)
def get_application_dimension_enrichment_summary(
    project_id: Annotated[UUID, Query(...)],
    db: DbSession,
) -> ApplicationDimensionEnrichmentSummaryResponse:
    try:
        summary = build_enrichment_summary(db, project_id)
    except (FileNotFoundError, ApplicationDimensionError) as exc:
        handle_not_found_or_bad_request(exc)
    return enrichment_summary_response(summary)
