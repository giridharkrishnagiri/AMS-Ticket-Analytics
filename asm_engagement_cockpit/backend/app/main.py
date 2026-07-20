import uuid
from datetime import date, timedelta
from decimal import Decimal
from typing import Annotated, Any

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import create_database_tables, get_db
from app.middleware import ApiKeyProtectionMiddleware, RequestLoggingMiddleware
from app.models import (
    DataPoint,
    DateRevisionHistory,
    Deliverable,
    Engagement,
    Reminder,
    StakeholderQuestion,
    Subtask,
    Task,
    Workstream,
)
from app.services.hierarchy_sort import sort_hierarchy_items
from app.schemas import (
    DashboardSummary,
    DataPointCreate,
    DataPointRead,
    DataPointUpdate,
    DateRevisionHistoryRead,
    DeliverableCreate,
    DeliverableRead,
    DeliverableUpdate,
    EngagementCreate,
    EngagementRead,
    EngagementUpdate,
    HealthResponse,
    ReminderGenerateResponse,
    ReminderRead,
    ReminderSnoozeRequest,
    StakeholderQuestionCreate,
    StakeholderQuestionRead,
    StakeholderQuestionUpdate,
    SubtaskCreate,
    SubtaskRead,
    SubtaskUpdate,
    TaskCreate,
    TaskRead,
    TaskUpdate,
    WorkstreamCreate,
    WorkstreamRead,
    WorkstreamUpdate,
)
from app.mvp5_findings_router import router as mvp5_findings_router
from app.mvp6_refinement_router import router as mvp6_refinement_router
from app.mvp10_timesheets_router import router as mvp10_timesheets_router
from app.mvp11_review_workflow_router import router as mvp11_review_workflow_router
from app.mvp12_recommendation_management_router import router as mvp12_recommendation_management_router
from app.mvp14_diagnostics_router import router as mvp14_diagnostics_router
from app.mvp18_workspace_router import router as mvp18_workspace_router
from app.workshop_chat_router import router as workshop_chat_router
from app.workshops_router import router as workshops_router

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version="0.4.0",
)

app.add_middleware(ApiKeyProtectionMiddleware)
app.add_middleware(RequestLoggingMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(mvp5_findings_router)
app.include_router(mvp6_refinement_router)
app.include_router(mvp10_timesheets_router)
app.include_router(mvp11_review_workflow_router)
app.include_router(mvp12_recommendation_management_router)
app.include_router(mvp14_diagnostics_router)
app.include_router(mvp18_workspace_router)
app.include_router(workshop_chat_router)
app.include_router(workshops_router)

COMPLETED_STATUS = "Completed"
REMINDER_LOOKAHEAD_DAYS = 7
DATA_POINT_CLOSED_STATUSES = {"received", "not available", "not applicable"}
QUESTION_CLOSED_STATUSES = {"responded", "closed"}


@app.on_event("startup")
def on_startup() -> None:
    create_database_tables()


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        app_name=settings.app_name,
        app_env=settings.app_env,
    )


def is_completed(status: str | None) -> bool:
    return (status or "").strip().lower() == COMPLETED_STATUS.lower()


def is_data_point_closed(status: str | None) -> bool:
    return (status or "").strip().lower() in DATA_POINT_CLOSED_STATUSES


def is_question_closed(status: str | None) -> bool:
    return (status or "").strip().lower() in QUESTION_CLOSED_STATUSES


def calculate_completed_ratio(items: list[Any]) -> Decimal:
    if not items:
        return Decimal("0.00")

    completed_count = sum(1 for item in items if is_completed(item.status))
    progress = Decimal(completed_count * 100) / Decimal(len(items))
    return progress.quantize(Decimal("0.01"))


def add_date_revision_history(
    db: Session,
    *,
    parent_type: str,
    parent_id: uuid.UUID,
    original_date: date | None,
    previous_revised_date: date | None,
    new_revised_date: date | None,
    reason: str | None,
) -> None:
    history = DateRevisionHistory(
        parent_type=parent_type,
        parent_id=parent_id,
        original_date=original_date,
        previous_revised_date=previous_revised_date,
        new_revised_date=new_revised_date,
        reason=reason or "No reason provided",
    )
    db.add(history)


