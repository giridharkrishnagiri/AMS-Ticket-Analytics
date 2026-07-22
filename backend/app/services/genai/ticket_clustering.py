from __future__ import annotations

import hashlib
import json
import logging
import math
import re
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import numpy as np
from sklearn.cluster import KMeans
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import (
    GenAIConfig,
    GenAITicketClassification,
    GenAITicketClusterLabel,
    GenAITicketEmbedding,
    GenAIUsageLog,
    Ticket,
)
from app.services.genai.config_service import get_or_create_config
from app.services.genai.llm_client import (
    LLMCompletionResult,
    chat_completion,
    embedding_request,
    provider_model_name,
)
from app.services.genai.prompt_service import get_prompt_template
from app.services.genai.ticket_classification import (
    MAX_DESCRIPTION_CHARS,
    analysis_range_label,
    clean_label,
    cluster_display_id,
    compact_text,
    eligible_ticket_statement_for_month_range,
    month_keys_in_range,
    normalize_confidence,
    project_customer_id,
    prompt_fingerprint,
    ticket_analysis_month,
    ticket_classification_summary,
    ticket_payload,
    validate_config,
    validate_month_range,
)
from app.services.genai.usage_log_service import create_usage_log

progress_logger = logging.getLogger("uvicorn.error")

PROMPT_KEY = "ticket_cluster_labeling"
OUTPUT_PROMPT_KEY = "ticket_cluster_analysis"
EMBEDDING_TEXT_VERSION = "cluster-ticket-text-v4-ticket-type-clean-description"
TICKET_TYPE_SEPARATION_PROMPT = """Ticket type rule:
- Incidents and Service Catalog Tasks are clustered separately.
- Incident labels should describe production/user-impact issues.
- Service Catalog Task labels should describe user request or fulfillment work.
- Do not reuse a label because another ticket type has similar wording unless it is truly the best
  label within the current ticket type."""
RANDOM_STATE = 42
MAX_TEXT_CHARS = 2600
MAX_REPRESENTATIVE_TEXT_CHARS = 500
TOKEN_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9_/-]{2,}")
NOISE_PATTERNS = (
    re.compile(r"\b(?:INC|SCTASK|TASK|RITM|REQ)\d+\b", re.IGNORECASE),
    re.compile(r"\b\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\b"),
    re.compile(r"\b\d{4}-\d{2}-\d{2}\b"),
    re.compile(r"\b\d{1,2}:\d{2}(?::\d{2})?\b"),
    re.compile(r"\b[A-F0-9]{16,}\b"),
)
DESCRIPTION_PERSONAL_FIELD_LABELS = (
    "best contact number",
    "business phone",
    "contact number",
    "contact no",
    "contact",
    "caller",
    "country",
    "date",
    "department",
    "e-mail",
    "email address",
    "email",
    "emp id",
    "employee id",
    "first name",
    "full name",
    "job title",
    "lan id",
    "lanid",
    "last name",
    "line manager",
    "location",
    "manager",
    "mobile number",
    "mobile",
    "name",
    "office location",
    "opened by",
    "phone number",
    "phone",
    "preferred contact",
    "requester",
    "requestor",
    "requested by",
    "submitted by",
    "telephone",
    "time",
    "user id",
    "userid",
)
DESCRIPTION_PERSONAL_FIELD_PATTERN = re.compile(
    rf"\b(?:{'|'.join(re.escape(label) for label in DESCRIPTION_PERSONAL_FIELD_LABELS)})"
    r"\s*[:=\-]\s*.*?(?=\s+[A-Za-z][A-Za-z /_-]{1,35}\s*[:=\-]|[;|\n]|$)",
    re.IGNORECASE,
)
DESCRIPTION_EMAIL_PATTERN = re.compile(
    r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
    re.IGNORECASE,
)
DESCRIPTION_PHONE_PATTERN = re.compile(r"\b(?:\+?\d[\d\s().-]{7,}\d)\b")
DESCRIPTION_GREETING_PATTERN = re.compile(
    r"^\s*(?:hi|hello|dear)\b[^,.;:\n]{0,80}[:,.;-]?\s*",
    re.IGNORECASE,
)
DESCRIPTION_SIGNATURE_PATTERN = re.compile(
    r"^\s*(?:best regards|kind regards|regards|thanks|thank you)\b.*$",
    re.IGNORECASE,
)
STOP_WORDS = {
    "about",
    "above",
    "access",
    "after",
    "again",
    "against",
    "all",
    "also",
    "and",
    "any",
    "are",
    "because",
    "been",
    "being",
    "below",
    "between",
    "but",
    "can",
    "cannot",
    "could",
    "description",
    "details",
    "does",
    "done",
    "during",
    "error",
    "from",
    "has",
    "have",
    "help",
    "how",
    "into",
    "issue",
    "not",
    "now",
    "only",
    "please",
    "request",
    "requested",
    "same",
    "service",
    "short",
    "should",
    "task",
    "that",
    "the",
    "their",
    "there",
    "this",
    "ticket",
    "unable",
    "user",
    "was",
    "were",
    "when",
    "where",
    "with",
    "would",
}


class TicketClusteringError(ValueError):
    pass


def log_progress(message: str, *args: Any) -> None:
    progress_logger.info("[ticket-cluster] " + message, *args)


@dataclass(frozen=True)
class TicketClusterRunRequest:
    project_id: UUID
    analysis_month: str
    analysis_month_to: str | None = None
    force_reprocess: bool = False
    level_1_count: int | None = None
    level_2_count: int | None = None
    level_3_count: int | None = None
    use_llm_labels: bool = True
    run_id: str | None = None


@dataclass(frozen=True)
class TicketClusterClearRequest:
    project_id: UUID
    analysis_month: str
    analysis_month_to: str | None = None


@dataclass(frozen=True)
class TicketEmbeddingClearRequest:
    project_id: UUID


@dataclass(frozen=True)
class TicketTextInput:
    ticket: Ticket
    normalized_text: str
    normalized_text_hash: str
    input_hash: str
    vector: list[float]


@dataclass
class ClusterInfo:
    key: str
    level: int
    ticket_indices: list[int]
    centroid: np.ndarray
    max_distance: float | None = None
    mean_distance: float | None = None
    parent_key: str | None = None
    child_keys: list[str] | None = None
    top_terms: list[str] | None = None
    label: str | None = None
    summary: str | None = None
    confidence: float | None = None


@dataclass
class AdaptiveLeaf:
    parent_key: str | None
    ticket_indices: list[int]
    centroid: np.ndarray
    max_distance: float
    mean_distance: float
    splittable: bool = True


def ticket_type_partition(ticket_type: str | None) -> str:
    normalized = (ticket_type or "").upper()
    if normalized == "INCIDENT":
        return "incident"
    if normalized == "SERVICE_CATALOG_TASK":
        return "sc_task"
    return "other"


def ticket_type_display(ticket_type: str | None) -> str:
    partition = ticket_type_partition(ticket_type)
    if partition == "incident":
        return "Incident"
    if partition == "sc_task":
        return "Service Catalog Task"
    return "Other Ticket"


def cluster_key_prefix(partition: str) -> str:
    if partition == "incident":
        return "INC"
    if partition == "sc_task":
        return "SCT"
    return "OTH"


def partition_input_indices(inputs: list[TicketTextInput]) -> dict[str, list[int]]:
    partitions: dict[str, list[int]] = {"incident": [], "sc_task": [], "other": []}
    for index, ticket_input in enumerate(inputs):
        partitions[ticket_type_partition(ticket_input.ticket.ticket_type)].append(index)
    return {key: indices for key, indices in partitions.items() if indices}


def split_target_count(
    partitions: dict[str, list[int]],
    target_count: int,
    *,
    maximum_by_partition: dict[str, int] | None = None,
) -> dict[str, int]:
    if not partitions or target_count <= 0:
        return {}
    maximums = {
        key: maximum_by_partition.get(key, len(indices)) if maximum_by_partition else len(indices)
        for key, indices in partitions.items()
    }
    capped_target = min(
        target_count,
        sum(maximums.values()),
    )
    allocation = {key: 0 for key in partitions}
    if capped_target <= 0:
        return allocation
    if capped_target < len(partitions):
        for key, _indices in sorted(
            partitions.items(),
            key=lambda item: len(item[1]),
            reverse=True,
        )[:capped_target]:
            allocation[key] = 1
        return allocation
    for key, maximum in maximums.items():
        if maximum > 0:
            allocation[key] = 1
    remaining = max(0, capped_target - sum(allocation.values()))
    total_items = sum(len(indices) for indices in partitions.values())
    remainders: list[tuple[float, str]] = []
    for key, indices in partitions.items():
        maximum = maximums[key]
        if maximum <= allocation[key]:
            continue
        exact = (len(indices) / total_items) * capped_target if total_items else 0
        additional = min(maximum - allocation[key], int(math.floor(exact)) - allocation[key])
        if additional > 0:
            allocation[key] += additional
            remaining -= additional
        remainders.append((exact - math.floor(exact), key))
    for _remainder, key in sorted(remainders, reverse=True):
        if remaining <= 0:
            break
        maximum = maximums[key]
        if allocation[key] < maximum:
            allocation[key] += 1
            remaining -= 1
    while remaining > 0:
        progressed = False
        for key, _indices in sorted(
            partitions.items(),
            key=lambda item: len(item[1]),
            reverse=True,
        ):
            maximum = maximums[key]
            if allocation[key] < maximum:
                allocation[key] += 1
                remaining -= 1
                progressed = True
                if remaining <= 0:
                    break
        if not progressed:
            break
    return allocation


