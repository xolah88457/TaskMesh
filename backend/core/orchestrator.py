"""
Multi-agent orchestrator — dynamic shared-task-list coordination.

Architecture:
  Phase 1 — Manager creates a task plan from the brief (+ uploaded files).
  Phase 2 — All agents run concurrently, claiming tasks from a SharedTaskList.
            Each agent loops: claim → execute → write files → complete → repeat.
  Phase 3 — The orchestrator monitors until all tasks are done or cancelled.

Coordination primitives:
  - SharedTaskList   : in-memory task queue (agents claim tasks autonomously)
  - FileLockRegistry : exclusive file ownership per agent during a run
  - AgentMailbox     : typed async message store for cross-agent comms
  - CoordinatorLog   : structured log of every coordinator decision
  - Auto-commit      : git commit after each agent task's files land
"""

from __future__ import annotations

import asyncio
import json
import re
import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

import socketio

from ..agents.base_agent import BaseAgent
from ..agents.manager_agent import ManagerAgent
from ..core.config_loader import ProjectConfig, get_project_dir, load_config
from ..core.task_list import SharedTaskList
from ..db.session import get_session
from ..db.models import Run, RunFile, UserUsage

# ─── file-block regex for agent output parsing ───────────────────────────────
_FILE_RE = re.compile(
    r'^---\s*FILE:\s*(.+?)\s*---\s*$(.+?)^---\s*END\s*FILE\s*---\s*$',
    re.MULTILINE | re.DOTALL
)


# ─── coordination helpers ──────────────────────────────────────────────────────

class FileLockRegistry:
    """
    Tracks exclusive file ownership per agent during a run.

    Rules:
      - Only one agent may hold a lock on a given path at a time.
      - The same agent can re-acquire its own lock (idempotent).
      - Conflicts are logged and the requesting agent takes over (last-write wins).
      - All locks are cleared at the start of each run.
    """

    def __init__(self) -> None:
        self._locks: dict[str, str] = {}  # path -> agent_id

    def acquire(self, path: str, agent_id: str) -> tuple[bool, str | None]:
        """Try to acquire lock. Returns (acquired, current_holder_or_None)."""
        holder = self._locks.get(path)
        if holder is not None and holder != agent_id:
            return False, holder
        self._locks[path] = agent_id
        return True, None

    def force_acquire(self, path: str, agent_id: str) -> None:
        self._locks[path] = agent_id

    def release(self, path: str, agent_id: str) -> None:
        if self._locks.get(path) == agent_id:
            del self._locks[path]

    def release_all(self, agent_id: str) -> None:
        paths = [p for p, a in list(self._locks.items()) if a == agent_id]
        for p in paths:
            del self._locks[p]

    def holder(self, path: str) -> str | None:
        return self._locks.get(path)

    def clear(self) -> None:
        self._locks.clear()

    def snapshot(self) -> dict[str, str]:
        return dict(self._locks)


class AgentMailbox:
    """
    Per-run async message store for cross-agent communication.

    Message types:
      message   - general notification
      blocker   - agent is blocked and needs coordinator help
      feedback  - reviewer feedback targeted at a specific agent
      approval  - reviewer approved the full run
    """

    def __init__(self) -> None:
        self._messages: list[dict] = []

    def send(
        self,
        from_agent: str,
        to_agent: str,
        content: str,
        msg_type: str = "message",
    ) -> dict:
        msg: dict = {
            "id": str(uuid.uuid4())[:8],
            "from": from_agent,
            "to": to_agent,
            "content": content,
            "type": msg_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "read": False,
        }
        self._messages.append(msg)
        return msg

    def inbox(self, agent_id: str) -> list[dict]:
        return [m for m in self._messages if m["to"] == agent_id]

    def unread(self, agent_id: str) -> list[dict]:
        msgs = [m for m in self._messages if m["to"] == agent_id and not m["read"]]
        for m in msgs:
            m["read"] = True
        return msgs

    def all_messages(self) -> list[dict]:
        return list(self._messages)

    def clear(self) -> None:
        self._messages.clear()


