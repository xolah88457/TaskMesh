"""
Custom auth API — email/password + Google OAuth + GitHub OAuth.

Endpoints:
  POST /api/auth/register           — create account with email + password
  POST /api/auth/login              — email + password → JWT
  GET  /api/auth/google/url         — return Google OAuth authorization URL
  GET  /api/auth/google/callback    — exchange code → upsert user → issue JWT → redirect frontend
  GET  /api/auth/github/url         — return GitHub OAuth authorization URL (for LOGIN, not code push)
  GET  /api/auth/github/callback    — exchange code → upsert user → issue JWT → redirect frontend
  GET  /api/auth/me                 — return current user info (requires auth)

Environment variables required:
  SECRET_KEY                — signs JWTs
  GOOGLE_CLIENT_ID          — GCP Console → APIs & Services → Credentials
  GOOGLE_CLIENT_SECRET      — same location
  GOOGLE_REDIRECT_URI       — (optional) override auto-detected callback URL
  GITHUB_AUTH_CLIENT_ID     — GitHub OAuth App for login
  GITHUB_AUTH_CLIENT_SECRET — same app
  GITHUB_AUTH_REDIRECT_URI  — (optional) override auto-detected callback URL
  FRONTEND_URL              — (optional) frontend URL for post-OAuth redirect
                               Required for split-origin (Vercel+Render).
                               Omit for same-origin or local dev (auto-derived).
  COOKIE_SAMESITE           — "strict" (default), "lax", or "none"
  ENVIRONMENT               — "production" forces Secure cookies
"""
import hmac
import logging
import os
import secrets
import uuid
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel

from ..auth.auth import hash_password, verify_password, create_token, require_auth, set_token_cookie

router = APIRouter(prefix="/auth")
_log = logging.getLogger(__name__)

GOOGLE_CLIENT_ID     = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI  = os.environ.get("GOOGLE_REDIRECT_URI", "")

GITHUB_AUTH_CLIENT_ID     = os.environ.get("GITHUB_AUTH_CLIENT_ID", "")
GITHUB_AUTH_CLIENT_SECRET = os.environ.get("GITHUB_AUTH_CLIENT_SECRET", "")
GITHUB_AUTH_REDIRECT_URI  = os.environ.get("GITHUB_AUTH_REDIRECT_URI", "")

FRONTEND_URL = os.environ.get("FRONTEND_URL", "")


def _get_base_url(request: Request) -> str:
    """Derive the backend's public URL from the incoming request.

    Handles reverse proxies (Render, Cloud Run, etc.) via
    X-Forwarded-Proto and X-Forwarded-Host headers.
    """
    scheme = request.headers.get("x-forwarded-proto", request.url.scheme or "http")
    host = request.headers.get("x-forwarded-host") or request.headers.get("host", "localhost:8000")
    return f"{scheme}://{host}"


def _oauth_redirect_uri(request: Request, env_var: str, path: str) -> str:
    """Build the OAuth redirect URI for a given callback path.

    FRONTEND_URL is the primary way to set the callback base — it routes
    OAuth callbacks through the proxy so cookies stay on a single origin.
    The per-provider env vars (GOOGLE_REDIRECT_URI / GITHUB_AUTH_REDIRECT_URI)
    act as fallback overrides when FRONTEND_URL is not set.
    """
    base = FRONTEND_URL or os.environ.get(env_var, "")
    if base:
        return f"{base.rstrip('/')}{path}"
    return f"{_get_base_url(request)}{path}"


def _get_frontend_url(request: Request) -> str:
    """Derive the frontend URL for post-OAuth redirects.

    Uses FRONTEND_URL env var if set (required for split-origin deploys
    like Vercel+Render). Otherwise assumes same-origin and falls back to
    the backend's own base URL (works for local dev).
    """
    if FRONTEND_URL:
        return FRONTEND_URL
    # Try Origin header — useful when the browser sends it
    origin = request.headers.get("origin", "")
    if origin and origin not in ("null", ""):
        return origin
    # Fall back to same-origin (local dev)
    return _get_base_url(request)


class RegisterRequest(BaseModel):
    email: str
    password: str
    name: str = ""
    remember_me: bool = False


class LoginRequest(BaseModel):
    email: str
    password: str
    remember_me: bool = False


