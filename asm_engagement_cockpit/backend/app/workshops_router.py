from __future__ import annotations

import json
import re
import uuid
import zipfile
from datetime import date, datetime
from decimal import Decimal
from io import BytesIO
from typing import Annotated, Any
from xml.etree import ElementTree

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.config import get_settings
from app.database import get_db
from app.models.workshops import LlmPromptTemplate, Workshop, WorkshopAction
from app.schemas.mvp18_workspace import DeleteResponse
from app.schemas.workshops import (
    LlmPromptTemplateRead,
    LlmPromptTemplateUpdate,
    PromptPreview,
    WorkshopActionCreate,
    WorkshopActionRead,
    WorkshopActionUpdate,
    WorkshopAnalysisUpdate,
    WorkshopListItem,
    WorkshopRead,
)
from app.security import require_authenticated_request

router = APIRouter(prefix="/api/ui", tags=["Workshops"])

WORKSHOP_ANALYSIS_PROMPT_KEY = "workshop_transcript_analysis"

DEFAULT_WORKSHOP_SYSTEM_PROMPT = (
    "You are an expert Application Support and Maintenance consulting facilitator. "
    "Analyze workshop transcripts for a consulting engagement. "
    "Extract concise meeting notes, key decisions, and action items. "
    "Do not invent facts. If an owner or due date is not stated, leave it blank. "
    "Return only valid JSON without markdown fences."
)

DEFAULT_WORKSHOP_USER_PROMPT = """Analyze this workshop transcript and return valid JSON with these keys:
{
  "meeting_notes": "Concise meeting notes as editable plain text.",
  "key_decisions": "Key decisions or agreements as editable plain text.",
  "actions": [
    {
      "action_text": "Action item text",
      "owner_name": "Owner if explicitly stated",
      "due_date": "YYYY-MM-DD if explicitly stated, otherwise null",
      "status": "Open",
      "notes": "Optional context"
    }
  ]
}

Workshop date: {{workshop_date}}
Workshop title: {{title}}
Functional track: {{functional_track}}
Duration hours: {{duration_hours}}
Participants:
{{participants_text}}

Agenda:
{{agenda}}

Transcript:
{{transcript_text}}
"""


def normalize_text(value: Any) -> str:
    return str(value or "").strip()


def ensure_default_prompt_templates(db: Session) -> None:
    existing = db.scalar(select(LlmPromptTemplate).where(LlmPromptTemplate.prompt_key == WORKSHOP_ANALYSIS_PROMPT_KEY))
    if existing is not None:
        return

    db.add(
        LlmPromptTemplate(
            prompt_key=WORKSHOP_ANALYSIS_PROMPT_KEY,
            name="Workshop Transcript Analysis",
            description="Extracts meeting notes, key decisions, and action items from a workshop transcript.",
            system_prompt=DEFAULT_WORKSHOP_SYSTEM_PROMPT,
            user_prompt_template=DEFAULT_WORKSHOP_USER_PROMPT,
            is_active=True,
        )
    )
    db.commit()


def get_prompt_template(db: Session, prompt_key: str = WORKSHOP_ANALYSIS_PROMPT_KEY) -> LlmPromptTemplate:
    ensure_default_prompt_templates(db)
    item = db.scalar(select(LlmPromptTemplate).where(LlmPromptTemplate.prompt_key == prompt_key))
    if item is None:
        raise HTTPException(status_code=404, detail="Prompt template not found")
    return item


def render_prompt(template: str, variables: dict[str, Any]) -> str:
    rendered = template
    for key, value in variables.items():
        rendered = rendered.replace(f"{{{{{key}}}}}", normalize_text(value))
    return rendered


def workshop_prompt_variables(workshop: Workshop) -> dict[str, Any]:
    return {
        "workshop_date": workshop.workshop_date.isoformat() if workshop.workshop_date else "",
        "title": workshop.title,
        "functional_track": workshop.functional_track,
        "duration_hours": workshop.duration_hours,
        "participants_text": workshop.participants_text,
        "agenda": workshop.agenda,
        "transcript_text": workshop.transcript_text,
    }


def build_prompt_preview(db: Session, workshop: Workshop) -> PromptPreview:
    template = get_prompt_template(db)
    return PromptPreview(
        prompt_key=template.prompt_key,
        system_prompt=template.system_prompt,
        user_prompt=render_prompt(template.user_prompt_template, workshop_prompt_variables(workshop)),
    )


