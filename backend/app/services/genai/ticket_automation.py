from __future__ import annotations

import csv
import hashlib
import io
import json
import logging
import re
import time
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import and_, delete, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import (
    GenAIConfig,
    GenAITicketAutomationAssessment,
    GenAITicketClassification,
    GenAIUsageLog,
    Ticket,
)
from app.services.genai.config_service import get_or_create_config
from app.services.genai.llm_client import LLMCompletionResult, chat_completion, provider_model_name
from app.services.genai.prompt_service import get_prompt_template
from app.services.genai.ticket_classification import (
    analysis_range_label,
    clean_label,
    compact_text,
    month_keys_in_range,
    normalize_confidence,
    project_customer_id,
    prompt_fingerprint,
    validate_config,
    validate_month_range,
)
from app.services.genai.ticket_clustering import _metadata_matches_analysis_range
from app.services.genai.usage_log_service import create_usage_log

progress_logger = logging.getLogger("app.services.genai.progress")
PROMPT_KEY = "ticket_automation_analysis"
OPERATION = "ticket_automation_analysis"
MAX_DESCRIPTION_CHARS = 1200
MAX_CLOSE_NOTES_CHARS = 1200
MAX_WORK_NOTES_CHARS = 1800
MAX_SUMMARY_CHARS = 4000
MAX_TEXT_FIELD_CHARS = 2000
MONTH_PATTERN = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
PAYLOAD_KEY_PATTERN = re.compile(r"[^a-z0-9]+")

AUTOMATION_POTENTIALS = {
    "High",
    "Medium",
    "Low",
    "Not Recommended",
    "Insufficient information",
}
RESOLUTION_PATHS = {
    "Problem Management",
    "IT-led automation",
    "Self-service",
    "Self-help",
    "L1.5 SOP",
    "L2/L3 resolution",
}


class TicketAutomationAnalysisError(ValueError):
    pass


def log_progress(message: str, *args: Any) -> None:
    progress_logger.info("[ticket-automation] " + message, *args)


@dataclass(frozen=True)
class TicketAutomationAnalysisRunRequest:
    project_id: UUID
    analysis_month: str
    analysis_month_to: str | None = None
    force_reprocess: bool = False
    cluster_limit: int | None = None
    run_id: str | None = None


@dataclass(frozen=True)
class TicketAutomationAnalysisClearRequest:
    project_id: UUID
    analysis_month: str
    analysis_month_to: str | None = None


@dataclass
class AutomationClusterCandidate:
    cluster_key: str
    cluster_run_id: str
    cluster_label: str
    category: str | None
    subcategory_1: str | None
    rows: list[tuple[GenAITicketClassification, Ticket]]

    @property
    def ticket_count(self) -> int:
        return len(self.rows)

    @property
    def ticket_type(self) -> str:
        counts = Counter((ticket.ticket_type or "").upper() for _row, ticket in self.rows)
        if counts.get("INCIDENT") and not counts.get("SERVICE_CATALOG_TASK"):
            return "INCIDENT"
        if counts.get("SERVICE_CATALOG_TASK") and not counts.get("INCIDENT"):
            return "SERVICE_CATALOG_TASK"
        return counts.most_common(1)[0][0] if counts else "UNKNOWN"

    @property
    def incident_count(self) -> int:
        return sum(
            1 for _row, ticket in self.rows if (ticket.ticket_type or "").upper() == "INCIDENT"
        )

    @property
    def sc_task_count(self) -> int:
        return sum(
            1
            for _row, ticket in self.rows
            if (ticket.ticket_type or "").upper() == "SERVICE_CATALOG_TASK"
        )


def hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def automation_prompt_text_and_version(db: Session) -> tuple[str, int]:
    prompt_template = get_prompt_template(db, PROMPT_KEY)
    prompt_text = (
        prompt_template.custom_prompt.strip()
        if prompt_template.is_custom_enabled
        and prompt_template.custom_prompt
        and prompt_template.custom_prompt.strip()
        else prompt_template.default_prompt
    )
    return prompt_text, prompt_template.version


def effective_automation_config(config: GenAIConfig) -> GenAIConfig:
    settings = get_settings()
    return GenAIConfig(
        is_enabled=config.is_enabled,
        provider=config.provider,
        model_name=settings.genai_ticket_automation_model_name
        or settings.genai_ticket_cluster_label_model_name
        or settings.genai_ticket_classification_model_name
        or config.model_name,
        temperature=config.temperature,
        top_p=config.top_p,
        max_output_tokens=(
            settings.genai_ticket_automation_max_output_tokens or config.max_output_tokens
        ),
        timeout_seconds=config.timeout_seconds,
        max_tool_calls=config.max_tool_calls,
        allow_recommendations=config.allow_recommendations,
        allow_chart_generation=config.allow_chart_generation,
        response_style=config.response_style,
    )


def clamp_cluster_limit(value: int | None) -> int:
    settings = get_settings()
    configured = value or settings.genai_ticket_automation_clusters_per_request
    return max(1, min(int(configured), 50))


def representative_ticket_limit() -> int:
    settings = get_settings()
    return max(1, min(int(settings.genai_ticket_automation_representative_ticket_count), 25))


