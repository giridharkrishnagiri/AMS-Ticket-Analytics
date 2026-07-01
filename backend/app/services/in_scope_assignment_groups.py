from __future__ import annotations

import csv
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import UUID

from openpyxl import load_workbook
from sqlalchemy import delete, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models import InScopeAssignmentGroup, Project
from app.services.ingestion import (
    CSV_ENCODING_CANDIDATES,
    ParsedSourceRow,
    build_raw_data,
    detect_csv_encoding,
    make_unique_headers,
    normalize_source_column_name,
    row_has_any_value,
)

MAX_MESSAGE_SAMPLES = 50

ASSIGNMENT_GROUP_ALIASES = (
    "Assigment Groups",
    "Assignment Groups",
    "Assignment Group",
    "Assignment group",
    "assignment_group",
    "Support Group",
    "Support group",
    "Group",
)
FUNCTIONAL_TRACK_ALIASES = (
    "Track",
    "Functional Track",
    "functional_track",
    "Functional track",
)


class InScopeAssignmentGroupsError(Exception):
    pass


def text_or_none(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.replace("\xa0", " ").strip()
        return text or None
    text = str(value).replace("\xa0", " ").strip()
    return text or None


@dataclass(frozen=True)
class InScopeAssignmentGroupPreviewRow:
    assignment_group: str
    functional_track: str | None
    source_row_number: int | None


@dataclass
class InScopeAssignmentGroupsImportResult:
    project_id: UUID
    source_filename: str
    total_rows: int = 0
    imported_count: int = 0
    skipped_count: int = 0
    duplicate_count: int = 0
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    preview_rows: list[InScopeAssignmentGroupPreviewRow] = field(default_factory=list)

    @property
    def error_count(self) -> int:
        return len(self.errors)

    @property
    def warning_count(self) -> int:
        return len(self.warnings)


@dataclass(frozen=True)
class InScopeAssignmentGroupsStatus:
    project_id: UUID
    active_count: int
    last_imported_at: Any | None
    preview_rows: list[InScopeAssignmentGroupPreviewRow]


def append_sample_message(messages: list[str], message: str) -> None:
    if len(messages) < MAX_MESSAGE_SAMPLES:
        messages.append(message)


def normalize_assignment_group_key(value: Any) -> str | None:
    text = text_or_none(value)
    if text is None:
        return None
    normalized = re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip().casefold()
    return normalized or None


def header_lookup(raw_data: dict[str, Any]) -> dict[str, Any]:
    return {
        normalize_source_column_name(column_name): value
        for column_name, value in raw_data.items()
    }


def get_aliased_value(raw_data: dict[str, Any], aliases: tuple[str, ...]) -> Any:
    for alias in aliases:
        if alias in raw_data:
            return raw_data[alias]
    lookup = header_lookup(raw_data)
    for alias in aliases:
        normalized_alias = normalize_source_column_name(alias)
        if normalized_alias in lookup:
            return lookup[normalized_alias]
    return None


def has_alias(headers: set[str], aliases: tuple[str, ...]) -> bool:
    return any(normalize_source_column_name(alias) in headers for alias in aliases)


def validate_headers(raw_data: dict[str, Any]) -> None:
    headers = {normalize_source_column_name(column_name) for column_name in raw_data}
    missing: list[str] = []
    if not has_alias(headers, ASSIGNMENT_GROUP_ALIASES):
        missing.append("Assigment Groups / Assignment Group")
    if not has_alias(headers, FUNCTIONAL_TRACK_ALIASES):
        missing.append("Track / Functional Track")
    if missing:
        raise InScopeAssignmentGroupsError(
            "In-scope assignment group workbook is missing required column(s): "
            + ", ".join(missing)
            + ".",
        )


def iter_reference_csv_rows(path: Path) -> Iterator[ParsedSourceRow]:
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


def iter_reference_xlsx_rows(path: Path) -> Iterator[ParsedSourceRow]:
    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        worksheet = workbook.worksheets[0]
        rows = worksheet.iter_rows(values_only=True)
        try:
            headers = make_unique_headers(next(rows))
        except StopIteration:
            return
        for row_number, values in enumerate(rows, start=2):
            raw_data = build_raw_data(headers, list(values))
            if row_has_any_value(raw_data):
                yield ParsedSourceRow(row_number=row_number, raw_data=raw_data)
    finally:
        workbook.close()


def iter_reference_file_rows(path: Path) -> Iterator[ParsedSourceRow]:
    extension = path.suffix.lower()
    if extension == ".csv":
        yield from iter_reference_csv_rows(path)
        return
    if extension == ".xlsx":
        yield from iter_reference_xlsx_rows(path)
        return
    raise InScopeAssignmentGroupsError(
        f"Unsupported in-scope assignment group reference extension: {extension}. Use XLSX or CSV.",
    )


def ensure_project(db: Session, project_id: UUID) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise FileNotFoundError(f"Project {project_id} was not found.")
    return project


def import_in_scope_assignment_groups(
    db: Session,
    project_id: UUID,
    path: Path,
    source_filename: str,
) -> InScopeAssignmentGroupsImportResult:
    project = ensure_project(db, project_id)
    result = InScopeAssignmentGroupsImportResult(
        project_id=project_id,
        source_filename=source_filename,
    )
    rows_by_key: dict[str, dict[str, Any]] = {}

    try:
        first_row_checked = False
        for parsed_row in iter_reference_file_rows(path):
            result.total_rows += 1
            if not first_row_checked:
                validate_headers(parsed_row.raw_data)
                first_row_checked = True

            assignment_group = text_or_none(
                get_aliased_value(parsed_row.raw_data, ASSIGNMENT_GROUP_ALIASES)
            )
            if assignment_group is None:
                result.skipped_count += 1
                continue

            assignment_group_key = normalize_assignment_group_key(assignment_group)
            if assignment_group_key is None:
                result.skipped_count += 1
                continue

            functional_track = text_or_none(
                get_aliased_value(parsed_row.raw_data, FUNCTIONAL_TRACK_ALIASES)
            )
            if functional_track is None:
                append_sample_message(
                    result.warnings,
                    f"Row {parsed_row.row_number}: Track is blank for '{assignment_group}'.",
                )

            if assignment_group_key in rows_by_key:
                result.duplicate_count += 1
            rows_by_key[assignment_group_key] = {
                "client_id": project.client_id,
                "project_id": project_id,
                "assignment_group": assignment_group,
                "assignment_group_key": assignment_group_key,
                "functional_track": functional_track,
                "source_filename": source_filename,
                "source_row_number": parsed_row.row_number,
                "is_active": True,
            }

        if result.total_rows == 0:
            raise InScopeAssignmentGroupsError(
                "In-scope assignment group reference file did not contain any data rows.",
            )

        db.execute(
            delete(InScopeAssignmentGroup).where(
                InScopeAssignmentGroup.project_id == project_id,
            )
        )
        for values in rows_by_key.values():
            db.add(InScopeAssignmentGroup(**values))

        result.imported_count = len(rows_by_key)
        result.preview_rows = [
            InScopeAssignmentGroupPreviewRow(
                assignment_group=str(values["assignment_group"]),
                functional_track=values["functional_track"],
                source_row_number=values["source_row_number"],
            )
            for values in list(rows_by_key.values())[:25]
        ]
        db.flush()
    except SQLAlchemyError as exc:
        db.rollback()
        raise InScopeAssignmentGroupsError(
            f"In-scope assignment group reference could not be saved: {exc}",
        ) from exc
    except UnicodeDecodeError as exc:
        db.rollback()
        raise InScopeAssignmentGroupsError(
            "In-scope assignment group reference CSV could not be decoded using supported "
            f"encodings: {', '.join(CSV_ENCODING_CANDIDATES)}",
        ) from exc
    except Exception:
        db.rollback()
        raise

    return result


def active_assignment_group_keys(db: Session, project_id: UUID) -> set[str]:
    ensure_project(db, project_id)
    return {
        key
        for key in db.scalars(
            select(InScopeAssignmentGroup.assignment_group_key).where(
                InScopeAssignmentGroup.project_id == project_id,
                InScopeAssignmentGroup.is_active.is_(True),
            ),
        ).all()
        if key
    }


def in_scope_assignment_groups_status(
    db: Session,
    project_id: UUID,
    *,
    preview_limit: int = 25,
) -> InScopeAssignmentGroupsStatus:
    ensure_project(db, project_id)
    active_count = int(
        db.scalar(
            select(func.count(InScopeAssignmentGroup.id)).where(
                InScopeAssignmentGroup.project_id == project_id,
                InScopeAssignmentGroup.is_active.is_(True),
            )
        )
        or 0
    )
    last_imported_at = db.scalar(
        select(func.max(InScopeAssignmentGroup.created_at)).where(
            InScopeAssignmentGroup.project_id == project_id,
            InScopeAssignmentGroup.is_active.is_(True),
        )
    )
    preview = db.scalars(
        select(InScopeAssignmentGroup)
        .where(
            InScopeAssignmentGroup.project_id == project_id,
            InScopeAssignmentGroup.is_active.is_(True),
        )
        .order_by(
            InScopeAssignmentGroup.assignment_group.asc(),
            InScopeAssignmentGroup.id.asc(),
        )
        .limit(preview_limit),
    ).all()
    return InScopeAssignmentGroupsStatus(
        project_id=project_id,
        active_count=active_count,
        last_imported_at=last_imported_at,
        preview_rows=[
            InScopeAssignmentGroupPreviewRow(
                assignment_group=row.assignment_group,
                functional_track=row.functional_track,
                source_row_number=row.source_row_number,
            )
            for row in preview
        ],
    )


def list_in_scope_assignment_groups(
    db: Session,
    project_id: UUID,
    *,
    limit: int = 100,
    offset: int = 0,
) -> list[InScopeAssignmentGroup]:
    ensure_project(db, project_id)
    return list(
        db.scalars(
            select(InScopeAssignmentGroup)
            .where(
                InScopeAssignmentGroup.project_id == project_id,
                InScopeAssignmentGroup.is_active.is_(True),
            )
            .order_by(
                InScopeAssignmentGroup.assignment_group.asc(),
                InScopeAssignmentGroup.id.asc(),
            )
            .offset(offset)
            .limit(limit),
        ).all()
    )
