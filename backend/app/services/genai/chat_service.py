from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Client, GenAIChatMessage, GenAIChatSession, Project
from app.schemas.genai import GenAIChatContext
from app.services.genai.agent import run_governed_chat_agent
from app.services.genai.charts import attach_charts_to_message
from app.services.genai.config_service import get_or_create_config
from app.services.genai.llm_client import LLMCompletionResult
from app.services.genai.prompt_service import get_active_prompt_text
from app.services.genai.usage_log_service import create_usage_log

DEFAULT_CHAT_TITLE = "New chat"
MAX_CHAT_HISTORY_MESSAGES = 12
PHASE_1C_CAPABILITY_PROMPT = """
You are currently running in Phase 1C of the GenAI workbench. You can answer general questions
about the purpose of the workbench, configuration, and intended capabilities. You do not yet have
access to governed analytics tools or live dashboard data. If the user asks for specific
Applications, Tickets, SLA, OLA, Problem, or Change data, explain that data-aware Q&A will be
available in the next phase and suggest a supported general alternative.
""".strip()
DISABLED_MESSAGE = "GenAI is disabled. Enable GenAI and configure a model before chatting."
MISSING_MODEL_MESSAGE = "Model name is not configured for GenAI."


class ChatServiceError(ValueError):
    pass


class ChatSessionNotFoundError(ChatServiceError):
    pass


@dataclass(frozen=True)
class ChatSessionListResult:
    items: list[GenAIChatSession]
    total: int


@dataclass(frozen=True)
class ChatSendResult:
    user_message: GenAIChatMessage
    assistant_message: GenAIChatMessage
    session: GenAIChatSession


def normalize_title(title: str | None) -> str:
    normalized = (title or DEFAULT_CHAT_TITLE).strip()
    return normalized[:255] if normalized else DEFAULT_CHAT_TITLE


def generate_title_from_message(content: str) -> str:
    first_line = content.strip().splitlines()[0] if content.strip() else DEFAULT_CHAT_TITLE
    first_sentence = first_line.split(". ", maxsplit=1)[0].strip()
    title = first_sentence[:50].strip()
    if len(first_sentence) > 50:
        title = f"{title.rstrip()}..."
    return title or DEFAULT_CHAT_TITLE


def utc_now() -> datetime:
    return datetime.now(UTC)


