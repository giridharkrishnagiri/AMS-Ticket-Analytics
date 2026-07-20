import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Deliverable
from app.models.mvp11_review_workflow import (
    DeliverableReviewActionItem,
    DeliverableReviewWorkflow,
)
from app.schemas.mvp11_review_workflow import (
    DeliverableReviewActionItemCreate,
    DeliverableReviewActionItemRead,
    DeliverableReviewActionItemUpdate,
    DeliverableReviewDecisionRequest,
    DeliverableReviewWorkflowCreate,
    DeliverableReviewWorkflowRead,
    DeliverableReviewWorkflowUpdate,
)

router = APIRouter(prefix="/api", tags=["MVP 11 Deliverable Review Workflow"])

APPROVED_DECISIONS = {"approved", "approve", "accepted", "accept"}
REWORK_DECISIONS = {"rework required", "rework", "needs rework", "changes requested"}
REJECTED_DECISIONS = {"rejected", "reject"}
IN_REVIEW_DECISIONS = {"in review", "reviewing"}


def normalize_status(value: str | None) -> str:
    return (value or "").strip().lower()


def update_model_from_payload(model: Any, payload: Any) -> None:
    data = payload.model_dump(exclude_unset=True)

    for field_name, value in data.items():
        setattr(model, field_name, value)


def get_required_deliverable(db: Session, deliverable_id: uuid.UUID) -> Deliverable:
    deliverable = db.get(Deliverable, deliverable_id)

    if deliverable is None:
        raise HTTPException(status_code=404, detail="Deliverable not found")

    return deliverable


def get_required_workflow(db: Session, workflow_id: uuid.UUID) -> DeliverableReviewWorkflow:
    workflow = db.get(DeliverableReviewWorkflow, workflow_id)

    if workflow is None:
        raise HTTPException(status_code=404, detail="Deliverable review workflow not found")

    return workflow


def get_required_action_item(db: Session, action_item_id: uuid.UUID) -> DeliverableReviewActionItem:
    action_item = db.get(DeliverableReviewActionItem, action_item_id)

    if action_item is None:
        raise HTTPException(status_code=404, detail="Deliverable review action item not found")

    return action_item


def derive_workflow_status_from_decision(decision: str) -> str:
    normalized = normalize_status(decision)

    if normalized in APPROVED_DECISIONS:
        return "Approved"

    if normalized in REWORK_DECISIONS:
        return "Rework Required"

    if normalized in REJECTED_DECISIONS:
        return "Rejected"

    if normalized in IN_REVIEW_DECISIONS:
        return "In Review"

    return decision.strip() or "In Review"


def update_deliverable_review_fields(
    deliverable: Deliverable,
    workflow_status: str,
    submitted_at: datetime | None = None,
    decision_at: datetime | None = None,
) -> None:
    deliverable.review_status = workflow_status

    if submitted_at is not None:
        deliverable.submission_date = submitted_at.date()

    if normalize_status(workflow_status) == "approved" and decision_at is not None:
        deliverable.approval_date = decision_at.date()


@router.post("/deliverable-review-workflows", response_model=DeliverableReviewWorkflowRead)
def create_review_workflow(
    payload: DeliverableReviewWorkflowCreate,
    db: Annotated[Session, Depends(get_db)],
) -> DeliverableReviewWorkflow:
    deliverable = get_required_deliverable(db, payload.deliverable_id)

    existing_current_workflows = list(
        db.scalars(
            select(DeliverableReviewWorkflow)
            .where(DeliverableReviewWorkflow.deliverable_id == payload.deliverable_id)
            .where(DeliverableReviewWorkflow.is_current == True)  # noqa: E712
        ).all()
    )

    for existing in existing_current_workflows:
        existing.is_current = False

    submitted_at = datetime.utcnow()

    workflow = DeliverableReviewWorkflow(
        deliverable_id=payload.deliverable_id,
        workflow_title=payload.workflow_title,
        workflow_status=payload.workflow_status,
        review_type=payload.review_type,
        submitted_by=payload.submitted_by,
        submitted_at=submitted_at,
        reviewer_name=payload.reviewer_name,
        reviewer_role=payload.reviewer_role,
        review_due_date=payload.review_due_date,
        review_notes=payload.review_notes,
        created_by=payload.created_by,
        is_current=True,
    )

    update_deliverable_review_fields(
        deliverable=deliverable,
        workflow_status=payload.workflow_status,
        submitted_at=submitted_at,
    )

    db.add(workflow)
    db.add(deliverable)
    db.commit()
    db.refresh(workflow)

    return workflow


@router.get("/deliverable-review-workflows", response_model=list[DeliverableReviewWorkflowRead])
def list_review_workflows(
    db: Annotated[Session, Depends(get_db)],
    deliverable_id: uuid.UUID | None = Query(default=None),
    current_only: bool = Query(default=False),
) -> list[DeliverableReviewWorkflow]:
    statement = select(DeliverableReviewWorkflow).order_by(DeliverableReviewWorkflow.created_at.desc())

    if deliverable_id is not None:
        statement = statement.where(DeliverableReviewWorkflow.deliverable_id == deliverable_id)

    if current_only:
        statement = statement.where(DeliverableReviewWorkflow.is_current == True)  # noqa: E712

    return list(db.scalars(statement).all())


