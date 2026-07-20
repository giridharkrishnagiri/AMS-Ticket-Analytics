import json
import os
import shutil
import uuid
from pathlib import Path
from typing import Annotated, Any

from agents import Agent, Runner, set_tracing_disabled, trace
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import DataPoint, Deliverable, StakeholderQuestion, Subtask, Task
from app.models.mvp5_findings import AnalysisOutput, EvidenceItem, Finding
from app.models.mvp7_files import UploadedFile
from app.models.mvp8_llm import DeliverableReview, LlmRecommendation
from app.schemas.mvp6_refinement import TextRefinementRequest, TextRefinementResponse
from app.schemas.mvp7_files import UploadedFileRead
from app.schemas.mvp8_llm import (
    DeliverableReviewGenerateRequest,
    DeliverableReviewRead,
    LlmRecommendationGenerateRequest,
    LlmRecommendationRead,
)

router = APIRouter(prefix="/api", tags=["MVP 6 Refinement, MVP 7 Files, MVP 8 LLM"])

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = Path(__file__).resolve().parents[2]
UPLOAD_DIR = PROJECT_ROOT / "data" / "uploads"

load_dotenv(BACKEND_ROOT / ".env", override=False)

settings = get_settings()

LLM_MODEL = os.getenv("OPENAI_MODEL") or os.getenv("LLM_MODEL") or settings.required_openai_model

OPENAI_TRACING_ENABLED = str(settings.openai_tracing).strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}

set_tracing_disabled(disabled=not OPENAI_TRACING_ENABLED)


def normalize_spacing(text: str) -> str:
    lines = [line.strip() for line in text.strip().splitlines()]
    lines = [line for line in lines if line]
    return "\n".join(lines)


def sentence_case(text: str) -> str:
    cleaned = normalize_spacing(text)
    if not cleaned:
        return cleaned

    if cleaned.endswith((".", "!", "?")):
        return cleaned

    return f"{cleaned}."


def refine_finding_text(raw_text: str) -> str:
    cleaned = sentence_case(raw_text)

    return (
        "Finding:\n"
        f"{cleaned}\n\n"
        "Business impact:\n"
        "This may affect the accuracy, completeness, or reliability of the consulting assessment if not validated.\n\n"
        "Recommendation:\n"
        "Validate the underlying source, confirm ownership and assumptions, and document the evidence before using this item in final deliverables.\n\n"
        "Confidence:\n"
        "Medium, pending source validation and stakeholder confirmation."
    )


def refine_analysis_text(raw_text: str) -> str:
    cleaned = sentence_case(raw_text)

    return (
        "Analysis summary:\n"
        f"{cleaned}\n\n"
        "Methodology:\n"
        "Review available data points, compare them against stakeholder inputs, identify patterns or gaps, and document assumptions.\n\n"
        "Assumptions:\n"
        "The available data reflects the current operational context unless further exceptions are identified.\n\n"
        "Limitations:\n"
        "This analysis should be treated as preliminary until supporting evidence and stakeholder confirmation are complete.\n\n"
        "Next step:\n"
        "Link relevant data points, stakeholder responses, and evidence items to support the analysis output."
    )


def refine_general_text(raw_text: str) -> str:
    cleaned = sentence_case(raw_text)

    return (
        "Refined note:\n"
        f"{cleaned}\n\n"
        "Suggested next step:\n"
        "Review, validate, and link this note to the appropriate consulting work item."
    )


def refine_text(payload: TextRefinementRequest) -> str:
    raw_text = payload.raw_text.strip()

    if not raw_text:
        raise HTTPException(status_code=400, detail="raw_text cannot be empty")

    refinement_type = payload.refinement_type.strip().lower()

    if refinement_type == "finding":
        return refine_finding_text(raw_text)

    if refinement_type == "analysis":
        return refine_analysis_text(raw_text)

    return refine_general_text(raw_text)


