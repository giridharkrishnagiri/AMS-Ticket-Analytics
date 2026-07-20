import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import DataPoint, Deliverable, StakeholderQuestion, Subtask, Task
from app.models.mvp5_findings import AnalysisOutput, EvidenceItem, Finding
from app.schemas.mvp5_findings import (
    AnalysisOutputCreate,
    AnalysisOutputRead,
    AnalysisOutputUpdate,
    EvidenceItemCreate,
    EvidenceItemRead,
    EvidenceItemUpdate,
    FindingCreate,
    FindingRead,
    FindingUpdate,
)

router = APIRouter(prefix="/api", tags=["MVP 5 Findings Analysis Evidence"])


def update_model_from_payload(item: Any, payload: Any) -> None:
    data = payload.model_dump(exclude_unset=True)
    for field_name, value in data.items():
        setattr(item, field_name, value)


def validate_optional_reference(db: Session, model: Any, item_id: uuid.UUID | None, label: str) -> None:
    if item_id is None:
        return

    if db.get(model, item_id) is None:
        raise HTTPException(status_code=404, detail=f"{label} not found")


def validate_finding_references(db: Session, payload: FindingCreate | FindingUpdate) -> None:
    subtask_id = getattr(payload, "subtask_id", None)
    if subtask_id is not None and db.get(Subtask, subtask_id) is None:
        raise HTTPException(status_code=404, detail="Sub-task not found")

    validate_optional_reference(db, Task, getattr(payload, "task_id", None), "Task")
    validate_optional_reference(db, Deliverable, getattr(payload, "deliverable_id", None), "Deliverable")


def validate_analysis_references(db: Session, payload: AnalysisOutputCreate | AnalysisOutputUpdate) -> None:
    subtask_id = getattr(payload, "subtask_id", None)
    if subtask_id is not None and db.get(Subtask, subtask_id) is None:
        raise HTTPException(status_code=404, detail="Sub-task not found")

    validate_optional_reference(db, Task, getattr(payload, "task_id", None), "Task")
    validate_optional_reference(db, Deliverable, getattr(payload, "deliverable_id", None), "Deliverable")


def validate_evidence_references(db: Session, payload: EvidenceItemCreate | EvidenceItemUpdate) -> None:
    validate_optional_reference(db, Subtask, getattr(payload, "subtask_id", None), "Sub-task")
    validate_optional_reference(db, Finding, getattr(payload, "finding_id", None), "Finding")
    validate_optional_reference(db, AnalysisOutput, getattr(payload, "analysis_output_id", None), "Analysis output")
    validate_optional_reference(db, DataPoint, getattr(payload, "data_point_id", None), "Data point")
    validate_optional_reference(db, StakeholderQuestion, getattr(payload, "stakeholder_question_id", None), "Stakeholder question")