def update_model_from_payload(
    db: Session,
    *,
    item: Any,
    payload: Any,
    parent_type: str,
    target_date_field: str,
    revised_date_field: str,
) -> None:
    data = payload.model_dump(exclude_unset=True)
    reason = data.pop("date_revision_reason", None)

    if revised_date_field in data:
        previous_revised_date = getattr(item, revised_date_field)
        new_revised_date = data[revised_date_field]

        if previous_revised_date != new_revised_date:
            add_date_revision_history(
                db,
                parent_type=parent_type,
                parent_id=item.id,
                original_date=getattr(item, target_date_field),
                previous_revised_date=previous_revised_date,
                new_revised_date=new_revised_date,
                reason=reason,
            )

    for field_name, value in data.items():
        setattr(item, field_name, value)


def update_simple_model_from_payload(item: Any, payload: Any) -> None:
    data = payload.model_dump(exclude_unset=True)
    for field_name, value in data.items():
        setattr(item, field_name, value)


def validate_completion_rules(db: Session, item: Any, item_type: str) -> None:
    if not is_completed(getattr(item, "status", None)):
        return

    if item_type == "engagement":
        workstreams = list(db.scalars(select(Workstream).where(Workstream.engagement_id == item.id)).all())
        incomplete = [child for child in workstreams if not is_completed(child.status)]
        if incomplete:
            raise HTTPException(status_code=400, detail="Engagement cannot be completed until all workstreams are completed.")

    if item_type == "workstream":
        deliverables = list(db.scalars(select(Deliverable).where(Deliverable.workstream_id == item.id)).all())
        incomplete = [child for child in deliverables if not is_completed(child.status)]
        if incomplete:
            raise HTTPException(status_code=400, detail="Workstream cannot be completed until all deliverables are completed.")

    if item_type == "deliverable":
        tasks = list(db.scalars(select(Task).where(Task.deliverable_id == item.id)).all())
        incomplete = [child for child in tasks if not is_completed(child.status)]
        if incomplete:
            raise HTTPException(status_code=400, detail="Deliverable cannot be completed until all tasks are completed.")

    if item_type == "task":
        subtasks = list(db.scalars(select(Subtask).where(Subtask.task_id == item.id)).all())
        incomplete = [child for child in subtasks if not is_completed(child.status)]
        if incomplete:
            raise HTTPException(status_code=400, detail="Task cannot be completed until all sub-tasks are completed.")


def recalculate_task_progress(db: Session, task_id: uuid.UUID) -> None:
    task = db.get(Task, task_id)
    if task is None:
        return
    subtasks = list(db.scalars(select(Subtask).where(Subtask.task_id == task.id)).all())
    task.progress_percent = calculate_completed_ratio(subtasks)


def recalculate_deliverable_progress(db: Session, deliverable_id: uuid.UUID) -> None:
    deliverable = db.get(Deliverable, deliverable_id)
    if deliverable is None:
        return
    tasks = list(db.scalars(select(Task).where(Task.deliverable_id == deliverable.id)).all())
    deliverable.progress_percent = calculate_completed_ratio(tasks)


def recalculate_workstream_progress(db: Session, workstream_id: uuid.UUID) -> None:
    workstream = db.get(Workstream, workstream_id)
    if workstream is None:
        return
    deliverables = list(db.scalars(select(Deliverable).where(Deliverable.workstream_id == workstream.id)).all())
    workstream.progress_percent = calculate_completed_ratio(deliverables)


def recalculate_engagement_progress(db: Session, engagement_id: uuid.UUID) -> None:
    engagement = db.get(Engagement, engagement_id)
    if engagement is None:
        return
    workstreams = list(db.scalars(select(Workstream).where(Workstream.engagement_id == engagement.id)).all())
    engagement.progress_percent = calculate_completed_ratio(workstreams)


def recalculate_from_subtask(db: Session, subtask: Subtask) -> None:
    task = db.get(Task, subtask.task_id)
    if task is None:
        return
    recalculate_task_progress(db, task.id)

    deliverable = db.get(Deliverable, task.deliverable_id)
    if deliverable is None:
        return
    recalculate_deliverable_progress(db, deliverable.id)

    workstream = db.get(Workstream, deliverable.workstream_id)
    if workstream is None:
        return
    recalculate_workstream_progress(db, workstream.id)
    recalculate_engagement_progress(db, workstream.engagement_id)


