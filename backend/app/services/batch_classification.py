from __future__ import annotations

from typing import Any


def derive_is_batch_related(ticket_type: Any, short_description: Any) -> bool:
    """Classify Mondelez Incident batch tickets from the normalized short description."""
    normalized_ticket_type = str(ticket_type or "").strip().upper()
    if normalized_ticket_type != "INCIDENT":
        return False

    description = str(short_description or "").casefold()
    return "automic" in description