def ensure_upload_dir() -> None:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def validate_optional_reference(db: Session, model: Any, item_id: uuid.UUID | None, label: str) -> None:
    if item_id is None:
        return

    if db.get(model, item_id) is None:
        raise HTTPException(status_code=404, detail=f"{label} not found")


def safe_filename(filename: str) -> str:
    cleaned = filename.replace("\\", "_").replace("/", "_").strip()
    if not cleaned:
        return "uploaded_file"
    return cleaned


def truncate_text(value: str | None, max_length: int = 6000) -> str:
    if not value:
        return ""

    cleaned = normalize_spacing(value)
    if len(cleaned) <= max_length:
        return cleaned

    return cleaned[:max_length] + "\n...[truncated]"


def json_or_empty(raw_output: str) -> dict[str, Any]:
    cleaned = raw_output.strip()

    if cleaned.startswith("```json"):
        cleaned = cleaned.removeprefix("```json").strip()

    if cleaned.startswith("```"):
        cleaned = cleaned.removeprefix("```").strip()

    if cleaned.endswith("```"):
        cleaned = cleaned.removesuffix("```").strip()

    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            return parsed
        return {}
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start >= 0 and end > start:
            try:
                parsed = json.loads(cleaned[start : end + 1])
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                return {}

    return {}


def get_required_item(db: Session, model: Any, item_id: uuid.UUID, label: str) -> Any:
    item = db.get(model, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"{label} not found")
    return item


def build_recommendation_context(db: Session, payload: LlmRecommendationGenerateRequest) -> str:
    sections: list[str] = []

    if payload.deliverable_id is not None:
        deliverable = get_required_item(db, Deliverable, payload.deliverable_id, "Deliverable")
        sections.append(
            "DELIVERABLE CONTEXT\n"
            f"Name: {deliverable.name}\n"
            f"External ID: {deliverable.external_id or '-'}\n"
            f"Status: {deliverable.status}\n"
            f"Description: {truncate_text(deliverable.description)}\n"
        )

    if payload.task_id is not None:
        task = get_required_item(db, Task, payload.task_id, "Task")
        sections.append(
            "TASK CONTEXT\n"
            f"Title: {task.title}\n"
            f"External ID: {task.external_id or '-'}\n"
            f"Status: {task.status}\n"
            f"Description: {truncate_text(task.description)}\n"
        )

    if payload.subtask_id is not None:
        subtask = get_required_item(db, Subtask, payload.subtask_id, "Sub-task")
        sections.append(
            "SUB-TASK CONTEXT\n"
            f"Title: {subtask.title}\n"
            f"External ID: {subtask.external_id or '-'}\n"
            f"Status: {subtask.status}\n"
            f"Description: {truncate_text(subtask.description)}\n"
            f"Completion Criteria: {truncate_text(subtask.completion_criteria)}\n"
        )

    if payload.finding_id is not None:
        finding = get_required_item(db, Finding, payload.finding_id, "Finding")
        sections.append(
            "FINDING CONTEXT\n"
            f"Title: {finding.title}\n"
            f"Type: {finding.finding_type or '-'}\n"
            f"Severity: {finding.severity or '-'}\n"
            f"Finding Text: {truncate_text(finding.finding_text)}\n"
            f"Business Impact: {truncate_text(finding.business_impact)}\n"
            f"Recommendation: {truncate_text(finding.recommendation)}\n"
        )

    if payload.analysis_output_id is not None:
        analysis = get_required_item(db, AnalysisOutput, payload.analysis_output_id, "Analysis output")
        sections.append(
            "ANALYSIS CONTEXT\n"
            f"Title: {analysis.analysis_title}\n"
            f"Type: {analysis.analysis_type or '-'}\n"
            f"Analysis Text: {truncate_text(analysis.analysis_text)}\n"
            f"Methodology: {truncate_text(analysis.methodology)}\n"
            f"Assumptions: {truncate_text(analysis.assumptions)}\n"
            f"Limitations: {truncate_text(analysis.limitations)}\n"
        )

    if not sections:
        sections.append(
            "GENERAL ASM ENGAGEMENT CONTEXT\n"
            "No specific work item was selected. Generate a general ASM consulting recommendation "
            "based on common application support and maintenance assessment needs."
        )

    return "\n\n".join(sections)


