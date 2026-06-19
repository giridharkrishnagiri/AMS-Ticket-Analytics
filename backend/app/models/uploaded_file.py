from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import BigInteger, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin, UuidPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.ingestion_job import IngestionJob
    from app.models.ticket import Ticket
    from app.models.ticket_raw_row import TicketRawRow
    from app.models.upload_batch import UploadBatch


class UploadedFile(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "uploaded_files"

    upload_batch_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("upload_batches.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    project_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    ticket_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    saved_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    storage_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    source_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    checksum_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="stored", index=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    upload_batch: Mapped[UploadBatch] = relationship(back_populates="uploaded_files")
    raw_rows: Mapped[list[TicketRawRow]] = relationship(
        back_populates="uploaded_file",
        cascade="all, delete-orphan",
    )
    ingestion_jobs: Mapped[list[IngestionJob]] = relationship(back_populates="uploaded_file")
    tickets: Mapped[list[Ticket]] = relationship(back_populates="uploaded_file")
