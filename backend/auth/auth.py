from __future__ import annotations

import os
import re
import warnings
from datetime import datetime, timezone, timedelta

import bcrypt
import jwt as pyjwt
from fastapi import HTTPException, Request, Security
from fastapi.responses import Response
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

_bearer = HTTPBearer(auto_error=False)

AUTH_DISABLED = os.environ.get("AUTH_DISABLED", "").lower() in ("1", "true", "yes")
_DEFAULT_SECRET = "dev-secret-change-in-production"
_SECRET_KEY   = os.environ.get("SECRET_KEY", _DEFAULT_SECRET)
_ALGORITHM    = "HS256"
_TOKEN_DAYS   = int(os.environ.get("JWT_TOKEN_DAYS", "30"))

if _SECRET_KEY == _DEFAULT_SECRET and not AUTH_DISABLED:
    warnings.warn(
        "SECRET_KEY env var is unset — JWTs will be signed with a publicly known "
        "default value. Set SECRET_KEY before going to production.",
        RuntimeWarning,
        stacklevel=2,
    )

if AUTH_DISABLED:
    warnings.warn(
        "AUTH_DISABLED is true — all JWT authentication and billing gates are "
        "bypassed. Never enable this in production.",
        RuntimeWarning,
        stacklevel=2,
    )


def _cookie_samesite() -> str:
    """Pick the auth cookie's SameSite policy.

    Defaults to "strict" — the safest for local dev where everything is
    same-origin. When the frontend and backend live on different domains
    (e.g. Vercel front, Render back) Socket.IO opens a direct WebSocket
    to the backend; samesite=strict drops the cookie on that cross-site
    request and the socket can't authenticate.

    Operators on a split-origin deploy should set:
        COOKIE_SAMESITE=none
        ENVIRONMENT=production       # forces secure=true
    """
    val = os.environ.get("COOKIE_SAMESITE", "strict").lower()
    if val not in ("strict", "lax", "none"):
        return "strict"
    return val


def set_token_cookie(
    response: Response,
    token: str,
    max_age_days: int | None = _TOKEN_DAYS,
    remember_me: bool = False,
) -> None:
    """Set the JWT in an HttpOnly cookie.

    When *remember_me* is False, the cookie is a session cookie (no max_age)
    and is deleted when the browser closes. When True, the cookie expires
    after 7 days (MAX_REMEMBER_DAYS).

    SameSite is configurable for split-origin deployments — see _cookie_samesite()."""
    samesite = _cookie_samesite()
    # Secure=True required for cookies to persist across browser restarts
    # over HTTPS. Disable only in explicit local development (AUTH_DISABLED).
    secure = not AUTH_DISABLED or os.environ.get("ENVIRONMENT") == "production" or samesite == "none"
    # Session cookie: no max_age/expires → deleted when browser closes
    # Remember-me: 7-day cookie
    max_days: int | None = None
    if remember_me:
        max_days = 7
    elif max_age_days is not None and max_age_days > 0:
        max_days = max_age_days
    cookie_kwargs: dict = dict(
        key="token",
        value=token,
        httponly=True,
        secure=secure,
        samesite=samesite,
        path="/",
    )
    if max_days is not None:
        cookie_kwargs["max_age"] = max_days * 86400
        cookie_kwargs["expires"] = (datetime.now(timezone.utc) + timedelta(days=max_days)).strftime("%a, %d %b %Y %H:%M:%S GMT")
    response.set_cookie(**cookie_kwargs)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def create_token(user_id: str, email: str, name: str = "") -> str:
    payload = {
        "sub":   user_id,
        "email": email,
        "name":  name,
        "exp":   datetime.now(timezone.utc) + timedelta(days=_TOKEN_DAYS),
        "iat":   datetime.now(timezone.utc),
    }
    return pyjwt.encode(payload, _SECRET_KEY, algorithm=_ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        return pyjwt.decode(token, _SECRET_KEY, algorithms=[_ALGORITHM])
    except pyjwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except pyjwt.InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail=f"Invalid token: {exc}")


def _read_cookie_token(request: Request) -> str | None:
    """Extract JWT from the HttpOnly cookie header."""
    cookie_str = request.headers.get("cookie", "")
    match = re.search(r'(?:^|;\s*)token=([^;]+)', cookie_str)
    if match:
        return match.group(1)
    return None


async def require_auth(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
) -> dict:
    """Authenticate via HttpOnly cookie (preferred) or Authorization: Bearer header.

    Cookie path is backward-compatible with the Bearer header path — during
    migration both methods work. Once all clients use cookies, Bearer can be removed.
    """
    if AUTH_DISABLED:
        return {"sub": "dev-user", "email": "dev@local", "name": "Dev User"}

    # Try HttpOnly cookie first (XSS-safe)
    cookie_token = _read_cookie_token(request)
    if cookie_token:
        return decode_token(cookie_token)

    # Fall back to Authorization: Bearer header
    if credentials:
        return decode_token(credentials.credentials)

    raise HTTPException(status_code=401, detail="Not authenticated")