def normalized_cluster_mode(value: str | None) -> str:
    mode = (value or "").strip().lower()
    return mode if mode in {"adaptive", "fixed"} else "adaptive"


def workbench_settings() -> dict[str, Any]:
    settings = get_settings()
    cluster_mode = normalized_cluster_mode(settings.genai_ticket_cluster_mode)
    return {
        "ticket_classification_button_enabled": settings.genai_ticket_classification_button_enabled,
        "ticket_cluster_analysis_button_enabled": (
            settings.genai_ticket_cluster_analysis_button_enabled
        ),
        "cluster_embedding_model_name": settings.genai_ticket_cluster_embedding_model_name,
        "cluster_label_model_name": settings.genai_ticket_cluster_label_model_name
        or settings.genai_ticket_classification_model_name,
        "cluster_mode": cluster_mode,
        "cluster_level_1_count": settings.genai_ticket_cluster_level_1_count,
        "cluster_level_2_count": settings.genai_ticket_cluster_level_2_count,
        "cluster_level_3_count": settings.genai_ticket_cluster_level_3_count,
        "cluster_level_1_distance_threshold": (
            settings.genai_ticket_cluster_level_1_distance_threshold
        ),
        "cluster_level_2_distance_threshold": (
            settings.genai_ticket_cluster_level_2_distance_threshold
        ),
        "cluster_level_3_distance_threshold": (
            settings.genai_ticket_cluster_level_3_distance_threshold
        ),
        "cluster_embedding_batch_size": settings.genai_ticket_cluster_embedding_batch_size,
        "cluster_label_batch_size": settings.genai_ticket_cluster_label_batch_size,
    }


def clamp_positive(value: int | None, default_value: int, *, minimum: int, maximum: int) -> int:
    if value is None:
        value = default_value
    return max(minimum, min(int(value), maximum))


def clamp_distance_threshold(value: float | None, default_value: float) -> float:
    if value is None:
        value = default_value
    return max(0.01, min(float(value), 1.5))


def derived_config(
    base_config: GenAIConfig,
    *,
    model_name: str | None,
    max_output_tokens: int | None = None,
    temperature: float | None = None,
) -> GenAIConfig:
    return GenAIConfig(
        is_enabled=base_config.is_enabled,
        provider=base_config.provider,
        model_name=model_name or base_config.model_name,
        temperature=base_config.temperature if temperature is None else temperature,
        top_p=base_config.top_p,
        max_output_tokens=max_output_tokens or base_config.max_output_tokens,
        timeout_seconds=base_config.timeout_seconds,
        max_tool_calls=base_config.max_tool_calls,
        allow_recommendations=base_config.allow_recommendations,
        allow_chart_generation=base_config.allow_chart_generation,
        response_style=base_config.response_style,
    )


def effective_embedding_config(config: GenAIConfig) -> GenAIConfig:
    settings = get_settings()
    return derived_config(
        config,
        model_name=settings.genai_ticket_cluster_embedding_model_name,
        temperature=0.0,
    )


def effective_label_config(config: GenAIConfig) -> GenAIConfig:
    settings = get_settings()
    return derived_config(
        config,
        model_name=(
            settings.genai_ticket_cluster_label_model_name
            or settings.genai_ticket_classification_model_name
            or config.model_name
        ),
        max_output_tokens=settings.genai_ticket_cluster_label_max_output_tokens
        or settings.genai_ticket_classification_max_output_tokens
        or config.max_output_tokens,
        temperature=0.1,
    )


def cleaned_description_for_embedding(value: Any) -> str:
    if value is None:
        return ""
    bounded_text = str(value)[:MAX_DESCRIPTION_CHARS]
    cleaned_lines: list[str] = []
    for raw_line in bounded_text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = raw_line.strip()
        if not line:
            continue
        if DESCRIPTION_SIGNATURE_PATTERN.match(line):
            continue
        line = DESCRIPTION_GREETING_PATTERN.sub("", line)
        line = DESCRIPTION_EMAIL_PATTERN.sub(" ", line)
        line = DESCRIPTION_PHONE_PATTERN.sub(" ", line)
        line = DESCRIPTION_PERSONAL_FIELD_PATTERN.sub(" ", line)
        line = re.sub(r"\s+", " ", line).strip(" ,;|-")
        if line:
            cleaned_lines.append(line)
    text = " ".join(cleaned_lines)
    return compact_text(text, max_chars=MAX_DESCRIPTION_CHARS) or ""


def normalized_ticket_text(ticket: Ticket) -> str:
    payload = ticket_payload(ticket)
    parts = [
        f"Ticket class: {ticket_type_display(ticket.ticket_type)}",
        f"Short description: {payload.get('short_description') or ''}",
        f"Description: {cleaned_description_for_embedding(ticket.description)}",
    ]
    text = " ".join(part for part in parts if part.strip())
    for pattern in NOISE_PATTERNS:
        text = pattern.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > MAX_TEXT_CHARS:
        text = text[:MAX_TEXT_CHARS].rstrip()
    return text or "No short description or description available"


def hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def embedding_input_hash(ticket: Ticket, normalized_text: str, embedding_model: str) -> str:
    payload = {
        "ticket_number": ticket.ticket_number,
        "ticket_type": ticket.ticket_type,
        "state": ticket.state,
        "normalized_text_hash": hash_text(normalized_text),
        "embedding_model": embedding_model,
        "text_version": EMBEDDING_TEXT_VERSION,
    }
    return hash_text(json.dumps(payload, sort_keys=True, ensure_ascii=False))


def top_terms_for_indices(
    inputs: list[TicketTextInput],
    indices: list[int],
    *,
    limit: int = 12,
) -> list[str]:
    counter: Counter[str] = Counter()
    for index in indices:
        for token in TOKEN_PATTERN.findall(inputs[index].normalized_text):
            normalized = token.strip("_/-").lower()
            if (
                len(normalized) < 3
                or normalized in STOP_WORDS
                or normalized.isdigit()
                or sum(ch.isdigit() for ch in normalized) > 8
            ):
                continue
            counter[normalized] += 1
    return [term for term, _count in counter.most_common(limit)]


def embedding_rows_by_key(
    db: Session,
    project_id: UUID,
    tickets: list[Ticket],
    embedding_model_name: str,
) -> dict[tuple[str, str], GenAITicketEmbedding]:
    if not tickets:
        return {}
    ticket_numbers = [ticket.ticket_number for ticket in tickets]
    rows = db.execute(
        select(GenAITicketEmbedding).where(
            GenAITicketEmbedding.project_id == project_id,
            GenAITicketEmbedding.embedding_model == embedding_model_name,
            GenAITicketEmbedding.ticket_number.in_(ticket_numbers),
        ),
    ).scalars()
    return {(row.ticket_number, row.input_hash): row for row in rows}


