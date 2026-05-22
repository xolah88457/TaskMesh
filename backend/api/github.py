"""
GitHub integration — OAuth connect and post-run push.

Flow:
  1. User clicks "Connect GitHub" in the UI
  2. Frontend opens GET /api/github/auth — redirects to GitHub OAuth
  3. GitHub redirects back to GET /api/github/callback?code=...
  4. Backend exchanges code for access token, stores in DB (user_github table)
  5. After a run completes, the orchestrator calls push_run_to_github()
     which creates a branch, commits all output files, and opens a PR

Environment variables required:
  GITHUB_CLIENT_ID     — GitHub OAuth app Client ID (code-push, not login)
  GITHUB_CLIENT_SECRET — GitHub OAuth app Client Secret
  GITHUB_REDIRECT_URI  — (optional) override auto-detected callback URL
  FRONTEND_URL         — (optional) frontend URL for post-OAuth redirect

The GitHub token is stored encrypted in the DB (UserGitHub table).
For simplicity, this implementation stores it in plaintext — add encryption
before going to production (use Python cryptography.fernet).
"""
import base64
import hashlib
import hmac
import logging
import os
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from ..auth.auth import require_auth

router = APIRouter(prefix="/github")
_log = logging.getLogger(__name__)

GITHUB_CLIENT_ID     = os.environ.get("GITHUB_CLIENT_ID", "")
GITHUB_CLIENT_SECRET = os.environ.get("GITHUB_CLIENT_SECRET", "")
GITHUB_REDIRECT_URI  = os.environ.get("GITHUB_REDIRECT_URI", "")
FRONTEND_URL         = os.environ.get("FRONTEND_URL", "")
SECRET_KEY           = os.environ.get("SECRET_KEY", "dev-secret-change-in-production")
# Note: GITHUB_CLIENT_ID/SECRET here are for code-push OAuth.
# Login OAuth uses GITHUB_AUTH_CLIENT_ID/SECRET in backend/api/auth.py.


def _get_base_url(request: Request) -> str:
    """Derive the backend's public URL from the incoming request.
    Handles reverse proxies (Render, etc.) via X-Forwarded-* headers."""
    scheme = request.headers.get("x-forwarded-proto", request.url.scheme or "http")
    host = request.headers.get("x-forwarded-host") or request.headers.get("host", "localhost:8000")
    return f"{scheme}://{host}"


def _github_redirect_uri(request: Request) -> str:
    """Build the GitHub OAuth redirect URI (code-push flow).

    Priority: explicit env var → FRONTEND_URL + path → request-derived.
    Routing through FRONTEND_URL keeps cookies on a single origin for
    split-origin deploys.
    """
    if GITHUB_REDIRECT_URI:
        return GITHUB_REDIRECT_URI
    if FRONTEND_URL:
        return f"{FRONTEND_URL.rstrip('/')}/api/github/callback"
    return f"{_get_base_url(request)}/api/github/callback"


def _frontend_redirect_url(request: Request) -> str:
    """Build the frontend URL for post-OAuth redirects.
    Uses FRONTEND_URL env var if set, otherwise falls back to same-origin."""
    if FRONTEND_URL:
        return FRONTEND_URL
    origin = request.headers.get("origin", "")
    if origin and origin not in ("null", ""):
        return origin
    return _get_base_url(request)


def _sign_state(user_id: str) -> str:
    """Pack user_id with an HMAC signature so the callback can verify it wasn't forged."""
    raw = user_id.encode()
    sig = hmac.new(SECRET_KEY.encode(), raw, hashlib.sha256).digest()[:16]
    return base64.urlsafe_b64encode(raw + b"." + base64.urlsafe_b64encode(sig)).decode().rstrip("=")


def _verify_state(state: str) -> str:
    """Return the user_id encoded in state, or raise if signature doesn't match."""
    try:
        padded = state + "=" * (-len(state) % 4)
        decoded = base64.urlsafe_b64decode(padded.encode())
        raw, sig_b64 = decoded.rsplit(b".", 1)
        sig = base64.urlsafe_b64decode(sig_b64)
        expected = hmac.new(SECRET_KEY.encode(), raw, hashlib.sha256).digest()[:16]
        if not hmac.compare_digest(sig, expected):
            raise ValueError("bad signature")
        return raw.decode()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid OAuth state: {e}")


