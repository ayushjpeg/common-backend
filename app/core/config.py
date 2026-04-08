from functools import lru_cache
from pathlib import Path
import logging

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", env_prefix="APP_")

    app_name: str = "Unified Control Backend"
    api_prefix: str = "/api"
    public_base_url: str = "https://common-backend.ayux.in"
    database_url: str = "postgresql+psycopg2://task_user:task_password@localhost:5432/task_ops"
    media_root: Path = Path("./storage")
    media_base_url: str | None = None
    allowed_origins: str
    auth_secret_key: str = "change-me"
    auth_cookie_name: str = "common_backend_session"
    auth_cookie_domain: str | None = ".ayux.in"
    auth_cookie_secure: bool = True
    auth_token_ttl_hours: int = 24 * 14
    oauth_state_ttl_minutes: int = 10
    google_client_id: str = ""
    google_client_secret: str = ""

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def _validate_allowed_origins(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("APP_ALLOWED_ORIGINS must not be empty")
        return value

    @property
    def parsed_allowed_origins(self) -> list[str]:
        origins = [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]
        if not origins:
            raise ValueError("APP_ALLOWED_ORIGINS must contain at least one origin")
        return origins

    @property
    def resolved_media_root(self) -> Path:
        return Path(self.media_root).resolve()


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.resolved_media_root.mkdir(parents=True, exist_ok=True)
    logging.getLogger("uvicorn").info("Allowed origins resolved: %s", settings.parsed_allowed_origins)
    return settings
