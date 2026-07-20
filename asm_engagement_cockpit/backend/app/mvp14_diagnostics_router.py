import json
import uuid
from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.database import get_db
from app.models import Reminder
from app.models.mvp16_operations import AppUser, AuditEvent, ExecutiveSnapshot, NotificationItem
from app.security import (
    create_session_token,
    require_authenticated_request,
    verify_session_token,
)

router = APIRouter(prefix="/api", tags=["Diagnostics, Auth, and Operations"])


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str
    display_name: str
    expires_in_minutes: int


class AuthStatusResponse(BaseModel):
    authenticated: bool
    auth_type: str
    username: str | None = None
    display_name: str | None = None
    expires_at: int | None = None
    expires_at_utc: str | None = None

    model_config = ConfigDict(extra="allow")


class RuntimeDiagnosticsResponse(BaseModel):
    app_name: str
    app_env: str
    database_status: str
    cors_origins: list[str]
    openai_model: str
    openai_tracing: bool
    openai_api_key_configured: bool
    api_auth_enabled: bool
    api_auth_key_configured: bool
    app_login_enabled: bool
    app_login_configured: bool
    app_login_username: str
    app_session_duration_minutes: int
    log_requests: bool


class AppUserCreate(BaseModel):
    username: str
    display_name: str
    email: str | None = None
    role: str = "Engagement Lead"
    is_active: bool = True


class AppUserRead(BaseModel):
    id: uuid.UUID
    username: str
    display_name: str
    email: str | None
    role: str
    is_active: bool
    source: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AuditEventCreate(BaseModel):
    event_type: str
    event_category: str = "General"
    entity_type: str | None = None
    entity_id: uuid.UUID | None = None
    entity_title: str | None = None
    actor_name: str | None = None
    actor_role: str | None = None
    description: str
    details: dict[str, Any] | None = None
    severity: str = "Info"


class AuditEventRead(BaseModel):
    id: uuid.UUID
    event_type: str
    event_category: str
    entity_type: str | None
    entity_id: uuid.UUID | None
    entity_title: str | None
    actor_name: str | None
    actor_role: str | None
    description: str
    details_json: str | None
    severity: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class NotificationRead(BaseModel):
    id: uuid.UUID
    notification_type: str
    title: str
    message: str
    severity: str
    status: str
    target_role: str | None
    target_user_name: str | None
    source_type: str | None
    source_id: uuid.UUID | None
    due_date: datetime | None
    read_at: datetime | None
    dismissed_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class NotificationUpdateRequest(BaseModel):
    status: str
    target_user_name: str | None = None


class ExecutiveSummaryResponse(BaseModel):
    generated_at: datetime
    health_status: str
    summary_text: str
    counts: dict[str, int]
    risks: list[str]
    recommended_management_actions: list[str]


class ExecutiveSnapshotRead(BaseModel):
    id: uuid.UUID
    snapshot_title: str
    summary_text: str
    health_status: str
    total_workstreams: int
    total_deliverables: int
    total_tasks: int
    total_subtasks: int
    open_reminders: int
    open_notifications: int
    open_review_actions: int
    open_recommendation_actions: int
    generated_by: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class OperationsDashboardResponse(BaseModel):
    users: int
    active_users: int
    audit_events: int
    unread_notifications: int
    open_notifications: int
    latest_audit_events: list[AuditEventRead]
    latest_notifications: list[NotificationRead]
    executive_summary: ExecutiveSummaryResponse


def _utc_from_epoch(epoch_seconds: int | None) -> str | None:
    if epoch_seconds is None:
        return None

    return datetime.fromtimestamp(epoch_seconds, tz=timezone.utc).isoformat()


def _count_table(db: Session, table_name: str) -> int:
    try:
        return int(db.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar() or 0)
    except Exception:
        return 0


def _count_open_status(db: Session, table_name: str, status_column: str = "status") -> int:
    try:
        statement = text(
            f"""
            SELECT COUNT(*)
            FROM {table_name}
            WHERE lower(coalesce({status_column}, '')) NOT IN ('completed', 'closed', 'dismissed', 'cancelled')
            """
        )
        return int(db.execute(statement).scalar() or 0)
    except Exception:
        return 0


