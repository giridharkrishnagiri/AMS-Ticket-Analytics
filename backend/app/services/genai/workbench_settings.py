from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import GenAIWorkbenchSetting, Ticket

WORKBENCH_SETTINGS_KEY = "default"
LEVEL_CLUSTER_MODES = {"capped", "threshold_only"}
CLUSTER_MODES = {"adaptive", "fixed"}
PAYLOAD_KEY_PATTERN = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True)
class TicketColumnDefinition:
    key: str
    label: str
    description: str
    direct_attrs: tuple[str, ...] = ()
    payload_keys: tuple[str, ...] = ()
    max_chars: int = 1200


TICKET_COLUMN_DEFINITIONS: tuple[TicketColumnDefinition, ...] = (
    TicketColumnDefinition(
        key="ticket_type",
        label="Ticket type",
        description="Incident or Service Catalog Task.",
        direct_attrs=("ticket_type",),
        max_chars=80,
    ),
    TicketColumnDefinition(
        key="short_description",
        label="Short description",
        description="Primary ticket title or short description.",
        direct_attrs=("short_description",),
        payload_keys=("short_description", "short description", "title"),
        max_chars=500,
    ),
    TicketColumnDefinition(
        key="description",
        label="Description",
        description="Detailed requester or system-generated ticket description.",
        direct_attrs=("description",),
        payload_keys=("description", "details", "detailed_description"),
        max_chars=1600,
    ),
    TicketColumnDefinition(
        key="existing_category",
        label="Existing category",
        description="Current ServiceNow category value.",
        direct_attrs=("category",),
        max_chars=255,
    ),
    TicketColumnDefinition(
        key="existing_subcategory",
        label="Existing subcategory",
        description="Current ServiceNow subcategory value.",
        direct_attrs=("subcategory",),
        max_chars=255,
    ),
    TicketColumnDefinition(
        key="catalog_item",
        label="Catalog item",
        description="Service catalog item code or short name.",
        direct_attrs=("catalog_item",),
        max_chars=255,
    ),
    TicketColumnDefinition(
        key="catalog_item_name",
        label="Catalog item name",
        description="Full service catalog item name.",
        direct_attrs=("catalog_item_name",),
        max_chars=500,
    ),
    TicketColumnDefinition(
        key="business_service",
        label="Business service / CI",
        description="Business service, service CI, or configuration item.",
        direct_attrs=("business_service", "business_service_ci_name", "cmdb_ci"),
        payload_keys=("business_service", "business service", "configuration_item", "cmdb_ci"),
        max_chars=255,
    ),
    TicketColumnDefinition(
        key="close_notes",
        label="Close notes",
        description="Resolution notes captured when the ticket was closed.",
        payload_keys=(
            "close_notes",
            "close notes",
            "close_note",
            "resolution_notes",
            "resolution notes",
            "resolved_notes",
            "fix_notes",
        ),
        max_chars=1200,
    ),
    TicketColumnDefinition(
        key="work_notes",
        label="Work notes",
        description="Engineer activity notes, comments, or work-log details.",
        payload_keys=(
            "work_notes",
            "work notes",
            "comments_and_work_notes",
            "comments and work notes",
            "activity",
            "activity_notes",
        ),
        max_chars=1800,
    ),
)

TICKET_COLUMN_BY_KEY = {definition.key: definition for definition in TICKET_COLUMN_DEFINITIONS}
DEFAULT_CLUSTERING_COLUMNS = ["ticket_type", "short_description", "description"]
DEFAULT_CLASSIFICATION_COLUMNS = [
    "ticket_type",
    "short_description",
    "description",
    "existing_category",
    "existing_subcategory",
    "catalog_item",
    "catalog_item_name",
]
DEFAULT_AUTOMATION_COLUMNS = [
    "ticket_type",
    "short_description",
    "description",
    "business_service",
    "close_notes",
    "work_notes",
]


