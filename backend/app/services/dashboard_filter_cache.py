from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from time import perf_counter
from typing import Any
from uuid import UUID

from sqlalchemy import delete, func, inspect, select, text
from sqlalchemy.orm import Session

from app.models import (
    DashboardFilterCacheStatus,
    DashboardFilterCatalog,
    DashboardFilterFact,
    Project,
)
from app.services.dashboard import (
    APPLICATION_CRITICALITY_ORDER,
    BLANK_LABEL,
    VOLUMETRICS_SCOPE_LABELS,
    VOLUMETRICS_TICKET_TYPE_LABELS,
    application_filter_sort_key,
    normalize_volumetrics_scope,
    normalize_volumetrics_ticket_type,
)
from app.services.dashboard_filter_facts import refresh_dashboard_filter_facts

DASHBOARD_FILTER_AREAS = ("applications", "volumetrics")
FILTER_CACHE_STATUSES = {"missing", "refreshing", "ready", "failed", "stale"}

APPLICATION_FILTER_KEYS = (
    "application_scope",
    "service_entitlement",
    "functional_track_ams_owner",
    "assignment_group_owner",
    "parent_application_name",
    "application_owner",
    "supported_by_vendor",
    "sap_non_sap",
    "architecture_type",
    "application_type",
    "business_critical",
    "install_status",
    "install_type",
    "hosting_env",
    "lifecycle_status_stage",
)

VOLUMETRICS_FILTER_KEYS = (
    "scope",
    "ticket_type",
    "service_entitlement",
    "functional_track_ams_owner",
    "assignment_group_support_lead",
    "parent_application_name",
    "application_owner",
    "supported_by_vendor",
    "sap_non_sap",
    "business_critical",
    "architecture_type",
    "install_type",
    "hosting_env",
    "priority",
    "state",
    "status_group",
)

APPLICATION_FACT_FIELDS = {
    "application_scope": "scope",
    "service_entitlement": "service_entitlement",
    "functional_track_ams_owner": "functional_track_ams_owner",
    "assignment_group_owner": "assignment_group_support_owner",
    "parent_application_name": "parent_business_application",
    "application_owner": "application_owner",
    "supported_by_vendor": "supported_by_vendor",
    "sap_non_sap": "sap_non_sap",
    "architecture_type": "architecture_type",
    "application_type": "application_type",
    "business_critical": "business_critical",
    "install_status": "install_status",
    "install_type": "install_type",
    "hosting_env": "hosting_env",
    "global": "global_flag",
    "life_cycle_stage": "life_cycle_stage",
    "life_cycle_stage_status": "life_cycle_stage_status",
}

VOLUMETRICS_FACT_FIELDS = {
    "service_entitlement": "service_entitlement",
    "functional_track_ams_owner": "functional_track_ams_owner",
    "assignment_group_support_lead": "assignment_group_support_owner",
    "parent_application_name": "parent_business_application",
    "application_owner": "application_owner",
    "supported_by_vendor": "supported_by_vendor",
    "sap_non_sap": "sap_non_sap",
    "business_critical": "business_critical",
    "architecture_type": "architecture_type",
    "install_type": "install_type",
    "hosting_env": "hosting_env",
    "priority": "priority",
    "state": "state",
    "status_group": "status_group",
}

APPLICATION_PAYLOAD_KEYS = {
    "architecture_type": ("Architecture type", "Architecture Type"),
    "application_type": ("Application type", "Application Type"),
    "business_critical": (
        "Business criticality",
        "Biz Criticality",
        "Business Criticality",
        "Business Critical",
    ),
    "install_status": ("Install Status",),
    "install_type": ("Install type", "Install Type"),
    "service_entitlement": ("Service Entitlement",),
    "service_type": ("Service Type",),
    "life_cycle_stage": ("Life Cycle Stage", "Lifecycle Status"),
}


@dataclass(frozen=True)
class DashboardFilterCacheRefreshResult:
    project_id: UUID
    dashboard_area: str
    status: str
    data_version: str
    facts_count: int
    catalog_count: int
    duration_ms: int


