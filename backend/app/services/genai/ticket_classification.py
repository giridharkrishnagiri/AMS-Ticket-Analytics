from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Select, and_, delete, func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import GenAIConfig, GenAITicketClassification, GenAIUsageLog, Project, Ticket
from app.services.genai.config_service import get_or_create_config
from app.services.genai.llm_client import LLMCompletionResult, chat_completion, provider_model_name
from app.services.genai.prompt_service import get_prompt_template
from app.services.genai.tools.validation import (
    GENERIC_TICKET_TYPES,
    ticket_closed_condition,
    ticket_completion_datetime_expression,
)
from app.services.genai.usage_log_service import create_usage_log

PROMPT_KEY = "ticket_classification_enrichment"
FALLBACK_CATEGORY = "Needs Review"
MAX_DESCRIPTION_CHARS = 1800
MAX_SHORT_DESCRIPTION_CHARS = 500
MAX_CATEGORY_REUSE_ITEMS = 50
DEFAULT_BATCH_SIZE = 10
MAX_BATCH_SIZE = 25
MONTH_PATTERN = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
TICKET_DUMP_EXCLUDED_COLUMNS = {
    "id",
    "project_id",
    "upload_batch_id",
    "uploaded_file_id",
    "raw_row_id",
    "application_dimension_id",
    "application_inventory_id",
    "normalized_payload",
}
TICKET_DUMP_CLASSIFICATION_COLUMNS = [
    "genai_category_quality",
    "genai_category",
    "genai_subcategory_1",
    "genai_subcategory_2",
    "genai_confidence",
    "genai_status",
    "genai_prompt_key",
    "genai_prompt_version",
    "genai_model_name",
    "genai_processed_at",
    "genai_error_message",
]


class TicketClassificationError(ValueError):
    pass


@dataclass(frozen=True)
class TicketClassificationRunRequest:
    project_id: UUID
    analysis_month: str
    force_reprocess: bool = False
    batch_size: int = DEFAULT_BATCH_SIZE
    batch_limit: int | None = None
    run_id: str | None = None


@dataclass(frozen=True)
class TicketClassificationClearRequest:
    project_id: UUID
    analysis_month: str


def validate_month_key(month_key: str) -> str:
    normalized = month_key.strip()
    if not MONTH_PATTERN.match(normalized):
        raise TicketClassificationError("Analysis month must be in YYYY-MM format.")
    return normalized


def month_bounds(month_key: str) -> tuple[datetime, datetime]:
    normalized = validate_month_key(month_key)
    year, month = (int(part) for part in normalized.split("-"))
    start = datetime(year, month, 1, tzinfo=UTC)
    if month == 12:
        end = datetime(year + 1, 1, 1, tzinfo=UTC)
    else:
        end = datetime(year, month + 1, 1, tzinfo=UTC)
    return start, end


def clamp_batch_size(value: int | None) -> int:
    if value is None:
        return DEFAULT_BATCH_SIZE
    return max(1, min(int(value), MAX_BATCH_SIZE))


def clamp_batch_limit(value: int | None) -> int | None:
    if value is None:
        return None
    return max(1, min(int(value), 50))


def compact_text(value: Any, *, max_chars: int) -> str | None:
    if value is None:
        return None
    text = re.sub(r"\s+", " ", str(value)).strip()
    if not text:
        return None
    if len(text) <= max_chars:
        return text
    return f"{text[:max_chars].rstrip()}..."


def clean_label(value: Any, *, max_chars: int = 255) -> str | None:
    if value is None:
        return None
    text = re.sub(r"\s+", " ", str(value)).strip()
    if not text or text.lower() in {"null", "none", "n/a", "na", "-"}:
        return None
    return text[:max_chars]


def normalize_category_quality(value: Any, *, category_was_blank: bool) -> str | None:
    if category_was_blank:
        return None
    text = clean_label(value, max_chars=40)
    if text is None:
        return None
    normalized = text.lower().replace("-", " ")
    if "non" in normalized and "meaning" in normalized:
        return "Non meaningful"
    if "meaning" in normalized:
        return "Meaningful"
    return None