def build_deliverable_review_context(db: Session, deliverable_id: uuid.UUID) -> str:
    deliverable = get_required_item(db, Deliverable, deliverable_id, "Deliverable")

    tasks = list(db.scalars(select(Task).where(Task.deliverable_id == deliverable_id)).all())

    findings = list(
        db.scalars(
            select(Finding)
            .where(Finding.deliverable_id == deliverable_id)
            .order_by(Finding.created_at.desc())
        ).all()
    )

    analysis_outputs = list(
        db.scalars(
            select(AnalysisOutput)
            .where(AnalysisOutput.deliverable_id == deliverable_id)
            .order_by(AnalysisOutput.created_at.desc())
        ).all()
    )

    recommendations = list(
        db.scalars(
            select(LlmRecommendation)
            .where(LlmRecommendation.deliverable_id == deliverable_id)
            .order_by(LlmRecommendation.created_at.desc())
        ).all()
    )

    sections: list[str] = [
        "DELIVERABLE\n"
        f"Name: {deliverable.name}\n"
        f"External ID: {deliverable.external_id or '-'}\n"
        f"Type: {deliverable.deliverable_type or '-'}\n"
        f"Status: {deliverable.status}\n"
        f"Review Status: {deliverable.review_status or '-'}\n"
        f"Progress: {deliverable.progress_percent}%\n"
        f"Description: {truncate_text(deliverable.description)}\n"
    ]

    if tasks:
        task_lines = []
        for task in tasks[:20]:
            task_lines.append(
                f"- {task.external_id or '-'} | {task.title} | Status: {task.status} | "
                f"Priority: {task.priority or '-'} | Progress: {task.progress_percent}%"
            )
        sections.append("TASKS\n" + "\n".join(task_lines))

    if findings:
        finding_lines = []
        for finding in findings[:20]:
            finding_lines.append(
                f"- {finding.title} | Severity: {finding.severity or '-'} | "
                f"Text: {truncate_text(finding.finding_text, 800)}"
            )
        sections.append("FINDINGS\n" + "\n".join(finding_lines))

    if analysis_outputs:
        analysis_lines = []
        for analysis in analysis_outputs[:20]:
            analysis_lines.append(
                f"- {analysis.analysis_title} | Type: {analysis.analysis_type or '-'} | "
                f"Text: {truncate_text(analysis.analysis_text, 800)}"
            )
        sections.append("ANALYSIS OUTPUTS\n" + "\n".join(analysis_lines))

    if recommendations:
        recommendation_lines = []
        for recommendation in recommendations[:20]:
            recommendation_lines.append(
                f"- {recommendation.title} | Priority: {recommendation.priority or '-'} | "
                f"Recommendation: {truncate_text(recommendation.recommendation_text, 800)}"
            )
        sections.append("LLM RECOMMENDATIONS\n" + "\n".join(recommendation_lines))

    return "\n\n".join(sections)


async def run_traced_agent(workflow_name: str, agent_name: str, instructions: str, user_input: str) -> str:
    if not os.getenv("OPENAI_API_KEY"):
        raise HTTPException(
            status_code=500,
            detail=(
                "OPENAI_API_KEY is not set. Add OPENAI_API_KEY to backend/.env "
                "before generating LLM recommendations."
            ),
        )

    agent = Agent(
        name=agent_name,
        instructions=instructions,
        model=LLM_MODEL,
    )

    with trace(
        workflow_name=workflow_name,
        metadata={
            "project": "ASM Engagement Cockpit",
            "mvp": "MVP 8",
            "model": LLM_MODEL,
            "openai_tracing_enabled": str(OPENAI_TRACING_ENABLED),
        },
    ):
        result = await Runner.run(agent, user_input)

    return str(result.final_output)


