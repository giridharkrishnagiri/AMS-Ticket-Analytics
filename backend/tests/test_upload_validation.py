from app.services.upload_storage import (
    build_saved_filename,
    is_allowed_upload_filename,
    sanitize_filename,
)


def test_upload_filename_validation_accepts_csv_and_xlsx() -> None:
    assert is_allowed_upload_filename("incidents.csv")
    assert is_allowed_upload_filename("service_catalog_tasks.XLSX")


def test_upload_filename_validation_rejects_unsupported_extensions() -> None:
    assert not is_allowed_upload_filename("notes.txt")
    assert not is_allowed_upload_filename("archive.zip")
    assert not is_allowed_upload_filename("")


def test_sanitize_filename_removes_windows_unsafe_characters() -> None:
    assert sanitize_filename(r"C:\temp\bad:name?.csv") == "bad_name_.csv"


def test_saved_filename_keeps_allowed_extension() -> None:
    saved_filename = build_saved_filename("Incidents June.xlsx")

    assert saved_filename.endswith(".xlsx")
    assert "Incidents June" in saved_filename