def new_data_version() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")


def validate_dashboard_area(dashboard_area: str) -> str:
    normalized = dashboard_area.strip().casefold()
    if normalized not in (*DASHBOARD_FILTER_AREAS, "all"):
        raise ValueError("dashboard_area must be applications, volumetrics, or all.")
    return normalized


def project_client_id(db: Session, project_id: UUID) -> UUID:
    client_id = db.scalar(select(Project.client_id).where(Project.id == project_id))
    if client_id is None:
        raise FileNotFoundError(f"Project {project_id} was not found.")
    return client_id


def get_or_create_status(
    db: Session,
    customer_id: UUID,
    project_id: UUID,
    dashboard_area: str,
) -> DashboardFilterCacheStatus:
    status_row = db.scalar(
        select(DashboardFilterCacheStatus).where(
            DashboardFilterCacheStatus.customer_id == customer_id,
            DashboardFilterCacheStatus.project_id == project_id,
            DashboardFilterCacheStatus.dashboard_area == dashboard_area,
        ),
    )
    if status_row is not None:
        return status_row
    status_row = DashboardFilterCacheStatus(
        customer_id=customer_id,
        project_id=project_id,
        dashboard_area=dashboard_area,
        status="missing",
        is_stale=True,
    )
    db.add(status_row)
    db.flush()
    return status_row


def mark_filter_caches_stale(
    db: Session,
    project_id: UUID,
    dashboard_areas: tuple[str, ...] = DASHBOARD_FILTER_AREAS,
) -> None:
    customer_id = project_client_id(db, project_id)
    for dashboard_area in dashboard_areas:
        status_row = get_or_create_status(db, customer_id, project_id, dashboard_area)
        if status_row.status == "ready":
            status_row.status = "stale"
        status_row.is_stale = True
        status_row.error_message = None


def filter_cache_status_items(
    db: Session,
    customer_id: UUID,
    project_id: UUID,
    dashboard_area: str | None = None,
) -> list[dict[str, Any]]:
    areas = DASHBOARD_FILTER_AREAS
    if dashboard_area:
        normalized = validate_dashboard_area(dashboard_area)
        areas = DASHBOARD_FILTER_AREAS if normalized == "all" else (normalized,)

    rows = db.scalars(
        select(DashboardFilterCacheStatus).where(
            DashboardFilterCacheStatus.customer_id == customer_id,
            DashboardFilterCacheStatus.project_id == project_id,
            DashboardFilterCacheStatus.dashboard_area.in_(areas),
        ),
    ).all()
    by_area = {row.dashboard_area: row for row in rows}
    items: list[dict[str, Any]] = []
    for area in areas:
        row = by_area.get(area)
        if row is None:
            items.append(
                {
                    "dashboard_area": area,
                    "status": "missing",
                    "data_version": None,
                    "last_success_at": None,
                    "is_stale": True,
                    "error_message": None,
                },
            )
            continue
        items.append(
            {
                "dashboard_area": row.dashboard_area,
                "status": row.status,
                "data_version": row.data_version,
                "last_success_at": row.last_success_at,
                "is_stale": row.is_stale,
                "error_message": row.error_message,
            },
        )
    return items


def refresh_all_filter_caches(
    db: Session,
    project_id: UUID,
) -> list[DashboardFilterCacheRefreshResult]:
    return [refresh_filter_cache(db, project_id, area) for area in DASHBOARD_FILTER_AREAS]


