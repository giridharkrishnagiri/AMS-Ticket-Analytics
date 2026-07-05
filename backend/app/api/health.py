from datetime import UTC, datetime
from time import perf_counter
from typing import Annotated, Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.schemas.health import HealthCheckItem, HealthPingResponse, HealthResponse

router = APIRouter(tags=["health"])
DbSession = Annotated[Session, Depends(get_db)]

FRONTEND_HEALTH_TARGETS = {
    "main_frontend": "http://127.0.0.1:5173",
    "genai_frontend": "http://127.0.0.1:3025",
}


def _duration_ms(started_at: float) -> int:
    return max(0, int((perf_counter() - started_at) * 1000))


def _check_frontend(name: str, url: str) -> HealthCheckItem:
    started_at = perf_counter()
    try:
        request = Request(url, headers={"User-Agent": "ams-health-check/1.0"})
        with urlopen(request, timeout=1.5) as response:
            status_code = response.getcode()
    except HTTPError as error:
        return HealthCheckItem(
            name=name,
            status="degraded",
            message=f"{url} responded with HTTP {error.code}.",
            duration_ms=_duration_ms(started_at),
            details={"url": url, "http_status": error.code},
        )
    except (OSError, URLError) as error:
        return HealthCheckItem(
            name=name,
            status="degraded",
            message=f"{url} is not reachable: {error}.",
            duration_ms=_duration_ms(started_at),
            details={"url": url},
        )

    return HealthCheckItem(
        name=name,
        status="ok",
        message=f"{url} is reachable.",
        duration_ms=_duration_ms(started_at),
        details={"url": url, "http_status": status_code},
    )


def _safe_int(value: Any) -> int:
    if value is None:
        return 0
    return int(value)