def normalize_confidence(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return max(0.0, min(parsed, 1.0))


def prompt_text_and_version(db: Session) -> tuple[str, int]:
    row = get_prompt_template(db, PROMPT_KEY)
    prompt_text = (
        row.custom_prompt.strip()
        if row.is_custom_enabled and row.custom_prompt and row.custom_prompt.strip()
        else row.default_prompt
    )
    return prompt_text, row.version


def prompt_fingerprint(prompt_text: str) -> str:
    return hashlib.sha256(prompt_text.encode("utf-8")).hexdigest()[:16]


def ticket_payload(ticket: Ticket) -> dict[str, Any]:
    existing_category = compact_text(ticket.category, max_chars=255)
    return {
        "ticket_number": ticket.ticket_number,
        "ticket_type": ticket.ticket_type,
        "short_description": compact_text(
            ticket.short_description,
            max_chars=MAX_SHORT_DESCRIPTION_CHARS,
        ),
        "description": compact_text(ticket.description, max_chars=MAX_DESCRIPTION_CHARS),
        "existing_category": existing_category,
        "existing_subcategory": compact_text(ticket.subcategory, max_chars=255),
        "catalog_item": compact_text(ticket.catalog_item, max_chars=255),
        "catalog_item_name": compact_text(ticket.catalog_item_name, max_chars=255),
    }


def input_hash_for_ticket(
    ticket: Ticket,
    *,
    model_name: str | None,
    prompt_version: int,
    prompt_fingerprint_value: str,
) -> str:
    payload = {
        "ticket_number": ticket.ticket_number,
        "ticket_type": ticket.ticket_type,
        "state": ticket.state,
        "short_description": compact_text(
            ticket.short_description,
            max_chars=MAX_SHORT_DESCRIPTION_CHARS,
        ),
        "description": compact_text(ticket.description, max_chars=MAX_DESCRIPTION_CHARS),
        "existing_category": compact_text(ticket.category, max_chars=255),
        "existing_subcategory": compact_text(ticket.subcategory, max_chars=255),
        "catalog_item": compact_text(ticket.catalog_item, max_chars=255),
        "catalog_item_name": compact_text(ticket.catalog_item_name, max_chars=255),
        "model_name": model_name,
        "prompt_key": PROMPT_KEY,
        "prompt_version": prompt_version,
        "prompt_fingerprint": prompt_fingerprint_value,
    }
    normalized_payload = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(normalized_payload.encode("utf-8")).hexdigest()


def eligible_ticket_statement(project_id: UUID, month_key: str) -> Select[tuple[Ticket]]:
    start, end = month_bounds(month_key)
    completed_at = ticket_completion_datetime_expression(Ticket)
    return (
        select(Ticket)
        .where(
            Ticket.project_id == project_id,
            Ticket.is_in_scope.is_(True),
            func.upper(Ticket.ticket_type).in_(GENERIC_TICKET_TYPES),
            ticket_closed_condition(Ticket),
            completed_at >= start,
            completed_at < end,
        )
        .order_by(Ticket.ticket_number.asc())
    )


def eligible_ticket_count(db: Session, project_id: UUID, month_key: str) -> int:
    statement = (
        eligible_ticket_statement(project_id, month_key)
        .order_by(None)
        .with_only_columns(func.count())
    )
    return int(db.execute(statement).scalar_one() or 0)


def existing_rows_for_month(
    db: Session,
    project_id: UUID,
    month_key: str,
) -> dict[str, GenAITicketClassification]:
    rows = db.execute(
        select(GenAITicketClassification).where(
            GenAITicketClassification.project_id == project_id,
            GenAITicketClassification.analysis_month == month_key,
        ),
    ).scalars()
    return {row.ticket_number: row for row in rows}


def reusable_categories(db: Session, project_id: UUID) -> list[str]:
    rows = db.execute(
        select(
            GenAITicketClassification.genai_category,
            func.count().label("ticket_count"),
        )
        .where(
            GenAITicketClassification.project_id == project_id,
            GenAITicketClassification.status == "success",
            GenAITicketClassification.genai_category.is_not(None),
            func.btrim(GenAITicketClassification.genai_category) != "",
        )
        .group_by(GenAITicketClassification.genai_category)
        .order_by(func.count().desc(), GenAITicketClassification.genai_category.asc())
        .limit(MAX_CATEGORY_REUSE_ITEMS),
    ).all()
    return [str(category) for category, _ticket_count in rows if category]


def build_messages(
    *,
    prompt_text: str,
    category_reuse_list: list[str],
    tickets: list[Ticket],
) -> list[dict[str, str]]:
    request_payload = {
        "category_reuse_list": category_reuse_list,
        "tickets": [ticket_payload(ticket) for ticket in tickets],
    }
    return [
        {"role": "system", "content": prompt_text},
        {
            "role": "user",
            "content": (
                "Classify the tickets in this JSON payload. Return only the requested JSON.\n"
                f"{json.dumps(request_payload, ensure_ascii=False)}"
            ),
        },
    ]


def extract_json_response(text: str | None) -> dict[str, Any]:
    if text is None or not text.strip():
        raise TicketClassificationError("The model returned an empty response.")
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped, flags=re.IGNORECASE)
        stripped = re.sub(r"\s*```$", "", stripped)
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start < 0 or end <= start:
            raise TicketClassificationError("The model did not return valid JSON.") from None
        try:
            parsed = json.loads(stripped[start : end + 1])
        except json.JSONDecodeError:
            raise TicketClassificationError("The model did not return valid JSON.") from None
    if isinstance(parsed, list):
        return {"tickets": parsed}
    if not isinstance(parsed, dict):
        raise TicketClassificationError("The model returned an unsupported JSON shape.")
    return parsed


