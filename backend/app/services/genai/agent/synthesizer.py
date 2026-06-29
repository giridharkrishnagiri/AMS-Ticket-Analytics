from __future__ import annotations

import re
from typing import Any

from app.models import GenAIConfig
from app.services.genai.agent.json_utils import compact_json
from app.services.genai.agent.state import LLMUsageAccumulator
from app.services.genai.llm_client import chat_completion

GENERIC_PHASE_2A_PROMPT = """
You are running in Phase 2A of the AMS GenAI Analytics Workbench.
You can answer general questions and summarize aggregate data returned by approved governed
analytics tools. You must not write SQL, request raw rows, or claim direct database access.
Chart requests can generate Plotly charts only from approved governed tool results.
""".strip()

UNSUPPORTED_RESPONSE = (
    "I could not answer this safely with the approved Phase 1E analytics tools. "
    "Try asking for an aggregate summary, a top-N ranking, a trend, or a distribution."
)

FORBIDDEN_RESPONSE_TERMS = (
    "normalized_payload",
    "cmdb_payload",
    "raw SLA/OLA payloads",
    "raw SLA payload",
    "raw OLA payload",
)


def sanitize_answer(text: str) -> str:
    sanitized = text
    for term in FORBIDDEN_RESPONSE_TERMS:
        sanitized = re.sub(
            re.escape(term),
            "restricted payload fields",
            sanitized,
            flags=re.IGNORECASE,
        )
    return sanitized


def _bullet_section(title: str, values: list[str]) -> str:
    if not values:
        return ""
    bullets = "\n".join(f"- {value}" for value in values)
    return f"\n\n{title}:\n{bullets}"


def _tool_table_summary(tool_results: list[dict[str, Any]]) -> str:
    summaries: list[str] = []
    for result in tool_results:
        title = (result.get("summary") or {}).get("title") or result.get("tool_name")
        rows = result.get("rows") if isinstance(result.get("rows"), list) else []
        if not rows:
            summaries.append(f"{title}: no rows returned.")
            continue
        preview_rows = rows[:8]
        preview_json = compact_json(preview_rows, max_chars=1500)
        summaries.append(f"{title}: {len(rows)} row(s) returned. Preview: {preview_json}")
    return "\n".join(summaries)


def deterministic_answer(
    *,
    question: str,
    classification: dict[str, Any],
    tool_results: list[dict[str, Any]],
    warnings: list[str],
) -> str:
    if classification.get("category") == "unsafe":
        return str(classification.get("reason") or UNSUPPORTED_RESPONSE)
    if classification.get("category") == "unsupported" and not tool_results:
        return str(classification.get("reason") or UNSUPPORTED_RESPONSE)
    if classification.get("category") == "general" and not tool_results:
        return (
            "The AMS GenAI Analytics Workbench can answer general setup questions and, in "
            "Phase 1E, data-aware questions through approved governed analytics tools. The "
            "LLM does not write SQL or access raw rows directly."
        )
    if classification.get("category") == "chart_request":
        prefix = (
            "I generated the governed aggregate result behind this chart request."
        )
    else:
        prefix = "Here is the governed aggregate result for your question."
    if not tool_results:
        return prefix if not warnings else f"{prefix}\n\nWarnings:\n- " + "\n- ".join(warnings)
    return f"{prefix}\n\n{_tool_table_summary(tool_results)}"


def synthesize_answer(
    config: GenAIConfig,
    prompt_templates: dict[str, str],
    *,
    question: str,
    classification: dict[str, Any],
    context: dict[str, Any],
    tool_results: list[dict[str, Any]],
    data_notes: list[str],
    warnings: list[str],
    assumptions: list[str],
    generated_charts: list[dict[str, Any]] | None = None,
    usage: LLMUsageAccumulator,
) -> tuple[str, list[str], list[str], str | None]:
    if classification.get("category") in {"unsafe", "unsupported"} and not tool_results:
        answer = deterministic_answer(
            question=question,
            classification=classification,
            tool_results=[],
            warnings=warnings,
        )
        return sanitize_answer(answer), [], warnings, None

    generated_charts = generated_charts or []

    system_prompt_parts = [
        prompt_templates.get("system_domain_rules", ""),
        prompt_templates.get("safety_guardrails", ""),
        prompt_templates.get("answer_summarizer", ""),
        GENERIC_PHASE_2A_PROMPT,
    ]
    if config.allow_recommendations:
        system_prompt_parts.append(prompt_templates.get("recommendation_generator", ""))
    else:
        system_prompt_parts.append("Do not include recommendations because they are disabled.")

    user_payload = {
        "question": question,
        "classification": classification,
        "context": context,
        "tool_results": tool_results,
        "data_notes": data_notes,
        "warnings": warnings,
        "assumptions": assumptions,
        "generated_charts": generated_charts,
        "response_requirements": [
            "Summarize only the provided governed tool results.",
            "Do not invent numbers.",
            "Do not mention SQL.",
            "For chart requests with generated_charts, say the chart was saved in AI Charts.",
            "Include filters, assumptions, data notes, and warnings when relevant.",
        ],
    }
    result = chat_completion(
        config,
        [
            {"role": "system", "content": "\n\n".join(system_prompt_parts)},
            {"role": "user", "content": compact_json(user_payload, max_chars=16000)},
        ],
    )
    usage.add(result)
    if result.ok and result.response_text:
        answer = result.response_text.strip()
        error_message = None
    else:
        answer = deterministic_answer(
            question=question,
            classification=classification,
            tool_results=tool_results,
            warnings=warnings,
        )
        error_message = result.error_message

    answer = sanitize_answer(answer)
    if classification.get("category") == "chart_request" and generated_charts:
        chart_titles = ", ".join(
            str(item.get("title") or "Generated chart") for item in generated_charts
        )
        if "ai charts" not in answer.lower():
            answer = f"{answer}\n\nI generated {chart_titles} and saved it in AI Charts."
    answer += _bullet_section("Assumptions / filters used", assumptions)
    answer += _bullet_section("Data notes", data_notes)
    answer += _bullet_section("Warnings", warnings)
    return answer, [], warnings, error_message