def parse_vtt(raw_text: str) -> str:
    lines: list[str] = []
    for raw_line in raw_text.replace("\ufeff", "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.upper().startswith("WEBVTT"):
            continue
        if line.upper().startswith(("NOTE", "STYLE", "REGION")):
            continue
        if "-->" in line:
            continue
        if re.fullmatch(r"\d+", line):
            continue
        line = re.sub(r"<[^>]+>", "", line)
        if line:
            lines.append(line)
    return "\n".join(lines)


def parse_docx(raw_bytes: bytes) -> str:
    try:
        with zipfile.ZipFile(BytesIO(raw_bytes)) as archive:
            document_xml = archive.read("word/document.xml")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not read DOCX transcript: {type(exc).__name__}") from exc

    root = ElementTree.fromstring(document_xml)
    namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    paragraphs: list[str] = []

    for paragraph in root.findall(".//w:p", namespace):
        text_parts = [node.text or "" for node in paragraph.findall(".//w:t", namespace)]
        paragraph_text = "".join(text_parts).strip()
        if paragraph_text:
            paragraphs.append(paragraph_text)

    return "\n".join(paragraphs)


async def extract_transcript_text(file: UploadFile) -> str:
    raw_bytes = await file.read()
    filename = (file.filename or "").lower()

    if filename.endswith(".vtt"):
        return parse_vtt(raw_bytes.decode("utf-8-sig", errors="replace"))
    if filename.endswith(".docx"):
        return parse_docx(raw_bytes)
    if filename.endswith(".txt") or filename.endswith(".srt"):
        return raw_bytes.decode("utf-8-sig", errors="replace")

    raise HTTPException(status_code=400, detail="Transcript must be a .vtt, .docx, .txt, or .srt file.")


def parse_date(value: str | None) -> date:
    if not value:
        raise HTTPException(status_code=422, detail="workshop_date is required")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="workshop_date must be YYYY-MM-DD") from exc


def parse_decimal(value: str | None) -> Decimal | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        return Decimal(str(value))
    except Exception as exc:
        raise HTTPException(status_code=422, detail="duration_hours must be a number") from exc