def refresh_filter_cache(
    db: Session,
    project_id: UUID,
    dashboard_area: str,
) -> DashboardFilterCacheRefreshResult:
    area = validate_dashboard_area(dashboard_area)
    if area == "all":
        results = refresh_all_filter_caches(db, project_id)
        facts_count = sum(result.facts_count for result in results)
        catalog_count = sum(result.catalog_count for result in results)
        duration_ms = sum(result.duration_ms for result in results)
        data_version = results[-1].data_version if results else new_data_version()
        return DashboardFilterCacheRefreshResult(
            project_id=project_id,
            dashboard_area="all",
            status="ready",
            data_version=data_version,
            facts_count=facts_count,
            catalog_count=catalog_count,
            duration_ms=duration_ms,
        )

    customer_id = project_client_id(db, project_id)
    status_row = get_or_create_status(db, customer_id, project_id, area)
    data_version = new_data_version()
    started_at = datetime.now(UTC)
    started = perf_counter()
    status_row.status = "refreshing"
    status_row.data_version = data_version
    status_row.started_at = started_at
    status_row.finished_at = None
    status_row.error_message = None
    db.flush()

    try:
        if area == "applications":
            facts_count = refresh_application_filter_facts(db, project_id, data_version)
        else:
            refresh_dashboard_filter_facts(db, project_id, data_version=data_version)
            facts_count = dashboard_area_fact_count(db, project_id, area)
        catalog_count = build_filter_catalog_from_facts(db, project_id, area, data_version)
        finished_at = datetime.now(UTC)
        status_row.status = "ready"
        status_row.finished_at = finished_at
        status_row.last_success_at = finished_at
        status_row.is_stale = False
        duration_ms = int((perf_counter() - started) * 1000)
        return DashboardFilterCacheRefreshResult(
            project_id=project_id,
            dashboard_area=area,
            status="ready",
            data_version=data_version,
            facts_count=facts_count,
            catalog_count=catalog_count,
            duration_ms=duration_ms,
        )
    except Exception as exc:
        status_row.status = "failed"
        status_row.finished_at = datetime.now(UTC)
        status_row.error_message = str(exc)
        status_row.is_stale = True
        raise


def dashboard_area_fact_count(db: Session, project_id: UUID, dashboard_area: str) -> int:
    return int(
        db.scalar(
            select(func.count(DashboardFilterFact.id)).where(
                DashboardFilterFact.project_id == project_id,
                DashboardFilterFact.dashboard_area == dashboard_area,
            ),
        )
        or 0,
    )


def dashboard_area_catalog_count(db: Session, project_id: UUID, dashboard_area: str) -> int:
    return int(
        db.scalar(
            select(func.count(DashboardFilterCatalog.id)).where(
                DashboardFilterCatalog.project_id == project_id,
                DashboardFilterCatalog.dashboard_area == dashboard_area,
            ),
        )
        or 0,
    )


def ensure_filter_cache_for_read(
    db: Session,
    customer_id: UUID,
    project_id: UUID,
    dashboard_area: str,
) -> dict[str, Any]:
    project_customer_id = project_client_id(db, project_id)
    if project_customer_id != customer_id:
        raise ValueError("customer_id does not match the selected project.")

    status = filter_cache_status_items(db, customer_id, project_id, dashboard_area)[0]
    catalog_count = dashboard_area_catalog_count(db, project_id, dashboard_area)
    if status["status"] == "missing" or catalog_count == 0:
        refresh_filter_cache(db, project_id, dashboard_area)
        db.commit()
        status = filter_cache_status_items(db, customer_id, project_id, dashboard_area)[0]
    return status


def payload_text_sql(alias: str, *keys: str) -> str:
    return "COALESCE(" + ", ".join(f"{alias}.cmdb_payload ->> '{key}'" for key in keys) + ")"


def cleaned_sql(expression: str, length: int = 255) -> str:
    return f"left(NULLIF(btrim({expression}), ''), {length})"


def dashboard_filter_fact_has_service_fields(db: Session) -> bool:
    inspector = inspect(db.get_bind())
    if "dashboard_filter_facts" not in inspector.get_table_names():
        return False
    columns = {column["name"] for column in inspector.get_columns("dashboard_filter_facts")}
    return {"service_entitlement", "service_type"}.issubset(columns)