def parsed_rows_by_ticket(response_text: str | None) -> dict[str, dict[str, Any]]:
    parsed = extract_json_response(response_text)
    rows = parsed.get("tickets")
    if not isinstance(rows, list):
        raise TicketClassificationError("The model JSON must contain a tickets array.")
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        ticket_number = clean_label(row.get("ticket_number"))
        if ticket_number:
            result[ticket_number] = row
    return result


def upsert_success_row(
    db: Session,
    *,
    existing_row: GenAITicketClassification | None,
    ticket: Ticket,
    customer_id: UUID | None,
    month_key: str,
    ticket_hash: str,
    prompt_version: int,
    model_name: str | None,
    classification: dict[str, Any],
    metadata: dict[str, Any],
) -> GenAITicketClassification:
    category = clean_label(classification.get("genai_category"))
    metadata_for_row = dict(metadata)
    if category is None:
        category = FALLBACK_CATEGORY
        metadata_for_row["category_fallback"] = "missing_model_category"
    row = existing_row or GenAITicketClassification(
        project_id=ticket.project_id,
        ticket_number=ticket.ticket_number,
        analysis_month=month_key,
    )
    row.customer_id = customer_id
    row.ticket_type = ticket.ticket_type
    row.input_hash = ticket_hash
    row.prompt_key = PROMPT_KEY
    row.prompt_version = prompt_version
    row.model_name = model_name
    row.status = "success"
    row.category_quality = normalize_category_quality(
        classification.get("category_quality"),
        category_was_blank=not bool(compact_text(ticket.category, max_chars=255)),
    )
    row.genai_category = category
    row.genai_subcategory_1 = clean_label(classification.get("genai_subcategory_1"))
    row.genai_subcategory_2 = clean_label(classification.get("genai_subcategory_2"))
    row.confidence = normalize_confidence(classification.get("confidence"))
    row.metadata_json = metadata_for_row
    row.error_message = None
    row.processed_at = datetime.now(UTC)
    db.add(row)
    return row


def upsert_error_row(
    db: Session,
    *,
    existing_row: GenAITicketClassification | None,
    ticket: Ticket,
    customer_id: UUID | None,
    month_key: str,
    ticket_hash: str,
    prompt_version: int,
    model_name: str | None,
    error_message: str,
    metadata: dict[str, Any],
) -> GenAITicketClassification:
    row = existing_row or GenAITicketClassification(
        project_id=ticket.project_id,
        ticket_number=ticket.ticket_number,
        analysis_month=month_key,
    )
    row.customer_id = customer_id
    row.ticket_type = ticket.ticket_type
    row.input_hash = ticket_hash
    row.prompt_key = PROMPT_KEY
    row.prompt_version = prompt_version
    row.model_name = model_name
    row.status = "error"
    row.category_quality = None
    row.genai_category = None
    row.genai_subcategory_1 = None
    row.genai_subcategory_2 = None
    row.confidence = None
    row.metadata_json = metadata
    row.error_message = error_message[:2000]
    row.processed_at = datetime.now(UTC)
    db.add(row)
    return row


