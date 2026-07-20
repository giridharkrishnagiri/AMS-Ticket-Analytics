import json
import shutil
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Any, Type

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import (
    DataPoint,
    Deliverable,
    Engagement,
    Reminder,
    StakeholderQuestion,
    Subtask,
    Task,
    Workstream,
)
from app.models.mvp18_workspace import (
    UiWorkspaceAnalysis,
    UiWorkspaceDataCollection,
    UiWorkspaceEvidence,
    UiWorkspaceFile,
    UiWorkspaceFinding,
    UiWorkspaceQuestion,
    UiWorkspaceRecommendation,
)
from app.schemas.mvp18_workspace import (
    BreadcrumbItem,
    DashboardStatusSummary,
    DeleteResponse,
    DeliverableCreateUi,
    DeliverableUpdateUi,
    DeliverableWorkspace,
    EngagementCreateUi,
    EngagementUpdateUi,
    EngagementWorkspace,
    EntitySummary,
    ReminderIndicator,
    ScopeType,
    StatusBucket,
    SubtaskCreateUi,
    SubtaskUpdateUi,
    SubtaskWorkspace,
    TaskCreateUi,
    TaskUpdateUi,
    TaskWorkspace,
    WorkstreamCreateUi,
    WorkstreamUpdateUi,
    WorkstreamWorkspace,
    WorkspaceAnalysisCreate,
    WorkspaceAnalysisRead,
    WorkspaceAnalysisUpdate,
    WorkspaceDataCollectionCreate,
    WorkspaceDataCollectionRead,
    WorkspaceDataCollectionUpdate,
    WorkspaceEvidenceCreate,
    WorkspaceEvidenceRead,
    WorkspaceEvidenceUpdate,
    WorkspaceFileRead,
    WorkspaceFindingCreate,
    WorkspaceFindingRead,
    WorkspaceFindingUpdate,
    WorkspaceFullRecords,
    WorkspaceQuestionCreate,
    WorkspaceQuestionRead,
    WorkspaceQuestionUpdate,
    WorkspaceRecommendationRead,
    WorkspaceRecommendationRequest,
    WorkspaceRecordCounts,
    WorkspaceTextRefinementRequest,
    WorkspaceTextRefinementResponse,
)
from app.security import require_authenticated_request
from app.services.hierarchy_sort import hierarchy_sort_key, sort_hierarchy_items

router = APIRouter(prefix="/api/ui", tags=["MVP 18 Simplified Workspace UI"])

UPLOAD_ROOT = Path("data/uploads/mvp18_workspace")

DEFAULT_MY_WORK_OWNER = "Giridhar"
OWNED_TABLES = {"workstreams", "deliverables", "tasks", "subtasks"}


def _owner_search_terms(owner_name: str) -> list[str]:
    normalized = owner_name.strip().lower()
    if not normalized:
        return []

    first_token = normalized.split()[0]
    terms = [normalized]
    if first_token and first_token != normalized:
        terms.append(first_token)
    return terms


def _contains_owner(value: Any, owner_name: str = DEFAULT_MY_WORK_OWNER) -> bool:
    normalized_value = str(value or "").strip().lower()
    return any(term in normalized_value for term in _owner_search_terms(owner_name))


def _safe_owner_row(db: Session, table_name: str, entity_id: uuid.UUID) -> dict[str, str | None]:
    if table_name not in OWNED_TABLES:
        return {"owner_name": None, "secondary_owner_name": None}

    try:
        row = db.execute(
            text(
                f"""
                SELECT owner_name, secondary_owner_name
                FROM {table_name}
                WHERE id = :entity_id
                """
            ),
            {"entity_id": str(entity_id)},
        ).mappings().first()
    except Exception:
        return {"owner_name": None, "secondary_owner_name": None}

    if row is None:
        return {"owner_name": None, "secondary_owner_name": None}

    return {
        "owner_name": row.get("owner_name"),
        "secondary_owner_name": row.get("secondary_owner_name"),
    }


def _ownership_rank(db: Session, table_name: str, item: Any, owner_name: str = DEFAULT_MY_WORK_OWNER) -> int:
    owner_row = _safe_owner_row(db, table_name, item.id)

    if _contains_owner(owner_row.get("owner_name"), owner_name):
        return 0

    if _contains_owner(owner_row.get("secondary_owner_name"), owner_name):
        return 1

    return 2


def _sort_for_my_work_priority(db: Session, table_name: str, items: list[Any], owner_name: str = DEFAULT_MY_WORK_OWNER) -> list[Any]:
    return sorted(
        items,
        key=lambda item: (
            _ownership_rank(db, table_name, item, owner_name),
            hierarchy_sort_key(item),
        ),
    )


def _entity_summary_with_ownership(db: Session, table_name: str, item: Any) -> dict[str, Any]:
    summary = _entity_summary(item).model_dump(mode="json")
    owner_row = _safe_owner_row(db, table_name, item.id)
    summary["owner_name"] = owner_row.get("owner_name") or summary.get("owner_name")
    summary["secondary_owner_name"] = owner_row.get("secondary_owner_name")
    summary["ownership_rank"] = _ownership_rank(db, table_name, item)
    return summary


def _owned_items(db: Session, model: Type[Any], table_name: str, owner_column: str, owner_name: str) -> list[Any]:
    if table_name not in OWNED_TABLES or owner_column not in {"owner_name", "secondary_owner_name"}:
        return []

    owner_terms = _owner_search_terms(owner_name)
    if not owner_terms:
        return []

    try:
        owner_predicates = " OR ".join(
            f"lower(coalesce({owner_column}, '')) LIKE :owner_pattern_{index}"
            for index in range(len(owner_terms))
        )
        owner_params = {
            f"owner_pattern_{index}": f"%{term}%"
            for index, term in enumerate(owner_terms)
        }
        rows = db.execute(
            text(
                f"""
                SELECT id
                FROM {table_name}
                WHERE {owner_predicates}
                ORDER BY external_id NULLS LAST
                """
            ),
            owner_params,
        ).mappings().all()
    except Exception:
        return []

    items: list[Any] = []
    for row in rows:
        try:
            item = db.get(model, uuid.UUID(str(row["id"])))
        except Exception:
            item = None
        if item is not None:
            items.append(item)

    return _sort_for_my_work_priority(db, table_name, items, owner_name)


def _now() -> datetime:
    return datetime.utcnow()


def _normalize_status(status: str | None) -> str:
    value = (status or "").strip().lower()
    if value in {"not started", "new", "todo", "to do"}:
        return "not_started"
    if value in {"in progress", "in-progress", "active", "started"}:
        return "in_progress"
    if value.startswith("on hold") or value in {"blocked", "waiting", "waiting for information"}:
        return "on_hold"
    if value in {"completed", "complete", "done", "closed", "approved"}:
        return "completed"
    return "other"


def _status_bucket(db: Session, model: Type[Any]) -> StatusBucket:
    rows = list(db.scalars(select(model)).all())
    bucket = StatusBucket(total=len(rows))

    for row in rows:
        normalized = _normalize_status(getattr(row, "status", None))
        if normalized == "not_started":
            bucket.not_started += 1
        elif normalized == "in_progress":
            bucket.in_progress += 1
        elif normalized == "on_hold":
            bucket.on_hold += 1
        elif normalized == "completed":
            bucket.completed += 1
        else:
            bucket.other += 1

    return bucket


def _table_columns(model: Type[Any]) -> set[str]:
    return {column.key for column in model.__table__.columns}


def _apply_payload(item: Any, payload: Any) -> None:
    data = payload.model_dump(exclude_unset=True)
    valid_columns = _table_columns(type(item))

    for key, value in data.items():
        if key in valid_columns:
            setattr(item, key, value)


