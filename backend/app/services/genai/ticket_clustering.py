from __future__ import annotations

import hashlib
import json
import re
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
    clean_label,
    compact_text,
    eligible_ticket_statement,
    normalize_confidence,
    project_customer_id,
    prompt_fingerprint,
    ticket_classification_summary,
    ticket_payload,
    validate_config,
    validate_month_key,
)
from app.services.genai.usage_log_service import create_usage_log

PROMPT_KEY = "ticket_cluster_labeling"
OUTPUT_PROMPT_KEY = "ticket_cluster_analysis"
EMBEDDING_TEXT_VERSION = "cluster-ticket-text-v1"
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


@dataclass(frozen=True)
class TicketClusterRunRequest:
    project_id: UUID
    analysis_month: str
    force_reprocess: bool = False
    level_1_count: int | None = None
    level_2_count: int | None = None
    level_3_count: int | None = None
    run_id: str | None = None


@dataclass(frozen=True)
class TicketClusterClearRequest:
    project_id: UUID
    analysis_month: str


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
    parent_key: str | None = None
    child_keys: list[str] | None = None
    top_terms: list[str] | None = None
    label: str | None = None
    summary: str | None = None
    confidence: float | None = None


def workbench_settings() -> dict[str, Any]:
    settings = get_settings()
    return {
        "ticket_classification_button_enabled": settings.genai_ticket_classification_button_enabled,
        "ticket_cluster_analysis_button_enabled": (
            settings.genai_ticket_cluster_analysis_button_enabled
        ),
        "cluster_embedding_model_name": settings.genai_ticket_cluster_embedding_model_name,
        "cluster_label_model_name": settings.genai_ticket_cluster_label_model_name
        or settings.genai_ticket_classification_model_name,
        "cluster_level_1_count": settings.genai_ticket_cluster_level_1_count,
        "cluster_level_2_count": settings.genai_ticket_cluster_level_2_count,
        "cluster_level_3_count": settings.genai_ticket_cluster_level_3_count,
        "cluster_embedding_batch_size": settings.genai_ticket_cluster_embedding_batch_size,
        "cluster_label_batch_size": settings.genai_ticket_cluster_label_batch_size,
    }


def clamp_positive(value: int | None, default_value: int, *, minimum: int, maximum: int) -> int:
    if value is None:
        value = default_value
    return max(minimum, min(int(value), maximum))


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


