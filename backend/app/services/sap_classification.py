from __future__ import annotations

from typing import Any

SAP_NON_SAP_SAP = "SAP"
SAP_NON_SAP_NON_SAP = "Non-SAP"


def derive_sap_non_sap(assignment_group: Any) -> str | None:
    """Classify Mondelez-style assignment groups by prefix.

    This is intentionally a simple customer-specific convention for now:
    IT-SAP* means SAP, IT-NSA* means Non-SAP, and everything else remains blank.
    """
    if assignment_group is None:
        return None

    normalized_assignment_group = str(assignment_group).strip().upper()
    if normalized_assignment_group.startswith("IT-SAP"):
        return SAP_NON_SAP_SAP
    if normalized_assignment_group.startswith("IT-NSA"):
        return SAP_NON_SAP_NON_SAP
    return None