def recalculate_from_task(db: Session, task: Task) -> None:
    recalculate_task_progress(db, task.id)
    deliverable = db.get(Deliverable, task.deliverable_id)
    if deliverable is None:
        return
    recalculate_deliverable_progress(db, deliverable.id)
    workstream = db.get(Workstream, deliverable.workstream_id)
    if workstream is None:
        return
    recalculate_workstream_progress(db, workstream.id)
    recalculate_engagement_progress(db, workstream.engagement_id)


def recalculate_from_deliverable(db: Session, deliverable: Deliverable) -> None:
    recalculate_deliverable_progress(db, deliverable.id)
    workstream = db.get(Workstream, deliverable.workstream_id)
    if workstream is None:
        return
    recalculate_workstream_progress(db, workstream.id)
    recalculate_engagement_progress(db, workstream.engagement_id)


def recalculate_from_workstream(db: Session, workstream: Workstream) -> None:
    recalculate_workstream_progress(db, workstream.id)
    recalculate_engagement_progress(db, workstream.engagement_id)


def get_effective_completion_date(item: Any) -> date | None:
    return getattr(item, "revised_completion_date", None) or getattr(item, "target_completion_date", None)


def get_parent_title(item: Any, parent_type: str) -> str:
    if parent_type == "task":
        return item.title
    if parent_type == "data_point":
        return item.topic
    if parent_type == "stakeholder_question":
        return item.question_text[:240]
    return item.name if hasattr(item, "name") else item.title


def get_parent_external_id(item: Any) -> str | None:
    return getattr(item, "external_id", None)


def close_active_reminders_for_parent(db: Session, *, parent_type: str, parent_id: uuid.UUID) -> None:
    reminders = list(
        db.scalars(
            select(Reminder).where(
                Reminder.parent_type == parent_type,
                Reminder.parent_id == parent_id,
                Reminder.is_active.is_(True),
            )
        ).all()
    )

    for reminder in reminders:
        reminder.is_active = False
        reminder.reminder_status = "Closed"


def classify_due_date(effective_due_date: date, today: date) -> tuple[str, str, str]:
    if effective_due_date < today:
        return "overdue", "Overdue", "high"
    if effective_due_date == today:
        return "due_today", "Due Today", "medium"
    if effective_due_date <= today + timedelta(days=REMINDER_LOOKAHEAD_DAYS):
        return "due_soon", "Due Soon", "low"
    return "not_due", "Not Due", "none"


def create_or_update_due_reminder(db: Session, *, parent_type: str, item: Any, today: date) -> bool:
    if is_completed(getattr(item, "status", None)):
        close_active_reminders_for_parent(db, parent_type=parent_type, parent_id=item.id)
        return False

    effective_due_date = get_effective_completion_date(item)

    if effective_due_date is None:
        close_active_reminders_for_parent(db, parent_type=parent_type, parent_id=item.id)
        return False

    reminder_type, reminder_status, severity = classify_due_date(effective_due_date, today)

    if reminder_type == "not_due":
        close_active_reminders_for_parent(db, parent_type=parent_type, parent_id=item.id)
        return False

    return upsert_reminder(
        db,
        parent_type=parent_type,
        item=item,
        today=today,
        reminder_type=reminder_type,
        reminder_status=reminder_status,
        severity=severity,
        effective_due_date=effective_due_date,
    )


