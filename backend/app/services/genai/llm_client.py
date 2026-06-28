from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.models import GenAIConfig

logger = logging.getLogger(__name__)

SYSTEM_TRUST_STORE_APPLIED = False


def apply_system_trust_store() -> None:
    """Use the OS certificate store when available for corporate-managed laptops."""
    global SYSTEM_TRUST_STORE_APPLIED
    if SYSTEM_TRUST_STORE_APPLIED:
        return
    try:
        import truststore
    except ImportError:
        logger.debug("truststore is not installed; using Python default SSL certificates")
        return
    try:
        truststore.inject_into_ssl()
    except Exception:
        logger.warning("Unable to apply system SSL trust store", exc_info=True)
        return
    SYSTEM_TRUST_STORE_APPLIED = True


apply_system_trust_store()

import litellm  # noqa: E402

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
NETWORK_ENV_KEYS = ("HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY")


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


def resolved_env_path(value: Path | None) -> str | None:
    if value is None:
        return None
    return str(get_settings().resolve_backend_path(value))


def apply_network_environment() -> None:
    apply_system_trust_store()
    settings = get_settings()
    env_values = {
        "SSL_CERT_FILE": resolved_env_path(settings.ssl_cert_file),
        "SSL_CERT_DIR": resolved_env_path(settings.ssl_cert_dir),
        "HTTP_PROXY": settings.http_proxy,
        "HTTPS_PROXY": settings.https_proxy,
        "NO_PROXY": settings.no_proxy,
    }
    for key, value in env_values.items():
        if value and not os.getenv(key):
            os.environ[key] = value
    for key in NETWORK_ENV_KEYS:
        value = os.getenv(key)
        if value and not os.getenv(key.lower()):
            os.environ[key.lower()] = value


def test_completion(config: GenAIConfig, prompt: str | None = None) -> LLMCompletionResult:
    apply_network_environment()
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