def _check_database(db: Session) -> tuple[list[HealthCheckItem], dict[str, Any]]:
    checks: list[HealthCheckItem] = []
    database_details: dict[str, Any] = {}

    started_at = perf_counter()
    try:
        database_row = db.execute(
            text(
                """
                SELECT
                    current_database() AS database_name,
                    inet_server_addr()::text AS server_address,
                    inet_server_port() AS server_port,
                    pg_database_size(current_database()) AS database_size_bytes,
                    current_setting('max_connections')::int AS max_connections
                """
            )
        ).mappings().one()
        database_details.update(dict(database_row))
        checks.append(
            HealthCheckItem(
                name="database",
                status="ok",
                message="Database connection is available.",
                duration_ms=_duration_ms(started_at),
                details=dict(database_row),
            )
        )
    except Exception as error:  # pragma: no cover - defensive health endpoint handling
        checks.append(
            HealthCheckItem(
                name="database",
                status="error",
                message=f"Database connection failed: {error}",
                duration_ms=_duration_ms(started_at),
            )
        )
        database_details["status"] = "error"
        return checks, database_details

    started_at = perf_counter()
    try:
        activity_row = db.execute(
            text(
                """
                SELECT
                    COUNT(*) AS connected_sessions,
                    COUNT(*) FILTER (WHERE state = 'active') AS active_sessions,
                    COUNT(*) FILTER (
                        WHERE cardinality(pg_blocking_pids(pid)) > 0
                    ) AS blocked_sessions,
                    COUNT(*) FILTER (WHERE wait_event_type = 'Lock') AS lock_waiting_sessions,
                    COUNT(*) FILTER (
                        WHERE state = 'idle in transaction'
                    ) AS idle_in_transaction_sessions
                FROM pg_stat_activity
                WHERE datname = current_database()
                  AND pid <> pg_backend_pid()
                """
            )
        ).mappings().one()
        lock_rows = db.execute(
            text(
                """
                SELECT
                    COALESCE(l.relation::regclass::text, l.locktype) AS relation_name,
                    l.mode,
                    l.granted,
                    a.pid,
                    a.state,
                    a.wait_event_type,
                    a.wait_event,
                    EXTRACT(
                        EPOCH FROM now() - COALESCE(a.xact_start, a.query_start, now())
                    )::int AS age_seconds
                FROM pg_locks l
                JOIN pg_stat_activity a ON a.pid = l.pid
                WHERE a.datname = current_database()
                  AND a.pid <> pg_backend_pid()
                  AND (
                    NOT l.granted
                    OR a.wait_event_type = 'Lock'
                    OR a.state = 'idle in transaction'
                  )
                ORDER BY age_seconds DESC NULLS LAST
                LIMIT 10
                """
            )
        ).mappings().all()

        activity = dict(activity_row)
        lock_sample = [dict(row) for row in lock_rows]
        blocked_sessions = _safe_int(activity.get("blocked_sessions"))
        lock_waiting_sessions = _safe_int(activity.get("lock_waiting_sessions"))
        idle_sessions = _safe_int(activity.get("idle_in_transaction_sessions"))
        lock_status = (
            "degraded" if blocked_sessions or lock_waiting_sessions or idle_sessions else "ok"
        )
        lock_message = (
            "Potential blocking database activity detected."
            if lock_status == "degraded"
            else "No blocking lock waits or idle transactions were detected."
        )
        lock_details = {**activity, "sample": lock_sample}
        database_details.update(
            {"activity": activity, "locks": lock_details, "status": lock_status}
        )
        checks.append(
            HealthCheckItem(
                name="database_locks",
                status=lock_status,
                message=lock_message,
                duration_ms=_duration_ms(started_at),
                details=lock_details,
            )
        )
    except Exception as error:  # pragma: no cover - permission-dependent diagnostics
        database_details["status"] = "degraded"
        checks.append(
            HealthCheckItem(
                name="database_locks",
                status="degraded",
                message=f"Database lock diagnostics could not be completed: {error}",
                duration_ms=_duration_ms(started_at),
            )
        )

    started_at = perf_counter()
    try:
        tablespace_rows = db.execute(
            text(
                """
                SELECT
                    spcname AS tablespace_name,
                    pg_tablespace_size(oid) AS size_bytes
                FROM pg_tablespace
                ORDER BY spcname
                """
            )
        ).mappings().all()
        tablespaces = [dict(row) for row in tablespace_rows]
        database_details["tablespaces"] = tablespaces
        checks.append(
            HealthCheckItem(
                name="database_tablespaces",
                status="ok",
                message="Database tablespaces are accessible.",
                duration_ms=_duration_ms(started_at),
                details={"tablespaces": tablespaces},
            )
        )
    except Exception as error:  # pragma: no cover - permission-dependent diagnostics
        database_details["status"] = "degraded"
        checks.append(
            HealthCheckItem(
                name="database_tablespaces",
                status="degraded",
                message=f"Database tablespace diagnostics could not be completed: {error}",
                duration_ms=_duration_ms(started_at),
            )
        )

    database_details.setdefault("status", "ok")
    return checks, database_details


def _overall_status(checks: list[HealthCheckItem]) -> str:
    statuses = {check.status for check in checks}
    if "error" in statuses:
        return "error"
    if statuses.intersection({"degraded", "warning"}):
        return "degraded"
    return "ok"


@router.get("/health/ping", response_model=HealthPingResponse)
def health_ping() -> HealthPingResponse:
    settings = get_settings()
    return HealthPingResponse(
        status="ok",
        service=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
        checked_at=datetime.now(UTC),
    )


@router.get("/health", response_model=HealthResponse)
def health_check(db: DbSession) -> HealthResponse:
    settings = get_settings()
    checks = [
        HealthCheckItem(
            name="backend_api",
            status="ok",
            message="FastAPI backend is responding.",
            details={"service": settings.app_name, "environment": settings.environment},
        )
    ]
    database_checks, database_details = _check_database(db)
    checks.extend(database_checks)

    frontends: dict[str, Any] = {}
    for name, url in FRONTEND_HEALTH_TARGETS.items():
        check = _check_frontend(name, url)
        checks.append(check)
        frontends[name] = check.model_dump()

    storage_root = settings.resolved_storage_root
    storage_status = "ok" if storage_root.exists() else "degraded"
    checks.append(
        HealthCheckItem(
            name="storage_root",
            status=storage_status,
            message=(
                "Storage root exists."
                if storage_status == "ok"
                else "Storage root does not exist yet."
            ),
            details={"path": str(storage_root)},
        )
    )

    return HealthResponse(
        status=_overall_status(checks),
        service=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
        checked_at=datetime.now(UTC),
        storage_root=str(storage_root),
        checks=checks,
        database=database_details,
        frontends=frontends,
    )
