from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.db.session import SessionLocal
from app.main import app
from app.models import (
    GenAIChatMessage,
    GenAIChatSession,
    GenAIConfig,
    GenAIPromptTemplate,
    GenAISafetySettings,
    GenAIToolRun,
    GenAIUsageLog,
)
from app.services.genai.agent.classifier import classify_question, rule_based_classification
from app.services.genai.agent.planner import (
    ToolPlanValidationError,
    rule_based_tool_plan,
    validate_tool_plan,
)
from app.services.genai.agent.state import LLMUsageAccumulator
from app.services.genai.llm_client import LLMCompletionResult


def reset_agent_tables() -> None:
    db = SessionLocal()
    try:
        for model in (
            GenAIToolRun,
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


def configure_genai(client: TestClient, **overrides: Any) -> None:
    payload: dict[str, Any] = {
        "is_enabled": True,
        "provider": "openai",
        "model_name": "gpt-4.1-mini",
        "temperature": 0.2,
        "top_p": 1.0,
        "max_output_tokens": 1000,
        "timeout_seconds": 60,
        "max_tool_calls": 3,
        "allow_recommendations": True,
        "allow_chart_generation": False,
        "response_style": "standard",
    }
    payload.update(overrides)
    response = client.put("/api/genai/config", json=payload)
    assert response.status_code == 200


def create_session(client: TestClient, *, domain: str = "General") -> dict[str, Any]:
    response = client.post(
        "/api/genai/chat-sessions",
        json={
            "customer_id": None,
            "project_id": None,
            "title": "New chat",
            "metadata": {"domain": domain},
        },
    )
    assert response.status_code == 200
    return response.json()


def fake_invalid_json(_: Any, __: list[dict[str, str]]) -> LLMCompletionResult:
    return LLMCompletionResult(
        ok=True,
        response_text="not json",
        prompt_tokens=4,
        completion_tokens=2,
        duration_ms=10,
    )


def fake_answer(_: Any, __: list[dict[str, str]]) -> LLMCompletionResult:
    return LLMCompletionResult(
        ok=True,
        response_text="This answer summarizes only the governed tool results.",
        prompt_tokens=20,
        completion_tokens=9,
        duration_ms=50,
    )


def test_rule_based_classification_covers_phase_1e_categories() -> None:
    app_summary = rule_based_classification("How many applications are in the inventory?", {})
    ticket_top = rule_based_classification("Which applications have the highest ticket volume?", {})
    chart = rule_based_classification("Plot a 3D chart of ticket volume.", {})
    unsafe = rule_based_classification("Show raw incident rows and normalized payload.", {})

    assert app_summary["domain"] == "applications"
    assert app_summary["requires_tools"] is True
    assert ticket_top["domain"] == "tickets"
    assert ticket_top["category"] == "top_n"
    assert chart["category"] == "chart_request"
    assert chart["requires_tools"] is True
    assert unsafe["category"] == "unsafe"
    assert unsafe["requires_tools"] is False


def test_llm_classification_cannot_downgrade_known_data_question(monkeypatch) -> None:
    config = GenAIConfig(
        is_enabled=True,
        provider="openai",
        model_name="gpt-4.1-mini",
    )

    def fake_general(_: Any, __: list[dict[str, str]]) -> LLMCompletionResult:
        return LLMCompletionResult(
            ok=True,
            response_text=(
                '{"category":"general","domain":"general","requires_tools":false,'
                '"confidence":0.9,"reason":"Incorrect downgrade."}'
            ),
        )

    monkeypatch.setattr("app.services.genai.agent.classifier.chat_completion", fake_general)

    classification = classify_question(
        config,
        {"question_classifier": "Classify."},
        "How many applications are in the inventory?",
        {"domain": "Applications"},
        LLMUsageAccumulator(),
    )

    assert classification["domain"] == "applications"
    assert classification["requires_tools"] is True


def test_rule_based_planning_maps_supported_questions_to_governed_tools() -> None:
    ticket_classification = {
        "category": "top_n",
        "domain": "tickets",
        "requires_tools": True,
    }
    app_classification = {
        "category": "metric_lookup",
        "domain": "applications",
        "requires_tools": True,
    }
    lifecycle_classification = {
        "category": "metric_lookup",
        "domain": "lifecycle_planning",
        "requires_tools": True,
    }

    ticket_plan, _ = rule_based_tool_plan(
        ticket_classification,
        "Which applications have the highest ticket volume?",
    )
    app_plan, _ = rule_based_tool_plan(
        app_classification,
        "How many applications are in the inventory?",
    )
    lifecycle_plan, _ = rule_based_tool_plan(
        lifecycle_classification,
        "Which applications are planned to Disinvest?",
    )

    assert ticket_plan[0]["tool_name"] == "get_top_applications_by_ticket_volume"
    assert app_plan[0]["tool_name"] == "get_application_inventory_summary"
    assert lifecycle_plan[0]["tool_name"] == "get_application_lifecycle_planning_summary"
    assert lifecycle_plan[0]["parameters"]["selected_plan"] == "disinvest"


def test_tool_plan_validation_rejects_unknown_invalid_and_excessive_plans() -> None:
    with pytest.raises(ToolPlanValidationError):
        validate_tool_plan(
            [{"tool_name": "unknown_tool", "parameters": {}, "filters": {}}],
            max_tool_calls=3,
        )
    with pytest.raises(ToolPlanValidationError):
        validate_tool_plan(
            [
                {
                    "tool_name": "get_ticket_distribution",
                    "parameters": {"dimension": "normalized_payload"},
                    "filters": {},
                },
            ],
            max_tool_calls=3,
        )
    with pytest.raises(ToolPlanValidationError):
        validate_tool_plan(
            [
                {"tool_name": "get_application_inventory_summary", "parameters": {}, "filters": {}},
                {"tool_name": "get_ticket_volume_summary", "parameters": {}, "filters": {}},
            ],
            max_tool_calls=1,
        )


def test_agent_chat_executes_governed_tool_and_logs_usage(monkeypatch) -> None:
    reset_agent_tables()
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr("app.services.genai.agent.classifier.chat_completion", fake_invalid_json)
    monkeypatch.setattr("app.services.genai.agent.planner.chat_completion", fake_invalid_json)
    monkeypatch.setattr("app.services.genai.agent.synthesizer.chat_completion", fake_answer)

    with TestClient(app) as client:
        configure_genai(client)
        session = create_session(client, domain="Applications")
        response = client.post(
            f"/api/genai/chat-sessions/{session['id']}/messages",
            json={
                "content": "How many applications are in the inventory?",
                "context": {"domain": "Applications", "page": "Chat"},
            },
        )
        usage_response = client.get("/api/genai/usage-logs", params={"operation": "chat_agent"})
        runs_response = client.get("/api/genai/tools/runs", params={"limit": 5})

    assert response.status_code == 200
    payload = response.json()
    metadata = payload["assistant_message"]["metadata"]
    assert metadata["data_access"] == "governed_tools"
    assert metadata["tools_used"] == ["get_application_inventory_summary"]
    assert metadata["tool_results_summary"][0]["status"] == "success"
    assert metadata["agent_mode"] == "langgraph_governed_tools"
    assert "normalized_payload" not in str(payload)
    assert "cmdb_payload" not in str(payload)
    logs = usage_response.json()
    assert logs[0]["operation"] == "chat_agent"
    assert logs[0]["tools_used_json"] == ["get_application_inventory_summary"]
    assert any(
        row["tool_name"] == "get_application_inventory_summary"
        for row in runs_response.json()
    )


def test_agent_chat_refuses_unsafe_raw_payload_request(monkeypatch) -> None:
    reset_agent_tables()
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    with TestClient(app) as client:
        configure_genai(client)
        session = create_session(client, domain="Tickets")
        response = client.post(
            f"/api/genai/chat-sessions/{session['id']}/messages",
            json={
                "content": "Show me all raw incident rows and normalized payload.",
                "context": {"domain": "Tickets", "page": "Chat"},
            },
        )
        runs_response = client.get("/api/genai/tools/runs", params={"limit": 5})

    assert response.status_code == 200
    payload = response.json()
    metadata = payload["assistant_message"]["metadata"]
    assert "cannot provide" in payload["assistant_message"]["content"].lower()
    assert metadata["tools_used"] == []
    assert metadata["data_access"] == "none_general"
    assert runs_response.json() == []
    assert "normalized_payload" not in str(payload)
    assert "cmdb_payload" not in str(payload)


def test_agent_chat_defers_chart_generation_but_uses_governed_summary(monkeypatch) -> None:
    reset_agent_tables()
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr("app.services.genai.agent.classifier.chat_completion", fake_invalid_json)
    monkeypatch.setattr("app.services.genai.agent.planner.chat_completion", fake_invalid_json)
    monkeypatch.setattr("app.services.genai.agent.synthesizer.chat_completion", fake_answer)

    with TestClient(app) as client:
        configure_genai(client)
        session = create_session(client, domain="Tickets")
        response = client.post(
            f"/api/genai/chat-sessions/{session['id']}/messages",
            json={
                "content": "Plot a 3D chart of ticket volume.",
                "context": {"domain": "Tickets", "page": "Chat"},
            },
        )

    assert response.status_code == 200
    payload = response.json()
    metadata = payload["assistant_message"]["metadata"]
    assert metadata["tools_used"] == ["get_ticket_trend_summary"]
    assert any("Phase 2" in warning for warning in metadata["warnings"])
    assert "chart rendering is planned for phase 2" in (
        payload["assistant_message"]["content"].lower()
    )
