from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import GenAIPromptTemplate
from app.services.genai.default_prompts import DEFAULT_PROMPTS, DEFAULT_PROMPTS_BY_KEY


class PromptTemplateError(ValueError):
    pass


def ensure_default_prompts(db: Session) -> list[GenAIPromptTemplate]:
    rows_by_key = {
        row.prompt_key: row
        for row in db.execute(select(GenAIPromptTemplate)).scalars().all()
    }
    for default_prompt in DEFAULT_PROMPTS:
        row = rows_by_key.get(default_prompt.prompt_key)
        if row is None:
            row = GenAIPromptTemplate(
                prompt_key=default_prompt.prompt_key,
                display_name=default_prompt.display_name,
                description=default_prompt.description,
                default_prompt=default_prompt.default_prompt,
                version=default_prompt.version,
            )
            db.add(row)
            rows_by_key[default_prompt.prompt_key] = row
        else:
            row.display_name = default_prompt.display_name
            row.description = default_prompt.description
            row.default_prompt = default_prompt.default_prompt
            row.version = default_prompt.version
    db.commit()
    return list_prompt_templates(db, ensure_seeded=False)


def list_prompt_templates(
    db: Session,
    *,
    ensure_seeded: bool = True,
) -> list[GenAIPromptTemplate]:
    if ensure_seeded:
        ensure_default_prompts(db)
    return (
        db.execute(select(GenAIPromptTemplate).order_by(GenAIPromptTemplate.prompt_key.asc()))
        .scalars()
        .all()
    )


def get_prompt_template(db: Session, prompt_key: str) -> GenAIPromptTemplate:
    ensure_default_prompts(db)
    row = db.execute(
        select(GenAIPromptTemplate).where(GenAIPromptTemplate.prompt_key == prompt_key),
    ).scalar_one_or_none()
    if row is None:
        raise PromptTemplateError(f"Prompt template '{prompt_key}' was not found.")
    return row


def update_prompt_template(
    db: Session,
    prompt_key: str,
    *,
    custom_prompt: str | None,
    is_custom_enabled: bool,
) -> GenAIPromptTemplate:
    if prompt_key not in DEFAULT_PROMPTS_BY_KEY:
        raise PromptTemplateError("Only default GenAI prompt templates can be customized.")

    row = get_prompt_template(db, prompt_key)
    normalized_prompt = custom_prompt.strip() if custom_prompt and custom_prompt.strip() else None
    if is_custom_enabled and normalized_prompt is None:
        raise PromptTemplateError("Custom prompt text is required when custom override is enabled.")

    row.custom_prompt = normalized_prompt
    row.is_custom_enabled = is_custom_enabled
    db.commit()
    db.refresh(row)
    return row


def reset_prompt_template(db: Session, prompt_key: str) -> GenAIPromptTemplate:
    if prompt_key not in DEFAULT_PROMPTS_BY_KEY:
        raise PromptTemplateError("Only default GenAI prompt templates can be reset.")

    row = get_prompt_template(db, prompt_key)
    row.custom_prompt = None
    row.is_custom_enabled = False
    db.commit()
    db.refresh(row)
    return row
