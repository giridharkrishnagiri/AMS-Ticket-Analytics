from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from uuid import UUID

from sqlalchemy import delete, func, inspect, select, text
from sqlalchemy.orm import Session

from app.models import DashboardFilterFact, Project, Ticket

GENERIC_TICKET_TYPES = ("INCIDENT", "SERVICE_CATALOG_TASK")


@dataclass(frozen=True)
class DashboardFilterFactsRefreshResult:
    project_id: UUID
    rows_deleted: int
    rows_inserted: int
    in_scope_rows: int
    out_of_scope_rows: int
    duration_ms: int


def clear_dashboard_filter_facts(db: Session, project_id: UUID) -> int:
    result = db.execute(
        delete(DashboardFilterFact).where(
            DashboardFilterFact.project_id == project_id,
            DashboardFilterFact.dashboard_area == "volumetrics",
        )
    )
    return int(result.rowcount or 0)


def project_has_generic_ticket_rows(db: Session, project_id: UUID) -> bool:
    return bool(
        db.scalar(
            select(Ticket.id)
            .where(
                Ticket.project_id == project_id,
                Ticket.ticket_type.in_(GENERIC_TICKET_TYPES),
            )
            .limit(1),
        ),
    )


def dashboard_filter_fact_count(db: Session, project_id: UUID) -> int:
    return int(
        db.scalar(
            select(func.count(DashboardFilterFact.id)).where(
                DashboardFilterFact.project_id == project_id,
                DashboardFilterFact.dashboard_area == "volumetrics",
            ),
        )
        or 0,
    )


def dashboard_filter_fact_service_field_fragments(db: Session) -> tuple[str, str]:
    inspector = inspect(db.get_bind())
    if "dashboard_filter_facts" not in inspector.get_table_names():
        return "", ""
    columns = {column["name"] for column in inspector.get_columns("dashboard_filter_facts")}
    if not {"service_entitlement", "service_type"}.issubset(columns):
        return "", ""
    return (
        """
                service_entitlement,
                service_type,
""",
        """
                left(NULLIF(btrim(t.service_entitlement), ''), 255),
                left(NULLIF(btrim(t.service_type), ''), 255),
""",
    )


def normalized_text_key_sql(expression: str) -> str:
    return (
        "lower(regexp_replace("
        f"btrim(replace({expression}, chr(160), ' ')), "
        "'[[:space:]]+', ' ', 'g'"
        "))"
    )


def ensure_dashboard_filter_facts(
    db: Session,
    project_id: UUID,
) -> DashboardFilterFactsRefreshResult | None:
    if dashboard_filter_fact_count(db, project_id) > 0:
        return None
    if not project_has_generic_ticket_rows(db, project_id):
        return None
    return refresh_dashboard_filter_facts(db, project_id)


def refresh_dashboard_filter_facts_for_batches(
    db: Session,
    project_id: UUID,
    batch_ids: list[UUID] | None = None,
) -> DashboardFilterFactsRefreshResult:
    # Uploads are infrequent and fact rows are intentionally narrow, so the first implementation
    # uses a full project refresh even when the caller supplies affected batch IDs.
    _ = batch_ids
    return refresh_dashboard_filter_facts(db, project_id)


def refresh_dashboard_filter_facts(
    db: Session,
    project_id: UUID,
    *,
    data_version: str | None = None,
) -> DashboardFilterFactsRefreshResult:
    if db.get(Project, project_id) is None:
        raise FileNotFoundError(f"Project {project_id} was not found.")

    started = perf_counter()
    rows_deleted = clear_dashboard_filter_facts(db, project_id)
    in_scope_rows = insert_in_scope_filter_facts(db, project_id, data_version)
    out_of_scope_rows = insert_out_of_scope_filter_facts(db, project_id, data_version)
    duration_ms = int((perf_counter() - started) * 1000)
    return DashboardFilterFactsRefreshResult(
        project_id=project_id,
        rows_deleted=rows_deleted,
        rows_inserted=in_scope_rows + out_of_scope_rows,
        in_scope_rows=in_scope_rows,
        out_of_scope_rows=out_of_scope_rows,
        duration_ms=duration_ms,
    )