@router.get("/deliverable-review-workflows/{workflow_id}", response_model=DeliverableReviewWorkflowRead)
def get_review_workflow(
    workflow_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
) -> DeliverableReviewWorkflow:
    return get_required_workflow(db, workflow_id)


@router.put("/deliverable-review-workflows/{workflow_id}", response_model=DeliverableReviewWorkflowRead)
def update_review_workflow(
    workflow_id: uuid.UUID,
    payload: DeliverableReviewWorkflowUpdate,
    db: Annotated[Session, Depends(get_db)],
) -> DeliverableReviewWorkflow:
    workflow = get_required_workflow(db, workflow_id)
    deliverable = get_required_deliverable(db, workflow.deliverable_id)

    update_model_from_payload(workflow, payload)

    if payload.workflow_status is not None:
        update_deliverable_review_fields(
            deliverable=deliverable,
            workflow_status=workflow.workflow_status,
            submitted_at=workflow.submitted_at,
            decision_at=workflow.decision_at,
        )

    db.add(workflow)
    db.add(deliverable)
    db.commit()
    db.refresh(workflow)

    return workflow


@router.post("/deliverable-review-workflows/{workflow_id}/decision", response_model=DeliverableReviewWorkflowRead)
def record_review_decision(
    workflow_id: uuid.UUID,
    payload: DeliverableReviewDecisionRequest,
    db: Annotated[Session, Depends(get_db)],
) -> DeliverableReviewWorkflow:
    workflow = get_required_workflow(db, workflow_id)
    deliverable = get_required_deliverable(db, workflow.deliverable_id)

    decision_at = datetime.utcnow()
    workflow_status = derive_workflow_status_from_decision(payload.decision)

    workflow.review_decision = payload.decision
    workflow.workflow_status = workflow_status
    workflow.decision_by = payload.decision_by
    workflow.decision_at = decision_at

    if payload.review_notes is not None:
        workflow.review_notes = payload.review_notes

    if payload.approval_notes is not None:
        workflow.approval_notes = payload.approval_notes

    if payload.rework_notes is not None:
        workflow.rework_notes = payload.rework_notes

    update_deliverable_review_fields(
        deliverable=deliverable,
        workflow_status=workflow_status,
        submitted_at=workflow.submitted_at,
        decision_at=decision_at,
    )

    db.add(workflow)
    db.add(deliverable)
    db.commit()
    db.refresh(workflow)

    return workflow


@router.post("/deliverable-review-action-items", response_model=DeliverableReviewActionItemRead)
def create_review_action_item(
    payload: DeliverableReviewActionItemCreate,
    db: Annotated[Session, Depends(get_db)],
) -> DeliverableReviewActionItem:
    workflow = get_required_workflow(db, payload.review_workflow_id)

    action_item = DeliverableReviewActionItem(
        review_workflow_id=workflow.id,
        deliverable_id=workflow.deliverable_id,
        action_title=payload.action_title,
        action_description=payload.action_description,
        owner_name=payload.owner_name,
        priority=payload.priority,
        status=payload.status,
        due_date=payload.due_date,
        created_by=payload.created_by,
    )

    db.add(action_item)
    db.commit()
    db.refresh(action_item)

    return action_item


@router.get("/deliverable-review-action-items", response_model=list[DeliverableReviewActionItemRead])
def list_review_action_items(
    db: Annotated[Session, Depends(get_db)],
    review_workflow_id: uuid.UUID | None = Query(default=None),
    deliverable_id: uuid.UUID | None = Query(default=None),
    status: str | None = Query(default=None),
) -> list[DeliverableReviewActionItem]:
    statement = select(DeliverableReviewActionItem).order_by(
        DeliverableReviewActionItem.created_at.desc()
    )

    if review_workflow_id is not None:
        statement = statement.where(DeliverableReviewActionItem.review_workflow_id == review_workflow_id)

    if deliverable_id is not None:
        statement = statement.where(DeliverableReviewActionItem.deliverable_id == deliverable_id)

    if status:
        statement = statement.where(DeliverableReviewActionItem.status == status)

    return list(db.scalars(statement).all())


@router.put("/deliverable-review-action-items/{action_item_id}", response_model=DeliverableReviewActionItemRead)
def update_review_action_item(
    action_item_id: uuid.UUID,
    payload: DeliverableReviewActionItemUpdate,
    db: Annotated[Session, Depends(get_db)],
) -> DeliverableReviewActionItem:
    action_item = get_required_action_item(db, action_item_id)

    previous_status = action_item.status
    update_model_from_payload(action_item, payload)

    if normalize_status(action_item.status) == "completed" and normalize_status(previous_status) != "completed":
        action_item.completed_at = datetime.utcnow()

    if normalize_status(action_item.status) != "completed":
        action_item.completed_at = None

    db.add(action_item)
    db.commit()
    db.refresh(action_item)

    return action_item