@dataclass(frozen=True)
class GenAIWorkbenchRuntimeSettings:
    genai_ticket_classification_button_enabled: bool
    genai_ticket_cluster_analysis_button_enabled: bool
    genai_ticket_automation_analysis_button_enabled: bool
    genai_ticket_classification_model_name: str | None
    genai_ticket_classification_max_output_tokens: int | None
    genai_ticket_cluster_embedding_model_name: str
    genai_ticket_cluster_label_model_name: str | None
    genai_ticket_cluster_label_max_output_tokens: int | None
    genai_ticket_cluster_embedding_batch_size: int
    genai_ticket_cluster_label_batch_size: int
    genai_ticket_cluster_mode: str
    genai_ticket_cluster_level_1_mode: str
    genai_ticket_cluster_level_2_mode: str
    genai_ticket_cluster_level_3_mode: str
    genai_ticket_cluster_level_1_count: int
    genai_ticket_cluster_level_2_count: int
    genai_ticket_cluster_level_3_count: int
    genai_ticket_cluster_level_1_distance_threshold: float
    genai_ticket_cluster_level_2_distance_threshold: float
    genai_ticket_cluster_level_3_distance_threshold: float
    genai_ticket_cluster_min_llm_label_ticket_count: int
    genai_ticket_cluster_representative_ticket_count: int
    genai_ticket_automation_model_name: str | None
    genai_ticket_automation_max_output_tokens: int | None
    genai_ticket_automation_representative_ticket_count: int
    genai_ticket_automation_clusters_per_request: int
    clustering_columns: list[str]
    classification_columns: list[str]
    automation_columns: list[str]


def _clean_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _int_setting(value: Any, default_value: int, *, minimum: int, maximum: int) -> int:
    try:
        candidate = int(value)
    except (TypeError, ValueError):
        candidate = default_value
    return max(minimum, min(candidate, maximum))


def _nullable_int_setting(
    value: Any,
    default_value: int | None,
    *,
    minimum: int,
    maximum: int,
) -> int | None:
    if value in (None, ""):
        return default_value
    return _int_setting(value, default_value or minimum, minimum=minimum, maximum=maximum)


def _float_setting(value: Any, default_value: float, *, minimum: float, maximum: float) -> float:
    try:
        candidate = float(value)
    except (TypeError, ValueError):
        candidate = default_value
    return max(minimum, min(candidate, maximum))


def _bool_setting(value: Any, default_value: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "y", "on"}:
            return True
        if normalized in {"0", "false", "no", "n", "off"}:
            return False
    return default_value


def _cluster_mode(value: Any, default_value: str = "adaptive") -> str:
    mode = str(value or "").strip().lower().replace("-", "_")
    return mode if mode in CLUSTER_MODES else default_value


def _level_mode(value: Any, default_value: str = "capped") -> str:
    mode = str(value or "").strip().lower().replace("-", "_")
    aliases = {
        "adaptive": "capped",
        "cap": "capped",
        "count_cap": "capped",
        "count_capped": "capped",
        "capped": "capped",
        "distance": "threshold_only",
        "distance_only": "threshold_only",
        "fixed": "threshold_only",
        "threshold": "threshold_only",
        "threshold_only": "threshold_only",
    }
    normalized = aliases.get(mode)
    if normalized in LEVEL_CLUSTER_MODES:
        return normalized
    return default_value


def normalize_column_keys(value: Any, default_value: list[str]) -> list[str]:
    if isinstance(value, str):
        raw_values = [part.strip() for part in value.split(",")]
    elif isinstance(value, list | tuple | set):
        raw_values = [str(part).strip() for part in value]
    else:
        raw_values = []
    selected: list[str] = []
    for key in raw_values:
        if key in TICKET_COLUMN_BY_KEY and key not in selected:
            selected.append(key)
    return selected or list(default_value)


