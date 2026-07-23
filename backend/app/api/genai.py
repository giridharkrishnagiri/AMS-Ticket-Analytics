from __future__ import annotations

import csv
import io
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from openpyxl import Workbook
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
    GenAITicketAutomationClearRequest,
    GenAITicketAutomationClearResponse,
    GenAITicketAutomationResultsResponse,
    GenAITicketAutomationRunRequest,
    GenAITicketAutomationRunResponse,
    GenAITicketCategoryQualityRunRequest,
    GenAITicketCategoryQualityRunResponse,
    GenAITicketClassificationClearRequest,
    GenAITicketClassificationClearResponse,
    GenAITicketClassificationPivotResponse,
    GenAITicketClassificationRunRequest,
    GenAITicketClassificationRunResponse,
    GenAITicketClassificationSummaryResponse,
    GenAITicketClassificationUsageRunsResponse,
    GenAITicketClusterClearRequest,
    GenAITicketClusterClearResponse,
    GenAITicketClusterRunRequest,
    GenAITicketClusterRunResponse,
    GenAITicketEmbeddingClearRequest,
    GenAITicketEmbeddingClearResponse,
    GenAIToolCatalogResponse,
    GenAIToolExecuteRequest,
    GenAIToolExecuteResponse,
    GenAIToolRunResponse,
    GenAIUsageLogResponse,
    GenAIUsageSummary,
    GenAIWorkbenchSettingsResponse,
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
from app.services.genai.ticket_automation import (
    TicketAutomationAnalysisClearRequest as ServiceTicketAutomationAnalysisClearRequest,
)
from app.services.genai.ticket_automation import (
    TicketAutomationAnalysisError,
    automation_analysis_csv,
    automation_results,
    automation_usage_runs,
    clear_ticket_automation_analysis,
    run_ticket_automation_analysis,
)
from app.services.genai.ticket_automation import (
    TicketAutomationAnalysisRunRequest as ServiceTicketAutomationAnalysisRunRequest,
)
from app.services.genai.ticket_classification import (
    TicketCategoryQualityRunRequest as ServiceTicketCategoryQualityRunRequest,
)
from app.services.genai.ticket_classification import (
    TicketClassificationClearRequest as ServiceTicketClassificationClearRequest,
)
from app.services.genai.ticket_classification import (
    TicketClassificationError,
    analysis_range_slug,
    clear_ticket_classification,
    run_ticket_category_quality_analysis,
    run_ticket_classification,
    ticket_category_quality_usage_runs,
    ticket_classification_dump_csv,
    ticket_classification_pivot,
    ticket_classification_summary,
    ticket_classification_usage_runs,
)
from app.services.genai.ticket_classification import (
    TicketClassificationRunRequest as ServiceTicketClassificationRunRequest,
)
from app.services.genai.ticket_clustering import (
    TicketClusterClearRequest as ServiceTicketClusterClearRequest,
)
from app.services.genai.ticket_clustering import (
    TicketClusteringError,
    clear_project_ticket_embeddings,
    clear_ticket_cluster_analysis,
    run_ticket_cluster_analysis,
    ticket_cluster_usage_runs,
    workbench_settings,
)
from app.services.genai.ticket_clustering import (
    TicketClusterRunRequest as ServiceTicketClusterRunRequest,
)
from app.services.genai.ticket_clustering import (
    TicketEmbeddingClearRequest as ServiceTicketEmbeddingClearRequest,
)
from app.services.genai.tools import execute_tool, list_tool_runs, list_tools
from app.services.genai.usage_log_service import create_usage_log, list_usage_logs

router = APIRouter(prefix="/genai", tags=["genai"])
DbSession = Annotated[Session, Depends(get_db)]
XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def csv_text_to_xlsx_bytes(csv_text: str, sheet_name: str) -> bytes:
    workbook = Workbook(write_only=True)
    worksheet = workbook.create_sheet(title=sheet_name[:31] or "Export")
    reader = csv.reader(io.StringIO(csv_text))
    for row in reader:
        worksheet.append(row)
    output = io.BytesIO()
    workbook.save(output)
    return output.getvalue()


@router.get("/config", response_model=GenAIConfigResponse)
def get_genai_config(db: DbSession) -> GenAIConfigResponse:
    return get_or_create_config(db)


@router.put("/config", response_model=GenAIConfigResponse)
def put_genai_config(
    request: GenAIConfigUpdateRequest,
    db: DbSession,
) -> GenAIConfigResponse:
    return update_config(db, request.model_dump(exclude_unset=True))


@router.get("/workbench-settings", response_model=GenAIWorkbenchSettingsResponse)
def get_genai_workbench_settings() -> GenAIWorkbenchSettingsResponse:
    return workbench_settings()


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


