from app.core.config import Settings


def test_settings_reads_uppercase_keys_from_env_file(monkeypatch, tmp_path) -> None:
    for key in ("DATABASE_URL", "APP_NAME", "LOCAL_STORAGE_ROOT"):
        monkeypatch.delenv(key, raising=False)

    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "DATABASE_URL=postgresql+psycopg://ams_user@localhost:5432/ams_ticket_intelligence",
                "APP_NAME=AMS Ticket Intelligence Test",
                "LOCAL_STORAGE_ROOT=local-test-storage",
            ]
        ),
        encoding="utf-8",
    )

    settings = Settings(_env_file=env_file)

    assert settings.database_url == (
        "postgresql+psycopg://ams_user@localhost:5432/ams_ticket_intelligence"
    )
    assert settings.app_name == "AMS Ticket Intelligence Test"
    assert str(settings.local_storage_root) == "local-test-storage"