def env_default_settings() -> dict[str, Any]:
    settings = get_settings()
    return {
        "ticket_classification_button_enabled": settings.genai_ticket_classification_button_enabled,
        "ticket_cluster_analysis_button_enabled": (
            settings.genai_ticket_cluster_analysis_button_enabled
        ),
        "ticket_automation_analysis_button_enabled": (
            settings.genai_ticket_automation_analysis_button_enabled
        ),
        "ticket_classification_model_name": settings.genai_ticket_classification_model_name,
        "ticket_classification_max_output_tokens": (
            settings.genai_ticket_classification_max_output_tokens
        ),
        "cluster_embedding_model_name": settings.genai_ticket_cluster_embedding_model_name,
        "cluster_label_model_name": settings.genai_ticket_cluster_label_model_name,
        "cluster_label_max_output_tokens": settings.genai_ticket_cluster_label_max_output_tokens,
        "cluster_embedding_batch_size": settings.genai_ticket_cluster_embedding_batch_size,
        "cluster_label_batch_size": settings.genai_ticket_cluster_label_batch_size,
        "cluster_mode": settings.genai_ticket_cluster_mode,
        "cluster_level_1_mode": settings.genai_ticket_cluster_level_1_mode,
        "cluster_level_2_mode": settings.genai_ticket_cluster_level_2_mode,
        "cluster_level_3_mode": settings.genai_ticket_cluster_level_3_mode,
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
        "cluster_min_llm_label_ticket_count": (
            settings.genai_ticket_cluster_min_llm_label_ticket_count
        ),
        "cluster_representative_ticket_count": (
            settings.genai_ticket_cluster_representative_ticket_count
        ),
        "automation_model_name": settings.genai_ticket_automation_model_name,
        "automation_max_output_tokens": settings.genai_ticket_automation_max_output_tokens,
        "automation_representative_ticket_count": (
            settings.genai_ticket_automation_representative_ticket_count
        ),
        "automation_clusters_per_request": settings.genai_ticket_automation_clusters_per_request,
        "clustering_columns": DEFAULT_CLUSTERING_COLUMNS,
        "classification_columns": DEFAULT_CLASSIFICATION_COLUMNS,
        "automation_columns": DEFAULT_AUTOMATION_COLUMNS,
    }


