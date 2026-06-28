from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import GenAISafetySettings

DEFAULT_SAFETY_SETTINGS: dict[str, Any] = {
    "allow_application_detail_rows": True,
    "allow_ticket_detail_rows": False,
    "allow_aggregate_ticket_data": True,
    "allow_problem_change_data": False,
    "allow_sla_ola_aggregate_data": True,
    "max_rows_returned_to_llm": 100,
    "max_chart_data_points": 500,
    "enforce_complete_month_cutoff": True,
    "mask_sensitive_fields": True,
}


def get_or_create_safety_settings(db: Session) -> GenAISafetySettings:
    settings = (
        db.execute(select(GenAISafetySettings).order_by(GenAISafetySettings.created_at.asc()))
        .scalars()
        .first()
    )
    if settings is not None:
        return settings

    settings = GenAISafetySettings(**DEFAULT_SAFETY_SETTINGS)
    db.add(settings)
    db.commit()
    db.refresh(settings)
    return settings


def update_safety_settings(db: Session, updates: dict[str, Any]) -> GenAISafetySettings:
    settings = get_or_create_safety_settings(db)
    for key, value in updates.items():
        setattr(settings, key, value)
    db.commit()
    db.refresh(settings)
    return settings