def _build_executive_summary(db: Session) -> ExecutiveSummaryResponse:
    counts = {
        "engagements": _count_table(db, "engagements"),
        "workstreams": _count_table(db, "workstreams"),
        "deliverables": _count_table(db, "deliverables"),
        "tasks": _count_table(db, "tasks"),
        "subtasks": _count_table(db, "subtasks"),
        "data_points": _count_table(db, "data_points"),
        "stakeholder_questions": _count_table(db, "stakeholder_questions"),
        "findings": _count_table(db, "findings"),
        "analysis_outputs": _count_table(db, "analysis_outputs"),
        "uploaded_files": _count_table(db, "uploaded_files"),
        "llm_recommendations": _count_table(db, "llm_recommendations"),
        "deliverable_reviews": _count_table(db, "deliverable_reviews"),
        "timesheet_entries": _count_table(db, "timesheet_entries"),
        "review_workflows": _count_table(db, "deliverable_review_workflows"),
        "review_action_items": _count_table(db, "deliverable_review_action_items"),
        "recommendation_action_items": _count_table(db, "llm_recommendation_action_items"),
        "audit_events": _count_table(db, "audit_events"),
        "notifications": _count_table(db, "notification_items"),
    }

    open_reminders = int(
        db.scalar(
            select(func.count())
            .select_from(Reminder)
            .where(Reminder.is_active.is_(True))
        )
        or 0
    )

    unread_notifications = int(
        db.scalar(
            select(func.count())
            .select_from(NotificationItem)
            .where(NotificationItem.status == "Unread")
        )
        or 0
    )

    open_review_actions = _count_open_status(db, "deliverable_review_action_items")
    open_recommendation_actions = _count_open_status(db, "llm_recommendation_action_items")

    counts["open_reminders"] = open_reminders
    counts["unread_notifications"] = unread_notifications
    counts["open_review_actions"] = open_review_actions
    counts["open_recommendation_actions"] = open_recommendation_actions

    risks: list[str] = []

    if open_reminders > 0:
        risks.append(f"{open_reminders} active reminders require attention.")

    if open_review_actions > 0:
        risks.append(f"{open_review_actions} review action items remain open.")

    if open_recommendation_actions > 0:
        risks.append(f"{open_recommendation_actions} recommendation action items remain open.")

    if counts["stakeholder_questions"] > 0 and counts["data_points"] > 0:
        risks.append("Stakeholder questions and data dependencies should be reviewed before final deliverable approval.")

    if not risks:
        risks.append("No major operational risks detected from current cockpit data.")

    recommended_actions = [
        "Review overdue and due-soon reminders daily.",
        "Close review action items before marking deliverables approved.",
        "Convert accepted recommendations into action items with clear owners.",
        "Use the executive snapshot before stakeholder status meetings.",
    ]

    if open_recommendation_actions > 0:
        recommended_actions.append("Prioritize open recommendation action items by delivery impact.")

    if unread_notifications > 0:
        recommended_actions.append("Review unread notifications and mark them read or dismissed.")

    if open_reminders == 0 and open_review_actions == 0 and open_recommendation_actions == 0:
        health_status = "Green"
    elif open_reminders <= 5 and open_review_actions <= 5 and open_recommendation_actions <= 5:
        health_status = "Amber"
    else:
        health_status = "Red"

    summary_text = (
        f"Current cockpit health is {health_status}. "
        f"There are {counts['workstreams']} workstreams, {counts['deliverables']} deliverables, "
        f"{counts['tasks']} tasks, and {counts['subtasks']} sub-tasks being tracked. "
        f"Open management attention items include {open_reminders} reminders, "
        f"{open_review_actions} review actions, and {open_recommendation_actions} recommendation actions."
    )

    return ExecutiveSummaryResponse(
        generated_at=datetime.utcnow(),
        health_status=health_status,
        summary_text=summary_text,
        counts=counts,
        risks=risks,
        recommended_management_actions=recommended_actions,
    )