def normalize_workbench_settings(raw_settings: dict[str, Any] | None = None) -> dict[str, Any]:
    defaults = env_default_settings()
    values = {**defaults, **(raw_settings or {})}
    return {
        "ticket_classification_button_enabled": _bool_setting(
            values.get("ticket_classification_button_enabled"),
            bool(defaults["ticket_classification_button_enabled"]),
        ),
        "ticket_cluster_analysis_button_enabled": _bool_setting(
            values.get("ticket_cluster_analysis_button_enabled"),
            bool(defaults["ticket_cluster_analysis_button_enabled"]),
        ),
        "ticket_automation_analysis_button_enabled": _bool_setting(
            values.get("ticket_automation_analysis_button_enabled"),
            bool(defaults["ticket_automation_analysis_button_enabled"]),
        ),
        "ticket_classification_model_name": _clean_string(
            values.get("ticket_classification_model_name"),
        ),
        "ticket_classification_max_output_tokens": _nullable_int_setting(
            values.get("ticket_classification_max_output_tokens"),
            defaults.get("ticket_classification_max_output_tokens"),
            minimum=500,
            maximum=32000,
        ),
        "cluster_embedding_model_name": _clean_string(
            values.get("cluster_embedding_model_name"),
        )
        or "text-embedding-3-small",
        "cluster_label_model_name": _clean_string(values.get("cluster_label_model_name")),
        "cluster_label_max_output_tokens": _nullable_int_setting(
            values.get("cluster_label_max_output_tokens"),
            defaults.get("cluster_label_max_output_tokens"),
            minimum=500,
            maximum=32000,
        ),
        "cluster_embedding_batch_size": _int_setting(
            values.get("cluster_embedding_batch_size"),
            int(defaults["cluster_embedding_batch_size"]),
            minimum=1,
            maximum=500,
        ),
        "cluster_label_batch_size": _int_setting(
            values.get("cluster_label_batch_size"),
            int(defaults["cluster_label_batch_size"]),
            minimum=1,
            maximum=50,
        ),
        "cluster_mode": _cluster_mode(values.get("cluster_mode")),
        "cluster_level_1_mode": _level_mode(values.get("cluster_level_1_mode"), "capped"),
        "cluster_level_2_mode": _level_mode(values.get("cluster_level_2_mode"), "capped"),
        "cluster_level_3_mode": _level_mode(
            values.get("cluster_level_3_mode"),
            "threshold_only",
        ),
        "cluster_level_1_count": _int_setting(
            values.get("cluster_level_1_count"),
            int(defaults["cluster_level_1_count"]),
            minimum=1,
            maximum=5000,
        ),
        "cluster_level_2_count": _int_setting(
            values.get("cluster_level_2_count"),
            int(defaults["cluster_level_2_count"]),
            minimum=1,
            maximum=10000,
        ),
        "cluster_level_3_count": _int_setting(
            values.get("cluster_level_3_count"),
            int(defaults["cluster_level_3_count"]),
            minimum=1,
            maximum=25000,
        ),
        "cluster_level_1_distance_threshold": _float_setting(
            values.get("cluster_level_1_distance_threshold"),
            float(defaults["cluster_level_1_distance_threshold"]),
            minimum=0.01,
            maximum=1.5,
        ),
        "cluster_level_2_distance_threshold": _float_setting(
            values.get("cluster_level_2_distance_threshold"),
            float(defaults["cluster_level_2_distance_threshold"]),
            minimum=0.01,
            maximum=1.5,
        ),
        "cluster_level_3_distance_threshold": _float_setting(
            values.get("cluster_level_3_distance_threshold"),
            float(defaults["cluster_level_3_distance_threshold"]),
            minimum=0.01,
            maximum=1.5,
        ),
        "cluster_min_llm_label_ticket_count": _int_setting(
            values.get("cluster_min_llm_label_ticket_count"),
            int(defaults["cluster_min_llm_label_ticket_count"]),
            minimum=1,
            maximum=100,
        ),
        "cluster_representative_ticket_count": _int_setting(
            values.get("cluster_representative_ticket_count"),
            int(defaults["cluster_representative_ticket_count"]),
            minimum=1,
            maximum=50,
        ),
        "automation_model_name": _clean_string(values.get("automation_model_name")),
        "automation_max_output_tokens": _nullable_int_setting(
            values.get("automation_max_output_tokens"),
            defaults.get("automation_max_output_tokens"),
            minimum=500,
            maximum=32000,
        ),
        "automation_representative_ticket_count": _int_setting(
            values.get("automation_representative_ticket_count"),
            int(defaults["automation_representative_ticket_count"]),
            minimum=1,
            maximum=50,
        ),
        "automation_clusters_per_request": _int_setting(
            values.get("automation_clusters_per_request"),
            int(defaults["automation_clusters_per_request"]),
            minimum=1,
            maximum=50,
        ),
        "clustering_columns": normalize_column_keys(
            values.get("clustering_columns"),
            DEFAULT_CLUSTERING_COLUMNS,
        ),
        "classification_columns": normalize_column_keys(
            values.get("classification_columns"),
            DEFAULT_CLASSIFICATION_COLUMNS,
        ),
        "automation_columns": normalize_column_keys(
            values.get("automation_columns"),
            DEFAULT_AUTOMATION_COLUMNS,
        ),
    }