@router.post("/register")
async def register(body: RegisterRequest):
    from sqlalchemy import select
    from ..db.session import get_session
    from ..db.models import User

    if not body.email or not body.password:
        raise HTTPException(status_code=400, detail="Email and password are required")
    if len(body.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    email = body.email.lower().strip()

    async with get_session() as session:
        if session is None:
            raise HTTPException(status_code=503, detail="Database not configured")

        result = await session.execute(select(User).where(User.email == email))
        if result.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Email already registered")

        user_id   = str(uuid.uuid4())
        user_name = body.name.strip() or email.split("@")[0]
        user = User(
            id=user_id,
            email=email,
            name=user_name,
            password_hash=hash_password(body.password),
            created_at=datetime.now(timezone.utc),
        )
        session.add(user)
        await session.flush()

    token = create_token(user_id, email, user_name)
    response = JSONResponse({"user": {"id": user_id, "email": email, "name": user_name}})
    set_token_cookie(response, token, remember_me=body.remember_me)
    return response


@router.post("/login")
async def login(body: LoginRequest):
    from sqlalchemy import select
    from ..db.session import get_session
    from ..db.models import User

    email = body.email.lower().strip()

    async with get_session() as session:
        if session is None:
            raise HTTPException(status_code=503, detail="Database not configured")
        result = await session.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()

    if not user or not user.password_hash:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = create_token(user.id, user.email, user.name or "")
    response = JSONResponse({"user": {"id": user.id, "email": user.email, "name": user.name}})
    set_token_cookie(response, token, remember_me=body.remember_me)
    return response


@router.get("/google/url")
async def google_auth_url(request: Request):
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=503, detail="Google OAuth not configured")
    redirect_uri = _oauth_redirect_uri(request, "GOOGLE_REDIRECT_URI", "/api/auth/google/callback")
    state = secrets.token_hex(16)
    url = (
        "https://accounts.google.com/o/oauth2/v2/auth"
        f"?client_id={GOOGLE_CLIENT_ID}"
        f"&redirect_uri={redirect_uri}"
        "&response_type=code"
        "&scope=openid%20email%20profile"
        "&access_type=offline"
        "&prompt=select_account"
        f"&state={state}"
    )
    response = JSONResponse({"auth_url": url})
    response.set_cookie("oauth_state", state, httponly=True, samesite="lax", max_age=300, path="/api/auth")
    _log.info("Google OAuth URL built: redirect_uri=%s", redirect_uri)
    return response


@router.get("/google/callback")
async def google_callback(request: Request, code: str, state: str = ""):
    """Exchange Google OAuth code for user info, upsert user, issue JWT, redirect to frontend."""
    print("[auth] Google callback hit — code=%s... state=%s...", code[:10] if code else "", state[:10] if state else "", flush=True)
    try:
        return await _google_callback_impl(request, code, state)
    except HTTPException:
        raise
    except Exception as exc:
        _log.exception("Google callback: unhandled exception")
        raise HTTPException(status_code=500, detail=f"Internal error: {type(exc).__name__}: {exc}")


async def _google_callback_impl(request: Request, code: str, state: str) -> RedirectResponse:
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        raise HTTPException(status_code=503, detail="Google OAuth not configured")

    redirect_uri = _oauth_redirect_uri(request, "GOOGLE_REDIRECT_URI", "/api/auth/google/callback")

    # Verify anti-CSRF state parameter. FastAPI always injects Request, so no
    # None-guard is needed; the previous `Request | None = None` annotation
    # tripped FastAPI's response-model analyser on Python 3.14.
    stored = request.cookies.get("oauth_state", "")
    if not stored or not hmac.compare_digest(stored, state):
        _log.warning("Google OAuth: invalid state parameter (csrf or expired)")
        raise HTTPException(status_code=400, detail="Invalid state parameter")

    async with httpx.AsyncClient() as client:
        try:
            # Exchange code for access token
            token_resp = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "code":          code,
                    "client_id":     GOOGLE_CLIENT_ID,
                    "client_secret": GOOGLE_CLIENT_SECRET,
                    "redirect_uri":  redirect_uri,
                    "grant_type":    "authorization_code",
                },
                timeout=15,
            )
        except httpx.HTTPError as exc:
            _log.exception("Google token exchange: httpx error")
            raise HTTPException(status_code=502, detail="Failed to reach Google")
        if token_resp.status_code != 200:
            _log.error("Google token exchange failed (status %s): %s", token_resp.status_code, token_resp.text)
            raise HTTPException(status_code=502, detail="Failed to exchange Google code")
        token_data = token_resp.json()
        access_token = token_data.get("access_token")
        if not access_token:
            _log.error("Google token response missing access_token: %s", token_data)
            raise HTTPException(status_code=502, detail="Failed to exchange Google code")

        try:
            # Get user info from Google
            userinfo_resp = await client.get(
                "https://www.googleapis.com/oauth2/v2/userinfo",
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=10,
            )
        except httpx.HTTPError as exc:
            _log.exception("Google userinfo: httpx error")
            raise HTTPException(status_code=502, detail="Failed to reach Google")
        if userinfo_resp.status_code != 200:
            _log.error("Google userinfo failed (status %s): %s", userinfo_resp.status_code, userinfo_resp.text)
            raise HTTPException(status_code=502, detail="Failed to get user info from Google")
        guser = userinfo_resp.json()

    google_id = guser.get("id") or guser.get("sub", "")
    email     = guser.get("email", "").lower().strip()
    name      = guser.get("name", "") or email.split("@")[0]

    if not email:
        raise HTTPException(status_code=400, detail="Google account has no email")

    from sqlalchemy import select
    from ..db.session import get_session
    from ..db.models import User

    async with get_session() as session:
        if session is None:
            raise HTTPException(status_code=503, detail="Database not configured")

        # Try by google_id first, then fall back to email (links existing email/password account)
        user = None
        if google_id:
            result = await session.execute(select(User).where(User.google_id == google_id))
            user = result.scalar_one_or_none()

        if user is None:
            result = await session.execute(select(User).where(User.email == email))
            user = result.scalar_one_or_none()

        if user is None:
            user_id = str(uuid.uuid4())
            user = User(
                id=user_id,
                email=email,
                name=name,
                google_id=google_id,
                created_at=datetime.now(timezone.utc),
            )
            session.add(user)
            await session.flush()
        else:
            # Link google_id to existing account if not yet linked
            if not user.google_id and google_id:
                user.google_id = google_id
            user.name = name

        user_id = user.id

    jwt_token = create_token(user_id, email, name)
    # Pass JWT in URL hash so it never hits a server log.
    # The cookie is set via POST /api/auth/exchange in a separate step
    # (not on the redirect) to avoid Set-Cookie being stripped by proxies.
    frontend_url = _get_frontend_url(request)
    response = RedirectResponse(f"{frontend_url}/auth/callback#{jwt_token}")
    # Clear the one-shot anti-CSRF state cookie now that it's been verified.
    # (GitHub callback already does this; Google was leaving it behind.)
    response.delete_cookie("oauth_state", path="/api/auth")
    return response


