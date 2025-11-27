import shutil
import uuid
from pathlib import Path
from typing import BinaryIO

from fastapi import UploadFile

from ..core.config import get_settings


class MediaStorage:
    def __init__(self, base_path: Path):
        self.base_path = base_path
        self.base_path.mkdir(parents=True, exist_ok=True)

    def save_upload(self, owner_type: str, upload: UploadFile) -> Path:
        suffix = Path(upload.filename or "").suffix
        dest_dir = self.base_path / owner_type
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_path = dest_dir / f"{uuid.uuid4()}{suffix}"
        with dest_path.open("wb") as buffer:
            shutil.copyfileobj(upload.file, buffer)
        upload.file.seek(0)
        return dest_path

    def save_bytes(self, owner_type: str, data: BinaryIO, suffix: str = "") -> Path:
        dest_dir = self.base_path / owner_type
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_path = dest_dir / f"{uuid.uuid4()}{suffix}"
        with dest_path.open("wb") as buffer:
            shutil.copyfileobj(data, buffer)
        data.seek(0)
        return dest_path


def get_media_storage() -> MediaStorage:
    settings = get_settings()
    return MediaStorage(settings.resolved_media_root)
