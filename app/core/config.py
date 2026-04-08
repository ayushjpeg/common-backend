from functools import lru_cache
from pathlib import Path
import logging
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", env_prefix="APP_")

    app_name: str = "Unified Control Backend"
    api_prefix: str = "/api"
    public_base_url: str = "https://common-backend.ayux.in"
    database_url: str = "postgresql+psycopg2://task_user:task_password@localhost:5432/task_ops"
    media_root: Path = Path("./storage")
    media_base_url: str | None = None
    allowed_origins: Annotated[list[str], NoDecode]
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
    def _split_origins(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                raise ValueError("APP_ALLOWED_ORIGINS must not be empty")
            return [origin.strip() for origin in stripped.split(",") if origin.strip()]
        if not value:
            raise ValueError("APP_ALLOWED_ORIGINS must not be empty")
        return value

    @property
    def resolved_media_root(self) -> Path:
        return Path(self.media_root).resolve()


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.resolved_media_root.mkdir(parents=True, exist_ok=True)
    logging.getLogger("uvicorn").info("Allowed origins resolved: %s", settings.allowed_origins)
    return settings
