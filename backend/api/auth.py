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
  GOOGLE_REDIRECT_URI       — e.g. http://localhost:8000/api/auth/google/callback
  GITHUB_AUTH_CLIENT_ID     — GitHub OAuth App for login (can be same app as push, different redirect)
  GITHUB_AUTH_CLIENT_SECRET — same app
  GITHUB_AUTH_REDIRECT_URI  — e.g. http://localhost:8000/api/auth/github/callback
  FRONTEND_URL              — where to redirect after OAuth (e.g. http://localhost:5173)
"""
import hmac
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

GOOGLE_CLIENT_ID     = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI  = os.environ.get("GOOGLE_REDIRECT_URI", "http://localhost:8000/api/auth/google/callback")

GITHUB_AUTH_CLIENT_ID     = os.environ.get("GITHUB_AUTH_CLIENT_ID", "")
GITHUB_AUTH_CLIENT_SECRET = os.environ.get("GITHUB_AUTH_CLIENT_SECRET", "")
GITHUB_AUTH_REDIRECT_URI  = os.environ.get("GITHUB_AUTH_REDIRECT_URI", "http://localhost:8000/api/auth/github/callback")

FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:5173")


class RegisterRequest(BaseModel):
    email: str
    password: str
    name: str = ""


class LoginRequest(BaseModel):
    email: str
    password: str


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
    set_token_cookie(response, token)
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
    set_token_cookie(response, token)
    return response


@router.get("/google/url")
async def google_auth_url():
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=503, detail="Google OAuth not configured")
    url = (
        "https://accounts.google.com/o/oauth2/v2/auth"
        f"?client_id={GOOGLE_CLIENT_ID}"
        f"&redirect_uri={GOOGLE_REDIRECT_URI}"
        "&response_type=code"
        "&scope=openid%20email%20profile"
        "&access_type=offline"
        "&prompt=select_account"
        f"&state={secrets.token_hex(16)}"
    )
    response = JSONResponse({"auth_url": url})
    response.set_cookie("oauth_state", url.split("&state=")[1], httponly=True, samesite="lax", max_age=300, path="/api/auth")
    return response


@router.get("/google/callback")
async def google_callback(code: str, state: str = "", request: "Request | None" = None):
    """Exchange Google OAuth code for user info, upsert user, issue JWT, redirect to frontend."""
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        raise HTTPException(status_code=503, detail="Google OAuth not configured")

    # Verify anti-CSRF state parameter
    from fastapi import Request as _Request
    if request and isinstance(request, _Request):
        stored = request.cookies.get("oauth_state", "")
        if not stored or not hmac.compare_digest(stored, state):
            raise HTTPException(status_code=400, detail="Invalid state parameter")

    async with httpx.AsyncClient() as client:
        # Exchange code for access token
        token_resp = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code":          code,
                "client_id":     GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "redirect_uri":  GOOGLE_REDIRECT_URI,
                "grant_type":    "authorization_code",
            },
            timeout=15,
        )
        if token_resp.status_code != 200:
            raise HTTPException(status_code=400, detail="Failed to exchange Google code")
        token_data = token_resp.json()

        # Get user info from Google
        userinfo_resp = await client.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {token_data['access_token']}"},
            timeout=10,
        )
        if userinfo_resp.status_code != 200:
            raise HTTPException(status_code=400, detail="Failed to get user info from Google")
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
    # The HttpOnly cookie is set alongside for XSS-safe auth.
    response = RedirectResponse(f"{FRONTEND_URL}/auth/callback#{jwt_token}")
    set_token_cookie(response, jwt_token)
    # Clear the one-shot anti-CSRF state cookie now that it's been verified.
    # (GitHub callback already does this; Google was leaving it behind.)
    response.delete_cookie("oauth_state", path="/api/auth")
    return response


@router.get("/github/url")
async def github_auth_url():
    if not GITHUB_AUTH_CLIENT_ID:
        raise HTTPException(status_code=503, detail="GitHub login not configured")
    url = (
        "https://github.com/login/oauth/authorize"
        f"?client_id={GITHUB_AUTH_CLIENT_ID}"
        f"&redirect_uri={GITHUB_AUTH_REDIRECT_URI}"
        "&scope=user:email"
        "&prompt=select_account"
        f"&state={secrets.token_hex(16)}"
    )
    response = JSONResponse({"auth_url": url})
    response.set_cookie("oauth_state", url.split("&state=")[1], httponly=True, samesite="lax", max_age=300, path="/api/auth")
    return response


@router.get("/github/callback")
async def github_callback(code: str, state: str = "", request: Request | None = None):
    """Exchange GitHub OAuth code for user info, upsert user, issue JWT, redirect to frontend."""
    if not GITHUB_AUTH_CLIENT_ID or not GITHUB_AUTH_CLIENT_SECRET:
        raise HTTPException(status_code=503, detail="GitHub login not configured")

    # Verify anti-CSRF state parameter
    if request:
        stored = request.cookies.get("oauth_state", "")
        if not stored or not hmac.compare_digest(stored, state):
            raise HTTPException(status_code=400, detail="Invalid state parameter")

    async with httpx.AsyncClient() as client:
        # Exchange code for access token
        token_resp = await client.post(
            "https://github.com/login/oauth/access_token",
            data={
                "client_id":     GITHUB_AUTH_CLIENT_ID,
                "client_secret": GITHUB_AUTH_CLIENT_SECRET,
                "code":          code,
                "redirect_uri":  GITHUB_AUTH_REDIRECT_URI,
            },
            headers={"Accept": "application/json"},
            timeout=15,
        )
        if token_resp.status_code != 200:
            raise HTTPException(status_code=400, detail="Failed to exchange GitHub code")
        token_data = token_resp.json()
        access_token = token_data.get("access_token")
        if not access_token:
            raise HTTPException(status_code=400, detail=f"GitHub OAuth error: {token_data.get('error_description', 'unknown')}")

        # Get GitHub user info
        user_resp = await client.get(
            "https://api.github.com/user",
            headers={"Authorization": f"Bearer {access_token}", "Accept": "application/vnd.github+json"},
            timeout=10,
        )
        if user_resp.status_code != 200:
            raise HTTPException(status_code=400, detail="Failed to get user info from GitHub")
        gh_user = user_resp.json()

        # Get primary email (GitHub hides emails unless scope includes user:email)
        email_resp = await client.get(
            "https://api.github.com/user/emails",
            headers={"Authorization": f"Bearer {access_token}", "Accept": "application/vnd.github+json"},
            timeout=10,
        )
        emails = email_resp.json() if email_resp.status_code == 200 else []

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
    response = RedirectResponse(f"{FRONTEND_URL}/auth/callback#{jwt_token}")
    set_token_cookie(response, jwt_token)
    response.delete_cookie("oauth_state", path="/api/auth")
    return response


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