def classification_metadata(row: GenAITicketClassification) -> dict[str, Any]:
    return dict(row.metadata_json) if isinstance(row.metadata_json, dict) else {}


def normalized_payload_key(value: str) -> str:
    return PAYLOAD_KEY_PATTERN.sub("", value.lower())


def payload_value(ticket: Ticket, keys: tuple[str, ...]) -> Any:
    payload = ticket.normalized_payload if isinstance(ticket.normalized_payload, dict) else {}
    sections = (
        payload.get("mapped_fields"),
        payload.get("raw_payload_json"),
        payload.get("unmapped_fields"),
    )
    normalized_keys = {normalized_payload_key(key) for key in keys}
    for section in sections:
        if not isinstance(section, dict):
            continue
        for key in keys:
            if key in section and section[key] not in (None, ""):
                return section[key]
        for section_key, section_value in section.items():
            if (
                isinstance(section_key, str)
                and normalized_payload_key(section_key) in normalized_keys
                and section_value not in (None, "")
            ):
                return section_value
    return None


def field_text(
    ticket: Ticket,
    *,
    direct_attrs: tuple[str, ...] = (),
    payload_keys: tuple[str, ...] = (),
    max_chars: int = MAX_TEXT_FIELD_CHARS,
) -> str | None:
    for attr in direct_attrs:
        value = getattr(ticket, attr, None)
        text = compact_text(value, max_chars=max_chars)
        if text:
            return text
    value = payload_value(ticket, payload_keys)
    return compact_text(value, max_chars=max_chars)


def ticket_evidence_payload(ticket: Ticket) -> dict[str, Any]:
    close_notes = field_text(
        ticket,
        payload_keys=(
            "close_notes",
            "close notes",
            "close_note",
            "resolution_notes",
            "resolution notes",
            "resolved_notes",
            "fix_notes",
        ),
        max_chars=MAX_CLOSE_NOTES_CHARS,
    )
    work_notes = field_text(
        ticket,
        payload_keys=(
            "work_notes",
            "work notes",
            "comments_and_work_notes",
            "comments and work notes",
            "activity",
            "activity_notes",
        ),
        max_chars=MAX_WORK_NOTES_CHARS,
    )
    business_service = field_text(
        ticket,
        direct_attrs=("business_service", "business_service_ci_name", "cmdb_ci"),
        payload_keys=("business_service", "business service", "configuration_item", "cmdb_ci"),
        max_chars=255,
    )
    return {
        "ticket_number": ticket.ticket_number,
        "ticket_type": ticket.ticket_type,
        "business_service": business_service,
        "short_description": field_text(
            ticket,
            direct_attrs=("short_description",),
            payload_keys=("short_description", "short description", "title"),
            max_chars=500,
        ),
        "description": field_text(
            ticket,
            direct_attrs=("description",),
            payload_keys=("description", "details", "detailed_description"),
            max_chars=MAX_DESCRIPTION_CHARS,
        ),
        "close_notes": close_notes,
        "work_notes": work_notes,
    }


def evidence_richness(payload: dict[str, Any]) -> tuple[int, int, int, str]:
    close_len = len(str(payload.get("close_notes") or ""))
    work_len = len(str(payload.get("work_notes") or ""))
    desc_len = len(str(payload.get("description") or ""))
    short_len = len(str(payload.get("short_description") or ""))
    return (close_len + work_len, desc_len + short_len, close_len, payload["ticket_number"])


def representative_tickets_for_candidate(
    candidate: AutomationClusterCandidate,
    *,
    limit: int,
) -> list[dict[str, Any]]:
    payloads = [ticket_evidence_payload(ticket) for _row, ticket in candidate.rows]
    payloads.sort(key=evidence_richness, reverse=True)
    return payloads[:limit]


def business_service_counts(candidate: AutomationClusterCandidate) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for _row, ticket in candidate.rows:
        service = field_text(
            ticket,
            direct_attrs=("business_service", "business_service_ci_name", "cmdb_ci"),
            payload_keys=("business_service", "business service", "configuration_item", "cmdb_ci"),
            max_chars=255,
        )
        counter[service or "Unknown"] += 1
    return dict(counter.most_common(10))


def cluster_input_hash(
    candidate: AutomationClusterCandidate,
    *,
    representative_tickets: list[dict[str, Any]],
    business_services: dict[str, int],
    model_name: str | None,
    prompt_version: int,
    prompt_fingerprint_value: str,
) -> str:
    payload = {
        "cluster_key": candidate.cluster_key,
        "cluster_run_id": candidate.cluster_run_id,
        "cluster_label": candidate.cluster_label,
        "category": candidate.category,
        "subcategory_1": candidate.subcategory_1,
        "ticket_numbers": sorted(ticket.ticket_number for _row, ticket in candidate.rows),
        "ticket_count": candidate.ticket_count,
        "business_services": business_services,
        "representative_tickets": representative_tickets,
        "model_name": model_name,
        "prompt_version": prompt_version,
        "prompt_fingerprint": prompt_fingerprint_value,
    }
    return hash_text(json.dumps(payload, sort_keys=True, ensure_ascii=False))