def _create_model(model: Type[Any], payload: Any, **forced_values: Any) -> Any:
    data = payload.model_dump(exclude_unset=True)
    data.update(forced_values)
    valid_columns = _table_columns(model)
    return model(**{key: value for key, value in data.items() if key in valid_columns})


def _entity_label(item: Any) -> str:
    external_id = getattr(item, "external_id", None)
    name = getattr(item, "name", None) or getattr(item, "title", None) or str(getattr(item, "id", ""))
    return f"{external_id} - {name}" if external_id else name


def _entity_summary(item: Any) -> EntitySummary:
    return EntitySummary(
        id=item.id,
        external_id=getattr(item, "external_id", None),
        name=getattr(item, "name", None),
        title=getattr(item, "title", None),
        description=getattr(item, "description", None),
        status=getattr(item, "status", None),
        priority=getattr(item, "priority", None),
        progress_percent=getattr(item, "progress_percent", None),
        owner_name=getattr(item, "owner_name", None) or getattr(item, "primary_owner", None),
        start_date=getattr(item, "start_date", None),
        target_date=(
            getattr(item, "target_completion_date", None)
            or getattr(item, "target_end_date", None)
        ),
        revised_date=(
            getattr(item, "revised_completion_date", None)
            or getattr(item, "revised_end_date", None)
        ),
        actual_date=(
            getattr(item, "actual_completion_date", None)
            or getattr(item, "actual_end_date", None)
        ),
        created_at=getattr(item, "created_at", None),
        updated_at=getattr(item, "updated_at", None),
    )


def _breadcrumb(*items: tuple[str, Any]) -> list[BreadcrumbItem]:
    return [
        BreadcrumbItem(
            entity_type=entity_type,
            entity_id=item.id,
            label=_entity_label(item),
        )
        for entity_type, item in items
    ]


def _get_or_404(db: Session, model: Type[Any], entity_id: uuid.UUID, label: str) -> Any:
    item = db.get(model, entity_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"{label} not found")
    return item


def _get_hierarchy_for_task(db: Session, task_id: uuid.UUID) -> tuple[Engagement, Workstream, Deliverable, Task]:
    task = _get_or_404(db, Task, task_id, "Task")
    deliverable = _get_or_404(db, Deliverable, task.deliverable_id, "Deliverable")
    workstream = _get_or_404(db, Workstream, deliverable.workstream_id, "Workstream")
    engagement = _get_or_404(db, Engagement, workstream.engagement_id, "Engagement")
    return engagement, workstream, deliverable, task


def _get_hierarchy_for_subtask(db: Session, subtask_id: uuid.UUID) -> tuple[Engagement, Workstream, Deliverable, Task, Subtask]:
    subtask = _get_or_404(db, Subtask, subtask_id, "Sub-task")
    engagement, workstream, deliverable, task = _get_hierarchy_for_task(db, subtask.task_id)
    return engagement, workstream, deliverable, task, subtask


def _validate_scope(db: Session, scope_type: str, scope_id: uuid.UUID) -> None:
    if scope_type == "task":
        _get_or_404(db, Task, scope_id, "Task")
        return
    if scope_type == "subtask":
        _get_or_404(db, Subtask, scope_id, "Sub-task")
        return
    raise HTTPException(status_code=400, detail="scope_type must be task or subtask")


def _count_model_for_scope(db: Session, model: Type[Any], scope_type: str, scope_id: uuid.UUID) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(model)
            .where(model.scope_type == scope_type, model.scope_id == scope_id)
        )
        or 0
    )


def _count_reminders_for_scope(db: Session, scope_type: str, scope_id: uuid.UUID) -> int:
    parent_type = "task" if scope_type == "task" else "subtask"
    return int(
        db.scalar(
            select(func.count())
            .select_from(Reminder)
            .where(
                Reminder.parent_type == parent_type,
                Reminder.parent_id == scope_id,
                Reminder.is_active.is_(True),
            )
        )
        or 0
    )


def _record_counts(db: Session, scope_type: str, scope_id: uuid.UUID) -> WorkspaceRecordCounts:
    return WorkspaceRecordCounts(
        data_collections=_count_model_for_scope(db, UiWorkspaceDataCollection, scope_type, scope_id),
        questions=_count_model_for_scope(db, UiWorkspaceQuestion, scope_type, scope_id),
        findings=_count_model_for_scope(db, UiWorkspaceFinding, scope_type, scope_id),
        analysis=_count_model_for_scope(db, UiWorkspaceAnalysis, scope_type, scope_id),
        evidence=_count_model_for_scope(db, UiWorkspaceEvidence, scope_type, scope_id),
        files=_count_model_for_scope(db, UiWorkspaceFile, scope_type, scope_id),
        recommendations=_count_model_for_scope(db, UiWorkspaceRecommendation, scope_type, scope_id),
        reminders=_count_reminders_for_scope(db, scope_type, scope_id),
    )


def _workspace_records(db: Session, scope_type: str, scope_id: uuid.UUID) -> WorkspaceFullRecords:
    _validate_scope(db, scope_type, scope_id)
    return WorkspaceFullRecords(
        data_collections=list(
            db.scalars(
                select(UiWorkspaceDataCollection)
                .where(UiWorkspaceDataCollection.scope_type == scope_type, UiWorkspaceDataCollection.scope_id == scope_id)
                .order_by(UiWorkspaceDataCollection.created_at.desc())
            ).all()
        ),
        questions=list(
            db.scalars(
                select(UiWorkspaceQuestion)
                .where(UiWorkspaceQuestion.scope_type == scope_type, UiWorkspaceQuestion.scope_id == scope_id)
                .order_by(UiWorkspaceQuestion.created_at.desc())
            ).all()
        ),
        findings=list(
            db.scalars(
                select(UiWorkspaceFinding)
                .where(UiWorkspaceFinding.scope_type == scope_type, UiWorkspaceFinding.scope_id == scope_id)
                .order_by(UiWorkspaceFinding.created_at.desc())
            ).all()
        ),
        analysis=list(
            db.scalars(
                select(UiWorkspaceAnalysis)
                .where(UiWorkspaceAnalysis.scope_type == scope_type, UiWorkspaceAnalysis.scope_id == scope_id)
                .order_by(UiWorkspaceAnalysis.created_at.desc())
            ).all()
        ),
        evidence=list(
            db.scalars(
                select(UiWorkspaceEvidence)
                .where(UiWorkspaceEvidence.scope_type == scope_type, UiWorkspaceEvidence.scope_id == scope_id)
                .order_by(UiWorkspaceEvidence.created_at.desc())
            ).all()
        ),
        files=list(
            db.scalars(
                select(UiWorkspaceFile)
                .where(UiWorkspaceFile.scope_type == scope_type, UiWorkspaceFile.scope_id == scope_id)
                .order_by(UiWorkspaceFile.uploaded_at.desc())
            ).all()
        ),
        recommendations=list(
            db.scalars(
                select(UiWorkspaceRecommendation)
                .where(UiWorkspaceRecommendation.scope_type == scope_type, UiWorkspaceRecommendation.scope_id == scope_id)
                .order_by(UiWorkspaceRecommendation.created_at.desc())
            ).all()
        ),
    )


def _delete_file_record(item: UiWorkspaceFile) -> None:
    try:
        path = Path(item.storage_path)
        if path.exists() and path.is_file():
            path.unlink()
    except Exception:
        pass


