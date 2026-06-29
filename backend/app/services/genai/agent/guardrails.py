from __future__ import annotations

import re
from typing import Any

UNSAFE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bnormalized[_\s-]*payload\b", re.IGNORECASE),
    re.compile(r"\bcmdb[_\s-]*payload\b", re.IGNORECASE),
    re.compile(r"\braw\s+(incident|ticket|row|payload|sla|ola)", re.IGNORECASE),
    re.compile(r"\bdump\b.*\b(ticket|incident|payload|row)", re.IGNORECASE),
    re.compile(r"\bselect\s+.+\s+from\b", re.IGNORECASE | re.DOTALL),
    re.compile(r"\b(run|execute)\s+(this\s+)?sql\b", re.IGNORECASE),
    re.compile(
        r"\b(delete|truncate|drop|update|insert)\s+(records?|rows?|table|from|into)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b(api[_\s-]*key|password|database credentials?|secret)\b", re.IGNORECASE),
)

PROBLEM_CHANGE_PATTERN = re.compile(r"\b(problem|problems|change|changes)\b", re.IGNORECASE)

SAFE_ALTERNATIVE = (
    "I cannot provide raw rows, payloads, credentials, SQL execution, or destructive actions "
    "through GenAI. I can help with governed aggregate summaries, trends, distributions, top-N "
    "rankings, and SLA/OLA adherence using approved analytics tools."
)


def unsafe_reason(question: str) -> str | None:
    for pattern in UNSAFE_PATTERNS:
        if pattern.search(question):
            return SAFE_ALTERNATIVE
    return None


def is_problem_change_request(question: str) -> bool:
    return bool(PROBLEM_CHANGE_PATTERN.search(question))


def guardrail_metadata(question: str) -> dict[str, Any] | None:
    reason = unsafe_reason(question)
    if reason:
        return {
            "category": "unsafe",
            "domain": "unsupported",
            "requires_tools": False,
            "confidence": 1.0,
            "reason": reason,
        }
    if is_problem_change_request(question):
        return {
            "category": "unsupported",
            "domain": "unsupported",
            "requires_tools": False,
            "confidence": 0.9,
            "reason": (
                "Problem and Change analytics are not enabled through governed GenAI tools in "
                "this phase."
            ),
        }
    return None
