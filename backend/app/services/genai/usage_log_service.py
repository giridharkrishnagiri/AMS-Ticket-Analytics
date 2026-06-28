from __future__ import annotations

import re
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import GenAIUsageLog

MAX_LOG_TEXT_LENGTH = 1000
SENSITIVE_LOG_MARKERS = (
    "normalized_payload",
    "cmdb_payload",
    "raw sla payload",
    "raw ola payload",
    "database credentials",
)


def compact_log_text(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    for marker in SENSITIVE_LOG_MARKERS:
        text = re.sub(re.escape(marker), "[redacted]", text, flags=re.IGNORECASE)
    if len(text) <= MAX_LOG_TEXT_LENGTH:
        return text
    return f"{text[:MAX_LOG_TEXT_LENGTH]}..."


def create_usage_log(
    db: Session,
    *,
    operation: str,
    status: str,
    provider: str | None = None,
    model_name: str | None = None,
    question: str | None = None,
    customer_id: UUID | None = None,
    project_id: UUID | None = None,
    session_id: str | None = None,
    message_id: str | None = None,
    tools_used_json: dict[str, Any] | list[Any] | None = None,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
    estimated_cost: float | None = None,
    duration_ms: int | None = None,
    error_message: str | None = None,
) -> GenAIUsageLog:
    row = GenAIUsageLog(
        operation=operation,
        status=status,
        provider=provider,
        model_name=model_name,
        question=compact_log_text(question),
        customer_id=customer_id,
        project_id=project_id,
        session_id=session_id,
        message_id=message_id,
        tools_used_json=tools_used_json,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        estimated_cost=estimated_cost,
        duration_ms=duration_ms,
        error_message=compact_log_text(error_message),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def list_usage_logs(
    db: Session,
    *,
    limit: int,
    offset: int,
    status: str | None = None,
    operation: str | None = None,
) -> list[GenAIUsageLog]:
    query = select(GenAIUsageLog)
    if status:
        query = query.where(GenAIUsageLog.status == status)
    if operation:
        query = query.where(GenAIUsageLog.operation == operation)
    query = query.order_by(GenAIUsageLog.created_at.desc()).limit(limit).offset(offset)
    return db.execute(query).scalars().all()
