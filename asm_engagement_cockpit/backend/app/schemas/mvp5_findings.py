import uuid
from datetime import date, datetime
from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, ConfigDict


def empty_string_to_none(value: Any) -> Any:
    if value == "":
        return None
    return value


OptionalDate = Annotated[date | None, BeforeValidator(empty_string_to_none)]


class FindingBase(BaseModel):
    subtask_id: uuid.UUID
    task_id: uuid.UUID | None = None
    deliverable_id: uuid.UUID | None = None

    title: str
    finding_type: str | None = None
    severity: str | None = None

    finding_text: str
    business_impact: str | None = None
    recommendation: str | None = None

    status: str = "Draft"
    confidence_level: str | None = None

    is_validated: bool = False
    validated_by: str | None = None
    validated_date: OptionalDate = None


class FindingCreate(FindingBase):
    pass


class FindingUpdate(BaseModel):
    task_id: uuid.UUID | None = None
    deliverable_id: uuid.UUID | None = None

    title: str | None = None
    finding_type: str | None = None
    severity: str | None = None

    finding_text: str | None = None
    business_impact: str | None = None
    recommendation: str | None = None

    status: str | None = None
    confidence_level: str | None = None

    is_validated: bool | None = None
    validated_by: str | None = None
    validated_date: OptionalDate = None


class FindingRead(FindingBase):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AnalysisOutputBase(BaseModel):
    subtask_id: uuid.UUID
    task_id: uuid.UUID | None = None
    deliverable_id: uuid.UUID | None = None

    analysis_title: str
    analysis_type: str | None = None

    analysis_text: str
    methodology: str | None = None
    assumptions: str | None = None
    limitations: str | None = None

    status: str = "Draft"
    confidence_level: str | None = None

    reviewed_by: str | None = None
    reviewed_date: OptionalDate = None


class AnalysisOutputCreate(AnalysisOutputBase):
    pass


class AnalysisOutputUpdate(BaseModel):
    task_id: uuid.UUID | None = None
    deliverable_id: uuid.UUID | None = None

    analysis_title: str | None = None
    analysis_type: str | None = None

    analysis_text: str | None = None
    methodology: str | None = None
    assumptions: str | None = None
    limitations: str | None = None

    status: str | None = None
    confidence_level: str | None = None

    reviewed_by: str | None = None
    reviewed_date: OptionalDate = None


class AnalysisOutputRead(AnalysisOutputBase):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EvidenceItemBase(BaseModel):
    subtask_id: uuid.UUID | None = None
    finding_id: uuid.UUID | None = None
    analysis_output_id: uuid.UUID | None = None
    data_point_id: uuid.UUID | None = None
    stakeholder_question_id: uuid.UUID | None = None

    evidence_type: str
    title: str
    description: str | None = None

    source_name: str | None = None
    source_reference: str | None = None
    evidence_date: OptionalDate = None

    confidence_level: str | None = None
    is_primary_evidence: bool = False

    notes: str | None = None


class EvidenceItemCreate(EvidenceItemBase):
    pass


class EvidenceItemUpdate(BaseModel):
    subtask_id: uuid.UUID | None = None
    finding_id: uuid.UUID | None = None
    analysis_output_id: uuid.UUID | None = None
    data_point_id: uuid.UUID | None = None
    stakeholder_question_id: uuid.UUID | None = None

    evidence_type: str | None = None
    title: str | None = None
    description: str | None = None

    source_name: str | None = None
    source_reference: str | None = None
    evidence_date: OptionalDate = None

    confidence_level: str | None = None
    is_primary_evidence: bool | None = None

    notes: str | None = None


class EvidenceItemRead(EvidenceItemBase):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)