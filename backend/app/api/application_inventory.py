from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.application_inventory import (
    ApplicationInventoryEnrichmentSummaryResponse,
    ApplicationInventoryEnrichRequest,
    ApplicationInventoryFilterValuesResponse,
    ApplicationInventoryItemResponse,
    ApplicationInventoryItemUpdateRequest,
    ApplicationInventoryUploadResponse,
    ScopeSummaryResponse,
    ScopeSummaryValueCountResponse,
    UnmatchedBusinessServiceResponse,
    UnmatchedBusinessServicesResponse,
    ValueCountResponse,
)
from app.services.application_inventory import (
    ApplicationInventoryError,
    BusinessServiceCoverage,
    InventoryEnrichmentSummary,
    InventoryUploadResult,
    ScopeSummary,
    build_inventory_enrichment_summary,
    build_scope_summary,
    deactivate_inventory_item,
    enrich_tickets_from_inventory,
    inventory_filter_values,
    list_inventory_items,
    unmatched_business_services,
    update_inventory_item,
    upload_application_inventory_file,
)

router = APIRouter(prefix="/application-inventory", tags=["application-inventory"])
DbSession = Annotated[Session, Depends(get_db)]
UPLOAD_COPY_CHUNK_SIZE = 1024 * 1024


async def copy_upload_to_temp_file(upload_file: UploadFile) -> Path:
    suffix = Path(upload_file.filename or "").suffix.lower()
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
        temp_path = Path(temp_file.name)
        while chunk := await upload_file.read(UPLOAD_COPY_CHUNK_SIZE):
            temp_file.write(chunk)
    return temp_path


