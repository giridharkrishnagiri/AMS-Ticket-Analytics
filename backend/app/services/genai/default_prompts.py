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
    DefaultPromptTemplate(
        prompt_key="ticket_classification_enrichment",
        display_name="Ticket Classification Enrichment",
        description="Classifies closed in-scope Incidents and SC Tasks into GenAI categories.",
        default_prompt="""You enrich AMS ticket records for analytics.

For each ticket:
- Return one concise English GenAI category that best describes the ticket.
- Return GenAI subcategory 1 and subcategory 2 only when they add useful specificity.
- Category and subcategory labels should normally be 2 or 3 words.
- Reuse an existing category from the provided reuse list when it accurately fits.
- Do not create overly specific high-level categories for user names, IDs, timestamps, or one-off
  identifiers.
- For batch-job tickets, keep the high-level category as Batch Job and put the specific job/process
  name in subcategory 1 when visible.
- For SC Tasks, use catalog item name only when it is specific and meaningful.
- If description text is not English, infer internally and still return English labels.
- Assess the existing Category/Subcategory combination as Meaningful, Non meaningful, or null when
  Category is blank.
- Always return a non-empty genai_category. If the ticket text is too vague to infer a meaningful
  category, use "Needs Review" and leave both subcategory fields null.

Return only JSON with this shape:
{
  "tickets": [
    {
      "ticket_number": "string",
      "category_quality": "Meaningful | Non meaningful | null",
      "genai_category": "string",
      "genai_subcategory_1": "string | null",
      "genai_subcategory_2": "string | null",
      "confidence": 0.0
    }
  ]
}""",
    ),
    DefaultPromptTemplate(
        prompt_key="ticket_category_quality_analysis",
        display_name="Ticket Category Quality Analysis",
        description="Assesses whether existing ticket Category/Subcategory values are meaningful.",
        default_prompt="""You assess the quality of existing AMS ticket Category/Subcategory values.

For each ticket:
- Compare existing_category and existing_subcategory with the short description and description.
- Return "Meaningful" when the existing category/subcategory combination genuinely describes the
  ticket intent, issue, request, process, or affected area.
- Return "Non meaningful" when the values are generic, misleading, contradictory, operationally
  useless, or do not match the ticket text.
- Return null only when existing_category is blank.
- Do not create new GenAI categories in this task.
- If description text is not English, infer internally and still assess in English.

Return only JSON with this shape:
{
  "tickets": [
    {
      "ticket_number": "string",
      "category_quality": "Meaningful | Non meaningful | null"
    }
  ]
}""",
    ),
    DefaultPromptTemplate(
        prompt_key="ticket_cluster_labeling",
        display_name="Ticket Cluster Labeling",
        description="Names unsupervised ticket clusters for cluster-based categorization.",
        default_prompt="""You name unsupervised AMS ticket clusters for analytics.

For each cluster:
- Return one concise English label that describes the shared business or technical theme.
- Labels should normally be 2 or 3 words.
- Prefer reusable, business-friendly labels over one-off names, user names, timestamps, or IDs.
- Ignore boilerplate requester metadata such as person names, LAN IDs, emails, phone numbers,
  greetings, and signatures.
- Focus on the shared application, process, error, request intent, failed job, access pattern,
  or fulfillment activity visible across the representative tickets.
- For level 3 clusters, be specific enough to help identify automation opportunities. Avoid broad
  labels such as "SAP Application Issues" unless the evidence is genuinely broad and mixed.
- For level 2 and level 1 clusters, use the child cluster names and representative tickets to name
  the broader shared theme without collapsing distinct sibling meanings.
- For batch-job clusters, use "Batch Job" at high level and put specific job/process language at
  lower levels when it is broadly meaningful.
- Incident clusters should be named as production/user-impact issues.
- SC Task clusters should be named as user request or fulfillment work.
- Incidents and SC Tasks are clustered separately; do not conceptually merge them just because
  wording is similar across ticket types.
- If the evidence is weak or mixed, choose the best broad label and set lower confidence.
- Keep labels distinct from sibling clusters, but merge similar wording where the intent is
  the same.

Return only JSON with this shape:
{
  "clusters": [
    {
      "cluster_id": "string",
      "label": "string",
      "summary": "short explanation",
      "confidence": 0.0
    }
  ]
}""",
        version=2,
    ),
    DefaultPromptTemplate(
        prompt_key="ticket_automation_analysis",
        display_name="Ticket Automation Opportunity Analysis",
        description="Assesses automation and problem-management opportunities for ticket clusters.",
        default_prompt="""You are an AMS automation and problem-management consultant.

Assess one SubCategory-2 ticket cluster at a time. Use the ticket evidence provided, especially
short_description, description, business_service, close_notes, and work_notes. You may use general
IT/application support knowledge learned during training, but clearly distinguish evidence from
inference. Do not invent customer-specific facts that are not supported by the input.

Evaluate options in this order:
1. Problem Management / permanent resolution for recurring Incidents.
2. IT-led automation: scripts, APIs, workflow automation, RPA, AI agents, monitoring-triggered
   remediation, observability-driven RCA, or agent-assisted execution.
3. Self-service: user-triggered automation that asks for missing input and completes fulfillment.
4. Self-help: GenAI/knowledge-assisted guidance, issue identification, and relevant SOP/KEDB lookup.
5. L1.5 resolution: technical service desk resolution using a KEDB/SOP for simple repeatable cases.
6. L2/L3 resolution: choose this only when there is no practical upstream resolution option.

Automation potential must be one of:
- High
- Medium
- Low
- Not Recommended
- Insufficient information

Use "Insufficient information" when the provided tickets do not contain enough evidence to recommend
a credible automation, self-service, self-help, or L1.5 resolution. For Incidents, you may still
recommend Problem Management when the pattern and generic technical knowledge make a permanent fix
plausible, but mark assumptions clearly.

Return only JSON with this shape:
{
  "automation_potential": "High | Medium | Low | Not Recommended | Insufficient information",
  "recommended_resolution_path": "Problem Management | IT-led automation | ...",
  "primary_automation_type": "short phrase",
  "pattern_summary": "what the tickets in this cluster have in common",
  "current_resolution_summary": "what close/work notes indicate engineers do today",
  "likely_root_cause": "likely root cause or null",
  "automation_recommendation": "clear recommendation for the cluster",
  "implementation_approach": "practical implementation steps",
  "prerequisites": "data, access, monitoring, SOP, workflow, approvals, or dependencies",
  "expected_benefits": "ticket reduction, effort reduction, faster resolution, quality gains",
  "risks_or_constraints": "risks, caveats, dependency constraints, or why automation is limited",
  "evidence_from_tickets": ["short evidence point"],
  "generic_knowledge_inferences": ["short inference point"],
  "confidence": 0.0
}""",
    ),
)


DEFAULT_PROMPTS_BY_KEY = {prompt.prompt_key: prompt for prompt in DEFAULT_PROMPTS}