class PushRequest(BaseModel):
    run_id: str
    repo: str      # "owner/repo"
    branch: str    # base branch to create PR against (default: "main")


# ── OAuth connect ─────────────────────────────────────────────────────────────

@router.get("/auth")
async def github_auth(request: Request, user: dict = Depends(require_auth)):
    """Return the GitHub OAuth authorization URL as JSON (frontend redirects using window.location.href)."""
    if not GITHUB_CLIENT_ID:
        raise HTTPException(status_code=503, detail="GitHub OAuth not configured")
    user_id = user.get("sub", "")
    state   = _sign_state(user_id)
    redirect_uri = _github_redirect_uri(request)
    url = (
        f"https://github.com/login/oauth/authorize"
        f"?client_id={GITHUB_CLIENT_ID}"
        f"&redirect_uri={redirect_uri}"
        f"&scope=repo"
        f"&state={state}"
    )
    _log.info("GitHub code-push OAuth URL built: redirect_uri=%s", redirect_uri)
    return {"auth_url": url}


@router.get("/callback")
async def github_callback(code: str, state: str, request: Request):
    """Exchange OAuth code for access token and store it."""
    if not GITHUB_CLIENT_ID or not GITHUB_CLIENT_SECRET:
        raise HTTPException(status_code=503, detail="GitHub OAuth not configured")

    user_id = _verify_state(state)
    redirect_uri = _github_redirect_uri(request)

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://github.com/login/oauth/access_token",
            data={
                "client_id":     GITHUB_CLIENT_ID,
                "client_secret": GITHUB_CLIENT_SECRET,
                "code":          code,
                "redirect_uri":  redirect_uri,
            },
            headers={"Accept": "application/json"},
            timeout=15,
        )
        if resp.status_code != 200:
            _log.error("GitHub code-push token exchange failed (status %s): %s", resp.status_code, resp.text)
            raise HTTPException(status_code=400, detail="Failed to exchange GitHub code")
        token_data = resp.json()

    access_token = token_data.get("access_token")
    if not access_token:
        raise HTTPException(status_code=400, detail=f"GitHub OAuth error: {token_data.get('error_description', 'unknown')}")

    # Get GitHub username
    async with httpx.AsyncClient() as client:
        me = await client.get(
            "https://api.github.com/user",
            headers={"Authorization": f"Bearer {access_token}", "Accept": "application/vnd.github+json"},
        )
        github_user = me.json().get("login", "")

    # Persist token
    from ..db.session import get_session
    from ..db.models import UserGitHub
    async with get_session() as session:
        if session is not None:
            row = await session.get(UserGitHub, user_id)
            if row is None:
                session.add(UserGitHub(
                    user_id=user_id,
                    github_login=github_user,
                    access_token=access_token,
                    connected_at=datetime.now(timezone.utc),
                ))
            else:
                row.github_login  = github_user
                row.access_token  = access_token
                row.connected_at  = datetime.now(timezone.utc)

    return RedirectResponse(f"{_frontend_redirect_url(request)}/?github=connected")


@router.get("/status")
async def github_status(user: dict = Depends(require_auth)):
    """Return GitHub connection status for the current user."""
    from ..db.session import get_session
    from ..db.models import UserGitHub
    user_id = user.get("sub", "")
    async with get_session() as session:
        if session is None:
            return {"connected": False}
        row = await session.get(UserGitHub, user_id)
        if row is None:
            return {"connected": False}
        return {"connected": True, "github_login": row.github_login}


@router.delete("/disconnect")
async def github_disconnect(user: dict = Depends(require_auth)):
    from ..db.session import get_session
    from ..db.models import UserGitHub
    user_id = user.get("sub", "")
    async with get_session() as session:
        if session is not None:
            row = await session.get(UserGitHub, user_id)
            if row:
                await session.delete(row)
    return {"status": "disconnected"}