def valid_cluster_label(label: str | None) -> str | None:
    cleaned = compact_text(label, max_chars=255)
    if not cleaned:
        return None
    if cleaned.lower().startswith("rare-"):
        return None
    return cleaned


def automation_cluster_candidates(
    db: Session,
    *,
    project_id: UUID,
    analysis_month: str,
    analysis_month_to: str,
) -> list[AutomationClusterCandidate]:
    month_keys = month_keys_in_range(analysis_month, analysis_month_to)
    rows = db.execute(
        select(GenAITicketClassification, Ticket)
        .join(
            Ticket,
            and_(
                Ticket.project_id == GenAITicketClassification.project_id,
                Ticket.ticket_number == GenAITicketClassification.ticket_number,
            ),
        )
        .where(
            GenAITicketClassification.project_id == project_id,
            GenAITicketClassification.analysis_month.in_(month_keys),
            GenAITicketClassification.status == "success",
            GenAITicketClassification.genai_subcategory_2.is_not(None),
        ),
    ).all()

    grouped: dict[tuple[str, str], AutomationClusterCandidate] = {}
    for classification, ticket in rows:
        metadata = classification_metadata(classification)
        if metadata.get("cluster_level_3_rare") is True:
            continue
        if metadata.get("cluster_level_3_llm_label_skipped") is True:
            continue
        label = valid_cluster_label(classification.genai_subcategory_2)
        if not label:
            continue
        cluster_key = compact_text(metadata.get("cluster_level_3"), max_chars=80)
        if not cluster_key:
            cluster_key = compact_text(classification.genai_subcategory_2_cluster_id, max_chars=80)
        if not cluster_key:
            continue
        cluster_run_id = compact_text(metadata.get("run_id"), max_chars=80) or "unknown"
        group_key = (cluster_run_id, cluster_key)
        candidate = grouped.get(group_key)
        if candidate is None:
            candidate = AutomationClusterCandidate(
                cluster_key=cluster_key,
                cluster_run_id=cluster_run_id,
                cluster_label=label,
                category=classification.genai_category,
                subcategory_1=classification.genai_subcategory_1,
                rows=[],
            )
            grouped[group_key] = candidate
        candidate.rows.append((classification, ticket))

    candidates = [
        candidate for candidate in grouped.values() if candidate.ticket_count >= 3
    ]
    candidates.sort(
        key=lambda candidate: (
            -candidate.ticket_count,
            candidate.ticket_type,
            candidate.cluster_label.lower(),
            candidate.cluster_key,
        ),
    )
    return candidates


def build_automation_messages(
    *,
    prompt_text: str,
    candidate: AutomationClusterCandidate,
    representative_tickets: list[dict[str, Any]],
    business_services: dict[str, int],
) -> list[dict[str, str]]:
    payload = {
        "cluster": {
            "cluster_key": candidate.cluster_key,
            "cluster_run_id": candidate.cluster_run_id,
            "subcategory_2_label": candidate.cluster_label,
            "category": candidate.category,
            "subcategory_1": candidate.subcategory_1,
            "ticket_type": candidate.ticket_type,
            "ticket_count": candidate.ticket_count,
            "incident_count": candidate.incident_count,
            "sc_task_count": candidate.sc_task_count,
            "business_services": business_services,
        },
        "representative_tickets": representative_tickets,
    }
    return [
        {"role": "system", "content": prompt_text},
        {
            "role": "user",
            "content": (
                "Assess the automation opportunity for this SubCategory-2 cluster. "
                "Return only the requested JSON object.\n"
                f"{json.dumps(payload, ensure_ascii=False)}"
            ),
        },
    ]


def parse_automation_response(response_text: str | None) -> dict[str, Any]:
    if not response_text or not response_text.strip():
        raise TicketAutomationAnalysisError("The automation analysis model returned no response.")
    text = response_text.strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise TicketAutomationAnalysisError(
                "The automation analysis model did not return valid JSON.",
            ) from None
        parsed = json.loads(text[start : end + 1])
    if not isinstance(parsed, dict):
        raise TicketAutomationAnalysisError(
            "The automation analysis response must be a JSON object.",
        )
    return parsed


def normalize_automation_potential(value: Any) -> str:
    cleaned = clean_label(value, max_chars=40)
    if cleaned in AUTOMATION_POTENTIALS:
        return cleaned
    lookup = {item.lower(): item for item in AUTOMATION_POTENTIALS}
    if cleaned and cleaned.lower() in lookup:
        return lookup[cleaned.lower()]
    return "Insufficient information"


def normalize_resolution_path(value: Any) -> str:
    cleaned = clean_label(value, max_chars=80)
    if cleaned in RESOLUTION_PATHS:
        return cleaned
    lookup = {item.lower(): item for item in RESOLUTION_PATHS}
    if cleaned and cleaned.lower() in lookup:
        return lookup[cleaned.lower()]
    return "L2/L3 resolution"


def text_or_none(value: Any, *, max_chars: int = MAX_SUMMARY_CHARS) -> str | None:
    return compact_text(value, max_chars=max_chars)


