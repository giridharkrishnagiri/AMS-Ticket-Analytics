from __future__ import annotations

from html import escape
from html.parser import HTMLParser
from types import SimpleNamespace
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import DashboardCommentary, Project

ALLOWED_COMMENTARY_TAGS = {"p", "br", "strong", "b", "em", "i", "u", "ul", "ol", "li", "span"}
VOID_COMMENTARY_TAGS = {"br"}
DROP_CONTENT_TAGS = {"script", "style", "iframe", "object", "embed"}
NORMALIZED_LOWER_FIELDS = {
    "dashboard_area",
    "tab_name",
    "sub_tab_name",
    "section_key",
    "chart_key",
    "scope_filter",
    "ticket_type_filter",
}


class CommentarySanitizer(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.drop_content_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        normalized = tag.lower()
        if normalized in DROP_CONTENT_TAGS:
            self.drop_content_depth += 1
            return
        if self.drop_content_depth:
            return
        if normalized in ALLOWED_COMMENTARY_TAGS:
            self.parts.append(f"<{normalized}>")

    def handle_endtag(self, tag: str) -> None:
        normalized = tag.lower()
        if normalized in DROP_CONTENT_TAGS and self.drop_content_depth:
            self.drop_content_depth -= 1
            return
        if self.drop_content_depth:
            return
        if normalized in ALLOWED_COMMENTARY_TAGS and normalized not in VOID_COMMENTARY_TAGS:
            self.parts.append(f"</{normalized}>")

    def handle_data(self, data: str) -> None:
        if self.drop_content_depth:
            return
        self.parts.append(escape(data, quote=False))

    def handle_entityref(self, name: str) -> None:
        if self.drop_content_depth:
            return
        self.parts.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        if self.drop_content_depth:
            return
        self.parts.append(f"&#{name};")

    def sanitized_html(self) -> str:
        return "".join(self.parts).strip()


class CommentaryTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in {"p", "br", "li"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def text(self) -> str:
        lines = [" ".join(part.split()) for part in "".join(self.parts).splitlines()]
        return "\n".join(line for line in lines if line).strip()


def sanitize_commentary_html(value: str | None) -> str | None:
    if not value or not value.strip():
        return None
    sanitizer = CommentarySanitizer()
    sanitizer.feed(value)
    sanitized = sanitizer.sanitized_html()
    return sanitized or None


def commentary_html_to_text(value: str | None) -> str | None:
    if not value:
        return None
    extractor = CommentaryTextExtractor()
    extractor.feed(value)
    text = extractor.text()
    return text or None


def normalized_key_value(field_name: str, value: Any, *, optional: bool = False) -> str:
    text = str(value or "").strip()
    if not text and optional:
        return ""
    if not text:
        return "all" if field_name in {"scope_filter", "ticket_type_filter"} else ""
    if field_name in NORMALIZED_LOWER_FIELDS:
        return text.lower()
    return text


def commentary_context_values(source: Any) -> dict[str, str]:
    return {
        "dashboard_area": normalized_key_value("dashboard_area", source.dashboard_area),
        "tab_name": normalized_key_value("tab_name", source.tab_name),
        "sub_tab_name": normalized_key_value(
            "sub_tab_name",
            getattr(source, "sub_tab_name", None),
            optional=True,
        ),
        "section_key": normalized_key_value("section_key", source.section_key),
        "chart_key": normalized_key_value(
            "chart_key",
            getattr(source, "chart_key", None),
            optional=True,
        ),
        "scope_filter": normalized_key_value(
            "scope_filter",
            getattr(source, "scope_filter", None) or "all",
        ),
        "ticket_type_filter": normalized_key_value(
            "ticket_type_filter",
            getattr(source, "ticket_type_filter", None) or "all",
        ),
        "functional_track_ams_owner": str(
            getattr(source, "functional_track_ams_owner", None) or "all",
        ).strip()
        or "all",
    }


def commentary_query(db: Session, project_id: UUID, context: dict[str, str]) -> Any:
    return db.execute(
        select(DashboardCommentary).where(
            DashboardCommentary.project_id == project_id,
            DashboardCommentary.dashboard_area == context["dashboard_area"],
            DashboardCommentary.tab_name == context["tab_name"],
            DashboardCommentary.sub_tab_name == context["sub_tab_name"],
            DashboardCommentary.section_key == context["section_key"],
            DashboardCommentary.chart_key == context["chart_key"],
            DashboardCommentary.scope_filter == context["scope_filter"],
            DashboardCommentary.ticket_type_filter == context["ticket_type_filter"],
            DashboardCommentary.functional_track_ams_owner
            == context["functional_track_ams_owner"],
        ),
    ).scalar_one_or_none()


def serialize_commentary(row: DashboardCommentary) -> dict[str, Any]:
    return {
        "id": row.id,
        "project_id": row.project_id,
        "dashboard_area": row.dashboard_area,
        "tab_name": row.tab_name,
        "sub_tab_name": row.sub_tab_name or None,
        "section_key": row.section_key,
        "chart_key": row.chart_key or None,
        "scope_filter": row.scope_filter,
        "ticket_type_filter": row.ticket_type_filter,
        "functional_track_ams_owner": row.functional_track_ams_owner,
        "commentary_html": row.commentary_html,
        "commentary_text": row.commentary_text,
        "updated_at": row.updated_at,
        "updated_by": row.updated_by,
    }


def get_commentary_by_context(db: Session, request: Any) -> dict[str, Any]:
    context = commentary_context_values(request)
    row = commentary_query(db, request.project_id, context)
    return {"commentary": serialize_commentary(row) if row else None}


def batch_commentaries(db: Session, request: Any) -> dict[str, Any]:
    context = commentary_context_values(
        SimpleNamespace(
            dashboard_area=request.dashboard_area,
            tab_name=request.tab_name,
            sub_tab_name=request.sub_tab_name,
            section_key="",
            chart_key="",
            scope_filter=request.scope_filter,
            ticket_type_filter=request.ticket_type_filter,
            functional_track_ams_owner=request.functional_track_ams_owner,
        ),
    )
    rows = (
        db.execute(
            select(DashboardCommentary)
            .where(
                DashboardCommentary.project_id == request.project_id,
                DashboardCommentary.dashboard_area == context["dashboard_area"],
                DashboardCommentary.tab_name == context["tab_name"],
                DashboardCommentary.sub_tab_name == context["sub_tab_name"],
                DashboardCommentary.scope_filter == context["scope_filter"],
                DashboardCommentary.ticket_type_filter == context["ticket_type_filter"],
                DashboardCommentary.functional_track_ams_owner
                == context["functional_track_ams_owner"],
            )
            .order_by(DashboardCommentary.section_key.asc(), DashboardCommentary.chart_key.asc()),
        )
        .scalars()
        .all()
    )
    return {"commentaries": [serialize_commentary(row) for row in rows]}


def upsert_commentary(db: Session, request: Any) -> dict[str, Any]:
    project = db.get(Project, request.project_id)
    if project is None:
        raise ValueError("Project not found")

    context = commentary_context_values(request)
    sanitized_html = sanitize_commentary_html(request.commentary_html)
    commentary_text = (
        request.commentary_text.strip()
        if request.commentary_text and request.commentary_text.strip()
        else commentary_html_to_text(sanitized_html)
    )
    row = commentary_query(db, request.project_id, context)
    if row is None:
        row = DashboardCommentary(
            client_id=project.client_id,
            project_id=request.project_id,
            created_by=request.updated_by,
            **context,
        )
        db.add(row)

    row.commentary_html = sanitized_html
    row.commentary_text = commentary_text
    row.updated_by = request.updated_by
    db.commit()
    db.refresh(row)
    return {"commentary": serialize_commentary(row)}


def export_project_commentaries(db: Session, project_id: UUID) -> list[dict[str, Any]]:
    rows = (
        db.execute(
            select(DashboardCommentary)
            .where(DashboardCommentary.project_id == project_id)
            .order_by(
                DashboardCommentary.dashboard_area.asc(),
                DashboardCommentary.tab_name.asc(),
                DashboardCommentary.sub_tab_name.asc(),
                DashboardCommentary.section_key.asc(),
                DashboardCommentary.chart_key.asc(),
            ),
        )
        .scalars()
        .all()
    )
    return [
        {
            key: value
            for key, value in serialize_commentary(row).items()
            if key not in {"id", "updated_at", "updated_by"}
        }
        for row in rows
    ]
