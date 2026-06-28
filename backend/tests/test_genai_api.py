from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.db.session import SessionLocal
from app.main import app
from app.models import GenAIConfig, GenAIPromptTemplate, GenAISafetySettings, GenAIUsageLog
from app.services.genai.default_prompts import DEFAULT_PROMPTS_BY_KEY
from app.services.genai.usage_log_service import create_usage_log


def reset_genai_tables() -> None:
    db = SessionLocal()
    try:
        for model in (GenAIUsageLog, GenAIPromptTemplate, GenAISafetySettings, GenAIConfig):
            db.execute(delete(model))
        db.commit()
    finally:
        db.close()


def configure_genai(client: TestClient, **overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "is_enabled": True,
        "provider": "openai",
        "model_name": "gpt-4.1-mini",
        "temperature": 0.2,
        "top_p": 1.0,
        "max_output_tokens": 1000,
        "timeout_seconds": 60,
        "max_tool_calls": 5,
        "allow_recommendations": True,
        "allow_chart_generation": False,
        "response_style": "standard",
    }
    payload.update(overrides)
    response = client.put("/api/genai/config", json=payload)
    assert response.status_code == 200
    return response.json()


def usage_log_count() -> int:
    db = SessionLocal()
    try:
        return db.query(GenAIUsageLog).count()
    finally:
        db.close()


def test_genai_config_get_returns_defaults_and_no_api_keys() -> None:
    reset_genai_tables()

    with TestClient(app) as client:
        response = client.get("/api/genai/config")

    assert response.status_code == 200
    payload = response.json()
    assert payload["is_enabled"] is False
    assert payload["provider"] == "openai"
    assert payload["model_name"] is None
    assert payload["temperature"] == 0.2
    assert payload["top_p"] == 1.0
    assert payload["max_output_tokens"] == 1000
    assert payload["response_style"] == "standard"
    assert "api_key" not in payload
    assert "OPENAI_API_KEY" not in str(payload)


def test_genai_config_put_updates_valid_config() -> None:
    reset_genai_tables()

    with TestClient(app) as client:
        response = client.put(
            "/api/genai/config",
            json={
                "is_enabled": True,
                "provider": "anthropic",
                "model_name": "claude-3-5-sonnet",
                "temperature": 0.4,
                "top_p": 0.9,
                "max_output_tokens": 2000,
                "timeout_seconds": 45,
                "max_tool_calls": 3,
                "allow_recommendations": False,
                "allow_chart_generation": True,
                "response_style": "concise",
            },
        )
        refresh_response = client.get("/api/genai/config")

    assert response.status_code == 200
    payload = refresh_response.json()
    assert payload["is_enabled"] is True
    assert payload["provider"] == "anthropic"
    assert payload["model_name"] == "claude-3-5-sonnet"
    assert payload["temperature"] == 0.4
    assert payload["top_p"] == 0.9
    assert payload["max_output_tokens"] == 2000
    assert payload["timeout_seconds"] == 45
    assert payload["max_tool_calls"] == 3
    assert payload["allow_recommendations"] is False
    assert payload["allow_chart_generation"] is True
    assert payload["response_style"] == "concise"


def test_genai_config_rejects_invalid_values() -> None:
    reset_genai_tables()

    with TestClient(app) as client:
        temperature_response = client.put("/api/genai/config", json={"temperature": 2.5})
        top_p_response = client.put("/api/genai/config", json={"top_p": 1.5})
        style_response = client.put("/api/genai/config", json={"response_style": "verbose"})

    assert temperature_response.status_code == 422
    assert top_p_response.status_code == 422
    assert style_response.status_code == 422


def test_genai_prompt_defaults_are_seeded_and_listed() -> None:
    reset_genai_tables()

    with TestClient(app) as client:
        response = client.get("/api/genai/prompts")

    assert response.status_code == 200
    prompt_keys = {row["prompt_key"] for row in response.json()}
    assert set(DEFAULT_PROMPTS_BY_KEY) == prompt_keys


def test_genai_prompt_update_and_reset() -> None:
    reset_genai_tables()

    with TestClient(app) as client:
        update_response = client.put(
            "/api/genai/prompts/system_domain_rules",
            json={
                "custom_prompt": "Use aggregate-only AMS answers.",
                "is_custom_enabled": True,
            },
        )
        reset_response = client.post("/api/genai/prompts/system_domain_rules/reset")

    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["custom_prompt"] == "Use aggregate-only AMS answers."
    assert updated["is_custom_enabled"] is True
    assert reset_response.status_code == 200
    reset = reset_response.json()
    assert reset["custom_prompt"] is None
    assert reset["is_custom_enabled"] is False


def test_genai_prompt_reseed_preserves_custom_prompts() -> None:
    reset_genai_tables()

    with TestClient(app) as client:
        update_response = client.put(
            "/api/genai/prompts/answer_summarizer",
            json={
                "custom_prompt": "Summarize with filters and exclusions.",
                "is_custom_enabled": True,
            },
        )
        reseed_response = client.post("/api/genai/prompts/reseed-defaults")
        prompt_response = client.get("/api/genai/prompts/answer_summarizer")

    assert update_response.status_code == 200
    assert reseed_response.status_code == 200
    assert prompt_response.status_code == 200
    payload = prompt_response.json()
    assert payload["custom_prompt"] == "Summarize with filters and exclusions."
    assert payload["is_custom_enabled"] is True