def _delete_workspace_records_for_scope(db: Session, scope_type: str, scope_id: uuid.UUID) -> None:
    for model in [
        UiWorkspaceDataCollection,
        UiWorkspaceQuestion,
        UiWorkspaceFinding,
        UiWorkspaceAnalysis,
        UiWorkspaceEvidence,
        UiWorkspaceRecommendation,
    ]:
        rows = list(
            db.scalars(
                select(model).where(model.scope_type == scope_type, model.scope_id == scope_id)
            ).all()
        )
        for row in rows:
            db.delete(row)

    files = list(
        db.scalars(
            select(UiWorkspaceFile).where(UiWorkspaceFile.scope_type == scope_type, UiWorkspaceFile.scope_id == scope_id)
        ).all()
    )
    for file_item in files:
        _delete_file_record(file_item)
        db.delete(file_item)

    parent_type = "task" if scope_type == "task" else "subtask"
    reminders = list(
        db.scalars(
            select(Reminder).where(Reminder.parent_type == parent_type, Reminder.parent_id == scope_id)
        ).all()
    )
    for reminder in reminders:
        db.delete(reminder)


def _delete_workspace_records_linked_to_entity(db: Session, entity_type: str, entity_id: uuid.UUID) -> None:
    files = list(
        db.scalars(
            select(UiWorkspaceFile).where(
                UiWorkspaceFile.linked_entity_type == entity_type,
                UiWorkspaceFile.linked_entity_id == entity_id,
            )
        ).all()
    )
    for file_item in files:
        _delete_file_record(file_item)
        db.delete(file_item)


def _delete_legacy_subtask_records(db: Session, subtask_id: uuid.UUID) -> None:
    data_points = list(db.scalars(select(DataPoint).where(DataPoint.subtask_id == subtask_id)).all())
    for item in data_points:
        _delete_workspace_records_linked_to_entity(db, "data_collection", item.id)
        reminders = list(
            db.scalars(
                select(Reminder).where(Reminder.parent_type == "data_point", Reminder.parent_id == item.id)
            ).all()
        )
        for reminder in reminders:
            db.delete(reminder)
        db.delete(item)

    questions = list(db.scalars(select(StakeholderQuestion).where(StakeholderQuestion.subtask_id == subtask_id)).all())
    for item in questions:
        _delete_workspace_records_linked_to_entity(db, "question", item.id)
        reminders = list(
            db.scalars(
                select(Reminder).where(Reminder.parent_type == "stakeholder_question", Reminder.parent_id == item.id)
            ).all()
        )
        for reminder in reminders:
            db.delete(reminder)
        db.delete(item)


def _delete_subtask_cascade(db: Session, subtask: Subtask) -> None:
    _delete_workspace_records_for_scope(db, "subtask", subtask.id)
    _delete_legacy_subtask_records(db, subtask.id)
    db.delete(subtask)


def _delete_task_cascade(db: Session, task: Task) -> None:
    subtasks = list(db.scalars(select(Subtask).where(Subtask.task_id == task.id)).all())
    for subtask in subtasks:
        _delete_subtask_cascade(db, subtask)

    _delete_workspace_records_for_scope(db, "task", task.id)

    reminders = list(
        db.scalars(select(Reminder).where(Reminder.parent_type == "task", Reminder.parent_id == task.id)).all()
    )
    for reminder in reminders:
        db.delete(reminder)

    db.delete(task)


def _delete_deliverable_cascade(db: Session, deliverable: Deliverable) -> None:
    tasks = list(db.scalars(select(Task).where(Task.deliverable_id == deliverable.id)).all())
    for task in tasks:
        _delete_task_cascade(db, task)

    reminders = list(
        db.scalars(
            select(Reminder).where(Reminder.parent_type == "deliverable", Reminder.parent_id == deliverable.id)
        ).all()
    )
    for reminder in reminders:
        db.delete(reminder)

    db.delete(deliverable)


def _delete_workstream_cascade(db: Session, workstream: Workstream) -> None:
    deliverables = list(db.scalars(select(Deliverable).where(Deliverable.workstream_id == workstream.id)).all())
    for deliverable in deliverables:
        _delete_deliverable_cascade(db, deliverable)

    db.delete(workstream)


def _delete_engagement_cascade(db: Session, engagement: Engagement) -> None:
    workstreams = list(db.scalars(select(Workstream).where(Workstream.engagement_id == engagement.id)).all())
    for workstream in workstreams:
        _delete_workstream_cascade(db, workstream)

    db.delete(engagement)


def _recalculate_progress_soft(db: Session) -> None:
    # Keep this MVP 18 router independent from main.py helpers.
    # Existing APIs still maintain detailed rollups. This recalculates basic rollups after UI deletes.
    for task in list(db.scalars(select(Task)).all()):
        subtasks = list(db.scalars(select(Subtask).where(Subtask.task_id == task.id)).all())
        if hasattr(task, "progress_percent"):
            if subtasks:
                completed = sum(1 for item in subtasks if _normalize_status(getattr(item, "status", None)) == "completed")
                task.progress_percent = Decimal(completed * 100) / Decimal(len(subtasks))
            else:
                task.progress_percent = Decimal("0.00")

    for deliverable in list(db.scalars(select(Deliverable)).all()):
        tasks = list(db.scalars(select(Task).where(Task.deliverable_id == deliverable.id)).all())
        if hasattr(deliverable, "progress_percent"):
            if tasks:
                completed = sum(1 for item in tasks if _normalize_status(getattr(item, "status", None)) == "completed")
                deliverable.progress_percent = Decimal(completed * 100) / Decimal(len(tasks))
            else:
                deliverable.progress_percent = Decimal("0.00")

    for workstream in list(db.scalars(select(Workstream)).all()):
        deliverables = list(db.scalars(select(Deliverable).where(Deliverable.workstream_id == workstream.id)).all())
        if hasattr(workstream, "progress_percent"):
            if deliverables:
                completed = sum(1 for item in deliverables if _normalize_status(getattr(item, "status", None)) == "completed")
                workstream.progress_percent = Decimal(completed * 100) / Decimal(len(deliverables))
            else:
                workstream.progress_percent = Decimal("0.00")

    for engagement in list(db.scalars(select(Engagement)).all()):
        workstreams = list(db.scalars(select(Workstream).where(Workstream.engagement_id == engagement.id)).all())
        if hasattr(engagement, "progress_percent"):
            if workstreams:
                completed = sum(1 for item in workstreams if _normalize_status(getattr(item, "status", None)) == "completed")
                engagement.progress_percent = Decimal(completed * 100) / Decimal(len(workstreams))
            else:
                engagement.progress_percent = Decimal("0.00")


def _run_llm(prompt: str, fallback: str, workflow_name: str) -> str:
    settings = get_settings()

    if not getattr(settings, "openai_api_key", None):
        return fallback

    try:
        from agents import Agent, Runner, trace

        agent = Agent(
            name="ASM Engagement Cockpit Workspace Advisor",
            instructions=(
                "You are an expert ASM consulting engagement advisor. "
                "Return clear, practical, executive-ready consulting text. "
                "Do not invent facts. If data is missing, identify data gaps and questions to ask."
            ),
            model=getattr(settings, "openai_model", "gpt-4.1-mini"),
        )

        with trace(workflow_name=workflow_name):
            result = Runner.run_sync(agent, prompt)

        return str(result.final_output).strip()
    except Exception as exc:
        return f"{fallback}\n\nLLM fallback note: {type(exc).__name__}: {exc}"


