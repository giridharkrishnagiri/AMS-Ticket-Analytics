from __future__ import annotations

from typing import Any

from sqlalchemy import desc, func, or_, select
from sqlalchemy.orm import Session

from app.models import ApplicationInventoryItem
from app.schemas.genai import GenAIToolColumn, GenAIToolExecuteResponse
from app.services.genai.tools.base import ToolExecutionRequest, ToolMetadata, tool_response
from app.services.genai.tools.validation import (
    ToolValidationError,
    apply_project_context,
    cap_rows,
    clean_text,
    distinct_nonblank_count_expression,
    ensure_allowed,
    lower_trim_expression,
    max_rows_from_safety,
    normalized_bool,
    normalized_key,
    project_ids_for_context,
)

APP = ApplicationInventoryItem

APPLICATION_DATA_NOTES = [
    "Application Inventory is the only application reference source.",
    "Counts use distinct Business Service CI Name where applicable.",
    "Raw CMDB payload fields are not selected or exposed by GenAI governed tools.",
]

APPLICATION_FILTER_FIELDS = {
    "functional_track": APP.functional_track,
    "ams_owner": APP.ams_owner,
    "supported_by_vendor": APP.supported_by_vendor,
    "parent_business_application": APP.parent_application_name,
    "parent_application_name": APP.parent_application_name,
    "application_owner": APP.application_owner,
    "assignment_group": APP.assignment_group,
    "assignment_group_support_owner": APP.assignment_group_owner,
    "sap_non_sap": APP.sap_non_sap,
    "hosting_env": APP.hosting_env,
    "global": APP.global_application,
    "global_application": APP.global_application,
    "life_cycle_stage_status": APP.lifecycle_stage_status,
    "lifecycle_stage_status": APP.lifecycle_stage_status,
}

APPLICATION_DIMENSIONS: dict[str, Any] = {
    "functional_track": APP.functional_track,
    "ams_owner": APP.ams_owner,
    "supported_by_vendor": APP.supported_by_vendor,
    "parent_business_application": APP.parent_application_name,
    "application_owner": APP.application_owner,
    "assignment_group": APP.assignment_group,
    "assignment_group_support_owner": APP.assignment_group_owner,
    "sap_non_sap": APP.sap_non_sap,
    "hosting_env": APP.hosting_env,
    "global": APP.global_application,
    "life_cycle_stage_status": APP.lifecycle_stage_status,
}

UNSUPPORTED_APPLICATION_DIMENSIONS = {
    "architecture_type",
    "application_type",
    "business_criticality",
    "install_status",
    "install_type",
    "life_cycle_stage",
}


def _metric_columns() -> list[GenAIToolColumn]:
    return [
        GenAIToolColumn(key="metric", label="Metric", type="string"),
        GenAIToolColumn(key="value", label="Value", type="number"),
    ]


def _distribution_columns(dimension_label: str) -> list[GenAIToolColumn]:
    return [
        GenAIToolColumn(key="dimension", label=dimension_label, type="string"),
        GenAIToolColumn(key="application_count", label="Applications", type="number"),
    ]


def _project_ids(db: Session, request: ToolExecutionRequest) -> list[Any] | None:
    return project_ids_for_context(
        db,
        customer_id=request.customer_id,
        project_id=request.project_id,
    )


def _apply_context_and_filters(
    statement: Any,
    db: Session,
    request: ToolExecutionRequest,
) -> tuple[Any, dict[str, list[str]], list[str]]:
    statement = apply_project_context(statement, APP, _project_ids(db, request))
    applied: dict[str, list[str]] = {}
    warnings: list[str] = []

    for raw_key, raw_values in (request.filters or {}).items():
        key = normalized_key(raw_key)
        if not key:
            continue
        if key not in APPLICATION_FILTER_FIELDS:
            if raw_values:
                warnings.append(f"Application filter '{key}' is not supported by this tool.")
            continue
        values = raw_values if isinstance(raw_values, list) else [raw_values]
        cleaned_values = [str(value).strip() for value in values if str(value).strip()]
        if not cleaned_values:
            continue
        column = APPLICATION_FILTER_FIELDS[key]
        statement = statement.where(func.btrim(column).in_(cleaned_values))
        applied[key] = cleaned_values

    return statement, applied, warnings