def refresh_application_filter_facts(
    db: Session,
    project_id: UUID,
    data_version: str,
) -> int:
    include_service_fields = dashboard_filter_fact_has_service_fields(db)
    service_columns = (
        """
                service_entitlement,
                service_type,
"""
        if include_service_fields
        else ""
    )
    service_selects = (
        """
                left(NULLIF(btrim(i.service_entitlement), ''), 255),
                left(NULLIF(btrim(i.service_type), ''), 255),
"""
        if include_service_fields
        else ""
    )
    db.execute(
        delete(DashboardFilterFact).where(
            DashboardFilterFact.project_id == project_id,
            DashboardFilterFact.dashboard_area == "applications",
        ),
    )
    architecture = cleaned_sql(
        payload_text_sql("i", *APPLICATION_PAYLOAD_KEYS["architecture_type"]),
    )
    application_type = cleaned_sql(
        payload_text_sql("i", *APPLICATION_PAYLOAD_KEYS["application_type"]),
    )
    business_critical = cleaned_sql(
        payload_text_sql("i", *APPLICATION_PAYLOAD_KEYS["business_critical"]),
    )
    install_status = cleaned_sql(payload_text_sql("i", *APPLICATION_PAYLOAD_KEYS["install_status"]))
    install_type = cleaned_sql(payload_text_sql("i", *APPLICATION_PAYLOAD_KEYS["install_type"]))
    life_cycle_stage = cleaned_sql(
        payload_text_sql("i", *APPLICATION_PAYLOAD_KEYS["life_cycle_stage"]),
    )
    result = db.execute(
        text(
            f"""
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
{service_columns}                global_flag,
                life_cycle_stage,
                life_cycle_stage_status,
                data_version
            )
            SELECT DISTINCT ON (lower(btrim(i.business_service_ci_name)))
                md5('application_inventory_items:' || i.id::text)::uuid,
                p.client_id,
                i.project_id,
                'applications',
                'application',
                'application_inventory_items',
                'application',
                COALESCE(NULLIF(btrim(i.scope_status), ''), 'out_of_scope'),
                i.id,
                left(NULLIF(btrim(i.business_service_ci_name), ''), 255),
                left(NULLIF(btrim(i.functional_track), ''), 255),
                left(NULLIF(btrim(i.ams_owner), ''), 255),
                left(
                    COALESCE(NULLIF(btrim(i.functional_track), ''), '{BLANK_LABEL}')
                    || ' - '
                    || COALESCE(NULLIF(btrim(i.ams_owner), ''), '{BLANK_LABEL}'),
                    512
                ),
                left(NULLIF(btrim(i.assignment_group), ''), 255),
                left(NULLIF(btrim(i.assignment_group_owner), ''), 255),
                left(
                    COALESCE(NULLIF(btrim(i.assignment_group), ''), '{BLANK_LABEL}')
                    || ' - '
                    || COALESCE(NULLIF(btrim(i.assignment_group_owner), ''), '{BLANK_LABEL}'),
                    512
                ),
                left(NULLIF(btrim(i.parent_application_name), ''), 255),
                left(NULLIF(btrim(i.business_service_ci_name), ''), 255),
                left(NULLIF(btrim(i.application_owner), ''), 255),
                left(NULLIF(btrim(i.supported_by_vendor), ''), 255),
                left(NULLIF(btrim(i.sap_non_sap), ''), 50),
                {architecture},
                {application_type},
                {business_critical},
                {install_status},
                {install_type},
                left(NULLIF(btrim(i.hosting_env), ''), 255),
{service_selects}                left(NULLIF(btrim(i.global_application), ''), 50),
                {life_cycle_stage},
                left(NULLIF(btrim(i.lifecycle_stage_status), ''), 255),
                :data_version
            FROM application_inventory_items AS i
            JOIN projects AS p ON p.id = i.project_id
            WHERE i.project_id = CAST(:project_id AS uuid)
              AND i.is_current IS true
              AND NULLIF(btrim(i.business_service_ci_name), '') IS NOT NULL
            ORDER BY lower(btrim(i.business_service_ci_name)), i.id
            """
        ),
        {"project_id": str(project_id), "data_version": data_version},
    )
    return int(result.rowcount or 0)