def validate_config(config: GenAIConfig) -> None:
    if not config.is_enabled:
        raise TicketClassificationError(
            "GenAI is disabled. Enable GenAI and configure a model before running enrichment.",
        )
    if not config.model_name or not config.model_name.strip():
        raise TicketClassificationError("Model name is not configured for GenAI.")


def effective_ticket_classification_config(config: GenAIConfig) -> GenAIConfig:
    model_override = (get_settings().genai_ticket_classification_model_name or "").strip()
    max_output_tokens_override = get_settings().genai_ticket_classification_max_output_tokens
    if not model_override and not max_output_tokens_override:
        return config
    return GenAIConfig(
        is_enabled=config.is_enabled,
        provider=config.provider,
        model_name=model_override or config.model_name,
        temperature=config.temperature,
        top_p=config.top_p,
        max_output_tokens=max_output_tokens_override or config.max_output_tokens,
        timeout_seconds=config.timeout_seconds,
        max_tool_calls=config.max_tool_calls,
        allow_recommendations=config.allow_recommendations,
        allow_chart_generation=config.allow_chart_generation,
        response_style=config.response_style,
    )


def project_customer_id(db: Session, project_id: UUID) -> UUID:
    customer_id = db.execute(
        select(Project.client_id).where(Project.id == project_id),
    ).scalar_one_or_none()
    if customer_id is None:
        raise TicketClassificationError("Project was not found.")
    return customer_id