def _recommendation_context(db: Session, scope_type: str, scope_id: uuid.UUID) -> dict[str, Any]:
    records = _workspace_records(db, scope_type, scope_id)

    if scope_type == "task":
        engagement, workstream, deliverable, task = _get_hierarchy_for_task(db, scope_id)
        scope_entity = task
        subtask = None
    else:
        engagement, workstream, deliverable, task, subtask = _get_hierarchy_for_subtask(db, scope_id)
        scope_entity = subtask

    return {
        "scope_type": scope_type,
        "scope_id": str(scope_id),
        "engagement": _entity_summary(engagement).model_dump(mode="json"),
        "workstream": _entity_summary(workstream).model_dump(mode="json"),
        "deliverable": _entity_summary(deliverable).model_dump(mode="json"),
        "task": _entity_summary(task).model_dump(mode="json"),
        "subtask": _entity_summary(subtask).model_dump(mode="json") if subtask is not None else None,
        "scope_entity": _entity_summary(scope_entity).model_dump(mode="json"),
        "data_collections": [item.model_dump(mode="json") for item in records.data_collections],
        "questions": [item.model_dump(mode="json") for item in records.questions],
        "findings": [item.model_dump(mode="json") for item in records.findings],
        "analysis": [item.model_dump(mode="json") for item in records.analysis],
        "evidence": [item.model_dump(mode="json") for item in records.evidence],
        "files": [
            {
                "original_filename": item.original_filename,
                "upload_category": item.upload_category,
                "description": item.description,
                "linked_entity_type": item.linked_entity_type,
                "uploaded_at": item.uploaded_at.isoformat() if item.uploaded_at else None,
            }
            for item in records.files
        ],
        "recommendations": [item.model_dump(mode="json") for item in records.recommendations],
    }


@router.get("/dashboard-status-summary", response_model=DashboardStatusSummary)
def get_dashboard_status_summary(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[dict[str, Any], Depends(require_authenticated_request)],
) -> DashboardStatusSummary:
    return DashboardStatusSummary(
        engagements=_status_bucket(db, Engagement),
        workstreams=_status_bucket(db, Workstream),
        deliverables=_status_bucket(db, Deliverable),
        tasks=_status_bucket(db, Task),
        subtasks=_status_bucket(db, Subtask),
    )


@router.get("/reminder-indicator", response_model=ReminderIndicator)
def get_reminder_indicator(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[dict[str, Any], Depends(require_authenticated_request)],
) -> ReminderIndicator:
    today = date.today()
    two_days = today + timedelta(days=2)

    active = list(
        db.scalars(
            select(Reminder).where(
                Reminder.is_active.is_(True),
                (Reminder.snoozed_until.is_(None)) | (Reminder.snoozed_until <= today),
            )
        ).all()
    )

    overdue = sum(1 for item in active if item.effective_due_date is not None and item.effective_due_date < today)
    due_soon = sum(1 for item in active if item.effective_due_date is not None and today <= item.effective_due_date <= two_days)
    other = max(len(active) - overdue - due_soon, 0)

    if overdue > 0:
        color = "red"
        label = f"{overdue} overdue item{'s' if overdue != 1 else ''}"
    elif due_soon > 0:
        color = "amber"
        label = f"{due_soon} item{'s' if due_soon != 1 else ''} due within 2 days"
    elif len(active) > 0:
        color = "green"
        label = f"{len(active)} active reminder{'s' if len(active) != 1 else ''}"
    else:
        color = "gray"
        label = "No active reminders"

    return ReminderIndicator(
        total_active=len(active),
        overdue=overdue,
        due_within_2_days=due_soon,
        other_active=other,
        color=color,
        label=label,
    )




@router.get("/my-work")
def get_my_work(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[dict[str, Any], Depends(require_authenticated_request)],
    owner_name: str = Query(default=DEFAULT_MY_WORK_OWNER),
) -> dict[str, Any]:
    primary_workstreams = _owned_items(db, Workstream, "workstreams", "owner_name", owner_name)
    secondary_workstreams = [
        item
        for item in _owned_items(db, Workstream, "workstreams", "secondary_owner_name", owner_name)
        if item.id not in {primary_item.id for primary_item in primary_workstreams}
    ]

    primary_deliverables = _owned_items(db, Deliverable, "deliverables", "owner_name", owner_name)
    secondary_deliverables = [
        item
        for item in _owned_items(db, Deliverable, "deliverables", "secondary_owner_name", owner_name)
        if item.id not in {primary_item.id for primary_item in primary_deliverables}
    ]

    primary_tasks = _owned_items(db, Task, "tasks", "owner_name", owner_name)
    secondary_tasks = [
        item
        for item in _owned_items(db, Task, "tasks", "secondary_owner_name", owner_name)
        if item.id not in {primary_item.id for primary_item in primary_tasks}
    ]

    return {
        "owner_name": owner_name,
        "primary_workstreams": [_entity_summary_with_ownership(db, "workstreams", item) for item in primary_workstreams],
        "secondary_workstreams": [_entity_summary_with_ownership(db, "workstreams", item) for item in secondary_workstreams],
        "primary_deliverables": [_entity_summary_with_ownership(db, "deliverables", item) for item in primary_deliverables],
        "secondary_deliverables": [_entity_summary_with_ownership(db, "deliverables", item) for item in secondary_deliverables],
        "primary_tasks": [_entity_summary_with_ownership(db, "tasks", item) for item in primary_tasks],
        "secondary_tasks": [_entity_summary_with_ownership(db, "tasks", item) for item in secondary_tasks],
        "counts": {
            "primary_workstreams": len(primary_workstreams),
            "secondary_workstreams": len(secondary_workstreams),
            "primary_deliverables": len(primary_deliverables),
            "secondary_deliverables": len(secondary_deliverables),
            "primary_tasks": len(primary_tasks),
            "secondary_tasks": len(secondary_tasks),
        },
    }



def _my_work_filtered_items(db: Session, table_name: str, items: list[Any], owner_name: str = DEFAULT_MY_WORK_OWNER) -> list[Any]:
    filtered = [item for item in items if _ownership_rank(db, table_name, item, owner_name) in {0, 1}]
    return _sort_for_my_work_priority(db, table_name, filtered, owner_name)


@router.get("/my-work/workstreams/{workstream_id}/workspace")
def get_my_work_workstream_workspace(
    workstream_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[dict[str, Any], Depends(require_authenticated_request)],
    owner_name: str = Query(default=DEFAULT_MY_WORK_OWNER),
) -> dict[str, Any]:
    workstream = _get_or_404(db, Workstream, workstream_id, "Workstream")
    engagement = _get_or_404(db, Engagement, workstream.engagement_id, "Engagement")
    deliverables = _my_work_filtered_items(
        db,
        "deliverables",
        list(db.scalars(select(Deliverable).where(Deliverable.workstream_id == workstream.id)).all()),
        owner_name,
    )

    return {
        "owner_name": owner_name,
        "engagement": _entity_summary_with_ownership(db, "engagements", engagement),
        "workstream": _entity_summary_with_ownership(db, "workstreams", workstream),
        "deliverables": [_entity_summary_with_ownership(db, "deliverables", item) for item in deliverables],
        "breadcrumb": [
            {"entity_type": "my_work", "entity_id": str(workstream.id), "label": "My Work"},
            {"entity_type": "workstream", "entity_id": str(workstream.id), "label": _entity_label(workstream)},
        ],
    }


@router.get("/my-work/deliverables/{deliverable_id}/workspace")
def get_my_work_deliverable_workspace(
    deliverable_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[dict[str, Any], Depends(require_authenticated_request)],
    owner_name: str = Query(default=DEFAULT_MY_WORK_OWNER),
) -> dict[str, Any]:
    deliverable = _get_or_404(db, Deliverable, deliverable_id, "Deliverable")
    workstream = _get_or_404(db, Workstream, deliverable.workstream_id, "Workstream")
    engagement = _get_or_404(db, Engagement, workstream.engagement_id, "Engagement")
    tasks = _my_work_filtered_items(
        db,
        "tasks",
        list(db.scalars(select(Task).where(Task.deliverable_id == deliverable.id)).all()),
        owner_name,
    )

    return {
        "owner_name": owner_name,
        "engagement": _entity_summary_with_ownership(db, "engagements", engagement),
        "workstream": _entity_summary_with_ownership(db, "workstreams", workstream),
        "deliverable": _entity_summary_with_ownership(db, "deliverables", deliverable),
        "tasks": [_entity_summary_with_ownership(db, "tasks", item) for item in tasks],
        "breadcrumb": [
            {"entity_type": "my_work", "entity_id": str(workstream.id), "label": "My Work"},
            {"entity_type": "workstream", "entity_id": str(workstream.id), "label": _entity_label(workstream)},
            {"entity_type": "deliverable", "entity_id": str(deliverable.id), "label": _entity_label(deliverable)},
        ],
    }


