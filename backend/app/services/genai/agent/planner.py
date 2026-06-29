from __future__ import annotations

import re
from typing import Any

from app.models import GenAIConfig
from app.schemas.genai import GenAIToolCatalogItem
from app.services.genai.agent.json_utils import compact_json, parse_json_object
from app.services.genai.agent.state import LLMUsageAccumulator
from app.services.genai.llm_client import chat_completion
from app.services.genai.tools.registry import get_tool

SAFE_SCOPES = {"in_scope", "out_of_scope", "all"}
SAFE_TICKET_TYPES = {"all", "incident", "sc_task"}
SENSITIVE_PLAN_MARKERS = (
    "normalized_payload",
    "cmdb_payload",
    "raw_sla",
    "raw_ola",
    "raw_rows",
    "sql",
)


class ToolPlanValidationError(ValueError):
    pass


def _contains(question: str, *patterns: str) -> bool:
    return any(re.search(pattern, question, flags=re.IGNORECASE) for pattern in patterns)


def _top_n(question: str, default: int = 10) -> int:
    match = re.search(r"\btop\s+(\d{1,3})\b", question, flags=re.IGNORECASE)
    if not match:
        return default
    return max(1, min(int(match.group(1)), 50))


def _selected_plan(question: str) -> str | None:
    for plan in ("disinvest", "invest", "maintain", "retired"):
        if re.search(rf"\b{plan}\b", question, flags=re.IGNORECASE):
            return plan
    return None


def _ticket_type(question: str) -> str:
    if _contains(question, r"\bincidents?\b"):
        return "incident"
    if _contains(question, r"\b(sc task|sc tasks|service catalog task)\b"):
        return "sc_task"
    return "all"


def _metric(question: str) -> str:
    if _contains(question, r"\b(resolved|closed)\b"):
        return "resolved_closed_count"
    if _contains(question, r"\b(cancelled|canceled|incomplete)\b"):
        return "canceled_closed_incomplete_count"
    return "created_count"


def _dimension_from_question(question: str, *, domain: str) -> str | None:
    dimension_patterns = (
        ("functional_track", (r"functional track", r"\btrack\b")),
        ("ams_owner", (r"ams owner",)),
        ("functional_track_ams_owner", (r"track.*owner", r"owner.*track")),
        ("sap_non_sap", (r"sap", r"non-sap", r"non sap")),
        ("supported_by_vendor", (r"supported.*vendor", r"\bvendor\b")),
        ("parent_business_application", (r"parent application", r"parent business application")),
        ("application_owner", (r"application owner",)),
        ("assignment_group", (r"assignment group",)),
        ("priority", (r"\bpriority\b",)),
        ("state", (r"\bstate\b", r"\bstatus\b")),
    )
    for dimension, patterns in dimension_patterns:
        if _contains(question, *patterns):
            return dimension
    if domain == "applications":
        return "functional_track"
    if domain == "tickets":
        return "parent_business_application"
    return None


def _plan_item(
    tool_name: str,
    *,
    reason: str,
    parameters: dict[str, Any] | None = None,
    filters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "tool_name": tool_name,
        "reason": reason,
        "parameters": parameters or {},
        "filters": filters or {},
    }