def settings_to_runtime(settings: dict[str, Any]) -> GenAIWorkbenchRuntimeSettings:
    return GenAIWorkbenchRuntimeSettings(
        genai_ticket_classification_button_enabled=settings[
            "ticket_classification_button_enabled"
        ],
        genai_ticket_cluster_analysis_button_enabled=settings[
            "ticket_cluster_analysis_button_enabled"
        ],
        genai_ticket_automation_analysis_button_enabled=settings[
            "ticket_automation_analysis_button_enabled"
        ],
        genai_ticket_classification_model_name=settings["ticket_classification_model_name"],
        genai_ticket_classification_max_output_tokens=settings[
            "ticket_classification_max_output_tokens"
        ],
        genai_ticket_cluster_embedding_model_name=settings["cluster_embedding_model_name"],
        genai_ticket_cluster_label_model_name=settings["cluster_label_model_name"],
        genai_ticket_cluster_label_max_output_tokens=settings["cluster_label_max_output_tokens"],
        genai_ticket_cluster_embedding_batch_size=settings["cluster_embedding_batch_size"],
        genai_ticket_cluster_label_batch_size=settings["cluster_label_batch_size"],
        genai_ticket_cluster_mode=settings["cluster_mode"],
        genai_ticket_cluster_level_1_mode=settings["cluster_level_1_mode"],
        genai_ticket_cluster_level_2_mode=settings["cluster_level_2_mode"],
        genai_ticket_cluster_level_3_mode=settings["cluster_level_3_mode"],
        genai_ticket_cluster_level_1_count=settings["cluster_level_1_count"],
        genai_ticket_cluster_level_2_count=settings["cluster_level_2_count"],
        genai_ticket_cluster_level_3_count=settings["cluster_level_3_count"],
        genai_ticket_cluster_level_1_distance_threshold=settings[
            "cluster_level_1_distance_threshold"
        ],
        genai_ticket_cluster_level_2_distance_threshold=settings[
            "cluster_level_2_distance_threshold"
        ],
        genai_ticket_cluster_level_3_distance_threshold=settings[
            "cluster_level_3_distance_threshold"
        ],
        genai_ticket_cluster_min_llm_label_ticket_count=settings[
            "cluster_min_llm_label_ticket_count"
        ],
        genai_ticket_cluster_representative_ticket_count=settings[
            "cluster_representative_ticket_count"
        ],
        genai_ticket_automation_model_name=settings["automation_model_name"],
        genai_ticket_automation_max_output_tokens=settings["automation_max_output_tokens"],
        genai_ticket_automation_representative_ticket_count=settings[
            "automation_representative_ticket_count"
        ],
        genai_ticket_automation_clusters_per_request=settings[
            "automation_clusters_per_request"
        ],
        clustering_columns=list(settings["clustering_columns"]),
        classification_columns=list(settings["classification_columns"]),
        automation_columns=list(settings["automation_columns"]),
    )