def get_workshop_or_404(db: Session, workshop_id: uuid.UUID) -> Workshop:
    item = db.get(Workshop, workshop_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Workshop not found")
    return item


def get_action_or_404(db: Session, action_id: uuid.UUID) -> WorkshopAction:
    item = db.get(WorkshopAction, action_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Workshop action not found")
    return item


def action_count(db: Session, workshop_id: uuid.UUID) -> int:
    return int(
        db.scalar(
            select(func.count()).select_from(WorkshopAction).where(WorkshopAction.workshop_id == workshop_id)
        )
        or 0
    )


def workshop_list_item(db: Session, workshop: Workshop) -> WorkshopListItem:
    return WorkshopListItem(
        id=workshop.id,
        workshop_date=workshop.workshop_date,
        title=workshop.title,
        functional_track=workshop.functional_track,
        duration_hours=workshop.duration_hours,
        transcript_filename=workshop.transcript_filename,
        recording_path=workshop.recording_path,
        last_analyzed_at=workshop.last_analyzed_at,
        action_count=action_count(db, workshop.id),
    )


def extract_json_object(raw_text: str) -> dict[str, Any]:
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned, flags=re.IGNORECASE).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(cleaned[start : end + 1])
            except json.JSONDecodeError:
                return {}
    return {}


def run_workshop_llm(system_prompt: str, user_prompt: str) -> str:
    settings = get_settings()
    if not settings.openai_api_key:
        return json.dumps(
            {
                "meeting_notes": "LLM analysis was not run because OPENAI_API_KEY is not configured.",
                "key_decisions": "",
                "actions": [],
            }
        )

    try:
        from agents import Agent, Runner, trace

        agent = Agent(
            name="ASM Workshop Transcript Analyst",
            instructions=system_prompt,
            model=settings.openai_model,
        )

        with trace(workflow_name="ASM Engagement Cockpit - Analyze Workshop Transcript"):
            result = Runner.run_sync(agent, user_prompt)

        return str(result.final_output).strip()
    except Exception as exc:
        return json.dumps(
            {
                "meeting_notes": f"LLM analysis failed: {type(exc).__name__}: {exc}",
                "key_decisions": "",
                "actions": [],
            }
        )


def apply_action_payload(item: WorkshopAction, payload: WorkshopActionUpdate) -> None:
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(item, key, value)


@router.get("/llm-prompts", response_model=list[LlmPromptTemplateRead])
def list_llm_prompts(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[dict[str, Any], Depends(require_authenticated_request)],
) -> list[LlmPromptTemplate]:
    ensure_default_prompt_templates(db)
    return list(db.scalars(select(LlmPromptTemplate).order_by(LlmPromptTemplate.name.asc())).all())


@router.get("/llm-prompts/{prompt_key}", response_model=LlmPromptTemplateRead)
def get_llm_prompt(
    prompt_key: str,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[dict[str, Any], Depends(require_authenticated_request)],
) -> LlmPromptTemplate:
    return get_prompt_template(db, prompt_key)


@router.put("/llm-prompts/{prompt_key}", response_model=LlmPromptTemplateRead)
def update_llm_prompt(
    prompt_key: str,
    payload: LlmPromptTemplateUpdate,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[dict[str, Any], Depends(require_authenticated_request)],
) -> LlmPromptTemplate:
    item = get_prompt_template(db, prompt_key)
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(item, key, value)
    db.commit()
    db.refresh(item)
    return item


@router.get("/workshops", response_model=list[WorkshopListItem])
def list_workshops(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[dict[str, Any], Depends(require_authenticated_request)],
) -> list[WorkshopListItem]:
    rows = list(db.scalars(select(Workshop).order_by(Workshop.workshop_date.desc(), Workshop.created_at.desc())).all())
    return [workshop_list_item(db, item) for item in rows]


@router.post("/workshops", response_model=WorkshopRead)
async def create_workshop(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[dict[str, Any], Depends(require_authenticated_request)],
    workshop_date: str = Form(...),
    title: str = Form(...),
    functional_track: str | None = Form(default=None),
    participants_text: str | None = Form(default=None),
    agenda: str | None = Form(default=None),
    duration_hours: str | None = Form(default=None),
    recording_path: str | None = Form(default=None),
    created_by: str | None = Form(default=None),
    transcript_file: UploadFile | None = File(default=None),
) -> Workshop:
    item = Workshop(
        workshop_date=parse_date(workshop_date),
        title=title.strip(),
        functional_track=normalize_text(functional_track) or None,
        participants_text=normalize_text(participants_text) or None,
        agenda=normalize_text(agenda) or None,
        duration_hours=parse_decimal(duration_hours),
        recording_path=normalize_text(recording_path) or None,
        created_by=normalize_text(created_by) or None,
        updated_by=normalize_text(created_by) or None,
    )

    if transcript_file is not None and transcript_file.filename:
        item.transcript_filename = transcript_file.filename
        item.transcript_content_type = transcript_file.content_type
        item.transcript_text = await extract_transcript_text(transcript_file)
        item.transcript_uploaded_at = datetime.utcnow()

    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.get("/workshops/{workshop_id}", response_model=WorkshopRead)
def get_workshop(
    workshop_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[dict[str, Any], Depends(require_authenticated_request)],
) -> Workshop:
    item = db.scalar(select(Workshop).options(selectinload(Workshop.actions)).where(Workshop.id == workshop_id))
    if item is None:
        raise HTTPException(status_code=404, detail="Workshop not found")
    return item


@router.put("/workshops/{workshop_id}", response_model=WorkshopRead)
async def update_workshop(
    workshop_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[dict[str, Any], Depends(require_authenticated_request)],
    workshop_date: str = Form(...),
    title: str = Form(...),
    functional_track: str | None = Form(default=None),
    participants_text: str | None = Form(default=None),
    agenda: str | None = Form(default=None),
    duration_hours: str | None = Form(default=None),
    recording_path: str | None = Form(default=None),
    updated_by: str | None = Form(default=None),
    transcript_file: UploadFile | None = File(default=None),
) -> Workshop:
    item = get_workshop_or_404(db, workshop_id)
    item.workshop_date = parse_date(workshop_date)
    item.title = title.strip()
    item.functional_track = normalize_text(functional_track) or None
    item.participants_text = normalize_text(participants_text) or None
    item.agenda = normalize_text(agenda) or None
    item.duration_hours = parse_decimal(duration_hours)
    item.recording_path = normalize_text(recording_path) or None
    item.updated_by = normalize_text(updated_by) or None

    if transcript_file is not None and transcript_file.filename:
        item.transcript_filename = transcript_file.filename
        item.transcript_content_type = transcript_file.content_type
        item.transcript_text = await extract_transcript_text(transcript_file)
        item.transcript_uploaded_at = datetime.utcnow()

    db.commit()
    db.refresh(item)
    return item


@router.delete("/workshops/{workshop_id}", response_model=DeleteResponse)
def delete_workshop(
    workshop_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[dict[str, Any], Depends(require_authenticated_request)],
) -> DeleteResponse:
    item = get_workshop_or_404(db, workshop_id)
    db.delete(item)
    db.commit()
    return DeleteResponse(deleted=True, entity_type="workshop", entity_id=workshop_id, message="Workshop was deleted.")


@router.get("/workshops/{workshop_id}/prompt-preview", response_model=PromptPreview)
def get_workshop_prompt_preview(
    workshop_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[dict[str, Any], Depends(require_authenticated_request)],
) -> PromptPreview:
    return build_prompt_preview(db, get_workshop_or_404(db, workshop_id))


@router.post("/workshops/{workshop_id}/analyze", response_model=WorkshopRead)
def analyze_workshop(
    workshop_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[dict[str, Any], Depends(require_authenticated_request)],
) -> Workshop:
    item = get_workshop_or_404(db, workshop_id)
    if not normalize_text(item.transcript_text):
        raise HTTPException(status_code=400, detail="Upload a transcript before analyzing the workshop.")

    prompt_preview = build_prompt_preview(db, item)
    output = run_workshop_llm(prompt_preview.system_prompt, prompt_preview.user_prompt)
    parsed = extract_json_object(output)

    item.meeting_notes = normalize_text(parsed.get("meeting_notes")) or output
    item.key_decisions = normalize_text(parsed.get("key_decisions")) or None
    item.llm_raw_output = output
    item.last_system_prompt = prompt_preview.system_prompt
    item.last_user_prompt = prompt_preview.user_prompt
    item.last_analyzed_at = datetime.utcnow()

    existing_actions = list(db.scalars(select(WorkshopAction).where(WorkshopAction.workshop_id == item.id)).all())
    for action in existing_actions:
        db.delete(action)

    for index, action_data in enumerate(parsed.get("actions") or []):
        if not isinstance(action_data, dict):
            continue
        action_text = normalize_text(action_data.get("action_text"))
        if not action_text:
            continue
        due_date_value = normalize_text(action_data.get("due_date")) or None
        due_date = None
        if due_date_value:
            try:
                due_date = date.fromisoformat(due_date_value)
            except ValueError:
                due_date = None
        db.add(
            WorkshopAction(
                workshop_id=item.id,
                action_text=action_text,
                owner_name=normalize_text(action_data.get("owner_name")) or None,
                due_date=due_date,
                status=normalize_text(action_data.get("status")) or "Open",
                notes=normalize_text(action_data.get("notes")) or None,
                order_index=index,
            )
        )

    db.commit()
    db.refresh(item)
    return get_workshop(item.id, db, {"username": "system"})


@router.put("/workshops/{workshop_id}/analysis", response_model=WorkshopRead)
def update_workshop_analysis(
    workshop_id: uuid.UUID,
    payload: WorkshopAnalysisUpdate,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[dict[str, Any], Depends(require_authenticated_request)],
) -> Workshop:
    item = get_workshop_or_404(db, workshop_id)
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(item, key, value)
    db.commit()
    db.refresh(item)
    return get_workshop(item.id, db, {"username": "system"})


@router.post("/workshops/{workshop_id}/actions", response_model=WorkshopActionRead)
def create_workshop_action(
    workshop_id: uuid.UUID,
    payload: WorkshopActionCreate,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[dict[str, Any], Depends(require_authenticated_request)],
) -> WorkshopAction:
    get_workshop_or_404(db, workshop_id)
    item = WorkshopAction(workshop_id=workshop_id, **payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.put("/workshops/actions/{action_id}", response_model=WorkshopActionRead)
def update_workshop_action(
    action_id: uuid.UUID,
    payload: WorkshopActionUpdate,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[dict[str, Any], Depends(require_authenticated_request)],
) -> WorkshopAction:
    item = get_action_or_404(db, action_id)
    apply_action_payload(item, payload)
    db.commit()
    db.refresh(item)
    return item


@router.delete("/workshops/actions/{action_id}", response_model=DeleteResponse)
def delete_workshop_action(
    action_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[dict[str, Any], Depends(require_authenticated_request)],
) -> DeleteResponse:
    item = get_action_or_404(db, action_id)
    workshop_id = item.workshop_id
    db.delete(item)
    db.commit()
    return DeleteResponse(deleted=True, entity_type="workshop_action", entity_id=action_id, message=f"Workshop action for {workshop_id} was deleted.")