@router.get("/github/url")
async def github_auth_url(request: Request):
    if not GITHUB_AUTH_CLIENT_ID:
        raise HTTPException(status_code=503, detail="GitHub login not configured")
    redirect_uri = _oauth_redirect_uri(request, "GITHUB_AUTH_REDIRECT_URI", "/api/auth/github/callback")
    state = secrets.token_hex(16)
    url = (
        "https://github.com/login/oauth/authorize"
        f"?client_id={GITHUB_AUTH_CLIENT_ID}"
        f"&redirect_uri={redirect_uri}"
        "&scope=user:email"
        "&prompt=select_account"
        f"&state={state}"
    )
    response = JSONResponse({"auth_url": url})
    response.set_cookie("oauth_state", state, httponly=True, samesite="lax", max_age=300, path="/api/auth")
    _log.info("GitHub OAuth URL built: redirect_uri=%s", redirect_uri)
    return response


@router.get("/github/callback")
async def github_callback(request: Request, code: str, state: str = ""):
    """Exchange GitHub OAuth code for user info, upsert user, issue JWT, redirect to frontend."""
    print("[auth] GitHub callback hit — code=%s... state=%s...", code[:10] if code else "", state[:10] if state else "", flush=True)
    try:
        return await _github_callback_impl(request, code, state)
    except HTTPException:
        raise
    except Exception as exc:
        _log.exception("GitHub callback: unhandled exception")
        raise HTTPException(status_code=500, detail=f"Internal error: {type(exc).__name__}: {exc}")