@router.get("/my-work/tasks/{task_id}/workspace")
def get_my_work_task_workspace(
    task_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[dict[str, Any], Depends(require_authenticated_request)],
    owner_name: str = Query(default=DEFAULT_MY_WORK_OWNER),
) -> dict[str, Any]:
    engagement, workstream, deliverable, task = _get_hierarchy_for_task(db, task_id)
    subtasks = _sort_for_my_work_priority(
        db,
        "subtasks",
        list(db.scalars(select(Subtask).where(Subtask.task_id == task.id)).all()),
        owner_name,
    )

    return {
        "owner_name": owner_name,
        "engagement": _entity_summary_with_ownership(db, "engagements", engagement),
        "workstream": _entity_summary_with_ownership(db, "workstreams", workstream),
        "deliverable": _entity_summary_with_ownership(db, "deliverables", deliverable),
        "task": _entity_summary_with_ownership(db, "tasks", task),
        "subtasks": [_entity_summary_with_ownership(db, "subtasks", item) for item in subtasks],
        "breadcrumb": [
            {"entity_type": "my_work", "entity_id": str(workstream.id), "label": "My Work"},
            {"entity_type": "workstream", "entity_id": str(workstream.id), "label": _entity_label(workstream)},
            {"entity_type": "deliverable", "entity_id": str(deliverable.id), "label": _entity_label(deliverable)},
            {"entity_type": "task", "entity_id": str(task.id), "label": _entity_label(task)},
        ],
        "record_counts": _record_counts(db, "task", task.id).model_dump(),
    }


@router.get("/my-work/subtasks/{subtask_id}/workspace")
def get_my_work_subtask_workspace(
    subtask_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[dict[str, Any], Depends(require_authenticated_request)],
    owner_name: str = Query(default=DEFAULT_MY_WORK_OWNER),
) -> dict[str, Any]:
    engagement, workstream, deliverable, task, subtask = _get_hierarchy_for_subtask(db, subtask_id)

    return {
        "owner_name": owner_name,
        "engagement": _entity_summary_with_ownership(db, "engagements", engagement),
        "workstream": _entity_summary_with_ownership(db, "workstreams", workstream),
        "deliverable": _entity_summary_with_ownership(db, "deliverables", deliverable),
        "task": _entity_summary_with_ownership(db, "tasks", task),
        "subtask": _entity_summary_with_ownership(db, "subtasks", subtask),
        "breadcrumb": [
            {"entity_type": "my_work", "entity_id": str(workstream.id), "label": "My Work"},
            {"entity_type": "workstream", "entity_id": str(workstream.id), "label": _entity_label(workstream)},
            {"entity_type": "deliverable", "entity_id": str(deliverable.id), "label": _entity_label(deliverable)},
            {"entity_type": "task", "entity_id": str(task.id), "label": _entity_label(task)},
            {"entity_type": "subtask", "entity_id": str(subtask.id), "label": _entity_label(subtask)},
        ],
        "record_counts": _record_counts(db, "subtask", subtask.id).model_dump(),
    }


@router.get("/engagements", response_model=list[EntitySummary])
def list_ui_engagements(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[dict[str, Any], Depends(require_authenticated_request)],
) -> list[EntitySummary]:
    return [_entity_summary(item) for item in db.scalars(select(Engagement).order_by(Engagement.created_at.desc())).all()]


@router.post("/engagements", response_model=EntitySummary)
def create_ui_engagement(
    payload: EngagementCreateUi,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[dict[str, Any], Depends(require_authenticated_request)],
) -> EntitySummary:
    item = _create_model(Engagement, payload)
    db.add(item)
    db.commit()
    db.refresh(item)
    return _entity_summary(item)


@router.put("/engagements/{engagement_id}", response_model=EntitySummary)
def update_ui_engagement(
    engagement_id: uuid.UUID,
    payload: EngagementUpdateUi,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[dict[str, Any], Depends(require_authenticated_request)],
) -> EntitySummary:
    item = _get_or_404(db, Engagement, engagement_id, "Engagement")
    _apply_payload(item, payload)
    db.commit()
    db.refresh(item)
    return _entity_summary(item)


@router.delete("/engagements/{engagement_id}", response_model=DeleteResponse)
def delete_ui_engagement(
    engagement_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[dict[str, Any], Depends(require_authenticated_request)],
) -> DeleteResponse:
    item = _get_or_404(db, Engagement, engagement_id, "Engagement")
    _delete_engagement_cascade(db, item)
    db.commit()
    return DeleteResponse(deleted=True, entity_type="engagement", entity_id=engagement_id, message="Engagement and all related child records were deleted.")


@router.get("/engagements/{engagement_id}/workspace", response_model=EngagementWorkspace)
def get_engagement_workspace(
    engagement_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[dict[str, Any], Depends(require_authenticated_request)],
) -> EngagementWorkspace:
    engagement = _get_or_404(db, Engagement, engagement_id, "Engagement")
    workstreams = sort_hierarchy_items(
        list(db.scalars(select(Workstream).where(Workstream.engagement_id == engagement.id)).all())
    )
    return EngagementWorkspace(
        engagement=_entity_summary(engagement),
        workstreams=[_entity_summary_with_ownership(db, "workstreams", item) for item in workstreams],
        breadcrumb=_breadcrumb(("engagement", engagement)),
    )


@router.post("/engagements/{engagement_id}/workstreams", response_model=EntitySummary)
def create_ui_workstream(
    engagement_id: uuid.UUID,
    payload: WorkstreamCreateUi,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[dict[str, Any], Depends(require_authenticated_request)],
) -> EntitySummary:
    _get_or_404(db, Engagement, engagement_id, "Engagement")
    item = _create_model(Workstream, payload, engagement_id=engagement_id)
    db.add(item)
    db.commit()
    db.refresh(item)
    return _entity_summary(item)


@router.put("/workstreams/{workstream_id}", response_model=EntitySummary)
def update_ui_workstream(
    workstream_id: uuid.UUID,
    payload: WorkstreamUpdateUi,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[dict[str, Any], Depends(require_authenticated_request)],
) -> EntitySummary:
    item = _get_or_404(db, Workstream, workstream_id, "Workstream")
    _apply_payload(item, payload)
    _recalculate_progress_soft(db)
    db.commit()
    db.refresh(item)
    return _entity_summary(item)


@router.delete("/workstreams/{workstream_id}", response_model=DeleteResponse)
def delete_ui_workstream(
    workstream_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[dict[str, Any], Depends(require_authenticated_request)],
) -> DeleteResponse:
    item = _get_or_404(db, Workstream, workstream_id, "Workstream")
    _delete_workstream_cascade(db, item)
    _recalculate_progress_soft(db)
    db.commit()
    return DeleteResponse(deleted=True, entity_type="workstream", entity_id=workstream_id, message="Workstream and all related child records were deleted.")


