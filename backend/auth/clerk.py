import os
import httpx
from jose import jwt, JWTError
from fastapi import HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

_bearer = HTTPBearer(auto_error=False)
_jwks_cache: dict | None = None

AUTH_DISABLED = os.environ.get("AUTH_DISABLED", "").lower() in ("1", "true", "yes")


async def _get_jwks() -> dict:
    global _jwks_cache
    if _jwks_cache is not None:
        return _jwks_cache
    url = os.environ.get("CLERK_JWKS_URL", "")
    if not url:
        raise HTTPException(status_code=500, detail="CLERK_JWKS_URL is not configured")
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, timeout=10)
        resp.raise_for_status()
        _jwks_cache = resp.json()
    return _jwks_cache


async def require_auth(
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
) -> dict:
    if AUTH_DISABLED:
        return {"sub": "dev-user"}

    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")

    token = credentials.credentials
    try:
        jwks = await _get_jwks()
        payload = jwt.decode(token, jwks, algorithms=["RS256"])
        return payload
    except JWTError as exc:
        raise HTTPException(status_code=401, detail=f"Invalid token: {exc}") from exc
