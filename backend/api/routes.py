import asyncio
import base64
import io
import json
import os
import re
import shutil
import time
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select, text

from ..auth.auth import require_auth
from ..core.config_loader import DEFAULT_AGENTS, DEFAULT_PROVIDER, save_config, get_project_dir, ProjectConfig, load_config
from ..core.orchestrator import Orchestrator

router = APIRouter()
_orchestrators: dict[str, Orchestrator] = {}  # user_id → per-user orchestrator
_sio = None                                   # set by _init_sio() from main.py
_default_config = load_config()               # shared readonly default for connect handler

_AUTH_DISABLED = os.environ.get("AUTH_DISABLED", "").lower() in ("1", "true", "yes")

# In-memory upload token store: token → {user_id, upload_dir, files, manifest, created_at}
# Tokens expire after _MAX_UPLOAD_TOKEN_AGE seconds (default 3600 = 1 hour).
# Configurable via UPLOAD_TOKEN_TTL env var (in seconds).
_upload_tokens: dict[str, dict] = {}
_MAX_UPLOAD_TOKEN_AGE = int(os.environ.get("UPLOAD_TOKEN_TTL", "3600"))


def set_orchestrator(orch):
    """Legacy — no longer used by main.py. Kept for test compatibility."""
    pass


def _init_sio(sio_instance):
    global _sio
    _sio = sio_instance


def get_default_config():
    return _default_config


def get_orchestrators() -> dict[str, Orchestrator]:
    return _orchestrators


def _orchestrator_done(user_id: str):
    _orchestrators.pop(user_id, None)


async def _cleanup_expired_tokens():
    """Remove expired upload tokens and their disk directories."""
    now = time.monotonic()
    expired = [
        token for token, data in _upload_tokens.items()
        if now - data.get("created_at", 0) > _MAX_UPLOAD_TOKEN_AGE
    ]
    for token in expired:
        data = _upload_tokens.pop(token, None)
        if data:
            upload_dir = Path(data.get("upload_dir", ""))
            try:
                if upload_dir.exists():
                    shutil.rmtree(upload_dir)
            except Exception:
                pass


async def _upload_cleanup_loop():
    """Background task: clean up expired tokens every 5 minutes."""
    while True:
        await asyncio.sleep(300)
        await _cleanup_expired_tokens()


def start_upload_cleanup():
    """Start the background upload token cleanup task. Called from lifespan."""
    asyncio.create_task(_upload_cleanup_loop())


# ── Health check ──────────────────────────────────────────────────────────────
# Public endpoint (no auth) so the dashboard banner can read it pre-login.
# Cached for 30 s to avoid hammering the upstream provider on every poll.

_health_cache: tuple[float, dict] | None = None
_HEALTH_TTL_SECS = 30


async def _probe_zen_api() -> dict:
    """Check that the OpenCode Zen base URL is reachable. 401 still counts as up."""
    api_key = os.environ.get("OPENCODE_GO_API_KEY", "")
    if not api_key:
        return {"status": "unconfigured", "detail": "OPENCODE_GO_API_KEY not set"}
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(
                "https://opencode.ai/zen/v1/models",
                headers={"Authorization": f"Bearer {api_key}"},
            )
        # 2xx or 401 both mean the endpoint is reachable; only network errors
        # / timeouts indicate degradation.
        if resp.status_code < 500:
            return {"status": "ok", "detail": f"HTTP {resp.status_code}"}
        return {"status": "degraded", "detail": f"HTTP {resp.status_code}"}
    except (httpx.TimeoutException, httpx.ConnectError, httpx.HTTPError) as e:
        return {"status": "degraded", "detail": f"{type(e).__name__}: {e}"}


async def _probe_database() -> dict:
    """Run a trivial query against the DB. Missing DATABASE_URL is not a failure."""
    from ..db.session import get_session
    try:
        async with get_session() as session:
            if session is None:
                return {"status": "unconfigured", "detail": "DATABASE_URL not set"}
            await session.execute(text("SELECT 1"))
        return {"status": "ok", "detail": "SELECT 1 succeeded"}
    except Exception as e:  # noqa: BLE001 — any DB failure is degraded
        return {"status": "degraded", "detail": f"{type(e).__name__}: {e}"}