@router.get(
    "/ticket-classification/summary",
    response_model=GenAITicketClassificationSummaryResponse,
)
def get_ticket_classification_summary(
    db: DbSession,
    project_id: UUID,
    analysis_month: str = "2026-05",
    analysis_month_to: str | None = None,
) -> GenAITicketClassificationSummaryResponse:
    try:
        return ticket_classification_summary(db, project_id, analysis_month, analysis_month_to)
    except TicketClassificationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get(
    "/ticket-classification/pivot",
    response_model=GenAITicketClassificationPivotResponse,
)
def get_ticket_classification_pivot(
    db: DbSession,
    project_id: UUID,
    analysis_month: str = "2026-05",
    analysis_month_to: str | None = None,
) -> GenAITicketClassificationPivotResponse:
    try:
        return ticket_classification_pivot(db, project_id, analysis_month, analysis_month_to)
    except TicketClassificationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/ticket-classification/ticket-dump")
def download_ticket_classification_dump(
    db: DbSession,
    project_id: UUID,
    analysis_month: str = "2026-05",
    analysis_month_to: str | None = None,
) -> Response:
    try:
        csv_text = ticket_classification_dump_csv(
            db,
            project_id,
            analysis_month,
            analysis_month_to,
        )
    except TicketClassificationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    filename = (
        "genai_ticket_classification_dump_"
        f"{analysis_range_slug(analysis_month, analysis_month_to or analysis_month)}.xlsx"
    )
    return Response(
        content=csv_text_to_xlsx_bytes(csv_text, "Ticket Classification"),
        media_type=XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get(
    "/ticket-classification/usage-runs",
    response_model=GenAITicketClassificationUsageRunsResponse,
)
def get_ticket_classification_usage_runs(
    db: DbSession,
    project_id: UUID,
    analysis_month: str = "2026-05",
    analysis_month_to: str | None = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
) -> GenAITicketClassificationUsageRunsResponse:
    try:
        return ticket_classification_usage_runs(
            db,
            project_id,
            analysis_month,
            analysis_month_to=analysis_month_to,
            limit=limit,
        )
    except TicketClassificationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get(
    "/ticket-category-quality/usage-runs",
    response_model=GenAITicketClassificationUsageRunsResponse,
)
def get_ticket_category_quality_usage_runs(
    db: DbSession,
    project_id: UUID,
    analysis_month: str = "2026-05",
    analysis_month_to: str | None = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
) -> GenAITicketClassificationUsageRunsResponse:
    try:
        return ticket_category_quality_usage_runs(
            db,
            project_id,
            analysis_month,
            analysis_month_to=analysis_month_to,
            limit=limit,
        )
    except TicketClassificationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get(
    "/ticket-automation-analysis/results",
    response_model=GenAITicketAutomationResultsResponse,
)
def get_ticket_automation_analysis_results(
    db: DbSession,
    project_id: UUID,
    analysis_month: str = "2026-05",
    analysis_month_to: str | None = None,
) -> GenAITicketAutomationResultsResponse:
    try:
        return automation_results(db, project_id, analysis_month, analysis_month_to)
    except (TicketClassificationError, TicketAutomationAnalysisError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/ticket-automation-analysis/download")
def download_ticket_automation_analysis(
    db: DbSession,
    project_id: UUID,
    analysis_month: str = "2026-05",
    analysis_month_to: str | None = None,
) -> Response:
    try:
        csv_text = automation_analysis_csv(db, project_id, analysis_month, analysis_month_to)
        start_month, end_month = analysis_month, analysis_month_to or analysis_month
        filename = (
            "genai_ticket_automation_analysis_"
            f"{analysis_range_slug(start_month, end_month)}.xlsx"
        )
        return Response(
            content=csv_text_to_xlsx_bytes(csv_text, "Automation Analysis"),
            media_type=XLSX_MEDIA_TYPE,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except (TicketClassificationError, TicketAutomationAnalysisError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get(
    "/ticket-automation-analysis/usage-runs",
    response_model=GenAITicketClassificationUsageRunsResponse,
)
def get_ticket_automation_analysis_usage_runs(
    db: DbSession,
    project_id: UUID,
    analysis_month: str = "2026-05",
    analysis_month_to: str | None = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
) -> GenAITicketClassificationUsageRunsResponse:
    try:
        return automation_usage_runs(
            db,
            project_id,
            analysis_month,
            analysis_month_to=analysis_month_to,
            limit=limit,
        )
    except (TicketClassificationError, TicketAutomationAnalysisError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post(
    "/ticket-automation-analysis/run",
    response_model=GenAITicketAutomationRunResponse,
)
def post_ticket_automation_analysis_run(
    request: GenAITicketAutomationRunRequest,
    db: DbSession,
) -> GenAITicketAutomationRunResponse:
    try:
        return run_ticket_automation_analysis(
            db,
            ServiceTicketAutomationAnalysisRunRequest(
                project_id=request.project_id,
                analysis_month=request.analysis_month,
                analysis_month_to=request.analysis_month_to,
                force_reprocess=request.force_reprocess,
                cluster_limit=request.cluster_limit,
                run_id=request.run_id,
            ),
        )
    except (TicketClassificationError, TicketAutomationAnalysisError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post(
    "/ticket-automation-analysis/clear",
    response_model=GenAITicketAutomationClearResponse,
)
def post_ticket_automation_analysis_clear(
    request: GenAITicketAutomationClearRequest,
    db: DbSession,
) -> GenAITicketAutomationClearResponse:
    try:
        return clear_ticket_automation_analysis(
            db,
            ServiceTicketAutomationAnalysisClearRequest(
                project_id=request.project_id,
                analysis_month=request.analysis_month,
                analysis_month_to=request.analysis_month_to,
            ),
        )
    except (TicketClassificationError, TicketAutomationAnalysisError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post(
    "/ticket-classification/run",
    response_model=GenAITicketClassificationRunResponse,
)
def post_ticket_classification_run(
    request: GenAITicketClassificationRunRequest,
    db: DbSession,
) -> GenAITicketClassificationRunResponse:
    try:
        return run_ticket_classification(
            db,
            ServiceTicketClassificationRunRequest(
                project_id=request.project_id,
                analysis_month=request.analysis_month,
                force_reprocess=request.force_reprocess,
                batch_size=request.batch_size,
                batch_limit=request.batch_limit,
                run_id=request.run_id,
            ),
        )
    except TicketClassificationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post(
    "/ticket-category-quality/run",
    response_model=GenAITicketCategoryQualityRunResponse,
)
def post_ticket_category_quality_run(
    request: GenAITicketCategoryQualityRunRequest,
    db: DbSession,
) -> GenAITicketCategoryQualityRunResponse:
    try:
        return run_ticket_category_quality_analysis(
            db,
            ServiceTicketCategoryQualityRunRequest(
                project_id=request.project_id,
                analysis_month=request.analysis_month,
                analysis_month_to=request.analysis_month_to,
                force_reprocess=request.force_reprocess,
                batch_size=request.batch_size,
                batch_limit=request.batch_limit,
                run_id=request.run_id,
            ),
        )
    except TicketClassificationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post(
    "/ticket-classification/clear",
    response_model=GenAITicketClassificationClearResponse,
)
def post_ticket_classification_clear(
    request: GenAITicketClassificationClearRequest,
    db: DbSession,
) -> GenAITicketClassificationClearResponse:
    try:
        return clear_ticket_classification(
            db,
            ServiceTicketClassificationClearRequest(
                project_id=request.project_id,
                analysis_month=request.analysis_month,
                analysis_month_to=request.analysis_month_to,
            ),
        )
    except TicketClassificationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get(
    "/ticket-cluster-analysis/usage-runs",
    response_model=GenAITicketClassificationUsageRunsResponse,
)
def get_ticket_cluster_analysis_usage_runs(
    db: DbSession,
    project_id: UUID,
    analysis_month: str = "2026-05",
    analysis_month_to: str | None = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
) -> GenAITicketClassificationUsageRunsResponse:
    try:
        return ticket_cluster_usage_runs(
            db,
            project_id,
            analysis_month,
            analysis_month_to=analysis_month_to,
            limit=limit,
        )
    except (TicketClassificationError, TicketClusteringError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post(
    "/ticket-cluster-analysis/run",
    response_model=GenAITicketClusterRunResponse,
)
def post_ticket_cluster_analysis_run(
    request: GenAITicketClusterRunRequest,
    db: DbSession,
) -> GenAITicketClusterRunResponse:
    try:
        return run_ticket_cluster_analysis(
            db,
            ServiceTicketClusterRunRequest(
                project_id=request.project_id,
                analysis_month=request.analysis_month,
                analysis_month_to=request.analysis_month_to,
                force_reprocess=request.force_reprocess,
                level_1_count=request.level_1_count,
                level_2_count=request.level_2_count,
                level_3_count=request.level_3_count,
                use_llm_labels=request.use_llm_labels,
                run_id=request.run_id,
            ),
        )
    except (TicketClassificationError, TicketClusteringError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post(
    "/ticket-cluster-analysis/clear",
    response_model=GenAITicketClusterClearResponse,
)
def post_ticket_cluster_analysis_clear(
    request: GenAITicketClusterClearRequest,
    db: DbSession,
) -> GenAITicketClusterClearResponse:
    try:
        return clear_ticket_cluster_analysis(
            db,
            ServiceTicketClusterClearRequest(
                project_id=request.project_id,
                analysis_month=request.analysis_month,
                analysis_month_to=request.analysis_month_to,
            ),
        )
    except (TicketClassificationError, TicketClusteringError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post(
    "/ticket-embeddings/clear",
    response_model=GenAITicketEmbeddingClearResponse,
)
def post_ticket_embeddings_clear(
    request: GenAITicketEmbeddingClearRequest,
    db: DbSession,
) -> GenAITicketEmbeddingClearResponse:
    try:
        return clear_project_ticket_embeddings(
            db,
            ServiceTicketEmbeddingClearRequest(project_id=request.project_id),
        )
    except TicketClusteringError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


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