def rule_based_tool_plan(
    classification: dict[str, Any],
    question: str,
    context: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], str | None]:
    q = question.lower()
    category = str(classification.get("category") or "")
    domain = str(classification.get("domain") or "")
    top_n = _top_n(question)

    if category == "chart_request":
        if "ticket" in q:
            return (
                [
                    _plan_item(
                        "get_ticket_trend_summary",
                        reason="Chart request can be answered as a governed ticket trend table.",
                        parameters={
                            "scope": "in_scope",
                            "ticket_type": _ticket_type(question),
                            "date_grain": "month",
                        },
                    ),
                ],
                "Chart rendering is planned for Phase 2; Phase 1E returns compact governed tables.",
            )
        if "application" in q:
            return (
                [
                    _plan_item(
                        "get_application_distribution",
                        reason=(
                            "Chart request can be answered as an application distribution "
                            "table."
                        ),
                        parameters={
                            "dimension": _dimension_from_question(
                                question,
                                domain="applications",
                            )
                        },
                    ),
                ],
                "Chart rendering is planned for Phase 2; Phase 1E returns compact governed tables.",
            )

    if domain == "applications":
        if _contains(q, r"active users?"):
            return (
                [
                    _plan_item(
                        "get_top_parent_applications_by_active_users",
                        reason="User asked for parent applications by active users.",
                        parameters={"top_n": top_n},
                    ),
                ],
                None,
            )
        if _contains(q, r"critical", r"hosting", r"production"):
            return (
                [
                    _plan_item(
                        "get_application_criticality_hosting_matrix",
                        reason="User asked for criticality or hosting matrix information.",
                    ),
                ],
                None,
            )
        if category == "distribution" or _contains(q, r"\bby\b", r"distribution"):
            return (
                [
                    _plan_item(
                        "get_application_distribution",
                        reason="User asked for application distribution by an approved dimension.",
                        parameters={
                            "dimension": _dimension_from_question(question, domain="applications"),
                            "top_n": top_n,
                        },
                    ),
                ],
                None,
            )
        return (
            [
                _plan_item(
                    "get_application_inventory_summary",
                    reason="User asked for Application Inventory summary metrics.",
                ),
            ],
            None,
        )

    if domain == "lifecycle_planning":
        parameters: dict[str, Any] = {}
        selected_plan = _selected_plan(question)
        if selected_plan is not None:
            parameters["selected_plan"] = selected_plan
            parameters["top_n"] = top_n
        return (
            [
                _plan_item(
                    "get_application_lifecycle_planning_summary",
                    reason="User asked for lifecycle planning analytics.",
                    parameters=parameters,
                ),
            ],
            None,
        )

    if domain == "tickets":
        parameters = {
            "scope": "in_scope",
            "ticket_type": _ticket_type(question),
            "metric": _metric(question),
            "top_n": top_n,
        }
        if category == "top_n" or _contains(q, r"highest|top|most"):
            return (
                [
                    _plan_item(
                        "get_top_applications_by_ticket_volume",
                        reason="User asked for top applications by governed ticket volume.",
                        parameters=parameters,
                    ),
                ],
                None,
            )
        if category == "trend_analysis" or _contains(q, r"trend|monthly|over time|latest complete"):
            return (
                [
                    _plan_item(
                        "get_ticket_trend_summary",
                        reason="User asked for ticket trend or latest complete-month volume.",
                        parameters={
                            "scope": "in_scope",
                            "ticket_type": _ticket_type(question),
                            "date_grain": "month",
                        },
                    ),
                ],
                None,
            )
        if category == "distribution" or _contains(q, r"\bby\b|vs|versus|sap|priority|state"):
            return (
                [
                    _plan_item(
                        "get_ticket_distribution",
                        reason="User asked for ticket distribution by an approved dimension.",
                        parameters={
                            **parameters,
                            "dimension": _dimension_from_question(question, domain="tickets"),
                        },
                    ),
                ],
                None,
            )
        return (
            [
                _plan_item(
                    "get_ticket_volume_summary",
                    reason="User asked for governed ticket volume summary.",
                    parameters={
                        "scope": "in_scope",
                        "ticket_type": _ticket_type(question),
                    },
                ),
            ],
            None,
        )

    if domain == "sla_ola":
        agreement_type = "ola"
        if _contains(q, r"\bsla\b") and not _contains(q, r"\bola\b"):
            agreement_type = "sla"
        if _contains(q, r"compare") and _contains(q, r"\bsla\b") and _contains(q, r"\bola\b"):
            return (
                [
                    _plan_item(
                        "get_sla_ola_summary",
                        reason="User asked to compare SLA aggregate adherence.",
                        parameters={"agreement_type": "sla", "metric": "both", "scope": "in_scope"},
                    ),
                    _plan_item(
                        "get_sla_ola_summary",
                        reason="User asked to compare OLA aggregate adherence.",
                        parameters={"agreement_type": "ola", "metric": "both", "scope": "in_scope"},
                    ),
                ],
                None,
            )
        if _contains(q, r"weak|vendor|by"):
            return (
                [
                    _plan_item(
                        "get_sla_ola_by_dimension",
                        reason="User asked for SLA/OLA adherence by vendor or dimension.",
                        parameters={
                            "agreement_type": agreement_type,
                            "metric": "both",
                            "dimension": "supported_by_vendor",
                            "scope": "in_scope",
                            "top_n": top_n,
                        },
                    ),
                ],
                None,
            )
        return (
            [
                _plan_item(
                    "get_sla_ola_summary",
                    reason="User asked for SLA/OLA aggregate adherence summary.",
                    parameters={
                        "agreement_type": agreement_type,
                        "metric": "both",
                        "scope": "in_scope",
                    },
                ),
            ],
            None,
        )

    return [], "I could not map this question to an approved governed analytics tool."


def _normalize_llm_plan(value: dict[str, Any] | None) -> tuple[list[dict[str, Any]], str | None]:
    if not value:
        return [], None
    tools = value.get("tools")
    if not isinstance(tools, list):
        return [], None
    normalized: list[dict[str, Any]] = []
    for item in tools:
        if not isinstance(item, dict):
            continue
        tool_name = str(item.get("tool_name") or "").strip()
        if not tool_name:
            continue
        parameters = item.get("parameters") if isinstance(item.get("parameters"), dict) else {}
        filters = item.get("filters") if isinstance(item.get("filters"), dict) else {}
        normalized.append(
            _plan_item(
                tool_name,
                reason=str(item.get("reason") or "Selected by tool planner.").strip(),
                parameters=parameters,
                filters=filters,
            ),
        )
    answer_strategy = value.get("answer_strategy")
    return normalized, str(answer_strategy).strip() if answer_strategy else None


