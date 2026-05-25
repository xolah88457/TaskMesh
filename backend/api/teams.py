"""
Agent Teams API.

Maps the TeamOrchestrator surface onto HTTP. Every route requires auth and
operates only on the calling user's teams (`Team.user_id == user.sub`).

Routes
------
POST   /api/teams                                   create team
GET    /api/teams                                   list teams owned by caller
GET    /api/teams/{team_id}                         full team snapshot
DELETE /api/teams/{team_id}                         cleanup + delete

POST   /api/teams/{team_id}/members                 spawn member
DELETE /api/teams/{team_id}/members/{member_id}    shut down member

POST   /api/teams/{team_id}/tasks                   create task
POST   /api/teams/{team_id}/tasks/{task_id}/claim   claim task
POST   /api/teams/{team_id}/tasks/{task_id}/complete  mark done
POST   /api/teams/{team_id}/tasks/{task_id}/execute   delegate to model
POST   /api/teams/{team_id}/tasks/{task_id}/fail    mark failed

POST   /api/teams/{team_id}/messages                send message
GET    /api/teams/{team_id}/messages                list recent messages
"""
from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ..auth.auth import require_auth
from ..core.team_orchestrator import TeamOrchestrator, TeamError

router = APIRouter(prefix="/teams")

# Single process-level instance. The class is stateless apart from
# tracking in-flight asyncio tasks for cancellation.
_orchestrator = TeamOrchestrator()

# Mirror billing's dev bypass — set in .env for local development.
_AUTH_DISABLED = os.environ.get("AUTH_DISABLED", "").lower() in ("1", "true", "yes")
# When set, the GitHub-installation gate is bypassed. Used for dev where the
# operator doesn't want to install the App locally. Plan gate still applies.
_TEAMS_REQUIRE_GITHUB = os.environ.get("TEAMS_REQUIRE_GITHUB", "true").lower() in ("1", "true", "yes")


def get_team_orchestrator() -> TeamOrchestrator:
    return _orchestrator


def _bind_sio(sio_instance) -> None:
    """Called from main.py once the Socket.IO server is constructed."""
    _orchestrator._sio = sio_instance


def _handle(exc: TeamError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.code)


async def require_teams_access(user: dict = Depends(require_auth)) -> dict:
    """Authorize the caller for Agent Teams.

    Two gates:
      1. Plan must be `pro` (subscription) or the user has bought a credit
         pack (which also stamps plan='pro' — see billing._handle_transaction_completed).
      2. The user must have installed the TaskMesh GitHub App and picked a
         default repo — Agent Teams writes its output there.

    Dev bypass: AUTH_DISABLED or user_id=='dev-user' skips both gates.
    The GitHub gate can also be skipped per-env via TEAMS_REQUIRE_GITHUB=false.
    """
    user_id = user.get("sub", "")
    if _AUTH_DISABLED or user_id == "dev-user":
        return user

    from ..db.session import get_session
    from ..db.models import UserCredits, UserGitHubInstall

    async with get_session() as session:
        if session is None:
            raise HTTPException(status_code=503, detail="db_unavailable")
        credits = await session.get(UserCredits, user_id)
        plan = credits.plan if credits else "none"
        if plan != "pro":
            # Both Starter and free users hit this — pack purchasers already
            # have plan='pro'. Pricing/UX surfaces this as "Pro or Top-Up only".
            raise HTTPException(status_code=402, detail="agent_teams_pro_only")

        if _TEAMS_REQUIRE_GITHUB:
            install = await session.get(UserGitHubInstall, user_id)
            if install is None or not install.default_repo:
                raise HTTPException(status_code=412, detail="github_not_connected")
    return user


# ─── request bodies ──────────────────────────────────────────────────────────

class CreateTeamBody(BaseModel):
    name:        str
    description: str = ""


class SpawnMemberBody(BaseModel):
    name:         str
    agent_type:   str = "generic"
    model:        str | None = None
    spawn_prompt: str = ""
    is_lead:      bool = False


class CreateTaskBody(BaseModel):
    title:       str
    description: str = ""
    depends_on:  list[str] = Field(default_factory=list)
    assigned_to: str | None = None


class ClaimTaskBody(BaseModel):
    member_id: str


class CompleteTaskBody(BaseModel):
    result:    str = ""
    member_id: str | None = None


class FailTaskBody(BaseModel):
    reason: str = ""


class ExecuteTaskBody(BaseModel):
    member_id: str


class SendMessageBody(BaseModel):
    from_member: str = "user"
    to_member:   str = "all"
    content:     str


# ─── team routes ─────────────────────────────────────────────────────────────

