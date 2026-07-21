"""add genai ticket clustering tables

Revision ID: 20260721_0049
Revises: 20260721_0048
Create Date: 2026-07-21 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260721_0049"
down_revision: str | None = "20260721_0048"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def index_exists(index_name: str, table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return any(index["name"] == index_name for index in inspector.get_indexes(table_name))


def upgrade() -> None:
    if not table_exists("genai_ticket_embeddings"):
        op.create_table(
            "genai_ticket_embeddings",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("ticket_number", sa.String(length=255), nullable=False),
            sa.Column("ticket_type", sa.String(length=40), nullable=False),
            sa.Column("input_hash", sa.String(length=64), nullable=False),
            sa.Column("embedding_model", sa.String(length=255), nullable=False),
            sa.Column("normalized_text_hash", sa.String(length=64), nullable=False),
            sa.Column("text_preview", sa.Text(), nullable=True),
            sa.Column("embedding_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
            sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(["customer_id"], ["clients.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "project_id",
                "ticket_number",
                "input_hash",
                "embedding_model",
                name="uq_genai_ticket_embeddings_project_ticket_hash_model",
            ),
        )
    for index_name, columns in (
        ("ix_genai_ticket_embeddings_customer_id", ["customer_id"]),
        ("ix_genai_ticket_embeddings_project_id", ["project_id"]),
        ("ix_genai_ticket_embeddings_ticket_number", ["ticket_number"]),
        ("ix_genai_ticket_embeddings_ticket_type", ["ticket_type"]),
        ("ix_genai_ticket_embeddings_input_hash", ["input_hash"]),
        ("ix_genai_ticket_embeddings_embedding_model", ["embedding_model"]),
        ("ix_genai_ticket_embeddings_normalized_text_hash", ["normalized_text_hash"]),
        ("ix_genai_ticket_embeddings_project_ticket", ["project_id", "ticket_number"]),
        ("ix_genai_ticket_embeddings_model_hash", ["embedding_model", "input_hash"]),
    ):
        if not index_exists(index_name, "genai_ticket_embeddings"):
            op.create_index(index_name, "genai_ticket_embeddings", columns)

    if not table_exists("genai_ticket_cluster_labels"):
        op.create_table(
            "genai_ticket_cluster_labels",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("analysis_month", sa.String(length=7), nullable=False),
            sa.Column("run_id", sa.String(length=80), nullable=False),
            sa.Column("cluster_level", sa.Integer(), nullable=False),
            sa.Column("cluster_key", sa.String(length=80), nullable=False),
            sa.Column("parent_cluster_key", sa.String(length=80), nullable=True),
            sa.Column("label", sa.String(length=255), nullable=False),
            sa.Column("summary", sa.Text(), nullable=True),
            sa.Column("confidence", sa.Float(), nullable=True),
            sa.Column("ticket_count", sa.Integer(), nullable=False),
            sa.Column("incident_count", sa.Integer(), nullable=False),
            sa.Column("sc_task_count", sa.Integer(), nullable=False),
            sa.Column(
                "representative_tickets_json",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=True,
            ),
            sa.Column("child_clusters_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(["customer_id"], ["clients.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "project_id",
                "analysis_month",
                "run_id",
                "cluster_level",
                "cluster_key",
                name="uq_genai_ticket_cluster_labels_run_level_key",
            ),
        )
    for index_name, columns in (
        ("ix_genai_ticket_cluster_labels_customer_id", ["customer_id"]),
        ("ix_genai_ticket_cluster_labels_project_id", ["project_id"]),
        ("ix_genai_ticket_cluster_labels_analysis_month", ["analysis_month"]),
        ("ix_genai_ticket_cluster_labels_run_id", ["run_id"]),
        ("ix_genai_ticket_cluster_labels_cluster_level", ["cluster_level"]),
        ("ix_genai_ticket_cluster_labels_cluster_key", ["cluster_key"]),
        ("ix_genai_ticket_cluster_labels_parent_cluster_key", ["parent_cluster_key"]),
        (
            "ix_genai_ticket_cluster_labels_project_month_run",
            ["project_id", "analysis_month", "run_id"],
        ),
        (
            "ix_genai_ticket_cluster_labels_level",
            ["project_id", "analysis_month", "cluster_level"],
        ),
    ):
        if not index_exists(index_name, "genai_ticket_cluster_labels"):
            op.create_index(index_name, "genai_ticket_cluster_labels", columns)


def downgrade() -> None:
    if table_exists("genai_ticket_cluster_labels"):
        op.drop_table("genai_ticket_cluster_labels")
    if table_exists("genai_ticket_embeddings"):
        op.drop_table("genai_ticket_embeddings")