def normalized_ticket_text(ticket: Ticket) -> str:
    payload = ticket_payload(ticket)
    parts = [
        f"Ticket type: {payload.get('ticket_type') or ''}",
        f"Catalog item: {payload.get('catalog_item_name') or payload.get('catalog_item') or ''}",
        f"Short description: {payload.get('short_description') or ''}",
        f"Description: {payload.get('description') or ''}",
        f"Existing category: {payload.get('existing_category') or ''}",
        f"Existing subcategory: {payload.get('existing_subcategory') or ''}",
    ]
    text = " ".join(part for part in parts if part.strip())
    for pattern in NOISE_PATTERNS:
        text = pattern.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > MAX_TEXT_CHARS:
        text = text[:MAX_TEXT_CHARS].rstrip()
    return text or f"Ticket type: {ticket.ticket_type or 'Unknown'}"


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
    run_id: str,
    tickets: list[Ticket],
    config: GenAIConfig,
) -> tuple[list[TicketTextInput], int, int]:
    settings = get_settings()
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
    for offset in range(0, len(pending_rows), batch_size):
        batch = pending_rows[offset : offset + batch_size]
        texts = [row[1] for row in batch]
        result = embedding_request(config, texts)
        create_usage_log(
            db,
            operation="ticket_cluster_embedding",
            status="success" if result.ok else "error",
            provider=config.provider,
            model_name=config.model_name,
            customer_id=customer_id,
            project_id=project_id,
            question=f"{month_key}: {len(batch)} ticket embedding rows",
            tools_used_json={
                "run_id": run_id,
                "analysis_month": month_key,
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


def ranked_keys(groups: dict[int, list[int]], inputs: list[TicketTextInput]) -> dict[int, str]:
    def sort_key(item: tuple[int, list[int]]) -> tuple[int, str]:
        _raw_label, indices = item
        first_ticket = min(inputs[index].ticket.ticket_number for index in indices)
        return (-len(indices), first_ticket)

    return {
        raw_label: f"L3-{position:03d}"
        for position, (raw_label, _indices) in enumerate(
            sorted(groups.items(), key=sort_key),
            start=1,
        )
    }


def build_level_3_clusters(
    inputs: list[TicketTextInput],
    vectors: np.ndarray,
    target_count: int,
) -> dict[str, ClusterInfo]:
    raw_labels = cluster_labels(vectors, target_count)
    groups: dict[int, list[int]] = defaultdict(list)
    for index, raw_label in enumerate(raw_labels):
        groups[int(raw_label)].append(index)
    key_map = ranked_keys(groups, inputs)
    clusters: dict[str, ClusterInfo] = {}
    for raw_label, indices in groups.items():
        key = key_map[raw_label]
        centroid = normalized_centroid(vectors[indices])
        clusters[key] = ClusterInfo(
            key=key,
            level=3,
            ticket_indices=indices,
            centroid=centroid,
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

    prefix = f"L{parent_level}"
    key_map = {
        raw_label: f"{prefix}-{position:03d}"
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
        parent_clusters[key] = ClusterInfo(
            key=key,
            level=parent_level,
            ticket_indices=ticket_indices,
            centroid=centroid,
            child_keys=child_keys,
            top_terms=top_terms_for_indices(inputs, ticket_indices),
        )
        for child in children:
            child.parent_key = key
    return dict(sorted(parent_clusters.items()))


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
                "short_description": compact_text(
                    ticket.short_description,
                    max_chars=MAX_REPRESENTATIVE_TEXT_CHARS,
                ),
                "description": compact_text(
                    ticket.description,
                    max_chars=MAX_REPRESENTATIVE_TEXT_CHARS,
                ),
                "catalog_item_name": compact_text(ticket.catalog_item_name, max_chars=255),
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


def cluster_payload(
    *,
    cluster: ClusterInfo,
    inputs: list[TicketTextInput],
    vectors: np.ndarray,
    child_clusters: dict[str, ClusterInfo] | None,
    representative_limit: int,
) -> dict[str, Any]:
    incident_count, sc_task_count = ticket_type_counts(inputs, cluster.ticket_indices)
    payload: dict[str, Any] = {
        "cluster_id": cluster.key,
        "ticket_count": len(cluster.ticket_indices),
        "incident_count": incident_count,
        "sc_task_count": sc_task_count,
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
    for offset in range(0, len(cluster_items), batch_size):
        batch = cluster_items[offset : offset + batch_size]
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
            question=f"{month_key}: label {len(batch)} level {level} clusters",
            tools_used_json={
                "run_id": run_id,
                "analysis_month": month_key,
                "cluster_level": level,
                "cluster_count": len(batch),
                "ticket_count": 0,
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
                create_usage_log(
                    db,
                    operation="ticket_cluster_labeling_parse",
                    status="error",
                    provider=config.provider,
                    model_name=config.model_name,
                    customer_id=customer_id,
                    project_id=project_id,
                    question=f"{month_key}: parse level {level} cluster labels",
                    tools_used_json={
                        "run_id": run_id,
                        "analysis_month": month_key,
                        "cluster_level": level,
                        "cluster_count": len(batch),
                        "ticket_count": 0,
                    },
                    error_message=str(exc),
                )
        else:
            failed_count += len(batch)

        for cluster in batch:
            parsed_row = parsed_labels.get(cluster.key) or {}
            label = clean_label(parsed_row.get("label")) or fallback_label(cluster)
            cluster.label = label
            cluster.summary = compact_text(parsed_row.get("summary"), max_chars=1000)
            cluster.confidence = normalize_confidence(parsed_row.get("confidence"))
        db.commit()
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
                    metadata_json=metadata,
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
    month_key: str,
    run_id: str,
    inputs: list[TicketTextInput],
    clusters_by_level: dict[int, dict[str, ClusterInfo]],
    label_model_name: str | None,
    prompt_version: int,
    prompt_fingerprint_value: str,
    run_metadata: dict[str, Any],
) -> int:
    db.execute(
        delete(GenAITicketClassification).where(
            GenAITicketClassification.project_id == project_id,
            GenAITicketClassification.analysis_month == month_key,
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
        db.add(
            GenAITicketClassification(
                customer_id=customer_id,
                project_id=project_id,
                ticket_number=ticket.ticket_number,
                ticket_type=ticket.ticket_type,
                analysis_month=month_key,
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
                genai_category=l1.label if l1 else l2.label if l2 else l3.label,
                genai_subcategory_1=l2.label if l1 and l2 else None,
                genai_subcategory_2=l3.label if l2 else None,
                confidence=confidence,
                metadata_json={
                    **run_metadata,
                    "run_id": run_id,
                    "analysis_mode": "cluster",
                    "cluster_level_1": l1.key if l1 else None,
                    "cluster_level_2": l2.key if l2 else None,
                    "cluster_level_3": l3.key,
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


def _cluster_usage_run_from_logs(
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
    ticket_count = max(
        (int(_metadata_from_usage_log(row).get("ticket_count") or 0) for row in ordered_logs),
        default=0,
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


def ticket_cluster_usage_run(
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
        if _metadata_from_usage_log(row).get("analysis_month") == month_key
        and _metadata_from_usage_log(row).get("run_id") == run_id
    ]
    if not logs:
        return None
    return _cluster_usage_run_from_logs(project_id, month_key, run_id, logs)


def ticket_cluster_usage_runs(
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
        if metadata.get("analysis_month") != month_key:
            continue
        run_id = str(metadata.get("run_id") or "")
        if not run_id:
            continue
        grouped_logs.setdefault(run_id, []).append(row)
    usage_runs = [
        _cluster_usage_run_from_logs(project_id, month_key, grouped_run_id, logs)
        for grouped_run_id, logs in grouped_logs.items()
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


def clear_ticket_cluster_analysis(
    db: Session,
    request: TicketClusterClearRequest,
) -> dict[str, Any]:
    month_key = validate_month_key(request.analysis_month)
    deleted_classification_count = db.execute(
        delete(GenAITicketClassification).where(
            GenAITicketClassification.project_id == request.project_id,
            GenAITicketClassification.analysis_month == month_key,
        ),
    ).rowcount
    deleted_cluster_label_count = db.execute(
        delete(GenAITicketClusterLabel).where(
            GenAITicketClusterLabel.project_id == request.project_id,
            GenAITicketClusterLabel.analysis_month == month_key,
        ),
    ).rowcount
    db.commit()
    return {
        "project_id": request.project_id,
        "analysis_month": month_key,
        "deleted_classification_count": int(deleted_classification_count or 0),
        "deleted_cluster_label_count": int(deleted_cluster_label_count or 0),
    }


def run_ticket_cluster_analysis(
    db: Session,
    request: TicketClusterRunRequest,
) -> dict[str, Any]:
    month_key = validate_month_key(request.analysis_month)
    run_id = (request.run_id or "").strip() or str(uuid4())
    customer_id = project_customer_id(db, request.project_id)
    base_config = get_or_create_config(db)
    validate_config(base_config)
    embedding_config = effective_embedding_config(base_config)
    label_config = effective_label_config(base_config)
    validate_config(embedding_config)
    validate_config(label_config)
    prompt_template = get_prompt_template(db, PROMPT_KEY)
    prompt_text = (
        prompt_template.custom_prompt.strip()
        if prompt_template.is_custom_enabled
        and prompt_template.custom_prompt
        and prompt_template.custom_prompt.strip()
        else prompt_template.default_prompt
    )
    prompt_version = prompt_template.version
    prompt_fingerprint_value = prompt_fingerprint(prompt_text)

    if request.force_reprocess:
        clear_ticket_cluster_analysis(
            db,
            TicketClusterClearRequest(
                project_id=request.project_id,
                analysis_month=month_key,
            ),
        )

    tickets = db.execute(eligible_ticket_statement(request.project_id, month_key)).scalars().all()
    eligible_count = len(tickets)
    if not tickets:
        return {
            "project_id": request.project_id,
            "analysis_month": month_key,
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
            "summary": ticket_classification_summary(db, request.project_id, month_key),
            "usage_run": ticket_cluster_usage_run(db, request.project_id, month_key, run_id),
        }

    inputs, cached_embedding_count, new_embedding_count = ensure_ticket_embeddings(
        db,
        project_id=request.project_id,
        customer_id=customer_id,
        month_key=month_key,
        run_id=run_id,
        tickets=tickets,
        config=embedding_config,
    )
    vectors = normalized_matrix(inputs)
    settings = get_settings()
    level_3_count = clamp_positive(
        request.level_3_count,
        settings.genai_ticket_cluster_level_3_count,
        minimum=1,
        maximum=min(300, len(inputs)),
    )
    level_2_count = clamp_positive(
        request.level_2_count,
        settings.genai_ticket_cluster_level_2_count,
        minimum=1,
        maximum=min(150, level_3_count),
    )
    level_1_count = clamp_positive(
        request.level_1_count,
        settings.genai_ticket_cluster_level_1_count,
        minimum=1,
        maximum=min(50, level_2_count),
    )

    level_3_clusters = build_level_3_clusters(inputs, vectors, level_3_count)
    level_2_clusters = build_parent_clusters(
        child_clusters=level_3_clusters,
        child_level=3,
        parent_level=2,
        target_count=min(level_2_count, len(level_3_clusters)),
        inputs=inputs,
    )
    level_1_clusters = build_parent_clusters(
        child_clusters=level_2_clusters,
        child_level=2,
        parent_level=1,
        target_count=min(level_1_count, len(level_2_clusters)),
        inputs=inputs,
    )
    clusters_by_level = {
        1: level_1_clusters,
        2: level_2_clusters,
        3: level_3_clusters,
    }
    failed_count = 0
    failed_count += label_cluster_level(
        db,
        project_id=request.project_id,
        customer_id=customer_id,
        month_key=month_key,
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
        run_id=run_id,
        level=1,
        clusters=level_1_clusters,
        inputs=inputs,
        vectors=vectors,
        child_clusters=level_2_clusters,
        prompt_text=prompt_text,
        config=label_config,
    )

    run_metadata = {
        "embedding_model": provider_model_name(embedding_config),
        "label_model": provider_model_name(label_config),
        "algorithm": "kmeans_hierarchical_centroids",
        "level_1_target": level_1_count,
        "level_2_target": level_2_count,
        "level_3_target": level_3_count,
        "text_version": EMBEDDING_TEXT_VERSION,
    }
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
    assigned_ticket_count = save_ticket_assignments(
        db,
        project_id=request.project_id,
        customer_id=customer_id,
        month_key=month_key,
        run_id=run_id,
        inputs=inputs,
        clusters_by_level=clusters_by_level,
        label_model_name=provider_model_name(label_config),
        prompt_version=prompt_version,
        prompt_fingerprint_value=prompt_fingerprint_value,
        run_metadata=run_metadata,
    )
    return {
        "project_id": request.project_id,
        "analysis_month": month_key,
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
        "summary": ticket_classification_summary(db, request.project_id, month_key),
        "usage_run": ticket_cluster_usage_run(db, request.project_id, month_key, run_id),
    }
