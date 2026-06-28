from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.genai import (
    GenAIConfigResponse,
    GenAIConfigUpdateRequest,
    GenAIPromptReseedResponse,
    GenAIPromptTemplateResponse,
    GenAIPromptTemplateUpdateRequest,
    GenAISafetySettingsResponse,
    GenAISafetySettingsUpdateRequest,
    GenAITestRequest,
    GenAITestResponse,
    GenAIUsageLogResponse,
    GenAIUsageSummary,
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
