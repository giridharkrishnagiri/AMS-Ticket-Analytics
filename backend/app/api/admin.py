from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.admin import (
    ClientDeleteRequest,
    DashboardFilterFactsRefreshRequest,
    DashboardFilterFactsRefreshResponse,
    OperationalDataResetRequest,
    OperationalDataResetResponse,
    ProjectDeleteRequest,
    ProjectOperationalDataResetRequest,
    ScopedDeleteResponse,
)
from app.services.admin_reset import (
    AdminResetError,
    delete_client_and_related_data,
    delete_project_and_related_data,
    reset_operational_data,
    reset_project_operational_data,
)
from app.services.dashboard_filter_facts import refresh_dashboard_filter_facts

router = APIRouter(prefix="/admin", tags=["admin"])
DbSession = Annotated[Session, Depends(get_db)]


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
