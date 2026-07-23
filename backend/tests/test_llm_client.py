from __future__ import annotations

from app.models import GenAIConfig
from app.services.genai.llm_client import completion_parameters


def test_completion_parameters_omit_sampling_for_gpt_5_family_models() -> None:
    config = GenAIConfig(
        provider="openai",
        model_name="gpt-5.6-terra",
        temperature=0.2,
        top_p=0.8,
        max_output_tokens=4000,
        timeout_seconds=120,
    )

    parameters = completion_parameters(config)

    assert parameters["model"] == "gpt-5.6-terra"
    assert parameters["max_tokens"] == 4000
    assert parameters["timeout"] == 120
    assert "temperature" not in parameters
    assert "top_p" not in parameters


def test_completion_parameters_keep_sampling_for_other_models() -> None:
    config = GenAIConfig(
        provider="openai",
        model_name="gpt-4.1-mini",
        temperature=0.2,
        top_p=0.8,
        max_output_tokens=1000,
        timeout_seconds=60,
    )

    parameters = completion_parameters(config)

    assert parameters["model"] == "gpt-4.1-mini"
    assert parameters["temperature"] == 0.2
    assert parameters["top_p"] == 0.8