def fact_display_expression(column: Any) -> Any:
    return func.coalesce(func.nullif(func.btrim(column), ""), BLANK_LABEL)


def fact_lifecycle_status_stage_expression() -> Any:
    return (
        fact_display_expression(DashboardFilterFact.life_cycle_stage)
        + " - "
        + fact_display_expression(DashboardFilterFact.life_cycle_stage_status)
    )


def fact_filter_expression(dashboard_area: str, filter_key: str) -> Any:
    if dashboard_area == "applications" and filter_key == "lifecycle_status_stage":
        return fact_lifecycle_status_stage_expression()
    if dashboard_area == "applications" and filter_key == "application_scope":
        return DashboardFilterFact.scope
    if dashboard_area == "volumetrics" and filter_key == "scope":
        return DashboardFilterFact.scope
    if dashboard_area == "volumetrics" and filter_key == "ticket_type":
        return DashboardFilterFact.record_type
    fields = (
        APPLICATION_FACT_FIELDS
        if dashboard_area == "applications"
        else VOLUMETRICS_FACT_FIELDS
    )
    field_name = fields.get(filter_key)
    if field_name is None:
        raise ValueError(f"Unsupported filter key {filter_key!r} for {dashboard_area}.")
    return fact_display_expression(getattr(DashboardFilterFact, field_name))


def filter_keys_for_area(dashboard_area: str, db: Session | None = None) -> tuple[str, ...]:
    keys = APPLICATION_FILTER_KEYS if dashboard_area == "applications" else VOLUMETRICS_FILTER_KEYS
    if db is not None and not dashboard_filter_fact_has_service_fields(db):
        return tuple(key for key in keys if key != "service_entitlement")
    return keys


def catalog_sort_key(filter_key: str, value: str) -> tuple[int, str]:
    if filter_key == "scope":
        order = ("all", "in_scope", "out_of_scope")
        return (order.index(value) if value in order else len(order), value.casefold())
    if filter_key == "ticket_type":
        order = ("all", "incident", "sc_task")
        return (order.index(value) if value in order else len(order), value.casefold())
    if filter_key == "application_scope":
        order = ("in_scope", "out_of_scope")
        return (order.index(value) if value in order else len(order), value.casefold())
    if filter_key in {"business_critical", "business_criticality"}:
        rank = {
            label.casefold(): index
            for index, label in enumerate(APPLICATION_CRITICALITY_ORDER)
        }
        return (rank.get(value.casefold(), len(rank)), value.casefold())
    return application_filter_sort_key(filter_key, value)[:2]


def catalog_display_value(filter_key: str, value: str) -> str:
    if filter_key == "scope":
        return VOLUMETRICS_SCOPE_LABELS.get(value, value)
    if filter_key == "ticket_type":
        return VOLUMETRICS_TICKET_TYPE_LABELS.get(value, value)
    if filter_key == "application_scope":
        return {
            "in_scope": "In Scope",
            "out_of_scope": "Out of Scope",
        }.get(value, value)
    return value


def build_filter_catalog_from_facts(
    db: Session,
    project_id: UUID,
    dashboard_area: str,
    data_version: str,
) -> int:
    project = db.get(Project, project_id)
    if project is None:
        raise FileNotFoundError(f"Project {project_id} was not found.")
    db.execute(
        delete(DashboardFilterCatalog).where(
            DashboardFilterCatalog.project_id == project_id,
            DashboardFilterCatalog.dashboard_area == dashboard_area,
        ),
    )
    refreshed_at = datetime.now(UTC)
    inserted = 0
    for filter_key in filter_keys_for_area(dashboard_area, db):
        rows = baseline_rows_for_filter(db, project_id, dashboard_area, filter_key)
        for sort_order, row in enumerate(
            sorted(rows, key=lambda item: catalog_sort_key(filter_key, item["value"])),
        ):
            db.add(
                DashboardFilterCatalog(
                    customer_id=project.client_id,
                    project_id=project_id,
                    dashboard_area=dashboard_area,
                    filter_key=filter_key,
                    filter_value=row["value"],
                    display_value=catalog_display_value(filter_key, row["value"]),
                    baseline_count=row["count"],
                    sort_order=sort_order,
                    data_version=data_version,
                    refreshed_at=refreshed_at,
                ),
            )
            inserted += 1
    db.flush()
    return inserted


