from __future__ import annotations

import csv
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import UUID

from openpyxl import load_workbook
from sqlalchemy import and_, func, select, text, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models import ApplicationInventoryItem, Project, Ticket
from app.services.ingestion import (
    CSV_ENCODING_CANDIDATES,
    INGESTION_BATCH_SIZE,
    ParsedSourceRow,
    build_raw_data,
    detect_csv_encoding,
    make_unique_headers,
    normalize_source_column_name,
    row_has_any_value,
)
from app.services.mapping import parse_bool_value, text_or_none

MAX_MESSAGE_SAMPLES = 50
TOP_UNMATCHED_LIMIT = 25
UNMATCHED_SAMPLE_LIMIT = 5
TARGET_WORKSHEET_NAME = "Group-App-BizService"

CORE_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "application_number_apm": (
        "Application Number (APM)",
        "Application Number",
        "application_number_apm",
    ),
    "parent_application_name": (
        "Parent Business Application",
        "Parent Application",
        "Parent Application Name",
    ),
    "assignment_group": ("Support group name", "Support Group", "Assignment Group"),
    "assignment_group_owner": (
        "Support group's owner",
        "Support group owner",
        "Assignment Group Owner",
    ),
    "application_owner": ("Application Owner",),
    "business_service_ci_name": ("Business Service CI Name", "Business Service"),
    "support_lead": ("Support Lead (Managed by)", "Support Lead", "Managed By"),
    "functional_track": ("Functional Track",),
    "ams_owner": ("AMS Owner",),
    "supported_by_vendor": ("Supported By Vendor", "Support vendor", "Vendor"),
    "active": ("Active",),
}
CORE_FIELD_NAMES = set(CORE_FIELD_ALIASES)
CORE_ALIAS_TO_FIELD = {
    normalize_source_column_name(alias): field_name
    for field_name, aliases in CORE_FIELD_ALIASES.items()
    for alias in aliases
}


class ApplicationInventoryError(Exception):
    pass


@dataclass(frozen=True)
class ValueCount:
    value: str
    count: int


@dataclass(frozen=True)
class UnmatchedBusinessService:
    business_service: str
    ticket_count: int
    assignment_group_count: int
    sample_assignment_groups: list[str]
    sample_ticket_numbers: list[str]


@dataclass
class InventoryUploadResult:
    project_id: UUID
    total_rows: int = 0
    inserted_count: int = 0
    updated_count: int = 0
    skipped_count: int = 0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    distinct_business_services: set[str] = field(default_factory=set)
    distinct_parent_applications: set[str] = field(default_factory=set)
    distinct_assignment_groups: set[str] = field(default_factory=set)
    distinct_application_owners: set[str] = field(default_factory=set)
    distinct_support_leads: set[str] = field(default_factory=set)
    distinct_functional_tracks: set[str] = field(default_factory=set)
    distinct_ams_owners: set[str] = field(default_factory=set)
    distinct_supported_vendors: set[str] = field(default_factory=set)

    @property
    def error_count(self) -> int:
        return len(self.errors)

    @property
    def warning_count(self) -> int:
        return len(self.warnings)


@dataclass(frozen=True)
class InventoryEnrichmentSummary:
    project_id: UUID
    total_tickets: int
    matched_tickets: int
    unmatched_tickets: int
    updated_tickets: int
    match_rate_pct: float | None
    matched_by_business_service_count: int
    matched_by_application_count: int
    unmatched_business_service_count: int
    distinct_ticket_business_service_count: int
    distinct_inventory_business_service_count: int
    top_unmatched_business_services: list[ValueCount]
    top_unmatched_applications: list[ValueCount]
    top_unmatched_assignment_groups: list[ValueCount]


@dataclass(frozen=True)
class BusinessServiceCoverage:
    project_id: UUID
    distinct_ticket_business_service_count: int
    distinct_inventory_business_service_count: int
    matched_business_service_count: int
    unmatched_business_service_count: int
    business_service_coverage_pct: float | None
    rows: list[UnmatchedBusinessService]