@router.post("/refine-text", response_model=TextRefinementResponse)
def refine_text_endpoint(payload: TextRefinementRequest) -> TextRefinementResponse:
    refined_text = refine_text(payload)

    return TextRefinementResponse(
        raw_text=payload.raw_text,
        refined_text=refined_text,
        refinement_type=payload.refinement_type,
        tone=payload.tone,
        output_format=payload.output_format,
    )


@router.post("/uploaded-files", response_model=UploadedFileRead)
def upload_file(
    db: Annotated[Session, Depends(get_db)],
    file: UploadFile = File(...),
    description: str | None = Form(default=None),
    upload_category: str | None = Form(default=None),
    subtask_id: uuid.UUID | None = Form(default=None),
    data_point_id: uuid.UUID | None = Form(default=None),
    stakeholder_question_id: uuid.UUID | None = Form(default=None),
    finding_id: uuid.UUID | None = Form(default=None),
    analysis_output_id: uuid.UUID | None = Form(default=None),
    evidence_item_id: uuid.UUID | None = Form(default=None),
    uploaded_by: str | None = Form(default=None),
) -> UploadedFile:
    validate_optional_reference(db, Subtask, subtask_id, "Sub-task")
    validate_optional_reference(db, DataPoint, data_point_id, "Data point")
    validate_optional_reference(db, StakeholderQuestion, stakeholder_question_id, "Stakeholder question")
    validate_optional_reference(db, Finding, finding_id, "Finding")
    validate_optional_reference(db, AnalysisOutput, analysis_output_id, "Analysis output")
    validate_optional_reference(db, EvidenceItem, evidence_item_id, "Evidence item")

    ensure_upload_dir()

    original_filename = safe_filename(file.filename or "uploaded_file")
    stored_filename = f"{uuid.uuid4()}_{original_filename}"
    storage_path = UPLOAD_DIR / stored_filename

    with storage_path.open("wb") as destination:
        shutil.copyfileobj(file.file, destination)

    file_size_bytes = storage_path.stat().st_size

    uploaded_file = UploadedFile(
        original_filename=original_filename,
        stored_filename=stored_filename,
        storage_path=str(storage_path),
        content_type=file.content_type,
        file_size_bytes=file_size_bytes,
        description=description,
        upload_category=upload_category,
        subtask_id=subtask_id,
        data_point_id=data_point_id,
        stakeholder_question_id=stakeholder_question_id,
        finding_id=finding_id,
        analysis_output_id=analysis_output_id,
        evidence_item_id=evidence_item_id,
        uploaded_by=uploaded_by,
    )

    db.add(uploaded_file)
    db.commit()
    db.refresh(uploaded_file)

    return uploaded_file


@router.get("/uploaded-files", response_model=list[UploadedFileRead])
def list_uploaded_files(
    db: Annotated[Session, Depends(get_db)],
    subtask_id: uuid.UUID | None = Query(default=None),
    data_point_id: uuid.UUID | None = Query(default=None),
    stakeholder_question_id: uuid.UUID | None = Query(default=None),
    finding_id: uuid.UUID | None = Query(default=None),
    analysis_output_id: uuid.UUID | None = Query(default=None),
    evidence_item_id: uuid.UUID | None = Query(default=None),
) -> list[UploadedFile]:
    statement = select(UploadedFile).order_by(UploadedFile.created_at.desc())

    if subtask_id is not None:
        statement = statement.where(UploadedFile.subtask_id == subtask_id)

    if data_point_id is not None:
        statement = statement.where(UploadedFile.data_point_id == data_point_id)

    if stakeholder_question_id is not None:
        statement = statement.where(UploadedFile.stakeholder_question_id == stakeholder_question_id)

    if finding_id is not None:
        statement = statement.where(UploadedFile.finding_id == finding_id)

    if analysis_output_id is not None:
        statement = statement.where(UploadedFile.analysis_output_id == analysis_output_id)

    if evidence_item_id is not None:
        statement = statement.where(UploadedFile.evidence_item_id == evidence_item_id)

    return list(db.scalars(statement).all())


