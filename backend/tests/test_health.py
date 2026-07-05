from fastapi.testclient import TestClient

from app.main import app


def test_health_check_returns_ok() -> None:
    with TestClient(app) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] in {"ok", "degraded", "error"}
    assert payload["service"] == "AMS Ticket Intelligence"
    assert "storage_root" in payload
    check_names = {check["name"] for check in payload["checks"]}
    assert "backend_api" in check_names
    assert "database" in check_names
    assert "database_locks" in check_names
    assert "main_frontend" in check_names
    assert "genai_frontend" in check_names
    assert "database" in payload
    assert "frontends" in payload


def test_health_ping_returns_lightweight_liveness() -> None:
    with TestClient(app) as client:
        response = client.get("/api/health/ping")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["service"] == "AMS Ticket Intelligence"
    assert payload["environment"]
    assert payload["checked_at"]
    assert "checks" not in payload
    assert "database" not in payload
    assert "frontends" not in payload