def _distinct_app_count(db: Session, statement: Any) -> int:
    return int(db.execute(statement).scalar_one() or 0)


def _count_distinct_apps(
    db: Session,
    request: ToolExecutionRequest,
    *,
    where_clause: Any | None = None,
) -> int:
    statement = select(
        func.count(func.distinct(func.nullif(func.btrim(APP.business_service_ci_name), "")))
    )
    statement, _, _ = _apply_context_and_filters(statement, db, request)
    if where_clause is not None:
        statement = statement.where(where_clause)
    return _distinct_app_count(db, statement)


def _normalized_dimension_expression(dimension: str) -> Any:
    if dimension == "functional_track_ams_owner":
        return func.nullif(
            func.concat_ws(
                " / ",
                func.nullif(func.btrim(APP.functional_track), ""),
                func.nullif(func.btrim(APP.ams_owner), ""),
            ),
            "",
        )
    if dimension == "assignment_group_support_owner":
        return func.nullif(
            func.concat_ws(
                " / ",
                func.nullif(func.btrim(APP.assignment_group), ""),
                func.nullif(func.btrim(APP.assignment_group_owner), ""),
            ),
            "",
        )
    return func.nullif(func.btrim(APPLICATION_DIMENSIONS[dimension]), "")


class ApplicationInventorySummaryTool:
    metadata = ToolMetadata(
        tool_name="get_application_inventory_summary",
        domain="applications",
        display_name="Application Inventory Summary",
        description="Returns high-level aggregate counts from normalized Application Inventory.",
        allowed_metrics=(
            "application_count",
            "functional_track_count",
            "ams_owner_count",
            "supported_vendor_count",
        ),
        max_rows=50,
        data_safety_level="aggregate",
    )

    def execute(self, db: Session, request: ToolExecutionRequest) -> GenAIToolExecuteResponse:
        statement = select(
            func.count(
                func.distinct(func.nullif(func.btrim(APP.business_service_ci_name), ""))
            ).label(
                "application_count",
            ),
            distinct_nonblank_count_expression(APP.functional_track).label(
                "functional_track_count"
            ),
            distinct_nonblank_count_expression(APP.ams_owner).label("ams_owner_count"),
            distinct_nonblank_count_expression(APP.supported_by_vendor).label(
                "supported_vendor_count",
            ),
            distinct_nonblank_count_expression(APP.assignment_group).label(
                "assignment_group_count"
            ),
            distinct_nonblank_count_expression(APP.application_owner).label(
                "application_owner_count",
            ),
        )
        statement, applied_filters, warnings = _apply_context_and_filters(statement, db, request)
        result = db.execute(statement).one()

        rows = [
            {"metric": "Total Applications", "value": int(result.application_count or 0)},
            {"metric": "Functional Tracks", "value": int(result.functional_track_count or 0)},
            {"metric": "AMS Owners", "value": int(result.ams_owner_count or 0)},
            {"metric": "Supported Vendors", "value": int(result.supported_vendor_count or 0)},
            {"metric": "Assignment Groups", "value": int(result.assignment_group_count or 0)},
            {"metric": "Application Owners", "value": int(result.application_owner_count or 0)},
            {
                "metric": "Global applications",
                "value": _count_distinct_apps(
                    db,
                    request,
                    where_clause=lower_trim_expression(APP.global_application).like("%global%"),
                ),
            },
            {
                "metric": "Local applications",
                "value": _count_distinct_apps(
                    db,
                    request,
                    where_clause=lower_trim_expression(APP.global_application).like("%local%"),
                ),
            },
        ]
        warnings.append(
            "Very Critical, Critical, Business application, and Technical application counts "
            "are not returned because those fields are not normalized in Application Inventory.",
        )

        return tool_response(
            metadata=self.metadata,
            status="success",
            title="Application Inventory Summary",
            description="Aggregate Application Inventory counts.",
            columns=_metric_columns(),
            rows=rows,
            applied_filters=applied_filters,
            data_notes=APPLICATION_DATA_NOTES,
            warnings=warnings,
        )


