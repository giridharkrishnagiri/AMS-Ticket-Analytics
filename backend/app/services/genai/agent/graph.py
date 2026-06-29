from __future__ import annotations

from datetime import UTC, datetime
from time import perf_counter
from typing import Any

from langgraph.graph import END, StateGraph
from sqlalchemy.orm import Session

from app.models import GenAIChatMessage, GenAIChatSession
from app.services.genai.agent.classifier import classify_question
from app.services.genai.agent.executor import execute_validated_plan
from app.services.genai.agent.guardrails import guardrail_metadata
from app.services.genai.agent.planner import (
    ToolPlanValidationError,
    plan_tools,
    validate_tool_plan,
)
from app.services.genai.agent.state import (
    AgentRuntime,
    GenAIAgentRunResult,
    GenAIAgentState,
    LLMUsageAccumulator,
)
from app.services.genai.agent.synthesizer import synthesize_answer
from app.services.genai.config_service import get_or_create_config
from app.services.genai.llm_client import LLMCompletionResult
from app.services.genai.prompt_service import get_active_prompt_text
from app.services.genai.safety_service import get_or_create_safety_settings
from app.services.genai.tools.registry import list_tools

PROMPT_KEYS = (
    "system_domain_rules",
    "question_classifier",
    "tool_planner",
    "answer_summarizer",
    "recommendation_generator",
    "safety_guardrails",
)


def _context_value(context: dict[str, Any], key: str, fallback: Any) -> Any:
    value = context.get(key)
    return value if value not in (None, "") else fallback


def _message_history(messages: list[GenAIChatMessage]) -> list[dict[str, str]]:
    history: list[dict[str, str]] = []
    for message in messages[-12:]:
        if message.role not in {"user", "assistant"}:
            continue
        history.append({"role": message.role, "content": message.content})
    return history


def _runtime(db: Session) -> AgentRuntime:
    config = get_or_create_config(db)
    prompts = {key: get_active_prompt_text(db, key) for key in PROMPT_KEYS}
    return AgentRuntime(
        config=config,
        safety_settings=get_or_create_safety_settings(db),
        prompt_templates=prompts,
        started_at=datetime.now(UTC),
        max_tool_calls=max(0, min(config.max_tool_calls, 3)),
    )


def _collect_result_summaries(tool_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "tool_name": result.get("tool_name"),
            "status": result.get("status"),
            "row_count": result.get("row_count"),
            "truncated": result.get("truncated"),
        }
        for result in tool_results
    ]


def _assistant_metadata(
    *,
    runtime: AgentRuntime,
    state: GenAIAgentState,
    usage: LLMCompletionResult,
    wall_duration_ms: int,
    status: str,
    error_message: str | None,
) -> dict[str, Any]:
    tool_results = state.get("tool_results", [])
    tools_used = state.get("tools_used", [])
    return {
        "provider": runtime.config.provider,
        "model_name": runtime.config.model_name,
        "duration_ms": wall_duration_ms,
        "usage": {
            "prompt_tokens": usage.prompt_tokens,
            "completion_tokens": usage.completion_tokens,
            "estimated_cost": usage.estimated_cost,
        },
        "classification": state.get("classification"),
        "tools_used": tools_used,
        "tool_results_summary": _collect_result_summaries(tool_results),
        "tool_results": tool_results,
        "data_notes": state.get("data_notes", []),
        "warnings": state.get("warnings", []),
        "assumptions": state.get("assumptions", []),
        "recommendations": state.get("recommendations", []),
        "data_access": "governed_tools" if tools_used else "none_general",
        "agent_mode": "langgraph_governed_tools",
        "status": status,
        "error_message": error_message,
        "context": state.get("context", {}),
    }


