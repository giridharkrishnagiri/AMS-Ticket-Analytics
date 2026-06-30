from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.services.genai.charts.validation import (
    ChartValidationError,
    assert_no_forbidden_markers,
    ensure_json_serializable,
    sanitize_chart_json,
    validate_chart_type,
)


@dataclass(frozen=True)
class BuiltChart:
    title: str
    subtitle: str | None
    chart_type: str
    chart_library: str
    chart_spec: dict[str, Any]
    table: dict[str, Any]
    source_tool_names: list[str]
    source_tool_results_summary: list[dict[str, Any]]
    parameters: dict[str, Any]
    filters: dict[str, Any]
    data_notes: list[str]
    warnings: list[str]


def _column_key(column: Any) -> str:
    if isinstance(column, dict):
        return str(column.get("key") or "")
    return str(getattr(column, "key", "") or "")


def _column_label(column: Any) -> str:
    if isinstance(column, dict):
        return str(column.get("label") or column.get("key") or "")
    return str(getattr(column, "label", "") or getattr(column, "key", "") or "")


def _column_type(column: Any) -> str:
    if isinstance(column, dict):
        return str(column.get("type") or "string")
    return str(getattr(column, "type", "string") or "string")


def _as_columns(tool_result: dict[str, Any]) -> list[dict[str, str]]:
    columns = tool_result.get("columns")
    if isinstance(columns, list) and columns:
        return [
            {
                "key": _column_key(column),
                "label": _column_label(column),
                "type": _column_type(column),
            }
            for column in columns
            if _column_key(column)
        ]
    rows = tool_result.get("rows") if isinstance(tool_result.get("rows"), list) else []
    if not rows:
        return []
    first_row = rows[0]
    if not isinstance(first_row, dict):
        return []
    return [
        {
            "key": key,
            "label": key.replace("_", " ").title(),
            "type": "number" if _is_number(value) else "string",
        }
        for key, value in first_row.items()
    ]


def _rows(tool_result: dict[str, Any]) -> list[dict[str, Any]]:
    rows = tool_result.get("rows")
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def _summary(tool_result: dict[str, Any]) -> dict[str, Any]:
    summary = tool_result.get("summary")
    return summary if isinstance(summary, dict) else {}


def _is_number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _numeric_keys(columns: list[dict[str, str]], rows: list[dict[str, Any]]) -> list[str]:
    keys: list[str] = []
    for column in columns:
        key = column["key"]
        if column.get("type") == "number" or any(_is_number(row.get(key)) for row in rows):
            keys.append(key)
    return keys


def _category_keys(columns: list[dict[str, str]], numeric_keys: list[str]) -> list[str]:
    numeric = set(numeric_keys)
    return [column["key"] for column in columns if column["key"] not in numeric]


