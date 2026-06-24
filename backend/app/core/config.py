from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
ENV_FILE = BACKEND_DIR / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        env_prefix="",
        extra="ignore",
        case_sensitive=False,
        env_ignore_empty=True,
    )

    app_name: str = "AMS Applications & Volumetrics Analytics"
    app_version: str = "0.1.0"
    environment: str = "local"
    database_url: str = "postgresql+psycopg://localhost:5432/ams_ticket_intelligence"
    cors_allowed_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    local_storage_root: Path = Path("storage")

    @property
    def cors_origins(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.cors_allowed_origins.split(",")
            if origin.strip()
        ]

    @property
    def resolved_storage_root(self) -> Path:
        root = self.local_storage_root
        if not root.is_absolute():
            root = BACKEND_DIR / root
        return root.resolve()

    @property
    def uploads_dir(self) -> Path:
        return self.resolved_storage_root / "uploads"

    @property
    def exports_dir(self) -> Path:
        return self.resolved_storage_root / "exports"


@lru_cache
def get_settings() -> Settings:
    return Settings()
