from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.db.session import SessionLocal
from app.main import app
from app.models import (
    ApplicationInventoryItem,
    AssessmentOutOfScopeTicket,
    Client,
    GenAISafetySettings,
    GenAIToolRun,
    GenAIUsageLog,
    Project,
    Ticket,
    UploadBatch,
)


def reset_tool_logs(project_id: UUID | None = None) -> None:
    db = SessionLocal()
    try:
        if project_id is None:
            db.execute(delete(GenAIToolRun))
            db.execute(delete(GenAIUsageLog).where(GenAIUsageLog.operation == "tool_execution"))
        else:
            db.execute(delete(GenAIToolRun).where(GenAIToolRun.project_id == project_id))
            db.execute(
                delete(GenAIUsageLog).where(
                    GenAIUsageLog.operation == "tool_execution",
                    GenAIUsageLog.project_id == project_id,
                ),
            )
        db.commit()
    finally:
        db.close()


def create_tool_project() -> tuple[UUID, UUID, UUID]:
    db = SessionLocal()
    suffix = uuid4().hex[:10]
    try:
        settings = db.query(GenAISafetySettings).first()
        if settings is None:
            settings = GenAISafetySettings()
            db.add(settings)
        settings.allow_application_detail_rows = True
        settings.allow_ticket_detail_rows = False
        settings.allow_aggregate_ticket_data = True
        settings.allow_problem_change_data = False
        settings.allow_sla_ola_aggregate_data = True
        settings.max_rows_returned_to_llm = 100
        settings.max_chart_data_points = 500
        settings.enforce_complete_month_cutoff = True
        settings.mask_sensitive_fields = True

        client = Client(name=f"GenAI Tools Client {suffix}", code=f"GT-C-{suffix}")
        db.add(client)
        db.flush()

        project = Project(
            client_id=client.id,
            name=f"GenAI Tools Project {suffix}",
            code=f"GT-P-{suffix}",
        )
        db.add(project)
        db.flush()

        batch = UploadBatch(
            project_id=project.id,
            month_key="2026-05",
            batch_name=f"GenAI Tools Batch {suffix}",
            status="NORMALIZED",
            file_count=1,
            total_size_bytes=1,
        )
        db.add(batch)
        db.flush()

        inventory_rows = [
            ApplicationInventoryItem(
                project_id=project.id,
                business_service_ci_name="Finance Service",
                parent_application_name="Finance Parent",
                functional_track="Finance",
                ams_owner="Asha",
                supported_by_vendor="Vendor A",
                assignment_group="AMS Finance",
                assignment_group_owner="Owner A",
                application_owner="App Owner A",
                sap_non_sap="SAP",
                hosting_env="Production",
                global_application="Global",
                lifecycle_stage_status="In Use",
                lifecycle_current="Invest",
                lifecycle_1_to_3_years="Maintain",
                lifecycle_3_to_5_years="Retired",
                active=True,
                active_users=100,
                cmdb_payload={"Business criticality": "Very Critical"},
            ),
            ApplicationInventoryItem(
                project_id=project.id,
                business_service_ci_name="Finance Portal",
                parent_application_name="Finance Parent",
                functional_track="Finance",
                ams_owner="Asha",
                supported_by_vendor="Vendor B",
                assignment_group="AMS Finance",
                assignment_group_owner="Owner A",
                application_owner="App Owner B",
                sap_non_sap="SAP",
                hosting_env="Production",
                global_application="Global",
                lifecycle_stage_status="In Use",
                lifecycle_current="Disinvest",
                lifecycle_1_to_3_years="Invest",
                lifecycle_3_to_5_years="Maintain",
                active=True,
                active_users=150,
                cmdb_payload={"Business criticality": "Critical"},
            ),
            ApplicationInventoryItem(
                project_id=project.id,
                business_service_ci_name="HR Service",
                parent_application_name="HR Parent",
                functional_track="HR",
                ams_owner="Ben",
                supported_by_vendor="Vendor A",
                assignment_group="AMS HR",
                assignment_group_owner="Owner B",
                application_owner="App Owner C",
                sap_non_sap="Non-SAP",
                hosting_env="Non-Prod",
                global_application="Local",
                lifecycle_stage_status="In Use",
                lifecycle_current="Maintain",
                lifecycle_1_to_3_years="Maintain",
                lifecycle_3_to_5_years="Retired",
                active=True,
                active_users=50,
            ),
            ApplicationInventoryItem(
                project_id=project.id,
                business_service_ci_name="Blank Track Service",
                parent_application_name="Blank Parent",
                functional_track=" ",
                ams_owner="",
                supported_by_vendor="Vendor C",
                assignment_group="AMS Other",
                assignment_group_owner="Owner C",
                application_owner="App Owner D",
                sap_non_sap="SAP",
                hosting_env="Dev",
                global_application="Local",
                lifecycle_stage_status="Retired",
                lifecycle_current="Retired",
                lifecycle_1_to_3_years="Retired",
                lifecycle_3_to_5_years="Retired",
                active=False,
                active_users=5,
            ),
        ]
        db.add_all(inventory_rows)

        created = datetime(2026, 5, 5, tzinfo=UTC)
        db.add_all(
            [
                Ticket(
                    project_id=project.id,
                    upload_batch_id=batch.id,
                    ticket_number=f"INC-{suffix}-1",
                    ticket_type="INCIDENT",
                    month_key="2026-05",
                    created_at=created,
                    resolved_at=datetime(2026, 5, 6, tzinfo=UTC),
                    state="Resolved",
                    priority="P1",
                    parent_application_name="Finance Parent",
                    business_service_ci_name="Finance Service",
                    functional_track="Finance",
                    ams_owner="Asha",
                    supported_by_vendor="Vendor A",
                    assignment_group="AMS Finance",
                    assignment_group_owner="Owner A",
                    application_owner="App Owner A",
                    sap_non_sap="SAP",
                    architecture_type="Cloud",
                    install_type="Install",
                    derived_vendor="Vendor A",
                    ola_response_sla_breached=False,
                    ola_resolution_sla_breached=True,
                    sla_response_sla_breached=False,
                    sla_resolution_sla_breached=False,
                    reopen_count=0,
                    normalized_payload={"secret": "not returned"},
                ),
                Ticket(
                    project_id=project.id,
                    upload_batch_id=batch.id,
                    ticket_number=f"SCTASK-{suffix}-1",
                    ticket_type="SERVICE_CATALOG_TASK",
                    month_key="2026-05",
                    created_at=created,
                    closed_at=datetime(2026, 5, 7, tzinfo=UTC),
                    state="Closed Complete",
                    priority="P2",
                    parent_application_name="HR Parent",
                    business_service_ci_name="HR Service",
                    functional_track="HR",
                    ams_owner="Ben",
                    supported_by_vendor="Vendor A",
                    assignment_group="AMS HR",
                    assignment_group_owner="Owner B",
                    application_owner="App Owner C",
                    sap_non_sap="Non-SAP",
                    architecture_type="On Prem",
                    install_type="Run",
                    derived_vendor="Vendor A",
                    ola_response_sla_breached=False,
                    ola_resolution_sla_breached=False,
                    sla_response_sla_breached=False,
                    sla_resolution_sla_breached=True,
                    reopen_count=0,
                ),
                Ticket(
                    project_id=project.id,
                    upload_batch_id=batch.id,
                    ticket_number=f"INC-{suffix}-2",
                    ticket_type="INCIDENT",
                    month_key="2026-05",
                    created_at=created,
                    resolved_at=datetime(2026, 5, 8, tzinfo=UTC),
                    state="Canceled",
                    priority="P3",
                    parent_application_name="Finance Parent",
                    business_service_ci_name="Finance Portal",
                    functional_track="Finance",
                    ams_owner="Asha",
                    supported_by_vendor="Vendor B",
                    assignment_group="AMS Finance",
                    assignment_group_owner="Owner A",
                    application_owner="App Owner B",
                    sap_non_sap="SAP",
                    architecture_type="Cloud",
                    install_type="Install",
                    derived_vendor="Vendor B",
                    reopen_count=0,
                ),
                Ticket(
                    project_id=project.id,
                    upload_batch_id=batch.id,
                    ticket_number=f"PRB-{suffix}-1",
                    ticket_type="PROBLEM",
                    month_key="2026-05",
                    created_at=created,
                    resolved_at=datetime(2026, 5, 9, tzinfo=UTC),
                    state="Resolved",
                    priority="P1",
                    parent_application_name="Finance Parent",
                    reopen_count=0,
                ),
                Ticket(
                    project_id=project.id,
                    upload_batch_id=batch.id,
                    ticket_number=f"CHG-{suffix}-1",
                    ticket_type="CHANGE",
                    month_key="2026-05",
                    created_at=created,
                    closed_at=datetime(2026, 5, 10, tzinfo=UTC),
                    state="Closed",
                    priority="P1",
                    parent_application_name="Finance Parent",
                    reopen_count=0,
                ),
                AssessmentOutOfScopeTicket(
                    project_id=project.id,
                    upload_batch_id=batch.id,
                    ticket_number=f"INC-OOS-{suffix}-1",
                    ticket_type="INCIDENT",
                    month_key="2026-05",
                    created_at=created,
                    resolved_at=datetime(2026, 5, 11, tzinfo=UTC),
                    state="Resolved",
                    priority="P2",
                    parent_application_name="Finance Parent",
                    business_service_ci_name="Finance Service",
                    functional_track="Finance",
                    ams_owner="Asha",
                    supported_by_vendor="Vendor A",
                    assignment_group="AMS Finance",
                    assignment_group_owner="Owner A",
                    sap_non_sap="SAP",
                    architecture_type="Cloud",
                    install_type="Install",
                    derived_vendor="Vendor A",
                    ola_response_sla_breached=False,
                    ola_resolution_sla_breached=False,
                    sla_response_sla_breached=False,
                    sla_resolution_sla_breached=False,
                    out_of_scope_reason="Duplicate",
                    reopen_count=0,
                ),
            ],
        )
        db.commit()
        return client.id, project.id, batch.id
    finally:
        db.close()


