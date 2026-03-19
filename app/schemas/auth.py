from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class UserRead(BaseModel):
    id: str
    email: str
    full_name: str | None = None
    picture_url: str | None = None
    preferences_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
    last_login_at: datetime | None = None

    class Config:
        from_attributes = True


class UserPreferencesUpdate(BaseModel):
    preferences_json: dict[str, Any] = Field(default_factory=dict)