@router.post("")
async def create_team(body: CreateTeamBody, user: dict = Depends(require_teams_access)):
    try:
        return await _orchestrator.create_team(
            user_id=user["sub"],
            name=body.name,
            description=body.description,
        )
    except TeamError as exc:
        raise _handle(exc)


@router.get("")
async def list_teams(user: dict = Depends(require_teams_access)):
    return {"teams": await _orchestrator.list_teams(user["sub"])}


@router.get("/{team_id}")
async def get_team(team_id: str, user: dict = Depends(require_teams_access)):
    try:
        return await _orchestrator.get_team_full(user["sub"], team_id)
    except TeamError as exc:
        raise _handle(exc)


@router.delete("/{team_id}")
async def delete_team(team_id: str, user: dict = Depends(require_teams_access)):
    try:
        return await _orchestrator.delete_team(user["sub"], team_id)
    except TeamError as exc:
        raise _handle(exc)


# ─── member routes ───────────────────────────────────────────────────────────

@router.post("/{team_id}/members")
async def spawn_member(team_id: str, body: SpawnMemberBody, user: dict = Depends(require_teams_access)):
    try:
        return await _orchestrator.spawn_member(
            user_id=user["sub"],
            team_id=team_id,
            name=body.name,
            agent_type=body.agent_type,
            model=body.model,
            spawn_prompt=body.spawn_prompt,
            is_lead=body.is_lead,
        )
    except TeamError as exc:
        raise _handle(exc)


@router.delete("/{team_id}/members/{member_id}")
async def shutdown_member(team_id: str, member_id: str, user: dict = Depends(require_teams_access)):
    try:
        return await _orchestrator.shutdown_member(
            user_id=user["sub"],
            team_id=team_id,
            member_id=member_id,
        )
    except TeamError as exc:
        raise _handle(exc)


# ─── task routes ─────────────────────────────────────────────────────────────

@router.post("/{team_id}/tasks")
async def create_task(team_id: str, body: CreateTaskBody, user: dict = Depends(require_teams_access)):
    try:
        return await _orchestrator.create_task(
            user_id=user["sub"],
            team_id=team_id,
            title=body.title,
            description=body.description,
            depends_on=body.depends_on,
            assigned_to=body.assigned_to,
            created_by="user",
        )
    except TeamError as exc:
        raise _handle(exc)


@router.post("/{team_id}/tasks/{task_id}/claim")
async def claim_task(team_id: str, task_id: str, body: ClaimTaskBody, user: dict = Depends(require_teams_access)):
    try:
        return await _orchestrator.claim_task(
            user_id=user["sub"],
            team_id=team_id,
            task_id=task_id,
            member_id=body.member_id,
        )
    except TeamError as exc:
        raise _handle(exc)


@router.post("/{team_id}/tasks/{task_id}/complete")
async def complete_task(team_id: str, task_id: str, body: CompleteTaskBody, user: dict = Depends(require_teams_access)):
    try:
        return await _orchestrator.complete_task(
            user_id=user["sub"],
            team_id=team_id,
            task_id=task_id,
            result=body.result,
            member_id=body.member_id,
        )
    except TeamError as exc:
        raise _handle(exc)


@router.post("/{team_id}/tasks/{task_id}/fail")
async def fail_task(team_id: str, task_id: str, body: FailTaskBody, user: dict = Depends(require_teams_access)):
    try:
        return await _orchestrator.fail_task(
            user_id=user["sub"],
            team_id=team_id,
            task_id=task_id,
            reason=body.reason,
        )
    except TeamError as exc:
        raise _handle(exc)


@router.post("/{team_id}/tasks/{task_id}/execute")
async def execute_task(team_id: str, task_id: str, body: ExecuteTaskBody, user: dict = Depends(require_teams_access)):
    try:
        return await _orchestrator.execute_task(
            user_id=user["sub"],
            team_id=team_id,
            task_id=task_id,
            member_id=body.member_id,
        )
    except TeamError as exc:
        raise _handle(exc)


# ─── messaging ───────────────────────────────────────────────────────────────

@router.post("/{team_id}/messages")
async def send_message(team_id: str, body: SendMessageBody, user: dict = Depends(require_teams_access)):
    try:
        return await _orchestrator.send_message(
            user_id=user["sub"],
            team_id=team_id,
            from_member=body.from_member,
            to_member=body.to_member,
            content=body.content,
        )
    except TeamError as exc:
        raise _handle(exc)


@router.get("/{team_id}/messages")
async def list_messages(
    team_id: str,
    limit: int = Query(200, ge=1, le=500),
    user: dict = Depends(require_teams_access),
):
    try:
        msgs = await _orchestrator.list_messages(user["sub"], team_id, limit=limit)
        return {"messages": msgs}
    except TeamError as exc:
        raise _handle(exc)
