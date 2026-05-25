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
GITHUB_APP_SLUG      = os.environ.get("GITHUB_APP_SLUG", "")  # e.g. "taskmesh"
FRONTEND_URL         = os.environ.get("FRONTEND_URL", "")
SECRET_KEY           = os.environ.get("SECRET_KEY", "dev-secret-change-in-production")
# Note: GITHUB_CLIENT_ID/SECRET here are for code-push OAuth.
# Login OAuth uses GITHUB_AUTH_CLIENT_ID/SECRET in backend/api/auth.py.
# GitHub App credentials live in backend/core/github_sink.py (GITHUB_APP_ID + key).


def _get_base_url(request: Request) -> str:
    """Derive the backend's public URL from the incoming request.
    Handles reverse proxies (Render, etc.) via X-Forwarded-* headers."""
    scheme = request.headers.get("x-forwarded-proto", request.url.scheme or "http")
    host = request.headers.get("x-forwarded-host") or request.headers.get("host", "localhost:8000")
    return f"{scheme}://{host}"


def _github_redirect_uri(request: Request) -> str:
    """Build the GitHub OAuth redirect URI (code-push flow).
    FRONTEND_URL takes priority; per-provider env var is a fallback."""
    base = FRONTEND_URL or GITHUB_REDIRECT_URI
    if base:
        return f"{base.rstrip('/')}/api/github/callback"
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
        try:
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
        except httpx.HTTPError:
            _log.exception("GitHub code-push token exchange: httpx error")
            raise HTTPException(status_code=502, detail="Failed to reach GitHub")
        if resp.status_code != 200:
            _log.error("GitHub code-push token exchange failed (status %s): %s", resp.status_code, resp.text)
            raise HTTPException(status_code=502, detail="Failed to exchange GitHub code")
        token_data = resp.json()

    access_token = token_data.get("access_token")
    if not access_token:
        err = token_data.get("error_description") or token_data.get("error") or str(token_data)
        _log.error("GitHub code-push token error: %s", err)
        raise HTTPException(status_code=401, detail=f"GitHub rejected OAuth: {err}")

    # Get GitHub username
    try:
        async with httpx.AsyncClient() as client:
            me = await client.get(
                "https://api.github.com/user",
                headers={"Authorization": f"Bearer {access_token}", "Accept": "application/vnd.github+json"},
                timeout=10,
            )
            if me.status_code != 200:
                _log.error("GitHub code-push user info failed (status %s): %s", me.status_code, me.text)
                raise HTTPException(status_code=502, detail="Failed to get user info from GitHub")
            github_user = me.json().get("login", "")
    except httpx.HTTPError:
        _log.exception("GitHub code-push user info: httpx error")
        raise HTTPException(status_code=502, detail="Failed to reach GitHub")

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


# ── GitHub App installation flow ─────────────────────────────────────────────
#
# Newer, preferred flow. The user installs the TaskMesh GitHub App on their
# account / org and selects which repos to grant. We never persist a long-
# lived bearer token; installation access tokens are minted on demand via
# core/github_sink.py.

class _InstallRepoBody(BaseModel):
    default_repo:   str
    default_branch: str = "main"


@router.get("/install/url")
async def github_install_url(user: dict = Depends(require_auth)):
    """Return the GitHub install URL for the TaskMesh App."""
    if not GITHUB_APP_SLUG:
        raise HTTPException(status_code=503, detail="github_app_unconfigured")
    user_id = user.get("sub", "")
    state   = _sign_state(user_id)
    url = (
        f"https://github.com/apps/{GITHUB_APP_SLUG}/installations/new"
        f"?state={state}"
    )
    return {"install_url": url}