@router.get("/workstreams/{workstream_id}/workspace", response_model=WorkstreamWorkspace)
def get_workstream_workspace(
    workstream_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[dict[str, Any], Depends(require_authenticated_request)],
) -> WorkstreamWorkspace:
    workstream = _get_or_404(db, Workstream, workstream_id, "Workstream")
    engagement = _get_or_404(db, Engagement, workstream.engagement_id, "Engagement")
    deliverables = sort_hierarchy_items(
        list(db.scalars(select(Deliverable).where(Deliverable.workstream_id == workstream.id)).all())
    )
    return WorkstreamWorkspace(
        engagement=_entity_summary(engagement),
        workstream=_entity_summary_with_ownership(db, "workstreams", workstream),
        deliverables=[_entity_summary_with_ownership(db, "deliverables", item) for item in deliverables],
        breadcrumb=_breadcrumb(("engagement", engagement), ("workstream", workstream)),
    )


@router.post("/workstreams/{workstream_id}/deliverables", response_model=EntitySummary)
def create_ui_deliverable(
    workstream_id: uuid.UUID,
    payload: DeliverableCreateUi,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[dict[str, Any], Depends(require_authenticated_request)],
) -> EntitySummary:
    _get_or_404(db, Workstream, workstream_id, "Workstream")
    item = _create_model(Deliverable, payload, workstream_id=workstream_id)
    db.add(item)
    _recalculate_progress_soft(db)
    db.commit()
    db.refresh(item)
    return _entity_summary(item)


@router.put("/deliverables/{deliverable_id}", response_model=EntitySummary)
def update_ui_deliverable(
    deliverable_id: uuid.UUID,
    payload: DeliverableUpdateUi,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[dict[str, Any], Depends(require_authenticated_request)],
) -> EntitySummary:
    item = _get_or_404(db, Deliverable, deliverable_id, "Deliverable")
    _apply_payload(item, payload)
    _recalculate_progress_soft(db)
    db.commit()
    db.refresh(item)
    return _entity_summary(item)


@router.delete("/deliverables/{deliverable_id}", response_model=DeleteResponse)
def delete_ui_deliverable(
    deliverable_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[dict[str, Any], Depends(require_authenticated_request)],
) -> DeleteResponse:
    item = _get_or_404(db, Deliverable, deliverable_id, "Deliverable")
    _delete_deliverable_cascade(db, item)
    _recalculate_progress_soft(db)
    db.commit()
    return DeleteResponse(deleted=True, entity_type="deliverable", entity_id=deliverable_id, message="Deliverable and all related child records were deleted.")


@router.get("/deliverables/{deliverable_id}/workspace", response_model=DeliverableWorkspace)
def get_deliverable_workspace(
    deliverable_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[dict[str, Any], Depends(require_authenticated_request)],
) -> DeliverableWorkspace:
    deliverable = _get_or_404(db, Deliverable, deliverable_id, "Deliverable")
    workstream = _get_or_404(db, Workstream, deliverable.workstream_id, "Workstream")
    engagement = _get_or_404(db, Engagement, workstream.engagement_id, "Engagement")
    tasks = sort_hierarchy_items(
        list(db.scalars(select(Task).where(Task.deliverable_id == deliverable.id)).all())
    )
    return DeliverableWorkspace(
        engagement=_entity_summary(engagement),
        workstream=_entity_summary_with_ownership(db, "workstreams", workstream),
        deliverable=_entity_summary_with_ownership(db, "deliverables", deliverable),
        tasks=[_entity_summary_with_ownership(db, "tasks", item) for item in tasks],
        breadcrumb=_breadcrumb(("engagement", engagement), ("workstream", workstream), ("deliverable", deliverable)),
    )


@router.post("/deliverables/{deliverable_id}/tasks", response_model=EntitySummary)
def create_ui_task(
    deliverable_id: uuid.UUID,
    payload: TaskCreateUi,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[dict[str, Any], Depends(require_authenticated_request)],
) -> EntitySummary:
    _get_or_404(db, Deliverable, deliverable_id, "Deliverable")
    item = _create_model(Task, payload, deliverable_id=deliverable_id)
    db.add(item)
    _recalculate_progress_soft(db)
    db.commit()
    db.refresh(item)
    return _entity_summary(item)


@router.put("/tasks/{task_id}", response_model=EntitySummary)
def update_ui_task(
    task_id: uuid.UUID,
    payload: TaskUpdateUi,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[dict[str, Any], Depends(require_authenticated_request)],
) -> EntitySummary:
    item = _get_or_404(db, Task, task_id, "Task")
    _apply_payload(item, payload)
    _recalculate_progress_soft(db)
    db.commit()
    db.refresh(item)
    return _entity_summary(item)


@router.delete("/tasks/{task_id}", response_model=DeleteResponse)
def delete_ui_task(
    task_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[dict[str, Any], Depends(require_authenticated_request)],
) -> DeleteResponse:
    item = _get_or_404(db, Task, task_id, "Task")
    _delete_task_cascade(db, item)
    _recalculate_progress_soft(db)
    db.commit()
    return DeleteResponse(deleted=True, entity_type="task", entity_id=task_id, message="Task and all related child records were deleted.")


@router.get("/tasks/{task_id}/workspace", response_model=TaskWorkspace)
def get_task_workspace(
    task_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[dict[str, Any], Depends(require_authenticated_request)],
) -> TaskWorkspace:
    engagement, workstream, deliverable, task = _get_hierarchy_for_task(db, task_id)
    subtasks = sort_hierarchy_items(
        list(db.scalars(select(Subtask).where(Subtask.task_id == task.id)).all())
    )
    return TaskWorkspace(
        engagement=_entity_summary(engagement),
        workstream=_entity_summary_with_ownership(db, "workstreams", workstream),
        deliverable=_entity_summary_with_ownership(db, "deliverables", deliverable),
        task=_entity_summary_with_ownership(db, "tasks", task),
        subtasks=[_entity_summary_with_ownership(db, "subtasks", item) for item in subtasks],
        breadcrumb=_breadcrumb(("engagement", engagement), ("workstream", workstream), ("deliverable", deliverable), ("task", task)),
        record_counts=_record_counts(db, "task", task.id),
    )


@router.post("/tasks/{task_id}/subtasks", response_model=EntitySummary)
def create_ui_subtask(
    task_id: uuid.UUID,
    payload: SubtaskCreateUi,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[dict[str, Any], Depends(require_authenticated_request)],
) -> EntitySummary:
    _get_or_404(db, Task, task_id, "Task")
    item = _create_model(Subtask, payload, task_id=task_id)
    db.add(item)
    _recalculate_progress_soft(db)
    db.commit()
    db.refresh(item)
    return _entity_summary(item)


@router.put("/subtasks/{subtask_id}", response_model=EntitySummary)
def update_ui_subtask(
    subtask_id: uuid.UUID,
    payload: SubtaskUpdateUi,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[dict[str, Any], Depends(require_authenticated_request)],
) -> EntitySummary:
    item = _get_or_404(db, Subtask, subtask_id, "Sub-task")
    _apply_payload(item, payload)
    _recalculate_progress_soft(db)
    db.commit()
    db.refresh(item)
    return _entity_summary(item)


@router.delete("/subtasks/{subtask_id}", response_model=DeleteResponse)
def delete_ui_subtask(
    subtask_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[dict[str, Any], Depends(require_authenticated_request)],
) -> DeleteResponse:
    item = _get_or_404(db, Subtask, subtask_id, "Sub-task")
    _delete_subtask_cascade(db, item)
    _recalculate_progress_soft(db)
    db.commit()
    return DeleteResponse(deleted=True, entity_type="subtask", entity_id=subtask_id, message="Sub-task and all related workspace records were deleted.")


