from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import GenAIConfig

DEFAULT_CONFIG: dict[str, Any] = {
    "is_enabled": False,
    "provider": "openai",
    "model_name": None,
    "temperature": 0.2,
    "top_p": 1.0,
    "max_output_tokens": 1000,
    "timeout_seconds": 60,
    "max_tool_calls": 5,
    "allow_recommendations": True,
    "allow_chart_generation": False,
    "response_style": "standard",
}


def get_or_create_config(db: Session) -> GenAIConfig:
    config = (
        db.execute(select(GenAIConfig).order_by(GenAIConfig.created_at.asc()))
        .scalars()
        .first()
    )
    if config is not None:
        return config

    config = GenAIConfig(**DEFAULT_CONFIG)
    db.add(config)
    db.commit()
    db.refresh(config)
    return config


def normalize_config_updates(updates: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(updates)
    if "model_name" in normalized and normalized["model_name"] is not None:
        normalized["model_name"] = normalized["model_name"].strip() or None
    if "provider" in normalized and normalized["provider"] is not None:
        normalized["provider"] = normalized["provider"].strip().lower()
    if "response_style" in normalized and normalized["response_style"] is not None:
        normalized["response_style"] = normalized["response_style"].strip().lower()
    return normalized


def update_config(db: Session, updates: dict[str, Any]) -> GenAIConfig:
    config = get_or_create_config(db)
    for key, value in normalize_config_updates(updates).items():
        setattr(config, key, value)
    db.commit()
    db.refresh(config)
    return config