def _record_audit_event(
    db: Session,
    *,
    event_type: str,
    event_category: str,
    description: str,
    actor_name: str | None = None,
    actor_role: str | None = None,
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    entity_title: str | None = None,
    details: dict[str, Any] | None = None,
    severity: str = "Info",
) -> AuditEvent:
    item = AuditEvent(
        event_type=event_type,
        event_category=event_category,
        entity_type=entity_type,
        entity_id=entity_id,
        entity_title=entity_title,
        actor_name=actor_name,
        actor_role=actor_role,
        description=description,
        details_json=json.dumps(details or {}, default=str),
        severity=severity,
    )
    db.add(item)
    return item


@router.post("/auth/login", response_model=LoginResponse)
def login(
    payload: LoginRequest,
    settings: Settings = Depends(get_settings),
) -> LoginResponse:
    if not settings.app_login_enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Application login is disabled.",
        )

    if not settings.login_is_ready:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Application login is enabled but login settings are not fully configured. "
                "Check APP_LOGIN_USERNAME, APP_LOGIN_PASSWORD, and APP_SESSION_SECRET_KEY."
            ),
        )

    username_matches = payload.username == settings.app_login_username
    password_matches = payload.password == settings.app_login_password

    if not username_matches or not password_matches:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password.",
        )

    token = create_session_token(
        username=settings.app_login_username,
        display_name=settings.app_login_display_name,
        settings=settings,
    )

    return LoginResponse(
        access_token=token,
        username=settings.app_login_username,
        display_name=settings.app_login_display_name,
        expires_in_minutes=settings.app_session_duration_minutes,
    )


@router.get("/auth/status", response_model=AuthStatusResponse)
def get_auth_status(
    auth_context: Annotated[dict[str, Any], Depends(require_authenticated_request)],
) -> AuthStatusResponse:
    expires_at = auth_context.get("expires_at")

    return AuthStatusResponse(
        authenticated=bool(auth_context.get("authenticated")),
        auth_type=str(auth_context.get("auth_type")),
        username=auth_context.get("username"),
        display_name=auth_context.get("display_name"),
        expires_at=expires_at,
        expires_at_utc=_utc_from_epoch(expires_at),
    )


@router.post("/auth/verify-token", response_model=AuthStatusResponse)
def verify_token(
    token: str,
    settings: Settings = Depends(get_settings),
) -> AuthStatusResponse:
    payload = verify_session_token(token, settings)
    expires_at = payload.get("exp")

    return AuthStatusResponse(
        authenticated=True,
        auth_type="session",
        username=payload.get("sub"),
        display_name=payload.get("display_name"),
        expires_at=expires_at,
        expires_at_utc=_utc_from_epoch(expires_at),
    )


@router.get("/diagnostics/runtime", response_model=RuntimeDiagnosticsResponse)
def get_runtime_diagnostics(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[dict[str, Any], Depends(require_authenticated_request)],
    settings: Settings = Depends(get_settings),
) -> RuntimeDiagnosticsResponse:
    db_status = "unknown"

    try:
        db.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception as exc:
        db_status = f"error: {type(exc).__name__}"

    return RuntimeDiagnosticsResponse(
        app_name=settings.app_name,
        app_env=settings.app_env,
        database_status=db_status,
        cors_origins=settings.cors_origins,
        openai_model=settings.openai_model,
        openai_tracing=settings.openai_tracing,
        openai_api_key_configured=bool(settings.openai_api_key),
        api_auth_enabled=settings.api_auth_enabled,
        api_auth_key_configured=bool(settings.api_auth_key),
        app_login_enabled=settings.app_login_enabled,
        app_login_configured=settings.login_is_ready,
        app_login_username=settings.app_login_username,
        app_session_duration_minutes=settings.app_session_duration_minutes,
        log_requests=settings.log_requests,
    )


