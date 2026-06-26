from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.mapping import (
    ApplyMappingRequest,
    ApplyMappingResponse,
    MappingTemplateResponse,
    MappingTemplateSaveRequest,
    ScopedApplyMappingRequest,
    ScopedApplyMappingResponse,
    SourceColumnsResponse,
    SuggestedMappingResponse,
)
from app.services.mapping import (
    MappingError,
    apply_mapping_to_batch,
    apply_mapping_with_scope,
    get_mapping_template,
    get_suggested_mapping_result,
    get_suggested_mapping_result_for_batch,
    infer_source_columns,
    infer_source_columns_for_ticket_type,
    mapping_rows_to_field_mapping,
    normalize_ticket_type_value,
    save_mapping_template,
)

router = APIRouter(prefix="/mappings", tags=["mappings"])
DbSession = Annotated[Session, Depends(get_db)]


@router.get("/batches/{upload_batch_id}/source-columns", response_model=SourceColumnsResponse)
def get_source_columns(upload_batch_id: UUID, db: DbSession) -> SourceColumnsResponse:
    try:
        source_columns = infer_source_columns(db, upload_batch_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return SourceColumnsResponse(upload_batch_id=upload_batch_id, source_columns=source_columns)


@router.get("/source-columns", response_model=SourceColumnsResponse)
def get_ticket_type_source_columns(
    db: DbSession,
    project_id: Annotated[UUID, Query(...)],
    ticket_type: Annotated[str, Query(min_length=1, max_length=40)],
    upload_batch_id: UUID | None = None,
) -> SourceColumnsResponse:
    try:
        if upload_batch_id is not None:
            source_columns = infer_source_columns(db, upload_batch_id)
        else:
            source_columns = infer_source_columns_for_ticket_type(db, project_id, ticket_type)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return SourceColumnsResponse(
        upload_batch_id=upload_batch_id,
        project_id=project_id,
        ticket_type=normalize_ticket_type_value(ticket_type),
        source_columns=source_columns,
    )


@router.get("/batches/{upload_batch_id}/suggested-mapping", response_model=SuggestedMappingResponse)
def get_suggested_mapping(upload_batch_id: UUID, db: DbSession) -> SuggestedMappingResponse:
    try:
        suggested_mapping = get_suggested_mapping_result_for_batch(db, upload_batch_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except MappingError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return SuggestedMappingResponse(
        upload_batch_id=upload_batch_id,
        project_id=suggested_mapping.project_id,
        ticket_type=suggested_mapping.ticket_type,
        mapping_source=suggested_mapping.mapping_source,
        mapping=suggested_mapping.mapping,
        source_columns=suggested_mapping.source_columns,
        suggested_mapping=suggested_mapping.mapping,
    )


@router.get("/suggested-mapping", response_model=SuggestedMappingResponse)
def get_project_ticket_type_suggested_mapping(
    db: DbSession,
    project_id: Annotated[UUID, Query(...)],
    ticket_type: Annotated[str, Query(min_length=1, max_length=40)],
    upload_batch_id: UUID | None = None,
) -> SuggestedMappingResponse:
    try:
        suggested_mapping = get_suggested_mapping_result(
            db=db,
            project_id=project_id,
            ticket_type=ticket_type,
            upload_batch_id=upload_batch_id,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except MappingError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return SuggestedMappingResponse(
        upload_batch_id=upload_batch_id,
        project_id=suggested_mapping.project_id,
        ticket_type=suggested_mapping.ticket_type,
        mapping_source=suggested_mapping.mapping_source,
        mapping=suggested_mapping.mapping,
        source_columns=suggested_mapping.source_columns,
        suggested_mapping=suggested_mapping.mapping,
    )


@router.post(
    "/templates",
    response_model=MappingTemplateResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_mapping_template(
    request: MappingTemplateSaveRequest,
    db: DbSession,
) -> MappingTemplateResponse:
    try:
        saved_rows = save_mapping_template(
            db=db,
            project_id=request.project_id,
            ticket_type=request.ticket_type,
            mapping=request.mapping,
            notes=request.notes,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except MappingError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    ticket_type = request.ticket_type.strip().upper()
    return MappingTemplateResponse(
        project_id=request.project_id,
        ticket_type=ticket_type,
        mapping=mapping_rows_to_field_mapping(saved_rows),
        columns=saved_rows,
    )


@router.get("/templates", response_model=MappingTemplateResponse)
def read_mapping_template(
    db: DbSession,
    project_id: Annotated[UUID, Query(...)],
    ticket_type: Annotated[str, Query(min_length=1, max_length=40)],
) -> MappingTemplateResponse:
    saved_rows = get_mapping_template(db, project_id, ticket_type)
    return MappingTemplateResponse(
        project_id=project_id,
        ticket_type=ticket_type.strip().upper(),
        mapping=mapping_rows_to_field_mapping(saved_rows),
        columns=saved_rows,
    )


@router.post("/batches/{upload_batch_id}/apply", response_model=ApplyMappingResponse)
def apply_mapping(
    upload_batch_id: UUID,
    request: ApplyMappingRequest,
    db: DbSession,
) -> ApplyMappingResponse:
    try:
        if request.save_as_default_for_ticket_type:
            suggested_mapping = get_suggested_mapping_result_for_batch(db, upload_batch_id)
            save_mapping_template(
                db=db,
                project_id=suggested_mapping.project_id,
                ticket_type=suggested_mapping.ticket_type,
                mapping=request.mapping or suggested_mapping.mapping,
            )
        result = apply_mapping_to_batch(
            db=db,
            upload_batch_id=upload_batch_id,
            mapping=request.mapping,
            delete_existing=request.delete_existing,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except MappingError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    return ApplyMappingResponse(
        upload_batch_id=result.upload_batch_id,
        status=result.status,
        total_raw_rows=result.total_raw_rows,
        normalized_ticket_count=result.normalized_ticket_count,
        out_of_scope_ticket_count=result.out_of_scope_ticket_count,
        blank_assignment_group_count=result.blank_assignment_group_count,
        assignment_group_not_in_inventory_count=(
            result.assignment_group_not_in_inventory_count
        ),
        duplicate_skipped_count=result.duplicate_skipped_count,
        failed_row_count=result.failed_row_count,
        warnings=result.warnings,
        errors=result.errors,
    )


@router.post("/apply", response_model=ScopedApplyMappingResponse)
def apply_mapping_for_scope(
    request: ScopedApplyMappingRequest,
    db: DbSession,
) -> ScopedApplyMappingResponse:
    try:
        result = apply_mapping_with_scope(
            db=db,
            project_id=request.project_id,
            ticket_type=request.ticket_type,
            upload_batch_id=request.upload_batch_id,
            scope=request.scope,
            mapping=request.mapping,
            delete_existing=request.delete_existing,
            save_as_default_for_ticket_type=request.save_as_default_for_ticket_type,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except MappingError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    return ScopedApplyMappingResponse(
        scope=result.scope,
        project_id=result.project_id,
        ticket_type=result.ticket_type,
        mapping_source=result.mapping_source,
        saved_as_default_for_ticket_type=result.saved_as_default_for_ticket_type,
        batch_results=result.batch_results,
        total_raw_rows=result.total_raw_rows,
        normalized_ticket_count=result.normalized_ticket_count,
        out_of_scope_ticket_count=result.out_of_scope_ticket_count,
        blank_assignment_group_count=result.blank_assignment_group_count,
        assignment_group_not_in_inventory_count=(
            result.assignment_group_not_in_inventory_count
        ),
        duplicate_skipped_count=result.duplicate_skipped_count,
        failed_row_count=result.failed_row_count,
        warnings=result.warnings,
        errors=result.errors,
    )