def run_governed_chat_agent(
    db: Session,
    *,
    session: GenAIChatSession,
    user_message: GenAIChatMessage,
    context: dict[str, Any],
    history: list[GenAIChatMessage],
) -> GenAIAgentRunResult:
    runtime = _runtime(db)
    usage = LLMUsageAccumulator()
    catalog = list_tools()
    started = perf_counter()

    def apply_guardrails(state: GenAIAgentState) -> GenAIAgentState:
        classification = guardrail_metadata(state["question"])
        if classification is None:
            return {
                "unsafe": False,
                "unsupported": False,
                "warnings": state.get("warnings", []),
            }
        return {
            "classification": classification,
            "unsafe": classification["category"] == "unsafe",
            "unsupported": classification["category"] == "unsupported",
            "warnings": [classification["reason"]],
        }

    def classify(state: GenAIAgentState) -> GenAIAgentState:
        if state.get("classification"):
            return {}
        classification = classify_question(
            runtime.config,
            runtime.prompt_templates,
            state["question"],
            state.get("context", {}),
            usage,
        )
        return {
            "classification": classification,
            "unsupported": classification["category"] == "unsupported",
            "unsafe": classification["category"] == "unsafe",
        }

    def plan(state: GenAIAgentState) -> GenAIAgentState:
        classification = state.get("classification") or {}
        planned, answer_strategy = plan_tools(
            runtime.config,
            runtime.prompt_templates,
            state["question"],
            state.get("context", {}),
            classification,
            catalog,
            usage,
        )
        return {"tool_plan": planned, "answer_strategy": answer_strategy}

    def validate(state: GenAIAgentState) -> GenAIAgentState:
        try:
            validated = validate_tool_plan(
                state.get("tool_plan", []),
                max_tool_calls=runtime.max_tool_calls,
            )
        except ToolPlanValidationError as exc:
            return {
                "validated_tool_plan": [],
                "unsupported": True,
                "warnings": [*state.get("warnings", []), str(exc)],
            }
        return {"validated_tool_plan": validated}

    def execute(state: GenAIAgentState) -> GenAIAgentState:
        context_json = state.get("context", {})
        tool_results, data_notes, warnings, tools_used = execute_validated_plan(
            db,
            plan=state.get("validated_tool_plan", []),
            customer_id=_context_value(context_json, "customer_id", session.customer_id),
            project_id=_context_value(context_json, "project_id", session.project_id),
        )
        assumptions = [
            "The answer uses approved governed analytics tools only.",
            "No free-form SQL or raw row access was used.",
        ]
        if context_json.get("domain"):
            assumptions.append(f"Workbench domain context: {context_json['domain']}.")
        return {
            "tool_results": tool_results,
            "data_notes": data_notes,
            "warnings": [*state.get("warnings", []), *warnings],
            "tools_used": tools_used,
            "assumptions": assumptions,
        }

    def synthesize(state: GenAIAgentState) -> GenAIAgentState:
        assumptions = state.get("assumptions", [])
        if not assumptions and not state.get("tools_used"):
            assumptions = ["Answered as a general GenAI workbench question."]
        answer, recommendations, warnings, error_message = synthesize_answer(
            runtime.config,
            runtime.prompt_templates,
            question=state["question"],
            classification=state.get("classification") or {},
            context=state.get("context", {}),
            tool_results=state.get("tool_results", []),
            data_notes=state.get("data_notes", []),
            warnings=state.get("warnings", []),
            assumptions=assumptions,
            usage=usage,
        )
        return {
            "answer": answer,
            "recommendations": recommendations,
            "assumptions": assumptions,
            "warnings": warnings,
            "error_message": error_message,
        }

    def route_after_classify(state: GenAIAgentState) -> str:
        classification = state.get("classification") or {}
        if state.get("unsafe") or state.get("unsupported"):
            return "synthesize_answer"
        if classification.get("requires_tools"):
            return "plan_tools"
        return "synthesize_answer"

    def route_after_validate(state: GenAIAgentState) -> str:
        if state.get("unsupported") or not state.get("validated_tool_plan"):
            return "synthesize_answer"
        return "execute_tools"

    graph = StateGraph(GenAIAgentState)
    graph.add_node("apply_guardrails", apply_guardrails)
    graph.add_node("classify_question", classify)
    graph.add_node("plan_tools", plan)
    graph.add_node("validate_tool_plan", validate)
    graph.add_node("execute_tools", execute)
    graph.add_node("synthesize_answer", synthesize)
    graph.set_entry_point("apply_guardrails")
    graph.add_edge("apply_guardrails", "classify_question")
    graph.add_conditional_edges(
        "classify_question",
        route_after_classify,
        {"plan_tools": "plan_tools", "synthesize_answer": "synthesize_answer"},
    )
    graph.add_edge("plan_tools", "validate_tool_plan")
    graph.add_conditional_edges(
        "validate_tool_plan",
        route_after_validate,
        {"execute_tools": "execute_tools", "synthesize_answer": "synthesize_answer"},
    )
    graph.add_edge("execute_tools", "synthesize_answer")
    graph.add_edge("synthesize_answer", END)

    initial_state: GenAIAgentState = {
        "session_id": str(session.id),
        "user_message_id": str(user_message.id),
        "customer_id": str(_context_value(context, "customer_id", session.customer_id))
        if _context_value(context, "customer_id", session.customer_id)
        else None,
        "project_id": str(_context_value(context, "project_id", session.project_id))
        if _context_value(context, "project_id", session.project_id)
        else None,
        "question": user_message.content,
        "context": context,
        "chat_history": _message_history(history),
        "tool_plan": [],
        "validated_tool_plan": [],
        "tool_results": [],
        "data_notes": [],
        "warnings": [],
        "assumptions": [],
        "tools_used": [],
        "recommendations": [],
        "unsupported": False,
        "unsafe": False,
        "started_at": runtime.started_at.isoformat(),
    }
    final_state = graph.compile().invoke(initial_state)
    wall_duration_ms = int((perf_counter() - started) * 1000)
    ok = not bool(final_state.get("error_message"))
    status = "success" if ok else "error"
    usage_result = usage.to_completion_result(
        ok=ok,
        response_text=final_state.get("answer"),
    )
    usage_result = LLMCompletionResult(
        ok=usage_result.ok,
        response_text=usage_result.response_text,
        prompt_tokens=usage_result.prompt_tokens,
        completion_tokens=usage_result.completion_tokens,
        estimated_cost=usage_result.estimated_cost,
        duration_ms=wall_duration_ms,
        error_message=usage_result.error_message,
    )
    metadata = _assistant_metadata(
        runtime=runtime,
        state=final_state,
        usage=usage_result,
        wall_duration_ms=wall_duration_ms,
        status=status,
        error_message=final_state.get("error_message"),
    )
    return GenAIAgentRunResult(
        answer=str(final_state.get("answer") or "The GenAI agent could not produce an answer."),
        metadata=metadata,
        usage=usage_result,
        status=status,
        error_message=final_state.get("error_message"),
    )