def upsert_reminder(
    db: Session,
    *,
    parent_type: str,
    item: Any,
    today: date,
    reminder_type: str,
    reminder_status: str,
    severity: str,
    effective_due_date: date,
) -> bool:
    parent_title = get_parent_title(item, parent_type)
    parent_external_id = get_parent_external_id(item)

    existing = db.scalar(
        select(Reminder).where(
            Reminder.parent_type == parent_type,
            Reminder.parent_id == item.id,
            Reminder.is_active.is_(True),
        )
    )

    display_name = f"{parent_external_id} - {parent_title}" if parent_external_id else parent_title
    title = f"{reminder_status}: {display_name}"

    if parent_type == "data_point":
        message = f"Data point '{display_name}' is expected by {effective_due_date} and is not yet received."
    elif parent_type == "stakeholder_question":
        message = f"Stakeholder response for '{display_name}' is expected by {effective_due_date} and is not yet received."
    elif reminder_status == "Overdue":
        message = f"{parent_type.title()} '{display_name}' is overdue. Complete it or revise the completion date."
    elif reminder_status == "Due Today":
        message = f"{parent_type.title()} '{display_name}' is due today."
    else:
        message = f"{parent_type.title()} '{display_name}' is due within the next {REMINDER_LOOKAHEAD_DAYS} days."

    if existing is None:
        reminder = Reminder(
            parent_type=parent_type,
            parent_id=item.id,
            parent_external_id=parent_external_id,
            parent_title=parent_title,
            reminder_type=reminder_type,
            reminder_status=reminder_status,
            severity=severity,
            reminder_date=today,
            effective_due_date=effective_due_date,
            title=title,
            message=message,
            is_active=True,
        )
        db.add(reminder)
    else:
        existing.parent_external_id = parent_external_id
        existing.parent_title = parent_title
        existing.reminder_type = reminder_type
        existing.reminder_status = reminder_status
        existing.severity = severity
        existing.reminder_date = today
        existing.effective_due_date = effective_due_date
        existing.title = title
        existing.message = message
        existing.dismissed_reason = None

    return True


def create_or_update_data_point_reminder(db: Session, *, item: DataPoint, today: date) -> bool:
    if is_data_point_closed(item.status) or item.actual_received_date is not None:
        close_active_reminders_for_parent(db, parent_type="data_point", parent_id=item.id)
        return False

    if item.expected_received_date is None:
        close_active_reminders_for_parent(db, parent_type="data_point", parent_id=item.id)
        return False

    reminder_type, reminder_status, severity = classify_due_date(item.expected_received_date, today)

    if reminder_type == "not_due":
        close_active_reminders_for_parent(db, parent_type="data_point", parent_id=item.id)
        return False

    return upsert_reminder(
        db,
        parent_type="data_point",
        item=item,
        today=today,
        reminder_type=reminder_type,
        reminder_status=reminder_status,
        severity=severity,
        effective_due_date=item.expected_received_date,
    )


def create_or_update_question_reminder(db: Session, *, item: StakeholderQuestion, today: date) -> bool:
    if is_question_closed(item.response_status) or item.actual_response_date is not None:
        close_active_reminders_for_parent(db, parent_type="stakeholder_question", parent_id=item.id)
        return False

    if item.expected_response_date is None:
        close_active_reminders_for_parent(db, parent_type="stakeholder_question", parent_id=item.id)
        return False

    reminder_type, reminder_status, severity = classify_due_date(item.expected_response_date, today)

    if reminder_type == "not_due":
        close_active_reminders_for_parent(db, parent_type="stakeholder_question", parent_id=item.id)
        return False

    return upsert_reminder(
        db,
        parent_type="stakeholder_question",
        item=item,
        today=today,
        reminder_type=reminder_type,
        reminder_status=reminder_status,
        severity=severity,
        effective_due_date=item.expected_response_date,
    )


def generate_all_reminders(db: Session) -> int:
    today = date.today()
    generated_or_updated = 0

    for deliverable in list(db.scalars(select(Deliverable)).all()):
        if create_or_update_due_reminder(db, parent_type="deliverable", item=deliverable, today=today):
            generated_or_updated += 1

    for task in list(db.scalars(select(Task)).all()):
        if create_or_update_due_reminder(db, parent_type="task", item=task, today=today):
            generated_or_updated += 1

    for subtask in list(db.scalars(select(Subtask)).all()):
        if create_or_update_due_reminder(db, parent_type="subtask", item=subtask, today=today):
            generated_or_updated += 1

    for data_point in list(db.scalars(select(DataPoint)).all()):
        if create_or_update_data_point_reminder(db, item=data_point, today=today):
            generated_or_updated += 1

    for question in list(db.scalars(select(StakeholderQuestion)).all()):
        if create_or_update_question_reminder(db, item=question, today=today):
            generated_or_updated += 1

    return generated_or_updated


