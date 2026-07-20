import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.mvp8_llm import LlmRecommendation
from app.models.mvp12_recommendation_management import (
    LlmRecommendationActionItem,
    LlmRecommendationDecision,
    LlmRecommendationRevision,
)
from app.schemas.mvp12_recommendation_management import (
    LlmRecommendationActionItemCreate,
    LlmRecommendationActionItemRead,
    LlmRecommendationActionItemUpdate,
    LlmRecommendationDecisionRead,
    LlmRecommendationDecisionRequest,
    LlmRecommendationManagementResponse,
    LlmRecommendationRevisionRead,
    LlmRecommendationRevisionRequest,
)

router = APIRouter(prefix="/api", tags=["MVP 12 Recommendation Management"])

ACCEPTED_DECISIONS = {"accept", "accepted", "approve", "approved"}
REJECTED_DECISIONS = {"reject", "rejected"}
DEFERRED_DECISIONS = {"defer", "deferred", "park", "parked"}
IN_PROGRESS_DECISIONS = {"in progress", "start", "started", "implement", "implementation started"}
NEEDS_REVISION_DECISIONS = {"needs revision", "revise", "revised", "revision required"}


def normalize(value: str | None) -> str:
    return (value or "").strip().lower()


def derive_recommendation_status(decision: str) -> str:
    normalized = normalize(decision)

    if normalized in ACCEPTED_DECISIONS:
        return "Accepted"

    if normalized in REJECTED_DECISIONS:
        return "Rejected"

    if normalized in DEFERRED_DECISIONS:
        return "Deferred"

    if normalized in IN_PROGRESS_DECISIONS:
        return "In Progress"

    if normalized in NEEDS_REVISION_DECISIONS:
        return "Needs Revision"

    if decision.strip():
        return decision.strip()

    return "Draft"


def get_required_recommendation(db: Session, recommendation_id: uuid.UUID) -> LlmRecommendation:
    recommendation = db.get(LlmRecommendation, recommendation_id)

    if recommendation is None:
        raise HTTPException(status_code=404, detail="LLM recommendation not found")

    return recommendation


def get_required_action_item(db: Session, action_item_id: uuid.UUID) -> LlmRecommendationActionItem:
    action_item = db.get(LlmRecommendationActionItem, action_item_id)

    if action_item is None:
        raise HTTPException(status_code=404, detail="LLM recommendation action item not found")

    return action_item


def update_model_from_payload(model: Any, payload: Any) -> None:
    data = payload.model_dump(exclude_unset=True)

    for field_name, value in data.items():
        setattr(model, field_name, value)


@router.post("/llm-recommendations/{recommendation_id}/decision", response_model=LlmRecommendationDecisionRead)
def record_llm_recommendation_decision(
    recommendation_id: uuid.UUID,
    payload: LlmRecommendationDecisionRequest,
    db: Annotated[Session, Depends(get_db)],
) -> LlmRecommendationDecision:
    recommendation = get_required_recommendation(db, recommendation_id)

    previous_status = recommendation.status
    new_status = derive_recommendation_status(payload.decision)

    decision = LlmRecommendationDecision(
        recommendation_id=recommendation.id,
        decision=payload.decision,
        decision_notes=payload.decision_notes,
        previous_status=previous_status,
        new_status=new_status,
        decided_by=payload.decided_by,
        decided_at=datetime.utcnow(),
    )

    recommendation.status = new_status

    db.add(decision)
    db.add(recommendation)
    db.commit()
    db.refresh(decision)

    return decision


@router.get("/llm-recommendation-decisions", response_model=list[LlmRecommendationDecisionRead])
def list_llm_recommendation_decisions(
    db: Annotated[Session, Depends(get_db)],
    recommendation_id: uuid.UUID | None = Query(default=None),
) -> list[LlmRecommendationDecision]:
    statement = select(LlmRecommendationDecision).order_by(LlmRecommendationDecision.decided_at.desc())

    if recommendation_id is not None:
        statement = statement.where(LlmRecommendationDecision.recommendation_id == recommendation_id)

    return list(db.scalars(statement).all())


@router.put("/llm-recommendations/{recommendation_id}/revise", response_model=LlmRecommendationRevisionRead)
def revise_llm_recommendation(
    recommendation_id: uuid.UUID,
    payload: LlmRecommendationRevisionRequest,
    db: Annotated[Session, Depends(get_db)],
) -> LlmRecommendationRevision:
    recommendation = get_required_recommendation(db, recommendation_id)

    revision = LlmRecommendationRevision(
        recommendation_id=recommendation.id,
        previous_title=recommendation.title,
        revised_title=payload.title if payload.title is not None else recommendation.title,
        previous_recommendation_text=recommendation.recommendation_text,
        revised_recommendation_text=(
            payload.recommendation_text
            if payload.recommendation_text is not None
            else recommendation.recommendation_text
        ),
        previous_rationale=recommendation.rationale,
        revised_rationale=payload.rationale if payload.rationale is not None else recommendation.rationale,
        previous_expected_benefit=recommendation.expected_benefit,
        revised_expected_benefit=(
            payload.expected_benefit
            if payload.expected_benefit is not None
            else recommendation.expected_benefit
        ),
        previous_implementation_notes=recommendation.implementation_notes,
        revised_implementation_notes=(
            payload.implementation_notes
            if payload.implementation_notes is not None
            else recommendation.implementation_notes
        ),
        revision_notes=payload.revision_notes,
        revised_by=payload.revised_by,
        revised_at=datetime.utcnow(),
    )

    if payload.title is not None:
        recommendation.title = payload.title

    if payload.recommendation_text is not None:
        recommendation.recommendation_text = payload.recommendation_text

    if payload.rationale is not None:
        recommendation.rationale = payload.rationale

    if payload.expected_benefit is not None:
        recommendation.expected_benefit = payload.expected_benefit

    if payload.implementation_notes is not None:
        recommendation.implementation_notes = payload.implementation_notes

    recommendation.status = "Revised"

    db.add(revision)
    db.add(recommendation)
    db.commit()
    db.refresh(revision)

    return revision


