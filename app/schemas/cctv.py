from datetime import datetime

from pydantic import BaseModel


class CCTVStreamBase(BaseModel):
    name: str
    stream_url: str
    location: str | None = None
    is_active: bool = True


class CCTVStreamCreate(CCTVStreamBase):
    pass


class CCTVStreamRead(CCTVStreamBase):
    id: str
    created_at: datetime

    class Config:
        from_attributes = True


class CCTVRecordingRead(BaseModel):
    id: str
    stream_id: str
    file_path: str
    duration_seconds: int | None
    recorded_at: datetime

    class Config:
        from_attributes = True
