from __future__ import annotations

import os
from datetime import datetime, timezone, timedelta

import bcrypt
import jwt as pyjwt
from fastapi import HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

_bearer = HTTPBearer(auto_error=False)

AUTH_DISABLED = os.environ.get("AUTH_DISABLED", "").lower() in ("1", "true", "yes")
_SECRET_KEY   = os.environ.get("SECRET_KEY", "dev-secret-change-in-production")
_ALGORITHM    = "HS256"
_TOKEN_DAYS   = 30


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


async def require_auth(
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
) -> dict:
    if AUTH_DISABLED:
        return {"sub": "dev-user", "email": "dev@local", "name": "Dev User"}

    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")

    return decode_token(credentials.credentials)