def _is_period_value(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    return bool(re.match(r"^\d{4}(-\d{2})?($|[-/]\d{2})", value.strip()))


def _time_key(columns: list[dict[str, str]], rows: list[dict[str, Any]]) -> str | None:
    preferred = {"period", "month", "week", "date"}
    for column in columns:
        key = column["key"]
        if key in preferred:
            return key
    for column in columns:
        key = column["key"]
        if any(_is_period_value(row.get(key)) for row in rows[:5]):
            return key
    return None


def _requested_chart_type(
    question: str | None,
    explicit: str | None,
) -> tuple[str | None, list[str]]:
    warnings: list[str] = []
    if explicit:
        return validate_chart_type(explicit), warnings
    text = (question or "").lower()
    if re.search(r"\b(3d|3-d|three dimensional|three-dimensional)\b", text):
        return "scatter_3d", warnings
    if "donut" in text or "doughnut" in text:
        return "donut", warnings
    if "pie" in text:
        return "pie", warnings
    if "line" in text or "trend" in text or "monthly" in text:
        return "line", warnings
    if "scatter" in text:
        return "scatter", warnings
    if "horizontal" in text:
        return "horizontal_bar", warnings
    if "bar" in text or "plot" in text or "chart" in text or "graph" in text:
        return "bar", warnings
    return None, warnings


def _metric_key(question: str | None, numeric_keys: list[str]) -> str | None:
    if not numeric_keys:
        return None
    text = (question or "").lower()
    preferred = (
        ("adherence_percent", ("adherence", "sla", "ola")),
        ("active_users", ("active user", "users")),
        ("created_count", ("created", "ticket", "volume")),
        ("resolved_closed_count", ("resolved", "closed")),
        ("canceled_closed_incomplete_count", ("cancel", "incomplete")),
        ("application_count", ("application", "inventory")),
        ("value", ("count", "total")),
    )
    for key, hints in preferred:
        if key in numeric_keys and (not hints or any(hint in text for hint in hints)):
            return key
    for key in (
        "created_count",
        "application_count",
        "active_users",
        "adherence_percent",
        "value",
    ):
        if key in numeric_keys:
            return key
    return numeric_keys[0]


def _label_for(columns: list[dict[str, str]], key: str) -> str:
    for column in columns:
        if column["key"] == key:
            return column.get("label") or key.replace("_", " ").title()
    return key.replace("_", " ").title()


def _append_warning(warnings: list[str], warning: str) -> None:
    if warning not in warnings:
        warnings.append(warning)


def _select_chart_type(
    *,
    requested: str | None,
    rows: list[dict[str, Any]],
    category_key: str | None,
    numeric_keys: list[str],
    time_key: str | None,
    metric_key: str | None,
    warnings: list[str],
) -> str:
    if not rows or not metric_key:
        return "table"
    measure_keys = [key for key in numeric_keys if key != time_key]
    if requested == "table":
        return "table"
    if requested == "scatter_3d":
        if len(measure_keys) >= 3:
            return "scatter_3d"
        _append_warning(
            warnings,
            "This governed dataset does not have three numeric measures required for a 3D "
            "chart. The chart was kept as a compatible 2D chart.",
        )
    if requested == "scatter":
        if len(measure_keys) >= 2:
            return "scatter"
        _append_warning(
            warnings,
            "Scatter charts require at least two numeric measures. A compatible chart type was "
            "used instead.",
        )
    if requested in {"grouped_bar", "stacked_bar"}:
        if category_key and len(measure_keys) >= 2:
            return requested
        _append_warning(
            warnings,
            "Grouped and stacked bar charts require one category and at least two numeric "
            "measures. A compatible chart type was used instead.",
        )
    if requested in {"pie", "donut"} and category_key:
        if len(rows) > 12:
            _append_warning(
                warnings,
                "Pie and donut charts are capped at 12 slices; "
                "a horizontal bar chart was generated instead.",
            )
            return "horizontal_bar"
        return requested
    if requested in {"pie", "donut"}:
        _append_warning(
            warnings,
            "Pie and donut charts require one category and one numeric measure. A compatible "
            "chart type was used instead.",
        )
    if requested in {"line", "multi_line"} and time_key:
        return "multi_line" if len(measure_keys) > 1 else "line"
    if requested in {"line", "multi_line"}:
        _append_warning(
            warnings,
            "Line charts require a time period field. A compatible chart type was used instead.",
        )
    if time_key and len(measure_keys) > 1:
        return "multi_line"
    if time_key:
        return "line"
    if category_key:
        labels = [str(row.get(category_key) or "") for row in rows]
        has_long_label = any(len(label) > 22 for label in labels)
        if requested == "horizontal_bar" or has_long_label or len(rows) > 8:
            return "horizontal_bar"
        if requested in {None, "bar", "grouped_bar", "stacked_bar", "scatter", "scatter_3d"}:
            return "bar"
        return requested
    return "table"


def _base_layout(title: str, subtitle: str | None) -> dict[str, Any]:
    rendered_title = title if not subtitle else f"{title}<br><sup>{subtitle}</sup>"
    return {
        "title": {"text": rendered_title},
        "paper_bgcolor": "#ffffff",
        "plot_bgcolor": "#ffffff",
        "margin": {"l": 80, "r": 32, "t": 88, "b": 72},
        "font": {"family": "Arial, sans-serif", "size": 13, "color": "#10233f"},
    }


def _table_trace(columns: list[dict[str, str]], rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    labels = [_label_for(columns, column["key"]) for column in columns]
    values = [[row.get(column["key"]) for row in rows] for column in columns]
    return [
        {
            "type": "table",
            "header": {"values": labels, "fill": {"color": "#e6f2f1"}, "align": "left"},
            "cells": {"values": values, "align": "left", "height": 28},
        }
    ]


def _build_plotly(
    *,
    chart_type: str,
    title: str,
    subtitle: str | None,
    columns: list[dict[str, str]],
    rows: list[dict[str, Any]],
    category_key: str | None,
    metric_key: str | None,
    numeric_keys: list[str],
    time_key: str | None,
    show_labels: bool = True,
    show_legend: bool = True,
    x_axis_title: str | None = None,
    y_axis_title: str | None = None,
    z_axis_title: str | None = None,
) -> dict[str, Any]:
    layout = _base_layout(title, subtitle)
    config = {"responsive": True, "displaylogo": False}
    if chart_type == "table" or not metric_key:
        return {"data": _table_trace(columns, rows), "layout": layout, "config": config}

    metric_label = _label_for(columns, metric_key)
    category_label = _label_for(columns, category_key or time_key or "")
    measure_keys = [key for key in numeric_keys if key != time_key]
    layout["showlegend"] = show_legend

    if chart_type == "horizontal_bar":
        y_values = [row.get(category_key or time_key or "") for row in rows]
        x_values = [row.get(metric_key) for row in rows]
        layout.update(
            {
                "xaxis": {"title": {"text": x_axis_title or metric_label}},
                "yaxis": {"title": {"text": y_axis_title or category_label}, "automargin": True},
            }
        )
        trace: dict[str, Any] = {
            "type": "bar",
            "orientation": "h",
            "x": x_values,
            "y": y_values,
            "marker": {"color": "#0f766e"},
            "showlegend": show_legend,
        }
        if show_labels:
            trace.update({"text": x_values, "textposition": "auto"})
        return {
            "data": [trace],
            "layout": layout,
            "config": config,
        }

    if chart_type == "bar":
        x_values = [row.get(category_key or time_key or "") for row in rows]
        y_values = [row.get(metric_key) for row in rows]
        layout.update(
            {
                "xaxis": {"title": {"text": x_axis_title or category_label}, "automargin": True},
                "yaxis": {"title": {"text": y_axis_title or metric_label}},
            }
        )
        trace = {
            "type": "bar",
            "x": x_values,
            "y": y_values,
            "marker": {"color": "#2563eb"},
            "showlegend": show_legend,
        }
        if show_labels:
            trace.update({"text": y_values, "textposition": "auto"})
        return {
            "data": [trace],
            "layout": layout,
            "config": config,
        }

    if chart_type in {"grouped_bar", "stacked_bar"} and category_key and len(measure_keys) >= 2:
        layout.update(
            {
                "barmode": "stack" if chart_type == "stacked_bar" else "group",
                "xaxis": {"title": {"text": x_axis_title or category_label}, "automargin": True},
                "yaxis": {"title": {"text": y_axis_title or "Value"}},
            }
        )
        return {
            "data": [
                {
                    "type": "bar",
                    "name": _label_for(columns, key),
                    "x": [row.get(category_key) for row in rows],
                    "y": [row.get(key) for row in rows],
                    "text": [row.get(key) for row in rows] if show_labels else None,
                    "textposition": "auto" if show_labels else None,
                    "showlegend": show_legend,
                }
                for key in measure_keys
            ],
            "layout": layout,
            "config": config,
        }

    if chart_type in {"pie", "donut"}:
        layout.update({"margin": {"l": 32, "r": 32, "t": 88, "b": 48}})
        return {
            "data": [
                {
                    "type": "pie",
                    "labels": [row.get(category_key or "") for row in rows],
                    "values": [row.get(metric_key) for row in rows],
                    "hole": 0.45 if chart_type == "donut" else 0,
                    "textinfo": "label+percent" if show_labels else "none",
                    "showlegend": show_legend,
                }
            ],
            "layout": layout,
            "config": config,
        }

    if chart_type in {"line", "multi_line"} and time_key:
        line_keys = [key for key in numeric_keys if key != time_key]
        if chart_type == "line":
            line_keys = [metric_key]
        layout.update(
            {
                "xaxis": {"title": {"text": x_axis_title or _label_for(columns, time_key)}},
                "yaxis": {"title": {"text": y_axis_title or "Count"}},
            }
        )
        return {
            "data": [
                {
                    "type": "scatter",
                    "mode": "lines+markers",
                    "name": _label_for(columns, key),
                    "x": [row.get(time_key) for row in rows],
                    "y": [row.get(key) for row in rows],
                    "text": [row.get(key) for row in rows] if show_labels else None,
                    "showlegend": show_legend,
                }
                for key in line_keys
            ],
            "layout": layout,
            "config": config,
        }

    if chart_type == "scatter" and len(measure_keys) >= 2:
        x_key, y_key = measure_keys[:2]
        text_key = category_key
        layout.update(
            {
                "xaxis": {"title": {"text": x_axis_title or _label_for(columns, x_key)}},
                "yaxis": {"title": {"text": y_axis_title or _label_for(columns, y_key)}},
            }
        )
        return {
            "data": [
                {
                    "type": "scatter",
                    "mode": "markers",
                    "x": [row.get(x_key) for row in rows],
                    "y": [row.get(y_key) for row in rows],
                    "text": [row.get(text_key) for row in rows] if text_key else None,
                    "marker": {"color": "#7c3aed", "size": 10},
                    "showlegend": show_legend,
                }
            ],
            "layout": layout,
            "config": config,
        }

    if chart_type == "scatter_3d" and len(measure_keys) >= 3:
        x_key, y_key, z_key = measure_keys[:3]
        text_key = category_key
        layout.update(
            {
                "scene": {
                    "xaxis": {"title": {"text": x_axis_title or _label_for(columns, x_key)}},
                    "yaxis": {"title": {"text": y_axis_title or _label_for(columns, y_key)}},
                    "zaxis": {"title": {"text": z_axis_title or _label_for(columns, z_key)}},
                }
            }
        )
        return {
            "data": [
                {
                    "type": "scatter3d",
                    "mode": "markers",
                    "x": [row.get(x_key) for row in rows],
                    "y": [row.get(y_key) for row in rows],
                    "z": [row.get(z_key) for row in rows],
                    "text": [row.get(text_key) for row in rows] if text_key else None,
                    "marker": {"color": "#7c3aed", "size": 5},
                    "showlegend": show_legend,
                }
            ],
            "layout": layout,
            "config": config,
        }

    return {"data": _table_trace(columns, rows), "layout": layout, "config": config}


def _columns_from_table(table: dict[str, Any]) -> list[dict[str, str]]:
    columns = table.get("columns") if isinstance(table, dict) else []
    if not isinstance(columns, list):
        return []
    return [
        {
            "key": _column_key(column),
            "label": _column_label(column),
            "type": _column_type(column),
        }
        for column in columns
        if _column_key(column)
    ]


def _rows_from_table(table: dict[str, Any]) -> list[dict[str, Any]]:
    rows = table.get("rows") if isinstance(table, dict) else []
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def _sort_rows(
    rows: list[dict[str, Any]],
    *,
    sort_order: str,
    metric_key: str | None,
) -> list[dict[str, Any]]:
    if sort_order == "original" or not metric_key:
        return list(rows)

    def sort_value(row: dict[str, Any]) -> float:
        value = row.get(metric_key)
        return float(value) if _is_number(value) else float("-inf")

    return sorted(rows, key=sort_value, reverse=sort_order == "descending")


def _requested_from_settings(
    *,
    chart_type: str | None,
    orientation: str | None,
    display_mode: str | None,
    current_chart_type: str | None,
) -> str | None:
    requested = validate_chart_type(chart_type) if chart_type else current_chart_type
    if display_mode == "3d":
        return "scatter_3d"
    if orientation == "horizontal" and requested in {None, "bar", "horizontal_bar"}:
        return "horizontal_bar"
    if orientation == "vertical" and requested in {"horizontal_bar", "bar"}:
        return "bar"
    return validate_chart_type(requested) if requested else None


def build_chart_from_table(
    table: dict[str, Any],
    *,
    title: str,
    subtitle: str | None,
    current_chart_type: str | None,
    source_tool_names: list[str] | None = None,
    source_tool_results_summary: list[dict[str, Any]] | None = None,
    parameters: dict[str, Any] | None = None,
    filters: dict[str, Any] | None = None,
    data_notes: list[str] | None = None,
    warnings: list[str] | None = None,
    chart_type: str | None = None,
    orientation: str | None = None,
    display_mode: str | None = None,
    show_labels: bool = True,
    show_legend: bool = True,
    sort_order: str = "original",
    top_n: int | None = None,
    x_axis_title: str | None = None,
    y_axis_title: str | None = None,
    z_axis_title: str | None = None,
    max_data_points: int = 500,
) -> BuiltChart:
    columns = _columns_from_table(table)
    rows = _rows_from_table(table)
    if not columns and rows:
        columns = _as_columns({"rows": rows})
    build_warnings = list(warnings or [])
    requested = _requested_from_settings(
        chart_type=chart_type,
        orientation=orientation,
        display_mode=display_mode,
        current_chart_type=current_chart_type,
    )

    max_points = max(1, int(max_data_points or 500))
    if top_n is not None and top_n > max_points:
        _append_warning(
            build_warnings,
            f"Top N was capped at {max_points} points by GenAI safety settings.",
        )
    row_limit = min(top_n or max_points, max_points)

    numeric_keys = _numeric_keys(columns, rows)
    time_key = _time_key(columns, rows)
    category_keys = [key for key in _category_keys(columns, numeric_keys) if key != time_key]
    category_key = category_keys[0] if category_keys else time_key
    metric_key = _metric_key(None, [key for key in numeric_keys if key != time_key])
    rows = _sort_rows(rows, sort_order=sort_order, metric_key=metric_key)

    truncated = False
    if len(rows) > row_limit:
        rows = rows[:row_limit]
        truncated = True
        _append_warning(
            build_warnings,
            f"Chart data was capped at {row_limit} points by GenAI safety settings.",
        )

    chart_type_value = _select_chart_type(
        requested=requested,
        rows=rows,
        category_key=category_key,
        numeric_keys=numeric_keys,
        time_key=time_key,
        metric_key=metric_key,
        warnings=build_warnings,
    )
    chart_type_value = validate_chart_type(chart_type_value)

    plotly = _build_plotly(
        chart_type=chart_type_value,
        title=title,
        subtitle=subtitle,
        columns=columns,
        rows=rows,
        category_key=category_key,
        metric_key=metric_key,
        numeric_keys=numeric_keys,
        time_key=time_key,
        show_labels=show_labels,
        show_legend=show_legend,
        x_axis_title=x_axis_title,
        y_axis_title=y_axis_title,
        z_axis_title=z_axis_title,
    )
    rebuilt_table: dict[str, Any] = {"columns": columns, "rows": rows}
    if truncated:
        rebuilt_table["truncated"] = True

    presentation_settings = {
        "orientation": orientation,
        "display_mode": "3d" if chart_type_value == "scatter_3d" else "2d",
        "show_labels": show_labels,
        "show_legend": show_legend,
        "sort_order": sort_order,
        "top_n": top_n,
        "x_axis_title": x_axis_title,
        "y_axis_title": y_axis_title,
        "z_axis_title": z_axis_title,
    }
    chart_spec = {
        "title": title,
        "subtitle": subtitle,
        "chart_type": chart_type_value,
        "chart_library": "plotly",
        "plotly": plotly,
        "table": rebuilt_table,
        "data_notes": list(data_notes or []),
        "warnings": build_warnings,
        "presentation_settings": presentation_settings,
    }
    chart_spec = sanitize_chart_json(chart_spec)
    assert_no_forbidden_markers(chart_spec)
    ensure_json_serializable(chart_spec)

    return BuiltChart(
        title=title,
        subtitle=subtitle,
        chart_type=chart_type_value,
        chart_library="plotly",
        chart_spec=chart_spec,
        table=rebuilt_table,
        source_tool_names=list(source_tool_names or []),
        source_tool_results_summary=list(source_tool_results_summary or []),
        parameters=parameters or {},
        filters=filters or {},
        data_notes=list(data_notes or []),
        warnings=build_warnings,
    )


def build_chart_from_tool_result(
    tool_result: dict[str, Any],
    *,
    question: str | None = None,
    requested_chart_type: str | None = None,
    max_data_points: int = 500,
) -> BuiltChart:
    if not isinstance(tool_result, dict):
        raise ChartValidationError("Tool result must be a JSON object.")
    status = str(tool_result.get("status") or "")
    if status not in {"success", "unsupported"}:
        raise ChartValidationError(
            "Only successful or unsupported governed tool results can be charted."
        )

    columns = _as_columns(tool_result)
    rows = _rows(tool_result)
    raw_warnings = tool_result.get("warnings")
    raw_data_notes = tool_result.get("data_notes")
    warnings = list(raw_warnings if isinstance(raw_warnings, list) else [])
    data_notes = list(raw_data_notes if isinstance(raw_data_notes, list) else [])
    requested, request_warnings = _requested_chart_type(question, requested_chart_type)
    warnings.extend(request_warnings)

    max_points = max(1, int(max_data_points or 500))
    truncated = False
    if len(rows) > max_points:
        rows = rows[:max_points]
        truncated = True
        warnings.append(
            f"Chart data was capped at {max_points} points by GenAI safety settings."
        )

    numeric_keys = _numeric_keys(columns, rows)
    time_key = _time_key(columns, rows)
    category_keys = [key for key in _category_keys(columns, numeric_keys) if key != time_key]
    category_key = category_keys[0] if category_keys else time_key
    metric_key = _metric_key(question, [key for key in numeric_keys if key != time_key])
    chart_type = _select_chart_type(
        requested=requested,
        rows=rows,
        category_key=category_key,
        numeric_keys=numeric_keys,
        time_key=time_key,
        metric_key=metric_key,
        warnings=warnings,
    )
    chart_type = validate_chart_type(chart_type)

    summary = _summary(tool_result)
    title = str(summary.get("title") or tool_result.get("tool_name") or "Generated Chart")
    subtitle = summary.get("description")
    if subtitle is not None:
        subtitle = str(subtitle)

    plotly = _build_plotly(
        chart_type=chart_type,
        title=title,
        subtitle=subtitle,
        columns=columns,
        rows=rows,
        category_key=category_key,
        metric_key=metric_key,
        numeric_keys=numeric_keys,
        time_key=time_key,
    )
    table = {"columns": columns, "rows": rows}
    if truncated:
        table["truncated"] = True

    chart_spec = {
        "title": title,
        "subtitle": subtitle,
        "chart_type": chart_type,
        "chart_library": "plotly",
        "plotly": plotly,
        "table": table,
        "data_notes": data_notes,
        "warnings": warnings,
    }
    chart_spec = sanitize_chart_json(chart_spec)
    assert_no_forbidden_markers(chart_spec)
    ensure_json_serializable(chart_spec)

    tool_name = str(tool_result.get("tool_name") or "")
    return BuiltChart(
        title=title,
        subtitle=subtitle,
        chart_type=chart_type,
        chart_library="plotly",
        chart_spec=chart_spec,
        table=table,
        source_tool_names=[tool_name] if tool_name else [],
        source_tool_results_summary=[
            {
                "tool_name": tool_name,
                "status": status,
                "row_count": tool_result.get("row_count", len(rows)),
                "truncated": bool(tool_result.get("truncated")) or truncated,
            }
        ],
        parameters={},
        filters=tool_result.get("applied_filters")
        if isinstance(tool_result.get("applied_filters"), dict)
        else {},
        data_notes=data_notes,
        warnings=warnings,
    )