def cleanup_client(client_id: UUID) -> None:
    db = SessionLocal()
    try:
        db.rollback()
        db.execute(delete(Client).where(Client.id == client_id))
        db.commit()
    finally:
        db.close()


def execute_tool(client: TestClient, tool_name: str, project_id: UUID, **payload) -> dict:
    request = {
        "tool_name": tool_name,
        "customer_id": None,
        "project_id": str(project_id),
        "parameters": payload.pop("parameters", {}),
        "filters": payload.pop("filters", {}),
    }
    request.update(payload)
    response = client.post("/api/genai/tools/execute", json=request)
    assert response.status_code == 200
    return response.json()


def test_tool_catalog_contains_expected_tools_and_no_duplicates() -> None:
    with TestClient(app) as client:
        response = client.get("/api/genai/tools/catalog")

    assert response.status_code == 200
    tool_names = [item["tool_name"] for item in response.json()["items"]]
    assert len(tool_names) == len(set(tool_names))
    assert "get_application_inventory_summary" in tool_names
    assert "get_ticket_volume_summary" in tool_names
    assert "get_sla_ola_summary" in tool_names


def test_unknown_tool_is_rejected_and_logged() -> None:
    reset_tool_logs()
    client_id, project_id, _batch_id = create_tool_project()
    try:
        with TestClient(app) as client:
            result = execute_tool(client, "not_a_tool", project_id)
            runs_response = client.get("/api/genai/tools/runs", params={"limit": 5})

        assert result["status"] == "rejected"
        assert "not registered" in result["warnings"][0]
        assert runs_response.status_code == 200
        assert any(run["tool_name"] == "not_a_tool" for run in runs_response.json())
    finally:
        reset_tool_logs(project_id)
        cleanup_client(client_id)