def run_ticket_classification(
    db: Session,
    request: TicketClassificationRunRequest,
) -> dict[str, Any]:
    month_key = validate_month_key(request.analysis_month)
    batch_size = clamp_batch_size(request.batch_size)
    batch_limit = clamp_batch_limit(request.batch_limit)
    customer_id = project_customer_id(db, request.project_id)
    config = effective_ticket_classification_config(get_or_create_config(db))
    validate_config(config)
    model_name = provider_model_name(config)
    prompt_text, prompt_version = prompt_text_and_version(db)
    fingerprint = prompt_fingerprint(prompt_text)
    existing_rows = existing_rows_for_month(db, request.project_id, month_key)
    tickets = db.execute(eligible_ticket_statement(request.project_id, month_key)).scalars().all()
    eligible_count = len(tickets)

    tickets_to_process: list[tuple[Ticket, str, GenAITicketClassification | None]] = []
    skipped_cached_count = 0
    for ticket in tickets:
        ticket_hash = input_hash_for_ticket(
            ticket,
            model_name=model_name,
            prompt_version=prompt_version,
            prompt_fingerprint_value=fingerprint,
        )
        existing_row = existing_rows.get(ticket.ticket_number)
        if (
            existing_row is not None
            and existing_row.status == "success"
            and existing_row.input_hash == ticket_hash
            and not request.force_reprocess
        ):
            skipped_cached_count += 1
            continue
        tickets_to_process.append((ticket, ticket_hash, existing_row))

    total_batches_to_process = (
        (len(tickets_to_process) + batch_size - 1) // batch_size if tickets_to_process else 0
    )
    request_tickets_to_process = (
        tickets_to_process[: batch_limit * batch_size] if batch_limit else tickets_to_process
    )

    processed_count = 0
    failed_count = 0
    prompt_tokens = 0
    completion_tokens = 0
    estimated_cost = 0.0
    duration_ms = 0
    category_reuse_list = reusable_categories(db, request.project_id)
    run_id = (request.run_id or "").strip() or str(uuid4())
    processed_batch_count = 0

    for index in range(0, len(request_tickets_to_process), batch_size):
        batch = request_tickets_to_process[index : index + batch_size]
        batch_tickets = [ticket for ticket, _ticket_hash, _existing_row in batch]
        messages = build_messages(
            prompt_text=prompt_text,
            category_reuse_list=category_reuse_list,
            tickets=batch_tickets,
        )
        result: LLMCompletionResult = chat_completion(config, messages)
        create_usage_log(
            db,
            operation="ticket_classification_enrichment",
            status="success" if result.ok else "error",
            provider=config.provider,
            model_name=config.model_name,
            question=f"{month_key}: {len(batch_tickets)} ticket classification rows",
            customer_id=customer_id,
            project_id=request.project_id,
            tools_used_json={
                "run_id": run_id,
                "prompt_key": PROMPT_KEY,
                "batch_size": len(batch_tickets),
                "ticket_count": len(batch_tickets),
                "analysis_month": month_key,
                "force_reprocess": request.force_reprocess,
                "batch_limit": batch_limit,
            },
            prompt_tokens=result.prompt_tokens,
            completion_tokens=result.completion_tokens,
            estimated_cost=result.estimated_cost,
            duration_ms=result.duration_ms,
            error_message=result.error_message,
        )
        prompt_tokens += result.prompt_tokens or 0
        completion_tokens += result.completion_tokens or 0
        estimated_cost += result.estimated_cost or 0.0
        duration_ms += result.duration_ms or 0
        metadata = {
            "prompt_fingerprint": fingerprint,
            "batch_ticket_count": len(batch_tickets),
            "category_reuse_count": len(category_reuse_list),
        }
        if not result.ok:
            error = result.error_message or "The model request failed."
            for ticket, ticket_hash, existing_row in batch:
                upsert_error_row(
                    db,
                    existing_row=existing_row,
                    ticket=ticket,
                    customer_id=customer_id,
                    month_key=month_key,
                    ticket_hash=ticket_hash,
                    prompt_version=prompt_version,
                    model_name=model_name,
                    error_message=error,
                    metadata=metadata,
                )
                failed_count += 1
            db.commit()
            processed_batch_count += 1
            continue
        try:
            parsed_rows = parsed_rows_by_ticket(result.response_text)
        except TicketClassificationError as exc:
            parse_error_message = str(exc)
            if result.completion_tokens and result.completion_tokens >= config.max_output_tokens:
                parse_error_message = (
                    f"{parse_error_message} The response likely reached the configured "
                    f"max output token limit ({config.max_output_tokens}). Reduce batch size or "
                    "increase GENAI_TICKET_CLASSIFICATION_MAX_OUTPUT_TOKENS."
                )
            for ticket, ticket_hash, existing_row in batch:
                upsert_error_row(
                    db,
                    existing_row=existing_row,
                    ticket=ticket,
                    customer_id=customer_id,
                    month_key=month_key,
                    ticket_hash=ticket_hash,
                    prompt_version=prompt_version,
                    model_name=model_name,
                    error_message=parse_error_message,
                    metadata=metadata,
                )
                failed_count += 1
            db.commit()
            processed_batch_count += 1
            continue

        for ticket, ticket_hash, existing_row in batch:
            classification = parsed_rows.get(ticket.ticket_number)
            if classification is None:
                upsert_error_row(
                    db,
                    existing_row=existing_row,
                    ticket=ticket,
                    customer_id=customer_id,
                    month_key=month_key,
                    ticket_hash=ticket_hash,
                    prompt_version=prompt_version,
                    model_name=model_name,
                    error_message="The model response did not include this ticket.",
                    metadata=metadata,
                )
                failed_count += 1
                continue
            try:
                upsert_success_row(
                    db,
                    existing_row=existing_row,
                    ticket=ticket,
                    customer_id=customer_id,
                    month_key=month_key,
                    ticket_hash=ticket_hash,
                    prompt_version=prompt_version,
                    model_name=model_name,
                    classification=classification,
                    metadata=metadata,
                )
                processed_count += 1
            except TicketClassificationError as exc:
                upsert_error_row(
                    db,
                    existing_row=existing_row,
                    ticket=ticket,
                    customer_id=customer_id,
                    month_key=month_key,
                    ticket_hash=ticket_hash,
                    prompt_version=prompt_version,
                    model_name=model_name,
                    error_message=str(exc),
                    metadata=metadata,
                )
                failed_count += 1
        db.commit()
        processed_batch_count += 1
        category_reuse_list = reusable_categories(db, request.project_id)

    summary = ticket_classification_summary(db, request.project_id, month_key)
    usage_run = ticket_classification_usage_run(db, request.project_id, month_key, run_id)
    remaining_ticket_count = max(
        eligible_count - summary["analyzed_ticket_count"],
        0,
    )
    return {
        "project_id": request.project_id,
        "analysis_month": month_key,
        "eligible_ticket_count": eligible_count,
        "processed_count": processed_count,
        "skipped_cached_count": skipped_cached_count,
        "skipped_error_count": 0,
        "failed_count": failed_count,
        "remaining_ticket_count": remaining_ticket_count,
        "processed_batch_count": processed_batch_count,
        "total_batch_count": total_batches_to_process,
        "summary": summary,
        "usage": {
            "prompt_tokens": prompt_tokens or None,
            "completion_tokens": completion_tokens or None,
            "estimated_cost": estimated_cost or None,
            "duration_ms": duration_ms or None,
        },
        "usage_run": usage_run,
    }


