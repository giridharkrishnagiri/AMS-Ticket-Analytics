from __future__ import annotations

import json
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.db.session import SessionLocal
from app.main import app
from app.models import GenAIGeneratedChart, GenAIUsageLog


def reset_chart_editing_tables() -> None:
    db = SessionLocal()
    try:
        db.execute(delete(GenAIGeneratedChart))
        db.execute(delete(GenAIUsageLog).where(GenAIUsageLog.operation.like("chart_%")))
        db.commit()
    finally:
        db.close()


def category_tool_result(rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "tool_name": "get_application_distribution",
        "domain": "applications",
        "status": "success",
        "summary": {
            "title": "Application Distribution",
            "description": "Distinct applications by functional track.",
        },
        "columns": [
            {"key": "dimension", "label": "Functional Track", "type": "string"},
            {"key": "application_count", "label": "Applications", "type": "number"},
        ],
        "rows": rows
        or [
            {"dimension": "Finance", "application_count": 12},
            {"dimension": "Supply Chain", "application_count": 8},
            {"dimension": "Manufacturing", "application_count": 4},
        ],
        "applied_filters": {"dimension": "functional_track"},
        "data_notes": ["Application Inventory is the only application reference source."],
        "warnings": [],
        "row_count": len(rows or [1, 2, 3]),
        "truncated": False,
    }


def three_metric_tool_result() -> dict[str, Any]:
    return {
        "tool_name": "safe_scatter_fixture",
        "domain": "applications",
        "status": "success",
        "summary": {"title": "Three Metric Fixture", "description": "Synthetic safe aggregate."},
        "columns": [
            {"key": "segment", "label": "Segment", "type": "string"},
            {"key": "x_metric", "label": "X Metric", "type": "number"},
            {"key": "y_metric", "label": "Y Metric", "type": "number"},
            {"key": "z_metric", "label": "Z Metric", "type": "number"},
        ],
        "rows": [
            {"segment": "A", "x_metric": 1, "y_metric": 5, "z_metric": 9},
            {"segment": "B", "x_metric": 2, "y_metric": 6, "z_metric": 12},
        ],
        "data_notes": ["Safe aggregate test fixture."],
        "warnings": [],
        "row_count": 2,
        "truncated": False,
    }


def create_chart(client: TestClient, tool_result: dict[str, Any] | None = None) -> dict[str, Any]:
    response = client.post(
        "/api/genai/charts/from-tool-result",
        json={
            "tool_result": tool_result or category_tool_result(),
            "question": "Plot applications by functional track.",
        },
    )
    assert response.status_code == 200
    return response.json()


def assert_no_forbidden_payload_markers(payload: dict[str, Any]) -> None:
    rendered = json.dumps(payload).lower()
    assert "normalized_payload" not in rendered
    assert "cmdb_payload" not in rendered
    assert "raw_sla" not in rendered
    assert "raw_ola" not in rendered
    assert "select *" not in rendered


def test_chart_update_edits_presentation_and_preserves_safe_data() -> None:
    reset_chart_editing_tables()
    with TestClient(app) as client:
        created = create_chart(client)
        response = client.put(
            f"/api/genai/charts/{created['id']}",
            json={
                "title": "Applications by Functional Track",
                "subtitle": "Application Inventory only",
                "chart_type": "pie",
                "show_labels": False,
                "show_legend": False,
                "sort_order": "descending",
                "top_n": 2,
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["title"] == "Applications by Functional Track"
    assert payload["subtitle"] == "Application Inventory only"
    assert payload["chart_type"] == "pie"
    assert payload["chart_spec"]["plotly"]["layout"]["showlegend"] is False
    assert payload["chart_spec"]["plotly"]["data"][0]["textinfo"] == "none"
    assert len(payload["table"]["rows"]) == 2
    assert payload["data_notes"] == [
        "Application Inventory is the only application reference source."
    ]
    assert_no_forbidden_payload_markers(payload)


def test_chart_update_rejects_unknown_settings_and_warns_for_incompatible_3d() -> None:
    reset_chart_editing_tables()
    with TestClient(app) as client:
        created = create_chart(client)
        unknown_response = client.put(
            f"/api/genai/charts/{created['id']}",
            json={"raw_sql": "select * from tickets"},
        )
        three_d_response = client.put(
            f"/api/genai/charts/{created['id']}",
            json={"chart_type": "scatter_3d", "display_mode": "3d"},
        )

    assert unknown_response.status_code == 422
    assert three_d_response.status_code == 200
    payload = three_d_response.json()
    assert payload["chart_type"] in {"bar", "horizontal_bar"}
    assert payload["chart_spec"]["plotly"]["data"][0]["type"] == "bar"
    assert any("three numeric measures" in warning for warning in payload["warnings"])
    assert "z" not in payload["chart_spec"]["plotly"]["data"][0]
    assert_no_forbidden_payload_markers(payload)


def test_chart_duplicate_archive_and_reset_lifecycle() -> None:
    reset_chart_editing_tables()
    with TestClient(app) as client:
        created = create_chart(client)
        update_response = client.put(
            f"/api/genai/charts/{created['id']}",
            json={"title": "Edited Chart", "chart_type": "horizontal_bar"},
        )
        duplicate_response = client.post(
            f"/api/genai/charts/{created['id']}/duplicate",
            json={"title": "Copy of Edited Chart"},
        )
        duplicate = duplicate_response.json()
        archive_response = client.post(f"/api/genai/charts/{duplicate['id']}/archive")
        list_response = client.get("/api/genai/charts")
        direct_archived_response = client.get(f"/api/genai/charts/{duplicate['id']}")
        reset_response = client.post(f"/api/genai/charts/{created['id']}/reset")

    assert update_response.status_code == 200
    assert duplicate_response.status_code == 200
    assert duplicate["id"] != created["id"]
    assert duplicate["title"] == "Copy of Edited Chart"
    assert duplicate["parameters"]["source_chart_id"] == created["id"]
    assert archive_response.status_code == 200
    assert archive_response.json()["is_archived"] is True
    visible_ids = {item["id"] for item in list_response.json()["items"]}
    assert duplicate["id"] not in visible_ids
    assert direct_archived_response.status_code == 200
    assert direct_archived_response.json()["is_archived"] is True
    assert reset_response.status_code == 200
    reset_payload = reset_response.json()
    assert reset_payload["title"] == "Application Distribution"
    assert reset_payload["chart_type"] == created["chart_type"]
    assert_no_forbidden_payload_markers(reset_payload)


def test_scatter_3d_requires_real_three_numeric_measures() -> None:
    reset_chart_editing_tables()
    with TestClient(app) as client:
        created = create_chart(client, three_metric_tool_result())
        response = client.put(
            f"/api/genai/charts/{created['id']}",
            json={
                "chart_type": "scatter_3d",
                "display_mode": "3d",
                "x_axis_title": "X",
                "y_axis_title": "Y",
                "z_axis_title": "Z",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    trace = payload["chart_spec"]["plotly"]["data"][0]
    assert payload["chart_type"] == "scatter_3d"
    assert trace["type"] == "scatter3d"
    assert trace["x"] == [1, 2]
    assert trace["y"] == [5, 6]
    assert trace["z"] == [9, 12]
    assert payload["chart_spec"]["plotly"]["layout"]["scene"]["zaxis"]["title"]["text"] == "Z"
    assert_no_forbidden_payload_markers(payload)
