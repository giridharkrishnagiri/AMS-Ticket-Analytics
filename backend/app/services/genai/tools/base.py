from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy.orm import Session

from app.models import GenAISafetySettings
from app.schemas.genai import GenAIToolColumn, GenAIToolExecuteResponse, GenAIToolSummary


@dataclass(frozen=True)
class ToolMetadata:
    tool_name: str
    domain: str
    display_name: str
    description: str
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)
    allowed_dimensions: tuple[str, ...] = ()
    allowed_metrics: tuple[str, ...] = ()
    max_rows: int = 100
    data_safety_level: str = "aggregate"


@dataclass(frozen=True)
class ToolExecutionRequest:
    tool_name: str
    customer_id: UUID | None
    project_id: UUID | None
    parameters: dict[str, Any]
    filters: dict[str, Any]
    safety_settings: GenAISafetySettings


class GovernedTool(Protocol):
    metadata: ToolMetadata

    def execute(self, db: Session, request: ToolExecutionRequest) -> GenAIToolExecuteResponse: ...


def tool_response(
    *,
    metadata: ToolMetadata,
    status: str,
    title: str,
    description: str | None = None,
    columns: list[GenAIToolColumn] | None = None,
    rows: list[dict[str, Any]] | None = None,
    totals: dict[str, Any] | None = None,
    applied_filters: dict[str, Any] | None = None,
    data_notes: list[str] | None = None,
    warnings: list[str] | None = None,
    row_count: int | None = None,
    truncated: bool = False,
    execution_ms: int | None = None,
) -> GenAIToolExecuteResponse:
    response_rows = rows or []
    return GenAIToolExecuteResponse(
        tool_name=metadata.tool_name,
        domain=metadata.domain,
        status=status,
        summary=GenAIToolSummary(title=title, description=description),
        columns=columns or [],
        rows=response_rows,
        totals=totals or {},
        applied_filters=applied_filters or {},
        data_notes=data_notes or [],
        warnings=warnings or [],
        row_count=len(response_rows) if row_count is None else row_count,
        truncated=truncated,
        execution_ms=execution_ms,
    )


def rejected_response(
    metadata: ToolMetadata,
    warning: str,
    *,
    title: str | None = None,
) -> GenAIToolExecuteResponse:
    return tool_response(
        metadata=metadata,
        status="rejected",
        title=title or metadata.display_name,
        description=metadata.description,
        warnings=[warning],
    )


def unsupported_response(
    metadata: ToolMetadata,
    warning: str,
    *,
    data_notes: list[str] | None = None,
) -> GenAIToolExecuteResponse:
    return tool_response(
        metadata=metadata,
        status="unsupported",
        title=metadata.display_name,
        description=metadata.description,
        data_notes=data_notes or [],
        warnings=[warning],
    )
