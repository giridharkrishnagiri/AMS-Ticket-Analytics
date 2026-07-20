import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any

from agents import Agent, Runner, set_tracing_disabled, trace
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import Deliverable, Subtask, Task, Workstream
from app.models.mvp10_timesheets import TimesheetEntry, TimesheetSummary
from app.schemas.mvp10_timesheets import (
    TimesheetEntryCreate,
    TimesheetEntryRead,
    TimesheetEntryUpdate,
    TimesheetSummaryGenerateRequest,
    TimesheetSummaryRead,
    TimesheetWeekSubmitRequest,
    TimesheetWeekSubmitResponse,
)

router = APIRouter(prefix="/api", tags=["MVP 10 Timesheets"])

BACKEND_ROOT = Path(__file__).resolve().parents[1]
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


def validate_optional_reference(db: Session, model: Any, item_id: uuid.UUID | None, label: str) -> None:
    if item_id is None:
        return

    if db.get(model, item_id) is None:
        raise HTTPException(status_code=404, detail=f"{label} not found")


def normalize_spacing(text: str | None) -> str:
    if not text:
        return ""

    lines = [line.strip() for line in text.strip().splitlines()]
    lines = [line for line in lines if line]
    return "\n".join(lines)


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


def update_model_from_payload(model: Any, payload: Any) -> None:
    data = payload.model_dump(exclude_unset=True)

    for field_name, value in data.items():
        setattr(model, field_name, value)


def get_entry_context_label(db: Session, entry: TimesheetEntry) -> str:
    labels: list[str] = []

    if entry.workstream_id:
        workstream = db.get(Workstream, entry.workstream_id)
        if workstream:
            labels.append(f"Workstream: {workstream.external_id or '-'} {workstream.name}")

    if entry.deliverable_id:
        deliverable = db.get(Deliverable, entry.deliverable_id)
        if deliverable:
            labels.append(f"Deliverable: {deliverable.external_id or '-'} {deliverable.name}")

    if entry.task_id:
        task = db.get(Task, entry.task_id)
        if task:
            labels.append(f"Task: {task.external_id or '-'} {task.title}")

    if entry.subtask_id:
        subtask = db.get(Subtask, entry.subtask_id)
        if subtask:
            labels.append(f"Sub-task: {subtask.external_id or '-'} {subtask.title}")

    if not labels:
        return "No linked work item"

    return " | ".join(labels)


def build_timesheet_summary_context(db: Session, entries: list[TimesheetEntry]) -> str:
    if not entries:
        return "No timesheet entries were found for the selected date range."

    lines: list[str] = []

    for entry in entries:
        linked_context = get_entry_context_label(db, entry)

        lines.append(
            "TIMESHEET ENTRY\n"
            f"Date: {entry.entry_date}\n"
            f"Person: {entry.person_name}\n"
            f"Linked Context: {linked_context}\n"
            f"Activity Type: {entry.activity_type}\n"
            f"Effort Hours: {entry.effort_hours}\n"
            f"Status: {entry.status}\n"
            f"Submitted: {entry.submitted}\n"
            f"Accomplishments: {normalize_spacing(entry.accomplishments)}\n"
            f"Blockers: {normalize_spacing(entry.blockers)}\n"
            f"Next Steps: {normalize_spacing(entry.next_steps)}\n"
        )

    return "\n\n".join(lines)


async def run_traced_timesheet_summary_agent(source_context: str, payload: TimesheetSummaryGenerateRequest) -> str:
    if not os.getenv("OPENAI_API_KEY"):
        raise HTTPException(
            status_code=500,
            detail=(
                "OPENAI_API_KEY is not set. Add OPENAI_API_KEY to backend/.env "
                "before generating LLM timesheet summaries."
            ),
        )

    workflow_name = "ASM MVP10 - Generate Timesheet Summary"

    instructions = (
        "You are an expert consulting delivery assistant. "
        "Summarize timesheet accomplishments into professional status-report language. "
        "Return only valid JSON with these keys: "
        "summary_text, accomplishments_summary, blockers_summary, next_steps_summary. "
        "Do not include markdown fences."
    )

    user_input = (
        f"Summary type: {payload.summary_type}\n"
        f"Person: {payload.person_name}\n"
        f"Date range: {payload.start_date} to {payload.end_date}\n\n"
        f"Timesheet entries:\n{source_context}\n\n"
        "Create a concise, executive-friendly summary that can be used for weekly reporting."
    )

    agent = Agent(
        name="ASM Timesheet Summary Assistant",
        instructions=instructions,
        model=LLM_MODEL,
    )

    with trace(
        workflow_name=workflow_name,
        metadata={
            "project": "ASM Engagement Cockpit",
            "mvp": "MVP 10",
            "model": LLM_MODEL,
            "openai_tracing_enabled": str(OPENAI_TRACING_ENABLED),
            "summary_type": payload.summary_type,
            "person_name": payload.person_name,
            "start_date": str(payload.start_date),
            "end_date": str(payload.end_date),
        },
    ):
        result = await Runner.run(agent, user_input)

    return str(result.final_output)


@router.post("/timesheets", response_model=TimesheetEntryRead)
def create_timesheet_entry(
    payload: TimesheetEntryCreate,
    db: Annotated[Session, Depends(get_db)],
) -> TimesheetEntry:
    validate_optional_reference(db, Workstream, payload.workstream_id, "Workstream")
    validate_optional_reference(db, Deliverable, payload.deliverable_id, "Deliverable")
    validate_optional_reference(db, Task, payload.task_id, "Task")
    validate_optional_reference(db, Subtask, payload.subtask_id, "Sub-task")

    if payload.effort_hours < 0:
        raise HTTPException(status_code=400, detail="effort_hours cannot be negative")

    entry = TimesheetEntry(**payload.model_dump())

    db.add(entry)
    db.commit()
    db.refresh(entry)

    return entry