@router.post("/push")
async def push_to_github(body: PushRequest, user: dict = Depends(require_auth)):
    """Create a branch, commit all files from a run, and open a PR. Pro plan only."""
    from ..db.session import get_session
    from ..db.models import UserGitHub, Run, UserCredits
    from sqlalchemy.orm import selectinload
    from sqlalchemy import select

    user_id = user.get("sub", "")

    # Pro gate
    async with get_session() as session:
        if session is not None:
            credits = await session.get(UserCredits, user_id)
            if not credits or credits.plan != "pro":
                raise HTTPException(
                    status_code=403,
                    detail="GitHub push requires Pro plan",
                )

    async with get_session() as session:
        if session is None:
            raise HTTPException(status_code=503, detail="Database not configured")

        # Verify GitHub is connected
        gh_row = await session.get(UserGitHub, user_id)
        if gh_row is None:
            raise HTTPException(status_code=400, detail="GitHub not connected")
        token = gh_row.access_token

        # Load run + files
        result = await session.execute(
            select(Run).where(Run.id == body.run_id).options(selectinload(Run.files))
        )
        run = result.scalar_one_or_none()
        if run is None or run.user_id != user_id:
            raise HTTPException(status_code=404, detail="Run not found")

        if not run.files:
            raise HTTPException(status_code=400, detail="This run has no output files to push")

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept":        "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    owner, repo = body.repo.split("/", 1)
    branch_name = f"taskmesh/{run.id[:8]}"

    async with httpx.AsyncClient(headers=headers, timeout=30) as gh:
        # Get base branch SHA
        base_ref = await gh.get(f"https://api.github.com/repos/{owner}/{repo}/git/ref/heads/{body.branch}")
        if base_ref.status_code == 404:
            raise HTTPException(status_code=400, detail=f"Branch '{body.branch}' not found in {body.repo}")
        base_sha = base_ref.json()["object"]["sha"]

        # Create new branch
        branch_resp = await gh.post(
            f"https://api.github.com/repos/{owner}/{repo}/git/refs",
            json={"ref": f"refs/heads/{branch_name}", "sha": base_sha},
        )
        if branch_resp.status_code not in (201, 422):  # 422 = already exists
            branch_resp.raise_for_status()

        # Get tree SHA of base commit
        commit_resp = await gh.get(f"https://api.github.com/repos/{owner}/{repo}/git/commits/{base_sha}")
        base_tree_sha = commit_resp.json()["tree"]["sha"]

        # Build git tree from files
        tree_items = [
            {
                "path":    f.path,
                "mode":    "100644",
                "type":    "blob",
                "content": f.content,
            }
            for f in run.files
        ]
        tree_resp = await gh.post(
            f"https://api.github.com/repos/{owner}/{repo}/git/trees",
            json={"base_tree": base_tree_sha, "tree": tree_items},
        )
        tree_resp.raise_for_status()
        new_tree_sha = tree_resp.json()["sha"]

        # Create commit
        commit_message = f"taskmesh: {run.brief[:72]}\n\nRun ID: {run.id}"
        new_commit = await gh.post(
            f"https://api.github.com/repos/{owner}/{repo}/git/commits",
            json={"message": commit_message, "tree": new_tree_sha, "parents": [base_sha]},
        )
        new_commit.raise_for_status()
        new_commit_sha = new_commit.json()["sha"]

        # Update branch to new commit
        await gh.patch(
            f"https://api.github.com/repos/{owner}/{repo}/git/refs/heads/{branch_name}",
            json={"sha": new_commit_sha, "force": True},
        )

        # Open PR
        pr_resp = await gh.post(
            f"https://api.github.com/repos/{owner}/{repo}/pulls",
            json={
                "title": f"[TaskMesh] {run.brief[:60]}",
                "body": (
                    f"Generated by **TaskMesh** on {datetime.now(timezone.utc).strftime('%Y-%m-%d')}.\n\n"
                    f"**Brief:** {run.brief}\n\n"
                    f"**Files changed:** {len(run.files)}\n\n"
                    f"Run ID: `{run.id}`"
                ),
                "head": branch_name,
                "base": body.branch,
            },
        )
        if pr_resp.status_code == 422:
            # PR might already exist
            return {"status": "branch_pushed", "branch": branch_name, "pr_url": None}
        pr_resp.raise_for_status()
        pr_url = pr_resp.json()["html_url"]

    return {"status": "pushed", "branch": branch_name, "pr_url": pr_url}