def baseline_rows_for_filter(
    db: Session,
    project_id: UUID,
    dashboard_area: str,
    filter_key: str,
) -> list[dict[str, Any]]:
    if dashboard_area == "applications" and filter_key == "application_scope":
        rows = {
            row["scope"]: int(row["count"] or 0)
            for row in db.execute(
                select(DashboardFilterFact.scope, func.count(DashboardFilterFact.id).label("count"))
                .where(
                    DashboardFilterFact.project_id == project_id,
                    DashboardFilterFact.dashboard_area == dashboard_area,
                )
                .group_by(DashboardFilterFact.scope),
            ).mappings()
            if row["scope"] is not None
        }
        return [
            {"value": "in_scope", "count": rows.get("in_scope", 0)},
            {"value": "out_of_scope", "count": rows.get("out_of_scope", 0)},
        ]
    if dashboard_area == "volumetrics" and filter_key == "scope":
        rows = [
            {"value": row["scope"], "count": int(row["count"] or 0)}
            for row in db.execute(
                select(DashboardFilterFact.scope, func.count(DashboardFilterFact.id).label("count"))
                .where(
                    DashboardFilterFact.project_id == project_id,
                    DashboardFilterFact.dashboard_area == dashboard_area,
                )
                .group_by(DashboardFilterFact.scope),
            ).mappings()
        ]
        total = sum(row["count"] for row in rows)
        return [{"value": "all", "count": total}, *rows]
    if dashboard_area == "volumetrics" and filter_key == "ticket_type":
        rows = [
            {"value": row["record_type"], "count": int(row["count"] or 0)}
            for row in db.execute(
                select(
                    DashboardFilterFact.record_type,
                    func.count(DashboardFilterFact.id).label("count"),
                )
                .where(
                    DashboardFilterFact.project_id == project_id,
                    DashboardFilterFact.dashboard_area == dashboard_area,
                )
                .group_by(DashboardFilterFact.record_type),
            ).mappings()
        ]
        total = sum(row["count"] for row in rows)
        return [{"value": "all", "count": total}, *rows]

    expression = fact_filter_expression(dashboard_area, filter_key)
    return [
        {"value": row["value"], "count": int(row["count"] or 0)}
        for row in db.execute(
            select(expression.label("value"), func.count(DashboardFilterFact.id).label("count"))
            .where(
                DashboardFilterFact.project_id == project_id,
                DashboardFilterFact.dashboard_area == dashboard_area,
            )
            .group_by(expression),
        ).mappings()
        if row["value"] is not None
    ]


def filter_catalog(
    db: Session,
    customer_id: UUID,
    project_id: UUID,
    dashboard_area: str,
) -> dict[str, Any]:
    area = validate_dashboard_area(dashboard_area)
    if area == "all":
        raise ValueError("dashboard_area must be applications or volumetrics for catalog reads.")
    status = ensure_filter_cache_for_read(db, customer_id, project_id, area)
    rows = db.scalars(
        select(DashboardFilterCatalog)
        .where(
            DashboardFilterCatalog.customer_id == customer_id,
            DashboardFilterCatalog.project_id == project_id,
            DashboardFilterCatalog.dashboard_area == area,
        )
        .order_by(
            DashboardFilterCatalog.filter_key.asc(),
            DashboardFilterCatalog.sort_order.asc(),
            DashboardFilterCatalog.display_value.asc(),
        ),
    ).all()
    filters: dict[str, list[dict[str, Any]]] = {
        key: [] for key in filter_keys_for_area(area, db)
    }
    for row in rows:
        filters.setdefault(row.filter_key, []).append(
            {
                "value": row.filter_value,
                "label": row.display_value,
                "baseline_count": row.baseline_count,
                "sort_order": row.sort_order,
            },
        )
    warnings: list[str] = []
    if status["status"] == "missing" or not rows:
        warnings.append(
            "Filter cache is missing. Refresh the dashboard filter cache in Maintenance.",
        )
    elif status["is_stale"]:
        warnings.append("Filter cache is stale. Showing the last available filter catalog.")
    return {
        "dashboard_area": area,
        "status": status["status"],
        "data_version": status["data_version"],
        "filters": filters,
        "warnings": warnings,
    }