def test_application_inventory_summary_uses_distinct_inventory_counts() -> None:
    client_id, project_id, _batch_id = create_tool_project()
    try:
        with TestClient(app) as client:
            result = execute_tool(client, "get_application_inventory_summary", project_id)

        assert result["status"] == "success"
        metrics = {row["metric"]: row["value"] for row in result["rows"]}
        assert metrics["Total Applications"] == 4
        assert metrics["Functional Tracks"] == 2
        assert metrics["AMS Owners"] == 2
        assert metrics["Supported Vendors"] == 3
        assert "cmdb_payload" not in str(result)
        assert any("not returned" in warning for warning in result["warnings"])
    finally:
        reset_tool_logs(project_id)
        cleanup_client(client_id)


def test_application_distribution_rejects_unsupported_payload_dimension() -> None:
    client_id, project_id, _batch_id = create_tool_project()
    try:
        with TestClient(app) as client:
            result = execute_tool(
                client,
                "get_application_distribution",
                project_id,
                parameters={"dimension": "business_criticality"},
            )

        assert result["status"] == "rejected"
        assert "raw CMDB payload" in result["warnings"][0]
    finally:
        reset_tool_logs(project_id)
        cleanup_client(client_id)


def test_application_distribution_excludes_blank_values_by_default() -> None:
    client_id, project_id, _batch_id = create_tool_project()
    try:
        with TestClient(app) as client:
            result = execute_tool(
                client,
                "get_application_distribution",
                project_id,
                parameters={"dimension": "functional_track", "top_n": 10},
            )

        assert result["status"] == "success"
        dimensions = {row["dimension"] for row in result["rows"]}
        assert dimensions == {"Finance", "HR"}
    finally:
        reset_tool_logs(project_id)
        cleanup_client(client_id)


