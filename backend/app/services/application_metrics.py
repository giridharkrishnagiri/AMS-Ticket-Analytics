from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.models import ApplicationInventoryItem, Project
from app.services.dashboard import latest_complete_month_window


@dataclass(frozen=True)
class ApplicationTicketUserMetricsSummary:
    project_id: UUID
    inventory_count: int
    active_users_count: int
    metrics_updated_count: int
    window_start: datetime
    window_end: datetime


def recompute_application_ticket_user_metrics(
    db: Session,
    project_id: UUID,
) -> ApplicationTicketUserMetricsSummary:
    project = db.get(Project, project_id)
    if project is None:
        raise FileNotFoundError(f"Project {project_id} was not found.")

    window_start, window_end = latest_complete_month_window(db, project_id, 6)
    db.execute(
        text(
            """
            UPDATE application_inventory_items
            SET
                avg_monthly_ticket_volume_6m = 0,
                tickets_per_user_per_month =
                    CASE
                        WHEN active_users IS NOT NULL AND active_users > 0 THEN 0
                        ELSE NULL
                    END
            WHERE project_id = CAST(:project_id AS uuid)
            """,
        ),
        {"project_id": str(project_id)},
    )
    result = db.execute(
        text(
            """
            WITH ticket_counts AS (
                SELECT
                    application_inventory_id,
                    count(*)::double precision / 6.0 AS avg_monthly_volume
                FROM tickets
                WHERE project_id = CAST(:project_id AS uuid)
                  AND application_inventory_id IS NOT NULL
                  AND created_at IS NOT NULL
                  AND created_at >= :window_start
                  AND created_at <= :window_end
                GROUP BY application_inventory_id
            )
            UPDATE application_inventory_items AS inventory
            SET
                avg_monthly_ticket_volume_6m = ticket_counts.avg_monthly_volume,
                tickets_per_user_per_month =
                    CASE
                        WHEN inventory.active_users IS NOT NULL
                         AND inventory.active_users > 0
                        THEN ticket_counts.avg_monthly_volume / inventory.active_users
                        ELSE NULL
                    END
            FROM ticket_counts
            WHERE inventory.id = ticket_counts.application_inventory_id
              AND inventory.project_id = CAST(:project_id AS uuid)
            """,
        ),
        {
            "project_id": str(project_id),
            "window_start": window_start,
            "window_end": window_end,
        },
    )
    db.flush()
    inventory_count = int(
        db.scalar(
            select(func.count(ApplicationInventoryItem.id)).where(
                ApplicationInventoryItem.project_id == project_id,
                ApplicationInventoryItem.active.is_(True),
            )
        )
        or 0
    )
    active_users_count = int(
        db.scalar(
            select(func.count(ApplicationInventoryItem.id)).where(
                ApplicationInventoryItem.project_id == project_id,
                ApplicationInventoryItem.active.is_(True),
                ApplicationInventoryItem.active_users.is_not(None),
                ApplicationInventoryItem.active_users > 0,
            )
        )
        or 0
    )
    return ApplicationTicketUserMetricsSummary(
        project_id=project_id,
        inventory_count=inventory_count,
        active_users_count=active_users_count,
        metrics_updated_count=int(result.rowcount or 0),
        window_start=window_start,
        window_end=window_end,
    )