def insert_in_scope_filter_facts(
    db: Session,
    project_id: UUID,
    data_version: str | None,
) -> int:
    service_columns, service_selects = dashboard_filter_fact_service_field_fragments(db)
    ticket_assignment_group_key = normalized_text_key_sql("t.assignment_group")
    scope_assignment_group_key = normalized_text_key_sql("s.assignment_group_key")
    scoped_functional_track = (
        "COALESCE(s.functional_track, left(NULLIF(btrim(t.functional_track), ''), 255))"
    )
    scoped_assignment_group = (
        "COALESCE(s.assignment_group, left(NULLIF(btrim(t.assignment_group), ''), 255))"
    )
    result = db.execute(
        text(
            f"""
            WITH scope_rows AS (
                SELECT DISTINCT ON ({scope_assignment_group_key})
                    {scope_assignment_group_key} AS assignment_group_key,
                    left(NULLIF(btrim(s.assignment_group), ''), 255) AS assignment_group,
                    left(NULLIF(btrim(s.functional_track), ''), 255) AS functional_track,
                    s.is_in_scope
                FROM in_scope_assignment_groups AS s
                WHERE s.project_id = CAST(:project_id AS uuid)
                  AND s.is_active IS true
                  AND NULLIF({scope_assignment_group_key}, '') IS NOT NULL
                  AND NULLIF(btrim(s.assignment_group), '') IS NOT NULL
                ORDER BY {scope_assignment_group_key}, s.is_in_scope DESC, s.assignment_group
            ),
            scope_presence AS (
                SELECT EXISTS(SELECT 1 FROM scope_rows) AS has_scope_rows
            )
            INSERT INTO dashboard_filter_facts (
                id,
                customer_id,
                project_id,
                dashboard_area,
                record_domain,
                record_source,
                record_type,
                scope,
                record_id,
                record_number,
                created_at_source,
                completed_at_source,
                created_month,
                completed_month,
                functional_track,
                ams_owner,
                functional_track_ams_owner,
                assignment_group,
                support_group_owner,
                assignment_group_support_owner,
                parent_business_application,
                business_service_ci_name,
                application_owner,
                supported_by_vendor,
                sap_non_sap,
                architecture_type,
                application_type,
                business_critical,
                install_status,
                install_type,
                hosting_env,
{service_columns}                priority,
                state,
                status_group,
                data_version
            )
            SELECT
                md5('tickets:' || t.id::text)::uuid,
                p.client_id,
                t.project_id,
                'volumetrics',
                'ticket',
                'tickets',
                CASE
                    WHEN t.ticket_type = 'INCIDENT' THEN 'incident'
                    WHEN t.ticket_type = 'SERVICE_CATALOG_TASK' THEN 'sc_task'
                    ELSE lower(t.ticket_type)
                END,
                'in_scope',
                t.id,
                t.ticket_number,
                t.created_at,
                CASE
                    WHEN lower(btrim(COALESCE(t.state, ''))) LIKE '%cancel%' THEN NULL
                    WHEN t.ticket_type = 'SERVICE_CATALOG_TASK'
                         AND lower(btrim(COALESCE(t.state, ''))) = 'closed incomplete' THEN NULL
                    WHEN t.ticket_type = 'INCIDENT' THEN t.resolved_at
                    WHEN t.ticket_type = 'SERVICE_CATALOG_TASK' THEN t.closed_at
                    ELSE COALESCE(t.resolved_at, t.closed_at)
                END,
                CAST(date_trunc('month', timezone('UTC', t.created_at)) AS date),
                CAST(date_trunc(
                    'month',
                    timezone('UTC', CASE
                        WHEN lower(btrim(COALESCE(t.state, ''))) LIKE '%cancel%' THEN NULL
                        WHEN t.ticket_type = 'SERVICE_CATALOG_TASK'
                             AND lower(btrim(COALESCE(t.state, ''))) = 'closed incomplete' THEN NULL
                        WHEN t.ticket_type = 'INCIDENT' THEN t.resolved_at
                        WHEN t.ticket_type = 'SERVICE_CATALOG_TASK' THEN t.closed_at
                        ELSE COALESCE(t.resolved_at, t.closed_at)
                    END)
                ) AS date),
                {scoped_functional_track},
                left(NULLIF(btrim(t.ams_owner), ''), 255),
                {scoped_functional_track},
                {scoped_assignment_group},
                left(NULLIF(btrim(t.support_lead), ''), 255),
                {scoped_assignment_group},
                left(NULLIF(btrim(t.parent_application_name), ''), 255),
                left(NULLIF(btrim(t.business_service_ci_name), ''), 255),
                left(NULLIF(btrim(t.application_owner), ''), 255),
                left(
                    COALESCE(
                        NULLIF(btrim(t.supported_by_vendor), ''),
                        NULLIF(btrim(t.derived_vendor), '')
                    ),
                    255
                ),
                left(NULLIF(btrim(t.sap_non_sap), ''), 50),
                left(NULLIF(btrim(t.architecture_type), ''), 255),
                NULL,
                left(NULLIF(btrim(t.business_critical), ''), 255),
                NULL,
                left(NULLIF(btrim(t.install_type), ''), 255),
                left(NULLIF(btrim(t.hosting_env), ''), 255),
{service_selects}                left(NULLIF(btrim(t.priority), ''), 50),
                left(NULLIF(btrim(t.state), ''), 100),
                left(
                    CASE
                        WHEN lower(btrim(COALESCE(t.state, ''))) LIKE '%cancel%' THEN 'cancelled'
                        WHEN t.ticket_type = 'SERVICE_CATALOG_TASK'
                             AND lower(btrim(COALESCE(t.state, ''))) = 'closed incomplete'
                            THEN 'cancelled'
                        WHEN lower(btrim(COALESCE(t.state, ''))) LIKE '%closed%' THEN 'closed'
                        WHEN lower(btrim(COALESCE(t.state, ''))) LIKE '%resolved%' THEN 'closed'
                        WHEN NULLIF(btrim(t.state), '') IS NULL THEN '(blank)'
                        ELSE btrim(t.state)
                    END,
                    100
                ),
                :data_version
            FROM tickets AS t
            JOIN projects AS p ON p.id = t.project_id
            CROSS JOIN scope_presence
            LEFT JOIN scope_rows AS s
              ON {ticket_assignment_group_key} = s.assignment_group_key
            WHERE t.project_id = CAST(:project_id AS uuid)
              AND t.ticket_type IN ('INCIDENT', 'SERVICE_CATALOG_TASK')
              AND t.is_in_scope IS true
              AND (
                  scope_presence.has_scope_rows IS false
                  OR (s.assignment_group_key IS NOT NULL AND s.is_in_scope IS true)
              )
            """
        ),
        {"project_id": str(project_id), "data_version": data_version},
    )
    return int(result.rowcount or 0)