def test_genai_safety_settings_defaults_update_and_validation() -> None:
    reset_genai_tables()

    with TestClient(app) as client:
        default_response = client.get("/api/genai/safety-settings")
        update_response = client.put(
            "/api/genai/safety-settings",
            json={
                "allow_application_detail_rows": False,
                "allow_ticket_detail_rows": False,
                "allow_aggregate_ticket_data": True,
                "allow_problem_change_data": True,
                "allow_sla_ola_aggregate_data": True,
                "max_rows_returned_to_llm": 250,
                "max_chart_data_points": 750,
                "enforce_complete_month_cutoff": False,
                "mask_sensitive_fields": True,
            },
        )
        invalid_response = client.put(
            "/api/genai/safety-settings",
            json={"max_rows_returned_to_llm": 0},
        )

    assert default_response.status_code == 200
    defaults = default_response.json()
    assert defaults["allow_application_detail_rows"] is True
    assert defaults["allow_ticket_detail_rows"] is False
    assert defaults["allow_aggregate_ticket_data"] is True
    assert defaults["allow_problem_change_data"] is False
    assert defaults["allow_sla_ola_aggregate_data"] is True
    assert defaults["max_rows_returned_to_llm"] == 100
    assert defaults["max_chart_data_points"] == 500

    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["allow_application_detail_rows"] is False
    assert updated["allow_problem_change_data"] is True
    assert updated["max_rows_returned_to_llm"] == 250
    assert updated["max_chart_data_points"] == 750
    assert updated["enforce_complete_month_cutoff"] is False
    assert invalid_response.status_code == 422


def test_genai_test_endpoint_returns_disabled_response_and_logs_usage() -> None:
    reset_genai_tables()

    with TestClient(app) as client:
        response = client.post("/api/genai/test", json={})
        logs_response = client.get("/api/genai/usage-logs")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is False
    assert "disabled" in payload["error_message"].lower()
    assert usage_log_count() == 1
    assert logs_response.json()[0]["status"] == "disabled"


def test_genai_test_endpoint_returns_missing_model_response() -> None:
    reset_genai_tables()

    with TestClient(app) as client:
        configure_genai(client, model_name="")
        response = client.post("/api/genai/test", json={})

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is False
    assert "Model name" in payload["error_message"]
    assert usage_log_count() == 1


def test_genai_test_endpoint_success_uses_litellm_and_logs_usage(monkeypatch) -> None:
    reset_genai_tables()
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    def fake_completion(**_: Any) -> dict[str, Any]:
        return {
            "choices": [{"message": {"content": "Hello from the AMS GenAI Analytics Workbench."}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 12},
        }

    monkeypatch.setattr("app.services.genai.llm_client.litellm.completion", fake_completion)

    with TestClient(app) as client:
        configure_genai(client)
        response = client.post(
            "/api/genai/test",
            json={"test_prompt": "Say hello from the AMS GenAI Analytics Workbench."},
        )
        logs_response = client.get("/api/genai/usage-logs", params={"operation": "config_test"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["response_text"] == "Hello from the AMS GenAI Analytics Workbench."
    assert payload["usage"]["prompt_tokens"] == 10
    assert payload["usage"]["completion_tokens"] == 12
    logs = logs_response.json()
    assert len(logs) == 1
    assert logs[0]["status"] == "success"
    assert logs[0]["prompt_tokens"] == 10
    assert logs[0]["completion_tokens"] == 12


def test_genai_test_endpoint_failed_litellm_call_returns_clean_error(monkeypatch) -> None:
    reset_genai_tables()
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    def fake_completion(**_: Any) -> dict[str, Any]:
        raise RuntimeError("raw exception with backend details")

    monkeypatch.setattr("app.services.genai.llm_client.litellm.completion", fake_completion)

    with TestClient(app) as client:
        configure_genai(client)
        response = client.post("/api/genai/test", json={})
        logs_response = client.get("/api/genai/usage-logs", params={"status": "error"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is False
    assert "raw exception" not in payload["error_message"]
    assert "model request failed" in payload["error_message"].lower()
    logs = logs_response.json()
    assert len(logs) == 1
    assert "raw exception" not in logs[0]["error_message"]


def test_genai_usage_logs_limit_and_redaction() -> None:
    reset_genai_tables()
    db = SessionLocal()
    try:
        create_usage_log(
            db,
            operation="prompt_test",
            status="success",
            provider="openai",
            model_name="gpt-4.1-mini",
            question="Do not expose normalized_payload or cmdb_payload values.",
            duration_ms=10,
        )
        create_usage_log(
            db,
            operation="config_test",
            status="error",
            provider="openai",
            model_name="gpt-4.1-mini",
            error_message="OPENAI_API_KEY is missing.",
            duration_ms=5,
        )
    finally:
        db.close()

    with TestClient(app) as client:
        response = client.get("/api/genai/usage-logs", params={"limit": 1})

    assert response.status_code == 200
    logs = response.json()
    assert len(logs) == 1
    assert "normalized_payload" not in str(logs)
    assert "cmdb_payload" not in str(logs)
    assert "tools_used_json" in logs[0]