@router.get("/uploaded-files/{uploaded_file_id}", response_model=UploadedFileRead)
def get_uploaded_file(
    uploaded_file_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
) -> UploadedFile:
    uploaded_file = db.get(UploadedFile, uploaded_file_id)

    if uploaded_file is None:
        raise HTTPException(status_code=404, detail="Uploaded file not found")

    return uploaded_file


@router.get("/uploaded-files/{uploaded_file_id}/download")
def download_uploaded_file(
    uploaded_file_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
) -> FileResponse:
    uploaded_file = db.get(UploadedFile, uploaded_file_id)

    if uploaded_file is None:
        raise HTTPException(status_code=404, detail="Uploaded file not found")

    storage_path = Path(uploaded_file.storage_path)

    if not storage_path.exists():
        raise HTTPException(status_code=404, detail="Stored file is missing from disk")

    return FileResponse(
        path=storage_path,
        filename=uploaded_file.original_filename,
        media_type=uploaded_file.content_type or "application/octet-stream",
    )


@router.post("/llm-recommendations/generate", response_model=LlmRecommendationRead)
async def generate_llm_recommendation(
    payload: LlmRecommendationGenerateRequest,
    db: Annotated[Session, Depends(get_db)],
) -> LlmRecommendation:
    validate_optional_reference(db, Deliverable, payload.deliverable_id, "Deliverable")
    validate_optional_reference(db, Task, payload.task_id, "Task")
    validate_optional_reference(db, Subtask, payload.subtask_id, "Sub-task")
    validate_optional_reference(db, Finding, payload.finding_id, "Finding")
    validate_optional_reference(db, AnalysisOutput, payload.analysis_output_id, "Analysis output")

    source_context = build_recommendation_context(db, payload)
    workflow_name = "ASM MVP8 - Generate LLM Recommendation"

    instructions = (
        "You are an expert Application Support and Maintenance consulting advisor. "
        "Generate practical, executive-ready ASM recommendations. "
        "Return only valid JSON with these keys: "
        "title, category, priority, recommendation_text, rationale, expected_benefit, implementation_notes. "
        "Do not include markdown fences."
    )

    user_input = (
        f"Recommendation type: {payload.recommendation_type}\n"
        f"Focus area: {payload.focus_area}\n\n"
        f"Context:\n{source_context}\n\n"
        "Generate one high-quality recommendation that is specific to the context."
    )

    llm_output = await run_traced_agent(
        workflow_name=workflow_name,
        agent_name="ASM Recommendation Advisor",
        instructions=instructions,
        user_input=user_input,
    )

    parsed = json_or_empty(llm_output)

    recommendation = LlmRecommendation(
        recommendation_type=payload.recommendation_type,
        category=parsed.get("category") or "ASM Improvement",
        priority=parsed.get("priority") or "Medium",
        title=parsed.get("title") or "ASM improvement recommendation",
        recommendation_text=parsed.get("recommendation_text") or llm_output,
        rationale=parsed.get("rationale"),
        expected_benefit=parsed.get("expected_benefit"),
        implementation_notes=parsed.get("implementation_notes"),
        source_context=source_context,
        llm_raw_output=llm_output,
        status="Draft",
        model_name=LLM_MODEL,
        trace_workflow_name=workflow_name,
        deliverable_id=payload.deliverable_id,
        task_id=payload.task_id,
        subtask_id=payload.subtask_id,
        finding_id=payload.finding_id,
        analysis_output_id=payload.analysis_output_id,
        created_by=payload.created_by,
    )

    db.add(recommendation)
    db.commit()
    db.refresh(recommendation)

    return recommendation