def _existing_assessments_for_period(
    db: Session,
    *,
    project_id: UUID,
    analysis_month: str,
    analysis_month_to: str,
) -> dict[tuple[str, str], GenAITicketAutomationAssessment]:
    rows = db.execute(
        select(GenAITicketAutomationAssessment).where(
            GenAITicketAutomationAssessment.project_id == project_id,
            GenAITicketAutomationAssessment.analysis_month == analysis_month,
            GenAITicketAutomationAssessment.analysis_month_to == analysis_month_to,
        ),
    ).scalars()
    return {(row.cluster_run_id, row.cluster_key): row for row in rows}


def save_automation_success(
    db: Session,
    *,
    existing_row: GenAITicketAutomationAssessment | None,
    project_id: UUID,
    customer_id: UUID | None,
    analysis_month: str,
    analysis_month_to: str,
    run_id: str,
    candidate: AutomationClusterCandidate,
    input_hash: str,
    prompt_version: int,
    model_name: str | None,
    parsed: dict[str, Any],
    representative_tickets: list[dict[str, Any]],
    business_services: dict[str, int],
    prompt_fingerprint_value: str,
) -> GenAITicketAutomationAssessment:
    row = existing_row or GenAITicketAutomationAssessment(
        customer_id=customer_id,
        project_id=project_id,
        analysis_month=analysis_month,
        analysis_month_to=analysis_month_to,
        cluster_run_id=candidate.cluster_run_id,
        cluster_key=candidate.cluster_key,
    )
    row.customer_id = customer_id
    row.run_id = run_id
    row.cluster_label = candidate.cluster_label
    row.category = candidate.category
    row.subcategory_1 = candidate.subcategory_1
    row.ticket_type = candidate.ticket_type
    row.ticket_count = candidate.ticket_count
    row.incident_count = candidate.incident_count
    row.sc_task_count = candidate.sc_task_count
    row.input_hash = input_hash
    row.prompt_key = PROMPT_KEY
    row.prompt_version = prompt_version
    row.model_name = model_name
    row.status = "success"
    row.automation_potential = normalize_automation_potential(
        parsed.get("automation_potential"),
    )
    row.recommended_resolution_path = normalize_resolution_path(
        parsed.get("recommended_resolution_path"),
    )
    row.primary_automation_type = text_or_none(
        parsed.get("primary_automation_type"),
        max_chars=120,
    )
    row.pattern_summary = text_or_none(parsed.get("pattern_summary"))
    row.current_resolution_summary = text_or_none(parsed.get("current_resolution_summary"))
    row.likely_root_cause = text_or_none(parsed.get("likely_root_cause"))
    row.automation_recommendation = text_or_none(parsed.get("automation_recommendation"))
    row.implementation_approach = text_or_none(parsed.get("implementation_approach"))
    row.prerequisites = text_or_none(parsed.get("prerequisites"))
    row.expected_benefits = text_or_none(parsed.get("expected_benefits"))
    row.risks_or_constraints = text_or_none(parsed.get("risks_or_constraints"))
    row.confidence = normalize_confidence(parsed.get("confidence"))
    row.business_services_json = business_services
    row.representative_tickets_json = representative_tickets
    row.evidence_json = {
        "evidence_from_tickets": parsed.get("evidence_from_tickets") or [],
        "generic_knowledge_inferences": parsed.get("generic_knowledge_inferences") or [],
    }
    row.metadata_json = {
        "run_id": run_id,
        "cluster_run_id": candidate.cluster_run_id,
        "cluster_key": candidate.cluster_key,
        "analysis_month_from": analysis_month,
        "analysis_month_to": analysis_month_to,
        "prompt_fingerprint": prompt_fingerprint_value,
        "representative_ticket_count": len(representative_tickets),
        "source_ticket_numbers": sorted(ticket.ticket_number for _row, ticket in candidate.rows),
    }
    row.error_message = None
    row.processed_at = datetime.now(UTC)
    db.add(row)
    return row


def save_automation_error(
    db: Session,
    *,
    existing_row: GenAITicketAutomationAssessment | None,
    project_id: UUID,
    customer_id: UUID | None,
    analysis_month: str,
    analysis_month_to: str,
    run_id: str,
    candidate: AutomationClusterCandidate,
    input_hash: str,
    prompt_version: int,
    model_name: str | None,
    representative_tickets: list[dict[str, Any]],
    business_services: dict[str, int],
    prompt_fingerprint_value: str,
    error_message: str,
) -> GenAITicketAutomationAssessment:
    row = existing_row or GenAITicketAutomationAssessment(
        customer_id=customer_id,
        project_id=project_id,
        analysis_month=analysis_month,
        analysis_month_to=analysis_month_to,
        cluster_run_id=candidate.cluster_run_id,
        cluster_key=candidate.cluster_key,
    )
    row.customer_id = customer_id
    row.run_id = run_id
    row.cluster_label = candidate.cluster_label
    row.category = candidate.category
    row.subcategory_1 = candidate.subcategory_1
    row.ticket_type = candidate.ticket_type
    row.ticket_count = candidate.ticket_count
    row.incident_count = candidate.incident_count
    row.sc_task_count = candidate.sc_task_count
    row.input_hash = input_hash
    row.prompt_key = PROMPT_KEY
    row.prompt_version = prompt_version
    row.model_name = model_name
    row.status = "error"
    row.automation_potential = None
    row.recommended_resolution_path = None
    row.primary_automation_type = None
    row.business_services_json = business_services
    row.representative_tickets_json = representative_tickets
    row.evidence_json = None
    row.metadata_json = {
        "run_id": run_id,
        "cluster_run_id": candidate.cluster_run_id,
        "cluster_key": candidate.cluster_key,
        "analysis_month_from": analysis_month,
        "analysis_month_to": analysis_month_to,
        "prompt_fingerprint": prompt_fingerprint_value,
        "representative_ticket_count": len(representative_tickets),
        "source_ticket_numbers": sorted(ticket.ticket_number for _row, ticket in candidate.rows),
    }
    row.error_message = error_message[:2000]
    row.processed_at = datetime.now(UTC)
    db.add(row)
    return row