def ticket_classification_summary(
    db: Session,
    project_id: UUID,
    analysis_month: str,
) -> dict[str, Any]:
    month_key = validate_month_key(analysis_month)
    eligible_count = eligible_ticket_count(db, project_id, month_key)
    base_filters = (
        GenAITicketClassification.project_id == project_id,
        GenAITicketClassification.analysis_month == month_key,
    )
    success_filters = (*base_filters, GenAITicketClassification.status == "success")
    totals = db.execute(
        select(
            func.count().filter(GenAITicketClassification.status == "success"),
            func.count().filter(GenAITicketClassification.status == "error"),
            func.count(func.distinct(GenAITicketClassification.genai_category)).filter(
                and_(
                    GenAITicketClassification.status == "success",
                    GenAITicketClassification.genai_category.is_not(None),
                ),
            ),
            func.count(func.distinct(GenAITicketClassification.genai_subcategory_1)).filter(
                and_(
                    GenAITicketClassification.status == "success",
                    GenAITicketClassification.genai_subcategory_1.is_not(None),
                ),
            ),
            func.count(func.distinct(GenAITicketClassification.genai_subcategory_2)).filter(
                and_(
                    GenAITicketClassification.status == "success",
                    GenAITicketClassification.genai_subcategory_2.is_not(None),
                ),
            ),
            func.max(GenAITicketClassification.processed_at),
        ).where(*base_filters),
    ).one()
    incident_count = db.execute(
        select(func.count())
        .select_from(GenAITicketClassification)
        .where(*success_filters, func.upper(GenAITicketClassification.ticket_type) == "INCIDENT"),
    ).scalar_one()
    sc_task_count = db.execute(
        select(func.count())
        .select_from(GenAITicketClassification)
        .where(
            *success_filters,
            func.upper(GenAITicketClassification.ticket_type) == "SERVICE_CATALOG_TASK",
        ),
    ).scalar_one()
    quality_rows = db.execute(
        select(GenAITicketClassification.category_quality, func.count())
        .where(*success_filters)
        .group_by(GenAITicketClassification.category_quality),
    ).all()
    category_quality_counts = {
        quality or "Not assessed": int(count or 0) for quality, count in quality_rows
    }
    return {
        "project_id": project_id,
        "analysis_month": month_key,
        "eligible_ticket_count": eligible_count,
        "analyzed_ticket_count": int(totals[0] or 0),
        "error_ticket_count": int(totals[1] or 0),
        "category_count": int(totals[2] or 0),
        "subcategory_1_count": int(totals[3] or 0),
        "subcategory_2_count": int(totals[4] or 0),
        "incident_count": int(incident_count or 0),
        "sc_task_count": int(sc_task_count or 0),
        "last_processed_at": totals[5],
        "category_quality_counts": category_quality_counts,
    }