async def _probe_project_dir() -> dict:
    try:
        project_dir = get_project_dir()
        if not project_dir.exists():
            project_dir.mkdir(parents=True, exist_ok=True)
        if not project_dir.is_dir():
            return {"status": "degraded", "detail": f"{project_dir} is not a directory"}
        if not os.access(str(project_dir), os.W_OK):
            return {"status": "degraded", "detail": f"{project_dir} is not writable"}
        return {"status": "ok", "detail": str(project_dir)}
    except Exception as e:  # noqa: BLE001
        return {"status": "degraded", "detail": f"{type(e).__name__}: {e}"}


@router.get("/health")
async def health_check():
    """Return aggregated health status. Cached for 30 s."""
    global _health_cache
    now = time.monotonic()
    if _health_cache is not None and now - _health_cache[0] < _HEALTH_TTL_SECS:
        return _health_cache[1]

    results = await asyncio.gather(
        _probe_zen_api(),
        _probe_database(),
        _probe_project_dir(),
        return_exceptions=True,
    )

    def _coerce(r):
        if isinstance(r, Exception):
            return {"status": "degraded", "detail": f"{type(r).__name__}: {r}"}
        return r

    checks = {
        "zen_api":     _coerce(results[0]),
        "database":    _coerce(results[1]),
        "project_dir": _coerce(results[2]),
    }
    # unconfigured is treated as OK at the top level — running without a DB
    # or without a key is a valid dev configuration.
    overall = "degraded" if any(c["status"] == "degraded" for c in checks.values()) else "ok"
    payload = {
        "status": overall,
        "checks": checks,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    _health_cache = (now, payload)
    return payload


class ProjectBrief(BaseModel):
    brief: str
    upload_token: str | None = None


def _make_slug(name: str) -> str:
    """Convert a project name into a URL-safe slug."""
    s = name.strip().lower()
    s = re.sub(r'[^a-z0-9]+', '-', s)
    return s.strip('-') or "project"


@router.get("/projects")
async def list_projects(user: dict = Depends(require_auth)):
    """Return minimal project list for Dashboard."""
    from ..db.models import Project
    from ..db.session import get_session
    user_id = user.get("sub", "anonymous")

    async with get_session() as session:
        if session is None:
            return {"projects": []}
        result = await session.execute(
            select(Project)
            .where(Project.user_id == user_id)
            .order_by(Project.updated_at.desc())
        )
        rows = result.scalars().all()
        return {
            "projects": [
                {
                    "id": p.id,
                    "name": p.name,
                    "slug": p.slug,
                    "desc": p.desc,
                    "icon": p.icon or "",
                    "created_at": p.created_at.isoformat() if p.created_at else None,
                    "updated_at": p.updated_at.isoformat() if p.updated_at else None,
                }
                for p in rows
            ]
        }


@router.get("/projects/{project_id}")
async def get_project(project_id: str, user: dict = Depends(require_auth)):
    """Return full project detail for Workspace header."""
    from ..db.models import Project
    from ..db.session import get_session
    user_id = user.get("sub", "anonymous")

    async with get_session() as session:
        if session is None:
            raise HTTPException(status_code=503, detail="Database unavailable")
        result = await session.execute(
            select(Project).where(Project.id == project_id, Project.user_id == user_id)
        )
        row = result.scalar_one_or_none()
        if not row:
            raise HTTPException(status_code=404, detail="Project not found")

        # Find latest run status for this project
        from ..db.models import Run
        from sqlalchemy.orm import selectinload
        run_result = await session.execute(
            select(Run)
            .where(Run.project_id == project_id)
            .order_by(Run.started_at.desc())
            .limit(1)
            .options(selectinload(Run.files))
        )
        run = run_result.scalar_one_or_none()
        file_count = 0
        if run:
            file_count = len(run.files) if run.files else 0

        return {
            "id": row.id,
            "name": row.name,
            "slug": row.slug,
            "desc": row.desc,
            "icon": row.icon or "",
            "status": run.status if run else "ready",
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            "file_count": file_count,
        }


class UploadFileItem(BaseModel):
    filename: str
    content: str  # base64-encoded


class UploadRequest(BaseModel):
    files: list[UploadFileItem]


@router.post("/upload")
async def upload_files(body: UploadRequest, user: dict = Depends(require_auth)):
    """Accept uploaded design files, store them, return a token for start_project."""
    from ..core.file_upload import store_files, build_file_manifest

    user_id = user.get("sub", "anonymous")
    files_data: list[tuple[str, bytes]] = []
    for item in body.files:
        try:
            content = base64.b64decode(item.content)
        except Exception:
            return {"error": f"Invalid base64 for {item.filename}"}
        files_data.append((item.filename, content))

    upload_token = str(uuid.uuid4())
    project_dir = get_project_dir()
    upload_dir = project_dir / "uploads" / upload_token

    try:
        stored = store_files(upload_dir, files_data)
    except ValueError as e:
        return {"error": str(e)}

    manifest = build_file_manifest(stored)
    _upload_tokens[upload_token] = {
        "user_id": user_id,
        "upload_dir": str(upload_dir),
        "files": stored,
        "manifest": manifest,
        "created_at": time.monotonic(),
    }

    return {
        "upload_token": upload_token,
        "files": stored,
        "manifest": manifest,
    }


@router.post("/start-project")
async def start_project(body: ProjectBrief, user: dict = Depends(require_auth)):
    user_id = user.get("sub", "anonymous")

    # Check if user already has a running orchestrator
    existing = _orchestrators.get(user_id)
    if existing is not None and existing.is_running():
        return {"error": "already running"}

    # Resolve upload token (pop on consumption so it can't be reused)
    upload_dir = ""
    if body.upload_token and body.upload_token in _upload_tokens:
        token_data = _upload_tokens.pop(body.upload_token)
        if token_data.get("user_id") == user_id:
            upload_dir = token_data.get("upload_dir", "")
        # Opportunistic cleanup of other expired tokens
        asyncio.create_task(_cleanup_expired_tokens())

    # Dev bypass — skip billing gate entirely in local dev mode
    if _AUTH_DISABLED or user_id == "dev-user":
        plan = "pro"
        agent_limit = None
        balance = 999999  # effectively unlimited for credit estimate
    else:
        # Billing gate
        from ..db.session import get_session
        from ..db.models import UserCredits
        plan    = "none"
        balance = 0
        async with get_session() as session:
            if session is not None:
                credits  = await session.get(UserCredits, user_id)
                plan     = credits.plan          if credits else "none"
                balance  = credits.balance_cents if credits else 0

        if plan == "none":
            return {"error": "no_subscription"}
        if balance <= 0:
            return {"error": "no_credits"}
        agent_limit = 3 if plan == "starter" else None

    # Create a fresh orchestrator for this user
    run_id = str(uuid.uuid4())
    room = f"user:{user_id}"
    user_config = await _load_user_config(user_id)
    orch = Orchestrator(
        sio=_sio,
        config=user_config,
        room=room,
        on_done=_orchestrator_done,
    )
    _orchestrators[user_id] = orch

    run_timeout = int(os.environ.get("RUN_TIMEOUT_SECONDS", "600"))
    orch._run_timeout_seconds = run_timeout

    asyncio.create_task(
        orch.run(body.brief, user_id=user_id, agent_limit=agent_limit, plan=plan,
                 api_key="", upload_dir=upload_dir, run_id=run_id)
    )

    # Credit estimate — warn if estimated cost exceeds balance (real users only)
    credit_warning = None
    if not (_AUTH_DISABLED or user_id == "dev-user") and plan != "none":
        est_tokens_per_call = (4000 + 2000)  # prompt + completion estimate
        num_agents = len(user_config.agents) - 1  # exclude manager
        total_est_tokens = num_agents * est_tokens_per_call * 2  # 2 rounds per agent
        est_cost_cents = max(1, int(total_est_tokens * 0.01))  # rough ~$0.01/1K tokens
        if isinstance(balance, int) and est_cost_cents > balance:
            credit_warning = (
                f"This run may consume up to ${est_cost_cents / 100:.2f} in credits, "
                f"which exceeds your balance. Consider topping up."
            )

    return {"status": "started", "run_id": run_id,
            "credit_warning": credit_warning}


@router.post("/cancel")
async def cancel_project(user: dict = Depends(require_auth)):
    user_id = user.get("sub", "anonymous")
    orch = _orchestrators.get(user_id)
    if orch is None:
        return {"status": "idle"}
    orch.cancel()
    return {"status": "cancelling"}


@router.get("/config")
async def get_config(user: dict = Depends(require_auth)):
    user_id = user.get("sub", "anonymous")
    if _AUTH_DISABLED or user_id == "dev-user":
        config_path = Path(os.getcwd()) / "agent-team.config.json"
        if config_path.exists():
            try:
                return json.loads(config_path.read_text())
            except (json.JSONDecodeError, OSError):
                pass
        return {"sprint": "Sprint #1", "provider": DEFAULT_PROVIDER, "agents": DEFAULT_AGENTS}
    config = await _load_user_config(user_id)
    return {"sprint": config.sprint, "provider": {"name": config.provider.name,
             "baseURL": config.provider.baseURL, "apiKey": config.provider.apiKey},
             "agents": config.agents}


async def _load_user_config(user_id: str, project_name: str | None = None) -> ProjectConfig:
    """Load per-user config from DB, falling back to disk file."""
    from ..db.session import get_session
    from ..db.models import User
    from ..core.config_loader import DEFAULT_AGENTS, ProviderConfig, ProjectConfig, load_config
    sprint = "Sprint #1"
    agents = [a.copy() for a in DEFAULT_AGENTS]
    provider = ProviderConfig()
    async with get_session() as session:
        if session is not None:
            user_row = await session.get(User, user_id)
            if user_row and user_row.config_json:
                data = json.loads(user_row.config_json)
                sprint = data.get("sprint", sprint)
                if isinstance(data.get("agents"), list) and data["agents"]:
                    agents = data["agents"]
                if isinstance(data.get("provider"), dict):
                    p = data["provider"]
                    provider = ProviderConfig(
                        name=p.get("name", provider.name),
                        baseURL=p.get("baseURL", provider.baseURL),
                        apiKey=p.get("apiKey", provider.apiKey),
                    )
    if all_agents_default(agents):
        config_path = Path(os.getcwd()) / "agent-team.config.json"
        if config_path.exists():
            config = load_config(str(config_path), project_name=project_name)
            return config
    if not provider.apiKey:
        provider.apiKey = os.environ.get("OPENCODE_GO_API_KEY", "")
    mgr = next((a for a in agents if a.get("id") == "manager"), DEFAULT_AGENTS[0].copy())
    others = [a for a in agents if a.get("id") != "manager"]
    agents = [mgr] + others
    return ProjectConfig(project="", sprint=sprint, agents=agents, provider=provider)


def all_agents_default(agents: list) -> bool:
    from ..core.config_loader import DEFAULT_AGENTS
    return agents == [a.copy() for a in DEFAULT_AGENTS]


@router.put("/config")
async def put_config(body: dict[str, Any], user: dict = Depends(require_auth)):
    """Update agent config — Pro plan only."""
    from ..db.session import get_session
    from ..db.models import UserCredits
    from fastapi import HTTPException
    user_id = user.get("sub", "anonymous")

    # Dev bypass — skip plan gate in local dev mode
    if _AUTH_DISABLED or user_id == "dev-user":
        await save_config(body)
        return {"status": "saved"}

    async with get_session() as session:
        if session is not None:
            credits = await session.get(UserCredits, user_id)
            plan    = credits.plan if credits else "none"
            if plan != "pro":
                raise HTTPException(
                    status_code=403,
                    detail="Shared agent config requires Pro plan",
                )
    await save_config(body, user_id)
    return {"status": "saved"}


@router.get("/runs")
async def list_runs(user: dict = Depends(require_auth)):
    from ..db.session import get_session
    from ..db.models import Run
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    user_id = user.get("sub", "anonymous")
    async with get_session() as session:
        if session is None:
            return []
        result = await session.execute(
            select(Run)
            .where(Run.user_id == user_id)
            .order_by(Run.started_at.desc())
            .limit(50)
            .options(selectinload(Run.files))
        )
        runs = result.scalars().all()
        return [
            {
                "id": r.id,
                "brief": r.brief[:120],
                "status": r.status,
                "agents_used": json.loads(r.agents_used) if r.agents_used else [],
                "started_at": r.started_at.isoformat() if r.started_at else None,
                "finished_at": r.finished_at.isoformat() if r.finished_at else None,
                "file_count": len(r.files),
            }
            for r in runs
        ]


@router.get("/runs/{run_id}")
async def get_run(run_id: str, user: dict = Depends(require_auth)):
    from ..db.session import get_session
    from ..db.models import Run, TaskAcceptance
    from sqlalchemy.orm import selectinload
    from sqlalchemy import select
    from fastapi import HTTPException
    user_id = user.get("sub", "anonymous")
    async with get_session() as session:
        if session is None:
            raise HTTPException(status_code=503, detail="Database not configured")
        result = await session.execute(
            select(Run).where(Run.id == run_id).options(selectinload(Run.files))
        )
        run = result.scalar_one_or_none()
        if run is None or run.user_id != user_id:
            raise HTTPException(status_code=404, detail="Run not found")

        # Fetch acceptance criteria
        acc_result = await session.execute(
            select(TaskAcceptance)
            .where(TaskAcceptance.run_id == run_id)
            .order_by(TaskAcceptance.task_id, TaskAcceptance.met_order)
        )
        acceptance: dict[str, list[dict]] = {}
        for row in acc_result.scalars().all():
            acceptance.setdefault(str(row.task_id), []).append({
                "id": str(row.id),
                "criterion": row.criterion,
                "met": bool(row.met),
                "met_order": row.met_order,
                "checked_by": row.checked_by,
                "checked_at": row.checked_at.isoformat() if row.checked_at else None,
            })

        return {
            "id": run.id,
            "brief": run.brief,
            "status": run.status,
            "agents_used": json.loads(run.agents_used) if run.agents_used else [],
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "finished_at": run.finished_at.isoformat() if run.finished_at else None,
            "files": [
                {"path": f.path, "size": f.size, "content": f.content}
                for f in run.files
            ],
            "acceptance": acceptance,
        }


@router.get("/runs/{run_id}/download")
async def download_run(run_id: str, user: dict = Depends(require_auth)):
    """Download all project files for a completed run as a ZIP archive."""
    from ..db.session import get_session
    from ..db.models import Run
    from sqlalchemy.orm import selectinload
    from sqlalchemy import select
    from fastapi import HTTPException
    user_id = user.get("sub", "anonymous")
    async with get_session() as session:
        if session is None:
            raise HTTPException(status_code=503, detail="Database not configured")
        result = await session.execute(
            select(Run).where(Run.id == run_id).options(selectinload(Run.files))
        )
        run = result.scalar_one_or_none()
        if run is None or run.user_id != user_id:
            raise HTTPException(status_code=404, detail="Run not found")

        files = run.files
        if not files:
            raise HTTPException(status_code=404, detail="No files in this run")

        # Check total size
        total_size = sum(f.size or len(f.content.encode()) for f in files)
        MAX_ZIP_BYTES = 50_000_000
        if total_size > MAX_ZIP_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"Total file size ({total_size} bytes) exceeds maximum ({MAX_ZIP_BYTES} bytes)",
            )

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in files:
                zf.writestr(f.path, f.content)
        buf.seek(0)

        return StreamingResponse(
            buf,
            media_type="application/zip",
            headers={
                "Content-Disposition": f'attachment; filename="run-{run_id[:8]}.zip"',
            },
        )