def count_active_reminders(db: Session, reminder_type: str | None = None) -> int:
    today = date.today()
    statement = select(func.count()).select_from(Reminder).where(
        Reminder.is_active.is_(True),
        (Reminder.snoozed_until.is_(None)) | (Reminder.snoozed_until <= today),
    )

    if reminder_type is not None:
        statement = statement.where(Reminder.reminder_type == reminder_type)

    return db.scalar(statement) or 0


@app.get("/api/dashboard/summary", response_model=DashboardSummary)
def dashboard_summary(db: Annotated[Session, Depends(get_db)]) -> DashboardSummary:
    generate_all_reminders(db)
    db.commit()

    return DashboardSummary(
        engagements=db.scalar(select(func.count()).select_from(Engagement)) or 0,
        workstreams=db.scalar(select(func.count()).select_from(Workstream)) or 0,
        deliverables=db.scalar(select(func.count()).select_from(Deliverable)) or 0,
        tasks=db.scalar(select(func.count()).select_from(Task)) or 0,
        subtasks=db.scalar(select(func.count()).select_from(Subtask)) or 0,
        data_points=db.scalar(select(func.count()).select_from(DataPoint)) or 0,
        stakeholder_questions=db.scalar(select(func.count()).select_from(StakeholderQuestion)) or 0,
        active_reminders=count_active_reminders(db),
        overdue_reminders=count_active_reminders(db, "overdue"),
        due_today_reminders=count_active_reminders(db, "due_today"),
        due_soon_reminders=count_active_reminders(db, "due_soon"),
    )


@app.post("/api/reminders/generate", response_model=ReminderGenerateResponse)
def generate_reminders(db: Annotated[Session, Depends(get_db)]) -> ReminderGenerateResponse:
    generated_or_updated = generate_all_reminders(db)
    db.commit()
    return ReminderGenerateResponse(
        generated_or_updated=generated_or_updated,
        active_reminders=count_active_reminders(db),
    )


@app.get("/api/reminders/active", response_model=list[ReminderRead])
def list_active_reminders(
    db: Annotated[Session, Depends(get_db)],
    include_snoozed: bool = Query(default=False),
) -> list[Reminder]:
    generate_all_reminders(db)
    db.commit()

    today = date.today()
    statement = select(Reminder).where(Reminder.is_active.is_(True))

    if not include_snoozed:
        statement = statement.where((Reminder.snoozed_until.is_(None)) | (Reminder.snoozed_until <= today))

    statement = statement.order_by(
        Reminder.effective_due_date.asc().nullslast(),
        Reminder.severity.desc(),
        Reminder.updated_at.desc(),
    )

    return list(db.scalars(statement).all())


@app.post("/api/reminders/{reminder_id}/snooze", response_model=ReminderRead)
def snooze_reminder(
    reminder_id: uuid.UUID,
    payload: ReminderSnoozeRequest,
    db: Annotated[Session, Depends(get_db)],
) -> Reminder:
    reminder = db.get(Reminder, reminder_id)
    if reminder is None:
        raise HTTPException(status_code=404, detail="Reminder not found")

    reminder.snoozed_until = payload.snoozed_until
    db.commit()
    db.refresh(reminder)
    return reminder


@app.get("/api/date-revision-history", response_model=list[DateRevisionHistoryRead])
def list_date_revision_history(
    db: Annotated[Session, Depends(get_db)],
    parent_type: str | None = Query(default=None),
    parent_id: uuid.UUID | None = Query(default=None),
) -> list[DateRevisionHistory]:
    statement = select(DateRevisionHistory).order_by(DateRevisionHistory.revised_at.desc())

    if parent_type is not None:
        statement = statement.where(DateRevisionHistory.parent_type == parent_type)

    if parent_id is not None:
        statement = statement.where(DateRevisionHistory.parent_id == parent_id)

    return list(db.scalars(statement).all())


