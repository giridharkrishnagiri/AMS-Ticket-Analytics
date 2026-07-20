from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_ROOT = Path(__file__).resolve().parents[1]


def install_os_truststore() -> None:
    try:
        import truststore
    except ImportError:
        return

    truststore.inject_into_ssl()


install_os_truststore()


class Settings(BaseSettings):
    app_name: str = "ASM Engagement Cockpit"
    app_env: str = "local"

    backend_cors_origins: str = "http://localhost:3020,http://127.0.0.1:3020"

    database_url: str = Field(
        default="postgresql+psycopg2://asm_user:asm_password@localhost:5434/asm_cockpit"
    )

    openai_api_key: str | None = None
    openai_tracing: bool = True
    openai_model: str = "gpt-4.1-mini"
    openai_chat_model: str = "gpt-5.6-luna"
    openai_deep_chat_model: str = "gpt-5.6-terra"
    openai_embedding_model: str = "text-embedding-3-small"

    api_auth_enabled: bool = False
    api_auth_key: str | None = None

    app_login_enabled: bool = True
    app_login_username: str = "giridhar"
    app_login_password: str = "change_this_password"
    app_login_display_name: str = "Giridhar Krishnagiri"
    app_session_secret_key: str = "change_this_to_a_long_random_secret_value"
    app_session_duration_minutes: int = 720

    log_requests: bool = True

    model_config = SettingsConfigDict(
        env_file=str(BACKEND_ROOT / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def cors_origins(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.backend_cors_origins.split(",")
            if origin.strip()
        ]

    @property
    def is_local(self) -> bool:
        return self.app_env.strip().lower() in {"local", "dev", "development"}

    @property
    def auth_is_ready(self) -> bool:
        if not self.api_auth_enabled:
            return True

        return bool(self.api_auth_key and self.api_auth_key.strip())

    @property
    def login_is_ready(self) -> bool:
        if not self.app_login_enabled:
            return True

        return bool(
            self.app_login_username.strip()
            and self.app_login_password.strip()
            and self.app_session_secret_key.strip()
            and self.app_session_secret_key != "change_this_to_a_long_random_secret_value"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