@router.get("/timesheets", response_model=list[TimesheetEntryRead])
def list_timesheet_entries(
    db: Annotated[Session, Depends(get_db)],
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    person_name: str | None = Query(default=None),
    submitted: bool | None = Query(default=None),
) -> list[TimesheetEntry]:
    statement = select(TimesheetEntry).order_by(TimesheetEntry.entry_date.desc(), TimesheetEntry.created_at.desc())

    if start_date:
        statement = statement.where(TimesheetEntry.entry_date >= start_date)

    if end_date:
        statement = statement.where(TimesheetEntry.entry_date <= end_date)

    if person_name:
        statement = statement.where(TimesheetEntry.person_name == person_name)

    if submitted is not None:
        statement = statement.where(TimesheetEntry.submitted == submitted)

    return list(db.scalars(statement).all())


@router.put("/timesheets/{timesheet_id}", response_model=TimesheetEntryRead)
def update_timesheet_entry(
    timesheet_id: uuid.UUID,
    payload: TimesheetEntryUpdate,
    db: Annotated[Session, Depends(get_db)],
) -> TimesheetEntry:
    entry = db.get(TimesheetEntry, timesheet_id)

    if entry is None:
        raise HTTPException(status_code=404, detail="Timesheet entry not found")

    update_model_from_payload(entry, payload)

    if entry.effort_hours < 0:
        raise HTTPException(status_code=400, detail="effort_hours cannot be negative")

    validate_optional_reference(db, Workstream, entry.workstream_id, "Workstream")
    validate_optional_reference(db, Deliverable, entry.deliverable_id, "Deliverable")
    validate_optional_reference(db, Task, entry.task_id, "Task")
    validate_optional_reference(db, Subtask, entry.subtask_id, "Sub-task")

    db.add(entry)
    db.commit()
    db.refresh(entry)

    return entry


@router.post("/timesheets/submit-week", response_model=TimesheetWeekSubmitResponse)
def submit_timesheet_week(
    payload: TimesheetWeekSubmitRequest,
    db: Annotated[Session, Depends(get_db)],
) -> TimesheetWeekSubmitResponse:
    if payload.end_date < payload.start_date:
        raise HTTPException(status_code=400, detail="end_date cannot be before start_date")

    entries = list(
        db.scalars(
            select(TimesheetEntry)
            .where(TimesheetEntry.entry_date >= payload.start_date)
            .where(TimesheetEntry.entry_date <= payload.end_date)
            .where(TimesheetEntry.person_name == payload.person_name)
        ).all()
    )

    submitted_at = datetime.utcnow()

    for entry in entries:
        entry.submitted = True
        entry.submitted_at = submitted_at
        entry.submitted_by = payload.submitted_by
        entry.status = "Submitted"

    db.commit()

    return TimesheetWeekSubmitResponse(
        submitted_count=len(entries),
        start_date=payload.start_date,
        end_date=payload.end_date,
        person_name=payload.person_name,
    )


@router.post("/timesheets/generate-summary", response_model=TimesheetSummaryRead)
async def generate_timesheet_summary(
    payload: TimesheetSummaryGenerateRequest,
    db: Annotated[Session, Depends(get_db)],
) -> TimesheetSummary:
    if payload.end_date < payload.start_date:
        raise HTTPException(status_code=400, detail="end_date cannot be before start_date")

    entries = list(
        db.scalars(
            select(TimesheetEntry)
            .where(TimesheetEntry.entry_date >= payload.start_date)
            .where(TimesheetEntry.entry_date <= payload.end_date)
            .where(TimesheetEntry.person_name == payload.person_name)
            .order_by(TimesheetEntry.entry_date.asc(), TimesheetEntry.created_at.asc())
        ).all()
    )

    if not entries:
        raise HTTPException(status_code=404, detail="No timesheet entries found for selected date range")

    source_context = build_timesheet_summary_context(db, entries)
    llm_output = await run_traced_timesheet_summary_agent(source_context, payload)
    parsed = json_or_empty(llm_output)

    total_effort_hours = sum(entry.effort_hours for entry in entries)

    summary = TimesheetSummary(
        person_name=payload.person_name,
        summary_type=payload.summary_type,
        start_date=payload.start_date,
        end_date=payload.end_date,
        total_effort_hours=total_effort_hours,
        entry_count=len(entries),
        summary_text=parsed.get("summary_text") or llm_output,
        accomplishments_summary=parsed.get("accomplishments_summary"),
        blockers_summary=parsed.get("blockers_summary"),
        next_steps_summary=parsed.get("next_steps_summary"),
        source_context=source_context,
        llm_raw_output=llm_output,
        model_name=LLM_MODEL,
        trace_workflow_name="ASM MVP10 - Generate Timesheet Summary",
        created_by=payload.created_by,
    )

    db.add(summary)
    db.commit()
    db.refresh(summary)

    return summary


@router.get("/timesheet-summaries", response_model=list[TimesheetSummaryRead])
def list_timesheet_summaries(
    db: Annotated[Session, Depends(get_db)],
    person_name: str | None = Query(default=None),
) -> list[TimesheetSummary]:
    statement = select(TimesheetSummary).order_by(TimesheetSummary.created_at.desc())

    if person_name:
        statement = statement.where(TimesheetSummary.person_name == person_name)

    return list(db.scalars(statement).all())