class CoordinatorLog:
    """
    Structured log of every coordinator decision during a run.

    Decision types: task_created, task_claimed, task_completed,
                    agent_online, agent_finished, file_locked, file_conflict,
                    auto_commit, run_complete.
    """

    def __init__(self) -> None:
        self._entries: list[dict] = []

    def record(
        self,
        decision_type: str,
        content: str,
        metadata: dict | None = None,
    ) -> dict:
        entry: dict = {
            "type": decision_type,
            "content": content,
            "metadata": metadata or {},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._entries.append(entry)
        return entry

    def all(self) -> list[dict]:
        return list(self._entries)

    def clear(self) -> None:
        self._entries.clear()


# ─── misc helpers ──────────────────────────────────────────────────────────────

def _now() -> str:
    t = datetime.now()
    return f"{t.minute:02d}:{t.second:02d}"


def _truncate(s: str, n: int = 100) -> str:
    s = s.strip()
    return s[:n] + "…" if len(s) > n else s


# ─── orchestrator ─────────────────────────────────────────────────────────────

class Orchestrator:
    def __init__(
        self,
        sio: socketio.AsyncServer,
        config: ProjectConfig,
        room: str = "",
        on_done: "Callable[[str], None] | None" = None,
    ):
        self.sio = sio
        self.config = config
        self._cwd = get_project_dir()
        self._agents: dict[str, BaseAgent] = {}
        self._file_poll_task: asyncio.Task | None = None
        self._run_task: asyncio.Task | None = None
        self._cancel_requested: bool = False
        self._room = room                    # Socket.IO room name (e.g. "user:{id}")
        self._on_done = on_done             # callback(user_id) on run end

        # coordination state — cleared at start of each run
        self._file_locks   = FileLockRegistry()
        self._mailbox      = AgentMailbox()
        self._coord_log    = CoordinatorLog()
        self._task_list    = SharedTaskList()

        # per-run execution tracking
        self._agent_written_files: dict[str, list[str]] = {}  # agent_id -> [paths]
        self._agent_loops: list[asyncio.Task] = []            # active agent loop tasks
        self._team_active = False

        self._setup_agents(config)

    # ── setup ──────────────────────────────────────────────────────────────────

    def _setup_agents(self, config: ProjectConfig) -> None:
        base_url = config.provider.baseURL
        api_key  = config.provider.apiKey

        self.manager = ManagerAgent(config.agents, base_url=base_url, api_key=api_key)
        self._agents = {"manager": self.manager}

        for a in config.agents:
            if a.get("id") == "manager":
                continue
            self._agents[a["id"]] = BaseAgent(
                name=a["id"],
                model=a.get("model", "deepseek-v4-flash"),
                system_prompt=a.get("system_prompt", ""),
                base_url=base_url,
                api_key=api_key,
                temperature=float(a.get("temperature", 0.7)),
                top_p=float(a.get("top_p", 0.9)),
                top_k=int(a.get("top_k", 0)),
                thinking_budget=int(a.get("thinking_budget", 0)),
                max_tokens=int(a.get("max_tokens", 8192)),
            )

    # ── status / cancel ────────────────────────────────────────────────────────

    def is_running(self) -> bool:
        return self._run_task is not None and not self._run_task.done()

    def cancel(self) -> None:
        # Set the flag first so agent loops and the monitor exit cleanly at their
        # next iteration. Then cancel the outer task so any in-flight `await`
        # raises CancelledError immediately.
        self._cancel_requested = True
        if self._run_task and not self._run_task.done():
            self._run_task.cancel()

    # ── emit helpers ───────────────────────────────────────────────────────────

    async def _emit_agent(self, agent_id: str, status: str) -> None:
        await self.sio.emit("agent_update", {"agentId": agent_id, "status": status}, room=self._room)

    async def _emit_log(self, agent_id: str, message: str) -> None:
        await self.sio.emit("log_update", {
            "time":    _now(),
            "agentId": agent_id,
            "message": _truncate(message),
        }, room=self._room)

    async def _emit_task_done(self, task_id: str) -> None:
        await self.sio.emit("task_update", {"taskId": task_id}, room=self._room)

    async def _emit_terminal(self, line: str) -> None:
        await self.sio.emit("terminal_line", {"line": _truncate(line, 120)}, room=self._room)

    async def _emit_files(self, count: int, filenames: list) -> None:
        await self.sio.emit("file_update", {"count": count, "files": filenames}, room=self._room)

    async def _emit_coordinator_log(self, entry: dict) -> None:
        await self.sio.emit("coordinator_log", {"entry": entry}, room=self._room)

    async def _emit_mailbox_msg(self, msg: dict) -> None:
        await self.sio.emit("mailbox_msg", msg, room=self._room)

    async def _bus_send(self, sender: str, recipient: str, content: str, msg_type: str = "message") -> None:
        """Send a cross-agent message: logs it, stores it in mailbox, emits to frontend."""
        msg = self._mailbox.send(sender, recipient, content, msg_type)
        await self._emit_log(sender, f"→ {recipient}: {_truncate(content, 75)}")
        await self._emit_mailbox_msg(msg)

    # ── coordinator log helpers ────────────────────────────────────────────────

    async def _clog(self, decision_type: str, content: str, metadata: dict | None = None) -> None:
        entry = self._coord_log.record(decision_type, content, metadata)
        await self._emit_coordinator_log(entry)

    # ── git / subprocess helpers ───────────────────────────────────────────────

    async def _git_status(self) -> tuple[int, list[str]]:
        try:
            proc = await asyncio.create_subprocess_exec(
                "git", "status", "--porcelain",
                cwd=str(self._cwd),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            stdout, _ = await proc.communicate()
            lines = [ln[3:].strip() for ln in stdout.decode().splitlines() if ln.strip()]
            return len(lines), lines
        except Exception:
            return 0, []

    async def _run_cmd(self, *args: str) -> None:
        await self._emit_terminal("$ " + " ".join(args))
        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                cwd=str(self._cwd),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            assert proc.stdout
            async for raw in proc.stdout:
                line = raw.decode(errors="replace").rstrip()
                if line:
                    await self._emit_terminal(line)
            await proc.wait()
        except Exception as e:
            await self._emit_terminal(f"[error] {e}")

    async def _auto_commit(self, agent_id: str, task_title: str, files: list[str]) -> None:
        """Conventional commit after each agent task (non-blocking if git fails)."""
        if not files:
            return
        try:
            proc = await asyncio.create_subprocess_exec(
                "git", "add", "--", *files,
                cwd=str(self._cwd),
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await proc.wait()
            if proc.returncode != 0:
                return

            short_id  = agent_id[:6]
            safe_title = task_title[:60].replace('"', "'")
            msg = f"feat({short_id}): {safe_title}"

            proc = await asyncio.create_subprocess_exec(
                "git", "commit", "-m", msg,
                cwd=str(self._cwd),
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await proc.wait()
            if proc.returncode == 0:
                await self._emit_terminal(f"  git commit: {msg}")
                await self._clog("auto_commit", f"{agent_id} committed {len(files)} file(s)", {
                    "agent": agent_id, "files": ",".join(files[:5]),
                })
        except Exception:
            pass  # git failures are non-blocking

    async def _start_file_polling(self) -> None:
        async def _poll():
            while True:
                await asyncio.sleep(2)
                count, files = await self._git_status()
                await self._emit_files(count, files)
        self._file_poll_task = asyncio.create_task(_poll())

    def _stop_file_polling(self) -> None:
        if self._file_poll_task:
            self._file_poll_task.cancel()
            self._file_poll_task = None

    # ── file writing with lock tracking ───────────────────────────────────────

    async def _write_files_from_parsed(
        self, agent_id: str, parsed_files: list[tuple[str, str]], run_id: str = ""
    ) -> list[str]:
        """Write files from (rel_path, content) tuples with lock tracking. Returns written paths."""
        written: list[str] = []

        for rel_path, content in parsed_files:
            rel_path = rel_path.strip().lstrip("/")
            if not rel_path:
                continue

            # Guard against path traversal
            target = (self._cwd / rel_path).resolve()
            if not str(target).startswith(str(self._cwd.resolve())):
                await self._emit_terminal(f"  [skipped] unsafe path: {rel_path}")
                continue

            # File-lock check
            acquired, holder = self._file_locks.acquire(rel_path, agent_id)
            if not acquired:
                await self._emit_terminal(
                    f"  [conflict] {rel_path} held by {holder}, {agent_id} taking over"
                )
                await self.sio.emit("file_conflict", {
                    "path": rel_path,
                    "requestingAgent": agent_id,
                    "holdingAgent": holder,
                }, room=self._room)
                await self._clog("file_conflict", f"{agent_id} overwrote {rel_path} (was {holder})", {
                    "path": rel_path, "winner": agent_id, "loser": holder or "",
                })
                self._file_locks.force_acquire(rel_path, agent_id)
            else:
                await self.sio.emit("file_locked", {"path": rel_path, "agentId": agent_id}, room=self._room)

            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            written.append(rel_path)
            await self._emit_terminal(f"  wrote {rel_path}")

            if run_id:
                async with get_session() as session:
                    if session is not None:
                        session.add(RunFile(
                            run_id=run_id,
                            path=rel_path,
                            content=content,
                            size=len(content.encode()),
                        ))

        # Release locks now that writing is done
        for path in written:
            self._file_locks.release(path, agent_id)
            await self.sio.emit("file_unlocked", {"path": path, "agentId": agent_id}, room=self._room)

        return written

    # ── credit deduction (fire-and-forget) ────────────────────────────────────

    async def _deduct_credits(self, result: dict) -> None:
        """Deduct token cost from UserCredits after an agent call + log to ZenUsage. Never raises."""
        user_id = getattr(self, "_current_user_id", "anonymous")
        if user_id == "anonymous":
            return
        try:
            from ..api.billing import calc_cost_cents
            from ..db.models import UserCredits, ZenUsage
            model      = result.get("model", "")
            prompt     = result.get("prompt_tokens", 0)
            completion = result.get("completion_tokens", 0)
            cost       = calc_cost_cents(model, prompt, completion)
            run_id     = getattr(self, "_run_id", "")
            async with get_session() as session:
                if session is None:
                    return
                if cost > 0:
                    creds = await session.get(UserCredits, user_id)
                    if creds is not None:
                        creds.balance_cents = max(0, creds.balance_cents - cost)
                        creds.updated_at    = datetime.now(timezone.utc)
                session.add(ZenUsage(
                    user_id=user_id,
                    run_id=run_id,
                    model=model,
                    prompt_tokens=prompt,
                    completion_tokens=completion,
                    cost_cents=cost,
                ))
        except Exception:
            pass  # billing failures must never block runs

    # ── main entry ─────────────────────────────────────────────────────────────

    async def run(
        self,
        brief: str,
        user_id: str = "anonymous",
        agent_limit: int | None = None,
        plan: str = "pro",
        api_key: str = "",
        upload_dir: str = "",
        run_id: str = "",
    ) -> None:
        self._run_task = asyncio.current_task()
        self._current_user_id = user_id
        self._agent_limit     = agent_limit
        self._plan            = plan
        self._api_key         = api_key
        self._upload_dir      = upload_dir
        self._run_id          = run_id or str(uuid.uuid4())
        run_id                = self._run_id
        cancelled = False
        year_month = datetime.now(timezone.utc).strftime("%Y-%m")

        # Clear per-run coordination state
        self._file_locks.clear()
        self._mailbox.clear()
        self._coord_log.clear()
        self._task_list.clear()
        self._agent_written_files.clear()
        self._team_active = False
        self._cancel_requested = False

        # Persist run start + increment usage counter
        async with get_session() as session:
            if session is not None:
                session.add(Run(id=run_id, user_id=user_id, brief=brief, status="running"))
                usage = await session.get(UserUsage, (user_id, year_month))
                if usage is None:
                    session.add(UserUsage(user_id=user_id, year_month=year_month, run_count=1))
                else:
                    usage.run_count += 1

        try:
            self.config = load_config()

            if api_key:
                self.config.provider.apiKey = api_key

            # Apply Starter plan model restrictions
            if plan != "pro":
                from ..api.billing import PRO_ONLY_MODELS, STARTER_MODEL_FALLBACK
                from ..core.config_loader import ProjectConfig
                patched = []
                for a in self.config.agents:
                    a = dict(a)
                    if a.get("model", "") in PRO_ONLY_MODELS:
                        a["model"] = STARTER_MODEL_FALLBACK
                    patched.append(a)
                self.config = ProjectConfig(
                    project=self.config.project,
                    sprint=self.config.sprint,
                    provider=self.config.provider,
                    agents=patched,
                )

            self._setup_agents(self.config)
            await self.sio.emit("init", {
                "project": self.config.project,
                "sprint":  self.config.sprint,
                "agents":  self.config.agents,
            }, room=self._room)

            count, files = await self._git_status()
            await self._emit_files(count, files)
            await self._run_cmd("git", "status")
            await self._start_file_polling()

            try:
                await self._run_pipeline(brief, run_id)
            except asyncio.CancelledError:
                cancelled = True
            finally:
                self._stop_file_polling()

            final_status = "cancelled" if cancelled else "done"
            if cancelled:
                await self._emit_terminal("⚠ Run cancelled by user")
            else:
                count, files = await self._git_status()
                await self._emit_files(count, files)
                await self._emit_terminal("✓ Run complete")

            async with get_session() as session:
                if session is not None:
                    run_row = await session.get(Run, run_id)
                    if run_row is not None:
                        run_row.status = final_status
                        run_row.finished_at = datetime.now(timezone.utc)

            await self.sio.emit("run_done", {}, room=self._room)

        except asyncio.CancelledError:
            self._stop_file_polling()
            async with get_session() as session:
                if session is not None:
                    run_row = await session.get(Run, run_id)
                    if run_row is not None:
                        run_row.status = "cancelled"
                        run_row.finished_at = datetime.now(timezone.utc)
            await self.sio.emit("run_done", {}, room=self._room)

        except Exception as e:
            self._stop_file_polling()
            async with get_session() as session:
                if session is not None:
                    run_row = await session.get(Run, run_id)
                    if run_row is not None:
                        run_row.status = "error"
                        run_row.finished_at = datetime.now(timezone.utc)
            await self._emit_terminal(f"[error] {e}")
            await self.sio.emit("run_done", {}, room=self._room)

        finally:
            self._run_task = None
            self._file_locks.clear()
            if self._on_done is not None:
                self._on_done(user_id)

    # ── pipeline ───────────────────────────────────────────────────────────────

    async def _run_pipeline(self, brief: str, run_id: str = "") -> None:
        await self._emit_terminal("$ agent-team start")

        # Identify non-manager, non-reviewer agents.
        # Manager is the planner (Phase 1) and reviewer is excluded from the executor
        # task list by build_manager_system — including either in the execution loop
        # would spin a no-op worker waiting for tasks that never get created.
        _REVIEWER_ROLES = {"reviewer", "code reviewer", "code review"}
        agent_cfgs = [
            a for a in self.config.agents
            if a.get("id") != "manager"
            and a.get("id") != "reviewer"
            and a.get("role", "").lower() not in _REVIEWER_ROLES
        ]
        agent_ids = [str(a["id"]) for a in agent_cfgs if a.get("id")]

        # Apply agent limit if set (Starter plan)
        agent_limit = getattr(self, "_agent_limit", None)
        if agent_limit is not None and len(agent_ids) > agent_limit:
            agent_ids = agent_ids[:agent_limit]

        await self.sio.emit("agents_selected", {"agentIds": agent_ids}, room=self._room)
        await self._emit_log("manager", f"Team: {', '.join(agent_ids)}.")

        # ── Phase 1: Manager creates the task plan ─────────────────────────────
        await self._emit_agent("manager", "thinking")
        await self._emit_log("manager", "Analyzing brief and creating task plan…")
        await self._clog("phase_start", "Phase 1: manager creating task plan", {"brief": brief[:120]})

        # Build the manager prompt with agent roster + upload context
        agent_roster = "\n".join(
            f'- {a.get("id", "?")}: {a.get("role", a.get("id", "?"))}'
            for a in self.config.agents
            if a.get("id") != "manager"
        )
        manager_prompt = (
            f"Project brief: {brief}\n\n"
            f"Available agents:\n{agent_roster}\n\n"
        )
        if hasattr(self, "_upload_dir") and self._upload_dir:
            upload_path = Path(self._upload_dir)
            if upload_path.exists():
                try:
                    from ..core.file_upload import build_file_manifest
                    files_list: list[dict] = []
                    for f in sorted(upload_path.iterdir()):
                        if f.is_file():
                            files_list.append({
                                "filename": f.name,
                                "size": f.stat().st_size,
                                "mime_type": "application/octet-stream",
                                "preview": "",
                            })
                    manifest = build_file_manifest(files_list)
                    if manifest:
                        manager_prompt += (
                            f"\nThe following files were uploaded for this project. "
                            f"Use them as design reference when creating tasks:\n\n{manifest}\n\n"
                        )
                except Exception:
                    pass

        manager_prompt += (
            "Create a task breakdown for the agents to execute. "
            "Return ONLY valid JSON — no markdown, no code fences:\n"
            '{"feature": "3-5 word name", "analysis": "1-2 sentence overview", '
            '"tasks": [{"id": "t1", "title": "<task>", "description": "<details>", "tag": "3-char tag"}]}\n'
        )

        _mgr_res = await self.manager.run(manager_prompt)
        asyncio.create_task(self._deduct_credits(_mgr_res))
        raw = _mgr_res["content"]

        # Parse manager JSON output
        json_match = re.search(r'\{.*\}', raw, re.DOTALL)
        plan: dict = {}
        if json_match:
            try:
                plan = json.loads(json_match.group())
            except json.JSONDecodeError:
                pass

        feature  = plan.get("feature", "")
        analysis = plan.get("analysis", "Decomposing project into subtasks…")
        tasks    = plan.get("tasks", [])

        await self._emit_log("manager", _truncate(analysis))

        if feature:
            await self.sio.emit("feature_set", {"feature": feature}, room=self._room)
            await self._emit_log("manager", f"Operation: {feature}")

        # Dispatch tasks to SharedTaskList
        if tasks:
            for t in tasks:
                desc = t.get("description", "")
                title = t.get("title", "Untitled task")
                self._task_list.add_task(
                    title=title,
                    description=desc,
                    created_by="manager",
                    status="available",
                )
            await self.sio.emit("tasks_init", {"tasks": self._task_list.all_tasks()}, room=self._room)
            await self._clog("task_created", f"Created {len(tasks)} tasks: {[t.get('title','') for t in tasks]}")
        else:
            # Fallback: create a single task if no tasks from manager
            self._task_list.add_task(
                title="Implement the project",
                description=brief[:200],
                created_by="manager",
                status="available",
            )
            await self.sio.emit("tasks_init", {"tasks": self._task_list.all_tasks()}, room=self._room)

        await self._emit_agent("manager", "done")
        await self._emit_log("manager", f"Task plan ready — {len(self._task_list.all_tasks())} tasks.")

        # Persist task list to disk for crash recovery
        self._task_list.save_to_disk(run_id, self._cwd)

        # ── Phase 2: Launch agent loops ────────────────────────────────────────
        self._team_active = True
        await self._emit_log("manager", f"Phase 2 — launching {len(agent_ids)} agent(s)…")
        await self._clog("phase_start", f"Phase 2: {len(agent_ids)} agents running agent loops")

        # Launch each agent in a concurrent loop, staggered by 0.5s
        async def launch_agent(aid: str, delay: float) -> None:
            await asyncio.sleep(delay)
            await self._run_agent_loop(aid, brief, run_id)

        agent_tasks = [launch_agent(aid, i * 0.5) for i, aid in enumerate(agent_ids)]
        self._agent_loops = [asyncio.create_task(t) for t in agent_tasks]

        # ── Phase 3: Monitor until completion ──────────────────────────────────
        while self._team_active:
            await asyncio.sleep(2)

            # Emit file updates
            count, files = await self._git_status()
            await self._emit_files(count, files)

            # Emit task list updates
            await self.sio.emit("tasks_init", {"tasks": self._task_list.all_tasks()}, room=self._room)

            # Persist task list
            self._task_list.save_to_disk(run_id, self._cwd)

            # Check if all agents are done
            all_loops_done = all(t.done() for t in self._agent_loops) if self._agent_loops else True
            all_tasks_done = self._task_list.is_all_done()

            if all_loops_done and all_tasks_done:
                self._team_active = False

            # Check for cancellation
            if self._cancel_requested:
                self._team_active = False

        # ── Phase 4: Finalize ──────────────────────────────────────────────────
        # Cancel any lingering agent loops
        for t in self._agent_loops:
            if not t.done():
                t.cancel()

        # Persist which agents were selected
        async with get_session() as session:
            if session is not None:
                run_row = await session.get(Run, run_id)
                if run_row is not None:
                    run_row.agents_used = json.dumps(agent_ids)

        # Final file check
        count, files = await self._git_status()
        await self._emit_files(count, files)

        summary = self._task_list.summary()
        await self._emit_log("manager", f"Run complete — {summary}")
        await self._clog("run_complete", f"Task summary: {summary}")

    # ── agent loop ─────────────────────────────────────────────────────────────

    async def _run_agent_loop(
        self,
        agent_id: str,
        brief: str,
        run_id: str,
    ) -> None:
        agent = self._agents.get(agent_id)
        if not agent:
            return

        await self._emit_agent(agent_id, "idle")
        await self._emit_log(agent_id, "Agent online — waiting for tasks")
        await self._clog("agent_online", f"{agent_id} started agent loop")

        if agent_id not in self._agent_written_files:
            self._agent_written_files[agent_id] = []

        while self._team_active:
            # Check for cancellation
            if self._cancel_requested:
                break

            # Read unread mailbox messages for context
            unread = self._mailbox.unread(agent_id)
            mailbox_context = ""
            if unread:
                mailbox_context = "\n".join(
                    f"[{m['type'].upper()} from {m['from']}]: {m['content']}"
                    for m in unread
                )

            # Try to claim a task
            task = self._task_list.claim_task(agent_id)
            if task is None:
                if self._task_list.is_all_done():
                    break
                await asyncio.sleep(1)
                continue

            task_id = task["id"]
            await self._emit_agent(agent_id, "coding")
            await self._emit_log(agent_id, f"Claimed: {task['title']}")
            await self._clog("task_claimed", f"{agent_id} claimed '{task['title']}'", {
                "agent": agent_id, "task": task_id,
            })

            self._task_list.start_task(task_id, agent_id)

            # Build the task prompt
            context_parts = [f"Project brief: {brief[:300]}"]
            if mailbox_context:
                context_parts.append(f"Mailbox messages:\n{mailbox_context}")

            # Include previously written file summaries for cross-agent awareness
            file_summaries: list[str] = []
            for aid, paths in self._agent_written_files.items():
                for p in paths[-5:]:  # last 5 files per agent
                    file_summaries.append(f"  {aid} wrote: {p}")
            if file_summaries:
                context_parts.append("Files written by other agents:\n" + "\n".join(file_summaries))

            context = "\n\n".join(context_parts)

            prompt = (
                f"Task: {task['title']}\n"
                f"Description: {task.get('description', '')}\n\n"
                f"{context}\n\n"
                "Write the complete implementation for this task. "
                "Output each file using this format:\n\n"
                "--- FILE: relative/path/from/project/root ---\n"
                "complete file contents here\n"
                "--- END FILE ---\n\n"
                "Write COMPLETE, RUNNABLE code. Multiple files are allowed — "
                "write each as its own FILE block. Do not use placeholders or TODOs."
            )

            _exec_res = await agent.run(prompt)
            asyncio.create_task(self._deduct_credits(_exec_res))
            result = _exec_res["content"]

            # Parse FILE blocks from agent output
            parsed_files: list[tuple[str, str]] = []
            for match in _FILE_RE.finditer(result):
                rel_path = match.group(1).strip()
                content  = match.group(2).strip()
                if rel_path:
                    parsed_files.append((rel_path, content))

            # Write parsed files to disk
            written: list[str] = []
            if parsed_files:
                written = await self._write_files_from_parsed(agent_id, parsed_files, run_id)
                self._agent_written_files[agent_id].extend(written)

            if written:
                await self._emit_log(agent_id, f"Wrote {len(written)} file(s): {', '.join(written[:3])}")
                # Auto-commit after each task
                await self._auto_commit(agent_id, task["title"], written)

            # Send a summary to manager via mailbox
            summary = _truncate(result, 150)
            await self._bus_send(agent_id, "manager", f"Completed '{task['title']}': {summary}")

            # Mark task complete
            self._task_list.complete_task(task_id, agent_id, written)
            await self._emit_task_done(task_id)

            await self._emit_agent(agent_id, "done")
            await self._clog("task_completed", f"{agent_id} completed '{task['title']}'", {
                "agent": agent_id, "task": task_id, "files": len(written),
            })

            await asyncio.sleep(0.3)

        await self._emit_agent(agent_id, "idle")
        await self._emit_log(agent_id, "Agent finished — no more tasks")
        await self._clog("agent_finished", f"{agent_id} exited agent loop")