def dynamic_filter_counts(
    db: Session,
    customer_id: UUID,
    project_id: UUID,
    dashboard_area: str,
    selected_filters: dict[str, list[str]],
    *,
    scope: str = "in_scope",
    ticket_type: str = "all",
    from_datetime: datetime | None = None,
    to_datetime: datetime | None = None,
) -> dict[str, Any]:
    area = validate_dashboard_area(dashboard_area)
    if area == "all":
        raise ValueError("dashboard_area must be applications or volumetrics for count reads.")
    started = perf_counter()
    status = ensure_filter_cache_for_read(db, customer_id, project_id, area)
    counts: dict[str, dict[str, int]] = {}
    for filter_key in filter_keys_for_area(area, db):
        rows = count_rows_for_filter(
            db,
            project_id,
            area,
            filter_key,
            selected_filters,
            scope=scope,
            ticket_type=ticket_type,
            from_datetime=from_datetime,
            to_datetime=to_datetime,
        )
        selected_values = selected_filters.get(filter_key, [])
        for selected_value in selected_values:
            rows.setdefault(selected_value, 0)
        counts[filter_key] = rows
    return {
        "dashboard_area": area,
        "status": "success",
        "data_version": status["data_version"],
        "counts": counts,
        "duration_ms": int((perf_counter() - started) * 1000),
        "warnings": [] if status["status"] != "missing" else ["Filter cache is missing."],
    }


def count_rows_for_filter(
    db: Session,
    project_id: UUID,
    dashboard_area: str,
    filter_key: str,
    selected_filters: dict[str, list[str]],
    *,
    scope: str,
    ticket_type: str,
    from_datetime: datetime | None,
    to_datetime: datetime | None,
) -> dict[str, int]:
    expression = fact_filter_expression(dashboard_area, filter_key)
    conditions = [
        DashboardFilterFact.project_id == project_id,
        DashboardFilterFact.dashboard_area == dashboard_area,
    ]
    if dashboard_area == "volumetrics":
        normalized_scope = normalize_volumetrics_scope(scope)
        if filter_key != "scope" and normalized_scope != "all":
            conditions.append(DashboardFilterFact.scope == normalized_scope)
        normalized_ticket_type = normalize_volumetrics_ticket_type(ticket_type)
        if filter_key != "ticket_type" and normalized_ticket_type != "all":
            conditions.append(DashboardFilterFact.record_type == normalized_ticket_type)
        if from_datetime is not None:
            conditions.append(DashboardFilterFact.created_at_source >= from_datetime)
        if to_datetime is not None:
            conditions.append(DashboardFilterFact.created_at_source <= to_datetime)

    for selected_key, selected_values in selected_filters.items():
        if selected_key == filter_key or not selected_values:
            continue
        selected_expression = fact_filter_expression(dashboard_area, selected_key)
        conditions.append(selected_expression.in_(selected_values))

    rows = db.execute(
        select(expression.label("value"), func.count(DashboardFilterFact.id).label("count"))
        .where(*conditions)
        .group_by(expression),
    ).mappings()
    return {str(row["value"]): int(row["count"] or 0) for row in rows if row["value"] is not None}
