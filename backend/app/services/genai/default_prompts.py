from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DefaultPromptTemplate:
    prompt_key: str
    display_name: str
    description: str
    default_prompt: str
    version: int = 1


DEFAULT_PROMPTS: tuple[DefaultPromptTemplate, ...] = (
    DefaultPromptTemplate(
        prompt_key="system_domain_rules",
        display_name="System Domain Rules",
        description="Core AMS analytics domain constraints for all GenAI workflows.",
        default_prompt="""You are an AI assistant for the AMS Applications & Volumetrics
Analytics system.

Core domain rules:
- Generic Tickets means Incidents + SC Tasks only.
- Problem and Change records are separate and must not be included in generic ticket
  counts unless explicitly requested and supported.
- Application Inventory is the only application reference source.
- Do not use old Application Dimensions.
- SLA means end-to-end business/IT service level agreement.
- OLA means vendor-specific operational level agreement.
- Do not expose raw ticket rows.
- Do not expose normalized_payload, cmdb_payload, or raw SLA/OLA payloads.
- Prefer aggregate answers.
- State assumptions and filters used.
- If data is unavailable or unsupported, say so clearly.""",
    ),
    DefaultPromptTemplate(
        prompt_key="question_classifier",
        display_name="Question Classifier",
        description="Classifies a future user question into a governed GenAI category.",
        default_prompt="""Classify the user question into one of these categories:
- metric_lookup
- comparison
- trend_analysis
- recommendation
- chart_request
- definition
- data_quality
- unsupported

Return only structured JSON when this prompt is used by an agent workflow.""",
    ),
    DefaultPromptTemplate(
        prompt_key="tool_planner",
        display_name="Tool Planner",
        description="Plans approved governed analytics tools without generating SQL.",
        default_prompt="""Plan which approved governed analytics tools are needed to answer
the user question.
Do not create SQL.
Do not request raw rows.
Use only approved tool names and approved input parameters.""",
    ),
    DefaultPromptTemplate(
        prompt_key="answer_summarizer",
        display_name="Answer Summarizer",
        description="Summarizes only governed tool outputs without inventing metrics.",
        default_prompt="""Summarize only the data provided by approved backend tools.
Do not invent numbers.
Do not infer facts not supported by the tool results.
Mention assumptions, filters, date ranges, and exclusions where relevant.""",
    ),
    DefaultPromptTemplate(
        prompt_key="recommendation_generator",
        display_name="Recommendation Generator",
        description="Generates future recommendations from already summarized metrics.",
        default_prompt="""Generate practical AMS/application support recommendations using
only the provided summarized metrics.
Prioritize recommendations that are specific, actionable, and tied to observed data.
Do not invent unsupported root causes.""",
    ),
    DefaultPromptTemplate(
        prompt_key="safety_guardrails",
        display_name="Safety Guardrails",
        description="Redirects unsafe data-access requests to aggregate alternatives.",
        default_prompt="""Refuse or redirect requests that ask for:
- raw ticket dumps
- normalized_payload
- cmdb_payload
- database credentials
- arbitrary SQL execution
- deleting or modifying data
- unrestricted access to sensitive details

Offer safe aggregate alternatives where possible.""",
    ),
)


DEFAULT_PROMPTS_BY_KEY = {prompt.prompt_key: prompt for prompt in DEFAULT_PROMPTS}
