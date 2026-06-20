from datetime import datetime

from pydantic import BaseModel


class PeriodMetricRow(BaseModel):
    period_start: datetime
    period_end: datetime
    period_label: str


class CreatedResolvedOpenRow(PeriodMetricRow):
    created_count: int
    resolved_count: int
    open_end_count: int


class MttrTrendRow(PeriodMetricRow):
    completed_ticket_count: int
    mttr_actual_days: float | None
    mttr_business_days: float | None


class SlaTrendRow(PeriodMetricRow):
    total_tickets_with_sla: int
    sla_met_count: int
    sla_breached_count: int
    sla_unknown_count: int
    sla_met_percentage: float | None
    sla_breached_percentage: float | None


class IncidentSlaTrendRow(PeriodMetricRow):
    period: str
    incident_count: int
    response_sla_applicable_count: int
    response_sla_met_count: int
    response_sla_breached_count: int
    response_sla_adherence_pct: float | None
    response_sla_breach_pct: float | None
    response_sla_avg_business_elapsed_seconds: float | None
    response_sla_avg_business_elapsed_hours: float | None
    resolution_sla_applicable_count: int
    resolution_sla_met_count: int
    resolution_sla_breached_count: int
    resolution_sla_adherence_pct: float | None
    resolution_sla_breach_pct: float | None
    resolution_sla_avg_business_elapsed_seconds: float | None
    resolution_sla_avg_business_elapsed_hours: float | None


class IncidentSlaSummaryResponse(BaseModel):
    incident_count: int
    response_sla_applicable_count: int
    response_sla_met_count: int
    response_sla_breached_count: int
    response_sla_adherence_pct: float | None
    response_sla_breach_pct: float | None
    response_sla_avg_business_elapsed_hours: float | None
    resolution_sla_applicable_count: int
    resolution_sla_met_count: int
    resolution_sla_breached_count: int
    resolution_sla_adherence_pct: float | None
    resolution_sla_breach_pct: float | None
    resolution_sla_avg_business_elapsed_hours: float | None
    response_accenture_count: int
    response_default_count: int
    resolution_accenture_count: int
    resolution_default_count: int


class IncidentSlaNameBreakdownItem(BaseModel):
    sla_name: str
    ticket_count: int
    met_count: int
    breached_count: int
    adherence_pct: float | None
    breach_pct: float | None
    avg_business_elapsed_hours: float | None


class IncidentSlaNameBreakdownResponse(BaseModel):
    response_sla_names: list[IncidentSlaNameBreakdownItem]
    resolution_sla_names: list[IncidentSlaNameBreakdownItem]


class ReopenTrendRow(PeriodMetricRow):
    total_tickets: int
    reopened_ticket_count: int
    total_reopen_count: int
    average_reopen_count: float | None


class ReassignmentTrendRow(PeriodMetricRow):
    total_tickets: int
    tickets_with_more_than_2_reassignments: int
    total_reassignment_count: int
    average_reassignment_count: float | None


class CreationSourceTrendRow(PeriodMetricRow):
    user_created_count: int
    system_created_count: int
    unknown_count: int


class TechnicalFunctionalBreakdownResponse(BaseModel):
    technical_count: int
    functional_count: int
    unknown_count: int
    not_applicable_count: int


class FilterValuesResponse(BaseModel):
    ticket_types: list[str]
    priorities: list[str]
    states: list[str]
    assignment_groups: list[str]
    applications: list[str]
    customers: list[str]
    towers: list[str]
    clusters: list[str]
    application_groups: list[str]
    application_names: list[str]
    month_keys: list[str]
    response_sla_names: list[str]
    resolution_sla_names: list[str]
    functional_tracks: list[str]
    ams_owners: list[str]
    supported_by_vendors: list[str]
    support_leads: list[str]
    application_owners: list[str]
    business_service_ci_names: list[str]
    parent_application_names: list[str]
