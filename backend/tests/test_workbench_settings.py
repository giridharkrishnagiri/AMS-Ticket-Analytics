from __future__ import annotations

from app.models import Ticket
from app.services.genai.ticket_classification import input_hash_for_ticket
from app.services.genai.workbench_settings import (
    DEFAULT_CLUSTERING_COLUMNS,
    normalize_workbench_settings,
    selected_ticket_payload,
)


def test_workbench_settings_normalize_modes_counts_and_columns() -> None:
    settings = normalize_workbench_settings(
        {
            "cluster_mode": "unexpected",
            "cluster_level_1_mode": "distance-only",
            "cluster_level_1_count": "40",
            "cluster_level_3_distance_threshold": "0.07",
            "clustering_columns": ["short_description", "not_a_column"],
            "automation_clusters_per_request": "12",
        },
    )

    assert settings["cluster_mode"] == "adaptive"
    assert settings["cluster_level_1_mode"] == "threshold_only"
    assert settings["cluster_level_1_count"] == 40
    assert settings["cluster_level_3_distance_threshold"] == 0.07
    assert settings["clustering_columns"] == ["short_description"]
    assert settings["automation_clusters_per_request"] == 12


def test_selected_ticket_payload_extracts_direct_and_raw_payload_fields() -> None:
    ticket = Ticket(
        ticket_number="INC001",
        ticket_type="INCIDENT",
        short_description="Access issue",
        description="Cannot access reporting workspace.",
        normalized_payload={
            "mapped_fields": {
                "Close notes": "Reset user assignment and confirmed access.",
            },
        },
    )

    payload = selected_ticket_payload(
        ticket,
        ["ticket_type", "short_description", "close_notes"],
        default_columns=DEFAULT_CLUSTERING_COLUMNS,
    )

    assert payload == {
        "ticket_number": "INC001",
        "ticket_type": "INCIDENT",
        "short_description": "Access issue",
        "close_notes": "Reset user assignment and confirmed access.",
    }


def test_classification_input_hash_changes_when_selected_columns_change() -> None:
    ticket = Ticket(
        ticket_number="INC002",
        ticket_type="INCIDENT",
        state="Resolved",
        short_description="Password reset error",
        description="User cannot reset password from portal.",
    )

    short_only_hash = input_hash_for_ticket(
        ticket,
        model_name="model",
        prompt_version=1,
        prompt_fingerprint_value="prompt",
        column_keys=["ticket_type", "short_description"],
    )
    with_description_hash = input_hash_for_ticket(
        ticket,
        model_name="model",
        prompt_version=1,
        prompt_fingerprint_value="prompt",
        column_keys=["ticket_type", "short_description", "description"],
    )

    assert short_only_hash != with_description_hash
