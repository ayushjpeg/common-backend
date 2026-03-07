import base64
import io
import mimetypes
import re
import shutil
import uuid
from pathlib import Path
from typing import BinaryIO

from fastapi import HTTPException, UploadFile, status

from ..core.config import get_settings


class MediaStorage:
    def __init__(self, base_path: Path):
        self.base_path = base_path
        self.base_path.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _parse_data_url(data_url: str) -> tuple[bytes, str | None]:
        pattern = re.compile(r"^data:(?P<mime>[\w/+.-]+)?;base64,(?P<data>.+)$")
        match = pattern.match(data_url.strip())
        if not match:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid data URL")
        mime_type = match.group("mime") or "application/octet-stream"
        try:
            raw_bytes = base64.b64decode(match.group("data"))
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unable to decode image data") from exc
        return raw_bytes, mime_type

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

    def save_data_url(self, owner_type: str, data_url: str) -> tuple[Path, str | None]:
        raw_bytes, mime_type = self._parse_data_url(data_url)
        suffix = mimetypes.guess_extension(mime_type or "") or ""
        dest_dir = self.base_path / owner_type
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_path = dest_dir / f"{uuid.uuid4()}{suffix}"
        with dest_path.open("wb") as buffer:
            buffer.write(raw_bytes)
        return dest_path, mime_type


def build_public_url(file_path: str | Path) -> str:
    settings = get_settings()
    path = Path(file_path)
    # Passthrough fully-qualified URLs (including data URLs).
    if path.as_posix().startswith("http://") or path.as_posix().startswith("https://") or path.as_posix().startswith("data:"):
        return path.as_posix()

    try:
        relative = path.resolve().relative_to(settings.resolved_media_root)
    except Exception:  # noqa: BLE001
        relative = path.name

    base = (settings.media_base_url or "/media").rstrip("/")
    return f"{base}/{Path(relative).as_posix()}"


def get_media_storage() -> MediaStorage:
    settings = get_settings()
    return MediaStorage(settings.resolved_media_root)
