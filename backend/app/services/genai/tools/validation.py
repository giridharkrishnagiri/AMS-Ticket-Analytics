from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import Select, and_, case, func, or_, select
from sqlalchemy.orm import Session

from app.models import GenAISafetySettings, Project

GENERIC_TICKET_TYPES = ("INCIDENT", "SERVICE_CATALOG_TASK")
TICKET_TYPE_MAP = {
    "all": GENERIC_TICKET_TYPES,
    "incident": ("INCIDENT",),
    "sc_task": ("SERVICE_CATALOG_TASK",),
}
VALID_SCOPES = {"in_scope", "out_of_scope", "all"}


class ToolValidationError(ValueError):
    pass


def normalized_key(value: Any, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text.lower() if text else default


def normalized_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def normalized_int(value: Any, default: int, *, minimum: int = 1, maximum: int = 1000) -> int:
    if value is None or value == "":
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ToolValidationError("Numeric parameter must be an integer.") from exc
    if parsed < minimum:
        raise ToolValidationError(f"Numeric parameter must be at least {minimum}.")
    if parsed > maximum:
        return maximum
    return parsed


def normalize_scope(parameters: dict[str, Any]) -> str:
    scope = normalized_key(parameters.get("scope"), "in_scope")
    if scope not in VALID_SCOPES:
        raise ToolValidationError("Scope must be in_scope, out_of_scope, or all.")
    return scope


def normalize_ticket_type(parameters: dict[str, Any]) -> str:
    ticket_type = normalized_key(parameters.get("ticket_type"), "all")
    if ticket_type not in TICKET_TYPE_MAP:
        raise ToolValidationError("Ticket type must be all, incident, or sc_task.")
    return ticket_type


def ensure_allowed(value: str | None, allowed: tuple[str, ...], label: str) -> str:
    normalized = normalized_key(value)
    if not normalized:
        raise ToolValidationError(f"{label} is required.")
    if normalized not in allowed:
        if normalized in {"normalized_payload", "cmdb_payload"}:
            raise ToolValidationError(
                f"{label} references a raw payload field and is not approved.",
            )
        raise ToolValidationError(f"{label} '{normalized}' is not approved for this tool.")
    return normalized


def parse_datetime(value: Any, *, end_of_day: bool = False) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime.combine(value, time.max if end_of_day else time.min)
    else:
        text = str(value).strip()
        try:
            if len(text) == 10:
                parsed_date = date.fromisoformat(text)
                parsed = datetime.combine(parsed_date, time.max if end_of_day else time.min)
            else:
                parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ToolValidationError("Dates must be ISO formatted.") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def previous_month_end(reference: datetime | None = None) -> datetime:
    now = (reference or datetime.now(UTC)).astimezone(UTC)
    first_day_this_month = datetime(now.year, now.month, 1, tzinfo=UTC)
    return first_day_this_month - timedelta(microseconds=1)


def date_range_from_parameters(
    parameters: dict[str, Any],
    *,
    use_complete_month_cutoff: bool,
) -> tuple[datetime | None, datetime | None, list[str]]:
    start = parse_datetime(parameters.get("from_date"))
    end = parse_datetime(parameters.get("to_date"), end_of_day=True)
    notes: list[str] = []
    if use_complete_month_cutoff:
        cutoff = previous_month_end()
        if end is None or end > cutoff:
            end = cutoff
        notes.append("Complete-month cutoff applied.")
    return start, end, notes


def project_ids_for_context(
    db: Session,
    *,
    customer_id: UUID | None,
    project_id: UUID | None,
) -> list[UUID] | None:
    if project_id is not None:
        return [project_id]
    if customer_id is None:
        return None
    return list(
        db.execute(select(Project.id).where(Project.client_id == customer_id)).scalars().all(),
    )


def apply_project_context(
    statement: Select[Any],
    model: Any,
    project_ids: list[UUID] | None,
) -> Select[Any]:
    if project_ids is None:
        return statement
    if not project_ids:
        return statement.where(model.project_id.is_(None))
    return statement.where(model.project_id.in_(project_ids))


def clean_text(value: Any, *, blank_label: str | None = None) -> str | None:
    if value is None:
        return blank_label
    text = str(value).strip()
    return text or blank_label


def lower_trim_expression(column: Any) -> Any:
    return func.lower(func.btrim(column))


def distinct_nonblank_count_expression(column: Any) -> Any:
    return func.count(func.distinct(func.nullif(func.btrim(column), "")))


def cap_rows(rows: list[dict[str, Any]], max_rows: int) -> tuple[list[dict[str, Any]], bool]:
    if len(rows) <= max_rows:
        return rows, False
    return rows[:max_rows], True


def max_rows_from_safety(
    parameters: dict[str, Any],
    safety_settings: GenAISafetySettings,
    *,
    default: int,
    tool_max_rows: int,
) -> int:
    configured = max(1, safety_settings.max_rows_returned_to_llm)
    allowed_max = max(1, min(configured, tool_max_rows))
    return normalized_int(
        parameters.get("top_n"),
        default=min(default, allowed_max),
        minimum=1,
        maximum=allowed_max,
    )


def apply_datetime_range(
    statement: Select[Any],
    date_expression: Any,
    start: datetime | None,
    end: datetime | None,
) -> Select[Any]:
    if start is not None:
        statement = statement.where(date_expression >= start)
    if end is not None:
        statement = statement.where(date_expression <= end)
    return statement


def ticket_type_values(ticket_type: str) -> tuple[str, ...]:
    return TICKET_TYPE_MAP[ticket_type]


def ticket_completion_datetime_expression(model: Any) -> Any:
    ticket_type = func.upper(model.ticket_type)
    return case(
        (ticket_type == "INCIDENT", model.resolved_at),
        (ticket_type == "SERVICE_CATALOG_TASK", model.closed_at),
        else_=func.coalesce(model.resolved_at, model.closed_at),
    )


def ticket_canceled_condition(model: Any) -> Any:
    ticket_type = func.upper(model.ticket_type)
    state = lower_trim_expression(model.state)
    return or_(
        and_(ticket_type == "INCIDENT", state.like("%cancel%")),
        and_(ticket_type == "SERVICE_CATALOG_TASK", state.like("%closed incomplete%")),
    )


def ticket_closed_condition(model: Any) -> Any:
    completion_date = ticket_completion_datetime_expression(model)
    return completion_date.is_not(None)


def ticket_open_condition(model: Any) -> Any:
    state = lower_trim_expression(model.state)
    return and_(
        model.created_at.is_not(None),
        ~or_(
            state.like("%cancel%"),
            state.like("%closed%"),
            state.like("%resolved%"),
            state.like("%complete%"),
        ),
    )


def ticket_status_group_expression(model: Any) -> Any:
    state = lower_trim_expression(model.state)
    return case(
        (ticket_canceled_condition(model), "Canceled / Closed Incomplete"),
        (or_(state.like("%resolved%"), state.like("%closed complete%")), "Resolved / Closed"),
        (state.like("%closed%"), "Closed"),
        (state == "", "Unspecified"),
        (state.is_(None), "Unspecified"),
        else_="Open / Other",
    )


def month_period_expression(date_expression: Any) -> Any:
    return func.to_char(func.date_trunc("month", date_expression), "YYYY-MM")


def numeric_percentage(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return round((numerator / denominator) * 100, 2)
