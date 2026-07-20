import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class UiWorkspaceDataCollection(Base):
    __tablename__ = "ui_workspace_data_collections"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    scope_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    scope_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)

    topic: Mapped[str] = mapped_column(String(500), nullable=False)
    source: Mapped[str | None] = mapped_column(String(300), nullable=True)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[str] = mapped_column(String(100), nullable=False, default="Requested")
    expected_received_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    actual_received_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    data_quality: Mapped[str | None] = mapped_column(String(100), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_by: Mapped[str | None] = mapped_column(String(250), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(250), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class UiWorkspaceQuestion(Base):
    __tablename__ = "ui_workspace_questions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    scope_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    scope_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)

    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    question_category: Mapped[str | None] = mapped_column(String(150), nullable=True)

    stakeholder_name: Mapped[str | None] = mapped_column(String(250), nullable=True)
    stakeholder_role: Mapped[str | None] = mapped_column(String(250), nullable=True)
    stakeholder_email: Mapped[str | None] = mapped_column(String(320), nullable=True)

    response_status: Mapped[str] = mapped_column(String(100), nullable=False, default="Pending")
    expected_response_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    actual_response_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    response_details: Mapped[str | None] = mapped_column(Text, nullable=True)

    follow_up_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    follow_up_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_by: Mapped[str | None] = mapped_column(String(250), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(250), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class UiWorkspaceFinding(Base):
    __tablename__ = "ui_workspace_findings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    scope_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    scope_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)

    title: Mapped[str] = mapped_column(String(500), nullable=False)
    finding_type: Mapped[str | None] = mapped_column(String(150), nullable=True)
    severity: Mapped[str | None] = mapped_column(String(100), nullable=True)

    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    refined_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    finding_text: Mapped[str] = mapped_column(Text, nullable=False)

    business_impact: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommendation: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[str] = mapped_column(String(100), nullable=False, default="Draft")
    confidence_level: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_validated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_by: Mapped[str | None] = mapped_column(String(250), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(250), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class UiWorkspaceAnalysis(Base):
    __tablename__ = "ui_workspace_analysis"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    scope_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    scope_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)

    analysis_title: Mapped[str] = mapped_column(String(500), nullable=False)
    analysis_type: Mapped[str | None] = mapped_column(String(150), nullable=True)

    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    refined_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    analysis_text: Mapped[str] = mapped_column(Text, nullable=False)

    methodology: Mapped[str | None] = mapped_column(Text, nullable=True)
    assumptions: Mapped[str | None] = mapped_column(Text, nullable=True)
    limitations: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[str] = mapped_column(String(100), nullable=False, default="Draft")
    confidence_level: Mapped[str | None] = mapped_column(String(100), nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(String(250), nullable=True)
    reviewed_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    created_by: Mapped[str | None] = mapped_column(String(250), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(250), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class UiWorkspaceEvidence(Base):
    __tablename__ = "ui_workspace_evidence"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    scope_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    scope_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)

    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_type: Mapped[str] = mapped_column(String(150), nullable=False, default="Document")
    source_name: Mapped[str | None] = mapped_column(String(300), nullable=True)
    source_reference: Mapped[str | None] = mapped_column(String(500), nullable=True)
    evidence_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    confidence_level: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_primary_evidence: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_by: Mapped[str | None] = mapped_column(String(250), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(250), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class UiWorkspaceFile(Base):
    __tablename__ = "ui_workspace_files"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    scope_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    scope_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)

    linked_entity_type: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    linked_entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)

    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    stored_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(250), nullable=True)
    file_size_bytes: Mapped[int | None] = mapped_column(nullable=True)

    upload_category: Mapped[str] = mapped_column(String(150), nullable=False, default="General")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    uploaded_by: Mapped[str | None] = mapped_column(String(250), nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class UiWorkspaceRecommendation(Base):
    __tablename__ = "ui_workspace_recommendations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    scope_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    scope_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)

    recommendation_type: Mapped[str] = mapped_column(String(150), nullable=False, default="Workspace Advisory")
    focus_area: Mapped[str | None] = mapped_column(String(500), nullable=True)

    title: Mapped[str] = mapped_column(String(500), nullable=False)
    ai_analysis: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommendation_text: Mapped[str] = mapped_column(Text, nullable=False)

    additional_data_to_collect: Mapped[str | None] = mapped_column(Text, nullable=True)
    additional_questions_to_ask: Mapped[str | None] = mapped_column(Text, nullable=True)
    risks: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_steps: Mapped[str | None] = mapped_column(Text, nullable=True)
    suggested_evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    automation_opportunities: Mapped[str | None] = mapped_column(Text, nullable=True)

    source_context_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[str] = mapped_column(String(100), nullable=False, default="Draft")
    confidence_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)

    created_by: Mapped[str | None] = mapped_column(String(250), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)