def automation_summary(
    db: Session,
    project_id: UUID,
    analysis_month: str,
    analysis_month_to: str | None = None,
) -> dict[str, Any]:
    start_month, end_month = validate_month_range(analysis_month, analysis_month_to)
    rows = db.execute(
        select(GenAITicketAutomationAssessment).where(
            GenAITicketAutomationAssessment.project_id == project_id,
            GenAITicketAutomationAssessment.analysis_month == start_month,
            GenAITicketAutomationAssessment.analysis_month_to == end_month,
        ),
    ).scalars().all()
    success_rows = [row for row in rows if row.status == "success"]
    potential_counts = Counter(row.automation_potential or "Not assessed" for row in success_rows)
    path_counts = Counter(row.recommended_resolution_path or "Not assessed" for row in success_rows)
    return {
        "project_id": project_id,
        "analysis_month": start_month,
        "analysis_month_from": start_month,
        "analysis_month_to": end_month,
        "assessed_cluster_count": len(success_rows),
        "error_cluster_count": sum(1 for row in rows if row.status == "error"),
        "ticket_count": int(sum(row.ticket_count or 0 for row in success_rows)),
        "high_potential_count": potential_counts.get("High", 0),
        "medium_potential_count": potential_counts.get("Medium", 0),
        "low_potential_count": potential_counts.get("Low", 0),
        "not_recommended_count": potential_counts.get("Not Recommended", 0),
        "insufficient_information_count": potential_counts.get("Insufficient information", 0),
        "potential_counts": dict(potential_counts),
        "resolution_path_counts": dict(path_counts),
        "last_processed_at": max(
            (row.processed_at for row in rows if row.processed_at is not None),
            default=None,
        ),
    }


def automation_row_payload(row: GenAITicketAutomationAssessment) -> dict[str, Any]:
    return {
        "id": row.id,
        "cluster_key": row.cluster_key,
        "cluster_label": row.cluster_label,
        "category": row.category,
        "subcategory_1": row.subcategory_1,
        "ticket_type": row.ticket_type,
        "ticket_count": row.ticket_count,
        "incident_count": row.incident_count,
        "sc_task_count": row.sc_task_count,
        "automation_potential": row.automation_potential,
        "recommended_resolution_path": row.recommended_resolution_path,
        "primary_automation_type": row.primary_automation_type,
        "pattern_summary": row.pattern_summary,
        "current_resolution_summary": row.current_resolution_summary,
        "likely_root_cause": row.likely_root_cause,
        "automation_recommendation": row.automation_recommendation,
        "implementation_approach": row.implementation_approach,
        "prerequisites": row.prerequisites,
        "expected_benefits": row.expected_benefits,
        "risks_or_constraints": row.risks_or_constraints,
        "confidence": row.confidence,
        "business_services": row.business_services_json or {},
        "evidence": row.evidence_json or {},
        "status": row.status,
        "error_message": row.error_message,
        "processed_at": row.processed_at,
    }


def automation_results(
    db: Session,
    project_id: UUID,
    analysis_month: str,
    analysis_month_to: str | None = None,
) -> dict[str, Any]:
    start_month, end_month = validate_month_range(analysis_month, analysis_month_to)
    rows = db.execute(
        select(GenAITicketAutomationAssessment)
        .where(
            GenAITicketAutomationAssessment.project_id == project_id,
            GenAITicketAutomationAssessment.analysis_month == start_month,
            GenAITicketAutomationAssessment.analysis_month_to == end_month,
        )
        .order_by(
            GenAITicketAutomationAssessment.ticket_count.desc(),
            GenAITicketAutomationAssessment.cluster_label.asc(),
        ),
    ).scalars().all()
    return {
        "project_id": project_id,
        "analysis_month": start_month,
        "analysis_month_from": start_month,
        "analysis_month_to": end_month,
        "summary": automation_summary(db, project_id, start_month, end_month),
        "rows": [automation_row_payload(row) for row in rows],
    }


def _metadata_from_usage_log(row: GenAIUsageLog) -> dict[str, Any]:
    return row.tools_used_json if isinstance(row.tools_used_json, dict) else {}


