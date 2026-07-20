import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Finding(Base):
    __tablename__ = "findings"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    subtask_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("subtasks.id", ondelete="CASCADE"))
    task_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True)
    deliverable_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("deliverables.id", ondelete="SET NULL"), nullable=True)

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    finding_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    severity: Mapped[str | None] = mapped_column(String(50), nullable=True)

    finding_text: Mapped[str] = mapped_column(Text, nullable=False)
    business_impact: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommendation: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[str] = mapped_column(String(100), default="Draft")
    confidence_level: Mapped[str | None] = mapped_column(String(50), nullable=True)

    is_validated: Mapped[bool] = mapped_column(Boolean, default=False)
    validated_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    validated_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    evidence_items: Mapped[list["EvidenceItem"]] = relationship(
        back_populates="finding",
        cascade="all, delete-orphan",
        foreign_keys="EvidenceItem.finding_id",
    )


class AnalysisOutput(Base):
    __tablename__ = "analysis_outputs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    subtask_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("subtasks.id", ondelete="CASCADE"))
    task_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True)
    deliverable_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("deliverables.id", ondelete="SET NULL"), nullable=True)

    analysis_title: Mapped[str] = mapped_column(String(255), nullable=False)
    analysis_type: Mapped[str | None] = mapped_column(String(100), nullable=True)

    analysis_text: Mapped[str] = mapped_column(Text, nullable=False)
    methodology: Mapped[str | None] = mapped_column(Text, nullable=True)
    assumptions: Mapped[str | None] = mapped_column(Text, nullable=True)
    limitations: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[str] = mapped_column(String(100), default="Draft")
    confidence_level: Mapped[str | None] = mapped_column(String(50), nullable=True)

    reviewed_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reviewed_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    evidence_items: Mapped[list["EvidenceItem"]] = relationship(
        back_populates="analysis_output",
        cascade="all, delete-orphan",
        foreign_keys="EvidenceItem.analysis_output_id",
    )


class EvidenceItem(Base):
    __tablename__ = "evidence_items"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    subtask_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("subtasks.id", ondelete="SET NULL"), nullable=True)
    finding_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("findings.id", ondelete="CASCADE"), nullable=True)
    analysis_output_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("analysis_outputs.id", ondelete="CASCADE"), nullable=True)
    data_point_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("data_points.id", ondelete="SET NULL"), nullable=True)
    stakeholder_question_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("stakeholder_questions.id", ondelete="SET NULL"), nullable=True)

    evidence_type: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    source_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_reference: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    confidence_level: Mapped[str | None] = mapped_column(String(50), nullable=True)
    is_primary_evidence: Mapped[bool] = mapped_column(Boolean, default=False)

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    finding: Mapped[Finding | None] = relationship(
        back_populates="evidence_items",
        foreign_keys=[finding_id],
    )
    analysis_output: Mapped[AnalysisOutput | None] = relationship(
        back_populates="evidence_items",
        foreign_keys=[analysis_output_id],
    )