@app.post("/api/engagements", response_model=EngagementRead)
def create_engagement(payload: EngagementCreate, db: Annotated[Session, Depends(get_db)]) -> Engagement:
    item = Engagement(**payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@app.get("/api/engagements", response_model=list[EngagementRead])
def list_engagements(db: Annotated[Session, Depends(get_db)]) -> list[Engagement]:
    return list(db.scalars(select(Engagement).order_by(Engagement.created_at.desc())).all())


@app.get("/api/engagements/{engagement_id}", response_model=EngagementRead)
def get_engagement(engagement_id: uuid.UUID, db: Annotated[Session, Depends(get_db)]) -> Engagement:
    item = db.get(Engagement, engagement_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Engagement not found")
    return item


@app.put("/api/engagements/{engagement_id}", response_model=EngagementRead)
def update_engagement(
    engagement_id: uuid.UUID,
    payload: EngagementUpdate,
    db: Annotated[Session, Depends(get_db)],
) -> Engagement:
    item = db.get(Engagement, engagement_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Engagement not found")

    update_model_from_payload(
        db,
        item=item,
        payload=payload,
        parent_type="engagement",
        target_date_field="target_end_date",
        revised_date_field="revised_end_date",
    )
    validate_completion_rules(db, item, "engagement")

    db.commit()
    db.refresh(item)
    return item


@app.post("/api/workstreams", response_model=WorkstreamRead)
def create_workstream(payload: WorkstreamCreate, db: Annotated[Session, Depends(get_db)]) -> Workstream:
    if db.get(Engagement, payload.engagement_id) is None:
        raise HTTPException(status_code=404, detail="Engagement not found")

    item = Workstream(**payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    recalculate_engagement_progress(db, item.engagement_id)
    db.commit()
    db.refresh(item)
    return item


@app.get("/api/workstreams", response_model=list[WorkstreamRead])
def list_workstreams(
    db: Annotated[Session, Depends(get_db)],
    engagement_id: uuid.UUID | None = Query(default=None),
) -> list[Workstream]:
    statement = select(Workstream)
    if engagement_id is not None:
        statement = select(Workstream).where(Workstream.engagement_id == engagement_id)
    return sort_hierarchy_items(list(db.scalars(statement).all()))


@app.get("/api/workstreams/{workstream_id}", response_model=WorkstreamRead)
def get_workstream(workstream_id: uuid.UUID, db: Annotated[Session, Depends(get_db)]) -> Workstream:
    item = db.get(Workstream, workstream_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Workstream not found")
    return item


@app.put("/api/workstreams/{workstream_id}", response_model=WorkstreamRead)
def update_workstream(
    workstream_id: uuid.UUID,
    payload: WorkstreamUpdate,
    db: Annotated[Session, Depends(get_db)],
) -> Workstream:
    item = db.get(Workstream, workstream_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Workstream not found")

    update_model_from_payload(
        db,
        item=item,
        payload=payload,
        parent_type="workstream",
        target_date_field="target_completion_date",
        revised_date_field="revised_completion_date",
    )
    validate_completion_rules(db, item, "workstream")
    recalculate_from_workstream(db, item)

    db.commit()
    db.refresh(item)
    return item


@app.post("/api/deliverables", response_model=DeliverableRead)
def create_deliverable(payload: DeliverableCreate, db: Annotated[Session, Depends(get_db)]) -> Deliverable:
    if db.get(Workstream, payload.workstream_id) is None:
        raise HTTPException(status_code=404, detail="Workstream not found")

    item = Deliverable(**payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    recalculate_from_deliverable(db, item)
    create_or_update_due_reminder(db, parent_type="deliverable", item=item, today=date.today())
    db.commit()
    db.refresh(item)
    return item


@app.get("/api/deliverables", response_model=list[DeliverableRead])
def list_deliverables(
    db: Annotated[Session, Depends(get_db)],
    workstream_id: uuid.UUID | None = Query(default=None),
) -> list[Deliverable]:
    statement = select(Deliverable)
    if workstream_id is not None:
        statement = select(Deliverable).where(Deliverable.workstream_id == workstream_id)
    return sort_hierarchy_items(list(db.scalars(statement).all()))


@app.get("/api/deliverables/{deliverable_id}", response_model=DeliverableRead)
def get_deliverable(deliverable_id: uuid.UUID, db: Annotated[Session, Depends(get_db)]) -> Deliverable:
    item = db.get(Deliverable, deliverable_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Deliverable not found")
    return item


@app.put("/api/deliverables/{deliverable_id}", response_model=DeliverableRead)
def update_deliverable(
    deliverable_id: uuid.UUID,
    payload: DeliverableUpdate,
    db: Annotated[Session, Depends(get_db)],
) -> Deliverable:
    item = db.get(Deliverable, deliverable_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Deliverable not found")

    update_model_from_payload(
        db,
        item=item,
        payload=payload,
        parent_type="deliverable",
        target_date_field="target_completion_date",
        revised_date_field="revised_completion_date",
    )
    validate_completion_rules(db, item, "deliverable")
    recalculate_from_deliverable(db, item)
    create_or_update_due_reminder(db, parent_type="deliverable", item=item, today=date.today())

    db.commit()
    db.refresh(item)
    return item


@app.post("/api/tasks", response_model=TaskRead)
def create_task(payload: TaskCreate, db: Annotated[Session, Depends(get_db)]) -> Task:
    if db.get(Deliverable, payload.deliverable_id) is None:
        raise HTTPException(status_code=404, detail="Deliverable not found")

    item = Task(**payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    recalculate_from_task(db, item)
    create_or_update_due_reminder(db, parent_type="task", item=item, today=date.today())
    db.commit()
    db.refresh(item)
    return item


@app.get("/api/tasks", response_model=list[TaskRead])
def list_tasks(
    db: Annotated[Session, Depends(get_db)],
    deliverable_id: uuid.UUID | None = Query(default=None),
) -> list[Task]:
    statement = select(Task)
    if deliverable_id is not None:
        statement = select(Task).where(Task.deliverable_id == deliverable_id)
    return sort_hierarchy_items(list(db.scalars(statement).all()))


@app.get("/api/tasks/{task_id}", response_model=TaskRead)
def get_task(task_id: uuid.UUID, db: Annotated[Session, Depends(get_db)]) -> Task:
    item = db.get(Task, task_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return item


@app.put("/api/tasks/{task_id}", response_model=TaskRead)
def update_task(
    task_id: uuid.UUID,
    payload: TaskUpdate,
    db: Annotated[Session, Depends(get_db)],
) -> Task:
    item = db.get(Task, task_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Task not found")

    update_model_from_payload(
        db,
        item=item,
        payload=payload,
        parent_type="task",
        target_date_field="target_completion_date",
        revised_date_field="revised_completion_date",
    )
    validate_completion_rules(db, item, "task")
    recalculate_from_task(db, item)
    create_or_update_due_reminder(db, parent_type="task", item=item, today=date.today())

    db.commit()
    db.refresh(item)
    return item


@app.post("/api/subtasks", response_model=SubtaskRead)
def create_subtask(payload: SubtaskCreate, db: Annotated[Session, Depends(get_db)]) -> Subtask:
    if db.get(Task, payload.task_id) is None:
        raise HTTPException(status_code=404, detail="Task not found")

    item = Subtask(**payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    recalculate_from_subtask(db, item)
    create_or_update_due_reminder(db, parent_type="subtask", item=item, today=date.today())
    db.commit()
    db.refresh(item)
    return item


@app.get("/api/subtasks", response_model=list[SubtaskRead])
def list_subtasks(
    db: Annotated[Session, Depends(get_db)],
    task_id: uuid.UUID | None = Query(default=None),
) -> list[Subtask]:
    statement = select(Subtask).order_by(Subtask.created_at.desc())
    if task_id is not None:
        statement = select(Subtask).where(Subtask.task_id == task_id).order_by(Subtask.created_at.desc())
    return list(db.scalars(statement).all())


@app.get("/api/subtasks/{subtask_id}", response_model=SubtaskRead)
def get_subtask(subtask_id: uuid.UUID, db: Annotated[Session, Depends(get_db)]) -> Subtask:
    item = db.get(Subtask, subtask_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Sub-task not found")
    return item


@app.put("/api/subtasks/{subtask_id}", response_model=SubtaskRead)
def update_subtask(
    subtask_id: uuid.UUID,
    payload: SubtaskUpdate,
    db: Annotated[Session, Depends(get_db)],
) -> Subtask:
    item = db.get(Subtask, subtask_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Sub-task not found")

    update_model_from_payload(
        db,
        item=item,
        payload=payload,
        parent_type="subtask",
        target_date_field="target_completion_date",
        revised_date_field="revised_completion_date",
    )
    recalculate_from_subtask(db, item)
    create_or_update_due_reminder(db, parent_type="subtask", item=item, today=date.today())

    db.commit()
    db.refresh(item)
    return item


@app.post("/api/data-points", response_model=DataPointRead)
def create_data_point(payload: DataPointCreate, db: Annotated[Session, Depends(get_db)]) -> DataPoint:
    if db.get(Subtask, payload.subtask_id) is None:
        raise HTTPException(status_code=404, detail="Sub-task not found")

    item = DataPoint(**payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    create_or_update_data_point_reminder(db, item=item, today=date.today())
    db.commit()
    db.refresh(item)
    return item


@app.get("/api/data-points", response_model=list[DataPointRead])
def list_data_points(
    db: Annotated[Session, Depends(get_db)],
    subtask_id: uuid.UUID | None = Query(default=None),
) -> list[DataPoint]:
    statement = select(DataPoint).order_by(DataPoint.created_at.desc())
    if subtask_id is not None:
        statement = select(DataPoint).where(DataPoint.subtask_id == subtask_id).order_by(DataPoint.created_at.desc())
    return list(db.scalars(statement).all())


@app.get("/api/data-points/{data_point_id}", response_model=DataPointRead)
def get_data_point(data_point_id: uuid.UUID, db: Annotated[Session, Depends(get_db)]) -> DataPoint:
    item = db.get(DataPoint, data_point_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Data point not found")
    return item


@app.put("/api/data-points/{data_point_id}", response_model=DataPointRead)
def update_data_point(
    data_point_id: uuid.UUID,
    payload: DataPointUpdate,
    db: Annotated[Session, Depends(get_db)],
) -> DataPoint:
    item = db.get(DataPoint, data_point_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Data point not found")

    update_simple_model_from_payload(item, payload)
    create_or_update_data_point_reminder(db, item=item, today=date.today())

    db.commit()
    db.refresh(item)
    return item


@app.post("/api/stakeholder-questions", response_model=StakeholderQuestionRead)
def create_stakeholder_question(
    payload: StakeholderQuestionCreate,
    db: Annotated[Session, Depends(get_db)],
) -> StakeholderQuestion:
    if db.get(Subtask, payload.subtask_id) is None:
        raise HTTPException(status_code=404, detail="Sub-task not found")

    item = StakeholderQuestion(**payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    create_or_update_question_reminder(db, item=item, today=date.today())
    db.commit()
    db.refresh(item)
    return item


@app.get("/api/stakeholder-questions", response_model=list[StakeholderQuestionRead])
def list_stakeholder_questions(
    db: Annotated[Session, Depends(get_db)],
    subtask_id: uuid.UUID | None = Query(default=None),
) -> list[StakeholderQuestion]:
    statement = select(StakeholderQuestion).order_by(StakeholderQuestion.created_at.desc())
    if subtask_id is not None:
        statement = (
            select(StakeholderQuestion)
            .where(StakeholderQuestion.subtask_id == subtask_id)
            .order_by(StakeholderQuestion.created_at.desc())
        )
    return list(db.scalars(statement).all())


@app.get("/api/stakeholder-questions/{question_id}", response_model=StakeholderQuestionRead)
def get_stakeholder_question(
    question_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
) -> StakeholderQuestion:
    item = db.get(StakeholderQuestion, question_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Stakeholder question not found")
    return item


@app.put("/api/stakeholder-questions/{question_id}", response_model=StakeholderQuestionRead)
def update_stakeholder_question(
    question_id: uuid.UUID,
    payload: StakeholderQuestionUpdate,
    db: Annotated[Session, Depends(get_db)],
) -> StakeholderQuestion:
    item = db.get(StakeholderQuestion, question_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Stakeholder question not found")

    update_simple_model_from_payload(item, payload)
    create_or_update_question_reminder(db, item=item, today=date.today())

    db.commit()
    db.refresh(item)
    return item
