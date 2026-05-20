import asyncio
import json
import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..auth.auth import require_auth
from ..core.config_loader import DEFAULT_AGENTS, DEFAULT_PROVIDER, save_config

router = APIRouter()
_orchestrator = None

_AUTH_DISABLED = os.environ.get("AUTH_DISABLED", "").lower() in ("1", "true", "yes")


def set_orchestrator(orch):
    global _orchestrator
    _orchestrator = orch


class ProjectBrief(BaseModel):
    brief: str


@router.post("/start-project")
async def start_project(body: ProjectBrief, user: dict = Depends(require_auth)):
    if _orchestrator is None:
        return {"error": "orchestrator not ready"}
    if _orchestrator.is_running():
        return {"error": "already running"}

    user_id = user.get("sub", "anonymous")

    # Dev bypass — skip billing gate entirely in local dev mode
    if _AUTH_DISABLED or user_id == "dev-user":
        asyncio.create_task(
            _orchestrator.run(body.brief, user_id=user_id, agent_limit=None, plan="pro")
        )
        return {"status": "started"}

    # Billing gate + user API key fetch in one session
    from ..db.session import get_session
    from ..db.models import UserCredits, User
    plan    = "none"
    balance = 0
    api_key = ""
    async with get_session() as session:
        if session is not None:
            credits  = await session.get(UserCredits, user_id)
            plan     = credits.plan          if credits else "none"
            balance  = credits.balance_cents if credits else 0
            user_row = await session.get(User, user_id)
            if user_row and user_row.opencode_api_key:
                api_key = user_row.opencode_api_key

    if plan == "none":
        return {"error": "no_subscription"}
    if balance <= 0:
        return {"error": "no_credits"}

    agent_limit = 3 if plan == "starter" else None
    asyncio.create_task(
        _orchestrator.run(body.brief, user_id=user_id, agent_limit=agent_limit, plan=plan, api_key=api_key)
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
    user_id = user.get("sub", "anonymous")
    async with get_session() as session:
        if session is None:
            return []
        result = await session.execute(
            select(Run)
            .where(Run.user_id == user_id)
            .order_by(Run.started_at.desc())
            .limit(50)
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
