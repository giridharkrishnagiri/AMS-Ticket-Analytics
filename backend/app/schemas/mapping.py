from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SourceColumnResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    normalized_name: str
    occurrence_count: int


class SourceColumnsResponse(BaseModel):
    upload_batch_id: UUID | None = None
    project_id: UUID | None = None
    ticket_type: str | None = None
    source_columns: list[SourceColumnResponse]


class SuggestedMappingResponse(BaseModel):
    upload_batch_id: UUID | None = None
    project_id: UUID | None = None
    ticket_type: str | None = None
    mapping_source: Literal["SAVED_TEMPLATE", "BUILT_IN_SUGGESTION"] = "BUILT_IN_SUGGESTION"
    mapping: dict[str, str] = Field(default_factory=dict)
    source_columns: list[str]
    suggested_mapping: dict[str, str]


class MappingTemplateSaveRequest(BaseModel):
    project_id: UUID
    ticket_type: str = Field(min_length=1, max_length=40)
    mapping: dict[str, str]
    notes: str | None = None


class MappingTemplateColumnResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source_column_name: str
    normalized_field_name: str | None
    data_type: str | None
    is_required: bool
    notes: str | None
    created_at: datetime
    updated_at: datetime


class MappingTemplateResponse(BaseModel):
    project_id: UUID
    ticket_type: str
    mapping: dict[str, str]
    columns: list[MappingTemplateColumnResponse]


class ApplyMappingRequest(BaseModel):
    mapping: dict[str, str] | None = None
    delete_existing: bool = True
    save_as_default_for_ticket_type: bool = False


class ScopedApplyMappingRequest(BaseModel):
    project_id: UUID
    ticket_type: str = Field(min_length=1, max_length=40)
    upload_batch_id: UUID | None = None
    scope: Literal["BATCH", "TICKET_TYPE"]
    mapping: dict[str, str] | None = None
    delete_existing: bool = True
    save_as_default_for_ticket_type: bool = True


class NormalizationErrorSampleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    row_number: int
    raw_row_id: UUID
    message: str


class ApplyMappingResponse(BaseModel):
    upload_batch_id: UUID
    status: str | None = None
    total_raw_rows: int
    normalized_ticket_count: int
    failed_row_count: int
    warnings: list[str]
    errors: list[NormalizationErrorSampleResponse]


class BatchApplyMappingResultResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    upload_batch_id: UUID
    batch_name: str
    status: str | None = None
    total_raw_rows: int
    normalized_ticket_count: int
    failed_row_count: int
    warnings: list[str]
    errors: list[NormalizationErrorSampleResponse]


class ScopedApplyMappingResponse(BaseModel):
    scope: Literal["BATCH", "TICKET_TYPE"]
    project_id: UUID
    ticket_type: str
    mapping_source: Literal["REQUEST_BODY", "SAVED_TEMPLATE", "BUILT_IN_SUGGESTION"]
    saved_as_default_for_ticket_type: bool
    batch_results: list[BatchApplyMappingResultResponse]
    total_raw_rows: int
    normalized_ticket_count: int
    failed_row_count: int
    warnings: list[str]
    errors: list[NormalizationErrorSampleResponse]