@router.get("/llm-recommendations", response_model=list[LlmRecommendationRead])
def list_llm_recommendations(
    db: Annotated[Session, Depends(get_db)],
    deliverable_id: uuid.UUID | None = Query(default=None),
    task_id: uuid.UUID | None = Query(default=None),
    subtask_id: uuid.UUID | None = Query(default=None),
    finding_id: uuid.UUID | None = Query(default=None),
    analysis_output_id: uuid.UUID | None = Query(default=None),
) -> list[LlmRecommendation]:
    statement = select(LlmRecommendation).order_by(LlmRecommendation.created_at.desc())

    if deliverable_id is not None:
        statement = statement.where(LlmRecommendation.deliverable_id == deliverable_id)

    if task_id is not None:
        statement = statement.where(LlmRecommendation.task_id == task_id)

    if subtask_id is not None:
        statement = statement.where(LlmRecommendation.subtask_id == subtask_id)

    if finding_id is not None:
        statement = statement.where(LlmRecommendation.finding_id == finding_id)

    if analysis_output_id is not None:
        statement = statement.where(LlmRecommendation.analysis_output_id == analysis_output_id)

    return list(db.scalars(statement).all())


@router.post("/deliverable-reviews/generate", response_model=DeliverableReviewRead)
async def generate_deliverable_review(
    payload: DeliverableReviewGenerateRequest,
    db: Annotated[Session, Depends(get_db)],
) -> DeliverableReview:
    deliverable = get_required_item(db, Deliverable, payload.deliverable_id, "Deliverable")

    source_context = build_deliverable_review_context(db, payload.deliverable_id)
    workflow_name = "ASM MVP8 - Generate Deliverable Review"

    instructions = (
        "You are a senior ASM consulting quality reviewer. "
        "Review the deliverable context for completeness, consulting quality, risk, and readiness. "
        "Return only valid JSON with these keys: "
        "review_title, review_summary, strengths, gaps, risks, recommended_actions, readiness_assessment. "
        "Do not include markdown fences."
    )

    user_input = (
        f"Review type: {payload.review_type}\n\n"
        f"Context:\n{source_context}\n\n"
        "Generate a practical deliverable review that helps the consultant improve the deliverable."
    )

    llm_output = await run_traced_agent(
        workflow_name=workflow_name,
        agent_name="ASM Deliverable Reviewer",
        instructions=instructions,
        user_input=user_input,
    )

    parsed = json_or_empty(llm_output)

    review = DeliverableReview(
        deliverable_id=payload.deliverable_id,
        review_title=parsed.get("review_title") or f"LLM review for {deliverable.name}",
        review_type=payload.review_type,
        review_status="Draft",
        review_summary=parsed.get("review_summary") or llm_output,
        strengths=parsed.get("strengths"),
        gaps=parsed.get("gaps"),
        risks=parsed.get("risks"),
        recommended_actions=parsed.get("recommended_actions"),
        readiness_assessment=parsed.get("readiness_assessment"),
        source_context=source_context,
        llm_raw_output=llm_output,
        model_name=LLM_MODEL,
        trace_workflow_name=workflow_name,
        created_by=payload.created_by,
    )

    db.add(review)
    db.commit()
    db.refresh(review)

    return review


@router.get("/deliverable-reviews", response_model=list[DeliverableReviewRead])
def list_deliverable_reviews(
    db: Annotated[Session, Depends(get_db)],
    deliverable_id: uuid.UUID | None = Query(default=None),
) -> list[DeliverableReview]:
    statement = select(DeliverableReview).order_by(DeliverableReview.created_at.desc())

    if deliverable_id is not None:
        statement = statement.where(DeliverableReview.deliverable_id == deliverable_id)

    return list(db.scalars(statement).all())
