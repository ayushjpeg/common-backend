from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", env_prefix="APP_")

    app_name: str = "Unified Control Backend"
    api_prefix: str = "/api"
    database_url: str = "postgresql+psycopg2://task_user:task_password@localhost:5432/task_ops"
    media_root: Path = Path("./storage")
    media_base_url: str | None = None
    allowed_origins: list[str] = ["http://localhost:5173", "http://localhost:8006"]
    api_key: str = "super-secret-key"

    @property
    def resolved_media_root(self) -> Path:
        return Path(self.media_root).resolve()


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.resolved_media_root.mkdir(parents=True, exist_ok=True)
    return settings
