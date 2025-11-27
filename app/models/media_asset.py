import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, JSON, String

from ..core.database import Base


class MediaAsset(Base):
    __tablename__ = "media_assets"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    owner_type = Column(String(64), nullable=False)
    owner_id = Column(String(64), nullable=True)
    file_path = Column(String(512), nullable=False)
    mime_type = Column(String(128), nullable=True)
    metadata_json = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
