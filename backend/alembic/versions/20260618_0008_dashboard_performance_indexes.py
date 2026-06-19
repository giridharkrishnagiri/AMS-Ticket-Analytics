"""add dashboard performance indexes

Revision ID: 20260618_0008
Revises: 20260617_0007
Create Date: 2026-06-18 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260618_0008"
down_revision: str | None = "20260617_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


INDEXES: tuple[tuple[str, list[str]], ...] = (
    ("ix_tickets_project_type_created_at", ["project_id", "ticket_type", "created_at"]),
    ("ix_tickets_project_type_resolved_at", ["project_id", "ticket_type", "resolved_at"]),
    ("ix_tickets_project_type_closed_at", ["project_id", "ticket_type", "closed_at"]),
    ("ix_tickets_project_type_priority", ["project_id", "ticket_type", "priority"]),
    (
        "ix_tickets_project_type_assignment_group",
        ["project_id", "ticket_type", "assignment_group"],
    ),
    ("ix_tickets_project_type_application", ["project_id", "ticket_type", "application"]),
    ("ix_tickets_project_type_sla_breached", ["project_id", "ticket_type", "sla_breached"]),
    ("ix_tickets_project_type_reopen_count", ["project_id", "ticket_type", "reopen_count"]),
    (
        "ix_tickets_project_type_reassignment_count",
        ["project_id", "ticket_type", "reassignment_count"],
    ),
    (
        "ix_tickets_project_type_is_system_created",
        ["project_id", "ticket_type", "is_system_created"],
    ),
    (
        "ix_tickets_project_type_technical_functional_type",
        ["project_id", "ticket_type", "technical_functional_type"],
    ),
)


def upgrade() -> None:
    for name, columns in INDEXES:
        op.create_index(name, "tickets", columns)


def downgrade() -> None:
    for name, _ in reversed(INDEXES):
        op.drop_index(name, table_name="tickets")