class ApplicationDistributionTool:
    metadata = ToolMetadata(
        tool_name="get_application_distribution",
        domain="applications",
        display_name="Application Distribution",
        description=(
            "Returns distinct application counts by an approved normalized inventory dimension."
        ),
        allowed_dimensions=tuple(sorted((*APPLICATION_DIMENSIONS, "functional_track_ams_owner"))),
        allowed_metrics=("application_count",),
        max_rows=100,
        data_safety_level="aggregate",
    )

    def execute(self, db: Session, request: ToolExecutionRequest) -> GenAIToolExecuteResponse:
        raw_dimension = normalized_key(request.parameters.get("dimension"))
        if raw_dimension in UNSUPPORTED_APPLICATION_DIMENSIONS:
            raise ToolValidationError(
                f"Application Inventory dimension '{raw_dimension}' is not normalized and cannot "
                "be served without raw CMDB payload fields.",
            )
        dimension = ensure_allowed(raw_dimension, self.metadata.allowed_dimensions, "Dimension")
        include_blank = normalized_bool(request.parameters.get("include_blank"), False)
        max_rows = max_rows_from_safety(
            request.parameters,
            request.safety_settings,
            default=10,
            tool_max_rows=self.metadata.max_rows,
        )
        dimension_expr = _normalized_dimension_expression(dimension)
        display_expr = func.coalesce(dimension_expr, "Unspecified")
        statement = (
            select(
                display_expr.label("dimension"),
                func.count(
                    func.distinct(func.nullif(func.btrim(APP.business_service_ci_name), ""))
                ).label(
                    "application_count",
                ),
            )
            .group_by(display_expr)
            .order_by(desc("application_count"), display_expr)
            .limit(max_rows + 1)
        )
        statement, applied_filters, warnings = _apply_context_and_filters(statement, db, request)
        if not include_blank:
            statement = statement.where(dimension_expr.is_not(None))
        rows = [
            {
                "dimension": clean_text(row.dimension, blank_label="Unspecified"),
                "application_count": int(row.application_count or 0),
            }
            for row in db.execute(statement)
        ]
        rows, truncated = cap_rows(rows, max_rows)

        return tool_response(
            metadata=self.metadata,
            status="success",
            title="Application Distribution",
            description="Distinct applications by normalized inventory dimension.",
            columns=_distribution_columns(dimension.replace("_", " ").title()),
            rows=rows,
            applied_filters={
                **applied_filters,
                "dimension": dimension,
                "include_blank": include_blank,
            },
            data_notes=APPLICATION_DATA_NOTES,
            warnings=warnings,
            truncated=truncated,
        )


class TopParentApplicationsByActiveUsersTool:
    metadata = ToolMetadata(
        tool_name="get_top_parent_applications_by_active_users",
        domain="applications",
        display_name="Top Parent Applications by Active Users",
        description=(
            "Returns top parent business applications by highest normalized active user count."
        ),
        allowed_metrics=("active_users",),
        max_rows=100,
        data_safety_level="aggregate",
    )

    def execute(self, db: Session, request: ToolExecutionRequest) -> GenAIToolExecuteResponse:
        max_rows = max_rows_from_safety(
            request.parameters,
            request.safety_settings,
            default=10,
            tool_max_rows=self.metadata.max_rows,
        )
        parent_expr = func.nullif(func.btrim(APP.parent_application_name), "")
        statement = (
            select(
                parent_expr.label("parent_business_application"),
                func.max(APP.active_users).label("active_users"),
                func.count(func.distinct(APP.active_users)).label(
                    "duplicate_active_user_count_variants"
                ),
            )
            .where(parent_expr.is_not(None), APP.active_users.is_not(None), APP.active_users > 0)
            .group_by(parent_expr)
            .order_by(desc("active_users"), parent_expr)
            .limit(max_rows + 1)
        )
        statement, applied_filters, warnings = _apply_context_and_filters(statement, db, request)
        rows = [
            {
                "parent_business_application": row.parent_business_application,
                "active_users": int(row.active_users or 0),
                "duplicate_active_user_count_variants": int(
                    row.duplicate_active_user_count_variants or 0,
                ),
            }
            for row in db.execute(statement)
        ]
        rows, truncated = cap_rows(rows, max_rows)
        if any(row["duplicate_active_user_count_variants"] > 1 for row in rows):
            warnings.append(
                "Some parent applications have multiple active-user values; "
                "the highest value is shown.",
            )

        return tool_response(
            metadata=self.metadata,
            status="success",
            title="Top Parent Applications by Active Users",
            description="Uses highest Active Users per Parent Business Application.",
            columns=[
                GenAIToolColumn(
                    key="parent_business_application",
                    label="Parent Business Application",
                    type="string",
                ),
                GenAIToolColumn(key="active_users", label="Active Users", type="number"),
                GenAIToolColumn(
                    key="duplicate_active_user_count_variants",
                    label="Duplicate Active User Count Variants",
                    type="number",
                ),
            ],
            rows=rows,
            applied_filters=applied_filters,
            data_notes=[
                *APPLICATION_DATA_NOTES,
                "If a parent application has multiple active-user counts, "
                "the highest value is used.",
            ],
            warnings=warnings,
            truncated=truncated,
        )