def ensure_ticket_embeddings(
    db: Session,
    *,
    project_id: UUID,
    customer_id: UUID | None,
    month_key: str,
    month_key_to: str,
    run_id: str,
    tickets: list[Ticket],
    config: GenAIConfig,
) -> tuple[list[TicketTextInput], int, int]:
    settings = get_settings()
    range_label = analysis_range_label(month_key, month_key_to)
    embedding_model = provider_model_name(config)
    existing_rows = embedding_rows_by_key(db, project_id, tickets, embedding_model)
    prepared_rows: list[tuple[Ticket, str, str, str, GenAITicketEmbedding | None]] = []
    cached_count = 0
    for ticket in tickets:
        text = normalized_ticket_text(ticket)
        text_hash = hash_text(text)
        input_hash = embedding_input_hash(ticket, text, embedding_model)
        existing_row = existing_rows.get((ticket.ticket_number, input_hash))
        if existing_row is not None:
            cached_count += 1
        prepared_rows.append((ticket, text, text_hash, input_hash, existing_row))

    pending_rows = [row for row in prepared_rows if row[4] is None]
    batch_size = clamp_positive(
        settings.genai_ticket_cluster_embedding_batch_size,
        100,
        minimum=1,
        maximum=500,
    )
    total_batches = math.ceil(len(pending_rows) / batch_size) if pending_rows else 0
    log_progress(
        "embedding cache check complete: %s tickets, %s cached, %s new, batch size %s",
        len(tickets),
        cached_count,
        len(pending_rows),
        batch_size,
    )
    for offset in range(0, len(pending_rows), batch_size):
        batch = pending_rows[offset : offset + batch_size]
        texts = [row[1] for row in batch]
        batch_number = (offset // batch_size) + 1
        log_progress(
            "embedding batch %s/%s started for %s tickets",
            batch_number,
            total_batches,
            len(batch),
        )
        result = embedding_request(config, texts)
        create_usage_log(
            db,
            operation="ticket_cluster_embedding",
            status="success" if result.ok else "error",
            provider=config.provider,
            model_name=config.model_name,
            customer_id=customer_id,
            project_id=project_id,
            question=f"{range_label}: {len(batch)} ticket embedding rows",
            tools_used_json={
                "run_id": run_id,
                "analysis_month": month_key,
                "analysis_month_from": month_key,
                "analysis_month_to": month_key_to,
                "ticket_count": len(batch),
                "embedding_model": embedding_model,
                "text_version": EMBEDDING_TEXT_VERSION,
            },
            prompt_tokens=result.prompt_tokens or result.total_tokens,
            completion_tokens=None,
            estimated_cost=result.estimated_cost,
            duration_ms=result.duration_ms,
            error_message=result.error_message,
        )
        if not result.ok or result.embeddings is None:
            db.commit()
            log_progress(
                "embedding batch %s/%s failed: %s",
                batch_number,
                total_batches,
                result.error_message or "unknown error",
            )
            raise TicketClusteringError(result.error_message or "Embedding generation failed.")
        for (ticket, text, text_hash, input_hash, _existing_row), vector in zip(
            batch,
            result.embeddings,
            strict=True,
        ):
            db.add(
                GenAITicketEmbedding(
                    customer_id=customer_id,
                    project_id=project_id,
                    ticket_number=ticket.ticket_number,
                    ticket_type=ticket.ticket_type,
                    input_hash=input_hash,
                    embedding_model=embedding_model,
                    normalized_text_hash=text_hash,
                    text_preview=compact_text(text, max_chars=1000),
                    embedding_json=vector,
                    metadata_json={"text_version": EMBEDDING_TEXT_VERSION},
                ),
            )
        db.commit()
        log_progress(
            "embedding batch %s/%s saved (%s vectors)",
            batch_number,
            total_batches,
            len(batch),
        )

    refreshed_rows = embedding_rows_by_key(db, project_id, tickets, embedding_model)
    inputs: list[TicketTextInput] = []
    for ticket, text, text_hash, input_hash, _existing_row in prepared_rows:
        row = refreshed_rows.get((ticket.ticket_number, input_hash))
        if row is None:
            raise TicketClusteringError(f"Embedding was not saved for {ticket.ticket_number}.")
        inputs.append(
            TicketTextInput(
                ticket=ticket,
                normalized_text=text,
                normalized_text_hash=text_hash,
                input_hash=input_hash,
                vector=[float(value) for value in row.embedding_json],
            ),
        )
    return inputs, cached_count, len(pending_rows)


def normalized_matrix(inputs: list[TicketTextInput]) -> np.ndarray:
    matrix = np.array([item.vector for item in inputs], dtype=float)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return matrix / norms


def cluster_labels(
    vectors: np.ndarray,
    cluster_count: int,
    *,
    weights: np.ndarray | None = None,
) -> np.ndarray:
    if len(vectors) == 0:
        return np.array([], dtype=int)
    if cluster_count <= 1 or len(vectors) == 1:
        return np.zeros(len(vectors), dtype=int)
    model = KMeans(
        n_clusters=min(cluster_count, len(vectors)),
        random_state=RANDOM_STATE,
        n_init=10,
    )
    if weights is None:
        return model.fit_predict(vectors)
    return model.fit_predict(vectors, sample_weight=weights)


def normalized_centroid(vectors: np.ndarray, weights: np.ndarray | None = None) -> np.ndarray:
    if weights is None:
        centroid = vectors.mean(axis=0)
    else:
        centroid = np.average(vectors, axis=0, weights=weights)
    norm = np.linalg.norm(centroid)
    if norm == 0:
        return centroid
    return centroid / norm


def cluster_distance_metrics(
    vectors: np.ndarray,
    indices: list[int],
    centroid: np.ndarray,
) -> tuple[float, float]:
    if not indices:
        return 0.0, 0.0
    distances = 1.0 - np.clip(vectors[indices] @ centroid, -1.0, 1.0)
    return float(np.max(distances)), float(np.mean(distances))


def ticket_distance_from_cluster_centroid(
    vectors: np.ndarray,
    ticket_index: int,
    cluster: ClusterInfo | None,
) -> float | None:
    if cluster is None:
        return None
    distance = 1.0 - np.clip(float(vectors[ticket_index] @ cluster.centroid), -1.0, 1.0)
    return float(distance)


def new_adaptive_leaf(
    *,
    parent_key: str | None,
    indices: list[int],
    vectors: np.ndarray,
) -> AdaptiveLeaf:
    centroid = normalized_centroid(vectors[indices])
    max_distance, mean_distance = cluster_distance_metrics(vectors, indices, centroid)
    return AdaptiveLeaf(
        parent_key=parent_key,
        ticket_indices=sorted(indices),
        centroid=centroid,
        max_distance=max_distance,
        mean_distance=mean_distance,
    )


def split_leaf_once(leaf: AdaptiveLeaf, vectors: np.ndarray) -> list[AdaptiveLeaf] | None:
    if len(leaf.ticket_indices) < 2:
        return None
    scoped_vectors = vectors[leaf.ticket_indices]
    unique_vectors = np.unique(np.round(scoped_vectors, decimals=8), axis=0)
    if len(unique_vectors) < 2:
        return None
    raw_labels = cluster_labels(scoped_vectors, 2)
    groups: dict[int, list[int]] = defaultdict(list)
    for scoped_position, raw_label in enumerate(raw_labels):
        groups[int(raw_label)].append(leaf.ticket_indices[scoped_position])
    if len(groups) < 2:
        return None
    child_leaves = [
        new_adaptive_leaf(parent_key=leaf.parent_key, indices=indices, vectors=vectors)
        for indices in groups.values()
        if indices
    ]
    if len(child_leaves) < 2:
        return None
    return child_leaves


def build_adaptive_clusters(
    inputs: list[TicketTextInput],
    vectors: np.ndarray,
    *,
    seed_groups: list[tuple[str | None, list[int]]],
    level: int,
    max_count: int,
    distance_threshold: float,
    key_prefix: str | None = None,
) -> dict[str, ClusterInfo]:
    if not seed_groups:
        return {}
    max_count = max(len(seed_groups), max_count)
    leaves = [
        new_adaptive_leaf(parent_key=parent_key, indices=indices, vectors=vectors)
        for parent_key, indices in seed_groups
        if indices
    ]

    while len(leaves) < max_count:
        candidate_positions = [
            position
            for position, leaf in enumerate(leaves)
            if leaf.splittable
            and len(leaf.ticket_indices) >= 2
            and leaf.max_distance > distance_threshold
        ]
        if not candidate_positions:
            break
        split_position = max(
            candidate_positions,
            key=lambda position: (
                leaves[position].max_distance,
                len(leaves[position].ticket_indices),
                -position,
            ),
        )
        split_leaf = leaves[split_position]
        child_leaves = split_leaf_once(split_leaf, vectors)
        if child_leaves is None:
            split_leaf.splittable = False
            continue
        leaves = leaves[:split_position] + child_leaves + leaves[split_position + 1 :]

    def sort_key(leaf: AdaptiveLeaf) -> tuple[int, str]:
        first_ticket = min(inputs[index].ticket.ticket_number for index in leaf.ticket_indices)
        return (-len(leaf.ticket_indices), first_ticket)

    clusters: dict[str, ClusterInfo] = {}
    for position, leaf in enumerate(sorted(leaves, key=sort_key), start=1):
        key = cluster_key(level, position, key_prefix=key_prefix)
        clusters[key] = ClusterInfo(
            key=key,
            level=level,
            ticket_indices=leaf.ticket_indices,
            centroid=leaf.centroid,
            max_distance=leaf.max_distance,
            mean_distance=leaf.mean_distance,
            parent_key=leaf.parent_key,
            top_terms=top_terms_for_indices(inputs, leaf.ticket_indices),
        )
    return dict(sorted(clusters.items()))


def cluster_key(level: int, position: int, *, key_prefix: str | None = None) -> str:
    key = f"L{level}-{position:03d}"
    return f"{key_prefix}-{key}" if key_prefix else key


def ranked_keys(
    groups: dict[int, list[int]],
    inputs: list[TicketTextInput],
    *,
    level: int,
    key_prefix: str | None = None,
) -> dict[int, str]:
    def sort_key(item: tuple[int, list[int]]) -> tuple[int, str]:
        _raw_label, indices = item
        first_ticket = min(inputs[index].ticket.ticket_number for index in indices)
        return (-len(indices), first_ticket)

    return {
        raw_label: cluster_key(level, position, key_prefix=key_prefix)
        for position, (raw_label, _indices) in enumerate(
            sorted(groups.items(), key=sort_key),
            start=1,
        )
    }


def build_level_3_clusters(
    inputs: list[TicketTextInput],
    vectors: np.ndarray,
    target_count: int,
    *,
    input_indices: list[int] | None = None,
    key_prefix: str | None = None,
) -> dict[str, ClusterInfo]:
    scoped_indices = input_indices or list(range(len(inputs)))
    scoped_vectors = vectors[scoped_indices]
    raw_labels = cluster_labels(scoped_vectors, target_count)
    groups: dict[int, list[int]] = defaultdict(list)
    for scoped_position, raw_label in enumerate(raw_labels):
        groups[int(raw_label)].append(scoped_indices[scoped_position])
    key_map = ranked_keys(groups, inputs, level=3, key_prefix=key_prefix)
    clusters: dict[str, ClusterInfo] = {}
    for raw_label, indices in groups.items():
        key = key_map[raw_label]
        centroid = normalized_centroid(vectors[indices])
        max_distance, mean_distance = cluster_distance_metrics(vectors, indices, centroid)
        clusters[key] = ClusterInfo(
            key=key,
            level=3,
            ticket_indices=indices,
            centroid=centroid,
            max_distance=max_distance,
            mean_distance=mean_distance,
            top_terms=top_terms_for_indices(inputs, indices),
        )
    return dict(sorted(clusters.items()))


def build_parent_clusters(
    *,
    child_clusters: dict[str, ClusterInfo],
    child_level: int,
    parent_level: int,
    target_count: int,
    inputs: list[TicketTextInput],
    vectors: np.ndarray,
    key_prefix: str | None = None,
) -> dict[str, ClusterInfo]:
    child_items = list(child_clusters.values())
    child_vectors = np.array([cluster.centroid for cluster in child_items], dtype=float)
    child_weights = np.array([len(cluster.ticket_indices) for cluster in child_items], dtype=float)
    raw_labels = cluster_labels(child_vectors, target_count, weights=child_weights)
    grouped_children: dict[int, list[ClusterInfo]] = defaultdict(list)
    for raw_label, child in zip(raw_labels, child_items, strict=True):
        grouped_children[int(raw_label)].append(child)

    def sort_key(item: tuple[int, list[ClusterInfo]]) -> tuple[int, str]:
        _raw_label, children = item
        ticket_count = sum(len(child.ticket_indices) for child in children)
        first_child = min(child.key for child in children)
        return (-ticket_count, first_child)

    key_map = {
        raw_label: cluster_key(parent_level, position, key_prefix=key_prefix)
        for position, (raw_label, _children) in enumerate(
            sorted(grouped_children.items(), key=sort_key),
            start=1,
        )
    }
    parent_clusters: dict[str, ClusterInfo] = {}
    for raw_label, children in grouped_children.items():
        key = key_map[raw_label]
        child_keys = sorted(child.key for child in children)
        ticket_indices = sorted(
            {ticket_index for child in children for ticket_index in child.ticket_indices},
        )
        centroid = normalized_centroid(
            np.array([child.centroid for child in children], dtype=float),
            np.array([len(child.ticket_indices) for child in children], dtype=float),
        )
        max_distance, mean_distance = cluster_distance_metrics(vectors, ticket_indices, centroid)
        parent_clusters[key] = ClusterInfo(
            key=key,
            level=parent_level,
            ticket_indices=ticket_indices,
            centroid=centroid,
            max_distance=max_distance,
            mean_distance=mean_distance,
            child_keys=child_keys,
            top_terms=top_terms_for_indices(inputs, ticket_indices),
        )
        for child in children:
            child.parent_key = key
    return dict(sorted(parent_clusters.items()))


def build_type_separated_clusters(
    inputs: list[TicketTextInput],
    vectors: np.ndarray,
    *,
    level_1_count: int,
    level_2_count: int,
    level_3_count: int,
) -> tuple[dict[str, ClusterInfo], dict[str, ClusterInfo], dict[str, ClusterInfo], dict[str, int]]:
    partitions = partition_input_indices(inputs)
    level_3_targets = split_target_count(partitions, level_3_count)
    level_3_clusters: dict[str, ClusterInfo] = {}
    level_3_by_partition: dict[str, dict[str, ClusterInfo]] = {}
    for partition, indices in partitions.items():
        clusters = build_level_3_clusters(
            inputs,
            vectors,
            min(level_3_targets.get(partition, 0), len(indices)),
            input_indices=indices,
            key_prefix=cluster_key_prefix(partition),
        )
        level_3_by_partition[partition] = clusters
        level_3_clusters.update(clusters)

    level_2_targets = split_target_count(
        partitions,
        level_2_count,
        maximum_by_partition={
            partition: len(clusters) for partition, clusters in level_3_by_partition.items()
        },
    )
    level_2_clusters: dict[str, ClusterInfo] = {}
    level_2_by_partition: dict[str, dict[str, ClusterInfo]] = {}
    for partition, child_clusters in level_3_by_partition.items():
        if not child_clusters:
            continue
        clusters = build_parent_clusters(
            child_clusters=child_clusters,
            child_level=3,
            parent_level=2,
            target_count=min(level_2_targets.get(partition, 0), len(child_clusters)),
            inputs=inputs,
            vectors=vectors,
            key_prefix=cluster_key_prefix(partition),
        )
        level_2_by_partition[partition] = clusters
        level_2_clusters.update(clusters)

    level_1_targets = split_target_count(
        partitions,
        level_1_count,
        maximum_by_partition={
            partition: len(clusters) for partition, clusters in level_2_by_partition.items()
        },
    )
    level_1_clusters: dict[str, ClusterInfo] = {}
    for partition, child_clusters in level_2_by_partition.items():
        if not child_clusters:
            continue
        clusters = build_parent_clusters(
            child_clusters=child_clusters,
            child_level=2,
            parent_level=1,
            target_count=min(level_1_targets.get(partition, 0), len(child_clusters)),
            inputs=inputs,
            vectors=vectors,
            key_prefix=cluster_key_prefix(partition),
        )
        level_1_clusters.update(clusters)

    partition_counts = {partition: len(indices) for partition, indices in partitions.items()}
    return (
        dict(sorted(level_1_clusters.items())),
        dict(sorted(level_2_clusters.items())),
        dict(sorted(level_3_clusters.items())),
        partition_counts,
    )


def attach_child_keys(
    parent_clusters: dict[str, ClusterInfo],
    child_clusters: dict[str, ClusterInfo],
) -> None:
    grouped: dict[str, list[str]] = defaultdict(list)
    for child in child_clusters.values():
        if child.parent_key and child.parent_key in parent_clusters:
            grouped[child.parent_key].append(child.key)
    for parent in parent_clusters.values():
        parent.child_keys = sorted(grouped.get(parent.key, []))


def build_adaptive_type_separated_clusters(
    inputs: list[TicketTextInput],
    vectors: np.ndarray,
    *,
    level_1_count: int,
    level_2_count: int,
    level_3_count: int,
    level_1_threshold: float,
    level_2_threshold: float,
    level_3_threshold: float,
) -> tuple[dict[str, ClusterInfo], dict[str, ClusterInfo], dict[str, ClusterInfo], dict[str, int]]:
    partitions = partition_input_indices(inputs)
    partition_counts = {partition: len(indices) for partition, indices in partitions.items()}
    level_1_targets = split_target_count(partitions, level_1_count)

    level_1_clusters: dict[str, ClusterInfo] = {}
    level_1_by_partition: dict[str, dict[str, ClusterInfo]] = {}
    for partition, indices in partitions.items():
        cap = max(1, min(level_1_targets.get(partition, 1), len(indices)))
        clusters = build_adaptive_clusters(
            inputs,
            vectors,
            seed_groups=[(None, indices)],
            level=1,
            max_count=cap,
            distance_threshold=level_1_threshold,
            key_prefix=cluster_key_prefix(partition),
        )
        level_1_by_partition[partition] = clusters
        level_1_clusters.update(clusters)

    level_2_clusters: dict[str, ClusterInfo] = {}
    level_2_by_partition: dict[str, dict[str, ClusterInfo]] = {}
    for partition, parent_clusters in level_1_by_partition.items():
        if not parent_clusters:
            continue
        indices = partitions[partition]
        clusters = build_adaptive_clusters(
            inputs,
            vectors,
            seed_groups=[
                (parent.key, parent.ticket_indices) for parent in parent_clusters.values()
            ],
            level=2,
            max_count=len(indices),
            distance_threshold=level_2_threshold,
            key_prefix=cluster_key_prefix(partition),
        )
        attach_child_keys(parent_clusters, clusters)
        level_2_by_partition[partition] = clusters
        level_2_clusters.update(clusters)

    level_3_clusters: dict[str, ClusterInfo] = {}
    for partition, parent_clusters in level_2_by_partition.items():
        if not parent_clusters:
            continue
        indices = partitions[partition]
        clusters = build_adaptive_clusters(
            inputs,
            vectors,
            seed_groups=[
                (parent.key, parent.ticket_indices) for parent in parent_clusters.values()
            ],
            level=3,
            max_count=len(indices),
            distance_threshold=level_3_threshold,
            key_prefix=cluster_key_prefix(partition),
        )
        attach_child_keys(parent_clusters, clusters)
        level_3_clusters.update(clusters)

    return (
        dict(sorted(level_1_clusters.items())),
        dict(sorted(level_2_clusters.items())),
        dict(sorted(level_3_clusters.items())),
        partition_counts,
    )


def representative_tickets(
    inputs: list[TicketTextInput],
    vectors: np.ndarray,
    cluster: ClusterInfo,
    *,
    limit: int,
) -> list[dict[str, Any]]:
    if not cluster.ticket_indices:
        return []
    scored = [
        (float(np.dot(vectors[index], cluster.centroid)), index) for index in cluster.ticket_indices
    ]
    scored.sort(key=lambda item: (-item[0], inputs[item[1]].ticket.ticket_number))
    representatives: list[dict[str, Any]] = []
    for score, index in scored[:limit]:
        ticket = inputs[index].ticket
        representatives.append(
            {
                "ticket_number": ticket.ticket_number,
                "ticket_type": ticket.ticket_type,
                "ticket_class": ticket_type_display(ticket.ticket_type),
                "short_description": compact_text(
                    ticket.short_description,
                    max_chars=MAX_REPRESENTATIVE_TEXT_CHARS,
                ),
                "description": compact_text(
                    ticket.description,
                    max_chars=MAX_REPRESENTATIVE_TEXT_CHARS,
                ),
                "similarity": round(score, 4),
            },
        )
    return representatives


def ticket_type_counts(inputs: list[TicketTextInput], indices: list[int]) -> tuple[int, int]:
    incident_count = 0
    sc_task_count = 0
    for index in indices:
        ticket_type = (inputs[index].ticket.ticket_type or "").upper()
        if ticket_type == "INCIDENT":
            incident_count += 1
        elif ticket_type == "SERVICE_CATALOG_TASK":
            sc_task_count += 1
    return incident_count, sc_task_count


def fallback_label(cluster: ClusterInfo) -> str:
    terms = [term.replace("_", " ").replace("-", " ").title() for term in (cluster.top_terms or [])]
    label = " ".join(terms[:2]).strip()
    return clean_label(label) or f"Cluster {cluster.key}"


def assign_cluster_id_labels(clusters_by_level: dict[int, dict[str, ClusterInfo]]) -> None:
    for level, clusters in clusters_by_level.items():
        for cluster in clusters.values():
            cluster.label = cluster_display_id(level, cluster.key) or f"Cluster {cluster.key}"
            cluster.summary = "LLM cluster naming was skipped for this calibration run."
            cluster.confidence = None


def cluster_payload(
    *,
    cluster: ClusterInfo,
    inputs: list[TicketTextInput],
    vectors: np.ndarray,
    child_clusters: dict[str, ClusterInfo] | None,
    representative_limit: int,
) -> dict[str, Any]:
    incident_count, sc_task_count = ticket_type_counts(inputs, cluster.ticket_indices)
    if incident_count and not sc_task_count:
        ticket_class = "Incident"
    elif sc_task_count and not incident_count:
        ticket_class = "Service Catalog Task"
    else:
        ticket_class = "Mixed/Other"
    payload: dict[str, Any] = {
        "cluster_id": cluster.key,
        "ticket_class": ticket_class,
        "ticket_count": len(cluster.ticket_indices),
        "incident_count": incident_count,
        "sc_task_count": sc_task_count,
        "max_distance_from_centroid": (
            round(cluster.max_distance, 4) if cluster.max_distance is not None else None
        ),
        "mean_distance_from_centroid": (
            round(cluster.mean_distance, 4) if cluster.mean_distance is not None else None
        ),
        "top_terms": cluster.top_terms or [],
        "representative_tickets": representative_tickets(
            inputs,
            vectors,
            cluster,
            limit=representative_limit,
        ),
    }
    if child_clusters and cluster.child_keys:
        payload["child_clusters"] = [
            {
                "cluster_id": child_key,
                "label": child_clusters[child_key].label,
                "ticket_count": len(child_clusters[child_key].ticket_indices),
                "max_distance_from_centroid": (
                    round(child_clusters[child_key].max_distance, 4)
                    if child_clusters[child_key].max_distance is not None
                    else None
                ),
                "top_terms": child_clusters[child_key].top_terms or [],
            }
            for child_key in cluster.child_keys
            if child_key in child_clusters
        ]
    return payload


def parse_cluster_label_response(response_text: str | None) -> dict[str, dict[str, Any]]:
    if not response_text or not response_text.strip():
        raise TicketClusteringError("The cluster labeling model returned an empty response.")
    text = response_text.strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise TicketClusteringError(
                "The cluster labeling model did not return valid JSON.",
            ) from None
        parsed = json.loads(text[start : end + 1])
    clusters = parsed.get("clusters") if isinstance(parsed, dict) else None
    if not isinstance(clusters, list):
        raise TicketClusteringError("The cluster labeling JSON must contain a clusters array.")
    labels: dict[str, dict[str, Any]] = {}
    for row in clusters:
        if not isinstance(row, dict):
            continue
        cluster_id = clean_label(row.get("cluster_id"), max_chars=80)
        if cluster_id:
            labels[cluster_id] = row
    return labels


def label_cluster_level(
    db: Session,
    *,
    project_id: UUID,
    customer_id: UUID | None,
    month_key: str,
    month_key_to: str,
    run_id: str,
    level: int,
    clusters: dict[str, ClusterInfo],
    inputs: list[TicketTextInput],
    vectors: np.ndarray,
    child_clusters: dict[str, ClusterInfo] | None,
    prompt_text: str,
    config: GenAIConfig,
) -> int:
    settings = get_settings()
    range_label = analysis_range_label(month_key, month_key_to)
    batch_size = clamp_positive(
        settings.genai_ticket_cluster_label_batch_size,
        15,
        minimum=1,
        maximum=50,
    )
    representative_limit = clamp_positive(
        settings.genai_ticket_cluster_representative_ticket_count,
        8,
        minimum=1,
        maximum=20,
    )
    failed_count = 0
    cluster_items = list(clusters.values())
    total_batches = math.ceil(len(cluster_items) / batch_size) if cluster_items else 0
    log_progress(
        "level %s labeling started: %s clusters, batch size %s",
        level,
        len(cluster_items),
        batch_size,
    )
    for offset in range(0, len(cluster_items), batch_size):
        batch = cluster_items[offset : offset + batch_size]
        batch_number = (offset // batch_size) + 1
        batch_ticket_count = sum(len(cluster.ticket_indices) for cluster in batch)
        log_progress(
            "level %s labeling batch %s/%s started for %s clusters",
            level,
            batch_number,
            total_batches,
            len(batch),
        )
        payload = {
            "level": level,
            "label_role": {
                1: "top-level category",
                2: "subcategory 1",
                3: "subcategory 2",
            }[level],
            "clusters": [
                cluster_payload(
                    cluster=cluster,
                    inputs=inputs,
                    vectors=vectors,
                    child_clusters=child_clusters,
                    representative_limit=representative_limit,
                )
                for cluster in batch
            ],
        }
        messages = [
            {"role": "system", "content": prompt_text},
            {
                "role": "user",
                "content": (
                    "Name these ticket clusters. Keep labels reusable and concise.\n"
                    f"{json.dumps(payload, ensure_ascii=False)}"
                ),
            },
        ]
        result: LLMCompletionResult = chat_completion(config, messages)
        create_usage_log(
            db,
            operation="ticket_cluster_labeling",
            status="success" if result.ok else "error",
            provider=config.provider,
            model_name=config.model_name,
            customer_id=customer_id,
            project_id=project_id,
            question=f"{range_label}: label {len(batch)} level {level} clusters",
            tools_used_json={
                "run_id": run_id,
                "analysis_month": month_key,
                "analysis_month_from": month_key,
                "analysis_month_to": month_key_to,
                "cluster_level": level,
                "cluster_count": len(batch),
                "ticket_count": batch_ticket_count if level == 3 else 0,
            },
            prompt_tokens=result.prompt_tokens,
            completion_tokens=result.completion_tokens,
            estimated_cost=result.estimated_cost,
            duration_ms=result.duration_ms,
            error_message=result.error_message,
        )
        parsed_labels: dict[str, dict[str, Any]] = {}
        if result.ok:
            try:
                parsed_labels = parse_cluster_label_response(result.response_text)
            except TicketClusteringError as exc:
                failed_count += len(batch)
                log_progress(
                    "level %s labeling batch %s/%s returned invalid JSON: %s",
                    level,
                    batch_number,
                    total_batches,
                    str(exc),
                )
                create_usage_log(
                    db,
                    operation="ticket_cluster_labeling_parse",
                    status="error",
                    provider=config.provider,
                    model_name=config.model_name,
                    customer_id=customer_id,
                    project_id=project_id,
                    question=f"{range_label}: parse level {level} cluster labels",
                    tools_used_json={
                        "run_id": run_id,
                        "analysis_month": month_key,
                        "analysis_month_from": month_key,
                        "analysis_month_to": month_key_to,
                        "cluster_level": level,
                        "cluster_count": len(batch),
                        "ticket_count": batch_ticket_count if level == 3 else 0,
                    },
                    error_message=str(exc),
                )
        else:
            failed_count += len(batch)
            log_progress(
                "level %s labeling batch %s/%s failed: %s",
                level,
                batch_number,
                total_batches,
                result.error_message or "unknown error",
            )

        for cluster in batch:
            parsed_row = parsed_labels.get(cluster.key) or {}
            label = clean_label(parsed_row.get("label")) or fallback_label(cluster)
            cluster.label = label
            cluster.summary = compact_text(parsed_row.get("summary"), max_chars=1000)
            cluster.confidence = normalize_confidence(parsed_row.get("confidence"))
        db.commit()
        parsed_label_count = sum(1 for cluster in batch if cluster.key in parsed_labels)
        fallback_count = len(batch) - parsed_label_count
        log_progress(
            "level %s labeling batch %s/%s complete (%s labels, %s fallback labels)",
            level,
            batch_number,
            total_batches,
            parsed_label_count,
            fallback_count,
        )
    log_progress(
        "level %s labeling complete: %s clusters, %s fallback/error labels",
        level,
        len(cluster_items),
        failed_count,
    )
    return failed_count


def save_cluster_labels(
    db: Session,
    *,
    project_id: UUID,
    customer_id: UUID | None,
    month_key: str,
    run_id: str,
    clusters_by_level: dict[int, dict[str, ClusterInfo]],
    inputs: list[TicketTextInput],
    vectors: np.ndarray,
    metadata: dict[str, Any],
) -> int:
    db.execute(
        delete(GenAITicketClusterLabel).where(
            GenAITicketClusterLabel.project_id == project_id,
            GenAITicketClusterLabel.analysis_month == month_key,
            GenAITicketClusterLabel.run_id == run_id,
        ),
    )
    representative_limit = clamp_positive(
        get_settings().genai_ticket_cluster_representative_ticket_count,
        8,
        minimum=1,
        maximum=20,
    )
    saved_count = 0
    for level, clusters in clusters_by_level.items():
        child_clusters = clusters_by_level.get(level + 1)
        for cluster in clusters.values():
            incident_count, sc_task_count = ticket_type_counts(inputs, cluster.ticket_indices)
            db.add(
                GenAITicketClusterLabel(
                    customer_id=customer_id,
                    project_id=project_id,
                    analysis_month=month_key,
                    run_id=run_id,
                    cluster_level=level,
                    cluster_key=cluster.key,
                    parent_cluster_key=cluster.parent_key,
                    label=cluster.label or fallback_label(cluster),
                    summary=cluster.summary,
                    confidence=cluster.confidence,
                    ticket_count=len(cluster.ticket_indices),
                    incident_count=incident_count,
                    sc_task_count=sc_task_count,
                    representative_tickets_json=representative_tickets(
                        inputs,
                        vectors,
                        cluster,
                        limit=representative_limit,
                    ),
                    child_clusters_json=(
                        [
                            {
                                "cluster_id": child_key,
                                "label": child_clusters[child_key].label,
                                "ticket_count": len(child_clusters[child_key].ticket_indices),
                            }
                            for child_key in (cluster.child_keys or [])
                            if child_clusters and child_key in child_clusters
                        ]
                        if child_clusters
                        else None
                    ),
                    metadata_json={
                        **metadata,
                        "cluster_max_distance_from_centroid": cluster.max_distance,
                        "cluster_mean_distance_from_centroid": cluster.mean_distance,
                    },
                ),
            )
            saved_count += 1
    db.commit()
    return saved_count


def classification_input_hash(
    ticket_input: TicketTextInput,
    *,
    run_metadata: dict[str, Any],
    prompt_fingerprint_value: str,
) -> str:
    payload = {
        "ticket_number": ticket_input.ticket.ticket_number,
        "input_hash": ticket_input.input_hash,
        "run_metadata": run_metadata,
        "prompt_fingerprint": prompt_fingerprint_value,
        "output_prompt_key": OUTPUT_PROMPT_KEY,
    }
    return hash_text(json.dumps(payload, sort_keys=True, ensure_ascii=False))


def save_ticket_assignments(
    db: Session,
    *,
    project_id: UUID,
    customer_id: UUID | None,
    month_keys: list[str],
    run_id: str,
    inputs: list[TicketTextInput],
    vectors: np.ndarray,
    clusters_by_level: dict[int, dict[str, ClusterInfo]],
    label_model_name: str | None,
    prompt_version: int,
    prompt_fingerprint_value: str,
    run_metadata: dict[str, Any],
) -> int:
    db.execute(
        delete(GenAITicketClassification).where(
            GenAITicketClassification.project_id == project_id,
            GenAITicketClassification.analysis_month.in_(month_keys),
        ),
    )
    l3_by_ticket_index: dict[int, ClusterInfo] = {}
    for cluster in clusters_by_level[3].values():
        for ticket_index in cluster.ticket_indices:
            l3_by_ticket_index[ticket_index] = cluster
    assigned_count = 0
    for ticket_index, ticket_input in enumerate(inputs):
        l3 = l3_by_ticket_index[ticket_index]
        l2 = clusters_by_level[2][l3.parent_key] if l3.parent_key else None
        l1 = clusters_by_level[1][l2.parent_key] if l2 and l2.parent_key else None
        ticket = ticket_input.ticket
        row_month_key = ticket_analysis_month(ticket)
        confidence_values = [
            value
            for value in (
                l1.confidence if l1 else None,
                l2.confidence if l2 else None,
                l3.confidence,
            )
            if value is not None
        ]
        confidence = (
            float(sum(confidence_values) / len(confidence_values)) if confidence_values else None
        )
        l1_ticket_distance = ticket_distance_from_cluster_centroid(vectors, ticket_index, l1)
        l2_ticket_distance = ticket_distance_from_cluster_centroid(vectors, ticket_index, l2)
        l3_ticket_distance = ticket_distance_from_cluster_centroid(vectors, ticket_index, l3)
        db.add(
            GenAITicketClassification(
                customer_id=customer_id,
                project_id=project_id,
                ticket_number=ticket.ticket_number,
                ticket_type=ticket.ticket_type,
                analysis_month=row_month_key,
                input_hash=classification_input_hash(
                    ticket_input,
                    run_metadata=run_metadata,
                    prompt_fingerprint_value=prompt_fingerprint_value,
                ),
                prompt_key=OUTPUT_PROMPT_KEY,
                prompt_version=prompt_version,
                model_name=label_model_name,
                status="success",
                category_quality=None,
                genai_category_cluster_id=cluster_display_id(1, l1.key if l1 else None),
                genai_category=l1.label if l1 else l2.label if l2 else l3.label,
                genai_subcategory_1_cluster_id=cluster_display_id(2, l2.key if l2 else None),
                genai_subcategory_1=l2.label if l1 and l2 else None,
                genai_subcategory_2_cluster_id=cluster_display_id(3, l3.key),
                genai_subcategory_2=l3.label if l2 else None,
                confidence=confidence,
                metadata_json={
                    **run_metadata,
                    "run_id": run_id,
                    "analysis_mode": "cluster",
                    "ticket_analysis_month": row_month_key,
                    "cluster_level_1": l1.key if l1 else None,
                    "cluster_level_2": l2.key if l2 else None,
                    "cluster_level_3": l3.key,
                    "cluster_level_1_max_distance_from_centroid": (
                        l1.max_distance if l1 else None
                    ),
                    "cluster_level_1_mean_distance_from_centroid": (
                        l1.mean_distance if l1 else None
                    ),
                    "cluster_level_1_ticket_distance_from_centroid": l1_ticket_distance,
                    "cluster_level_2_max_distance_from_centroid": (
                        l2.max_distance if l2 else None
                    ),
                    "cluster_level_2_mean_distance_from_centroid": (
                        l2.mean_distance if l2 else None
                    ),
                    "cluster_level_2_ticket_distance_from_centroid": l2_ticket_distance,
                    "cluster_level_3_max_distance_from_centroid": l3.max_distance,
                    "cluster_level_3_mean_distance_from_centroid": l3.mean_distance,
                    "cluster_level_3_ticket_distance_from_centroid": l3_ticket_distance,
                    "normalized_text_hash": ticket_input.normalized_text_hash,
                },
                error_message=None,
                processed_at=datetime.now(UTC),
            ),
        )
        assigned_count += 1
    db.commit()
    return assigned_count


def _metadata_from_usage_log(row: GenAIUsageLog) -> dict[str, Any]:
    return row.tools_used_json if isinstance(row.tools_used_json, dict) else {}


def _sum_optional(values: list[int | float | None]) -> int | float | None:
    present_values = [value for value in values if value is not None]
    if not present_values:
        return None
    return sum(present_values)


def _metadata_matches_analysis_range(
    metadata: dict[str, Any],
    start_month: str,
    end_month: str,
) -> bool:
    metadata_start_month = str(
        metadata.get("analysis_month_from") or metadata.get("analysis_month") or "",
    )
    metadata_end_month = str(metadata.get("analysis_month_to") or metadata_start_month)
    return metadata_start_month == start_month and metadata_end_month == end_month


def _cluster_usage_run_from_logs(
    project_id: UUID,
    start_month: str,
    end_month: str,
    run_id: str,
    logs: list[GenAIUsageLog],
) -> dict[str, Any]:
    ordered_logs = sorted(logs, key=lambda row: row.created_at)
    embedding_logs = [row for row in ordered_logs if row.operation == "ticket_cluster_embedding"]
    llm_logs = [row for row in ordered_logs if row.operation == "ticket_cluster_labeling"]
    prompt_tokens = _sum_optional([row.prompt_tokens for row in ordered_logs])
    completion_tokens = _sum_optional([row.completion_tokens for row in ordered_logs])
    estimated_cost = _sum_optional([row.estimated_cost for row in ordered_logs])
    duration_ms = _sum_optional([row.duration_ms for row in ordered_logs])
    embedding_tokens = _sum_optional([row.prompt_tokens for row in embedding_logs])
    embedding_cost = _sum_optional([row.estimated_cost for row in embedding_logs])
    llm_prompt_tokens = _sum_optional([row.prompt_tokens for row in llm_logs])
    llm_completion_tokens = _sum_optional([row.completion_tokens for row in llm_logs])
    llm_cost = _sum_optional([row.estimated_cost for row in llm_logs])
    total_tokens = (
        int((prompt_tokens or 0) + (completion_tokens or 0))
        if prompt_tokens is not None or completion_tokens is not None
        else None
    )
    llm_total_tokens = (
        int((llm_prompt_tokens or 0) + (llm_completion_tokens or 0))
        if llm_prompt_tokens is not None or llm_completion_tokens is not None
        else None
    )
    embedded_ticket_count = sum(
        int(_metadata_from_usage_log(row).get("ticket_count") or 0) for row in embedding_logs
    )
    labeled_level_3_ticket_count = sum(
        int(metadata.get("ticket_count") or 0)
        for row in llm_logs
        for metadata in [_metadata_from_usage_log(row)]
        if metadata.get("cluster_level") == 3
    )
    ticket_count = embedded_ticket_count or labeled_level_3_ticket_count or max(
        (int(_metadata_from_usage_log(row).get("ticket_count") or 0) for row in ordered_logs),
        default=0,
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
        "embedding_model_name": embedding_logs[-1].model_name if embedding_logs else None,
        "embedding_tokens": int(embedding_tokens) if embedding_tokens is not None else None,
        "embedding_cost": float(embedding_cost) if embedding_cost is not None else None,
        "embedding_batch_count": len(embedding_logs),
        "llm_model_name": llm_logs[-1].model_name if llm_logs else None,
        "llm_prompt_tokens": int(llm_prompt_tokens) if llm_prompt_tokens is not None else None,
        "llm_completion_tokens": (
            int(llm_completion_tokens) if llm_completion_tokens is not None else None
        ),
        "llm_total_tokens": llm_total_tokens,
        "llm_cost": float(llm_cost) if llm_cost is not None else None,
        "llm_batch_count": len(llm_logs),
        "duration_ms": int(duration_ms) if duration_ms is not None else None,
        "ticket_count": ticket_count,
        "batch_count": len(ordered_logs),
        "success_batch_count": sum(1 for row in ordered_logs if row.status == "success"),
        "error_batch_count": sum(1 for row in ordered_logs if row.status == "error"),
        "started_at": ordered_logs[0].created_at if ordered_logs else None,
        "completed_at": ordered_logs[-1].created_at if ordered_logs else None,
    }


def ticket_cluster_usage_run(
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
            GenAIUsageLog.operation.in_(
                [
                    "ticket_cluster_embedding",
                    "ticket_cluster_labeling",
                    "ticket_cluster_labeling_parse",
                ],
            ),
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
    return _cluster_usage_run_from_logs(project_id, start_month, end_month, run_id, logs)


def ticket_cluster_usage_runs(
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
            GenAIUsageLog.operation.in_(
                [
                    "ticket_cluster_embedding",
                    "ticket_cluster_labeling",
                    "ticket_cluster_labeling_parse",
                ],
            ),
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
        _cluster_usage_run_from_logs(project_id, start_month, end_month, grouped_run_id, logs)
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


def clear_ticket_cluster_analysis(
    db: Session,
    request: TicketClusterClearRequest,
) -> dict[str, Any]:
    start_month, end_month = validate_month_range(
        request.analysis_month,
        request.analysis_month_to,
    )
    month_keys = month_keys_in_range(start_month, end_month)
    deleted_classification_count = db.execute(
        delete(GenAITicketClassification).where(
            GenAITicketClassification.project_id == request.project_id,
            GenAITicketClassification.analysis_month.in_(month_keys),
        ),
    ).rowcount
    deleted_cluster_label_count = db.execute(
        delete(GenAITicketClusterLabel).where(
            GenAITicketClusterLabel.project_id == request.project_id,
            GenAITicketClusterLabel.analysis_month.in_(month_keys),
        ),
    ).rowcount
    db.commit()
    return {
        "project_id": request.project_id,
        "analysis_month": start_month,
        "analysis_month_from": start_month,
        "analysis_month_to": end_month,
        "deleted_classification_count": int(deleted_classification_count or 0),
        "deleted_cluster_label_count": int(deleted_cluster_label_count or 0),
    }


def clear_project_ticket_embeddings(
    db: Session,
    request: TicketEmbeddingClearRequest,
) -> dict[str, Any]:
    deleted_embedding_count = db.execute(
        delete(GenAITicketEmbedding).where(
            GenAITicketEmbedding.project_id == request.project_id,
        ),
    ).rowcount
    db.commit()
    return {
        "project_id": request.project_id,
        "deleted_embedding_count": int(deleted_embedding_count or 0),
    }


def run_ticket_cluster_analysis(
    db: Session,
    request: TicketClusterRunRequest,
) -> dict[str, Any]:
    run_started_at = time.perf_counter()
    month_key, month_key_to = validate_month_range(
        request.analysis_month,
        request.analysis_month_to,
    )
    month_keys = month_keys_in_range(month_key, month_key_to)
    range_label = analysis_range_label(month_key, month_key_to)
    run_id = (request.run_id or "").strip() or str(uuid4())
    log_progress(
        "run %s started for project %s period %s",
        run_id,
        request.project_id,
        range_label,
    )
    customer_id = project_customer_id(db, request.project_id)
    base_config = get_or_create_config(db)
    validate_config(base_config)
    embedding_config = effective_embedding_config(base_config)
    label_config = effective_label_config(base_config)
    use_llm_labels = bool(request.use_llm_labels)
    validate_config(embedding_config)
    if use_llm_labels:
        validate_config(label_config)
    prompt_template = get_prompt_template(db, PROMPT_KEY)
    prompt_text = (
        prompt_template.custom_prompt.strip()
        if prompt_template.is_custom_enabled
        and prompt_template.custom_prompt
        and prompt_template.custom_prompt.strip()
        else prompt_template.default_prompt
    )
    prompt_text = f"{prompt_text.rstrip()}\n\n{TICKET_TYPE_SEPARATION_PROMPT}"
    prompt_version = prompt_template.version
    prompt_fingerprint_value = prompt_fingerprint(prompt_text)

    if request.force_reprocess:
        log_progress("run %s force reprocess requested; clearing previous cluster output", run_id)
        clear_ticket_cluster_analysis(
            db,
            TicketClusterClearRequest(
                project_id=request.project_id,
                analysis_month=month_key,
                analysis_month_to=month_key_to,
            ),
        )

    tickets = db.execute(
        eligible_ticket_statement_for_month_range(
            request.project_id,
            month_key,
            month_key_to,
        ),
    ).scalars().all()
    eligible_count = len(tickets)
    log_progress("run %s eligible ticket selection complete: %s tickets", run_id, eligible_count)
    if not tickets:
        log_progress("run %s complete: no eligible tickets", run_id)
        return {
            "project_id": request.project_id,
            "analysis_month": month_key,
            "analysis_month_from": month_key,
            "analysis_month_to": month_key_to,
            "run_id": run_id,
            "eligible_ticket_count": 0,
            "embedded_ticket_count": 0,
            "cached_embedding_count": 0,
            "new_embedding_count": 0,
            "level_1_cluster_count": 0,
            "level_2_cluster_count": 0,
            "level_3_cluster_count": 0,
            "labeled_cluster_count": 0,
            "assigned_ticket_count": 0,
            "failed_count": 0,
            "llm_labeling_enabled": use_llm_labels,
            "summary": ticket_classification_summary(
                db,
                request.project_id,
                month_key,
                month_key_to,
            ),
            "usage_run": ticket_cluster_usage_run(
                db,
                request.project_id,
                month_key,
                run_id,
                month_key_to,
            ),
        }

    stage_started_at = time.perf_counter()
    inputs, cached_embedding_count, new_embedding_count = ensure_ticket_embeddings(
        db,
        project_id=request.project_id,
        customer_id=customer_id,
        month_key=month_key,
        month_key_to=month_key_to,
        run_id=run_id,
        tickets=tickets,
        config=embedding_config,
    )
    log_progress(
        "run %s embeddings ready: %s vectors (%s cached, %s new) in %.2fs",
        run_id,
        len(inputs),
        cached_embedding_count,
        new_embedding_count,
        time.perf_counter() - stage_started_at,
    )
    stage_started_at = time.perf_counter()
    vectors = normalized_matrix(inputs)
    log_progress(
        "run %s normalized embedding matrix prepared: %s rows x %s dimensions",
        run_id,
        vectors.shape[0],
        vectors.shape[1] if vectors.ndim == 2 else 0,
    )
    settings = get_settings()
    cluster_mode = normalized_cluster_mode(settings.genai_ticket_cluster_mode)
    level_3_count = clamp_positive(
        request.level_3_count,
        settings.genai_ticket_cluster_level_3_count,
        minimum=1,
        maximum=len(inputs),
    )
    level_2_count = clamp_positive(
        request.level_2_count,
        settings.genai_ticket_cluster_level_2_count,
        minimum=1,
        maximum=min(level_3_count, len(inputs)),
    )
    level_1_count = clamp_positive(
        request.level_1_count,
        settings.genai_ticket_cluster_level_1_count,
        minimum=1,
        maximum=min(level_2_count, len(inputs)),
    )
    level_1_threshold = clamp_distance_threshold(
        settings.genai_ticket_cluster_level_1_distance_threshold,
        0.42,
    )
    level_2_threshold = clamp_distance_threshold(
        settings.genai_ticket_cluster_level_2_distance_threshold,
        0.32,
    )
    level_3_threshold = clamp_distance_threshold(
        settings.genai_ticket_cluster_level_3_distance_threshold,
        0.24,
    )
    if cluster_mode == "adaptive":
        log_progress(
            (
                "run %s clustering mode=adaptive caps: level 1=%s, "
                "level 2=threshold-driven, level 3=threshold-driven; "
                "configured reference counts=%s/%s/%s; distance thresholds=%s/%s/%s"
            ),
            run_id,
            level_1_count,
            level_1_count,
            level_2_count,
            level_3_count,
            level_1_threshold,
            level_2_threshold,
            level_3_threshold,
        )
    else:
        log_progress(
            (
                "run %s clustering mode=fixed targets: level 1=%s, level 2=%s, "
                "level 3=%s; distance thresholds=%s/%s/%s"
            ),
            run_id,
            level_1_count,
            level_2_count,
            level_3_count,
            level_1_threshold,
            level_2_threshold,
            level_3_threshold,
        )

    if cluster_mode == "fixed":
        level_1_clusters, level_2_clusters, level_3_clusters, partition_counts = (
            build_type_separated_clusters(
                inputs,
                vectors,
                level_1_count=level_1_count,
                level_2_count=level_2_count,
                level_3_count=level_3_count,
            )
        )
    else:
        level_1_clusters, level_2_clusters, level_3_clusters, partition_counts = (
            build_adaptive_type_separated_clusters(
                inputs,
                vectors,
                level_1_count=level_1_count,
                level_2_count=level_2_count,
                level_3_count=level_3_count,
                level_1_threshold=level_1_threshold,
                level_2_threshold=level_2_threshold,
                level_3_threshold=level_3_threshold,
            )
        )
    log_progress(
        (
            "run %s %s clustering complete: %s/%s/%s clusters "
            "across partitions %s in %.2fs"
        ),
        run_id,
        cluster_mode,
        len(level_1_clusters),
        len(level_2_clusters),
        len(level_3_clusters),
        partition_counts,
        time.perf_counter() - stage_started_at,
    )
    clusters_by_level = {
        1: level_1_clusters,
        2: level_2_clusters,
        3: level_3_clusters,
    }
    failed_count = 0
    if use_llm_labels:
        log_progress("run %s cluster labeling started", run_id)
        failed_count += label_cluster_level(
            db,
            project_id=request.project_id,
            customer_id=customer_id,
            month_key=month_key,
            month_key_to=month_key_to,
            run_id=run_id,
            level=3,
            clusters=level_3_clusters,
            inputs=inputs,
            vectors=vectors,
            child_clusters=None,
            prompt_text=prompt_text,
            config=label_config,
        )
        failed_count += label_cluster_level(
            db,
            project_id=request.project_id,
            customer_id=customer_id,
            month_key=month_key,
            month_key_to=month_key_to,
            run_id=run_id,
            level=2,
            clusters=level_2_clusters,
            inputs=inputs,
            vectors=vectors,
            child_clusters=level_3_clusters,
            prompt_text=prompt_text,
            config=label_config,
        )
        failed_count += label_cluster_level(
            db,
            project_id=request.project_id,
            customer_id=customer_id,
            month_key=month_key,
            month_key_to=month_key_to,
            run_id=run_id,
            level=1,
            clusters=level_1_clusters,
            inputs=inputs,
            vectors=vectors,
            child_clusters=level_2_clusters,
            prompt_text=prompt_text,
            config=label_config,
        )
    else:
        log_progress("run %s cluster labeling skipped; using cluster IDs as labels", run_id)
        assign_cluster_id_labels(clusters_by_level)

    run_metadata = {
        "analysis_month": month_key,
        "analysis_month_from": month_key,
        "analysis_month_to": month_key_to,
        "analysis_range": range_label,
        "embedding_model": provider_model_name(embedding_config),
        "label_model": provider_model_name(label_config) if use_llm_labels else None,
        "llm_labeling_enabled": use_llm_labels,
        "algorithm": (
            "adaptive_recursive_kmeans_centroid_radius"
            if cluster_mode == "adaptive"
            else "kmeans_hierarchical_centroids"
        ),
        "cluster_mode": cluster_mode,
        "ticket_type_separated": True,
        "ticket_type_partition_counts": partition_counts,
        "level_1_target": level_1_count,
        "level_2_target": level_2_count,
        "level_3_target": level_3_count,
        "level_1_cap_mode": "configured_count",
        "level_2_cap_mode": (
            "threshold_driven_up_to_ticket_count"
            if cluster_mode == "adaptive"
            else "configured_count"
        ),
        "level_3_cap_mode": (
            "threshold_driven_up_to_ticket_count"
            if cluster_mode == "adaptive"
            else "configured_count"
        ),
        "level_1_distance_threshold": level_1_threshold,
        "level_2_distance_threshold": level_2_threshold,
        "level_3_distance_threshold": level_3_threshold,
        "text_version": EMBEDDING_TEXT_VERSION,
    }
    log_progress("run %s saving cluster labels", run_id)
    labeled_cluster_count = save_cluster_labels(
        db,
        project_id=request.project_id,
        customer_id=customer_id,
        month_key=month_key,
        run_id=run_id,
        clusters_by_level=clusters_by_level,
        inputs=inputs,
        vectors=vectors,
        metadata=run_metadata,
    )
    log_progress("run %s saving ticket assignments", run_id)
    assigned_ticket_count = save_ticket_assignments(
        db,
        project_id=request.project_id,
        customer_id=customer_id,
        month_keys=month_keys,
        run_id=run_id,
        inputs=inputs,
        vectors=vectors,
        clusters_by_level=clusters_by_level,
        label_model_name=provider_model_name(label_config) if use_llm_labels else None,
        prompt_version=prompt_version,
        prompt_fingerprint_value=prompt_fingerprint_value,
        run_metadata=run_metadata,
    )
    log_progress(
        (
            "run %s complete: %s tickets assigned, %s cluster labels saved, "
            "%s fallback/error labels, %.2fs elapsed"
        ),
        run_id,
        assigned_ticket_count,
        labeled_cluster_count,
        failed_count,
        time.perf_counter() - run_started_at,
    )
    usage_run = ticket_cluster_usage_run(
        db,
        request.project_id,
        month_key,
        run_id,
        month_key_to,
    )
    if usage_run:
        log_progress(
            (
                "run %s usage summary: embedding tokens=%s cost=%s; "
                "llm input tokens=%s output tokens=%s cost=%s; total cost=%s"
            ),
            run_id,
            usage_run.get("embedding_tokens"),
            usage_run.get("embedding_cost"),
            usage_run.get("llm_prompt_tokens"),
            usage_run.get("llm_completion_tokens"),
            usage_run.get("llm_cost"),
            usage_run.get("estimated_cost"),
        )
    return {
        "project_id": request.project_id,
        "analysis_month": month_key,
        "analysis_month_from": month_key,
        "analysis_month_to": month_key_to,
        "run_id": run_id,
        "eligible_ticket_count": eligible_count,
        "embedded_ticket_count": len(inputs),
        "cached_embedding_count": cached_embedding_count,
        "new_embedding_count": new_embedding_count,
        "level_1_cluster_count": len(level_1_clusters),
        "level_2_cluster_count": len(level_2_clusters),
        "level_3_cluster_count": len(level_3_clusters),
        "labeled_cluster_count": labeled_cluster_count,
        "assigned_ticket_count": assigned_ticket_count,
        "failed_count": failed_count,
        "llm_labeling_enabled": use_llm_labels,
        "summary": ticket_classification_summary(
            db,
            request.project_id,
            month_key,
            month_key_to,
        ),
        "usage_run": usage_run,
    }