@router.post("/operations/bootstrap-current-user", response_model=AppUserRead)
def bootstrap_current_user(
    db: Annotated[Session, Depends(get_db)],
    auth_context: Annotated[dict[str, Any], Depends(require_authenticated_request)],
    settings: Settings = Depends(get_settings),
) -> AppUser:
    username = auth_context.get("username") or settings.app_login_username
    display_name = auth_context.get("display_name") or settings.app_login_display_name

    existing = db.scalar(select(AppUser).where(AppUser.username == username))

    if existing is not None:
        existing.display_name = display_name
        existing.is_active = True
        existing.updated_at = datetime.utcnow()

        _record_audit_event(
            db,
            event_type="user_bootstrap_refreshed",
            event_category="User Management",
            description=f"User profile refreshed for {display_name}.",
            actor_name=display_name,
            actor_role=existing.role,
            entity_type="app_user",
            entity_id=existing.id,
            entity_title=existing.display_name,
        )

        db.commit()
        db.refresh(existing)
        return existing

    item = AppUser(
        username=username,
        display_name=display_name,
        email=None,
        role="Engagement Lead",
        is_active=True,
        source="login_session",
    )
    db.add(item)
    db.flush()

    _record_audit_event(
        db,
        event_type="user_bootstrapped",
        event_category="User Management",
        description=f"User profile created for {display_name}.",
        actor_name=display_name,
        actor_role=item.role,
        entity_type="app_user",
        entity_id=item.id,
        entity_title=item.display_name,
    )

    db.commit()
    db.refresh(item)
    return item


@router.post("/operations/users", response_model=AppUserRead)
def create_app_user(
    payload: AppUserCreate,
    db: Annotated[Session, Depends(get_db)],
    auth_context: Annotated[dict[str, Any], Depends(require_authenticated_request)],
) -> AppUser:
    existing = db.scalar(select(AppUser).where(AppUser.username == payload.username))

    if existing is not None:
        raise HTTPException(status_code=400, detail="Username already exists.")

    item = AppUser(
        username=payload.username,
        display_name=payload.display_name,
        email=payload.email,
        role=payload.role,
        is_active=payload.is_active,
        source="manual",
    )
    db.add(item)
    db.flush()

    _record_audit_event(
        db,
        event_type="user_created",
        event_category="User Management",
        description=f"User {payload.display_name} was created.",
        actor_name=auth_context.get("display_name"),
        actor_role=auth_context.get("auth_type"),
        entity_type="app_user",
        entity_id=item.id,
        entity_title=item.display_name,
        details=payload.model_dump(),
    )

    db.commit()
    db.refresh(item)
    return item


@router.get("/operations/users", response_model=list[AppUserRead])
def list_app_users(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[dict[str, Any], Depends(require_authenticated_request)],
) -> list[AppUser]:
    return list(db.scalars(select(AppUser).order_by(AppUser.created_at.desc())).all())


@router.get("/operations/roles")
def list_roles(
    _: Annotated[dict[str, Any], Depends(require_authenticated_request)],
) -> list[dict[str, object]]:
    return [
        {
            "role": "Engagement Lead",
            "permissions": [
                "View executive dashboard",
                "Manage users",
                "View audit events",
                "Generate executive snapshots",
                "Manage notifications",
            ],
        },
        {
            "role": "Delivery Owner",
            "permissions": [
                "View delivery work items",
                "Manage action items",
                "View reminders",
                "Create audit notes",
            ],
        },
        {
            "role": "Reviewer / Approver",
            "permissions": [
                "View review workflows",
                "Manage review action items",
                "Record review decisions",
            ],
        },
        {
            "role": "Data Gathering Owner",
            "permissions": [
                "View data points",
                "Track stakeholder questions",
                "Manage data follow-ups",
            ],
        },
        {
            "role": "Automation / AI Advisor",
            "permissions": [
                "View LLM recommendations",
                "Manage recommendation action items",
                "View automation roadmap outputs",
            ],
        },
    ]


@router.post("/operations/audit-events", response_model=AuditEventRead)
def create_audit_event(
    payload: AuditEventCreate,
    db: Annotated[Session, Depends(get_db)],
    auth_context: Annotated[dict[str, Any], Depends(require_authenticated_request)],
) -> AuditEvent:
    item = _record_audit_event(
        db,
        event_type=payload.event_type,
        event_category=payload.event_category,
        entity_type=payload.entity_type,
        entity_id=payload.entity_id,
        entity_title=payload.entity_title,
        actor_name=payload.actor_name or auth_context.get("display_name"),
        actor_role=payload.actor_role or auth_context.get("auth_type"),
        description=payload.description,
        details=payload.details,
        severity=payload.severity,
    )

    db.commit()
    db.refresh(item)
    return item


