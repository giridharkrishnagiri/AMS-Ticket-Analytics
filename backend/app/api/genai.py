from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.genai import (
    GenAIChartDuplicateRequest,
    GenAIChartFromToolResultRequest,
    GenAIChartUpdateRequest,
    GenAIChatMessageCreateRequest,
    GenAIChatMessageCreateResponse,
    GenAIChatSessionCreateRequest,
    GenAIChatSessionDetailResponse,
    GenAIChatSessionListResponse,
    GenAIChatSessionResponse,
    GenAIChatSessionUpdateRequest,
    GenAIConfigResponse,
    GenAIConfigUpdateRequest,
    GenAIContextOptionResponse,
    GenAIGeneratedChartListResponse,
    GenAIGeneratedChartResponse,
    GenAIPromptReseedResponse,
    GenAIPromptTemplateResponse,
    GenAIPromptTemplateUpdateRequest,
    GenAISafetySettingsResponse,
    GenAISafetySettingsUpdateRequest,
    GenAITestRequest,
    GenAITestResponse,
    GenAIToolCatalogResponse,
    GenAIToolExecuteRequest,
    GenAIToolExecuteResponse,
    GenAIToolRunResponse,
    GenAIUsageLogResponse,
    GenAIUsageSummary,
)
from app.services.genai.charts import (
    archive_generated_chart,
    create_chart_from_tool_result,
    duplicate_generated_chart,
    get_generated_chart,
    list_generated_charts,
    reset_generated_chart,
    update_generated_chart,
)
from app.services.genai.charts.chart_store import (
    GeneratedChartNotFoundError,
    to_chart_list_item,
    to_chart_response,
)
from app.services.genai.charts.validation import ChartValidationError
from app.services.genai.chat_service import (
    ChatServiceError,
    ChatSessionNotFoundError,
    archive_session,
    create_session,
    get_session,
    get_session_messages,
    list_context_customers,
    list_context_projects,
    list_sessions,
    send_chat_message,
    update_session,
)
from app.services.genai.config_service import get_or_create_config, update_config
from app.services.genai.llm_client import SAFE_DEFAULT_TEST_PROMPT, test_completion
from app.services.genai.prompt_service import (
    PromptTemplateError,
    ensure_default_prompts,
    get_prompt_template,
    list_prompt_templates,
    reset_prompt_template,
    update_prompt_template,
)
from app.services.genai.safety_service import (
    get_or_create_safety_settings,
    update_safety_settings,
)
from app.services.genai.tools import execute_tool, list_tool_runs, list_tools
from app.services.genai.usage_log_service import create_usage_log, list_usage_logs

router = APIRouter(prefix="/genai", tags=["genai"])
DbSession = Annotated[Session, Depends(get_db)]


@router.get("/config", response_model=GenAIConfigResponse)
def get_genai_config(db: DbSession) -> GenAIConfigResponse:
    return get_or_create_config(db)


@router.put("/config", response_model=GenAIConfigResponse)
def put_genai_config(
    request: GenAIConfigUpdateRequest,
    db: DbSession,
) -> GenAIConfigResponse:
    return update_config(db, request.model_dump(exclude_unset=True))


@router.get("/prompts", response_model=list[GenAIPromptTemplateResponse])
def get_genai_prompts(db: DbSession) -> list[GenAIPromptTemplateResponse]:
    return list_prompt_templates(db)


@router.post("/prompts/reseed-defaults", response_model=GenAIPromptReseedResponse)
def post_reseed_genai_prompts(db: DbSession) -> GenAIPromptReseedResponse:
    rows = ensure_default_prompts(db)
    return GenAIPromptReseedResponse(
        prompt_count=len(rows),
        prompt_keys=[row.prompt_key for row in rows],
    )


@router.get("/prompts/{prompt_key}", response_model=GenAIPromptTemplateResponse)
def get_genai_prompt(prompt_key: str, db: DbSession) -> GenAIPromptTemplateResponse:
    try:
        return get_prompt_template(db, prompt_key)
    except PromptTemplateError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.put("/prompts/{prompt_key}", response_model=GenAIPromptTemplateResponse)
def put_genai_prompt(
    prompt_key: str,
    request: GenAIPromptTemplateUpdateRequest,
    db: DbSession,
) -> GenAIPromptTemplateResponse:
    try:
        return update_prompt_template(
            db,
            prompt_key,
            custom_prompt=request.custom_prompt,
            is_custom_enabled=request.is_custom_enabled,
        )
    except PromptTemplateError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/prompts/{prompt_key}/reset", response_model=GenAIPromptTemplateResponse)
def post_reset_genai_prompt(prompt_key: str, db: DbSession) -> GenAIPromptTemplateResponse:
    try:
        return reset_prompt_template(db, prompt_key)
    except PromptTemplateError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/safety-settings", response_model=GenAISafetySettingsResponse)
def get_genai_safety_settings(db: DbSession) -> GenAISafetySettingsResponse:
    return get_or_create_safety_settings(db)


