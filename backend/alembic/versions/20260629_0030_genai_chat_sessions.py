"""genai chat sessions

Revision ID: 20260629_0030
Revises: 20260628_0029
Create Date: 2026-06-29 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260629_0030"
down_revision: str | None = "20260628_0029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "genai_chat_sessions",
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False, server_default="New chat"),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["customer_id"], ["clients.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_genai_chat_sessions_customer_id", "genai_chat_sessions", ["customer_id"])
    op.create_index("ix_genai_chat_sessions_project_id", "genai_chat_sessions", ["project_id"])
    op.create_index(
        "ix_genai_chat_sessions_last_message_at",
        "genai_chat_sessions",
        ["last_message_at"],
    )
    op.create_index(
        "ix_genai_chat_sessions_archived_last_message",
        "genai_chat_sessions",
        ["is_archived", "last_message_at"],
    )

    op.create_table(
        "genai_chat_messages",
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["genai_chat_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_genai_chat_messages_session_id", "genai_chat_messages", ["session_id"])
    op.create_index(
        "ix_genai_chat_messages_session_created",
        "genai_chat_messages",
        ["session_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_genai_chat_messages_session_created", table_name="genai_chat_messages")
    op.drop_index("ix_genai_chat_messages_session_id", table_name="genai_chat_messages")
    op.drop_table("genai_chat_messages")
    op.drop_index(
        "ix_genai_chat_sessions_archived_last_message",
        table_name="genai_chat_sessions",
    )
    op.drop_index("ix_genai_chat_sessions_last_message_at", table_name="genai_chat_sessions")
    op.drop_index("ix_genai_chat_sessions_project_id", table_name="genai_chat_sessions")
    op.drop_index("ix_genai_chat_sessions_customer_id", table_name="genai_chat_sessions")
    op.drop_table("genai_chat_sessions")