@router.get("/subtasks/{subtask_id}/workspace", response_model=SubtaskWorkspace)
def get_subtask_workspace(
    subtask_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[dict[str, Any], Depends(require_authenticated_request)],
) -> SubtaskWorkspace:
    engagement, workstream, deliverable, task, subtask = _get_hierarchy_for_subtask(db, subtask_id)
    return SubtaskWorkspace(
        engagement=_entity_summary(engagement),
        workstream=_entity_summary_with_ownership(db, "workstreams", workstream),
        deliverable=_entity_summary_with_ownership(db, "deliverables", deliverable),
        task=_entity_summary_with_ownership(db, "tasks", task),
        subtask=_entity_summary_with_ownership(db, "subtasks", subtask),
        breadcrumb=_breadcrumb(("engagement", engagement), ("workstream", workstream), ("deliverable", deliverable), ("task", task), ("subtask", subtask)),
        record_counts=_record_counts(db, "subtask", subtask.id),
    )


@router.get("/workspace/{scope_type}/{scope_id}/records", response_model=WorkspaceFullRecords)
def get_workspace_records(
    scope_type: ScopeType,
    scope_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[dict[str, Any], Depends(require_authenticated_request)],
) -> WorkspaceFullRecords:
    return _workspace_records(db, scope_type, scope_id)


@router.post("/workspace/{scope_type}/{scope_id}/data-collections", response_model=WorkspaceDataCollectionRead)
def create_workspace_data_collection(scope_type: ScopeType, scope_id: uuid.UUID, payload: WorkspaceDataCollectionCreate, db: Annotated[Session, Depends(get_db)], _: Annotated[dict[str, Any], Depends(require_authenticated_request)]) -> UiWorkspaceDataCollection:
    _validate_scope(db, scope_type, scope_id)
    item = UiWorkspaceDataCollection(**payload.model_dump(), scope_type=scope_type, scope_id=scope_id)
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.put("/workspace/data-collections/{data_collection_id}", response_model=WorkspaceDataCollectionRead)
def update_workspace_data_collection(data_collection_id: uuid.UUID, payload: WorkspaceDataCollectionUpdate, db: Annotated[Session, Depends(get_db)], _: Annotated[dict[str, Any], Depends(require_authenticated_request)]) -> UiWorkspaceDataCollection:
    item = _get_or_404(db, UiWorkspaceDataCollection, data_collection_id, "Data collection")
    _apply_payload(item, payload)
    db.commit()
    db.refresh(item)
    return item


@router.delete("/workspace/data-collections/{data_collection_id}", response_model=DeleteResponse)
def delete_workspace_data_collection(data_collection_id: uuid.UUID, db: Annotated[Session, Depends(get_db)], _: Annotated[dict[str, Any], Depends(require_authenticated_request)]) -> DeleteResponse:
    item = _get_or_404(db, UiWorkspaceDataCollection, data_collection_id, "Data collection")
    _delete_workspace_records_linked_to_entity(db, "data_collection", item.id)
    db.delete(item)
    db.commit()
    return DeleteResponse(deleted=True, entity_type="data_collection", entity_id=data_collection_id, message="Data collection was deleted.")


@router.post("/workspace/{scope_type}/{scope_id}/questions", response_model=WorkspaceQuestionRead)
def create_workspace_question(scope_type: ScopeType, scope_id: uuid.UUID, payload: WorkspaceQuestionCreate, db: Annotated[Session, Depends(get_db)], _: Annotated[dict[str, Any], Depends(require_authenticated_request)]) -> UiWorkspaceQuestion:
    _validate_scope(db, scope_type, scope_id)
    item = UiWorkspaceQuestion(**payload.model_dump(), scope_type=scope_type, scope_id=scope_id)
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.put("/workspace/questions/{question_id}", response_model=WorkspaceQuestionRead)
def update_workspace_question(question_id: uuid.UUID, payload: WorkspaceQuestionUpdate, db: Annotated[Session, Depends(get_db)], _: Annotated[dict[str, Any], Depends(require_authenticated_request)]) -> UiWorkspaceQuestion:
    item = _get_or_404(db, UiWorkspaceQuestion, question_id, "Question")
    _apply_payload(item, payload)
    db.commit()
    db.refresh(item)
    return item


@router.delete("/workspace/questions/{question_id}", response_model=DeleteResponse)
def delete_workspace_question(question_id: uuid.UUID, db: Annotated[Session, Depends(get_db)], _: Annotated[dict[str, Any], Depends(require_authenticated_request)]) -> DeleteResponse:
    item = _get_or_404(db, UiWorkspaceQuestion, question_id, "Question")
    _delete_workspace_records_linked_to_entity(db, "question", item.id)
    db.delete(item)
    db.commit()
    return DeleteResponse(deleted=True, entity_type="question", entity_id=question_id, message="Question was deleted.")


@router.post("/workspace/{scope_type}/{scope_id}/findings", response_model=WorkspaceFindingRead)
def create_workspace_finding(scope_type: ScopeType, scope_id: uuid.UUID, payload: WorkspaceFindingCreate, db: Annotated[Session, Depends(get_db)], _: Annotated[dict[str, Any], Depends(require_authenticated_request)]) -> UiWorkspaceFinding:
    _validate_scope(db, scope_type, scope_id)
    item = UiWorkspaceFinding(**payload.model_dump(), scope_type=scope_type, scope_id=scope_id)
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.put("/workspace/findings/{finding_id}", response_model=WorkspaceFindingRead)
def update_workspace_finding(finding_id: uuid.UUID, payload: WorkspaceFindingUpdate, db: Annotated[Session, Depends(get_db)], _: Annotated[dict[str, Any], Depends(require_authenticated_request)]) -> UiWorkspaceFinding:
    item = _get_or_404(db, UiWorkspaceFinding, finding_id, "Finding")
    _apply_payload(item, payload)
    db.commit()
    db.refresh(item)
    return item


@router.delete("/workspace/findings/{finding_id}", response_model=DeleteResponse)
def delete_workspace_finding(finding_id: uuid.UUID, db: Annotated[Session, Depends(get_db)], _: Annotated[dict[str, Any], Depends(require_authenticated_request)]) -> DeleteResponse:
    item = _get_or_404(db, UiWorkspaceFinding, finding_id, "Finding")
    _delete_workspace_records_linked_to_entity(db, "finding", item.id)
    db.delete(item)
    db.commit()
    return DeleteResponse(deleted=True, entity_type="finding", entity_id=finding_id, message="Finding was deleted.")


@router.post("/workspace/{scope_type}/{scope_id}/analysis", response_model=WorkspaceAnalysisRead)
def create_workspace_analysis(scope_type: ScopeType, scope_id: uuid.UUID, payload: WorkspaceAnalysisCreate, db: Annotated[Session, Depends(get_db)], _: Annotated[dict[str, Any], Depends(require_authenticated_request)]) -> UiWorkspaceAnalysis:
    _validate_scope(db, scope_type, scope_id)
    item = UiWorkspaceAnalysis(**payload.model_dump(), scope_type=scope_type, scope_id=scope_id)
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.put("/workspace/analysis/{analysis_id}", response_model=WorkspaceAnalysisRead)
def update_workspace_analysis(analysis_id: uuid.UUID, payload: WorkspaceAnalysisUpdate, db: Annotated[Session, Depends(get_db)], _: Annotated[dict[str, Any], Depends(require_authenticated_request)]) -> UiWorkspaceAnalysis:
    item = _get_or_404(db, UiWorkspaceAnalysis, analysis_id, "Analysis")
    _apply_payload(item, payload)
    db.commit()
    db.refresh(item)
    return item


@router.delete("/workspace/analysis/{analysis_id}", response_model=DeleteResponse)
def delete_workspace_analysis(analysis_id: uuid.UUID, db: Annotated[Session, Depends(get_db)], _: Annotated[dict[str, Any], Depends(require_authenticated_request)]) -> DeleteResponse:
    item = _get_or_404(db, UiWorkspaceAnalysis, analysis_id, "Analysis")
    _delete_workspace_records_linked_to_entity(db, "analysis", item.id)
    db.delete(item)
    db.commit()
    return DeleteResponse(deleted=True, entity_type="analysis", entity_id=analysis_id, message="Analysis was deleted.")