@router.put("/safety-settings", response_model=GenAISafetySettingsResponse)
def put_genai_safety_settings(
    request: GenAISafetySettingsUpdateRequest,
    db: DbSession,
) -> GenAISafetySettingsResponse:
    return update_safety_settings(db, request.model_dump(exclude_unset=True))


@router.get("/tools/catalog", response_model=GenAIToolCatalogResponse)
def get_genai_tools_catalog() -> GenAIToolCatalogResponse:
    return GenAIToolCatalogResponse(items=list_tools())


@router.post("/tools/execute", response_model=GenAIToolExecuteResponse)
def post_genai_tool_execute(
    request: GenAIToolExecuteRequest,
    db: DbSession,
) -> GenAIToolExecuteResponse:
    return execute_tool(db, request)


@router.get("/tools/runs", response_model=list[GenAIToolRunResponse])
def get_genai_tool_runs(
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    tool_name: str | None = None,
    domain: str | None = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
) -> list[GenAIToolRunResponse]:
    return list_tool_runs(
        db,
        limit=limit,
        offset=offset,
        tool_name=tool_name,
        domain=domain,
        status=status_filter,
    )


@router.get("/charts", response_model=GenAIGeneratedChartListResponse)
def get_genai_charts(
    db: DbSession,
    customer_id: UUID | None = None,
    project_id: UUID | None = None,
    session_id: str | None = None,
    chart_type: str | None = None,
    include_archived: bool = False,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> GenAIGeneratedChartListResponse:
    result = list_generated_charts(
        db,
        customer_id=customer_id,
        project_id=project_id,
        session_id=session_id,
        chart_type=chart_type,
        include_archived=include_archived,
        limit=limit,
        offset=offset,
    )
    return GenAIGeneratedChartListResponse(
        items=[to_chart_list_item(item) for item in result.items],
        total=result.total,
    )


@router.get("/charts/{chart_id}", response_model=GenAIGeneratedChartResponse)
def get_genai_chart(chart_id: UUID, db: DbSession) -> GenAIGeneratedChartResponse:
    try:
        return to_chart_response(get_generated_chart(db, chart_id))
    except GeneratedChartNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.put("/charts/{chart_id}", response_model=GenAIGeneratedChartResponse)
def put_genai_chart(
    chart_id: UUID,
    request: GenAIChartUpdateRequest,
    db: DbSession,
) -> GenAIGeneratedChartResponse:
    try:
        chart = update_generated_chart(db, chart_id, request.model_dump(exclude_unset=True))
    except GeneratedChartNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ChartValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return to_chart_response(chart)


@router.post("/charts/{chart_id}/duplicate", response_model=GenAIGeneratedChartResponse)
def post_duplicate_genai_chart(
    chart_id: UUID,
    request: GenAIChartDuplicateRequest,
    db: DbSession,
) -> GenAIGeneratedChartResponse:
    try:
        return to_chart_response(duplicate_generated_chart(db, chart_id, title=request.title))
    except GeneratedChartNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/charts/{chart_id}/archive", response_model=GenAIGeneratedChartResponse)
def post_archive_genai_chart(chart_id: UUID, db: DbSession) -> GenAIGeneratedChartResponse:
    try:
        return to_chart_response(archive_generated_chart(db, chart_id))
    except GeneratedChartNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/charts/{chart_id}/reset", response_model=GenAIGeneratedChartResponse)
def post_reset_genai_chart(chart_id: UUID, db: DbSession) -> GenAIGeneratedChartResponse:
    try:
        return to_chart_response(reset_generated_chart(db, chart_id))
    except GeneratedChartNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/charts/from-tool-result", response_model=GenAIGeneratedChartResponse)
def post_genai_chart_from_tool_result(
    request: GenAIChartFromToolResultRequest,
    db: DbSession,
) -> GenAIGeneratedChartResponse:
    try:
        chart = create_chart_from_tool_result(
            db,
            tool_result=request.tool_result,
            customer_id=request.customer_id,
            project_id=request.project_id,
            session_id=request.session_id,
            message_id=request.message_id,
            question=request.question,
            chart_type=request.chart_type,
        )
    except ChartValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return to_chart_response(chart)


@router.get("/context/customers", response_model=list[GenAIContextOptionResponse])
def get_genai_context_customers(db: DbSession) -> list[GenAIContextOptionResponse]:
    return [
        GenAIContextOptionResponse(
            id=customer.id,
            name=customer.name,
            code=customer.code,
            label=customer.name,
        )
        for customer in list_context_customers(db)
    ]


@router.get("/context/projects", response_model=list[GenAIContextOptionResponse])
def get_genai_context_projects(
    db: DbSession,
    customer_id: UUID | None = None,
) -> list[GenAIContextOptionResponse]:
    return [
        GenAIContextOptionResponse(
            id=project.id,
            name=project.name,
            code=project.code,
            customer_id=customer.id,
            customer_name=customer.name,
            customer_code=customer.code,
            label=f"{customer.name} - {project.name}",
        )
        for project, customer in list_context_projects(db, customer_id)
    ]


@router.post("/chat-sessions", response_model=GenAIChatSessionResponse)
def post_genai_chat_session(
    request: GenAIChatSessionCreateRequest,
    db: DbSession,
) -> GenAIChatSessionResponse:
    return create_session(
        db,
        customer_id=request.customer_id,
        project_id=request.project_id,
        title=request.title,
        metadata=request.metadata,
    )


@router.get("/chat-sessions", response_model=GenAIChatSessionListResponse)
def get_genai_chat_sessions(
    db: DbSession,
    customer_id: UUID | None = None,
    project_id: UUID | None = None,
    include_archived: bool = False,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> GenAIChatSessionListResponse:
    result = list_sessions(
        db,
        customer_id=customer_id,
        project_id=project_id,
        include_archived=include_archived,
        limit=limit,
        offset=offset,
    )
    return GenAIChatSessionListResponse(items=result.items, total=result.total)


@router.get("/chat-sessions/{session_id}", response_model=GenAIChatSessionDetailResponse)
def get_genai_chat_session(
    session_id: UUID,
    db: DbSession,
) -> GenAIChatSessionDetailResponse:
    try:
        session = get_session(db, session_id)
    except ChatSessionNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return GenAIChatSessionDetailResponse(
        session=session,
        messages=get_session_messages(db, session_id),
    )


@router.put("/chat-sessions/{session_id}", response_model=GenAIChatSessionResponse)
def put_genai_chat_session(
    session_id: UUID,
    request: GenAIChatSessionUpdateRequest,
    db: DbSession,
) -> GenAIChatSessionResponse:
    try:
        return update_session(
            db,
            session_id,
            title=request.title,
            metadata=request.metadata,
        )
    except ChatSessionNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/chat-sessions/{session_id}/archive", response_model=GenAIChatSessionResponse)
def post_archive_genai_chat_session(
    session_id: UUID,
    db: DbSession,
) -> GenAIChatSessionResponse:
    try:
        return archive_session(db, session_id)
    except ChatSessionNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post(
    "/chat-sessions/{session_id}/messages",
    response_model=GenAIChatMessageCreateResponse,
)
def post_genai_chat_message(
    session_id: UUID,
    request: GenAIChatMessageCreateRequest,
    db: DbSession,
) -> GenAIChatMessageCreateResponse:
    try:
        result = send_chat_message(
            db,
            session_id=session_id,
            content=request.content,
            context=request.context,
        )
    except ChatSessionNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ChatServiceError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return GenAIChatMessageCreateResponse(
        user_message=result.user_message,
        assistant_message=result.assistant_message,
        session=result.session,
    )


@router.post("/test", response_model=GenAITestResponse)
def post_genai_test(request: GenAITestRequest, db: DbSession) -> GenAITestResponse:
    config = get_or_create_config(db)
    prompt = (request.test_prompt or SAFE_DEFAULT_TEST_PROMPT).strip() or SAFE_DEFAULT_TEST_PROMPT
    provider = config.provider
    model_name = config.model_name

    if not config.is_enabled:
        error_message = "GenAI is disabled. Enable GenAI and configure a model before testing."
        create_usage_log(
            db,
            operation="config_test",
            status="disabled",
            provider=provider,
            model_name=model_name,
            question=prompt,
            error_message=error_message,
        )
        return GenAITestResponse(
            ok=False,
            provider=provider,
            model_name=model_name,
            error_message=error_message,
        )

    if not model_name or not model_name.strip():
        error_message = "Model name is not configured for GenAI."
        create_usage_log(
            db,
            operation="config_test",
            status="error",
            provider=provider,
            model_name=model_name,
            question=prompt,
            error_message=error_message,
        )
        return GenAITestResponse(
            ok=False,
            provider=provider,
            model_name=model_name,
            error_message=error_message,
        )

    result = test_completion(config, prompt)
    create_usage_log(
        db,
        operation="config_test",
        status="success" if result.ok else "error",
        provider=provider,
        model_name=model_name,
        question=prompt,
        prompt_tokens=result.prompt_tokens,
        completion_tokens=result.completion_tokens,
        estimated_cost=result.estimated_cost,
        duration_ms=result.duration_ms,
        error_message=result.error_message,
    )
    return GenAITestResponse(
        ok=result.ok,
        provider=provider,
        model_name=model_name,
        response_text=result.response_text,
        duration_ms=result.duration_ms,
        usage=GenAIUsageSummary(
            prompt_tokens=result.prompt_tokens,
            completion_tokens=result.completion_tokens,
            estimated_cost=result.estimated_cost,
        ),
        error_message=result.error_message,
    )


@router.get("/usage-logs", response_model=list[GenAIUsageLogResponse])
def get_genai_usage_logs(
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    operation: str | None = None,
) -> list[GenAIUsageLogResponse]:
    return list_usage_logs(
        db,
        limit=limit,
        offset=offset,
        status=status_filter,
        operation=operation,
    )