def _sum_optional(values: list[int | float | None]) -> int | float | None:
    present_values = [value for value in values if value is not None]
    if not present_values:
        return None
    return sum(present_values)


def _automation_usage_run_from_logs(
    project_id: UUID,
    start_month: str,
    end_month: str,
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
        "analysis_month": start_month,
        "analysis_month_from": start_month,
        "analysis_month_to": end_month,
        "model_name": ordered_logs[-1].model_name if ordered_logs else None,
        "provider": ordered_logs[-1].provider if ordered_logs else None,
        "prompt_tokens": int(prompt_tokens) if prompt_tokens is not None else None,
        "completion_tokens": int(completion_tokens) if completion_tokens is not None else None,
        "total_tokens": total_tokens,
        "estimated_cost": float(estimated_cost) if estimated_cost is not None else None,
        "llm_model_name": ordered_logs[-1].model_name if ordered_logs else None,
        "llm_prompt_tokens": int(prompt_tokens) if prompt_tokens is not None else None,
        "llm_completion_tokens": (
            int(completion_tokens) if completion_tokens is not None else None
        ),
        "llm_total_tokens": total_tokens,
        "llm_cost": float(estimated_cost) if estimated_cost is not None else None,
        "llm_batch_count": len(ordered_logs),
        "duration_ms": int(duration_ms) if duration_ms is not None else None,
        "ticket_count": ticket_count,
        "batch_count": len(ordered_logs),
        "success_batch_count": sum(1 for row in ordered_logs if row.status == "success"),
        "error_batch_count": sum(1 for row in ordered_logs if row.status == "error"),
        "started_at": ordered_logs[0].created_at if ordered_logs else None,
        "completed_at": ordered_logs[-1].created_at if ordered_logs else None,
    }


def automation_usage_run(
    db: Session,
    project_id: UUID,
    analysis_month: str,
    run_id: str,
    analysis_month_to: str | None = None,
) -> dict[str, Any] | None:
    start_month, end_month = validate_month_range(analysis_month, analysis_month_to)
    rows = db.execute(
        select(GenAIUsageLog)
        .where(
            GenAIUsageLog.project_id == project_id,
            GenAIUsageLog.operation == OPERATION,
        )
        .order_by(GenAIUsageLog.created_at.desc())
        .limit(2000),
    ).scalars()
    logs = [
        row
        for row in rows
        if (metadata := _metadata_from_usage_log(row)).get("run_id") == run_id
        and _metadata_matches_analysis_range(metadata, start_month, end_month)
    ]
    if not logs:
        return None
    return _automation_usage_run_from_logs(project_id, start_month, end_month, run_id, logs)


def automation_usage_runs(
    db: Session,
    project_id: UUID,
    analysis_month: str,
    *,
    analysis_month_to: str | None = None,
    limit: int = 10,
) -> dict[str, Any]:
    start_month, end_month = validate_month_range(analysis_month, analysis_month_to)
    rows = db.execute(
        select(GenAIUsageLog)
        .where(
            GenAIUsageLog.project_id == project_id,
            GenAIUsageLog.operation == OPERATION,
        )
        .order_by(GenAIUsageLog.created_at.desc())
        .limit(2000),
    ).scalars()
    grouped_logs: dict[str, list[GenAIUsageLog]] = {}
    for row in rows:
        metadata = _metadata_from_usage_log(row)
        if not _metadata_matches_analysis_range(metadata, start_month, end_month):
            continue
        run_id = str(metadata.get("run_id") or "")
        if not run_id:
            continue
        grouped_logs.setdefault(run_id, []).append(row)
    usage_runs = [
        _automation_usage_run_from_logs(project_id, start_month, end_month, grouped_run_id, logs)
        for grouped_run_id, logs in grouped_logs.items()
    ]
    usage_runs.sort(
        key=lambda row: row["completed_at"] or datetime.min.replace(tzinfo=UTC),
        reverse=True,
    )
    return {
        "project_id": project_id,
        "analysis_month": start_month,
        "analysis_month_from": start_month,
        "analysis_month_to": end_month,
        "runs": usage_runs[: max(1, min(limit, 50))],
    }


