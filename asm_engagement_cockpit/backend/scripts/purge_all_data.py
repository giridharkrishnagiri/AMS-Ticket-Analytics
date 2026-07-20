"""Purge all ASM Engagement Cockpit application data while keeping database tables.

Run from the backend folder:

    uv run python scripts/purge_all_data.py --yes

Optional file cleanup:

    uv run python scripts/purge_all_data.py --yes --delete-files
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from sqlalchemy import create_engine, text

from app.config import get_settings

TABLES = [
    # MVP 18 simplified workspace records
    "ui_workspace_files",
    "ui_workspace_recommendations",
    "ui_workspace_evidence",
    "ui_workspace_analysis",
    "ui_workspace_findings",
    "ui_workspace_questions",
    "ui_workspace_data_collections",
    # MVP 16 operations/governance
    "executive_snapshots",
    "notification_items",
    "audit_events",
    "app_users",
    # MVP 12 recommendation lifecycle
    "llm_recommendation_action_items",
    "llm_recommendation_revisions",
    "llm_recommendation_decisions",
    # MVP 11 review workflow
    "deliverable_review_action_items",
    "deliverable_review_workflows",
    # MVP 10 timesheets
    "timesheet_summaries",
    "timesheet_entries",
    # MVP 8 LLM records
    "deliverable_reviews",
    "llm_recommendations",
    # MVP 7 files / MVP 5 records
    "uploaded_files",
    "evidence_items",
    "analysis_outputs",
    "findings",
    # MVP 4 / MVP 3 / MVP 2 records
    "stakeholder_questions",
    "data_points",
    "reminders",
    "date_revision_history",
    # Core hierarchy, leaf-to-root
    "subtasks",
    "tasks",
    "deliverables",
    "workstreams",
    "engagements",
    # Older optional user table if present
    "users",
]


def quoted_table_list(table_names: list[str]) -> str:
    return ", ".join(f'public."{table_name}"' for table_name in table_names)


def existing_tables(engine) -> list[str]:
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_type = 'BASE TABLE'
                """
            )
        ).scalars().all()

    available = set(rows)
    return [table_name for table_name in TABLES if table_name in available]


def delete_uploaded_files() -> None:
    backend_dir = Path(__file__).resolve().parents[1]
    project_dir = backend_dir.parent
    upload_dir = project_dir / "data" / "uploads"

    if not upload_dir.exists():
        print(f"Upload folder does not exist, nothing to delete: {upload_dir}")
        return

    for child in upload_dir.iterdir():
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()

    print(f"Deleted uploaded files from: {upload_dir}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Purge all ASM Engagement Cockpit application data.")
    parser.add_argument("--yes", action="store_true", help="Actually purge the data. Without this flag, only prints what would be purged.")
    parser.add_argument("--delete-files", action="store_true", help="Also delete files under data/uploads.")
    args = parser.parse_args()

    settings = get_settings()
    engine = create_engine(settings.database_url)
    tables_to_purge = existing_tables(engine)

    print("ASM Engagement Cockpit purge plan")
    print("Database URL:", settings.database_url)
    print("Tables found:", len(tables_to_purge))

    for table_name in tables_to_purge:
        print(f" - {table_name}")

    if not tables_to_purge:
        print("No known application tables found. Nothing to purge.")
        return 0

    if not args.yes:
        print("\nDry run only. Re-run with --yes to purge these tables.")
        print("Add --delete-files if you also want to delete uploaded files from data/uploads.")
        return 0

    truncate_sql = f"TRUNCATE TABLE {quoted_table_list(tables_to_purge)} RESTART IDENTITY CASCADE"

    with engine.begin() as connection:
        connection.execute(text(truncate_sql))

    print("\nDatabase purge completed successfully.")

    if args.delete_files:
        delete_uploaded_files()
    else:
        print("Uploaded files were not deleted. Re-run with --delete-files if needed.")

    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