@router.post("/workspace/{scope_type}/{scope_id}/evidence", response_model=WorkspaceEvidenceRead)
def create_workspace_evidence(scope_type: ScopeType, scope_id: uuid.UUID, payload: WorkspaceEvidenceCreate, db: Annotated[Session, Depends(get_db)], _: Annotated[dict[str, Any], Depends(require_authenticated_request)]) -> UiWorkspaceEvidence:
    _validate_scope(db, scope_type, scope_id)
    item = UiWorkspaceEvidence(**payload.model_dump(), scope_type=scope_type, scope_id=scope_id)
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.put("/workspace/evidence/{evidence_id}", response_model=WorkspaceEvidenceRead)
def update_workspace_evidence(evidence_id: uuid.UUID, payload: WorkspaceEvidenceUpdate, db: Annotated[Session, Depends(get_db)], _: Annotated[dict[str, Any], Depends(require_authenticated_request)]) -> UiWorkspaceEvidence:
    item = _get_or_404(db, UiWorkspaceEvidence, evidence_id, "Evidence")
    _apply_payload(item, payload)
    db.commit()
    db.refresh(item)
    return item


@router.delete("/workspace/evidence/{evidence_id}", response_model=DeleteResponse)
def delete_workspace_evidence(evidence_id: uuid.UUID, db: Annotated[Session, Depends(get_db)], _: Annotated[dict[str, Any], Depends(require_authenticated_request)]) -> DeleteResponse:
    item = _get_or_404(db, UiWorkspaceEvidence, evidence_id, "Evidence")
    _delete_workspace_records_linked_to_entity(db, "evidence", item.id)
    db.delete(item)
    db.commit()
    return DeleteResponse(deleted=True, entity_type="evidence", entity_id=evidence_id, message="Evidence was deleted.")


@router.get("/workspace/{scope_type}/{scope_id}/files", response_model=list[WorkspaceFileRead])
def list_workspace_files(scope_type: ScopeType, scope_id: uuid.UUID, db: Annotated[Session, Depends(get_db)], _: Annotated[dict[str, Any], Depends(require_authenticated_request)]) -> list[UiWorkspaceFile]:
    _validate_scope(db, scope_type, scope_id)
    return list(db.scalars(select(UiWorkspaceFile).where(UiWorkspaceFile.scope_type == scope_type, UiWorkspaceFile.scope_id == scope_id).order_by(UiWorkspaceFile.uploaded_at.desc())).all())


@router.post("/workspace/{scope_type}/{scope_id}/files", response_model=WorkspaceFileRead)
def upload_workspace_file(
    scope_type: ScopeType,
    scope_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[dict[str, Any], Depends(require_authenticated_request)],
    file: UploadFile = File(...),
    upload_category: str = "General",
    description: str | None = None,
    linked_entity_type: str | None = None,
    linked_entity_id: uuid.UUID | None = None,
    uploaded_by: str | None = None,
) -> UiWorkspaceFile:
    _validate_scope(db, scope_type, scope_id)

    UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
    stored_filename = f"{uuid.uuid4()}_{file.filename}"
    storage_path = UPLOAD_ROOT / stored_filename

    with storage_path.open("wb") as output:
        shutil.copyfileobj(file.file, output)

    item = UiWorkspaceFile(
        scope_type=scope_type,
        scope_id=scope_id,
        linked_entity_type=linked_entity_type,
        linked_entity_id=linked_entity_id,
        original_filename=file.filename or stored_filename,
        stored_filename=stored_filename,
        storage_path=str(storage_path),
        content_type=file.content_type,
        file_size_bytes=storage_path.stat().st_size if storage_path.exists() else None,
        upload_category=upload_category,
        description=description,
        uploaded_by=uploaded_by,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.delete("/workspace/files/{file_id}", response_model=DeleteResponse)
def delete_workspace_file(file_id: uuid.UUID, db: Annotated[Session, Depends(get_db)], _: Annotated[dict[str, Any], Depends(require_authenticated_request)]) -> DeleteResponse:
    item = _get_or_404(db, UiWorkspaceFile, file_id, "Workspace file")
    _delete_file_record(item)
    db.delete(item)
    db.commit()
    return DeleteResponse(deleted=True, entity_type="file", entity_id=file_id, message="File record and stored file were deleted.")


@router.post("/workspace/refine-text", response_model=WorkspaceTextRefinementResponse)
def refine_workspace_text(
    payload: WorkspaceTextRefinementRequest,
    _: Annotated[dict[str, Any], Depends(require_authenticated_request)],
) -> WorkspaceTextRefinementResponse:
    fallback = (
        "Refined consulting wording:\n\n"
        f"{payload.text.strip()}\n\n"
        "Recommended edit: clarify the business context, state the implication, and identify the next action."
    )

    prompt = (
        f"Refinement goal: {payload.refinement_goal}\n\n"
        f"Context: {payload.context or 'No additional context provided.'}\n\n"
        f"Text to refine:\n{payload.text}\n\n"
        "Return only the refined text."
    )

    refined_text = _run_llm(
        prompt=prompt,
        fallback=fallback,
        workflow_name="ASM MVP18 - Refine Workspace Text",
    )

    return WorkspaceTextRefinementResponse(
        original_text=payload.text,
        refined_text=refined_text,
        refinement_goal=payload.refinement_goal,
    )


@router.post("/workspace/{scope_type}/{scope_id}/generate-recommendation", response_model=WorkspaceRecommendationRead)
def generate_workspace_recommendation(
    scope_type: ScopeType,
    scope_id: uuid.UUID,
    payload: WorkspaceRecommendationRequest,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[dict[str, Any], Depends(require_authenticated_request)],
) -> UiWorkspaceRecommendation:
    _validate_scope(db, scope_type, scope_id)
    context = _recommendation_context(db, scope_type, scope_id)

    fallback = (
        "AI recommendation draft:\n\n"
        "Review the available data collections, stakeholder questions, findings, analysis, evidence, and files. "
        "Identify missing data, unresolved stakeholder responses, unvalidated findings, and evidence gaps before finalizing this work item."
    )

    prompt = (
        "Generate a practical ASM consulting workspace recommendation using the following JSON context. "
        "Focus on data gaps, questions to ask, risks/blockers, additional evidence needed, next steps, and AI/automation opportunities. "
        "Do not invent facts. If evidence is missing, explicitly say so.\n\n"
        f"Recommendation type: {payload.recommendation_type}\n"
        f"Focus area: {payload.focus_area}\n\n"
        f"Context JSON:\n{json.dumps(context, indent=2, default=str)}"
    )

    output = _run_llm(
        prompt=prompt,
        fallback=fallback,
        workflow_name="ASM MVP18 - Generate Workspace Recommendation",
    )

    item = UiWorkspaceRecommendation(
        scope_type=scope_type,
        scope_id=scope_id,
        recommendation_type=payload.recommendation_type,
        focus_area=payload.focus_area,
        title=f"{payload.recommendation_type} - {_entity_label(_get_or_404(db, Task if scope_type == 'task' else Subtask, scope_id, 'Scope item'))}",
        ai_analysis=output,
        recommendation_text=output,
        additional_data_to_collect="Review output for listed data gaps.",
        additional_questions_to_ask="Review output for suggested stakeholder questions.",
        risks="Review output for identified risks and blockers.",
        next_steps="Review output for suggested next steps.",
        suggested_evidence="Review output for suggested evidence to gather.",
        automation_opportunities="Review output for AI and automation opportunities.",
        source_context_json=json.dumps(context, default=str),
        status="Draft",
        confidence_score=Decimal("0.80"),
        created_by=payload.created_by,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item
