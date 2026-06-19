from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import BigInteger, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin, UuidPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.ticket import Ticket
    from app.models.upload_batch import UploadBatch
    from app.models.uploaded_file import UploadedFile


class TicketRawRow(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "ticket_raw_rows"
    __table_args__ = (
        UniqueConstraint("uploaded_file_id", "row_number", name="uq_ticket_raw_rows_file_row"),
    )

    project_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    upload_batch_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("upload_batches.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    uploaded_file_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("uploaded_files.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    ticket_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    row_number: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    raw_ticket_number: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    raw_data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    row_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    upload_batch: Mapped[UploadBatch] = relationship(back_populates="raw_rows")
    uploaded_file: Mapped[UploadedFile] = relationship(back_populates="raw_rows")
    ticket: Mapped[Ticket | None] = relationship(back_populates="raw_row")