@router.post("/findings", response_model=FindingRead)
def create_finding(payload: FindingCreate, db: Annotated[Session, Depends(get_db)]) -> Finding:
    validate_finding_references(db, payload)

    item = Finding(**payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.get("/findings", response_model=list[FindingRead])
def list_findings(
    db: Annotated[Session, Depends(get_db)],
    subtask_id: uuid.UUID | None = Query(default=None),
    task_id: uuid.UUID | None = Query(default=None),
    deliverable_id: uuid.UUID | None = Query(default=None),
) -> list[Finding]:
    statement = select(Finding).order_by(Finding.created_at.desc())

    if subtask_id is not None:
        statement = statement.where(Finding.subtask_id == subtask_id)

    if task_id is not None:
        statement = statement.where(Finding.task_id == task_id)

    if deliverable_id is not None:
        statement = statement.where(Finding.deliverable_id == deliverable_id)

    return list(db.scalars(statement).all())


@router.get("/findings/{finding_id}", response_model=FindingRead)
def get_finding(finding_id: uuid.UUID, db: Annotated[Session, Depends(get_db)]) -> Finding:
    item = db.get(Finding, finding_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Finding not found")
    return item


@router.put("/findings/{finding_id}", response_model=FindingRead)
def update_finding(
    finding_id: uuid.UUID,
    payload: FindingUpdate,
    db: Annotated[Session, Depends(get_db)],
) -> Finding:
    item = db.get(Finding, finding_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Finding not found")

    validate_finding_references(db, payload)
    update_model_from_payload(item, payload)

    db.commit()
    db.refresh(item)
    return item


@router.post("/analysis-outputs", response_model=AnalysisOutputRead)
def create_analysis_output(
    payload: AnalysisOutputCreate,
    db: Annotated[Session, Depends(get_db)],
) -> AnalysisOutput:
    validate_analysis_references(db, payload)

    item = AnalysisOutput(**payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.get("/analysis-outputs", response_model=list[AnalysisOutputRead])
def list_analysis_outputs(
    db: Annotated[Session, Depends(get_db)],
    subtask_id: uuid.UUID | None = Query(default=None),
    task_id: uuid.UUID | None = Query(default=None),
    deliverable_id: uuid.UUID | None = Query(default=None),
) -> list[AnalysisOutput]:
    statement = select(AnalysisOutput).order_by(AnalysisOutput.created_at.desc())

    if subtask_id is not None:
        statement = statement.where(AnalysisOutput.subtask_id == subtask_id)

    if task_id is not None:
        statement = statement.where(AnalysisOutput.task_id == task_id)

    if deliverable_id is not None:
        statement = statement.where(AnalysisOutput.deliverable_id == deliverable_id)

    return list(db.scalars(statement).all())


@router.get("/analysis-outputs/{analysis_output_id}", response_model=AnalysisOutputRead)
def get_analysis_output(
    analysis_output_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
) -> AnalysisOutput:
    item = db.get(AnalysisOutput, analysis_output_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Analysis output not found")
    return item


@router.put("/analysis-outputs/{analysis_output_id}", response_model=AnalysisOutputRead)
def update_analysis_output(
    analysis_output_id: uuid.UUID,
    payload: AnalysisOutputUpdate,
    db: Annotated[Session, Depends(get_db)],
) -> AnalysisOutput:
    item = db.get(AnalysisOutput, analysis_output_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Analysis output not found")

    validate_analysis_references(db, payload)
    update_model_from_payload(item, payload)

    db.commit()
    db.refresh(item)
    return item


@router.post("/evidence-items", response_model=EvidenceItemRead)
def create_evidence_item(
    payload: EvidenceItemCreate,
    db: Annotated[Session, Depends(get_db)],
) -> EvidenceItem:
    validate_evidence_references(db, payload)

    item = EvidenceItem(**payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.get("/evidence-items", response_model=list[EvidenceItemRead])
def list_evidence_items(
    db: Annotated[Session, Depends(get_db)],
    subtask_id: uuid.UUID | None = Query(default=None),
    finding_id: uuid.UUID | None = Query(default=None),
    analysis_output_id: uuid.UUID | None = Query(default=None),
    data_point_id: uuid.UUID | None = Query(default=None),
    stakeholder_question_id: uuid.UUID | None = Query(default=None),
) -> list[EvidenceItem]:
    statement = select(EvidenceItem).order_by(EvidenceItem.created_at.desc())

    if subtask_id is not None:
        statement = statement.where(EvidenceItem.subtask_id == subtask_id)

    if finding_id is not None:
        statement = statement.where(EvidenceItem.finding_id == finding_id)

    if analysis_output_id is not None:
        statement = statement.where(EvidenceItem.analysis_output_id == analysis_output_id)

    if data_point_id is not None:
        statement = statement.where(EvidenceItem.data_point_id == data_point_id)

    if stakeholder_question_id is not None:
        statement = statement.where(EvidenceItem.stakeholder_question_id == stakeholder_question_id)

    return list(db.scalars(statement).all())


@router.get("/evidence-items/{evidence_item_id}", response_model=EvidenceItemRead)
def get_evidence_item(
    evidence_item_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
) -> EvidenceItem:
    item = db.get(EvidenceItem, evidence_item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Evidence item not found")
    return item


@router.put("/evidence-items/{evidence_item_id}", response_model=EvidenceItemRead)
def update_evidence_item(
    evidence_item_id: uuid.UUID,
    payload: EvidenceItemUpdate,
    db: Annotated[Session, Depends(get_db)],
) -> EvidenceItem:
    item = db.get(EvidenceItem, evidence_item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Evidence item not found")

    validate_evidence_references(db, payload)
    update_model_from_payload(item, payload)

    db.commit()
    db.refresh(item)
    return item