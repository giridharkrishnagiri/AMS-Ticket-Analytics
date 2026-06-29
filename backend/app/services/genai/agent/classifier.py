from __future__ import annotations

import re
from typing import Any

from app.models import GenAIConfig
from app.services.genai.agent.guardrails import guardrail_metadata
from app.services.genai.agent.json_utils import compact_json, parse_json_object
from app.services.genai.agent.state import LLMUsageAccumulator
from app.services.genai.llm_client import chat_completion

ALLOWED_CATEGORIES = {
    "general",
    "metric_lookup",
    "comparison",
    "trend_analysis",
    "distribution",
    "top_n",
    "recommendation",
    "chart_request",
    "definition",
    "data_quality",
    "unsupported",
    "unsafe",
}
ALLOWED_DOMAINS = {
    "applications",
    "tickets",
    "sla_ola",
    "overview",
    "lifecycle_planning",
    "general",
    "unsupported",
}


def _contains(text: str, *patterns: str) -> bool:
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)


def rule_based_classification(
    question: str,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    guarded = guardrail_metadata(question)
    if guarded is not None:
        return guarded

    q = question.strip().lower()
    domain_hint = str((context or {}).get("domain") or "").lower()

    if _contains(q, r"\b(plot|chart|graph|visuali[sz]e|3d)\b"):
        domain = "tickets" if "ticket" in q else "applications" if "application" in q else "general"
        return {
            "category": "chart_request",
            "domain": domain,
            "requires_tools": domain != "general",
            "confidence": 0.8,
            "reason": (
                "The user asked for charting; Phase 1E can return governed tabular "
                "summaries only."
            ),
        }

    if _contains(q, r"\b(what can|how does|why should|purpose|workbench|genai)\b"):
        return {
            "category": "general",
            "domain": "general",
            "requires_tools": False,
            "confidence": 0.86,
            "reason": "The user asked a general workbench question.",
        }

    if _contains(q, r"\b(sla|ola|adherence|breach|vendor)\b"):
        category = "comparison" if "compare" in q else "metric_lookup"
        if _contains(q, r"\bby\b", r"\bweak\b", r"\bvendor"):
            category = "distribution"
        return {
            "category": category,
            "domain": "sla_ola",
            "requires_tools": True,
            "confidence": 0.84,
            "reason": "The user asked about SLA/OLA aggregate adherence.",
        }

    if _contains(q, r"\b(ticket|tickets|incident|incidents|sc task|sc tasks|volume|backlog)\b"):
        category = "metric_lookup"
        if _contains(q, r"\b(highest|top|largest|most)\b"):
            category = "top_n"
        elif _contains(q, r"\btrend|month|monthly|week|weekly|over time|latest complete\b"):
            category = "trend_analysis"
        elif _contains(q, r"\bdistribution|by|vs|versus|sap|non-sap|priority|state)\b"):
            category = "distribution"
        return {
            "category": category,
            "domain": "tickets",
            "requires_tools": True,
            "confidence": 0.86,
            "reason": "The user asked for governed ticket analytics.",
        }

    if _contains(q, r"\b(lifecycle|disinvest|invest|maintain|retired)\b"):
        return {
            "category": "metric_lookup",
            "domain": "lifecycle_planning",
            "requires_tools": True,
            "confidence": 0.85,
            "reason": "The user asked about lifecycle planning analytics.",
        }

    if _contains(
        q,
        r"\b(application|applications|inventory|functional track|active users)\b",
        r"\b(critical|hosting|production)\b",
    ):
        category = "metric_lookup"
        if _contains(q, r"\b(highest|top|largest|most)\b"):
            category = "top_n"
        elif _contains(q, r"\b(distribution|by|functional track|track|owner|sap|non-sap)\b"):
            category = "distribution"
        return {
            "category": category,
            "domain": "applications",
            "requires_tools": True,
            "confidence": 0.86,
            "reason": "The user asked for governed Application Inventory analytics.",
        }

    if "tickets" in domain_hint:
        return {
            "category": "metric_lookup",
            "domain": "tickets",
            "requires_tools": True,
            "confidence": 0.65,
            "reason": "The current UI context is Tickets.",
        }
    if "application" in domain_hint:
        return {
            "category": "metric_lookup",
            "domain": "applications",
            "requires_tools": True,
            "confidence": 0.65,
            "reason": "The current UI context is Applications.",
        }

    return {
        "category": "unsupported",
        "domain": "unsupported",
        "requires_tools": False,
        "confidence": 0.45,
        "reason": "The question did not map safely to a Phase 1E governed tool.",
    }


def _validated_classification(value: dict[str, Any] | None) -> dict[str, Any] | None:
    if not value:
        return None
    category = str(value.get("category") or "").strip().lower()
    domain = str(value.get("domain") or "").strip().lower()
    if category not in ALLOWED_CATEGORIES or domain not in ALLOWED_DOMAINS:
        return None
    requires_tools = bool(value.get("requires_tools"))
    confidence = value.get("confidence")
    try:
        parsed_confidence = float(confidence) if confidence is not None else 0.5
    except (TypeError, ValueError):
        parsed_confidence = 0.5
    return {
        "category": category,
        "domain": domain,
        "requires_tools": requires_tools,
        "confidence": max(0.0, min(parsed_confidence, 1.0)),
        "reason": str(value.get("reason") or "Classified by GenAI agent.").strip(),
    }


def classify_question(
    config: GenAIConfig,
    prompt_templates: dict[str, str],
    question: str,
    context: dict[str, Any],
    usage: LLMUsageAccumulator,
) -> dict[str, Any]:
    fallback = rule_based_classification(question, context)
    if fallback["category"] in {"unsafe", "unsupported"}:
        return fallback

    prompt = "\n\n".join(
        [
            prompt_templates.get("question_classifier", ""),
            "Classify this user question for the GenAI governed analytics agent.",
            "Return JSON only with category, domain, requires_tools, confidence, and reason.",
            f"Allowed categories: {sorted(ALLOWED_CATEGORIES)}",
            f"Allowed domains: {sorted(ALLOWED_DOMAINS)}",
            f"Context JSON: {compact_json(context, max_chars=2000)}",
            f"Question: {question}",
        ],
    )
    result = chat_completion(
        config,
        [
            {"role": "system", "content": "You return strict JSON only."},
            {"role": "user", "content": prompt},
        ],
    )
    usage.add(result)
    if not result.ok:
        return fallback
    parsed = _validated_classification(parse_json_object(result.response_text))
    if parsed is None:
        return fallback
    if fallback.get("requires_tools") and (
        not parsed.get("requires_tools") or parsed.get("domain") != fallback.get("domain")
    ):
        return fallback
    if parsed.get("category") == "unsupported" and fallback.get("category") != "unsupported":
        return fallback
    return parsed
