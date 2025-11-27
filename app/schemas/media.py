from datetime import datetime
from typing import Any

from pydantic import BaseModel


class MediaAssetRead(BaseModel):
    id: str
    owner_type: str
    owner_id: str | None
    file_path: str
    mime_type: str | None
    metadata_json: dict[str, Any]
    created_at: datetime

    class Config:
        from_attributes = True