def create_session(
    db: Session,
    *,
    customer_id: UUID | None = None,
    project_id: UUID | None = None,
    title: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> GenAIChatSession:
    session = GenAIChatSession(
        customer_id=customer_id,
        project_id=project_id,
        title=normalize_title(title),
        metadata_json=metadata or {},
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def list_sessions(
    db: Session,
    *,
    customer_id: UUID | None = None,
    project_id: UUID | None = None,
    include_archived: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> ChatSessionListResult:
    query = select(GenAIChatSession)
    count_query = select(func.count()).select_from(GenAIChatSession)
    filters = []
    if customer_id is not None:
        filters.append(GenAIChatSession.customer_id == customer_id)
    if project_id is not None:
        filters.append(GenAIChatSession.project_id == project_id)
    if not include_archived:
        filters.append(GenAIChatSession.is_archived.is_(False))
    if filters:
        query = query.where(*filters)
        count_query = count_query.where(*filters)
    query = query.order_by(
        GenAIChatSession.last_message_at.desc().nulls_last(),
        GenAIChatSession.created_at.desc(),
    )
    items = db.execute(query.limit(limit).offset(offset)).scalars().all()
    total = db.execute(count_query).scalar_one()
    return ChatSessionListResult(items=items, total=total)


def get_session(db: Session, session_id: UUID) -> GenAIChatSession:
    session = db.get(GenAIChatSession, session_id)
    if session is None:
        raise ChatSessionNotFoundError("Chat session was not found.")
    return session


def get_session_messages(db: Session, session_id: UUID) -> list[GenAIChatMessage]:
    return (
        db.execute(
            select(GenAIChatMessage)
            .where(GenAIChatMessage.session_id == session_id)
            .order_by(GenAIChatMessage.created_at.asc()),
        )
        .scalars()
        .all()
    )


def update_session(
    db: Session,
    session_id: UUID,
    *,
    title: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> GenAIChatSession:
    session = get_session(db, session_id)
    if title is not None:
        session.title = normalize_title(title)
    if metadata is not None:
        session.metadata_json = metadata
    db.commit()
    db.refresh(session)
    return session


def archive_session(db: Session, session_id: UUID) -> GenAIChatSession:
    session = get_session(db, session_id)
    session.is_archived = True
    db.commit()
    db.refresh(session)
    return session


def recent_messages(db: Session, session_id: UUID) -> list[GenAIChatMessage]:
    rows = (
        db.execute(
            select(GenAIChatMessage)
            .where(GenAIChatMessage.session_id == session_id)
            .order_by(GenAIChatMessage.created_at.desc())
            .limit(MAX_CHAT_HISTORY_MESSAGES),
        )
        .scalars()
        .all()
    )
    return list(reversed(rows))


def llm_role_for_message(role: str) -> str:
    return role if role in {"user", "assistant", "system"} else "assistant"


def build_chat_prompt_messages(
    db: Session,
    *,
    session: GenAIChatSession,
    history: list[GenAIChatMessage],
    context: GenAIChatContext,
) -> list[dict[str, str]]:
    domain_rules = get_active_prompt_text(db, "system_domain_rules")
    safety_guardrails = get_active_prompt_text(db, "safety_guardrails")
    context_note = (
        "Current UI context metadata only; it is not live dashboard data:\n"
        f"- customer_id: {context.customer_id or session.customer_id or 'not selected'}\n"
        f"- project_id: {context.project_id or session.project_id or 'not selected'}\n"
        f"- domain: {context.domain}\n"
        f"- page: {context.page}"
    )
    system_prompt = "\n\n".join(
        [
            domain_rules,
            safety_guardrails,
            PHASE_1C_CAPABILITY_PROMPT,
            context_note,
        ],
    )
    messages = [{"role": "system", "content": system_prompt}]
    for message in history:
        messages.append(
            {
                "role": llm_role_for_message(message.role),
                "content": message.content,
            },
        )
    return messages


def chat_metadata(
    *,
    session: GenAIChatSession,
    context: GenAIChatContext,
    provider: str | None,
    model_name: str | None,
    result: LLMCompletionResult | None,
    status: str,
    error_message: str | None = None,
) -> dict[str, Any]:
    return {
        "provider": provider,
        "model_name": model_name,
        "duration_ms": result.duration_ms if result else None,
        "usage": {
            "prompt_tokens": result.prompt_tokens if result else None,
            "completion_tokens": result.completion_tokens if result else None,
            "estimated_cost": result.estimated_cost if result else None,
        },
        "tools_used": [],
        "data_access": "none_general",
        "status": status,
        "error_message": error_message,
        "context": {
            "customer_id": str(context.customer_id or session.customer_id)
            if context.customer_id or session.customer_id
            else None,
            "project_id": str(context.project_id or session.project_id)
            if context.project_id or session.project_id
            else None,
            "domain": context.domain,
            "page": context.page,
            "filters": context.filters,
            "time_range": context.time_range,
        },
    }


def store_assistant_message(
    db: Session,
    *,
    session: GenAIChatSession,
    content: str,
    metadata: dict[str, Any],
) -> GenAIChatMessage:
    assistant_message = GenAIChatMessage(
        session_id=session.id,
        role="assistant",
        content=content,
        metadata_json=metadata,
    )
    session.last_message_at = utc_now()
    db.add(assistant_message)
    db.commit()
    db.refresh(assistant_message)
    db.refresh(session)
    return assistant_message


def send_chat_message(
    db: Session,
    *,
    session_id: UUID,
    content: str,
    context: GenAIChatContext,
) -> ChatSendResult:
    session = get_session(db, session_id)
    if session.is_archived:
        raise ChatServiceError("Archived chat sessions cannot accept new messages.")

    normalized_content = content.strip()
    if not normalized_content:
        raise ChatServiceError("Message content is required.")

    user_message_count = db.execute(
        select(func.count())
        .select_from(GenAIChatMessage)
        .where(GenAIChatMessage.session_id == session.id, GenAIChatMessage.role == "user"),
    ).scalar_one()

    user_message = GenAIChatMessage(
        session_id=session.id,
        role="user",
        content=normalized_content,
        metadata_json={"context": context.model_dump(mode="json")},
    )
    if session.title == DEFAULT_CHAT_TITLE and user_message_count == 0:
        session.title = generate_title_from_message(normalized_content)
    session.last_message_at = utc_now()
    db.add(user_message)
    db.commit()
    db.refresh(user_message)
    db.refresh(session)

    config = get_or_create_config(db)
    provider = config.provider
    model_name = config.model_name

    if not config.is_enabled:
        metadata = chat_metadata(
            session=session,
            context=context,
            provider=provider,
            model_name=model_name,
            result=None,
            status="disabled",
            error_message=DISABLED_MESSAGE,
        )
        assistant_message = store_assistant_message(
            db,
            session=session,
            content=DISABLED_MESSAGE,
            metadata=metadata,
        )
        create_usage_log(
            db,
            operation="chat_agent",
            status="disabled",
            provider=provider,
            model_name=model_name,
            question=normalized_content,
            customer_id=session.customer_id,
            project_id=session.project_id,
            session_id=str(session.id),
            message_id=str(assistant_message.id),
            tools_used_json=[],
            error_message=DISABLED_MESSAGE,
        )
        return ChatSendResult(user_message, assistant_message, session)

    if not model_name or not model_name.strip():
        metadata = chat_metadata(
            session=session,
            context=context,
            provider=provider,
            model_name=model_name,
            result=None,
            status="error",
            error_message=MISSING_MODEL_MESSAGE,
        )
        assistant_message = store_assistant_message(
            db,
            session=session,
            content=MISSING_MODEL_MESSAGE,
            metadata=metadata,
        )
        create_usage_log(
            db,
            operation="chat_agent",
            status="error",
            provider=provider,
            model_name=model_name,
            question=normalized_content,
            customer_id=session.customer_id,
            project_id=session.project_id,
            session_id=str(session.id),
            message_id=str(assistant_message.id),
            tools_used_json=[],
            error_message=MISSING_MODEL_MESSAGE,
        )
        return ChatSendResult(user_message, assistant_message, session)

    agent_result = run_governed_chat_agent(
        db,
        session=session,
        user_message=user_message,
        context=context.model_dump(mode="json"),
        history=recent_messages(db, session.id),
    )
    assistant_message = store_assistant_message(
        db,
        session=session,
        content=agent_result.answer,
        metadata=agent_result.metadata,
    )
    generated_charts = agent_result.metadata.get("generated_charts")
    if isinstance(generated_charts, list):
        attach_charts_to_message(
            db,
            [
                str(item.get("chart_id"))
                for item in generated_charts
                if isinstance(item, dict) and item.get("chart_id")
            ],
            assistant_message.id,
        )
    create_usage_log(
        db,
        operation="chat_agent",
        status=agent_result.status,
        provider=provider,
        model_name=model_name,
        question=normalized_content,
        customer_id=context.customer_id or session.customer_id,
        project_id=context.project_id or session.project_id,
        session_id=str(session.id),
        message_id=str(assistant_message.id),
        tools_used_json=agent_result.metadata.get("tools_used", []),
        prompt_tokens=agent_result.usage.prompt_tokens,
        completion_tokens=agent_result.usage.completion_tokens,
        estimated_cost=agent_result.usage.estimated_cost,
        duration_ms=agent_result.usage.duration_ms,
        error_message=agent_result.error_message,
    )
    return ChatSendResult(user_message, assistant_message, session)


def list_context_customers(db: Session) -> list[Client]:
    return (
        db.execute(
            select(Client)
            .where(Client.is_active.is_(True))
            .order_by(Client.name.asc(), Client.code.asc()),
        )
        .scalars()
        .all()
    )


def list_context_projects(
    db: Session,
    customer_id: UUID | None = None,
) -> list[tuple[Project, Client]]:
    statement = select(Project, Client).join(Client, Project.client_id == Client.id)
    statement = statement.where(Project.is_active.is_(True), Client.is_active.is_(True))
    if customer_id is not None:
        statement = statement.where(Project.client_id == customer_id)
    statement = statement.order_by(Client.name.asc(), Project.name.asc())
    return list(db.execute(statement).all())
