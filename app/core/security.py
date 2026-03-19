from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import jwt
from fastapi import Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from ..models.user import User
from .config import get_settings
from .database import get_db


def require_api_key(request: Request) -> None:
    if request.method == "OPTIONS":
        return


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def create_session_token(user: User) -> str:
    settings = get_settings()
    issued_at = _now_utc()
    expires_at = issued_at + timedelta(hours=settings.auth_token_ttl_hours)
    payload = {
        "sub": user.id,
        "email": user.email,
        "type": "session",
        "iat": int(issued_at.timestamp()),
        "exp": int(expires_at.timestamp()),
        "iss": settings.public_base_url.rstrip("/"),
    }
    return jwt.encode(payload, settings.auth_secret_key, algorithm="HS256")


def create_oauth_state(redirect_origin: str) -> str:
    settings = get_settings()
    issued_at = _now_utc()
    expires_at = issued_at + timedelta(minutes=settings.oauth_state_ttl_minutes)
    payload = {
        "type": "oauth_state",
        "redirect_origin": redirect_origin.rstrip("/"),
        "iat": int(issued_at.timestamp()),
        "exp": int(expires_at.timestamp()),
        "iss": settings.public_base_url.rstrip("/"),
    }
    return jwt.encode(payload, settings.auth_secret_key, algorithm="HS256")


def decode_oauth_state(token: str) -> dict:
    settings = get_settings()
    payload = jwt.decode(
        token,
        settings.auth_secret_key,
        algorithms=["HS256"],
        issuer=settings.public_base_url.rstrip("/"),
    )
    if payload.get("type") != "oauth_state":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid OAuth state")
    return payload


def _cookie_options(origin: str | None = None) -> dict:
    settings = get_settings()
    hostname = urlparse(origin or "").hostname or ""
    is_local = hostname in {"localhost", "127.0.0.1"}
    return {
        "key": settings.auth_cookie_name,
        "httponly": True,
        "secure": False if is_local else settings.auth_cookie_secure,
        "samesite": "lax",
        "domain": None if is_local else settings.auth_cookie_domain,
        "path": "/",
        "max_age": settings.auth_token_ttl_hours * 3600,
    }


def set_auth_cookie(response: Response, token: str, origin: str | None = None) -> None:
    response.set_cookie(value=token, **_cookie_options(origin))


def clear_auth_cookie(response: Response, origin: str | None = None) -> None:
    options = _cookie_options(origin)
    response.delete_cookie(
        key=options["key"],
        path=options["path"],
        domain=options["domain"],
        secure=options["secure"],
        httponly=options["httponly"],
        samesite=options["samesite"],
    )


def _extract_session_token(request: Request) -> str | None:
    settings = get_settings()
    cookie_token = request.cookies.get(settings.auth_cookie_name)
    if cookie_token:
        return cookie_token
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header.removeprefix("Bearer ").strip()
    return None


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = _extract_session_token(request)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.auth_secret_key,
            algorithms=["HS256"],
            issuer=settings.public_base_url.rstrip("/"),
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session") from exc

    if payload.get("type") != "session":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session")

    user = db.get(User, payload.get("sub"))
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user