def test_lifecycle_selected_plan_returns_capped_safe_inventory_rows() -> None:
    client_id, project_id, _batch_id = create_tool_project()
    try:
        with TestClient(app) as client:
            result = execute_tool(
                client,
                "get_application_lifecycle_planning_summary",
                project_id,
                parameters={"selected_plan": "Invest", "top_n": 1},
            )

        assert result["status"] == "success"
        assert result["row_count"] == 1
        assert result["truncated"] is True
        assert "cmdb_payload" not in str(result)
        assert "business_service_ci_name" in result["rows"][0]
    finally:
        reset_tool_logs(project_id)
        cleanup_client(client_id)


def test_ticket_volume_summary_excludes_problem_and_change_records() -> None:
    client_id, project_id, _batch_id = create_tool_project()
    try:
        with TestClient(app) as client:
            result = execute_tool(
                client,
                "get_ticket_volume_summary",
                project_id,
                parameters={"scope": "in_scope", "ticket_type": "all"},
            )

        assert result["status"] == "success"
        metrics = {row["metric"]: row["value"] for row in result["rows"]}
        assert metrics["Created count"] == 3
        assert metrics["Incident count"] == 2
        assert metrics["SC Task count"] == 1
        assert metrics["Canceled/Closed Incomplete count"] == 1
        assert "Problems and Changes are excluded." in result["data_notes"]
        assert "normalized_payload" not in str(result)
    finally:
        reset_tool_logs(project_id)
        cleanup_client(client_id)


def test_ticket_scope_all_includes_out_of_scope_generic_tickets_only() -> None:
    client_id, project_id, _batch_id = create_tool_project()
    try:
        with TestClient(app) as client:
            result = execute_tool(
                client,
                "get_ticket_volume_summary",
                project_id,
                parameters={"scope": "all", "ticket_type": "all"},
            )

        metrics = {row["metric"]: row["value"] for row in result["rows"]}
        assert result["status"] == "success"
        assert metrics["Created count"] == 4
        assert metrics["Incident count"] == 3
        assert metrics["SC Task count"] == 1
    finally:
        reset_tool_logs(project_id)
        cleanup_client(client_id)


def test_ticket_distribution_rejects_invalid_metric_and_dimension() -> None:
    client_id, project_id, _batch_id = create_tool_project()
    try:
        with TestClient(app) as client:
            bad_metric = execute_tool(
                client,
                "get_ticket_distribution",
                project_id,
                parameters={
                    "dimension": "functional_track",
                    "metric": "raw_rows",
                },
            )
            bad_dimension = execute_tool(
                client,
                "get_ticket_distribution",
                project_id,
                parameters={"dimension": "normalized_payload", "metric": "created_count"},
            )

        assert bad_metric["status"] == "rejected"
        assert bad_dimension["status"] == "rejected"
    finally:
        reset_tool_logs(project_id)
        cleanup_client(client_id)