def raise_inventory_http_error(exc: Exception) -> None:
    if isinstance(exc, FileNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    if isinstance(exc, ApplicationInventoryError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


def value_count_response(rows: list) -> list[ValueCountResponse]:
    return [ValueCountResponse(value=row.value, count=row.count) for row in rows]


def upload_response(result: InventoryUploadResult) -> ApplicationInventoryUploadResponse:
    return ApplicationInventoryUploadResponse(
        project_id=result.project_id,
        total_rows=result.total_rows,
        inserted_count=result.inserted_count,
        updated_count=result.updated_count,
        skipped_count=result.skipped_count,
        error_count=result.error_count,
        warning_count=result.warning_count,
        errors=result.errors,
        warnings=result.warnings,
        distinct_business_service_count=len(result.distinct_business_services),
        distinct_parent_application_count=len(result.distinct_parent_applications),
        distinct_assignment_group_count=len(result.distinct_assignment_groups),
        distinct_application_owner_count=len(result.distinct_application_owners),
        distinct_support_lead_count=len(result.distinct_support_leads),
        distinct_functional_track_count=len(result.distinct_functional_tracks),
        distinct_ams_owner_count=len(result.distinct_ams_owners),
        distinct_supported_vendor_count=len(result.distinct_supported_vendors),
    )


def enrichment_response(
    summary: InventoryEnrichmentSummary,
) -> ApplicationInventoryEnrichmentSummaryResponse:
    return ApplicationInventoryEnrichmentSummaryResponse(
        project_id=summary.project_id,
        total_tickets=summary.total_tickets,
        matched_tickets=summary.matched_tickets,
        unmatched_tickets=summary.unmatched_tickets,
        updated_tickets=summary.updated_tickets,
        match_rate_pct=summary.match_rate_pct,
        matched_by_business_service_count=summary.matched_by_business_service_count,
        matched_by_application_count=summary.matched_by_application_count,
        unmatched_business_service_count=summary.unmatched_business_service_count,
        distinct_ticket_business_service_count=summary.distinct_ticket_business_service_count,
        distinct_inventory_business_service_count=(
            summary.distinct_inventory_business_service_count
        ),
        top_unmatched_business_services=value_count_response(
            summary.top_unmatched_business_services
        ),
        top_unmatched_applications=value_count_response(summary.top_unmatched_applications),
        top_unmatched_assignment_groups=value_count_response(
            summary.top_unmatched_assignment_groups
        ),
    )


def coverage_response(coverage: BusinessServiceCoverage) -> UnmatchedBusinessServicesResponse:
    return UnmatchedBusinessServicesResponse(
        project_id=coverage.project_id,
        distinct_ticket_business_service_count=coverage.distinct_ticket_business_service_count,
        distinct_inventory_business_service_count=(
            coverage.distinct_inventory_business_service_count
        ),
        matched_business_service_count=coverage.matched_business_service_count,
        unmatched_business_service_count=coverage.unmatched_business_service_count,
        business_service_coverage_pct=coverage.business_service_coverage_pct,
        rows=[
            UnmatchedBusinessServiceResponse(
                business_service=row.business_service,
                ticket_count=row.ticket_count,
                assignment_group_count=row.assignment_group_count,
                sample_assignment_groups=row.sample_assignment_groups,
                sample_ticket_numbers=row.sample_ticket_numbers,
            )
            for row in coverage.rows
        ],
    )


def scope_summary_response(summary: ScopeSummary) -> ScopeSummaryResponse:
    return ScopeSummaryResponse(
        project_id=summary.project_id,
        in_scope_tickets=summary.in_scope_tickets,
        out_of_scope_tickets=summary.out_of_scope_tickets,
        total_classified_tickets=summary.total_classified_tickets,
        in_scope_pct=summary.in_scope_pct,
        out_of_scope_pct=summary.out_of_scope_pct,
        distinct_in_scope_assignment_groups=summary.distinct_in_scope_assignment_groups,
        distinct_out_of_scope_assignment_groups=(
            summary.distinct_out_of_scope_assignment_groups
        ),
        top_out_of_scope_assignment_groups=[
            ScopeSummaryValueCountResponse(value=row.value, count=row.count)
            for row in summary.top_out_of_scope_assignment_groups
        ],
        top_out_of_scope_business_services=[
            ScopeSummaryValueCountResponse(value=row.value, count=row.count)
            for row in summary.top_out_of_scope_business_services
        ],
    )


@router.get("", response_model=list[ApplicationInventoryItemResponse])
def get_application_inventory(
    project_id: Annotated[UUID, Query(...)],
    db: DbSession,
) -> list[ApplicationInventoryItemResponse]:
    try:
        return list_inventory_items(db, project_id)
    except (FileNotFoundError, ApplicationInventoryError) as exc:
        raise_inventory_http_error(exc)
    return []


@router.post(
    "/upload",
    response_model=ApplicationInventoryUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_application_inventory(
    project_id: Annotated[UUID, Form(...)],
    file: Annotated[UploadFile, File(...)],
    db: DbSession,
) -> ApplicationInventoryUploadResponse:
    filename = file.filename or "application-inventory"
    extension = Path(filename).suffix.lower()
    if extension not in {".csv", ".xlsx"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Application Inventory upload supports CSV and XLSX files.",
        )

    temp_path = await copy_upload_to_temp_file(file)
    try:
        result = upload_application_inventory_file(db, project_id, temp_path, filename)
    except (FileNotFoundError, ApplicationInventoryError) as exc:
        raise_inventory_http_error(exc)
    finally:
        temp_path.unlink(missing_ok=True)
        await file.close()

    return upload_response(result)


@router.post("/enrich-tickets", response_model=ApplicationInventoryEnrichmentSummaryResponse)
def enrich_application_inventory_tickets(
    request: ApplicationInventoryEnrichRequest,
    db: DbSession,
) -> ApplicationInventoryEnrichmentSummaryResponse:
    try:
        summary = enrich_tickets_from_inventory(
            db,
            request.project_id,
            replace_existing=request.replace_existing,
        )
    except (FileNotFoundError, ApplicationInventoryError) as exc:
        raise_inventory_http_error(exc)
    return enrichment_response(summary)


@router.get(
    "/enrichment-summary",
    response_model=ApplicationInventoryEnrichmentSummaryResponse,
)
def get_application_inventory_enrichment_summary(
    project_id: Annotated[UUID, Query(...)],
    db: DbSession,
) -> ApplicationInventoryEnrichmentSummaryResponse:
    try:
        summary = build_inventory_enrichment_summary(db, project_id)
    except (FileNotFoundError, ApplicationInventoryError) as exc:
        raise_inventory_http_error(exc)
    return enrichment_response(summary)


@router.get("/unmatched-business-services", response_model=UnmatchedBusinessServicesResponse)
def get_unmatched_business_services(
    project_id: Annotated[UUID, Query(...)],
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> UnmatchedBusinessServicesResponse:
    try:
        coverage = unmatched_business_services(db, project_id, limit=limit, offset=offset)
    except (FileNotFoundError, ApplicationInventoryError) as exc:
        raise_inventory_http_error(exc)
    return coverage_response(coverage)


@router.get("/filter-values", response_model=ApplicationInventoryFilterValuesResponse)
def get_application_inventory_filter_values(
    project_id: Annotated[UUID, Query(...)],
    db: DbSession,
) -> dict[str, list[str]]:
    try:
        return inventory_filter_values(db, project_id)
    except (FileNotFoundError, ApplicationInventoryError) as exc:
        raise_inventory_http_error(exc)
    return {}


@router.get("/scope-summary", response_model=ScopeSummaryResponse)
def get_application_inventory_scope_summary(
    project_id: Annotated[UUID, Query(...)],
    db: DbSession,
) -> ScopeSummaryResponse:
    try:
        summary = build_scope_summary(db, project_id)
    except (FileNotFoundError, ApplicationInventoryError) as exc:
        raise_inventory_http_error(exc)
    return scope_summary_response(summary)


@router.put("/{item_id}", response_model=ApplicationInventoryItemResponse)
def put_application_inventory_item(
    item_id: UUID,
    request: ApplicationInventoryItemUpdateRequest,
    db: DbSession,
) -> ApplicationInventoryItemResponse:
    try:
        return update_inventory_item(db, item_id, request.model_dump(exclude_unset=True))
    except (FileNotFoundError, ApplicationInventoryError) as exc:
        raise_inventory_http_error(exc)
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unable to update item.")


@router.delete("/{item_id}", response_model=ApplicationInventoryItemResponse)
def delete_application_inventory_item(
    item_id: UUID,
    db: DbSession,
) -> ApplicationInventoryItemResponse:
    try:
        return deactivate_inventory_item(db, item_id)
    except (FileNotFoundError, ApplicationInventoryError) as exc:
        raise_inventory_http_error(exc)
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Unable to deactivate item.",
    )
