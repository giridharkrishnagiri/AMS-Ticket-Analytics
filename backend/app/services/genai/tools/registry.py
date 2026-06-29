from __future__ import annotations

import re
from time import perf_counter
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import GenAIToolRun
from app.schemas.genai import (
    GenAIToolCatalogItem,
    GenAIToolExecuteRequest,
    GenAIToolExecuteResponse,
)
from app.services.genai.safety_service import get_or_create_safety_settings
from app.services.genai.tools.application_tools import (
    ApplicationCriticalityHostingMatrixTool,
    ApplicationDistributionTool,
    ApplicationInventorySummaryTool,
    ApplicationLifecyclePlanningSummaryTool,
    TopParentApplicationsByActiveUsersTool,
)
from app.services.genai.tools.base import (
    GovernedTool,
    ToolExecutionRequest,
    ToolMetadata,
    tool_response,
)
from app.services.genai.tools.sla_ola_tools import SlaOlaByDimensionTool, SlaOlaSummaryTool
from app.services.genai.tools.ticket_tools import (
    TicketDistributionTool,
    TicketTrendSummaryTool,
    TicketVolumeSummaryTool,
    TopApplicationsByTicketVolumeTool,
)
from app.services.genai.tools.validation import ToolValidationError
from app.services.genai.usage_log_service import create_usage_log

SENSITIVE_KEY_PATTERN = re.compile(
    r"(normalized_payload|cmdb_payload|raw_sla|raw_ola|api_key|password|secret)",
    re.IGNORECASE,
)

REGISTERED_TOOLS: tuple[GovernedTool, ...] = (
    ApplicationInventorySummaryTool(),
    ApplicationDistributionTool(),
    TopParentApplicationsByActiveUsersTool(),
    ApplicationCriticalityHostingMatrixTool(),
    ApplicationLifecyclePlanningSummaryTool(),
    TicketVolumeSummaryTool(),
    TicketTrendSummaryTool(),
    TicketDistributionTool(),
    TopApplicationsByTicketVolumeTool(),
    SlaOlaSummaryTool(),
    SlaOlaByDimensionTool(),
)

TOOLS_BY_NAME: dict[str, GovernedTool] = {
    tool.metadata.tool_name: tool for tool in REGISTERED_TOOLS
}


def _metadata_to_catalog_item(metadata: ToolMetadata) -> GenAIToolCatalogItem:
    return GenAIToolCatalogItem(
        tool_name=metadata.tool_name,
        domain=metadata.domain,
        display_name=metadata.display_name,
        description=metadata.description,
        input_schema=metadata.input_schema,
        output_schema=metadata.output_schema,
        allowed_dimensions=list(metadata.allowed_dimensions),
        allowed_metrics=list(metadata.allowed_metrics),
        max_rows=metadata.max_rows,
        data_safety_level=metadata.data_safety_level,
    )


def list_tools() -> list[GenAIToolCatalogItem]:
    return [
        _metadata_to_catalog_item(tool.metadata)
        for tool in sorted(
            REGISTERED_TOOLS, key=lambda item: (item.metadata.domain, item.metadata.tool_name)
        )
    ]


def get_tool(tool_name: str) -> GovernedTool | None:
    return TOOLS_BY_NAME.get(tool_name)


def _safe_json(value: Any) -> Any:
    if isinstance(value, dict):
        safe: dict[str, Any] = {}
        for key, child_value in value.items():
            key_text = str(key)
            if SENSITIVE_KEY_PATTERN.search(key_text):
                safe["redacted_payload_field"] = "[redacted]"
            else:
                safe[key_text] = _safe_json(child_value)
        return safe
    if isinstance(value, list):
        return [_safe_json(item) for item in value[:100]]
    if isinstance(value, str) and len(value) > 500:
        return f"{value[:500]}..."
    return value


def _build_unknown_tool_response(request: GenAIToolExecuteRequest) -> GenAIToolExecuteResponse:
    metadata = ToolMetadata(
        tool_name=request.tool_name,
        domain="unknown",
        display_name="Unknown Governed Tool",
        description="The requested governed analytics tool is not registered.",
        max_rows=0,
    )
    return tool_response(
        metadata=metadata,
        status="rejected",
        title="Unknown Governed Tool",
        description=metadata.description,
        warnings=[f"Tool '{request.tool_name}' is not registered."],
    )


def _log_tool_run(
    db: Session,
    *,
    request: GenAIToolExecuteRequest,
    response: GenAIToolExecuteResponse,
    error_message: str | None = None,
) -> GenAIToolRun:
    row = GenAIToolRun(
        tool_name=request.tool_name,
        domain=response.domain,
        customer_id=request.customer_id,
        project_id=request.project_id,
        status=response.status,
        parameters_json=_safe_json(request.parameters),
        filters_json=_safe_json(request.filters),
        row_count=response.row_count,
        truncated=response.truncated,
        execution_ms=response.execution_ms,
        warnings_json=response.warnings,
        error_message=error_message,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    create_usage_log(
        db,
        operation="tool_execution",
        status=response.status,
        customer_id=request.customer_id,
        project_id=request.project_id,
        question=request.tool_name,
        tools_used_json=[request.tool_name],
        duration_ms=response.execution_ms,
        error_message=error_message or "; ".join(response.warnings[:3]) or None,
    )
    return row


def execute_tool(db: Session, request: GenAIToolExecuteRequest) -> GenAIToolExecuteResponse:
    started = perf_counter()
    tool = get_tool(request.tool_name)
    if tool is None:
        response = _build_unknown_tool_response(request)
        response.execution_ms = int((perf_counter() - started) * 1000)
        _log_tool_run(db, request=request, response=response, error_message=response.warnings[0])
        return response

    safety_settings = get_or_create_safety_settings(db)
    execution_request = ToolExecutionRequest(
        tool_name=request.tool_name,
        customer_id=request.customer_id,
        project_id=request.project_id,
        parameters=request.parameters or {},
        filters=request.filters or {},
        safety_settings=safety_settings,
    )

    try:
        response = tool.execute(db, execution_request)
    except ToolValidationError as exc:
        response = tool_response(
            metadata=tool.metadata,
            status="rejected",
            title=tool.metadata.display_name,
            description=tool.metadata.description,
            warnings=[str(exc)],
        )
    except Exception as exc:  # noqa: BLE001 - convert unexpected tool failures into clean API responses.
        response = tool_response(
            metadata=tool.metadata,
            status="error",
            title=tool.metadata.display_name,
            description=tool.metadata.description,
            warnings=["Tool execution failed. Check backend logs for details."],
        )
        response.execution_ms = int((perf_counter() - started) * 1000)
        _log_tool_run(db, request=request, response=response, error_message=str(exc))
        return response

    response.execution_ms = int((perf_counter() - started) * 1000)
    error_message = "; ".join(response.warnings[:3]) if response.status != "success" else None
    _log_tool_run(db, request=request, response=response, error_message=error_message)
    return response


def list_tool_runs(
    db: Session,
    *,
    limit: int,
    offset: int,
    tool_name: str | None = None,
    domain: str | None = None,
    status: str | None = None,
) -> list[GenAIToolRun]:
    statement = select(GenAIToolRun)
    if tool_name:
        statement = statement.where(GenAIToolRun.tool_name == tool_name)
    if domain:
        statement = statement.where(GenAIToolRun.domain == domain)
    if status:
        statement = statement.where(GenAIToolRun.status == status)
    statement = statement.order_by(GenAIToolRun.created_at.desc()).limit(limit).offset(offset)
    return db.execute(statement).scalars().all()