def append_sample_message(messages: list[str], message: str) -> None:
    if len(messages) < MAX_MESSAGE_SAMPLES:
        messages.append(message)


def normalize_match_key(value: Any) -> str | None:
    text = text_or_none(value)
    return text.lower() if text is not None else None


def get_raw_value(raw_data: dict[str, Any], field_name: str) -> Any:
    for alias in CORE_FIELD_ALIASES[field_name]:
        if alias in raw_data:
            return raw_data[alias]

    normalized_lookup = {
        normalize_source_column_name(column_name): value
        for column_name, value in raw_data.items()
    }
    for alias in CORE_FIELD_ALIASES[field_name]:
        normalized_alias = normalize_source_column_name(alias)
        if normalized_alias in normalized_lookup:
            return normalized_lookup[normalized_alias]
    return None


def build_cmdb_payload(raw_data: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for column_name, value in raw_data.items():
        normalized_name = normalize_source_column_name(column_name)
        if CORE_ALIAS_TO_FIELD.get(normalized_name) in CORE_FIELD_NAMES:
            continue
        payload[column_name] = text_or_none(value) if isinstance(value, str) else value
    return payload


def parse_active(value: Any, row_number: int, result: InventoryUploadResult) -> bool | None:
    text = text_or_none(value)
    if text is None:
        return True

    parsed = parse_bool_value(value)
    if parsed is None:
        append_sample_message(
            result.warnings,
            f"Row {row_number}: Active value '{text}' could not be parsed.",
        )
    return parsed


def clean_inventory_values(
    project_id: UUID,
    source_filename: str,
    parsed_row: ParsedSourceRow,
    result: InventoryUploadResult,
) -> dict[str, Any] | None:
    values: dict[str, Any] = {
        "project_id": project_id,
        "application_number_apm": text_or_none(
            get_raw_value(parsed_row.raw_data, "application_number_apm")
        ),
        "parent_application_name": text_or_none(
            get_raw_value(parsed_row.raw_data, "parent_application_name")
        ),
        "assignment_group": text_or_none(get_raw_value(parsed_row.raw_data, "assignment_group")),
        "assignment_group_owner": text_or_none(
            get_raw_value(parsed_row.raw_data, "assignment_group_owner")
        ),
        "application_owner": text_or_none(
            get_raw_value(parsed_row.raw_data, "application_owner")
        ),
        "business_service_ci_name": text_or_none(
            get_raw_value(parsed_row.raw_data, "business_service_ci_name")
        ),
        "support_lead": text_or_none(get_raw_value(parsed_row.raw_data, "support_lead")),
        "functional_track": text_or_none(get_raw_value(parsed_row.raw_data, "functional_track")),
        "ams_owner": text_or_none(get_raw_value(parsed_row.raw_data, "ams_owner")),
        "supported_by_vendor": text_or_none(
            get_raw_value(parsed_row.raw_data, "supported_by_vendor")
        ),
        "active": parse_active(
            get_raw_value(parsed_row.raw_data, "active"),
            parsed_row.row_number,
            result,
        ),
        "cmdb_payload": build_cmdb_payload(parsed_row.raw_data),
        "source_filename": source_filename,
        "source_row_number": parsed_row.row_number,
    }

    if values["business_service_ci_name"] is None:
        result.skipped_count += 1
        append_sample_message(
            result.errors,
            f"Row {parsed_row.row_number}: Business Service CI Name is required.",
        )
        return None

    track_upload_distincts(result, values)
    return values


def track_upload_distincts(result: InventoryUploadResult, values: dict[str, Any]) -> None:
    distinct_fields = (
        ("business_service_ci_name", result.distinct_business_services),
        ("parent_application_name", result.distinct_parent_applications),
        ("assignment_group", result.distinct_assignment_groups),
        ("application_owner", result.distinct_application_owners),
        ("support_lead", result.distinct_support_leads),
        ("functional_track", result.distinct_functional_tracks),
        ("ams_owner", result.distinct_ams_owners),
        ("supported_by_vendor", result.distinct_supported_vendors),
    )
    for field_name, target_set in distinct_fields:
        value = normalize_match_key(values.get(field_name))
        if value is not None:
            target_set.add(value)


def duplicate_key_condition(values: dict[str, Any]) -> Any:
    return and_(
        ApplicationInventoryItem.project_id == values["project_id"],
        func.lower(func.btrim(ApplicationInventoryItem.business_service_ci_name))
        == normalize_match_key(values["business_service_ci_name"]),
        func.coalesce(
            func.lower(func.btrim(ApplicationInventoryItem.parent_application_name)),
            "",
        )
        == (normalize_match_key(values["parent_application_name"]) or ""),
        func.coalesce(
            func.lower(func.btrim(ApplicationInventoryItem.assignment_group)),
            "",
        )
        == (normalize_match_key(values["assignment_group"]) or ""),
    )


def upsert_inventory_item(db: Session, values: dict[str, Any]) -> bool:
    item = db.scalar(
        select(ApplicationInventoryItem).where(duplicate_key_condition(values)).limit(1)
    )
    if item is None:
        db.add(ApplicationInventoryItem(**values))
        db.flush()
        return True

    for field_name, value in values.items():
        setattr(item, field_name, value)
    db.flush()
    return False


def iter_inventory_csv_rows(path: Path) -> Iterator[ParsedSourceRow]:
    encoding = detect_csv_encoding(path)
    with path.open("r", encoding=encoding, newline="") as csv_file:
        reader = csv.reader(csv_file)
        try:
            headers = make_unique_headers(next(reader))
        except StopIteration:
            return

        for row_number, values in enumerate(reader, start=2):
            raw_data = build_raw_data(headers, values)
            if row_has_any_value(raw_data):
                yield ParsedSourceRow(row_number=row_number, raw_data=raw_data)


def find_inventory_header_row(rows: Iterator[tuple[Any, ...]]) -> tuple[int, list[str]] | None:
    for row_number, values in enumerate(rows, start=1):
        raw_headers = list(values)
        normalized_headers = {
            normalize_source_column_name(str(value))
            for value in raw_headers
            if value is not None and str(value).strip()
        }
        if "business_service_ci_name" in normalized_headers:
            return row_number, make_unique_headers(raw_headers)
    return None


def iter_inventory_xlsx_rows(
    path: Path,
    result: InventoryUploadResult,
) -> Iterator[ParsedSourceRow]:
    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        if TARGET_WORKSHEET_NAME in workbook.sheetnames:
            worksheet = workbook[TARGET_WORKSHEET_NAME]
        else:
            worksheet = workbook.worksheets[0]
            append_sample_message(
                result.warnings,
                f"Worksheet '{TARGET_WORKSHEET_NAME}' was not found; used first worksheet.",
            )

        rows = worksheet.iter_rows(values_only=True)
        header = find_inventory_header_row(rows)
        if header is None:
            raise ApplicationInventoryError(
                "Could not find a header row containing Business Service CI Name."
            )

        header_row_number, headers = header
        for row_number, values in enumerate(rows, start=header_row_number + 1):
            raw_data = build_raw_data(headers, list(values))
            if row_has_any_value(raw_data):
                yield ParsedSourceRow(row_number=row_number, raw_data=raw_data)
    finally:
        workbook.close()


def iter_inventory_file_rows(
    path: Path,
    result: InventoryUploadResult,
) -> Iterator[ParsedSourceRow]:
    extension = path.suffix.lower()
    if extension == ".csv":
        yield from iter_inventory_csv_rows(path)
        return
    if extension == ".xlsx":
        yield from iter_inventory_xlsx_rows(path, result)
        return
    raise ApplicationInventoryError(
        f"Unsupported application inventory file extension: {extension}. Use CSV or XLSX."
    )


def ensure_project_exists(db: Session, project_id: UUID) -> None:
    if db.get(Project, project_id) is None:
        raise FileNotFoundError(f"Project {project_id} was not found.")


def upload_application_inventory_file(
    db: Session,
    project_id: UUID,
    path: Path,
    source_filename: str,
) -> InventoryUploadResult:
    ensure_project_exists(db, project_id)
    result = InventoryUploadResult(project_id=project_id)

    try:
        for parsed_row in iter_inventory_file_rows(path, result):
            result.total_rows += 1
            values = clean_inventory_values(project_id, source_filename, parsed_row, result)
            if values is None:
                continue

            inserted = upsert_inventory_item(db, values)
            if inserted:
                result.inserted_count += 1
            else:
                result.updated_count += 1

            if (result.inserted_count + result.updated_count) % INGESTION_BATCH_SIZE == 0:
                db.commit()

        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise ApplicationInventoryError(
            f"Application inventory rows could not be saved: {exc}"
        ) from exc
    except UnicodeDecodeError as exc:
        db.rollback()
        raise ApplicationInventoryError(
            "Application inventory CSV could not be decoded using supported encodings: "
            + ", ".join(CSV_ENCODING_CANDIDATES)
        ) from exc
    except Exception:
        db.rollback()
        raise

    return result


def list_inventory_items(db: Session, project_id: UUID) -> list[ApplicationInventoryItem]:
    ensure_project_exists(db, project_id)
    statement = (
        select(ApplicationInventoryItem)
        .where(ApplicationInventoryItem.project_id == project_id)
        .order_by(
            ApplicationInventoryItem.parent_application_name.asc().nullslast(),
            ApplicationInventoryItem.business_service_ci_name.asc(),
            ApplicationInventoryItem.assignment_group.asc().nullslast(),
        )
    )
    return list(db.scalars(statement).all())


def update_inventory_item(
    db: Session,
    item_id: UUID,
    values: dict[str, Any],
) -> ApplicationInventoryItem:
    item = db.get(ApplicationInventoryItem, item_id)
    if item is None:
        raise FileNotFoundError(f"Application inventory item {item_id} was not found.")

    for field_name, value in values.items():
        if hasattr(item, field_name):
            setattr(item, field_name, value)
    db.commit()
    db.refresh(item)
    return item


def deactivate_inventory_item(db: Session, item_id: UUID) -> ApplicationInventoryItem:
    return update_inventory_item(db, item_id, {"active": False})


def reset_inventory_ticket_columns(db: Session, project_id: UUID) -> None:
    db.execute(
        update(Ticket)
        .where(Ticket.project_id == project_id)
        .values(
            application_inventory_id=None,
            parent_application_number=None,
            parent_application_name=None,
            business_service_ci_name=None,
            application_owner=None,
            support_lead=None,
            functional_track=None,
            ams_owner=None,
            supported_by_vendor=None,
            assignment_group_owner=None,
        )
    )


def update_tickets_from_inventory(
    db: Session,
    project_id: UUID,
    *,
    ticket_column: str,
) -> int:
    statement = text(
        f"""
        WITH candidates AS (
            SELECT
                t.id AS ticket_id,
                i.id AS inventory_id,
                i.application_number_apm,
                i.parent_application_name,
                i.business_service_ci_name,
                i.application_owner,
                i.support_lead,
                i.functional_track,
                i.ams_owner,
                i.supported_by_vendor,
                i.assignment_group_owner,
                row_number() OVER (
                    PARTITION BY t.id
                    ORDER BY
                        CASE
                            WHEN i.active IS true THEN 0
                            WHEN i.active IS NULL THEN 1
                            ELSE 2
                        END,
                        CASE
                            WHEN lower(coalesce(btrim(t.assignment_group), '')) =
                                 lower(coalesce(btrim(i.assignment_group), ''))
                                 AND nullif(btrim(i.assignment_group), '') IS NOT NULL
                            THEN 0
                            ELSE 1
                        END,
                        i.source_row_number ASC NULLS LAST,
                        i.created_at ASC,
                        i.id ASC
                ) AS row_rank
            FROM tickets AS t
            JOIN application_inventory_items AS i
              ON i.project_id = t.project_id
             AND nullif(btrim(t.{ticket_column}), '') IS NOT NULL
             AND lower(btrim(t.{ticket_column})) = lower(btrim(i.business_service_ci_name))
            WHERE t.project_id = CAST(:project_id AS uuid)
              AND t.application_inventory_id IS NULL
        )
        UPDATE tickets AS t
        SET
            application_inventory_id = candidates.inventory_id,
            parent_application_number = candidates.application_number_apm,
            parent_application_name = candidates.parent_application_name,
            business_service_ci_name = candidates.business_service_ci_name,
            application_owner = candidates.application_owner,
            support_lead = candidates.support_lead,
            functional_track = candidates.functional_track,
            ams_owner = candidates.ams_owner,
            supported_by_vendor = candidates.supported_by_vendor,
            assignment_group_owner = candidates.assignment_group_owner
        FROM candidates
        WHERE candidates.row_rank = 1
          AND t.id = candidates.ticket_id
        """
    )
    result = db.execute(statement, {"project_id": str(project_id)})
    return int(result.rowcount or 0)


def count_tickets(db: Session, project_id: UUID, *, matched: bool | None = None) -> int:
    statement = select(func.count(Ticket.id)).where(Ticket.project_id == project_id)
    if matched is True:
        statement = statement.where(Ticket.application_inventory_id.is_not(None))
    elif matched is False:
        statement = statement.where(Ticket.application_inventory_id.is_(None))
    return int(db.scalar(statement) or 0)


def distinct_ticket_business_service_count(db: Session, project_id: UUID) -> int:
    statement = select(
        func.count(func.distinct(func.lower(func.btrim(Ticket.business_service))))
    ).where(
        Ticket.project_id == project_id,
        Ticket.business_service.is_not(None),
        func.btrim(Ticket.business_service) != "",
    )
    return int(db.scalar(statement) or 0)


def distinct_inventory_business_service_count(db: Session, project_id: UUID) -> int:
    statement = select(
        func.count(
            func.distinct(func.lower(func.btrim(ApplicationInventoryItem.business_service_ci_name)))
        )
    ).where(
        ApplicationInventoryItem.project_id == project_id,
        ApplicationInventoryItem.business_service_ci_name.is_not(None),
        func.btrim(ApplicationInventoryItem.business_service_ci_name) != "",
    )
    return int(db.scalar(statement) or 0)


def matched_ticket_business_service_count(db: Session, project_id: UUID) -> int:
    statement = text(
        """
        WITH ticket_services AS (
            SELECT DISTINCT lower(btrim(business_service)) AS service_key
            FROM tickets
            WHERE project_id = CAST(:project_id AS uuid)
              AND nullif(btrim(business_service), '') IS NOT NULL
        ),
        inventory_services AS (
            SELECT DISTINCT lower(btrim(business_service_ci_name)) AS service_key
            FROM application_inventory_items
            WHERE project_id = CAST(:project_id AS uuid)
              AND nullif(btrim(business_service_ci_name), '') IS NOT NULL
        )
        SELECT count(*) AS matched_count
        FROM ticket_services t
        JOIN inventory_services i ON i.service_key = t.service_key
        """
    )
    return int(db.execute(statement, {"project_id": str(project_id)}).scalar_one() or 0)


def top_unmatched_values(db: Session, project_id: UUID, column: Any) -> list[ValueCount]:
    statement = (
        select(column, func.count(Ticket.id))
        .where(
            Ticket.project_id == project_id,
            Ticket.application_inventory_id.is_(None),
            column.is_not(None),
            func.btrim(column) != "",
        )
        .group_by(column)
        .order_by(func.count(Ticket.id).desc(), column.asc())
        .limit(TOP_UNMATCHED_LIMIT)
    )
    return [
        ValueCount(value=str(value), count=int(count))
        for value, count in db.execute(statement).all()
        if value
    ]


def current_business_service_match_count(db: Session, project_id: UUID) -> int:
    statement = select(func.count(Ticket.id)).where(
        Ticket.project_id == project_id,
        Ticket.application_inventory_id.is_not(None),
        Ticket.business_service_ci_name.is_not(None),
        func.lower(func.btrim(Ticket.business_service))
        == func.lower(func.btrim(Ticket.business_service_ci_name)),
    )
    return int(db.scalar(statement) or 0)


def current_application_match_count(db: Session, project_id: UUID) -> int:
    statement = select(func.count(Ticket.id)).where(
        Ticket.project_id == project_id,
        Ticket.application_inventory_id.is_not(None),
        Ticket.business_service_ci_name.is_not(None),
        func.lower(func.btrim(Ticket.application))
        == func.lower(func.btrim(Ticket.business_service_ci_name)),
        func.coalesce(func.lower(func.btrim(Ticket.business_service)), "")
        != func.lower(func.btrim(Ticket.business_service_ci_name)),
    )
    return int(db.scalar(statement) or 0)


def calculate_rate(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return round((numerator / denominator) * 100, 2)


def build_inventory_enrichment_summary(
    db: Session,
    project_id: UUID,
    *,
    updated_tickets: int = 0,
    matched_by_business_service_count: int | None = None,
    matched_by_application_count: int | None = None,
) -> InventoryEnrichmentSummary:
    ensure_project_exists(db, project_id)
    total_tickets = count_tickets(db, project_id)
    matched_tickets = count_tickets(db, project_id, matched=True)
    unmatched_tickets = max(total_tickets - matched_tickets, 0)
    distinct_ticket_services = distinct_ticket_business_service_count(db, project_id)
    distinct_inventory_services = distinct_inventory_business_service_count(db, project_id)
    matched_services = matched_ticket_business_service_count(db, project_id)
    unmatched_services = max(distinct_ticket_services - matched_services, 0)

    return InventoryEnrichmentSummary(
        project_id=project_id,
        total_tickets=total_tickets,
        matched_tickets=matched_tickets,
        unmatched_tickets=unmatched_tickets,
        updated_tickets=updated_tickets,
        match_rate_pct=calculate_rate(matched_tickets, total_tickets),
        matched_by_business_service_count=(
            current_business_service_match_count(db, project_id)
            if matched_by_business_service_count is None
            else matched_by_business_service_count
        ),
        matched_by_application_count=(
            current_application_match_count(db, project_id)
            if matched_by_application_count is None
            else matched_by_application_count
        ),
        unmatched_business_service_count=unmatched_services,
        distinct_ticket_business_service_count=distinct_ticket_services,
        distinct_inventory_business_service_count=distinct_inventory_services,
        top_unmatched_business_services=top_unmatched_values(
            db,
            project_id,
            Ticket.business_service,
        ),
        top_unmatched_applications=top_unmatched_values(db, project_id, Ticket.application),
        top_unmatched_assignment_groups=top_unmatched_values(
            db,
            project_id,
            Ticket.assignment_group,
        ),
    )


def enrich_tickets_from_inventory(
    db: Session,
    project_id: UUID,
    *,
    replace_existing: bool,
) -> InventoryEnrichmentSummary:
    ensure_project_exists(db, project_id)
    if replace_existing:
        reset_inventory_ticket_columns(db, project_id)
        db.flush()

    business_service_updates = update_tickets_from_inventory(
        db,
        project_id,
        ticket_column="business_service",
    )
    application_updates = update_tickets_from_inventory(
        db,
        project_id,
        ticket_column="application",
    )
    db.commit()

    return build_inventory_enrichment_summary(
        db,
        project_id,
        updated_tickets=business_service_updates + application_updates,
        matched_by_business_service_count=business_service_updates,
        matched_by_application_count=application_updates,
    )


def inventory_filter_values(db: Session, project_id: UUID) -> dict[str, list[str]]:
    ensure_project_exists(db, project_id)
    columns = {
        "application_owners": ApplicationInventoryItem.application_owner,
        "support_leads": ApplicationInventoryItem.support_lead,
        "functional_tracks": ApplicationInventoryItem.functional_track,
        "ams_owners": ApplicationInventoryItem.ams_owner,
        "supported_by_vendors": ApplicationInventoryItem.supported_by_vendor,
        "parent_application_names": ApplicationInventoryItem.parent_application_name,
        "business_service_ci_names": ApplicationInventoryItem.business_service_ci_name,
        "assignment_groups": ApplicationInventoryItem.assignment_group,
    }
    values: dict[str, list[str]] = {}
    for key, column in columns.items():
        statement = (
            select(column)
            .distinct()
            .where(
                ApplicationInventoryItem.project_id == project_id,
                column.is_not(None),
                func.btrim(column) != "",
            )
            .order_by(column)
        )
        values[key] = [str(value) for value in db.scalars(statement).all() if value]
    return values


def unmatched_business_services(
    db: Session,
    project_id: UUID,
    *,
    limit: int,
    offset: int,
) -> BusinessServiceCoverage:
    ensure_project_exists(db, project_id)
    distinct_ticket_services = distinct_ticket_business_service_count(db, project_id)
    distinct_inventory_services = distinct_inventory_business_service_count(db, project_id)
    matched_services = matched_ticket_business_service_count(db, project_id)
    unmatched_services = max(distinct_ticket_services - matched_services, 0)

    statement = text(
        """
        WITH inventory_services AS (
            SELECT DISTINCT lower(btrim(business_service_ci_name)) AS service_key
            FROM application_inventory_items
            WHERE project_id = CAST(:project_id AS uuid)
              AND nullif(btrim(business_service_ci_name), '') IS NOT NULL
        )
        SELECT
            t.business_service,
            count(*) AS ticket_count,
            count(DISTINCT t.assignment_group) AS assignment_group_count,
            (array_remove(array_agg(DISTINCT t.assignment_group), NULL))[1:5]
                AS sample_assignment_groups,
            (array_agg(t.ticket_number ORDER BY t.ticket_number))[1:5]
                AS sample_ticket_numbers
        FROM tickets AS t
        LEFT JOIN inventory_services AS i
          ON i.service_key = lower(btrim(t.business_service))
        WHERE t.project_id = CAST(:project_id AS uuid)
          AND nullif(btrim(t.business_service), '') IS NOT NULL
          AND i.service_key IS NULL
        GROUP BY t.business_service
        ORDER BY count(*) DESC, t.business_service ASC
        LIMIT :limit OFFSET :offset
        """
    )
    rows = [
        UnmatchedBusinessService(
            business_service=str(row["business_service"]),
            ticket_count=int(row["ticket_count"] or 0),
            assignment_group_count=int(row["assignment_group_count"] or 0),
            sample_assignment_groups=list(row["sample_assignment_groups"] or []),
            sample_ticket_numbers=list(row["sample_ticket_numbers"] or []),
        )
        for row in db.execute(
            statement,
            {"project_id": str(project_id), "limit": limit, "offset": offset},
        )
        .mappings()
        .all()
    ]

    return BusinessServiceCoverage(
        project_id=project_id,
        distinct_ticket_business_service_count=distinct_ticket_services,
        distinct_inventory_business_service_count=distinct_inventory_services,
        matched_business_service_count=matched_services,
        unmatched_business_service_count=unmatched_services,
        business_service_coverage_pct=calculate_rate(matched_services, distinct_ticket_services),
        rows=rows,
    )
