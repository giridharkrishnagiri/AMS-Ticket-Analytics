from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from typing import Any

import litellm

from app.models import GenAIConfig

logger = logging.getLogger(__name__)

SAFE_DEFAULT_TEST_PROMPT = "Say hello from the AMS GenAI Analytics Workbench."
PROVIDER_API_KEY_ENV: dict[str, str] = {
    "openai": "OPENAI_API_KEY",
    "azure": "AZURE_OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "custom": "LITELLM_API_KEY",
}
GENERIC_FAILURE_MESSAGE = (
    "The model request failed. Check the provider, model name, API key, and network settings."
)


@dataclass(frozen=True)
class LLMCompletionResult:
    ok: bool
    response_text: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    estimated_cost: float | None = None
    duration_ms: int | None = None
    error_message: str | None = None


def provider_model_name(config: GenAIConfig) -> str:
    model_name = (config.model_name or "").strip()
    provider = config.provider.strip().lower()
    if provider == "azure" and not model_name.startswith("azure/"):
        return f"azure/{model_name}"
    if provider == "anthropic" and not model_name.startswith("anthropic/"):
        return f"anthropic/{model_name}"
    if provider == "ollama" and not model_name.startswith("ollama/"):
        return f"ollama/{model_name}"
    return model_name


def missing_api_key_message(provider: str) -> str | None:
    env_key = PROVIDER_API_KEY_ENV.get(provider)
    if env_key and not os.getenv(env_key):
        return f"{env_key} is not configured for the selected provider."
    return None


def value_from_response(source: Any, key: str) -> Any:
    if isinstance(source, dict):
        return source.get(key)
    return getattr(source, key, None)


def response_text(response: Any) -> str | None:
    choices = value_from_response(response, "choices") or []
    if not choices:
        return None
    choice = choices[0]
    message = value_from_response(choice, "message")
    content = value_from_response(message, "content") if message is not None else None
    if content is None:
        content = value_from_response(choice, "text")
    return str(content).strip() if content else None


def usage_token(response: Any, key: str) -> int | None:
    usage = value_from_response(response, "usage")
    token_value = value_from_response(usage, key) if usage is not None else None
    return int(token_value) if token_value is not None else None


def estimated_completion_cost(response: Any) -> float | None:
    try:
        cost = litellm.completion_cost(completion_response=response)
    except Exception:
        return None
    return float(cost) if cost is not None else None


def test_completion(config: GenAIConfig, prompt: str | None = None) -> LLMCompletionResult:
    provider = config.provider.strip().lower()
    missing_key = missing_api_key_message(provider)
    if missing_key:
        return LLMCompletionResult(ok=False, error_message=missing_key)

    request_prompt = (prompt or SAFE_DEFAULT_TEST_PROMPT).strip() or SAFE_DEFAULT_TEST_PROMPT
    started_at = time.perf_counter()
    try:
        response = litellm.completion(
            model=provider_model_name(config),
            messages=[{"role": "user", "content": request_prompt}],
            temperature=config.temperature,
            top_p=config.top_p,
            max_tokens=config.max_output_tokens,
            timeout=config.timeout_seconds,
        )
        duration_ms = int((time.perf_counter() - started_at) * 1000)
        return LLMCompletionResult(
            ok=True,
            response_text=response_text(response),
            prompt_tokens=usage_token(response, "prompt_tokens"),
            completion_tokens=usage_token(response, "completion_tokens"),
            estimated_cost=estimated_completion_cost(response),
            duration_ms=duration_ms,
        )
    except Exception:
        duration_ms = int((time.perf_counter() - started_at) * 1000)
        logger.exception("GenAI LiteLLM test request failed")
        return LLMCompletionResult(
            ok=False,
            duration_ms=duration_ms,
            error_message=GENERIC_FAILURE_MESSAGE,
        )
