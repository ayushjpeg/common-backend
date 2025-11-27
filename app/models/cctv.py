import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from ..core.database import Base


class CCTVStream(Base):
    __tablename__ = "cctv_streams"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False)
    stream_url = Column(Text, nullable=False)
    location = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    recordings = relationship("CCTVRecording", back_populates="stream", cascade="all, delete-orphan")


class CCTVRecording(Base):
    __tablename__ = "cctv_recordings"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    stream_id = Column(String(36), ForeignKey("cctv_streams.id", ondelete="CASCADE"), nullable=False)
    file_path = Column(String(512), nullable=False)
    duration_seconds = Column(Integer, nullable=True)
    recorded_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    stream = relationship("CCTVStream", back_populates="recordings")