@router.get("/operations/audit-events", response_model=list[AuditEventRead])
def list_audit_events(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[dict[str, Any], Depends(require_authenticated_request)],
    limit: int = Query(default=50, ge=1, le=200),
    entity_type: str | None = Query(default=None),
) -> list[AuditEvent]:
    statement = select(AuditEvent)

    if entity_type:
        statement = statement.where(AuditEvent.entity_type == entity_type)

    statement = statement.order_by(AuditEvent.created_at.desc()).limit(limit)

    return list(db.scalars(statement).all())


@router.post("/operations/notifications/generate", response_model=list[NotificationRead])
def generate_notifications(
    db: Annotated[Session, Depends(get_db)],
    auth_context: Annotated[dict[str, Any], Depends(require_authenticated_request)],
) -> list[NotificationItem]:
    active_reminders = list(
        db.scalars(
            select(Reminder)
            .where(Reminder.is_active.is_(True))
            .order_by(Reminder.effective_due_date.asc().nullslast())
        ).all()
    )

    generated: list[NotificationItem] = []

    for reminder in active_reminders:
        existing = db.scalar(
            select(NotificationItem).where(
                NotificationItem.source_type == "reminder",
                NotificationItem.source_id == reminder.id,
                NotificationItem.status.in_(["Unread", "Read"]),
            )
        )

        due_date = None
        if reminder.effective_due_date is not None:
            due_date = datetime.combine(reminder.effective_due_date, datetime.min.time())

        if existing is not None:
            existing.title = reminder.title
            existing.message = reminder.message
            existing.severity = reminder.severity.title()
            existing.due_date = due_date
            existing.updated_at = datetime.utcnow()
            generated.append(existing)
            continue

        item = NotificationItem(
            notification_type="Reminder",
            title=reminder.title,
            message=reminder.message,
            severity=reminder.severity.title(),
            status="Unread",
            target_role="Engagement Lead",
            target_user_name=None,
            source_type="reminder",
            source_id=reminder.id,
            due_date=due_date,
        )
        db.add(item)
        generated.append(item)

    _record_audit_event(
        db,
        event_type="notifications_generated",
        event_category="Notifications",
        description=f"Generated or refreshed {len(generated)} notifications from active reminders.",
        actor_name=auth_context.get("display_name"),
        actor_role=auth_context.get("auth_type"),
        details={"generated_count": len(generated)},
    )

    db.commit()

    for item in generated:
        db.refresh(item)

    return generated


@router.get("/operations/notifications", response_model=list[NotificationRead])
def list_notifications(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[dict[str, Any], Depends(require_authenticated_request)],
    include_dismissed: bool = Query(default=False),
) -> list[NotificationItem]:
    statement = select(NotificationItem)

    if not include_dismissed:
        statement = statement.where(NotificationItem.status != "Dismissed")

    statement = statement.order_by(NotificationItem.created_at.desc())

    return list(db.scalars(statement).all())


@router.put("/operations/notifications/{notification_id}", response_model=NotificationRead)
def update_notification(
    notification_id: uuid.UUID,
    payload: NotificationUpdateRequest,
    db: Annotated[Session, Depends(get_db)],
    auth_context: Annotated[dict[str, Any], Depends(require_authenticated_request)],
) -> NotificationItem:
    item = db.get(NotificationItem, notification_id)

    if item is None:
        raise HTTPException(status_code=404, detail="Notification not found.")

    normalized_status = payload.status.strip().title()

    if normalized_status not in {"Unread", "Read", "Dismissed"}:
        raise HTTPException(status_code=400, detail="Status must be Unread, Read, or Dismissed.")

    item.status = normalized_status
    item.target_user_name = payload.target_user_name or item.target_user_name

    if normalized_status == "Read":
        item.read_at = datetime.utcnow()
    elif normalized_status == "Dismissed":
        item.dismissed_at = datetime.utcnow()

    _record_audit_event(
        db,
        event_type="notification_updated",
        event_category="Notifications",
        entity_type="notification",
        entity_id=item.id,
        entity_title=item.title,
        actor_name=auth_context.get("display_name"),
        actor_role=auth_context.get("auth_type"),
        description=f"Notification status changed to {normalized_status}.",
        details={"notification_id": str(item.id), "status": normalized_status},
    )

    db.commit()
    db.refresh(item)
    return item