def insert_out_of_scope_filter_facts(
    db: Session,
    project_id: UUID,
    data_version: str | None,
) -> int:
    service_columns, service_selects = dashboard_filter_fact_service_field_fragments(db)
    ticket_assignment_group_key = normalized_text_key_sql("t.assignment_group")
    scope_assignment_group_key = normalized_text_key_sql("s.assignment_group_key")
    scoped_functional_track = (
        "COALESCE(s.functional_track, left(NULLIF(btrim(t.functional_track), ''), 255))"
    )
    scoped_assignment_group = (
        "COALESCE(s.assignment_group, left(NULLIF(btrim(t.assignment_group), ''), 255))"
    )
    result = db.execute(
        text(
            f"""
            WITH scope_rows AS (
                SELECT DISTINCT ON ({scope_assignment_group_key})
                    {scope_assignment_group_key} AS assignment_group_key,
                    left(NULLIF(btrim(s.assignment_group), ''), 255) AS assignment_group,
                    left(NULLIF(btrim(s.functional_track), ''), 255) AS functional_track,
                    s.is_in_scope
                FROM in_scope_assignment_groups AS s
                WHERE s.project_id = CAST(:project_id AS uuid)
                  AND s.is_active IS true
                  AND NULLIF({scope_assignment_group_key}, '') IS NOT NULL
                  AND NULLIF(btrim(s.assignment_group), '') IS NOT NULL
                ORDER BY {scope_assignment_group_key}, s.is_in_scope DESC, s.assignment_group
            ),
            scope_presence AS (
                SELECT EXISTS(SELECT 1 FROM scope_rows) AS has_scope_rows
            )
            INSERT INTO dashboard_filter_facts (
                id,
                customer_id,
                project_id,
                dashboard_area,
                record_domain,
                record_source,
                record_type,
                scope,
                record_id,
                record_number,
                created_at_source,
                completed_at_source,
                created_month,
                completed_month,
                functional_track,
                ams_owner,
                functional_track_ams_owner,
                assignment_group,
                support_group_owner,
                assignment_group_support_owner,
                parent_business_application,
                business_service_ci_name,
                application_owner,
                supported_by_vendor,
                sap_non_sap,
                architecture_type,
                application_type,
                business_critical,
                install_status,
                install_type,
                hosting_env,
{service_columns}                priority,
                state,
                status_group,
                data_version
            )
            SELECT
                md5('tickets:out_of_scope:' || t.id::text)::uuid,
                p.client_id,
                t.project_id,
                'volumetrics',
                'ticket',
                'tickets',
                CASE
                    WHEN t.ticket_type = 'INCIDENT' THEN 'incident'
                    WHEN t.ticket_type = 'SERVICE_CATALOG_TASK' THEN 'sc_task'
                    ELSE lower(t.ticket_type)
                END,
                'out_of_scope',
                t.id,
                t.ticket_number,
                t.created_at,
                CASE
                    WHEN lower(btrim(COALESCE(t.state, ''))) LIKE '%cancel%' THEN NULL
                    WHEN t.ticket_type = 'SERVICE_CATALOG_TASK'
                         AND lower(btrim(COALESCE(t.state, ''))) = 'closed incomplete' THEN NULL
                    WHEN t.ticket_type = 'INCIDENT' THEN t.resolved_at
                    WHEN t.ticket_type = 'SERVICE_CATALOG_TASK' THEN t.closed_at
                    ELSE COALESCE(t.resolved_at, t.closed_at)
                END,
                CAST(date_trunc('month', timezone('UTC', t.created_at)) AS date),
                CAST(date_trunc(
                    'month',
                    timezone('UTC', CASE
                        WHEN lower(btrim(COALESCE(t.state, ''))) LIKE '%cancel%' THEN NULL
                        WHEN t.ticket_type = 'SERVICE_CATALOG_TASK'
                             AND lower(btrim(COALESCE(t.state, ''))) = 'closed incomplete' THEN NULL
                        WHEN t.ticket_type = 'INCIDENT' THEN t.resolved_at
                        WHEN t.ticket_type = 'SERVICE_CATALOG_TASK' THEN t.closed_at
                        ELSE COALESCE(t.resolved_at, t.closed_at)
                    END)
                ) AS date),
                {scoped_functional_track},
                left(NULLIF(btrim(t.ams_owner), ''), 255),
                {scoped_functional_track},
                {scoped_assignment_group},
                left(NULLIF(btrim(t.support_lead), ''), 255),
                {scoped_assignment_group},
                left(NULLIF(btrim(t.parent_application_name), ''), 255),
                left(NULLIF(btrim(t.business_service_ci_name), ''), 255),
                left(NULLIF(btrim(t.application_owner), ''), 255),
                left(
                    COALESCE(
                        NULLIF(btrim(t.supported_by_vendor), ''),
                        NULLIF(btrim(t.derived_vendor), '')
                    ),
                    255
                ),
                left(NULLIF(btrim(t.sap_non_sap), ''), 50),
                left(NULLIF(btrim(t.architecture_type), ''), 255),
                NULL,
                left(NULLIF(btrim(t.business_critical), ''), 255),
                NULL,
                left(NULLIF(btrim(t.install_type), ''), 255),
                left(NULLIF(btrim(t.hosting_env), ''), 255),
{service_selects}                left(NULLIF(btrim(t.priority), ''), 50),
                left(NULLIF(btrim(t.state), ''), 100),
                left(
                    CASE
                        WHEN lower(btrim(COALESCE(t.state, ''))) LIKE '%cancel%' THEN 'cancelled'
                        WHEN t.ticket_type = 'SERVICE_CATALOG_TASK'
                             AND lower(btrim(COALESCE(t.state, ''))) = 'closed incomplete'
                            THEN 'cancelled'
                        WHEN lower(btrim(COALESCE(t.state, ''))) LIKE '%closed%' THEN 'closed'
                        WHEN lower(btrim(COALESCE(t.state, ''))) LIKE '%resolved%' THEN 'closed'
                        WHEN NULLIF(btrim(t.state), '') IS NULL THEN '(blank)'
                        ELSE btrim(t.state)
                    END,
                    100
                ),
                :data_version
            FROM tickets AS t
            JOIN projects AS p ON p.id = t.project_id
            CROSS JOIN scope_presence
            LEFT JOIN scope_rows AS s
              ON {ticket_assignment_group_key} = s.assignment_group_key
            WHERE t.project_id = CAST(:project_id AS uuid)
              AND t.ticket_type IN ('INCIDENT', 'SERVICE_CATALOG_TASK')
              AND t.is_in_scope IS false
              AND (
                  scope_presence.has_scope_rows IS false
                  OR s.assignment_group_key IS NOT NULL
              )
            """
        ),
        {"project_id": str(project_id), "data_version": data_version},
    )
    return int(result.rowcount or 0)
