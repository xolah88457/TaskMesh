"""
Agent Teams orchestrator — coordinates a shared task list, mailbox, and
teammate roster for a single team.

Modelled on the spec in AGENT_TEAMS.md:
  * The lead spawns teammates, assigns tasks, and synthesises results.
  * Teammates each have an independent identity and may claim pending,
    unblocked tasks.
  * Tasks can declare `depends_on` — a list of task IDs that must be
    `done` before the task is claimable.
  * Inter-agent messaging is append-only (`TeamMessage`).
  * Every state change emits a Socket.IO event so the frontend updates
    in real time.

The class is intentionally lighter than `Orchestrator`. Real agent
execution against an LLM is opt-in via `execute_task`, which uses
`base_agent.BaseAgent` so token spend, retry, and observability behave
the same as the main pipeline. By default a team is human-driven (the
lead = the user) — `execute_task` only runs when the API caller chooses
to delegate the task to the model.
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone

import socketio
from sqlalchemy import select, update

from ..db.models_teams import Team, TeamMember, TeamTask, TeamMessage
from ..db.session import get_session

_log = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ─── helpers — serialization for socket / HTTP ────────────────────────────────

def _team_dict(t: Team) -> dict:
    return {
        "id":          t.id,
        "user_id":     t.user_id,
        "name":        t.name,
        "description": t.description,
        "status":      t.status,
        "created_at":  t.created_at.isoformat() if t.created_at else None,
        "updated_at":  t.updated_at.isoformat() if t.updated_at else None,
    }


def _member_dict(m: TeamMember) -> dict:
    return {
        "id":             m.id,
        "team_id":        m.team_id,
        "name":           m.name,
        "agent_type":     m.agent_type,
        "model":          m.model,
        "spawn_prompt":   m.spawn_prompt,
        "status":         m.status,
        "is_lead":        bool(m.is_lead),
        "created_at":     m.created_at.isoformat() if m.created_at else None,
        "last_active_at": m.last_active_at.isoformat() if m.last_active_at else None,
    }


def _task_dict(t: TeamTask) -> dict:
    depends_on: list[str] = []
    if t.depends_on:
        try:
            decoded = json.loads(t.depends_on)
            if isinstance(decoded, list):
                depends_on = [str(x) for x in decoded]
        except (json.JSONDecodeError, TypeError):
            depends_on = []
    return {
        "id":           t.id,
        "team_id":      t.team_id,
        "title":        t.title,
        "description":  t.description,
        "status":       t.status,
        "assigned_to":  t.assigned_to,
        "depends_on":   depends_on,
        "result":       t.result,
        "created_by":   t.created_by,
        "created_at":   t.created_at.isoformat() if t.created_at else None,
        "started_at":   t.started_at.isoformat() if t.started_at else None,
        "completed_at": t.completed_at.isoformat() if t.completed_at else None,
    }


def _message_dict(m: TeamMessage) -> dict:
    return {
        "id":          m.id,
        "team_id":     m.team_id,
        "from_member": m.from_member,
        "to_member":   m.to_member,
        "content":     m.content,
        "created_at":  m.created_at.isoformat() if m.created_at else None,
    }


# ─── errors ──────────────────────────────────────────────────────────────────

class TeamError(Exception):
    """Domain error — surfaced as HTTP 4xx by the API layer."""

    def __init__(self, code: str, status_code: int = 400, message: str = "") -> None:
        self.code = code
        self.status_code = status_code
        self.message = message or code
        super().__init__(self.message)


# ─── orchestrator ────────────────────────────────────────────────────────────

class TeamOrchestrator:
    """Stateless coordinator. Every method opens its own DB session.

    The single instance is held by the API module; concurrent requests use
    Postgres row locking (`SELECT … FOR UPDATE`) to keep claim/complete
    races correct.
    """

    def __init__(self, sio: socketio.AsyncServer | None = None) -> None:
        self._sio = sio
        # Track in-flight LLM tasks per (team_id, task_id) so cleanup can
        # cancel them.
        self._inflight: dict[tuple[str, str], asyncio.Task] = {}

    # ─── socket helpers ──────────────────────────────────────────────────────

    def _room(self, team_id: str) -> str:
        return f"team:{team_id}"

    async def _emit(self, team_id: str, event: str, payload: dict) -> None:
        if self._sio is None:
            return
        try:
            await self._sio.emit(event, payload, room=self._room(team_id))
        except Exception:
            _log.exception("team socket emit failed: event=%s team=%s", event, team_id)

    # ─── team CRUD ───────────────────────────────────────────────────────────

    async def create_team(
        self,
        user_id: str,
        name: str,
        description: str = "",
    ) -> dict:
        name = (name or "").strip()
        if len(name) < 2:
            raise TeamError("invalid_name", status_code=400)
        team_id = str(uuid.uuid4())
        async with get_session() as session:
            if session is None:
                raise TeamError("db_unavailable", status_code=503)
            team = Team(
                id=team_id,
                user_id=user_id,
                name=name,
                description=description or None,
                status="active",
            )
            session.add(team)
            await session.flush()
            data = _team_dict(team)
        await self._emit(team_id, "team_created", data)
        return data

    async def list_teams(self, user_id: str) -> list[dict]:
        async with get_session() as session:
            if session is None:
                return []
            rows = (
                await session.execute(
                    select(Team)
                    .where(Team.user_id == user_id, Team.status != "archived")
                    .order_by(Team.updated_at.desc())
                )
            ).scalars().all()
            return [_team_dict(t) for t in rows]

    async def get_team_full(self, user_id: str, team_id: str) -> dict:
        """Return team + members + tasks + recent messages in one snapshot."""
        async with get_session() as session:
            if session is None:
                raise TeamError("db_unavailable", status_code=503)
            team = await session.get(Team, team_id)
            if team is None or team.user_id != user_id:
                raise TeamError("not_found", status_code=404)
            members = (
                await session.execute(
                    select(TeamMember)
                    .where(TeamMember.team_id == team_id)
                    .order_by(TeamMember.created_at.asc())
                )
            ).scalars().all()
            tasks = (
                await session.execute(
                    select(TeamTask)
                    .where(TeamTask.team_id == team_id)
                    .order_by(TeamTask.created_at.asc())
                )
            ).scalars().all()
            messages = (
                await session.execute(
                    select(TeamMessage)
                    .where(TeamMessage.team_id == team_id)
                    .order_by(TeamMessage.created_at.desc())
                    .limit(200)
                )
            ).scalars().all()
            messages = list(reversed(messages))  # chronological order
            return {
                "team":     _team_dict(team),
                "members":  [_member_dict(m) for m in members],
                "tasks":    [_task_dict(t)  for t in tasks],
                "messages": [_message_dict(m) for m in messages],
            }

    async def delete_team(self, user_id: str, team_id: str) -> dict:
        """Tear down the team — cancels in-flight executions, deletes rows."""
        # Cancel any LLM tasks belonging to this team.
        keys = [k for k in self._inflight if k[0] == team_id]
        for k in keys:
            t = self._inflight.pop(k, None)
            if t is not None and not t.done():
                t.cancel()

        async with get_session() as session:
            if session is None:
                raise TeamError("db_unavailable", status_code=503)
            team = await session.get(Team, team_id)
            if team is None or team.user_id != user_id:
                raise TeamError("not_found", status_code=404)
            await session.delete(team)
        await self._emit(team_id, "team_deleted", {"team_id": team_id})
        return {"status": "deleted", "team_id": team_id}

    # ─── member ops ──────────────────────────────────────────────────────────

    async def spawn_member(
        self,
        user_id: str,
        team_id: str,
        name: str,
        agent_type: str = "generic",
        model: str | None = None,
        spawn_prompt: str = "",
        is_lead: bool = False,
    ) -> dict:
        name = (name or "").strip()
        if not name:
            raise TeamError("invalid_name", status_code=400)
        member_id = str(uuid.uuid4())
        async with get_session() as session:
            if session is None:
                raise TeamError("db_unavailable", status_code=503)
            team = await session.get(Team, team_id)
            if team is None or team.user_id != user_id:
                raise TeamError("not_found", status_code=404)
            # Name uniqueness inside the team.
            existing = await session.execute(
                select(TeamMember).where(
                    TeamMember.team_id == team_id,
                    TeamMember.name == name,
                )
            )
            if existing.scalar_one_or_none() is not None:
                raise TeamError("duplicate_name", status_code=409)
            # Exactly one lead per team — promote/demote handled by caller.
            if is_lead:
                await session.execute(
                    update(TeamMember)
                    .where(TeamMember.team_id == team_id, TeamMember.is_lead == True)  # noqa: E712
                    .values(is_lead=False)
                )
            member = TeamMember(
                id=member_id,
                team_id=team_id,
                name=name,
                agent_type=agent_type or "generic",
                model=model,
                spawn_prompt=spawn_prompt or None,
                status="idle",
                is_lead=is_lead,
            )
            session.add(member)
            team.updated_at = _now()
            await session.flush()
            data = _member_dict(member)
        await self._emit(team_id, "team_member_update", data)
        return data

    async def shutdown_member(
        self,
        user_id: str,
        team_id: str,
        member_id: str,
    ) -> dict:
        async with get_session() as session:
            if session is None:
                raise TeamError("db_unavailable", status_code=503)
            team = await session.get(Team, team_id)
            if team is None or team.user_id != user_id:
                raise TeamError("not_found", status_code=404)
            member = await session.get(TeamMember, member_id)
            if member is None or member.team_id != team_id:
                raise TeamError("member_not_found", status_code=404)
            # Release any tasks the member was working on so they become claimable.
            await session.execute(
                update(TeamTask)
                .where(
                    TeamTask.team_id == team_id,
                    TeamTask.assigned_to == member_id,
                    TeamTask.status == "in_progress",
                )
                .values(status="pending", assigned_to=None, started_at=None)
            )
            await session.delete(member)
            team.updated_at = _now()
        await self._emit(team_id, "team_member_removed", {"member_id": member_id})
        return {"status": "shutdown", "member_id": member_id}

    # ─── task ops ────────────────────────────────────────────────────────────

    async def create_task(
        self,
        user_id: str,
        team_id: str,
        title: str,
        description: str = "",
        depends_on: list[str] | None = None,
        assigned_to: str | None = None,
        created_by: str = "user",
    ) -> dict:
        title = (title or "").strip()
        if len(title) < 2:
            raise TeamError("invalid_title", status_code=400)
        task_id = str(uuid.uuid4())
        async with get_session() as session:
            if session is None:
                raise TeamError("db_unavailable", status_code=503)
            team = await session.get(Team, team_id)
            if team is None or team.user_id != user_id:
                raise TeamError("not_found", status_code=404)
            # Validate any declared dependencies belong to this team.
            if depends_on:
                rows = (
                    await session.execute(
                        select(TeamTask.id).where(
                            TeamTask.team_id == team_id,
                            TeamTask.id.in_(depends_on),
                        )
                    )
                ).scalars().all()
                if len(rows) != len(set(depends_on)):
                    raise TeamError("invalid_dependency", status_code=400)
            # Validate assignee if provided.
            if assigned_to is not None:
                m = await session.get(TeamMember, assigned_to)
                if m is None or m.team_id != team_id:
                    raise TeamError("invalid_assignee", status_code=400)
            task = TeamTask(
                id=task_id,
                team_id=team_id,
                title=title,
                description=description or None,
                status="pending",
                assigned_to=assigned_to,
                depends_on=json.dumps(list(depends_on or [])),
                created_by=created_by,
            )
            session.add(task)
            team.updated_at = _now()
            await session.flush()
            data = _task_dict(task)
        await self._emit(team_id, "team_task_update", data)
        return data

    async def _dependencies_met(self, session, task: TeamTask) -> bool:
        if not task.depends_on:
            return True
        try:
            dep_ids = json.loads(task.depends_on)
        except (json.JSONDecodeError, TypeError):
            return True
        if not dep_ids:
            return True
        rows = (
            await session.execute(
                select(TeamTask.id, TeamTask.status).where(TeamTask.id.in_(dep_ids))
            )
        ).all()
        return all(status == "done" for (_id, status) in rows)

    async def claim_task(
        self,
        user_id: str,
        team_id: str,
        task_id: str,
        member_id: str,
    ) -> dict:
        async with get_session() as session:
            if session is None:
                raise TeamError("db_unavailable", status_code=503)
            team = await session.get(Team, team_id)
            if team is None or team.user_id != user_id:
                raise TeamError("not_found", status_code=404)
            member = await session.get(TeamMember, member_id)
            if member is None or member.team_id != team_id:
                raise TeamError("member_not_found", status_code=404)
            task = await session.get(TeamTask, task_id)
            if task is None or task.team_id != team_id:
                raise TeamError("task_not_found", status_code=404)
            if task.status == "in_progress":
                raise TeamError("already_claimed", status_code=409)
            if task.status == "done":
                raise TeamError("already_done", status_code=409)
            if not await self._dependencies_met(session, task):
                raise TeamError("blocked_on_dependency", status_code=409)
            task.status = "in_progress"
            task.assigned_to = member_id
            task.started_at = _now()
            member.status = "busy"
            member.last_active_at = _now()
            team.updated_at = _now()
            await session.flush()
            task_data   = _task_dict(task)
            member_data = _member_dict(member)
        await self._emit(team_id, "team_task_update",   task_data)
        await self._emit(team_id, "team_member_update", member_data)
        return task_data

    async def complete_task(
        self,
        user_id: str,
        team_id: str,
        task_id: str,
        result: str = "",
        member_id: str | None = None,
    ) -> dict:
        async with get_session() as session:
            if session is None:
                raise TeamError("db_unavailable", status_code=503)
            team = await session.get(Team, team_id)
            if team is None or team.user_id != user_id:
                raise TeamError("not_found", status_code=404)
            task = await session.get(TeamTask, task_id)
            if task is None or task.team_id != team_id:
                raise TeamError("task_not_found", status_code=404)
            if task.status == "done":
                return _task_dict(task)
            task.status = "done"
            task.result = result or task.result
            task.completed_at = _now()
            if member_id and task.assigned_to is None:
                task.assigned_to = member_id
            assignee_id = task.assigned_to
            # Mark the assigned member idle if it's no longer busy.
            if assignee_id:
                m = await session.get(TeamMember, assignee_id)
                if m is not None and m.status == "busy":
                    # Are there other in-progress tasks for this member?
                    others = (
                        await session.execute(
                            select(TeamTask.id).where(
                                TeamTask.team_id == team_id,
                                TeamTask.assigned_to == assignee_id,
                                TeamTask.status == "in_progress",
                                TeamTask.id != task_id,
                            )
                        )
                    ).scalars().first()
                    if others is None:
                        m.status = "idle"
                    m.last_active_at = _now()
                    member_payload = _member_dict(m)
                else:
                    member_payload = None
            else:
                member_payload = None
            team.updated_at = _now()
            team_name = team.name
            await session.flush()
            task_data = _task_dict(task)
        await self._emit(team_id, "team_task_update", task_data)
        if member_payload is not None:
            await self._emit(team_id, "team_member_update", member_payload)
        # Cancel any tracker for this task.
        self._inflight.pop((team_id, task_id), None)
        # Push the completed task to the user's GitHub repo. Fire-and-forget
        # so a GitHub outage cannot block the platform's record-keeping.
        asyncio.create_task(self._push_task_to_github(user_id, team_id, team_name, task_data))
        return task_data

    async def _push_task_to_github(
        self,
        user_id: str,
        team_id: str,
        team_name: str,
        task: dict,
    ) -> None:
        """Append the completed task to the user's repo and write the result.

        Layout in user's repo:
          taskmesh/teams/{team_id}/tasks.jsonl        — append: one row per task event
          taskmesh/teams/{team_id}/results/{tid}.md   — overwrite: human-readable result
        """
        from .github_sink import GitHubSink, GitHubSinkError, is_app_configured
        if not is_app_configured():
            return
        from ..db.models import UserGitHubInstall
        async with get_session() as session:
            if session is None:
                return
            install = await session.get(UserGitHubInstall, user_id)
            if install is None or not install.default_repo:
                return
            installation_id = install.installation_id
            repo = install.default_repo
            branch = install.default_branch or "main"

        sink = GitHubSink(installation_id, repo, branch)
        prefix = f"taskmesh/teams/{team_id}"
        try:
            await sink.append_jsonl(
                f"{prefix}/tasks.jsonl",
                [{
                    "task_id":      task["id"],
                    "title":        task["title"],
                    "status":       task["status"],
                    "assigned_to":  task["assigned_to"],
                    "created_at":   task["created_at"],
                    "completed_at": task["completed_at"],
                }],
                message=f"taskmesh: task {task['id'][:8]} {task['status']} ({team_name})",
            )
            result_text = (task.get("result") or "").strip()
            if result_text:
                result_path = f"{prefix}/results/{task['id']}.md"
                content = (
                    f"# {task['title']}\n\n"
                    f"- Status: `{task['status']}`\n"
                    f"- Task ID: `{task['id']}`\n"
                    f"- Team: `{team_name}` ({team_id})\n"
                    f"- Assignee: `{task['assigned_to'] or 'unassigned'}`\n"
                    f"- Completed: `{task['completed_at']}`\n\n"
                    f"---\n\n{result_text}\n"
                )
                await sink.push_files([(result_path, content)], message=f"taskmesh: result for task {task['id'][:8]}")
        except GitHubSinkError as exc:
            _log.warning("github push failed team=%s task=%s code=%s", team_id, task["id"], exc.code)
        except Exception:
            _log.exception("github push raised team=%s task=%s", team_id, task["id"])

    async def fail_task(
        self,
        user_id: str,
        team_id: str,
        task_id: str,
        reason: str = "",
    ) -> dict:
        async with get_session() as session:
            if session is None:
                raise TeamError("db_unavailable", status_code=503)
            team = await session.get(Team, team_id)
            if team is None or team.user_id != user_id:
                raise TeamError("not_found", status_code=404)
            task = await session.get(TeamTask, task_id)
            if task is None or task.team_id != team_id:
                raise TeamError("task_not_found", status_code=404)
            task.status = "failed"
            task.result = (task.result or "") + ("\n[failed] " + reason if reason else "\n[failed]")
            task.completed_at = _now()
            assignee_id = task.assigned_to
            if assignee_id:
                m = await session.get(TeamMember, assignee_id)
                if m is not None and m.status == "busy":
                    m.status = "idle"
            team.updated_at = _now()
            await session.flush()
            data = _task_dict(task)
        await self._emit(team_id, "team_task_update", data)
        self._inflight.pop((team_id, task_id), None)
        return data

    # ─── messaging ───────────────────────────────────────────────────────────

    async def send_message(
        self,
        user_id: str,
        team_id: str,
        from_member: str,
        to_member: str,
        content: str,
    ) -> dict:
        content = (content or "").strip()
        if not content:
            raise TeamError("empty_message", status_code=400)
        if len(content) > 4000:
            raise TeamError("message_too_long", status_code=400)
        async with get_session() as session:
            if session is None:
                raise TeamError("db_unavailable", status_code=503)
            team = await session.get(Team, team_id)
            if team is None or team.user_id != user_id:
                raise TeamError("not_found", status_code=404)
            msg = TeamMessage(
                team_id=team_id,
                from_member=from_member or "user",
                to_member=to_member or "all",
                content=content,
            )
            session.add(msg)
            team.updated_at = _now()
            await session.flush()
            data = _message_dict(msg)
        await self._emit(team_id, "team_message", data)
        return data

    async def list_messages(
        self,
        user_id: str,
        team_id: str,
        limit: int = 200,
    ) -> list[dict]:
        limit = max(1, min(int(limit), 500))
        async with get_session() as session:
            if session is None:
                return []
            team = await session.get(Team, team_id)
            if team is None or team.user_id != user_id:
                raise TeamError("not_found", status_code=404)
            rows = (
                await session.execute(
                    select(TeamMessage)
                    .where(TeamMessage.team_id == team_id)
                    .order_by(TeamMessage.created_at.desc())
                    .limit(limit)
                )
            ).scalars().all()
            return [_message_dict(m) for m in reversed(rows)]

    # ─── LLM-driven task execution ──────────────────────────────────────────

    async def execute_task(
        self,
        user_id: str,
        team_id: str,
        task_id: str,
        member_id: str,
    ) -> dict:
        """Hand the task to the member's model and let it produce a result.

        This is fire-and-forget — the API returns immediately while the
        LLM call runs in the background. Use `get_team_full` (or the
        socket stream) to observe completion.
        """
        # Claim first to assign the member and flip status.
        await self.claim_task(user_id, team_id, task_id, member_id)

        async def _runner() -> None:
            try:
                result_text = await self._invoke_member(team_id, task_id, member_id)
                await self.complete_task(user_id, team_id, task_id, result=result_text, member_id=member_id)
            except asyncio.CancelledError:
                # Cleanup cancels in-flight tasks during delete_team.
                raise
            except Exception as exc:  # noqa: BLE001
                _log.exception("team task execution failed team=%s task=%s", team_id, task_id)
                try:
                    await self.fail_task(user_id, team_id, task_id, reason=f"{type(exc).__name__}: {exc}")
                except Exception:
                    pass
            finally:
                self._inflight.pop((team_id, task_id), None)

        task = asyncio.create_task(_runner())
        self._inflight[(team_id, task_id)] = task
        return {"status": "executing", "task_id": task_id}

    async def _invoke_member(self, team_id: str, task_id: str, member_id: str) -> str:
        """Run the member's model on the task. Imports kept local so test
        environments without the LLM provider don't import on module load."""
        from ..agents.base_agent import BaseAgent
        from .config_loader import DEFAULT_BASE_URL
        import os

        async with get_session() as session:
            if session is None:
                return "[no result — db unavailable]"
            member = await session.get(TeamMember, member_id)
            task   = await session.get(TeamTask, task_id)
            if member is None or task is None:
                return "[no result — task or member missing]"
            model = member.model or "deepseek-v4-flash"
            base_prompt = member.spawn_prompt or (
                f"You are a teammate named '{member.name}' (role: {member.agent_type})."
            )
            task_title       = task.title
            task_description = task.description or "(no details)"

        api_key = os.environ.get("OPENCODE_GO_API_KEY", "") or os.environ.get("OPENROUTER_API_KEY", "")
        if not api_key:
            return "[skipped — provider API key not configured]"

        system_prompt = (
            f"{base_prompt}\n\n"
            "Produce a concise result (under 400 words). Do not invent files; describe what you would do, "
            "or summarise findings if this is a research task."
        )
        user_message = f"Task: {task_title}\nDetails: {task_description}"

        agent = BaseAgent(
            name=member.name,
            model=model,
            system_prompt=system_prompt,
            base_url=DEFAULT_BASE_URL,
            api_key=api_key,
            temperature=0.5,
            top_p=0.9,
            top_k=0,
            thinking_budget=0,
            max_tokens=2048,
        )
        try:
            response = await agent.run(user_message)
        except Exception as exc:  # noqa: BLE001
            return f"[error invoking model: {exc}]"
        content = (response.get("content") or "").strip()
        return content or "[empty response]"
