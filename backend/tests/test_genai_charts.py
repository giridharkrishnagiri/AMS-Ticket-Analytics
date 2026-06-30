from __future__ import annotations

import json
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.db.session import SessionLocal
from app.main import app
from app.models import GenAIGeneratedChart, GenAIUsageLog
from app.services.genai.charts.chart_builder import build_chart_from_tool_result
from app.services.genai.charts.validation import ChartValidationError, validate_chart_type


def reset_chart_tables() -> None:
    db = SessionLocal()
    try:
        db.execute(delete(GenAIGeneratedChart))
        db.execute(delete(GenAIUsageLog).where(GenAIUsageLog.operation == "chart_generation"))
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
        ],
        "applied_filters": {"dimension": "functional_track"},
        "data_notes": ["Application Inventory is the only application reference source."],
        "warnings": [],
        "row_count": len(rows or [1, 2]),
        "truncated": False,
    }


def trend_tool_result() -> dict[str, Any]:
    return {
        "tool_name": "get_ticket_trend_summary",
        "domain": "tickets",
        "status": "success",
        "summary": {"title": "Ticket Trend Summary", "description": "Monthly ticket trend."},
        "columns": [
            {"key": "period", "label": "Period", "type": "string"},
            {"key": "created_count", "label": "Created", "type": "number"},
            {"key": "resolved_closed_count", "label": "Resolved", "type": "number"},
        ],
        "rows": [
            {"period": "2026-04", "created_count": 10, "resolved_closed_count": 8},
            {"period": "2026-05", "created_count": 12, "resolved_closed_count": 11},
        ],
        "data_notes": ["Generic Tickets includes Incidents and SC Tasks only."],
        "warnings": [],
        "row_count": 2,
        "truncated": False,
    }


def test_chart_type_validation_and_json_safety() -> None:
    assert validate_chart_type("bar") == "bar"
    try:
        validate_chart_type("javascript")
    except ChartValidationError:
        pass
    else:
        raise AssertionError("Invalid chart type should be rejected.")

    chart = build_chart_from_tool_result(category_tool_result(), question="Plot applications.")
    json.dumps(chart.chart_spec)
    rendered = json.dumps(chart.chart_spec).lower()
    assert "callback" not in rendered
    assert "javascript:" not in rendered
    assert "normalized_payload" not in rendered
    assert "cmdb_payload" not in rendered


def test_chart_builder_category_metric_and_long_labels() -> None:
    chart = build_chart_from_tool_result(category_tool_result(), question="Plot applications.")
    assert chart.chart_type == "bar"
    assert chart.chart_spec["plotly"]["data"][0]["type"] == "bar"

    long_rows = [
        {"dimension": "Global Finance Transformation Application Suite", "application_count": 12},
        {"dimension": "Supply Chain Planning", "application_count": 8},
    ]
    long_label_chart = build_chart_from_tool_result(
        category_tool_result(long_rows),
        question="Create a bar chart of applications.",
    )
    assert long_label_chart.chart_type == "horizontal_bar"
    assert long_label_chart.chart_spec["plotly"]["data"][0]["orientation"] == "h"


def test_chart_builder_trend_and_pie_fallback_rules() -> None:
    trend_chart = build_chart_from_tool_result(
        trend_tool_result(),
        question="Create a line chart of monthly ticket volume.",
    )
    assert trend_chart.chart_type == "multi_line"
    assert len(trend_chart.chart_spec["plotly"]["data"]) == 2

    pie_chart = build_chart_from_tool_result(
        category_tool_result(),
        question="Show applications by functional track as a pie chart.",
    )
    assert pie_chart.chart_type == "pie"

    many_rows = [
        {"dimension": f"Track {index}", "application_count": index}
        for index in range(1, 15)
    ]
    fallback_chart = build_chart_from_tool_result(
        category_tool_result(many_rows),
        question="Show applications by functional track as a pie chart.",
    )
    assert fallback_chart.chart_type == "horizontal_bar"
    assert any("Pie and donut charts are capped" in warning for warning in fallback_chart.warnings)


def test_chart_builder_enforces_max_data_points_and_three_d_fallback() -> None:
    many_rows = [
        {"dimension": f"Track {index}", "application_count": index}
        for index in range(1, 8)
    ]
    chart = build_chart_from_tool_result(
        category_tool_result(many_rows),
        question="Plot a 3D chart of applications by functional track.",
        max_data_points=3,
    )
    assert len(chart.table["rows"]) == 3
    assert chart.chart_type in {"bar", "horizontal_bar"}
    assert any("three numeric measures" in warning for warning in chart.warnings)
    assert any("capped at 3 points" in warning for warning in chart.warnings)


def test_generated_chart_api_persists_and_returns_safe_specs() -> None:
    reset_chart_tables()
    with TestClient(app) as client:
        create_response = client.post(
            "/api/genai/charts/from-tool-result",
            json={
                "tool_result": category_tool_result(),
                "question": "Plot applications by functional track.",
            },
        )
        assert create_response.status_code == 200
        created = create_response.json()
        list_response = client.get("/api/genai/charts", params={"limit": 10})
        detail_response = client.get(f"/api/genai/charts/{created['id']}")

    assert list_response.status_code == 200
    assert detail_response.status_code == 200
    assert list_response.json()["total"] >= 1
    detail = detail_response.json()
    assert detail["chart_type"] == "bar"
    assert detail["chart_library"] == "plotly"
    assert detail["table"]["rows"][0]["dimension"] == "Finance"
    rendered = json.dumps(detail).lower()
    assert "normalized_payload" not in rendered
    assert "cmdb_payload" not in rendered
