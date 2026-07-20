import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class UploadedFileRead(BaseModel):
    id: uuid.UUID

    original_filename: str
    stored_filename: str
    storage_path: str

    content_type: str | None
    file_size_bytes: int

    description: str | None
    upload_category: str | None

    subtask_id: uuid.UUID | None
    data_point_id: uuid.UUID | None
    stakeholder_question_id: uuid.UUID | None
    finding_id: uuid.UUID | None
    analysis_output_id: uuid.UUID | None
    evidence_item_id: uuid.UUID | None

    uploaded_by: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)