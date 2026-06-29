from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, TypedDict

from app.models import GenAIConfig, GenAISafetySettings
from app.services.genai.llm_client import LLMCompletionResult


class GenAIAgentState(TypedDict, total=False):
    session_id: str
    user_message_id: str | None
    customer_id: str | None
    project_id: str | None
    question: str
    context: dict[str, Any]
    chat_history: list[dict[str, str]]
    config: dict[str, Any]
    safety_settings: dict[str, Any]
    prompt_templates: dict[str, str]
    classification: dict[str, Any] | None
    tool_plan: list[dict[str, Any]]
    validated_tool_plan: list[dict[str, Any]]
    answer_strategy: str | None
    tool_results: list[dict[str, Any]]
    answer: str | None
    recommendations: list[str]
    data_notes: list[str]
    warnings: list[str]
    assumptions: list[str]
    tools_used: list[str]
    unsupported: bool
    unsafe: bool
    error_message: str | None
    started_at: str
    usage: dict[str, int | float | None]
    llm_status: str


@dataclass
class GenAIAgentRunResult:
    answer: str
    metadata: dict[str, Any]
    usage: LLMCompletionResult
    status: str
    error_message: str | None = None


@dataclass
class AgentRuntime:
    config: GenAIConfig
    safety_settings: GenAISafetySettings
    prompt_templates: dict[str, str]
    started_at: datetime
    max_tool_calls: int


@dataclass
class LLMUsageAccumulator:
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    estimated_cost: float | None = None
    duration_ms: int | None = None
    errors: list[str] = field(default_factory=list)

    def add(self, result: LLMCompletionResult | None) -> None:
        if result is None:
            return
        self.prompt_tokens = _sum_optional(self.prompt_tokens, result.prompt_tokens)
        self.completion_tokens = _sum_optional(
            self.completion_tokens,
            result.completion_tokens,
        )
        self.estimated_cost = _sum_optional_float(self.estimated_cost, result.estimated_cost)
        self.duration_ms = _sum_optional(self.duration_ms, result.duration_ms)
        if result.error_message:
            self.errors.append(result.error_message)

    def to_completion_result(self, *, ok: bool, response_text: str | None) -> LLMCompletionResult:
        return LLMCompletionResult(
            ok=ok,
            response_text=response_text,
            prompt_tokens=self.prompt_tokens,
            completion_tokens=self.completion_tokens,
            estimated_cost=self.estimated_cost,
            duration_ms=self.duration_ms,
            error_message="; ".join(self.errors) if self.errors else None,
        )


def _sum_optional(left: int | None, right: int | None) -> int | None:
    if left is None:
        return right
    if right is None:
        return left
    return left + right


def _sum_optional_float(left: float | None, right: float | None) -> float | None:
    if left is None:
        return right
    if right is None:
        return left
    return left + right
