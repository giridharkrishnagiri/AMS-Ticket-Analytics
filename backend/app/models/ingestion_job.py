from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin, UuidPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.upload_batch import UploadBatch
    from app.models.uploaded_file import UploadedFile


class IngestionJob(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "ingestion_jobs"

    upload_batch_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("upload_batches.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    uploaded_file_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("uploaded_files.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    job_type: Mapped[str] = mapped_column(String(80), nullable=False, default="file_ingestion")
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="pending", index=True)
    rows_total: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    rows_processed: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    upload_batch: Mapped[UploadBatch] = relationship(back_populates="ingestion_jobs")
    uploaded_file: Mapped[UploadedFile | None] = relationship(back_populates="ingestion_jobs")

    @property
    def processed_row_count(self) -> int:
        return self.rows_processed
