import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class UploadedFile(Base):
    __tablename__ = "uploaded_files"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    stored_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)

    content_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    upload_category: Mapped[str | None] = mapped_column(String(100), nullable=True)

    subtask_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("subtasks.id", ondelete="SET NULL"), nullable=True)
    data_point_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("data_points.id", ondelete="SET NULL"), nullable=True)
    stakeholder_question_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("stakeholder_questions.id", ondelete="SET NULL"),
        nullable=True,
    )
    finding_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("findings.id", ondelete="SET NULL"), nullable=True)
    analysis_output_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("analysis_outputs.id", ondelete="SET NULL"),
        nullable=True,
    )
    evidence_item_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("evidence_items.id", ondelete="SET NULL"),
        nullable=True,
    )

    uploaded_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())