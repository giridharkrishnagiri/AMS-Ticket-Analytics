from __future__ import annotations

from uuid import uuid4

from app.models import GenAITicketAutomationAssessment
from app.services.genai.ticket_automation import (
    resolved_automation_potential,
    row_automation_potential,
)


def test_problem_management_resolution_is_not_recommended_for_automation() -> None:
    assert (
        resolved_automation_potential("High", "Problem Management")
        == "Not Recommended"
    )


def test_row_automation_potential_overrides_existing_problem_management_rows() -> None:
    row = GenAITicketAutomationAssessment(
        project_id=uuid4(),
        analysis_month="2026-05",
        analysis_month_to="2026-05",
        run_id="run",
        cluster_run_id="cluster-run",
        cluster_key="cluster",
        cluster_label="Cluster",
        ticket_type="INCIDENT",
        input_hash="hash",
        prompt_key="ticket_automation_analysis",
        automation_potential="High",
        recommended_resolution_path="Problem Management",
    )

    assert row_automation_potential(row) == "Not Recommended"


def test_non_problem_management_potential_is_preserved() -> None:
    assert resolved_automation_potential("Medium", "IT-led automation") == "Medium"
