from __future__ import annotations

from datetime import datetime
from urllib.parse import urlencode

import requests
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..core.database import get_db
from ..core.security import clear_auth_cookie, create_oauth_state, create_session_token, decode_oauth_state, get_current_user, set_auth_cookie
from ..models.user import User
from ..schemas.auth import UserPreferencesUpdate, UserRead
from ..services.gym_seed import ensure_user_gym_defaults

router = APIRouter(prefix="/auth", tags=["auth"])


def _normalize_origin(origin: str) -> str:
    return origin.rstrip("/")


def _is_allowed_origin(origin: str) -> bool:
    settings = get_settings()
    normalized = _normalize_origin(origin)
    return any(_normalize_origin(allowed) == normalized for allowed in settings.parsed_allowed_origins)


def _google_callback_url() -> str:
    settings = get_settings()
    return f"{settings.public_base_url.rstrip('/')}{settings.api_prefix}/auth/google/callback"


def _redirect_with_error(origin: str, message: str) -> RedirectResponse:
    return RedirectResponse(url=f"{origin.rstrip('/')}/?auth_error={message}", status_code=status.HTTP_302_FOUND)


def _upsert_google_user(db: Session, profile: dict) -> User:
    email = (profile.get("email") or "").strip().lower()
    if not email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Google account did not provide an email")
    if not profile.get("email_verified"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Google email is not verified")

    google_sub = profile.get("sub")
    user = None
    if google_sub:
        user = db.query(User).filter(User.google_sub == google_sub).first()
    if user is None:
        user = db.query(User).filter(User.email == email).first()

    if user is None:
        user = User(email=email)
        db.add(user)

    user.email = email
    user.google_sub = google_sub or user.google_sub
    user.full_name = profile.get("name") or user.full_name
    user.picture_url = profile.get("picture") or user.picture_url
    user.last_login_at = datetime.utcnow()
    db.commit()
    db.refresh(user)
    ensure_user_gym_defaults(db, user.id)
    db.refresh(user)
    return user


@router.get("/google/start")
def google_start(redirect_origin: str = Query(..., min_length=1)):
    settings = get_settings()
    if not settings.google_client_id or not settings.google_client_secret:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Google auth is not configured")
    if not _is_allowed_origin(redirect_origin):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Redirect origin is not allowed")

    state = create_oauth_state(redirect_origin)
    query = urlencode(
        {
            "client_id": settings.google_client_id,
            "redirect_uri": _google_callback_url(),
            "response_type": "code",
            "scope": "openid email profile",
            "prompt": "select_account",
            "access_type": "online",
            "state": state,
        }
    )
    return RedirectResponse(url=f"https://accounts.google.com/o/oauth2/v2/auth?{query}", status_code=status.HTTP_302_FOUND)


@router.get("/google/callback")
def google_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_db),
):
    if not state:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing OAuth state")

    state_payload = decode_oauth_state(state)
    redirect_origin = state_payload["redirect_origin"]

    if error:
        return _redirect_with_error(redirect_origin, error)
    if not code:
        return _redirect_with_error(redirect_origin, "missing_code")

    settings = get_settings()
    token_response = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "code": code,
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "redirect_uri": _google_callback_url(),
            "grant_type": "authorization_code",
        },
        timeout=30,
    )
    if not token_response.ok:
        return _redirect_with_error(redirect_origin, "token_exchange_failed")

    access_token = token_response.json().get("access_token")
    if not access_token:
        return _redirect_with_error(redirect_origin, "missing_access_token")

    profile_response = requests.get(
        "https://openidconnect.googleapis.com/v1/userinfo",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=30,
    )
    if not profile_response.ok:
        return _redirect_with_error(redirect_origin, "userinfo_failed")

    user = _upsert_google_user(db, profile_response.json())
    session_token = create_session_token(user)
    response = RedirectResponse(url=f"{redirect_origin.rstrip('/')}/", status_code=status.HTTP_302_FOUND)
    set_auth_cookie(response, session_token, redirect_origin)
    return response


@router.get("/me", response_model=UserRead)
def read_current_user(current_user: User = Depends(get_current_user)):
    return current_user


@router.patch("/me/preferences", response_model=UserRead)
def update_preferences(payload: UserPreferencesUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    merged = dict(current_user.preferences_json or {})
    merged.update(payload.preferences_json or {})
    current_user.preferences_json = merged
    db.add(current_user)
    db.commit()
    db.refresh(current_user)
    return current_user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request):
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    clear_auth_cookie(response, request.headers.get("Origin"))
    return response