class ApplicationCriticalityHostingMatrixTool:
    metadata = ToolMetadata(
        tool_name="get_application_criticality_hosting_matrix",
        domain="applications",
        display_name="Application Criticality / Hosting Matrix",
        description=(
            "Returns an Application Inventory criticality by hosting matrix when normalized "
            "fields exist."
        ),
        allowed_dimensions=("business_criticality", "hosting_env"),
        allowed_metrics=("application_count",),
        max_rows=25,
        data_safety_level="aggregate",
    )

    def execute(self, db: Session, request: ToolExecutionRequest) -> GenAIToolExecuteResponse:
        return tool_response(
            metadata=self.metadata,
            status="unsupported",
            title="Application Criticality / Hosting Matrix",
            description=self.metadata.description,
            rows=[],
            data_notes=APPLICATION_DATA_NOTES,
            warnings=[
                "Application Inventory does not currently have a normalized Business "
                "Criticality field. "
                "The GenAI tool will not read raw CMDB payload fields to build this matrix.",
            ],
        )


class ApplicationLifecyclePlanningSummaryTool:
    metadata = ToolMetadata(
        tool_name="get_application_lifecycle_planning_summary",
        domain="applications",
        display_name="Application Lifecycle Planning Summary",
        description=(
            "Returns lifecycle planning matrix for In Use applications from normalized "
            "inventory fields."
        ),
        allowed_dimensions=(
            "lifecycle_current",
            "lifecycle_1_to_3_years",
            "lifecycle_3_to_5_years",
        ),
        allowed_metrics=("application_count",),
        max_rows=100,
        data_safety_level="aggregate",
    )

    def execute(self, db: Session, request: ToolExecutionRequest) -> GenAIToolExecuteResponse:
        selected_plan = normalized_key(request.parameters.get("selected_plan"))
        plan_order = ("invest", "disinvest", "maintain", "retired")
        plan_labels = {
            "invest": "Invest",
            "disinvest": "Disinvest",
            "maintain": "Maintain",
            "retired": "Retired",
        }
        horizon_columns = (
            ("current", APP.lifecycle_current),
            ("1_to_3_years", APP.lifecycle_1_to_3_years),
            ("3_to_5_years", APP.lifecycle_3_to_5_years),
        )
        base_filter = lower_trim_expression(APP.lifecycle_stage_status) == "in use"

        if selected_plan:
            if selected_plan not in plan_order:
                raise ToolValidationError(
                    "selected_plan must be Invest, Disinvest, Maintain, or Retired."
                )
            if not request.safety_settings.allow_application_detail_rows:
                raise ToolValidationError(
                    "Application detail rows are disabled by GenAI safety settings.",
                )
            max_rows = max_rows_from_safety(
                request.parameters,
                request.safety_settings,
                default=25,
                tool_max_rows=self.metadata.max_rows,
            )
            selected_conditions = [
                lower_trim_expression(column) == selected_plan for _, column in horizon_columns
            ]
            statement = (
                select(
                    APP.business_service_ci_name,
                    APP.parent_application_name,
                    APP.functional_track,
                    APP.ams_owner,
                    APP.application_owner,
                    APP.supported_by_vendor,
                    APP.lifecycle_current,
                    APP.lifecycle_1_to_3_years,
                    APP.lifecycle_3_to_5_years,
                )
                .where(base_filter, or_(*selected_conditions))
                .order_by(APP.business_service_ci_name)
                .limit(max_rows + 1)
            )
            statement, applied_filters, warnings = _apply_context_and_filters(
                statement, db, request
            )
            rows = []
            for row in db.execute(statement):
                horizons = [
                    label
                    for label, value in (
                        ("Current", row.lifecycle_current),
                        ("1 to 3 years", row.lifecycle_1_to_3_years),
                        ("3 to 5 years", row.lifecycle_3_to_5_years),
                    )
                    if normalized_key(value) == selected_plan
                ]
                rows.append(
                    {
                        "business_service_ci_name": row.business_service_ci_name,
                        "parent_business_application": row.parent_application_name,
                        "functional_track": row.functional_track,
                        "ams_owner": row.ams_owner,
                        "application_owner": row.application_owner,
                        "supported_by_vendor": row.supported_by_vendor,
                        "lifecycle_current": row.lifecycle_current,
                        "lifecycle_1_to_3_years": row.lifecycle_1_to_3_years,
                        "lifecycle_3_to_5_years": row.lifecycle_3_to_5_years,
                        "selected_plan_horizons": horizons,
                    },
                )
            rows, truncated = cap_rows(rows, max_rows)
            return tool_response(
                metadata=self.metadata,
                status="success",
                title=f"Applications with {plan_labels[selected_plan]} Lifecycle Plan",
                description="Application Inventory list capped by GenAI safety settings.",
                columns=[
                    GenAIToolColumn(
                        key="business_service_ci_name", label="Business Service CI Name"
                    ),
                    GenAIToolColumn(
                        key="parent_business_application",
                        label="Parent Business Application",
                    ),
                    GenAIToolColumn(key="functional_track", label="Functional Track"),
                    GenAIToolColumn(key="ams_owner", label="AMS Owner"),
                    GenAIToolColumn(key="application_owner", label="Application Owner"),
                    GenAIToolColumn(key="supported_by_vendor", label="Supported Vendor"),
                    GenAIToolColumn(key="selected_plan_horizons", label="Selected Plan Horizons"),
                ],
                rows=rows,
                applied_filters={**applied_filters, "selected_plan": plan_labels[selected_plan]},
                data_notes=[
                    *APPLICATION_DATA_NOTES,
                    "Application detail rows are limited to normalized Application Inventory "
                    "fields.",
                ],
                warnings=warnings,
                truncated=truncated,
            )

        rows: list[dict[str, Any]] = []
        column_totals = {key: 0 for key, _ in horizon_columns}
        grand_total = 0
        applied_filters: dict[str, Any] = {}
        warnings: list[str] = []

        for plan in plan_order:
            row: dict[str, Any] = {"plan": plan_labels[plan]}
            row_total = 0
            for horizon_key, column in horizon_columns:
                statement = select(
                    func.count(
                        func.distinct(func.nullif(func.btrim(APP.business_service_ci_name), ""))
                    ),
                ).where(base_filter, lower_trim_expression(column) == plan)
                statement, applied_filters, filter_warnings = _apply_context_and_filters(
                    statement,
                    db,
                    request,
                )
                warnings.extend(filter_warnings)
                count = int(db.execute(statement).scalar_one() or 0)
                row[horizon_key] = count
                row_total += count
                column_totals[horizon_key] += count
            row["row_total"] = row_total
            grand_total += row_total
            rows.append(row)

        return tool_response(
            metadata=self.metadata,
            status="success",
            title="Application Lifecycle Planning Summary",
            description="Lifecycle plan counts for In Use applications.",
            columns=[
                GenAIToolColumn(key="plan", label="Plan"),
                GenAIToolColumn(key="current", label="Current", type="number"),
                GenAIToolColumn(key="1_to_3_years", label="1 to 3 years", type="number"),
                GenAIToolColumn(key="3_to_5_years", label="3 to 5 years", type="number"),
                GenAIToolColumn(key="row_total", label="Row Total", type="number"),
            ],
            rows=rows,
            totals={**column_totals, "grand_total": grand_total},
            applied_filters={**applied_filters, "life_cycle_stage_status": "In Use"},
            data_notes=[
                *APPLICATION_DATA_NOTES,
                "Lifecycle planning uses only normalized lifecycle fields and In Use applications.",
            ],
            warnings=sorted(set(warnings)),
        )
