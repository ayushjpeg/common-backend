from functools import lru_cache
from pathlib import Path
import logging

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


_DEFAULT_ORIGINS = [
    "http://localhost:5173",
    "http://localhost:8006",
    "http://localhost:4173",
    "http://localhost:3000",
    "http://localhost:8004",
    "https://food.ayux.in",
    "https://cctv.ayux.in",
    "https://gym.ayux.in",
    "https://tasks.ayux.in",
]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", env_prefix="APP_")

    app_name: str = "Unified Control Backend"
    api_prefix: str = "/api"
    database_url: str = "postgresql+psycopg2://task_user:task_password@localhost:5432/task_ops"
    media_root: Path = Path("./storage")
    media_base_url: str | None = None
    allowed_origins: list[str] | str = Field(default_factory=lambda: _DEFAULT_ORIGINS.copy())
    api_key: str = "super-secret-key"

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return _DEFAULT_ORIGINS.copy()
            return [origin.strip() for origin in stripped.split(",") if origin.strip()]
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
