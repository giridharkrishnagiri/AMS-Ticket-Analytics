from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.main import app
from app.models import (
    Client,
    GenAIChatMessage,
    GenAIChatSession,
    GenAIConfig,
    GenAIGeneratedChart,
    GenAIPromptTemplate,
    GenAISafetySettings,
    GenAITicketClassification,
    GenAIToolRun,
    GenAIUsageLog,
    Project,
    Ticket,
    UploadBatch,
    UploadedFile,
)
from app.services.genai.default_prompts import DEFAULT_PROMPTS_BY_KEY
from app.services.genai.llm_client import LLMCompletionResult
from app.services.genai.usage_log_service import create_usage_log


def reset_genai_tables() -> None:
    db = SessionLocal()
    try:
        for model in (
            GenAIToolRun,
            GenAIGeneratedChart,
            GenAITicketClassification,
            GenAIUsageLog,
            GenAIChatMessage,
            GenAIChatSession,
            GenAIPromptTemplate,
            GenAISafetySettings,
            GenAIConfig,
        ):
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


def create_chat_session(client: TestClient, **overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "customer_id": None,
        "project_id": None,
        "title": "New chat",
        "metadata": {"domain": "General"},
    }
    payload.update(overrides)
    response = client.post("/api/genai/chat-sessions", json=payload)
    assert response.status_code == 200
    return response.json()


def test_llm_client_applies_system_trust_store_once(monkeypatch) -> None:
    from app.services.genai import llm_client

    calls: list[bool] = []

    def fake_inject_into_ssl() -> None:
        calls.append(True)

    monkeypatch.setattr("truststore.inject_into_ssl", fake_inject_into_ssl)
    monkeypatch.setattr(llm_client, "SYSTEM_TRUST_STORE_APPLIED", False)

    llm_client.apply_system_trust_store()
    llm_client.apply_system_trust_store()

    assert calls == [True]


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


def test_genai_chat_session_lifecycle() -> None:
    reset_genai_tables()

    with TestClient(app) as client:
        created = create_chat_session(client, title="  ", metadata={"domain": "Applications"})
        list_response = client.get("/api/genai/chat-sessions")
        detail_response = client.get(f"/api/genai/chat-sessions/{created['id']}")
        update_response = client.put(
            f"/api/genai/chat-sessions/{created['id']}",
            json={"title": "Renamed session", "metadata": {"domain": "Tickets"}},
        )
        archive_response = client.post(f"/api/genai/chat-sessions/{created['id']}/archive")
        active_list_response = client.get("/api/genai/chat-sessions")
        archived_list_response = client.get(
            "/api/genai/chat-sessions",
            params={"include_archived": True},
        )

    assert created["title"] == "New chat"
    assert created["metadata"] == {"domain": "Applications"}
    assert list_response.status_code == 200
    assert list_response.json()["total"] == 1
    assert detail_response.status_code == 200
    assert detail_response.json()["messages"] == []
    assert update_response.status_code == 200
    assert update_response.json()["title"] == "Renamed session"
    assert update_response.json()["metadata"] == {"domain": "Tickets"}
    assert archive_response.status_code == 200
    assert archive_response.json()["is_archived"] is True
    assert active_list_response.json()["total"] == 0
    assert archived_list_response.json()["total"] == 1