@router.get("/operations/executive-summary", response_model=ExecutiveSummaryResponse)
def get_executive_summary(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[dict[str, Any], Depends(require_authenticated_request)],
) -> ExecutiveSummaryResponse:
    return _build_executive_summary(db)


@router.post("/operations/executive-snapshots", response_model=ExecutiveSnapshotRead)
def create_executive_snapshot(
    db: Annotated[Session, Depends(get_db)],
    auth_context: Annotated[dict[str, Any], Depends(require_authenticated_request)],
) -> ExecutiveSnapshot:
    summary = _build_executive_summary(db)

    item = ExecutiveSnapshot(
        snapshot_title=f"Executive Snapshot - {datetime.utcnow().date().isoformat()}",
        summary_text=summary.summary_text,
        health_status=summary.health_status,
        total_workstreams=summary.counts.get("workstreams", 0),
        total_deliverables=summary.counts.get("deliverables", 0),
        total_tasks=summary.counts.get("tasks", 0),
        total_subtasks=summary.counts.get("subtasks", 0),
        open_reminders=summary.counts.get("open_reminders", 0),
        open_notifications=summary.counts.get("unread_notifications", 0),
        open_review_actions=summary.counts.get("open_review_actions", 0),
        open_recommendation_actions=summary.counts.get("open_recommendation_actions", 0),
        generated_by=auth_context.get("display_name"),
    )
    db.add(item)
    db.flush()

    _record_audit_event(
        db,
        event_type="executive_snapshot_created",
        event_category="Executive Reporting",
        entity_type="executive_snapshot",
        entity_id=item.id,
        entity_title=item.snapshot_title,
        actor_name=auth_context.get("display_name"),
        actor_role=auth_context.get("auth_type"),
        description=f"Executive snapshot created with health status {summary.health_status}.",
        details=summary.model_dump(),
    )

    db.commit()
    db.refresh(item)
    return item


@router.get("/operations/executive-snapshots", response_model=list[ExecutiveSnapshotRead])
def list_executive_snapshots(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[dict[str, Any], Depends(require_authenticated_request)],
    limit: int = Query(default=20, ge=1, le=100),
) -> list[ExecutiveSnapshot]:
    return list(
        db.scalars(
            select(ExecutiveSnapshot)
            .order_by(ExecutiveSnapshot.created_at.desc())
            .limit(limit)
        ).all()
    )


@router.get("/operations/dashboard", response_model=OperationsDashboardResponse)
def get_operations_dashboard(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[dict[str, Any], Depends(require_authenticated_request)],
) -> OperationsDashboardResponse:
    users = int(db.scalar(select(func.count()).select_from(AppUser)) or 0)
    active_users = int(
        db.scalar(
            select(func.count())
            .select_from(AppUser)
            .where(AppUser.is_active.is_(True))
        )
        or 0
    )
    audit_events = int(db.scalar(select(func.count()).select_from(AuditEvent)) or 0)
    unread_notifications = int(
        db.scalar(
            select(func.count())
            .select_from(NotificationItem)
            .where(NotificationItem.status == "Unread")
        )
        or 0
    )
    open_notifications = int(
        db.scalar(
            select(func.count())
            .select_from(NotificationItem)
            .where(NotificationItem.status.in_(["Unread", "Read"]))
        )
        or 0
    )

    latest_audit_events = list(
        db.scalars(
            select(AuditEvent)
            .order_by(AuditEvent.created_at.desc())
            .limit(10)
        ).all()
    )

    latest_notifications = list(
        db.scalars(
            select(NotificationItem)
            .order_by(NotificationItem.created_at.desc())
            .limit(10)
        ).all()
    )

    return OperationsDashboardResponse(
        users=users,
        active_users=active_users,
        audit_events=audit_events,
        unread_notifications=unread_notifications,
        open_notifications=open_notifications,
        latest_audit_events=latest_audit_events,
        latest_notifications=latest_notifications,
        executive_summary=_build_executive_summary(db),
    )