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


def set_token_cookie(response: Response, token: str, max_age_days: int = _TOKEN_DAYS) -> None:
    """Set the JWT in an HttpOnly, SameSite=Strict cookie."""
    response.set_cookie(
        key="token",
        value=token,
        httponly=True,
        secure=os.environ.get("ENVIRONMENT") == "production",
        samesite="strict",
        max_age=max_age_days * 86400,
        path="/",
    )


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
