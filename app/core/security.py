from fastapi import HTTPException, Request, Security
from fastapi.security import APIKeyHeader
from starlette import status

from .config import get_settings


_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def require_api_key(request: Request, api_key: str = Security(_api_key_header)) -> None:
    if request.method == "OPTIONS":
        return
    settings = get_settings()
    if settings.api_key and api_key != settings.api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")