def ticket_classification_pivot(
    db: Session,
    project_id: UUID,
    analysis_month: str,
) -> dict[str, Any]:
    month_key = validate_month_key(analysis_month)
    rows = db.execute(
        select(
            GenAITicketClassification.genai_category,
            GenAITicketClassification.genai_subcategory_1,
            GenAITicketClassification.genai_subcategory_2,
            func.count().label("total_count"),
            func.count()
            .filter(func.upper(GenAITicketClassification.ticket_type) == "INCIDENT")
            .label("incident_count"),
            func.count()
            .filter(func.upper(GenAITicketClassification.ticket_type) == "SERVICE_CATALOG_TASK")
            .label("sc_task_count"),
        )
        .where(
            GenAITicketClassification.project_id == project_id,
            GenAITicketClassification.analysis_month == month_key,
            GenAITicketClassification.status == "success",
        )
        .group_by(
            GenAITicketClassification.genai_category,
            GenAITicketClassification.genai_subcategory_1,
            GenAITicketClassification.genai_subcategory_2,
        )
        .order_by(
            GenAITicketClassification.genai_category.asc(),
            GenAITicketClassification.genai_subcategory_1.asc().nullsfirst(),
            GenAITicketClassification.genai_subcategory_2.asc().nullsfirst(),
        ),
    ).all()
    return {
        "project_id": project_id,
        "analysis_month": month_key,
        "rows": [
            {
                "genai_category": category,
                "genai_subcategory_1": subcategory_1,
                "genai_subcategory_2": subcategory_2,
                "incident_count": int(incident_count or 0),
                "sc_task_count": int(sc_task_count or 0),
                "total_count": int(total_count or 0),
            }
            for (
                category,
                subcategory_1,
                subcategory_2,
                total_count,
                incident_count,
                sc_task_count,
            ) in rows
        ],
    }


def _csv_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def ticket_classification_dump_csv(
    db: Session,
    project_id: UUID,
    analysis_month: str,
) -> str:
    month_key = validate_month_key(analysis_month)
    tickets = db.execute(eligible_ticket_statement(project_id, month_key)).scalars().all()
    classification_rows = existing_rows_for_month(db, project_id, month_key)
    ticket_columns = [
        column.name
        for column in Ticket.__table__.columns
        if column.name not in TICKET_DUMP_EXCLUDED_COLUMNS
    ]
    output = io.StringIO(newline="")
    writer = csv.DictWriter(
        output,
        fieldnames=[*ticket_columns, *TICKET_DUMP_CLASSIFICATION_COLUMNS],
    )
    writer.writeheader()
    for ticket in tickets:
        classification = classification_rows.get(ticket.ticket_number)
        row = {column: _csv_value(getattr(ticket, column, None)) for column in ticket_columns}
        row.update(
            {
                "genai_category_quality": (
                    classification.category_quality if classification is not None else None
                ),
                "genai_category": (
                    classification.genai_category if classification is not None else None
                ),
                "genai_subcategory_1": (
                    classification.genai_subcategory_1 if classification is not None else None
                ),
                "genai_subcategory_2": (
                    classification.genai_subcategory_2 if classification is not None else None
                ),
                "genai_confidence": (
                    classification.confidence if classification is not None else None
                ),
                "genai_status": classification.status if classification is not None else None,
                "genai_prompt_key": (
                    classification.prompt_key if classification is not None else None
                ),
                "genai_prompt_version": (
                    classification.prompt_version if classification is not None else None
                ),
                "genai_model_name": (
                    classification.model_name if classification is not None else None
                ),
                "genai_processed_at": (
                    _csv_value(classification.processed_at)
                    if classification is not None
                    else None
                ),
                "genai_error_message": (
                    classification.error_message if classification is not None else None
                ),
            },
        )
        writer.writerow(row)
    return output.getvalue()


def _metadata_from_usage_log(row: GenAIUsageLog) -> dict[str, Any]:
    return row.tools_used_json if isinstance(row.tools_used_json, dict) else {}


def _sum_optional(values: list[int | float | None]) -> int | float | None:
    present_values = [value for value in values if value is not None]
    if not present_values:
        return None
    return sum(present_values)