@router.get("/llm-recommendation-revisions", response_model=list[LlmRecommendationRevisionRead])
def list_llm_recommendation_revisions(
    db: Annotated[Session, Depends(get_db)],
    recommendation_id: uuid.UUID | None = Query(default=None),
) -> list[LlmRecommendationRevision]:
    statement = select(LlmRecommendationRevision).order_by(LlmRecommendationRevision.revised_at.desc())

    if recommendation_id is not None:
        statement = statement.where(LlmRecommendationRevision.recommendation_id == recommendation_id)

    return list(db.scalars(statement).all())


@router.post("/llm-recommendation-action-items", response_model=LlmRecommendationActionItemRead)
def create_llm_recommendation_action_item(
    payload: LlmRecommendationActionItemCreate,
    db: Annotated[Session, Depends(get_db)],
) -> LlmRecommendationActionItem:
    recommendation = get_required_recommendation(db, payload.recommendation_id)

    action_item = LlmRecommendationActionItem(
        recommendation_id=recommendation.id,
        deliverable_id=recommendation.deliverable_id,
        task_id=recommendation.task_id,
        subtask_id=recommendation.subtask_id,
        finding_id=recommendation.finding_id,
        analysis_output_id=recommendation.analysis_output_id,
        action_title=payload.action_title,
        action_description=payload.action_description,
        owner_name=payload.owner_name,
        priority=payload.priority,
        status=payload.status,
        due_date=payload.due_date,
        created_by=payload.created_by,
    )

    if normalize(recommendation.status) in {"draft", "accepted", "revised"}:
        recommendation.status = "Action Created"

    db.add(action_item)
    db.add(recommendation)
    db.commit()
    db.refresh(action_item)

    return action_item


@router.get("/llm-recommendation-action-items", response_model=list[LlmRecommendationActionItemRead])
def list_llm_recommendation_action_items(
    db: Annotated[Session, Depends(get_db)],
    recommendation_id: uuid.UUID | None = Query(default=None),
    status: str | None = Query(default=None),
) -> list[LlmRecommendationActionItem]:
    statement = select(LlmRecommendationActionItem).order_by(LlmRecommendationActionItem.created_at.desc())

    if recommendation_id is not None:
        statement = statement.where(LlmRecommendationActionItem.recommendation_id == recommendation_id)

    if status:
        statement = statement.where(LlmRecommendationActionItem.status == status)

    return list(db.scalars(statement).all())


@router.put("/llm-recommendation-action-items/{action_item_id}", response_model=LlmRecommendationActionItemRead)
def update_llm_recommendation_action_item(
    action_item_id: uuid.UUID,
    payload: LlmRecommendationActionItemUpdate,
    db: Annotated[Session, Depends(get_db)],
) -> LlmRecommendationActionItem:
    action_item = get_required_action_item(db, action_item_id)

    previous_status = action_item.status
    update_model_from_payload(action_item, payload)

    if normalize(action_item.status) == "completed" and normalize(previous_status) != "completed":
        action_item.completed_at = datetime.utcnow()

    if normalize(action_item.status) != "completed":
        action_item.completed_at = None

    recommendation = get_required_recommendation(db, action_item.recommendation_id)

    all_action_items = list(
        db.scalars(
            select(LlmRecommendationActionItem)
            .where(LlmRecommendationActionItem.recommendation_id == recommendation.id)
        ).all()
    )

    if all_action_items and all(normalize(item.status) == "completed" for item in all_action_items):
        recommendation.status = "Completed"
    elif any(normalize(item.status) in {"open", "in progress"} for item in all_action_items):
        recommendation.status = "In Progress"

    db.add(action_item)
    db.add(recommendation)
    db.commit()
    db.refresh(action_item)

    return action_item


@router.post("/llm-recommendations/{recommendation_id}/mark-completed", response_model=LlmRecommendationManagementResponse)
def mark_llm_recommendation_completed(
    recommendation_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
) -> LlmRecommendationManagementResponse:
    recommendation = get_required_recommendation(db, recommendation_id)
    recommendation.status = "Completed"

    db.add(recommendation)
    db.commit()

    return LlmRecommendationManagementResponse(
        recommendation_id=recommendation.id,
        status=recommendation.status,
        message="LLM recommendation marked completed.",
    )