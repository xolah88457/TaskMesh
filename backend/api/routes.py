import asyncio
import base64
import json
import os
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..auth.auth import require_auth
from ..core.config_loader import DEFAULT_AGENTS, DEFAULT_PROVIDER, save_config, get_project_dir

router = APIRouter()
_orchestrator = None

_AUTH_DISABLED = os.environ.get("AUTH_DISABLED", "").lower() in ("1", "true", "yes")

# In-memory upload token store: token → {user_id, upload_dir, files, manifest}
_upload_tokens: dict[str, dict] = {}


def set_orchestrator(orch):
    global _orchestrator
    _orchestrator = orch


class ProjectBrief(BaseModel):
    brief: str
    upload_token: str | None = None


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
    }

    return {
        "upload_token": upload_token,
        "files": stored,
        "manifest": manifest,
    }


@router.post("/start-project")
async def start_project(body: ProjectBrief, user: dict = Depends(require_auth)):
    if _orchestrator is None:
        return {"error": "orchestrator not ready"}
    if _orchestrator.is_running():
        return {"error": "already running"}

    user_id = user.get("sub", "anonymous")

    # Resolve upload token
    upload_dir = ""
    if body.upload_token and body.upload_token in _upload_tokens:
        token_data = _upload_tokens[body.upload_token]
        if token_data.get("user_id") == user_id:
            upload_dir = token_data.get("upload_dir", "")

    # Dev bypass — skip billing gate entirely in local dev mode
    if _AUTH_DISABLED or user_id == "dev-user":
        asyncio.create_task(
            _orchestrator.run(body.brief, user_id=user_id, agent_limit=None, plan="pro",
                              upload_dir=upload_dir)
        )
        return {"status": "started"}

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
    asyncio.create_task(
        _orchestrator.run(body.brief, user_id=user_id, agent_limit=agent_limit, plan=plan,
                          api_key="", upload_dir=upload_dir)
    )
    return {"status": "started"}


@router.post("/cancel")
async def cancel_project(_user: dict = Depends(require_auth)):
    if _orchestrator is None:
        return {"error": "orchestrator not ready"}
    _orchestrator.cancel()
    return {"status": "cancelling"}


@router.get("/config")
async def get_config(_user: dict = Depends(require_auth)):
    config_path = Path(os.getcwd()) / "agent-team.config.json"
    if config_path.exists():
        try:
            return json.loads(config_path.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {
        "sprint": "Sprint #1",
        "provider": DEFAULT_PROVIDER,
        "agents": DEFAULT_AGENTS,
    }


@router.put("/config")
async def put_config(body: dict[str, Any], user: dict = Depends(require_auth)):
    """Update agent config — Pro plan only."""
    from ..db.session import get_session
    from ..db.models import UserCredits
    from fastapi import HTTPException
    user_id = user.get("sub", "anonymous")

    # Dev bypass — skip plan gate in local dev mode
    if _AUTH_DISABLED or user_id == "dev-user":
        save_config(body)
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
    save_config(body)
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
        }
