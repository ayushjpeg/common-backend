import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, JSON, String

from ..core.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String(255), nullable=False, unique=True, index=True)
    full_name = Column(String(255), nullable=True)
    google_sub = Column(String(255), nullable=True, unique=True, index=True)
    picture_url = Column(String(512), nullable=True)
    preferences_json = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login_at = Column(DateTime, nullable=True)