def test_top_applications_by_ticket_volume_returns_compact_aggregates() -> None:
    client_id, project_id, _batch_id = create_tool_project()
    try:
        with TestClient(app) as client:
            result = execute_tool(
                client,
                "get_top_applications_by_ticket_volume",
                project_id,
                parameters={"scope": "all", "metric": "created_count", "top_n": 2},
            )

        assert result["status"] == "success"
        assert result["rows"][0]["application"] == "Finance Parent"
        assert result["rows"][0]["created_count"] == 3
        assert "normalized_payload" not in str(result)
    finally:
        reset_tool_logs(project_id)
        cleanup_client(client_id)


def test_ola_summary_adherence_excludes_missing_values() -> None:
    client_id, project_id, _batch_id = create_tool_project()
    try:
        with TestClient(app) as client:
            result = execute_tool(
                client,
                "get_sla_ola_summary",
                project_id,
                parameters={"agreement_type": "ola", "metric": "both", "scope": "in_scope"},
            )

        assert result["status"] == "success"
        rows = {row["metric"]: row for row in result["rows"]}
        assert rows["response"]["captured_count"] == 2
        assert rows["response"]["adherence_percent"] == 100.0
        assert rows["resolution"]["captured_count"] == 2
        assert rows["resolution"]["adherence_percent"] == 50.0
    finally:
        reset_tool_logs(project_id)
        cleanup_client(client_id)


def test_sla_by_dimension_works_with_supported_schema_fields() -> None:
    client_id, project_id, _batch_id = create_tool_project()
    try:
        with TestClient(app) as client:
            result = execute_tool(
                client,
                "get_sla_ola_by_dimension",
                project_id,
                parameters={
                    "agreement_type": "sla",
                    "dimension": "functional_track",
                    "metric": "response",
                    "scope": "all",
                },
            )

        assert result["status"] == "success"
        assert {row["dimension"] for row in result["rows"]} >= {"Finance", "HR"}
        assert "normalized_payload" not in str(result).lower()
        assert "cmdb_payload" not in str(result).lower()
    finally:
        reset_tool_logs(project_id)
        cleanup_client(client_id)


def test_ticket_safety_setting_can_reject_aggregate_tool() -> None:
    client_id, project_id, _batch_id = create_tool_project()
    try:
        with TestClient(app) as client:
            safety = client.get("/api/genai/safety-settings").json()
            update_response = client.put(
                "/api/genai/safety-settings",
                json={
                    "allow_aggregate_ticket_data": False,
                    "max_rows_returned_to_llm": safety["max_rows_returned_to_llm"],
                },
            )
            assert update_response.status_code == 200
            result = execute_tool(client, "get_ticket_volume_summary", project_id)
            client.put("/api/genai/safety-settings", json={"allow_aggregate_ticket_data": True})

        assert result["status"] == "rejected"
        assert "disabled" in result["warnings"][0].lower()
    finally:
        reset_tool_logs(project_id)
        cleanup_client(client_id)


def test_tool_runs_endpoint_filters_recent_runs() -> None:
    client_id, project_id, _batch_id = create_tool_project()
    try:
        with TestClient(app) as client:
            execute_tool(client, "get_application_inventory_summary", project_id)
            execute_tool(client, "get_ticket_volume_summary", project_id)
            response = client.get(
                "/api/genai/tools/runs",
                params={"tool_name": "get_ticket_volume_summary", "limit": 1},
            )

        assert response.status_code == 200
        rows = response.json()
        assert len(rows) == 1
        assert rows[0]["tool_name"] == "get_ticket_volume_summary"
        assert "rows" not in str(rows[0]["parameters_json"]).lower()
        assert "normalized_payload" not in str(rows).lower()
        assert "cmdb_payload" not in str(rows).lower()
    finally:
        reset_tool_logs(project_id)
        cleanup_client(client_id)