def test_genai_chat_message_success_persists_messages_and_usage(monkeypatch) -> None:
    reset_genai_tables()
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    def fake_classifier(_: Any, __: list[dict[str, str]]) -> LLMCompletionResult:
        return LLMCompletionResult(
            ok=True,
            response_text=(
                '{"category":"general","domain":"general","requires_tools":false,'
                '"confidence":0.9,"reason":"General question."}'
            ),
            prompt_tokens=11,
            completion_tokens=7,
            duration_ms=100,
        )

    def fake_synthesizer(_: Any, __: list[dict[str, str]]) -> LLMCompletionResult:
        return LLMCompletionResult(
            ok=True,
            response_text="The workbench can help configure and test GenAI features.",
            prompt_tokens=20,
            completion_tokens=5,
            estimated_cost=0.001,
            duration_ms=356,
        )

    monkeypatch.setattr("app.services.genai.agent.classifier.chat_completion", fake_classifier)
    monkeypatch.setattr("app.services.genai.agent.synthesizer.chat_completion", fake_synthesizer)

    with TestClient(app) as client:
        configure_genai(client)
        session = create_chat_session(client)
        response = client.post(
            f"/api/genai/chat-sessions/{session['id']}/messages",
            json={
                "content": "What can this GenAI workbench do?",
                "context": {"domain": "General", "page": "Chat"},
            },
        )
        detail_response = client.get(f"/api/genai/chat-sessions/{session['id']}")
        logs_response = client.get("/api/genai/usage-logs", params={"operation": "chat_agent"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["user_message"]["role"] == "user"
    assert payload["assistant_message"]["role"] == "assistant"
    assert payload["assistant_message"]["content"].startswith("The workbench can help")
    assert payload["assistant_message"]["metadata"]["provider"] == "openai"
    assert payload["assistant_message"]["metadata"]["model_name"] == "gpt-4.1-mini"
    assert payload["assistant_message"]["metadata"]["agent_mode"] == "langgraph_governed_tools"
    assert payload["assistant_message"]["metadata"]["data_access"] == "none_general"
    assert payload["assistant_message"]["metadata"]["usage"]["prompt_tokens"] == 31
    assert payload["assistant_message"]["metadata"]["tools_used"] == []
    assert payload["session"]["title"] == "What can this GenAI workbench do?"
    assert payload["session"]["last_message_at"] is not None
    assert len(detail_response.json()["messages"]) == 2
    logs = logs_response.json()
    assert len(logs) == 1
    assert logs[0]["operation"] == "chat_agent"
    assert logs[0]["status"] == "success"
    assert logs[0]["prompt_tokens"] == 31
    assert logs[0]["completion_tokens"] == 12


def test_genai_chat_disabled_and_missing_model_return_clean_messages() -> None:
    reset_genai_tables()

    with TestClient(app) as client:
        disabled_session = create_chat_session(client)
        disabled_response = client.post(
            f"/api/genai/chat-sessions/{disabled_session['id']}/messages",
            json={"content": "Hello"},
        )
        configure_genai(client, model_name="")
        missing_model_session = create_chat_session(client)
        missing_model_response = client.post(
            f"/api/genai/chat-sessions/{missing_model_session['id']}/messages",
            json={"content": "Hello again"},
        )
        logs_response = client.get("/api/genai/usage-logs", params={"operation": "chat_agent"})

    assert disabled_response.status_code == 200
    disabled_payload = disabled_response.json()
    assert "disabled" in disabled_payload["assistant_message"]["content"].lower()
    assert disabled_payload["assistant_message"]["metadata"]["status"] == "disabled"
    assert missing_model_response.status_code == 200
    missing_payload = missing_model_response.json()
    assert "Model name" in missing_payload["assistant_message"]["content"]
    assert missing_payload["assistant_message"]["metadata"]["status"] == "error"
    statuses = {row["status"] for row in logs_response.json()}
    assert {"disabled", "error"} <= statuses


def test_genai_chat_litellm_failure_stores_error_and_usage(monkeypatch) -> None:
    reset_genai_tables()
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    def fake_completion(**_: Any) -> dict[str, Any]:
        raise RuntimeError("raw provider exception")

    monkeypatch.setattr("app.services.genai.llm_client.litellm.completion", fake_completion)

    with TestClient(app) as client:
        configure_genai(client)
        session = create_chat_session(client)
        response = client.post(
            f"/api/genai/chat-sessions/{session['id']}/messages",
            json={"content": "What can this GenAI workbench do?"},
        )
        logs_response = client.get("/api/genai/usage-logs", params={"operation": "chat_agent"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["assistant_message"]["metadata"]["status"] == "error"
    assert "raw provider exception" not in payload["assistant_message"]["content"]
    assert "workbench" in payload["assistant_message"]["content"].lower()
    assert logs_response.json()[0]["status"] == "error"
    assert "raw provider exception" not in str(logs_response.json())


def test_genai_chat_rejects_blank_and_archived_messages() -> None:
    reset_genai_tables()

    with TestClient(app) as client:
        session = create_chat_session(client)
        blank_response = client.post(
            f"/api/genai/chat-sessions/{session['id']}/messages",
            json={"content": "   "},
        )
        client.post(f"/api/genai/chat-sessions/{session['id']}/archive")
        archived_response = client.post(
            f"/api/genai/chat-sessions/{session['id']}/messages",
            json={"content": "Hello after archive"},
        )

    assert blank_response.status_code == 400
    assert "required" in blank_response.json()["detail"].lower()
    assert archived_response.status_code == 400
    assert "archived" in archived_response.json()["detail"].lower()


def test_genai_chat_context_endpoints_return_compact_options() -> None:
    reset_genai_tables()
    db = SessionLocal()
    suffix = uuid4().hex[:8].upper()
    customer_code = f"GENAI_CTX_{suffix}"
    project_code = f"GENAI_CTX_PROJECT_{suffix}"
    client_row = Client(name="GenAI Test Customer", code=customer_code, is_active=True)
    db.add(client_row)
    db.flush()
    project_row = Project(
        client_id=client_row.id,
        name="GenAI Test Project",
        code=project_code,
        is_active=True,
    )
    db.add(project_row)
    db.commit()
    client_id = str(client_row.id)
    project_id = str(project_row.id)
    try:
        with TestClient(app) as client:
            customers_response = client.get("/api/genai/context/customers")
            projects_response = client.get(
                "/api/genai/context/projects",
                params={"customer_id": str(client_row.id)},
            )
    finally:
        db.delete(project_row)
        db.delete(client_row)
        db.commit()
        db.close()

    assert customers_response.status_code == 200
    customers = customers_response.json()
    assert any(row["id"] == client_id for row in customers)
    assert "description" not in customers[0]
    assert projects_response.status_code == 200
    projects = projects_response.json()
    assert projects == [
        {
            "id": project_id,
            "name": "GenAI Test Project",
            "code": project_code,
            "customer_id": client_id,
            "customer_name": "GenAI Test Customer",
            "customer_code": customer_code,
            "label": "GenAI Test Customer - GenAI Test Project",
        },
    ]


def test_genai_chat_data_specific_question_uses_governed_tool_metadata(
    monkeypatch,
) -> None:
    reset_genai_tables()
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    def fake_invalid_json(_: Any, __: list[dict[str, str]]) -> LLMCompletionResult:
        return LLMCompletionResult(
            ok=True,
            response_text="not json",
            prompt_tokens=10,
            completion_tokens=3,
            duration_ms=25,
        )

    def fake_synthesizer(_: Any, __: list[dict[str, str]]) -> LLMCompletionResult:
        return LLMCompletionResult(
            ok=True,
            response_text="The governed ticket tool returned the top application volume summary.",
            prompt_tokens=44,
            completion_tokens=19,
            duration_ms=321,
        )

    monkeypatch.setattr("app.services.genai.agent.classifier.chat_completion", fake_invalid_json)
    monkeypatch.setattr("app.services.genai.agent.planner.chat_completion", fake_invalid_json)
    monkeypatch.setattr("app.services.genai.agent.synthesizer.chat_completion", fake_synthesizer)

    with TestClient(app) as client:
        configure_genai(client)
        session = create_chat_session(client, metadata={"domain": "Tickets"})
        response = client.post(
            f"/api/genai/chat-sessions/{session['id']}/messages",
            json={
                "content": "Which applications have the highest ticket volume?",
                "context": {"domain": "Tickets", "page": "Chat"},
            },
        )

    assert response.status_code == 200
    payload = response.json()
    metadata = payload["assistant_message"]["metadata"]
    assert metadata["data_access"] == "governed_tools"
    assert metadata["tools_used"] == ["get_top_applications_by_ticket_volume"]
    assert metadata["tool_results_summary"][0]["tool_name"] == (
        "get_top_applications_by_ticket_volume"
    )
    assert "normalized_payload" not in str(payload)
    assert "cmdb_payload" not in str(payload)


def create_ticket_classification_project() -> tuple[UUID, UUID, UUID, UUID, str]:
    db = SessionLocal()
    suffix = uuid4().hex[:12]
    try:
        client_row = Client(name=f"Classification Client {suffix}", code=f"CLS-C-{suffix}")
        db.add(client_row)
        db.flush()

        project = Project(
            client_id=client_row.id,
            name=f"Classification Project {suffix}",
            code=f"CLS-P-{suffix}",
        )
        db.add(project)
        db.flush()

        upload_batch = UploadBatch(
            project_id=project.id,
            month_key="2026-05",
            batch_name=f"Classification Batch {suffix}",
            status="NORMALIZED",
            file_count=1,
            total_size_bytes=1,
        )
        db.add(upload_batch)
        db.flush()

        uploaded_file = UploadedFile(
            upload_batch_id=upload_batch.id,
            project_id=project.id,
            ticket_type="INCIDENT",
            original_filename="classification.csv",
            saved_filename="classification.csv",
            storage_path="C:\\temp\\classification.csv",
            size_bytes=1,
            status="NORMALIZED",
        )
        db.add(uploaded_file)
        db.flush()
        db.commit()
        return (
            client_row.id,
            project.id,
            upload_batch.id,
            uploaded_file.id,
            suffix,
        )
    finally:
        db.close()


def cleanup_classification_client(client_id: UUID) -> None:
    db = SessionLocal()
    try:
        db.execute(delete(Client).where(Client.id == client_id))
        db.commit()
    finally:
        db.close()


def add_classification_ticket(
    *,
    project_id: UUID,
    upload_batch_id: UUID,
    uploaded_file_id: UUID,
    ticket_number: str,
    ticket_type: str,
    state: str,
    resolved_at: datetime | None = None,
    closed_at: datetime | None = None,
    is_in_scope: bool = True,
) -> None:
    db = SessionLocal()
    try:
        db.add(
            Ticket(
                project_id=project_id,
                upload_batch_id=upload_batch_id,
                uploaded_file_id=uploaded_file_id,
                ticket_number=ticket_number,
                ticket_type=ticket_type,
                is_in_scope=is_in_scope,
                month_key="2026-05",
                created_at=datetime(2026, 5, 1, tzinfo=UTC),
                resolved_at=resolved_at,
                closed_at=closed_at,
                short_description=f"{ticket_number} short description",
                description=f"{ticket_number} detailed description",
                state=state,
                priority="P3",
                assignment_group="AMS Support",
                category="Access",
                subcategory="User",
                catalog_item_name=(
                    "General Service Request"
                    if ticket_type == "SERVICE_CATALOG_TASK"
                    else None
                ),
                reopen_count=0,
            ),
        )
        db.commit()
    finally:
        db.close()


def test_ticket_classification_enrichment_filters_caches_pivots_and_clears(monkeypatch) -> None:
    reset_genai_tables()
    monkeypatch.setenv("GENAI_TICKET_CLASSIFICATION_MODEL_NAME", "gpt-ticket-classifier-test")
    monkeypatch.setenv("GENAI_TICKET_CLASSIFICATION_MAX_OUTPUT_TOKENS", "4000")
    get_settings.cache_clear()
    client_id, project_id, upload_batch_id, uploaded_file_id, _suffix = (
        create_ticket_classification_project()
    )
    project_id_text = str(project_id)
    try:
        may_5 = datetime(2026, 5, 5, 12, 0, tzinfo=UTC)
        may_6 = datetime(2026, 5, 6, 12, 0, tzinfo=UTC)
        may_7 = datetime(2026, 5, 7, 12, 0, tzinfo=UTC)
        may_8 = datetime(2026, 5, 8, 12, 0, tzinfo=UTC)

        add_classification_ticket(
            project_id=project_id,
            upload_batch_id=upload_batch_id,
            uploaded_file_id=uploaded_file_id,
            ticket_number="INC-CLASSIFY",
            ticket_type="INCIDENT",
            state="Resolved",
            resolved_at=may_5,
        )
        add_classification_ticket(
            project_id=project_id,
            upload_batch_id=upload_batch_id,
            uploaded_file_id=uploaded_file_id,
            ticket_number="INC-CANCELED",
            ticket_type="INCIDENT",
            state="Canceled",
            resolved_at=may_6,
        )
        add_classification_ticket(
            project_id=project_id,
            upload_batch_id=upload_batch_id,
            uploaded_file_id=uploaded_file_id,
            ticket_number="SCTASK-CLASSIFY",
            ticket_type="SERVICE_CATALOG_TASK",
            state="Closed Complete",
            closed_at=may_7,
        )
        add_classification_ticket(
            project_id=project_id,
            upload_batch_id=upload_batch_id,
            uploaded_file_id=uploaded_file_id,
            ticket_number="SCTASK-INCOMPLETE",
            ticket_type="SERVICE_CATALOG_TASK",
            state="Closed Incomplete",
            closed_at=may_8,
        )
        add_classification_ticket(
            project_id=project_id,
            upload_batch_id=upload_batch_id,
            uploaded_file_id=uploaded_file_id,
            ticket_number="INC-OUT-SCOPE",
            ticket_type="INCIDENT",
            state="Resolved",
            resolved_at=may_5,
            is_in_scope=False,
        )

        received_ticket_numbers: list[str] = []
        model_names_seen: list[str | None] = []
        max_output_tokens_seen: list[int] = []

        def fake_chat_completion(_config, messages):
            model_names_seen.append(_config.model_name)
            max_output_tokens_seen.append(_config.max_output_tokens)
            payload = json.loads(messages[1]["content"].split("\n", 1)[1])
            ticket_rows = payload["tickets"]
            received_ticket_numbers.extend(row["ticket_number"] for row in ticket_rows)
            return LLMCompletionResult(
                ok=True,
                response_text=json.dumps(
                    {
                        "tickets": [
                            {
                                "ticket_number": row["ticket_number"],
                                "category_quality": "Meaningful",
                                "genai_category": (
                                    "Access Issue"
                                    if row["ticket_type"] == "INCIDENT"
                                    else "User Administration"
                                ),
                                "genai_subcategory_1": (
                                    "Login Support"
                                    if row["ticket_type"] == "INCIDENT"
                                    else "New User"
                                ),
                                "genai_subcategory_2": None,
                                "confidence": 0.92,
                            }
                            for row in ticket_rows
                        ],
                    },
                ),
                prompt_tokens=20,
                completion_tokens=30,
                estimated_cost=0.001,
                duration_ms=15,
            )

        monkeypatch.setattr(
            "app.services.genai.ticket_classification.chat_completion",
            fake_chat_completion,
        )

        with TestClient(app) as client:
            configure_genai(client)
            run_id = "test-ticket-classification-progress-run"
            run_response = client.post(
                "/api/genai/ticket-classification/run",
                json={
                    "project_id": project_id_text,
                    "analysis_month": "2026-05",
                    "batch_size": 1,
                    "batch_limit": 1,
                    "run_id": run_id,
                },
            )
            assert run_response.status_code == 200
            run_payload = run_response.json()
            assert run_payload["eligible_ticket_count"] == 2
            assert run_payload["processed_count"] == 1
            assert run_payload["failed_count"] == 0
            assert run_payload["remaining_ticket_count"] == 1
            assert run_payload["processed_batch_count"] == 1
            assert run_payload["total_batch_count"] == 2
            assert run_payload["usage_run"]["model_name"] == "gpt-ticket-classifier-test"
            assert run_payload["usage_run"]["prompt_tokens"] == 20
            assert run_payload["usage_run"]["completion_tokens"] == 30
            assert run_payload["usage_run"]["total_tokens"] == 50
            assert run_payload["usage_run"]["estimated_cost"] == 0.001
            assert run_payload["usage_run"]["ticket_count"] == 1
            assert received_ticket_numbers == ["INC-CLASSIFY"]
            assert model_names_seen == ["gpt-ticket-classifier-test"]
            assert max_output_tokens_seen == [4000]

            second_run_response = client.post(
                "/api/genai/ticket-classification/run",
                json={
                    "project_id": project_id_text,
                    "analysis_month": "2026-05",
                    "batch_size": 1,
                    "batch_limit": 1,
                    "run_id": run_id,
                },
            )
            assert second_run_response.status_code == 200
            second_run_payload = second_run_response.json()
            assert second_run_payload["processed_count"] == 1
            assert second_run_payload["remaining_ticket_count"] == 0
            assert second_run_payload["usage_run"]["run_id"] == run_id
            assert second_run_payload["usage_run"]["prompt_tokens"] == 40
            assert second_run_payload["usage_run"]["completion_tokens"] == 60
            assert second_run_payload["usage_run"]["total_tokens"] == 100
            assert second_run_payload["usage_run"]["estimated_cost"] == 0.002
            assert second_run_payload["usage_run"]["ticket_count"] == 2
            assert set(received_ticket_numbers) == {"INC-CLASSIFY", "SCTASK-CLASSIFY"}
            assert model_names_seen == [
                "gpt-ticket-classifier-test",
                "gpt-ticket-classifier-test",
            ]
            assert max_output_tokens_seen == [4000, 4000]

            cached_response = client.post(
                "/api/genai/ticket-classification/run",
                json={
                    "project_id": project_id_text,
                    "analysis_month": "2026-05",
                    "batch_size": 1,
                    "batch_limit": 1,
                },
            )
            assert cached_response.status_code == 200
            assert cached_response.json()["skipped_cached_count"] == 2
            assert cached_response.json()["processed_batch_count"] == 0

            pivot_response = client.get(
                "/api/genai/ticket-classification/pivot",
                params={"project_id": project_id_text, "analysis_month": "2026-05"},
            )
            assert pivot_response.status_code == 200
            pivot_rows = pivot_response.json()["rows"]
            assert {row["genai_category"] for row in pivot_rows} == {
                "Access Issue",
                "User Administration",
            }

            usage_response = client.get(
                "/api/genai/ticket-classification/usage-runs",
                params={"project_id": project_id_text, "analysis_month": "2026-05"},
            )
            assert usage_response.status_code == 200
            usage_runs = usage_response.json()["runs"]
            assert len(usage_runs) == 1
            assert usage_runs[0]["model_name"] == "gpt-ticket-classifier-test"
            assert usage_runs[0]["prompt_tokens"] == 40
            assert usage_runs[0]["completion_tokens"] == 60
            assert usage_runs[0]["estimated_cost"] == 0.002

            clear_response = client.post(
                "/api/genai/ticket-classification/clear",
                json={"project_id": project_id_text, "analysis_month": "2026-05"},
            )
            assert clear_response.status_code == 200
            assert clear_response.json()["deleted_count"] == 2

            summary_response = client.get(
                "/api/genai/ticket-classification/summary",
                params={"project_id": project_id_text, "analysis_month": "2026-05"},
            )
            assert summary_response.status_code == 200
            assert summary_response.json()["analyzed_ticket_count"] == 0

        db = SessionLocal()
        try:
            remaining = db.execute(
                select(GenAITicketClassification).where(
                    GenAITicketClassification.project_id == project_id,
                ),
            ).scalars().all()
            assert remaining == []
        finally:
            db.close()
    finally:
        cleanup_classification_client(client_id)
        get_settings.cache_clear()