def run_ticket_automation_analysis(
    db: Session,
    request: TicketAutomationAnalysisRunRequest,
) -> dict[str, Any]:
    run_started_at = time.perf_counter()
    start_month, end_month = validate_month_range(
        request.analysis_month,
        request.analysis_month_to,
    )
    range_label = analysis_range_label(start_month, end_month)
    customer_id = project_customer_id(db, request.project_id)
    config = effective_automation_config(get_or_create_config(db))
    validate_config(config)
    model_name = provider_model_name(config)
    prompt_text, prompt_version = automation_prompt_text_and_version(db)
    prompt_fingerprint_value = prompt_fingerprint(prompt_text)
    run_id = (request.run_id or "").strip() or str(uuid4())
    cluster_limit = clamp_cluster_limit(request.cluster_limit)
    log_progress(
        "run %s started for project %s, period %s, model %s, request cluster limit %s",
        run_id,
        request.project_id,
        range_label,
        model_name,
        cluster_limit,
    )

    if request.force_reprocess:
        log_progress(
            "run %s force reprocess requested; clearing previous automation output",
            run_id,
        )
        clear_ticket_automation_analysis(
            db,
            TicketAutomationAnalysisClearRequest(
                project_id=request.project_id,
                analysis_month=start_month,
                analysis_month_to=end_month,
            ),
        )

    log_progress("run %s selecting eligible SubCategory-2 clusters", run_id)
    candidates = automation_cluster_candidates(
        db,
        project_id=request.project_id,
        analysis_month=start_month,
        analysis_month_to=end_month,
    )
    existing_rows = _existing_assessments_for_period(
        db,
        project_id=request.project_id,
        analysis_month=start_month,
        analysis_month_to=end_month,
    )

    skipped_cached_count = 0
    candidates_to_process: list[
        tuple[
            AutomationClusterCandidate,
            list[dict[str, Any]],
            dict[str, int],
            str,
            GenAITicketAutomationAssessment | None,
        ]
    ] = []
    for candidate in candidates:
        representative_tickets = representative_tickets_for_candidate(
            candidate,
            limit=representative_ticket_limit(),
        )
        business_services = business_service_counts(candidate)
        input_hash = cluster_input_hash(
            candidate,
            representative_tickets=representative_tickets,
            business_services=business_services,
            model_name=model_name,
            prompt_version=prompt_version,
            prompt_fingerprint_value=prompt_fingerprint_value,
        )
        existing_row = existing_rows.get((candidate.cluster_run_id, candidate.cluster_key))
        if (
            not request.force_reprocess
            and existing_row is not None
            and existing_row.status == "success"
            and existing_row.input_hash == input_hash
        ):
            skipped_cached_count += 1
            continue
        candidates_to_process.append(
            (
                candidate,
                representative_tickets,
                business_services,
                input_hash,
                existing_row,
            ),
        )

    request_candidates = candidates_to_process[:cluster_limit]
    log_progress(
        (
            "run %s candidate selection complete: %s eligible clusters, "
            "%s cached, %s pending, processing %s in this request"
        ),
        run_id,
        len(candidates),
        skipped_cached_count,
        len(candidates_to_process),
        len(request_candidates),
    )
    processed_count = 0
    failed_count = 0
    prompt_tokens = 0
    completion_tokens = 0
    estimated_cost = 0.0
    duration_ms = 0

    for (
        candidate,
        representative_tickets,
        business_services,
        input_hash,
        existing_row,
    ) in request_candidates:
        cluster_number = processed_count + failed_count + 1
        log_progress(
            "run %s cluster %s/%s started: %s (%s tickets, %s representatives)",
            run_id,
            cluster_number,
            len(request_candidates),
            candidate.cluster_key,
            candidate.ticket_count,
            len(representative_tickets),
        )
        messages = build_automation_messages(
            prompt_text=prompt_text,
            candidate=candidate,
            representative_tickets=representative_tickets,
            business_services=business_services,
        )
        result: LLMCompletionResult = chat_completion(config, messages)
        create_usage_log(
            db,
            operation=OPERATION,
            status="success" if result.ok else "error",
            provider=config.provider,
            model_name=config.model_name,
            question=f"{range_label}: automation analysis for {candidate.cluster_key}",
            customer_id=customer_id,
            project_id=request.project_id,
            tools_used_json={
                "run_id": run_id,
                "prompt_key": PROMPT_KEY,
                "analysis_month": start_month,
                "analysis_month_from": start_month,
                "analysis_month_to": end_month,
                "cluster_key": candidate.cluster_key,
                "cluster_run_id": candidate.cluster_run_id,
                "ticket_count": candidate.ticket_count,
                "representative_ticket_count": len(representative_tickets),
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

        if not result.ok:
            save_automation_error(
                db,
                existing_row=existing_row,
                project_id=request.project_id,
                customer_id=customer_id,
                analysis_month=start_month,
                analysis_month_to=end_month,
                run_id=run_id,
                candidate=candidate,
                input_hash=input_hash,
                prompt_version=prompt_version,
                model_name=model_name,
                representative_tickets=representative_tickets,
                business_services=business_services,
                prompt_fingerprint_value=prompt_fingerprint_value,
                error_message=result.error_message or "The model request failed.",
            )
            db.commit()
            failed_count += 1
            log_progress(
                "run %s cluster %s/%s failed: %s",
                run_id,
                cluster_number,
                len(request_candidates),
                result.error_message or "model request failed",
            )
            continue

        try:
            parsed = parse_automation_response(result.response_text)
        except TicketAutomationAnalysisError as exc:
            save_automation_error(
                db,
                existing_row=existing_row,
                project_id=request.project_id,
                customer_id=customer_id,
                analysis_month=start_month,
                analysis_month_to=end_month,
                run_id=run_id,
                candidate=candidate,
                input_hash=input_hash,
                prompt_version=prompt_version,
                model_name=model_name,
                representative_tickets=representative_tickets,
                business_services=business_services,
                prompt_fingerprint_value=prompt_fingerprint_value,
                error_message=str(exc),
            )
            db.commit()
            failed_count += 1
            log_progress(
                "run %s cluster %s/%s parse failed: %s",
                run_id,
                cluster_number,
                len(request_candidates),
                str(exc),
            )
            continue

        save_automation_success(
            db,
            existing_row=existing_row,
            project_id=request.project_id,
            customer_id=customer_id,
            analysis_month=start_month,
            analysis_month_to=end_month,
            run_id=run_id,
            candidate=candidate,
            input_hash=input_hash,
            prompt_version=prompt_version,
            model_name=model_name,
            parsed=parsed,
            representative_tickets=representative_tickets,
            business_services=business_services,
            prompt_fingerprint_value=prompt_fingerprint_value,
        )
        db.commit()
        processed_count += 1
        log_progress(
            "run %s cluster %s/%s complete: %s potential, %s path",
            run_id,
            cluster_number,
            len(request_candidates),
            normalize_automation_potential(parsed.get("automation_potential")),
            normalize_resolution_path(parsed.get("recommended_resolution_path")),
        )

    remaining_cluster_count = max(len(candidates_to_process) - len(request_candidates), 0)
    summary = automation_summary(db, request.project_id, start_month, end_month)
    usage_run = automation_usage_run(db, request.project_id, start_month, run_id, end_month)
    log_progress(
        (
            "run %s request complete: %s processed, %s failed, %s cached, "
            "%s remaining, duration %s ms"
        ),
        run_id,
        processed_count,
        failed_count,
        skipped_cached_count,
        remaining_cluster_count,
        int((time.perf_counter() - run_started_at) * 1000),
    )
    return {
        "project_id": request.project_id,
        "analysis_month": start_month,
        "analysis_month_from": start_month,
        "analysis_month_to": end_month,
        "run_id": run_id,
        "eligible_cluster_count": len(candidates),
        "processed_count": processed_count,
        "skipped_cached_count": skipped_cached_count,
        "failed_count": failed_count,
        "remaining_cluster_count": remaining_cluster_count,
        "processed_batch_count": len(request_candidates),
        "total_batch_count": len(candidates_to_process),
        "summary": summary,
        "usage": {
            "prompt_tokens": prompt_tokens or None,
            "completion_tokens": completion_tokens or None,
            "estimated_cost": estimated_cost or None,
            "duration_ms": duration_ms or int((time.perf_counter() - run_started_at) * 1000),
        },
        "usage_run": usage_run,
    }


def clear_ticket_automation_analysis(
    db: Session,
    request: TicketAutomationAnalysisClearRequest,
) -> dict[str, Any]:
    start_month, end_month = validate_month_range(
        request.analysis_month,
        request.analysis_month_to,
    )
    deleted_count = db.execute(
        delete(GenAITicketAutomationAssessment).where(
            GenAITicketAutomationAssessment.project_id == request.project_id,
            GenAITicketAutomationAssessment.analysis_month == start_month,
            GenAITicketAutomationAssessment.analysis_month_to == end_month,
        ),
    ).rowcount
    db.commit()
    return {
        "project_id": request.project_id,
        "analysis_month": start_month,
        "analysis_month_from": start_month,
        "analysis_month_to": end_month,
        "deleted_count": int(deleted_count or 0),
    }


def automation_analysis_csv(
    db: Session,
    project_id: UUID,
    analysis_month: str,
    analysis_month_to: str | None = None,
) -> str:
    result = automation_results(db, project_id, analysis_month, analysis_month_to)
    if not result["rows"]:
        range_label = analysis_range_label(
            result["analysis_month_from"],
            result["analysis_month_to"],
        )
        raise TicketAutomationAnalysisError(
            f"No saved automation analysis rows exist for {range_label}. "
            "Run Automation Analysis before downloading the CSV.",
        )
    output = io.StringIO(newline="")
    fieldnames = [
        "cluster_key",
        "cluster_label",
        "category",
        "subcategory_1",
        "ticket_type",
        "ticket_count",
        "incident_count",
        "sc_task_count",
        "automation_potential",
        "recommended_resolution_path",
        "primary_automation_type",
        "pattern_summary",
        "current_resolution_summary",
        "likely_root_cause",
        "automation_recommendation",
        "implementation_approach",
        "prerequisites",
        "expected_benefits",
        "risks_or_constraints",
        "confidence",
        "business_services",
        "evidence_from_tickets",
        "generic_knowledge_inferences",
        "status",
        "error_message",
        "processed_at",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for row in result["rows"]:
        evidence = row.get("evidence") if isinstance(row.get("evidence"), dict) else {}
        writer.writerow(
            {
                **{field: row.get(field) for field in fieldnames},
                "business_services": json.dumps(row.get("business_services") or {}),
                "evidence_from_tickets": json.dumps(
                    evidence.get("evidence_from_tickets") or [],
                    ensure_ascii=False,
                ),
                "generic_knowledge_inferences": json.dumps(
                    evidence.get("generic_knowledge_inferences") or [],
                    ensure_ascii=False,
                ),
                "processed_at": (
                    row["processed_at"].isoformat()
                    if isinstance(row.get("processed_at"), datetime)
                    else row.get("processed_at")
                ),
            },
        )
    return output.getvalue()