def _usage_run_from_logs(
    project_id: UUID,
    month_key: str,
    run_id: str,
    logs: list[GenAIUsageLog],
) -> dict[str, Any]:
    ordered_logs = sorted(logs, key=lambda row: row.created_at)
    prompt_tokens = _sum_optional([row.prompt_tokens for row in ordered_logs])
    completion_tokens = _sum_optional([row.completion_tokens for row in ordered_logs])
    estimated_cost = _sum_optional([row.estimated_cost for row in ordered_logs])
    duration_ms = _sum_optional([row.duration_ms for row in ordered_logs])
    total_tokens = (
        int((prompt_tokens or 0) + (completion_tokens or 0))
        if prompt_tokens is not None or completion_tokens is not None
        else None
    )
    ticket_count = sum(
        int(_metadata_from_usage_log(row).get("ticket_count") or 0) for row in ordered_logs
    )
    return {
        "run_id": run_id,
        "project_id": project_id,
        "analysis_month": month_key,
        "model_name": ordered_logs[-1].model_name if ordered_logs else None,
        "provider": ordered_logs[-1].provider if ordered_logs else None,
        "prompt_tokens": int(prompt_tokens) if prompt_tokens is not None else None,
        "completion_tokens": int(completion_tokens) if completion_tokens is not None else None,
        "total_tokens": total_tokens,
        "estimated_cost": float(estimated_cost) if estimated_cost is not None else None,
        "duration_ms": int(duration_ms) if duration_ms is not None else None,
        "ticket_count": ticket_count,
        "batch_count": len(ordered_logs),
        "success_batch_count": sum(1 for row in ordered_logs if row.status == "success"),
        "error_batch_count": sum(1 for row in ordered_logs if row.status == "error"),
        "started_at": ordered_logs[0].created_at if ordered_logs else None,
        "completed_at": ordered_logs[-1].created_at if ordered_logs else None,
    }


def ticket_classification_usage_run(
    db: Session,
    project_id: UUID,
    analysis_month: str,
    run_id: str,
) -> dict[str, Any] | None:
    month_key = validate_month_key(analysis_month)
    rows = db.execute(
        select(GenAIUsageLog)
        .where(
            GenAIUsageLog.project_id == project_id,
            GenAIUsageLog.operation == "ticket_classification_enrichment",
        )
        .order_by(GenAIUsageLog.created_at.desc())
        .limit(1000),
    ).scalars()
    logs = [
        row
        for row in rows
        if _metadata_from_usage_log(row).get("analysis_month") == month_key
        and _metadata_from_usage_log(row).get("run_id") == run_id
    ]
    if not logs:
        return None
    return _usage_run_from_logs(project_id, month_key, run_id, logs)


def ticket_classification_usage_runs(
    db: Session,
    project_id: UUID,
    analysis_month: str,
    *,
    limit: int = 10,
) -> dict[str, Any]:
    month_key = validate_month_key(analysis_month)
    rows = db.execute(
        select(GenAIUsageLog)
        .where(
            GenAIUsageLog.project_id == project_id,
            GenAIUsageLog.operation == "ticket_classification_enrichment",
        )
        .order_by(GenAIUsageLog.created_at.desc())
        .limit(1000),
    ).scalars()
    grouped_logs: dict[str, list[GenAIUsageLog]] = {}
    for row in rows:
        metadata = _metadata_from_usage_log(row)
        if metadata.get("analysis_month") != month_key:
            continue
        run_id = str(metadata.get("run_id") or "")
        if not run_id:
            continue
        grouped_logs.setdefault(run_id, []).append(row)
    usage_runs = [
        _usage_run_from_logs(project_id, month_key, run_id, logs)
        for run_id, logs in grouped_logs.items()
    ]
    usage_runs.sort(
        key=lambda row: row["completed_at"] or datetime.min.replace(tzinfo=UTC),
        reverse=True,
    )
    return {
        "project_id": project_id,
        "analysis_month": month_key,
        "runs": usage_runs[: max(1, min(limit, 50))],
    }


def clear_ticket_classification(
    db: Session,
    request: TicketClassificationClearRequest,
) -> dict[str, Any]:
    month_key = validate_month_key(request.analysis_month)
    deleted_count = db.execute(
        delete(GenAITicketClassification).where(
            GenAITicketClassification.project_id == request.project_id,
            GenAITicketClassification.analysis_month == month_key,
        ),
    ).rowcount
    db.commit()
    return {
        "project_id": request.project_id,
        "analysis_month": month_key,
        "deleted_count": int(deleted_count or 0),
    }
