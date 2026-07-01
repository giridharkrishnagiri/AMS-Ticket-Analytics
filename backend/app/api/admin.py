from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.admin import (
    ClientDeleteRequest,
    DashboardFilterFactsRefreshRequest,
    DashboardFilterFactsRefreshResponse,
    InScopeAssignmentGroupPreviewRowResponse,
    InScopeAssignmentGroupRowResponse,
    InScopeAssignmentGroupsImportResponse,
    InScopeAssignmentGroupsStatusResponse,
    OperationalDataResetRequest,
    OperationalDataResetResponse,
    OperationalReprocessingRequest,
    OperationalReprocessingResponse,
    ProjectDeleteRequest,
    ProjectOperationalDataResetRequest,
    ScopedDeleteResponse,
)
from app.services.admin_reset import (
    AdminResetError,
    delete_client_and_related_data,
    delete_project_and_related_data,
    prepare_operational_reprocessing,
    reset_operational_data,
    reset_project_operational_data,
)
from app.services.dashboard_filter_cache import mark_filter_caches_stale
from app.services.dashboard_filter_facts import refresh_dashboard_filter_facts
from app.services.in_scope_assignment_groups import (
    InScopeAssignmentGroupsError,
    import_in_scope_assignment_groups,
    in_scope_assignment_groups_status,
    list_in_scope_assignment_groups,
)

router = APIRouter(prefix="/admin", tags=["admin"])
DbSession = Annotated[Session, Depends(get_db)]
UPLOAD_COPY_CHUNK_SIZE = 1024 * 1024


async def copy_upload_to_temp_file(upload_file: UploadFile) -> Path:
    suffix = Path(upload_file.filename or "").suffix.lower()
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
        temp_path = Path(temp_file.name)
        while chunk := await upload_file.read(UPLOAD_COPY_CHUNK_SIZE):
            temp_file.write(chunk)
    return temp_path


def reference_preview_response(row) -> InScopeAssignmentGroupPreviewRowResponse:
    return InScopeAssignmentGroupPreviewRowResponse(
        assignment_group=row.assignment_group,
        functional_track=row.functional_track,
        source_row_number=row.source_row_number,
    )


@router.post("/reset-operational-data", response_model=OperationalDataResetResponse)
def post_reset_operational_data(
    request: OperationalDataResetRequest,
    db: DbSession,
) -> OperationalDataResetResponse:
    try:
        result = reset_operational_data(db, request.confirmation)
    except AdminResetError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return OperationalDataResetResponse(
        deleted_counts=result.deleted_counts,
        updated_counts=result.updated_counts or {},
        preserved=result.preserved,
    )


@router.post(
    "/projects/reset-operational-data",
    response_model=OperationalDataResetResponse,
)
def post_reset_project_operational_data(
    request: ProjectOperationalDataResetRequest,
    db: DbSession,
) -> OperationalDataResetResponse:
    try:
        result = reset_project_operational_data(
            db,
            request.project_id,
            request.confirmation,
            reset_incidents=request.reset_incidents,
            reset_sc_tasks=request.reset_sc_tasks,
            reset_problems=request.reset_problems,
            reset_changes=request.reset_changes,
            reset_incident_sla=request.reset_incident_sla,
        )
    except AdminResetError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return OperationalDataResetResponse(
        deleted_counts=result.deleted_counts,
        updated_counts=result.updated_counts or {},
        preserved=result.preserved,
        reset_incidents=result.reset_incidents,
        reset_sc_tasks=result.reset_sc_tasks,
        reset_problems=result.reset_problems,
        reset_changes=result.reset_changes,
        reset_incident_sla=result.reset_incident_sla,
        incident_sla_reset_reason=result.incident_sla_reset_reason,
    )


@router.post(
    "/dashboard-filter-facts/refresh",
    response_model=DashboardFilterFactsRefreshResponse,
)
def post_refresh_dashboard_filter_facts(
    request: DashboardFilterFactsRefreshRequest,
    db: DbSession,
) -> DashboardFilterFactsRefreshResponse:
    try:
        result = refresh_dashboard_filter_facts(db, request.project_id)
        db.commit()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return DashboardFilterFactsRefreshResponse(
        project_id=result.project_id,
        rows_deleted=result.rows_deleted,
        rows_inserted=result.rows_inserted,
        in_scope_rows=result.in_scope_rows,
        out_of_scope_rows=result.out_of_scope_rows,
        duration_ms=result.duration_ms,
    )