@router.get("/install/callback")
async def github_install_callback(
    request: Request,
    installation_id: str,
    state: str = "",
    setup_action: str = "install",
):
    """GitHub App post-install redirect. Persists the installation_id."""
    user_id = _verify_state(state) if state else ""
    if not user_id:
        raise HTTPException(status_code=400, detail="missing_state")
    if setup_action not in ("install", "update"):
        # 'request' or other states — ignore silently and bounce home.
        return RedirectResponse(f"{_frontend_redirect_url(request)}/?github=skipped")

    # Fetch the installation to learn the github_login of the account
    from ..core.github_sink import _make_app_jwt, is_app_configured
    github_login = ""
    if is_app_configured():
        try:
            app_jwt = _make_app_jwt()
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"https://api.github.com/app/installations/{installation_id}",
                    headers={
                        "Authorization": f"Bearer {app_jwt}",
                        "Accept": "application/vnd.github+json",
                        "X-GitHub-Api-Version": "2022-11-28",
                    },
                )
            if resp.status_code == 200:
                github_login = resp.json().get("account", {}).get("login", "")
        except Exception:
            _log.exception("github install callback: failed to read installation")

    from ..db.session import get_session
    from ..db.models import UserGitHubInstall
    async with get_session() as session:
        if session is None:
            raise HTTPException(status_code=503, detail="db_unavailable")
        row = await session.get(UserGitHubInstall, user_id)
        if row is None:
            session.add(UserGitHubInstall(
                user_id=user_id,
                installation_id=installation_id,
                github_login=github_login or None,
                scopes="contents:write,pull_requests:write",
                installed_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            ))
        else:
            row.installation_id = installation_id
            if github_login:
                row.github_login = github_login
            row.updated_at = datetime.now(timezone.utc)
    return RedirectResponse(f"{_frontend_redirect_url(request)}/teams?github=installed")


@router.get("/install/status")
async def github_install_status(user: dict = Depends(require_auth)):
    """Return current install state for the authenticated user."""
    from ..db.session import get_session
    from ..db.models import UserGitHubInstall
    user_id = user.get("sub", "")
    async with get_session() as session:
        if session is None:
            return {"installed": False}
        row = await session.get(UserGitHubInstall, user_id)
        if row is None:
            return {"installed": False}
        return {
            "installed":      True,
            "installation_id": row.installation_id,
            "github_login":   row.github_login,
            "default_repo":   row.default_repo,
            "default_branch": row.default_branch,
        }


@router.put("/install/repo")
async def github_install_set_repo(body: _InstallRepoBody, user: dict = Depends(require_auth)):
    """Set the user's default repo + branch for Agent Teams output."""
    if "/" not in body.default_repo or not body.default_repo.strip("/"):
        raise HTTPException(status_code=400, detail="invalid_repo")
    from ..db.session import get_session
    from ..db.models import UserGitHubInstall
    user_id = user.get("sub", "")
    async with get_session() as session:
        if session is None:
            raise HTTPException(status_code=503, detail="db_unavailable")
        row = await session.get(UserGitHubInstall, user_id)
        if row is None:
            raise HTTPException(status_code=404, detail="not_installed")
        row.default_repo   = body.default_repo.strip()
        row.default_branch = (body.default_branch or "main").strip()
        row.updated_at     = datetime.now(timezone.utc)
    return {
        "default_repo":   row.default_repo,
        "default_branch": row.default_branch,
    }


@router.delete("/install")
async def github_install_uninstall(user: dict = Depends(require_auth)):
    """Remove the install row. Does NOT call GitHub — the user uninstalls there separately."""
    from ..db.session import get_session
    from ..db.models import UserGitHubInstall
    user_id = user.get("sub", "")
    async with get_session() as session:
        if session is not None:
            row = await session.get(UserGitHubInstall, user_id)
            if row:
                await session.delete(row)
    return {"status": "uninstalled"}


@router.get("/install/repos")
async def github_install_list_repos(user: dict = Depends(require_auth)):
    """List repos the installation has access to. Used by the repo-picker UI."""
    from ..db.session import get_session
    from ..db.models import UserGitHubInstall
    from ..core.github_sink import _installation_token, GitHubSinkError
    user_id = user.get("sub", "")
    async with get_session() as session:
        if session is None:
            raise HTTPException(status_code=503, detail="db_unavailable")
        row = await session.get(UserGitHubInstall, user_id)
    if row is None:
        raise HTTPException(status_code=400, detail="not_installed")
    try:
        token = await _installation_token(row.installation_id)
    except GitHubSinkError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.code)
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            "https://api.github.com/installation/repositories?per_page=100",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail="github_list_failed")
    data = resp.json()
    repos = [
        {
            "full_name":     r.get("full_name", ""),
            "default_branch": r.get("default_branch", "main"),
            "private":       bool(r.get("private", False)),
        }
        for r in data.get("repositories", [])
    ]
    return {"repositories": repos}


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