def _get_or_create_row(db: Session) -> GenAIWorkbenchSetting:
    row = db.execute(
        select(GenAIWorkbenchSetting).where(
            GenAIWorkbenchSetting.settings_key == WORKBENCH_SETTINGS_KEY,
        ),
    ).scalar_one_or_none()
    if row is not None:
        return row
    row = GenAIWorkbenchSetting(
        settings_key=WORKBENCH_SETTINGS_KEY,
        settings_json=normalize_workbench_settings({}),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_effective_workbench_settings(db: Session) -> GenAIWorkbenchRuntimeSettings:
    row = _get_or_create_row(db)
    normalized = normalize_workbench_settings(row.settings_json)
    if normalized != row.settings_json:
        row.settings_json = normalized
        db.commit()
        db.refresh(row)
    return settings_to_runtime(normalized)


def workbench_settings_response(db: Session) -> dict[str, Any]:
    runtime_settings = get_effective_workbench_settings(db)
    response = runtime_settings_response(runtime_settings)
    response["available_ticket_columns"] = [
        {
            "key": definition.key,
            "label": definition.label,
            "description": definition.description,
        }
        for definition in TICKET_COLUMN_DEFINITIONS
    ]
    return response


def update_workbench_settings(db: Session, updates: dict[str, Any]) -> dict[str, Any]:
    row = _get_or_create_row(db)
    merged = {**normalize_workbench_settings(row.settings_json), **updates}
    row.settings_json = normalize_workbench_settings(merged)
    db.commit()
    db.refresh(row)
    return workbench_settings_response(db)


def runtime_settings_response(settings: GenAIWorkbenchRuntimeSettings) -> dict[str, Any]:
    return {
        "ticket_classification_button_enabled": (
            settings.genai_ticket_classification_button_enabled
        ),
        "ticket_cluster_analysis_button_enabled": (
            settings.genai_ticket_cluster_analysis_button_enabled
        ),
        "ticket_automation_analysis_button_enabled": (
            settings.genai_ticket_automation_analysis_button_enabled
        ),
        "ticket_classification_model_name": settings.genai_ticket_classification_model_name,
        "ticket_classification_max_output_tokens": (
            settings.genai_ticket_classification_max_output_tokens
        ),
        "cluster_embedding_model_name": settings.genai_ticket_cluster_embedding_model_name,
        "cluster_label_model_name": settings.genai_ticket_cluster_label_model_name,
        "cluster_label_max_output_tokens": (
            settings.genai_ticket_cluster_label_max_output_tokens
        ),
        "cluster_mode": settings.genai_ticket_cluster_mode,
        "cluster_level_1_mode": settings.genai_ticket_cluster_level_1_mode,
        "cluster_level_2_mode": settings.genai_ticket_cluster_level_2_mode,
        "cluster_level_3_mode": settings.genai_ticket_cluster_level_3_mode,
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
        "cluster_min_llm_label_ticket_count": (
            settings.genai_ticket_cluster_min_llm_label_ticket_count
        ),
        "cluster_representative_ticket_count": (
            settings.genai_ticket_cluster_representative_ticket_count
        ),
        "automation_model_name": settings.genai_ticket_automation_model_name,
        "automation_max_output_tokens": settings.genai_ticket_automation_max_output_tokens,
        "automation_representative_ticket_count": (
            settings.genai_ticket_automation_representative_ticket_count
        ),
        "automation_clusters_per_request": (
            settings.genai_ticket_automation_clusters_per_request
        ),
        "clustering_columns": list(settings.clustering_columns),
        "classification_columns": list(settings.classification_columns),
        "automation_columns": list(settings.automation_columns),
    }


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


def compact_value(value: Any, *, max_chars: int) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    text = re.sub(r"\s+", " ", text)
    if len(text) > max_chars:
        return text[:max_chars].rstrip()
    return text


def ticket_field_text(ticket: Ticket, key: str) -> str | None:
    definition = TICKET_COLUMN_BY_KEY.get(key)
    if definition is None:
        return None
    for attr in definition.direct_attrs:
        value = getattr(ticket, attr, None)
        text = compact_value(value, max_chars=definition.max_chars)
        if text:
            return text
    value = payload_value(ticket, definition.payload_keys)
    return compact_value(value, max_chars=definition.max_chars)


def selected_ticket_payload(
    ticket: Ticket,
    column_keys: list[str] | tuple[str, ...],
    *,
    default_columns: list[str],
    include_empty_columns: bool = True,
) -> dict[str, Any]:
    selected_columns = normalize_column_keys(list(column_keys), default_columns)
    payload: dict[str, Any] = {"ticket_number": ticket.ticket_number}
    for key in selected_columns:
        value = ticket_field_text(ticket, key)
        if value is not None or include_empty_columns:
            payload[key] = value
    return payload


def runtime_settings_metadata(settings: GenAIWorkbenchRuntimeSettings) -> dict[str, Any]:
    metadata = runtime_settings_response(settings)
    return {
        key: value
        for key, value in metadata.items()
        if key
        not in {
            "available_ticket_columns",
        }
    }


def runtime_settings_hash(settings: GenAIWorkbenchRuntimeSettings) -> str:
    import hashlib
    import json

    payload = asdict(settings)
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