async def _github_callback_impl(request: Request, code: str, state: str) -> RedirectResponse:
    if not GITHUB_AUTH_CLIENT_ID or not GITHUB_AUTH_CLIENT_SECRET:
        raise HTTPException(status_code=503, detail="GitHub login not configured")

    redirect_uri = _oauth_redirect_uri(request, "GITHUB_AUTH_REDIRECT_URI", "/api/auth/github/callback")

    # Verify anti-CSRF state parameter. FastAPI always injects Request — the
    # previous `Request | None = None` form was misinterpreted as a Pydantic
    # response model field on Python 3.14 and broke startup.
    stored = request.cookies.get("oauth_state", "")
    if not stored or not hmac.compare_digest(stored, state):
        _log.warning("GitHub OAuth: invalid state parameter (csrf or expired)")
        raise HTTPException(status_code=400, detail="Invalid state parameter")

    async with httpx.AsyncClient() as client:
        try:
            # Exchange code for access token
            token_resp = await client.post(
                "https://github.com/login/oauth/access_token",
                data={
                    "client_id":     GITHUB_AUTH_CLIENT_ID,
                    "client_secret": GITHUB_AUTH_CLIENT_SECRET,
                    "code":          code,
                    "redirect_uri":  redirect_uri,
                },
                headers={"Accept": "application/json"},
                timeout=15,
            )
        except httpx.HTTPError as exc:
            _log.exception("GitHub token exchange: httpx error")
            raise HTTPException(status_code=502, detail="Failed to reach GitHub")
        if token_resp.status_code != 200:
            _log.error("GitHub token exchange failed (status %s): %s", token_resp.status_code, token_resp.text)
            raise HTTPException(status_code=502, detail="Failed to exchange GitHub code")
        token_data = token_resp.json()
        access_token = token_data.get("access_token")
        if not access_token:
            err = token_data.get("error_description") or token_data.get("error") or str(token_data)
            _log.error("GitHub OAuth token error: %s", err)
            raise HTTPException(status_code=401, detail=f"GitHub rejected OAuth: {err}")

        try:
            # Get GitHub user info
            user_resp = await client.get(
                "https://api.github.com/user",
                headers={"Authorization": f"Bearer {access_token}", "Accept": "application/vnd.github+json"},
                timeout=10,
            )
        except httpx.HTTPError as exc:
            _log.exception("GitHub user info: httpx error")
            raise HTTPException(status_code=502, detail="Failed to reach GitHub")
        if user_resp.status_code != 200:
            _log.error("GitHub user info failed (status %s): %s", user_resp.status_code, user_resp.text)
            raise HTTPException(status_code=502, detail="Failed to get user info from GitHub")
        gh_user = user_resp.json()

        # Get primary email (GitHub hides emails unless scope includes user:email)
        try:
            email_resp = await client.get(
                "https://api.github.com/user/emails",
                headers={"Authorization": f"Bearer {access_token}", "Accept": "application/vnd.github+json"},
                timeout=10,
            )
            emails = email_resp.json() if email_resp.status_code == 200 else []
        except Exception:
            _log.exception("GitHub email fetch failed — using noreply fallback")
            emails = []

    github_id = str(gh_user.get("id", ""))
    name      = gh_user.get("name") or gh_user.get("login", "")
    # Pick primary verified email, fall back to first email, fall back to noreply
    email = next(
        (e["email"] for e in emails if e.get("primary") and e.get("verified")),
        next((e["email"] for e in emails), f"{gh_user.get('login', github_id)}@users.noreply.github.com"),
    ).lower()

    from sqlalchemy import select
    from ..db.session import get_session
    from ..db.models import User

    async with get_session() as session:
        if session is None:
            raise HTTPException(status_code=503, detail="Database not configured")

        # Try by github_id first, then email
        user_row = None
        if github_id:
            result = await session.execute(select(User).where(User.github_id == github_id))
            user_row = result.scalar_one_or_none()

        if user_row is None:
            result = await session.execute(select(User).where(User.email == email))
            user_row = result.scalar_one_or_none()

        if user_row is None:
            user_id = str(uuid.uuid4())
            user_row = User(
                id=user_id,
                email=email,
                name=name,
                github_id=github_id,
                created_at=datetime.now(timezone.utc),
            )
            session.add(user_row)
            await session.flush()
        else:
            if not user_row.github_id and github_id:
                user_row.github_id = github_id
            user_row.name = name

        user_id = user_row.id

    jwt_token = create_token(user_id, email, name)
    frontend_url = _get_frontend_url(request)
    response = RedirectResponse(f"{frontend_url}/auth/callback#{jwt_token}")
    response.delete_cookie("oauth_state", path="/api/auth")
    return response


@router.post("/exchange")
async def exchange_token(request: Request):
    """Exchange a JWT (from OAuth callback hash or login response) for an HttpOnly cookie.

    The JWT is passed in the JSON body. This endpoint sets the cookie on a
    regular JSON response rather than a redirect, avoiding Set-Cookie being
    stripped or mangled by proxies like Vercel rewrites.

    OAuth tokens always get a 7-day remember-me cookie.
    """
    from ..auth.auth import _verify_token, set_token_cookie, _TOKEN_DAYS
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")
    jwt_str = body.get("token", "")
    if not jwt_str:
        raise HTTPException(status_code=400, detail="Missing token")
    try:
        claims = _verify_token(jwt_str)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    resp = JSONResponse({"id": claims.get("sub", ""), "email": claims.get("email", ""), "name": claims.get("name", "")})
    set_token_cookie(resp, jwt_str, remember_me=body.get("remember_me", True))
    return resp


@router.get("/me")
async def get_me(user: dict = Depends(require_auth)):
    return {
        "id":    user["sub"],
        "email": user.get("email", ""),
        "name":  user.get("name", ""),
    }


@router.post("/logout")
async def logout_auth():
    """Clear the HttpOnly auth cookie. No auth required — if no cookie, it's a no-op."""
    from ..auth.auth import _cookie_samesite
    response = JSONResponse({"status": "logged_out"})
    samesite = _cookie_samesite()
    response.delete_cookie(
        key="token",
        path="/",
        httponly=True,
        secure=os.environ.get("ENVIRONMENT") == "production" or samesite == "none",
        samesite=samesite,
    )
    return response