def plan_tools(
    config: GenAIConfig,
    prompt_templates: dict[str, str],
    question: str,
    context: dict[str, Any],
    classification: dict[str, Any],
    catalog: list[GenAIToolCatalogItem],
    usage: LLMUsageAccumulator,
) -> tuple[list[dict[str, Any]], str | None]:
    fallback_plan, fallback_strategy = rule_based_tool_plan(classification, question, context)
    if not classification.get("requires_tools"):
        return [], None

    planner_prompt = "\n\n".join(
        [
            prompt_templates.get("tool_planner", ""),
            "Create a JSON-only plan using only the registered governed analytics tools.",
            "Do not create SQL. Do not request raw rows. Do not request payload fields.",
            f"Classification JSON: {compact_json(classification, max_chars=2000)}",
            f"Context JSON: {compact_json(context, max_chars=2000)}",
            "Tool catalog JSON: "
            f"{compact_json([item.model_dump(mode='json') for item in catalog])}",
            f"Question: {question}",
            (
                "Return JSON with shape {\"tools\": [{\"tool_name\": string, "
                "\"reason\": string, \"parameters\": object, \"filters\": object}], "
                "\"answer_strategy\": string}."
            ),
        ],
    )
    result = chat_completion(
        config,
        [
            {"role": "system", "content": "You return strict JSON only."},
            {"role": "user", "content": planner_prompt},
        ],
    )
    usage.add(result)
    if not result.ok:
        return fallback_plan, fallback_strategy
    planned, answer_strategy = _normalize_llm_plan(parse_json_object(result.response_text))
    return (planned or fallback_plan), (answer_strategy or fallback_strategy)


def _contains_sensitive_value(value: Any) -> bool:
    if isinstance(value, dict):
        return any(
            _contains_sensitive_value(key) or _contains_sensitive_value(child)
            for key, child in value.items()
        )
    if isinstance(value, list):
        return any(_contains_sensitive_value(item) for item in value)
    if isinstance(value, str):
        lowered = value.lower()
        return any(marker in lowered for marker in SENSITIVE_PLAN_MARKERS)
    return False


def validate_tool_plan(
    plan: list[dict[str, Any]],
    *,
    max_tool_calls: int,
) -> list[dict[str, Any]]:
    if len(plan) > max_tool_calls:
        raise ToolPlanValidationError(
            f"Tool plan requested {len(plan)} tools, exceeding the configured limit of "
            f"{max_tool_calls}.",
        )
    validated: list[dict[str, Any]] = []
    for item in plan:
        tool_name = str(item.get("tool_name") or "").strip()
        tool = get_tool(tool_name)
        if tool is None:
            raise ToolPlanValidationError(f"Tool '{tool_name}' is not registered.")
        parameters = item.get("parameters") if isinstance(item.get("parameters"), dict) else {}
        filters = item.get("filters") if isinstance(item.get("filters"), dict) else {}
        if _contains_sensitive_value(parameters) or _contains_sensitive_value(filters):
            raise ToolPlanValidationError(
                "Tool plan requested a forbidden raw payload or SQL field.",
            )

        dimension = parameters.get("dimension")
        if dimension is not None and str(dimension) not in set(tool.metadata.allowed_dimensions):
            raise ToolPlanValidationError(
                f"Dimension '{dimension}' is not approved for {tool_name}.",
            )
        metric = parameters.get("metric")
        if metric is not None and str(metric) not in set(tool.metadata.allowed_metrics):
            raise ToolPlanValidationError(f"Metric '{metric}' is not approved for {tool_name}.")
        scope = parameters.get("scope")
        if scope is not None and str(scope) not in SAFE_SCOPES:
            raise ToolPlanValidationError(f"Scope '{scope}' is not approved.")
        ticket_type = parameters.get("ticket_type")
        if ticket_type is not None and str(ticket_type) not in SAFE_TICKET_TYPES:
            raise ToolPlanValidationError(f"Ticket type '{ticket_type}' is not approved.")
        top_n = parameters.get("top_n")
        if top_n is not None:
            try:
                parsed_top_n = int(top_n)
            except (TypeError, ValueError) as exc:
                raise ToolPlanValidationError("top_n must be a positive integer.") from exc
            if parsed_top_n < 1:
                raise ToolPlanValidationError("top_n must be a positive integer.")
            parameters = {**parameters, "top_n": min(parsed_top_n, tool.metadata.max_rows)}

        validated.append(
            {
                "tool_name": tool_name,
                "reason": str(item.get("reason") or "Approved governed tool.").strip(),
                "parameters": parameters,
                "filters": filters,
            },
        )
    return validated