@router.post(
    "/in-scope-assignment-groups/import",
    response_model=InScopeAssignmentGroupsImportResponse,
    status_code=status.HTTP_201_CREATED,
)
async def post_import_in_scope_assignment_groups(
    project_id: Annotated[UUID, Form(...)],
    file: Annotated[UploadFile, File(...)],
    db: DbSession,
) -> InScopeAssignmentGroupsImportResponse:
    filename = file.filename or "in-scope-assignment-groups"
    extension = Path(filename).suffix.lower()
    if extension not in {".xlsx", ".csv"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="In-Scope Assignment Groups import supports XLSX and CSV files.",
        )

    temp_path = await copy_upload_to_temp_file(file)
    try:
        result = import_in_scope_assignment_groups(db, project_id, temp_path, filename)
        mark_filter_caches_stale(db, project_id)
        db.commit()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except InScopeAssignmentGroupsError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    finally:
        temp_path.unlink(missing_ok=True)
        await file.close()

    return InScopeAssignmentGroupsImportResponse(
        project_id=result.project_id,
        source_filename=result.source_filename,
        total_rows=result.total_rows,
        imported_count=result.imported_count,
        skipped_count=result.skipped_count,
        duplicate_count=result.duplicate_count,
        warning_count=result.warning_count,
        error_count=result.error_count,
        warnings=result.warnings,
        errors=result.errors,
        preview_rows=[reference_preview_response(row) for row in result.preview_rows],
    )


@router.get(
    "/in-scope-assignment-groups/status",
    response_model=InScopeAssignmentGroupsStatusResponse,
)
def get_in_scope_assignment_groups_status(
    project_id: Annotated[UUID, Query(...)],
    db: DbSession,
) -> InScopeAssignmentGroupsStatusResponse:
    try:
        summary = in_scope_assignment_groups_status(db, project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return InScopeAssignmentGroupsStatusResponse(
        project_id=summary.project_id,
        active_count=summary.active_count,
        last_imported_at=summary.last_imported_at,
        preview_rows=[reference_preview_response(row) for row in summary.preview_rows],
    )


@router.get(
    "/in-scope-assignment-groups",
    response_model=list[InScopeAssignmentGroupRowResponse],
)
def get_in_scope_assignment_groups(
    project_id: Annotated[UUID, Query(...)],
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[InScopeAssignmentGroupRowResponse]:
    try:
        return list_in_scope_assignment_groups(db, project_id, limit=limit, offset=offset)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post(
    "/projects/prepare-operational-reprocessing",
    response_model=OperationalReprocessingResponse,
)
def post_prepare_operational_reprocessing(
    request: OperationalReprocessingRequest,
    db: DbSession,
) -> OperationalReprocessingResponse:
    try:
        result = prepare_operational_reprocessing(
            db,
            request.project_id,
            list(request.domains),
            request.start_point,
            request.confirmation,
        )
    except AdminResetError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return OperationalReprocessingResponse(
        project_id=result.project_id,
        domains=result.domains,
        start_point=result.start_point,
        cleared_counts=result.cleared_counts,
        updated_counts=result.updated_counts,
        preserved=result.preserved,
        warnings=result.warnings,
    )


@router.post("/projects/delete", response_model=ScopedDeleteResponse)
def post_delete_project(
    request: ProjectDeleteRequest,
    db: DbSession,
) -> ScopedDeleteResponse:
    try:
        result = delete_project_and_related_data(
            db,
            request.project_id,
            request.confirmation,
        )
    except AdminResetError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return ScopedDeleteResponse(
        deleted_counts=result.deleted_counts,
        preserved=result.preserved,
    )


@router.post("/clients/delete", response_model=ScopedDeleteResponse)
def post_delete_client(
    request: ClientDeleteRequest,
    db: DbSession,
) -> ScopedDeleteResponse:
    try:
        result = delete_client_and_related_data(
            db,
            request.client_id,
            request.confirmation,
        )
    except AdminResetError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return ScopedDeleteResponse(
        deleted_counts=result.deleted_counts,
        preserved=result.preserved,
    )
