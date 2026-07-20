import uuid
from datetime import date, datetime
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict


def empty_string_to_none(value):
    if value == "":
        return None
    return value


OptionalDate = Annotated[date | None, BeforeValidator(empty_string_to_none)]


class TimesheetEntryBase(BaseModel):
    entry_date: date
    person_name: str = "Giridhar Krishnagiri"

    workstream_id: uuid.UUID | None = None
    deliverable_id: uuid.UUID | None = None
    task_id: uuid.UUID | None = None
    subtask_id: uuid.UUID | None = None

    activity_type: str = "Delivery"
    accomplishments: str
    blockers: str | None = None
    next_steps: str | None = None

    effort_hours: float = 0.0
    status: str = "Draft"


class TimesheetEntryCreate(TimesheetEntryBase):
    pass


class TimesheetEntryUpdate(BaseModel):
    entry_date: OptionalDate = None
    person_name: str | None = None

    workstream_id: uuid.UUID | None = None
    deliverable_id: uuid.UUID | None = None
    task_id: uuid.UUID | None = None
    subtask_id: uuid.UUID | None = None

    activity_type: str | None = None
    accomplishments: str | None = None
    blockers: str | None = None
    next_steps: str | None = None

    effort_hours: float | None = None
    status: str | None = None
    submitted: bool | None = None


class TimesheetEntryRead(BaseModel):
    id: uuid.UUID

    entry_date: date
    person_name: str

    workstream_id: uuid.UUID | None
    deliverable_id: uuid.UUID | None
    task_id: uuid.UUID | None
    subtask_id: uuid.UUID | None

    activity_type: str
    accomplishments: str
    blockers: str | None
    next_steps: str | None

    effort_hours: float
    status: str

    submitted: bool
    submitted_at: datetime | None
    submitted_by: str | None

    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TimesheetWeekSubmitRequest(BaseModel):
    start_date: date
    end_date: date
    person_name: str = "Giridhar Krishnagiri"
    submitted_by: str = "Giridhar Krishnagiri"


class TimesheetWeekSubmitResponse(BaseModel):
    submitted_count: int
    start_date: date
    end_date: date
    person_name: str


class TimesheetSummaryGenerateRequest(BaseModel):
    start_date: date
    end_date: date
    person_name: str = "Giridhar Krishnagiri"
    summary_type: str = "Custom Date Range"
    created_by: str = "Giridhar Krishnagiri"


class TimesheetSummaryRead(BaseModel):
    id: uuid.UUID

    person_name: str
    summary_type: str
    start_date: date
    end_date: date

    total_effort_hours: float
    entry_count: int

    summary_text: str
    accomplishments_summary: str | None
    blockers_summary: str | None
    next_steps_summary: str | None

    source_context: str | None
    llm_raw_output: str | None
    model_name: str | None
    trace_workflow_name: str | None

    created_by: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)