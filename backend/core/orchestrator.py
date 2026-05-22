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
from ..db.models import Run, RunFile, UserUsage, ActionFile, ActionTool

# ─── file-block regex for agent output parsing ───────────────────────────────
_FILE_RE = re.compile(
    r'^---\s*FILE:\s*(.+?)\s*---\s*$(.+?)^---\s*END\s*FILE\s*---\s*$',
    re.MULTILINE | re.DOTALL
)

# ─── pipeline constants ────────────────────────────────────────────────────────
MAX_RESEARCH_ROUNDS = 2
MAX_PLAN_ROUNDS = 2
MAX_REWORK_ITERATIONS = 1


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
        self._task_list: SharedTaskList | None = None

        # pipeline stage tracking
        self._stage        = "idle"             # research | plan | production | validation
        self._stage_artifacts: dict[str, dict] = {}  # per-stage data

        # rework loop control
        self._rework_iteration = 0

        # stage artifacts (populated by stages 1-2)
        self._research_summary = ""
        self._research_artifacts: dict[str, str] = {}  # agent_id → report
        self._plan_artifacts: dict[str, str] = {}       # agent_id → spec

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

    async def _emit_thinking(self, agent_id: str, thinking: str) -> None:
        """Emit thinking/reasoning content from an agent. Fire-and-forget safe."""
        if not thinking:
            return
        await self.sio.emit("thinking_content", {
            "agentId": agent_id,
            "time": _now(),
            "content": thinking[:2000],
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
        # Persist to DB if available
        asyncio.create_task(self._persist_coordinator_event(decision_type, content, metadata))
        # Regenerate crash-recovery snapshot
        asyncio.create_task(self._write_current_md_snapshot())

    async def _persist_coordinator_event(self, event_type: str, content: str,
                                          metadata: dict | None = None) -> None:
        """Persist a coordinator event to DB. Fire-and-forget, never raises."""
        run_id = getattr(self, "_run_id", "")
        if not run_id:
            return
        try:
            from ..db.models import CoordinatorEvent
            import json
            async with get_session() as session:
                if session is not None:
                    session.add(CoordinatorEvent(
                        run_id=run_id,
                        event_type=event_type,
                        agent_id=None,
                        content=content,
                        metadata_json=json.dumps(metadata) if metadata else None,
                    ))
        except Exception:
            pass

    async def _write_current_md_snapshot(self) -> None:
        """Write .taskmesh/current.md crash-recovery snapshot. Fire-and-forget."""
        try:
            if self._task_list is None:
                return
            tasks = await self._task_list.all_tasks()
            brief = getattr(self, "_current_brief", "")
            phase = self._stage
            total_files = sum(
                len(paths) for paths in self._agent_written_files.values()
            )
            coord_count = len(self._coord_log.all())

            lines = [
                f"# TaskMesh run {self._run_id}",
                f"Brief: {brief}",
                f"Started: {datetime.now(timezone.utc).isoformat()}",
                f"Phase: {phase}",
                "Tasks:",
            ]
            for t in tasks:
                icon = {"available": "⬜", "claimed": "⏳", "in_progress": "🔄",
                        "completed": "✓", "blocked": "🚫", "failed": "✗"}.get(t["status"], "?")
                agent = f" (by {t['assigned_to']})" if t.get("assigned_to") else ""
                acc = t.get("acceptance", [])
                met_count = 0
                if "_acceptance_met" in t:
                    met_count = sum(
                        1 for v in t["_acceptance_met"].values() if v.get("met"))
                criteria = f" — {met_count}/{len(acc)} criteria met" if acc else ""
                lines.append(f"  {icon} {t['id']} — {t['title']} ({t['status']}){agent}{criteria}")
            lines.append(f"Files written: {total_files}")
            lines.append(f"Coordinator events: {coord_count}")

            target = self._cwd / ".taskmesh" / "current.md"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("\n".join(lines) + "\n", encoding="utf-8")
        except Exception:
            pass

    async def _enter_stage(self, stage: str, participants: list[str],
                            metadata: dict | None = None) -> None:
        """Transition to a new pipeline stage. Emits stage_start event."""
        self._stage = stage
        self._stage_artifacts[stage] = {}
        await self.sio.emit("stage_start", {
            "stage": stage,
            "participants": participants,
        }, room=self._room)
        await self._clog("stage_start", f"Stage: {stage}", {
            "stage": stage,
            "participants": ",".join(participants),
            **(metadata or {}),
        })

    async def _check_resumable(self, user_id: str, current_run_id: str) -> None:
        """Check for stale running runs and emit run_resumable. Never raises."""
        try:
            async with get_session() as session:
                if session is None:
                    return
                from ..db.models import Run as RunModel
                from sqlalchemy import select
                result = await session.execute(
                    select(RunModel)
                    .where(
                        RunModel.user_id == user_id,
                        RunModel.status == "running",
                        RunModel.id != current_run_id,
                    )
                    .limit(1)
                )
                stale = result.scalar_one_or_none()
                if stale is not None:
                    await self.sio.emit("run_resumable", {
                        "runId": stale.id,
                        "brief": stale.brief[:120],
                        "startedAt": stale.started_at.isoformat() if stale.started_at else "",
                    }, room=self._room)
        except Exception:
            pass

    async def _run_search_for_agent(
        self, agent_id: str, query: str
    ) -> str:
        """Run docs.search for an agent query. Returns formatted results string."""
        from ..core.docs_search import search_docs
        roots: list[Path] = [self._cwd]
        upload_dir = getattr(self, "_upload_dir", "")
        if upload_dir:
            p = Path(upload_dir)
            if p.exists():
                roots.append(p)
        snippets = search_docs(query, roots, max_results=10)
        if not snippets:
            return f"Search for '{query}' returned no results."
        lines = [f"Search results for '{query}':"]
        for s in snippets:
            lines.append(f"  {s.file}:{s.line}  {s.text}")
        return "\n".join(lines)

    async def _run_with_search(
        self,
        agent: BaseAgent,
        prompt: str,
        agent_id: str,
        task_id: int | None = None,
        max_rounds: int = 3,
    ) -> str:
        """Run agent, handling <search> blocks with re-prompt. Returns final content."""
        _SEARCH_RE = re.compile(r'<search>(.+?)</search>', re.DOTALL | re.IGNORECASE)

        _exec_res = await agent.run(prompt)
        asyncio.create_task(self._deduct_credits(_exec_res))
        asyncio.create_task(self._record_tool_call(agent_id, _exec_res, task_id=task_id))
        asyncio.create_task(self._emit_thinking(agent_id, _exec_res.get("thinking_content", "")))
        result = _exec_res["content"]

        search_rounds = 0
        while search_rounds < max_rounds:
            searches = _SEARCH_RE.findall(result)
            if not searches:
                break
            search_rounds += 1
            search_results: list[str] = []
            for query in searches:
                q = query.strip()[:200]
                if not q:
                    continue
                sr = await self._run_search_for_agent(agent_id, q)
                search_results.append(sr)
                asyncio.create_task(self._record_tool_call(
                    agent_id,
                    {"prompt_tokens": 0, "completion_tokens": 0, "_status": "ok",
                     "_error": json.dumps({"query": q, "results": sr[:500]}),
                    },
                    tool_name="docs.search",
                    task_id=task_id,
                ))
            if not search_results:
                break
            enriched = (
                result.replace("<search>", "[SEARCH RAN] <search>").replace("</search>", "</search> [SEARCH RAN]")
                + "\n\n[SEARCH RESULTS]\n" + "\n---\n".join(search_results)
                + "\n[/SEARCH RESULTS]\n\n"
                "Use the search results above to refine your answer. Do NOT output <search> blocks — "
                "search has already been completed. Just write the code."
            )
            _exec_res = await agent.run(enriched)
            asyncio.create_task(self._deduct_credits(_exec_res))
            asyncio.create_task(self._record_tool_call(agent_id, _exec_res, task_id=task_id))
            result = _exec_res["content"]

        return result

    def _build_upload_manifest_context(self) -> str:
        """Build upload file manifest string from _upload_dir. Cached per run."""
        if not getattr(self, "_manifest_cached", False):
            self._manifest_context = ""
            upload_dir = getattr(self, "_upload_dir", "")
            if upload_dir:
                upload_path = Path(upload_dir)
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
                            self._manifest_context = (
                                "\nThe following files were uploaded for this project. "
                                "Use them as design reference when creating tasks:\n\n"
                                f"{manifest}\n"
                            )
                    except Exception:
                        pass
            self._manifest_cached = True
        return self._manifest_context

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
                await asyncio.sleep(5)
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
                asyncio.create_task(self._record_file_op(
                    agent_id, rel_path, "skipped", notes="unsafe path",
                ))
                continue

            # File-lock check
            acquired, holder = self._file_locks.acquire(rel_path, agent_id)
            was_conflict = not acquired
            if was_conflict:
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

            existed_before = target.exists()
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            written.append(rel_path)
            await self._emit_terminal(f"  wrote {rel_path}")

            if was_conflict:
                op = "conflict"
            elif existed_before:
                op = "overwritten"
            else:
                op = "written"
            size_bytes = len(content.encode())
            asyncio.create_task(self._record_file_op(
                agent_id,
                rel_path,
                op,
                size_bytes=size_bytes,
                notes=(f"overwrote {holder}" if was_conflict and holder else ""),
            ))

            if run_id:
                async with get_session() as session:
                    if session is not None:
                        session.add(RunFile(
                            run_id=run_id,
                            path=rel_path,
                            content=content,
                            size=size_bytes,
                        ))

        # Release locks now that writing is done
        for path in written:
            self._file_locks.release(path, agent_id)
            await self.sio.emit("file_unlocked", {"path": path, "agentId": agent_id}, room=self._room)

        return written

    # ── action audit (fire-and-forget) ────────────────────────────────────────

    async def _record_file_op(
        self,
        agent_id: str,
        rel_path: str,
        op: str,
        size_bytes: int = 0,
        notes: str = "",
        task_id: int | None = None,
    ) -> None:
        """Append an ActionFile row. Never raises — DB outages must not block runs."""
        run_id = getattr(self, "_run_id", "")
        if not run_id:
            return
        try:
            async with get_session() as session:
                if session is None:
                    return
                session.add(ActionFile(
                    run_id=run_id,
                    agent_id=agent_id,
                    task_id=task_id,
                    path=rel_path,
                    op=op,
                    size_bytes=size_bytes,
                    notes=notes or None,
                ))
        except Exception:
            pass

    async def _record_tool_call(
        self,
        agent_id: str,
        result: dict,
        tool_name: str = "llm.call",
        task_id: int | None = None,
    ) -> None:
        """Append an ActionTool row using telemetry attached by BaseAgent._run_with_retry.

        Looks for _attempts / _status / _error / _duration_ms on result. Falls back
        to status='ok', attempts=1 when telemetry is missing (older callers).
        """
        run_id = getattr(self, "_run_id", "")
        if not run_id:
            return
        try:
            async with get_session() as session:
                if session is None:
                    return
                session.add(ActionTool(
                    run_id=run_id,
                    agent_id=agent_id,
                    task_id=task_id,
                    tool_name=tool_name,
                    model=result.get("model") or None,
                    prompt_tokens=int(result.get("prompt_tokens", 0) or 0),
                    completion_tokens=int(result.get("completion_tokens", 0) or 0),
                    status=result.get("_status", "ok"),
                    attempts=int(result.get("_attempts", 1) or 1),
                    error=(result.get("_error") or None),
                    duration_ms=int(result.get("_duration_ms", 0) or 0),
                ))
        except Exception:
            pass

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
                    year_month=datetime.now(timezone.utc).strftime("%Y-%m"),
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
        self._task_list = SharedTaskList(run_id=self._run_id, session_factory=get_session)
        self._agent_written_files.clear()
        self._team_active = False
        self._cancel_requested = False
        self._current_brief = brief
        self._stage = "idle"
        self._stage_artifacts.clear()
        self._rework_iteration = 0
        self._manifest_cached = False

        # Check for interrupted runs from a prior process
        asyncio.create_task(self._check_resumable(user_id, self._run_id))

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

        # Identify agents by role — planners do Stages 1-2, executors do Stage 3.
        _REVIEWER_ROLES = {"reviewer", "code reviewer", "code review"}
        all_agents = self.config.agents

        planners = [
            a for a in all_agents
            if a.get("planner") and a.get("id") != "manager"
        ]
        planner_ids = [str(a["id"]) for a in planners]

        executors = [
            a for a in all_agents
            if a.get("id") != "manager"
            and a.get("id") != "reviewer"
            and not a.get("planner", False)
            and a.get("role", "").lower() not in _REVIEWER_ROLES
        ]
        executor_ids = [str(a["id"]) for a in executors]

        # Apply agent limit if set (Starter plan)
        agent_limit = getattr(self, "_agent_limit", None)
        if agent_limit is not None and len(executor_ids) > agent_limit:
            executor_ids = executor_ids[:agent_limit]

        all_participant_ids = executor_ids + planner_ids
        if all_participant_ids:
            await self.sio.emit("agents_selected", {"agentIds": all_participant_ids}, room=self._room)
            await self._emit_log("manager", f"Team: {', '.join(all_participant_ids)}.")

        manifest = self._build_upload_manifest_context()

        # ═══ Stage 1: Research ════════════════════════════════════════════════
        await self._enter_stage("research", ["manager"] + planner_ids)
        await self._run_stage_research(brief, planners, planner_ids, manifest)

        # ═══ Stage 2: Plan ════════════════════════════════════════════════════
        await self._enter_stage("plan", ["manager"] + planner_ids)
        await self._run_stage_plan(brief, planners, planner_ids, executor_ids, manifest)

        # ═══ Stage 3: Production + Validation ═════════════════════════════════
        approved = False
        while True:
            await self._enter_stage("production", executor_ids,
                                     metadata={"rework": str(self._rework_iteration)})
            await self._run_stage_production(brief, run_id, executor_ids)
            if self._cancel_requested:
                break

            await self._enter_stage("validation", ["manager", "reviewer"] + planner_ids)
            approved = await self._run_stage_validation(brief)
            if approved or self._rework_iteration >= MAX_REWORK_ITERATIONS:
                break
            self._rework_iteration += 1

        # ═══ Finalize ═════════════════════════════════════════════════════════
        for t in self._agent_loops:
            if not t.done():
                t.cancel()

        async with get_session() as session:
            if session is not None:
                run_row = await session.get(Run, run_id)
                if run_row is not None:
                    run_row.agents_used = json.dumps(executor_ids)

        count, files = await self._git_status()
        await self._emit_files(count, files)

        summary = await self._task_list.summary()
        await self._emit_log("manager", f"Run complete — {summary}")
        await self._clog("run_complete", f"Task summary: {summary}")

    # ══════════════════════════════════════════════════════════════════════════
    # Stage 1: Research
    # ══════════════════════════════════════════════════════════════════════════

    async def _run_stage_research(
        self, brief: str, planners: list[dict],
        planner_ids: list[str], manifest: str,
    ) -> None:
        await self._emit_agent("manager", "thinking")
        await self._emit_log("manager", "Stage 1: Research — analyzing requirements…")

        # No planner agents → Manager does solo research
        if not planner_ids:
            research_prompt = (
                f"Project brief: {brief}\n\n"
                f"{manifest}\n"
                "You are in the Research stage. Analyze the brief and identify:\n"
                "1. Required tools, libraries, and frameworks\n"
                "2. Key architectural decisions and constraints\n"
                "3. Potential risks and edge cases\n\n"
                "Produce a structured research report. Use plain text, not JSON."
            )
            _res = await self.manager.run(research_prompt)
            asyncio.create_task(self._deduct_credits(_res))
            asyncio.create_task(self._record_tool_call("manager", _res))
            self._research_summary = _res["content"]
            await self._emit_log("manager", "Research complete (solo)")
            await self.sio.emit("research_complete", {
                "summary": self._research_summary[:500],
                "artifacts": {"manager": self._research_summary[:200]},
            }, room=self._room)
            return

        # Concurrent planner research
        async def _run_planner_research(agent_id: str) -> tuple[str, str]:
            agent = self._agents.get(agent_id)
            if not agent:
                return agent_id, ""
            agent_cfg = next((a for a in self.config.agents if a.get("id") == agent_id), {})
            role = agent_cfg.get("role", agent_id)
            prompt = (
                f"Project brief: {brief}\n\n"
                f"{manifest}\n"
                f"Your role: {role}\n\n"
                "You are in the Research stage. Research this project and identify:\n"
                f"- Tools, libraries, and frameworks relevant to your role ({role})\n"
                "- Key architectural decisions\n"
                "- Constraints and risks\n\n"
                "Use <search> blocks to search the existing codebase or uploaded files "
                "for relevant context. Produce a structured report. Plain text, not JSON."
            )
            try:
                result = await self._run_with_search(agent, prompt, agent_id)
            except Exception:
                result = ""
            self._research_artifacts[agent_id] = result
            await self.sio.emit("research_report", {
                "agentId": agent_id,
                "report": result[:500],
            }, room=self._room)
            return agent_id, result

        tasks = [asyncio.create_task(_run_planner_research(aid)) for aid in planner_ids]
        await asyncio.gather(*tasks, return_exceptions=True)

        # Manager summary round
        research_context = "\n\n".join(
            f"=== {aid} Research Report ===\n{text}"
            for aid, text in self._research_artifacts.items()
            if text
        )
        summary_prompt = (
            f"Project brief: {brief}\n\n"
            "Below are research reports from specialized agents. "
            "Consolidate them into a single research summary:\n\n"
            f"{research_context}\n\n"
            "Produce a consolidated research summary covering:\n"
            "1. Tools/technologies to use\n"
            "2. Key constraints\n"
            "3. Risks flagged\n"
            "Plain text, not JSON."
        )
        _res = await self.manager.run(summary_prompt)
        asyncio.create_task(self._deduct_credits(_res))
        asyncio.create_task(self._record_tool_call("manager", _res))
        self._research_summary = _res["content"]

        # Multi-turn follow-up (capped at MAX_RESEARCH_ROUNDS)
        for _round in range(MAX_RESEARCH_ROUNDS):
            follow_prompt = (
                f"Research summary so far:\n{self._research_summary}\n\n"
                "Based on the research above, is anything unclear or missing? "
                "If yes, write exactly ONE question per planner agent prefixed with "
                "the agent ID like 'Q researcher: ...' or 'Q webdev: ...'. "
                "If no questions remain, respond with just 'DONE'."
            )
            _res = await self.manager.run(follow_prompt)
            asyncio.create_task(self._deduct_credits(_res))
            content = _res["content"]
            if content.strip().upper().startswith("DONE"):
                break
            questions = re.findall(r'Q\s+(\w+)\s*:\s*(.+)', content)
            if not questions:
                break
            for target_id, question in questions:
                agent = self._agents.get(target_id)
                if not agent:
                    continue
                try:
                    ans = await self._run_with_search(
                        agent,
                        f"Project brief: {brief}\n\n"
                        f"The Manager asked you this question:\n{question.strip()}\n\n"
                        "Answer concisely. Use <search> if needed.",
                        target_id,
                    )
                except Exception:
                    ans = f"(unable to answer: {question})"
                # Feed response back to Manager for updated summary
                update_prompt = (
                    f"Previous research summary:\n{self._research_summary}\n\n"
                    f"{target_id} responded to your question '{question.strip()}':\n{ans}\n\n"
                    "Update the consolidated research summary incorporating this new information."
                )
                _upd = await self.manager.run(update_prompt)
                asyncio.create_task(self._deduct_credits(_upd))
                self._research_summary = _upd["content"]

        await self._emit_agent("manager", "done")
        await self._emit_log("manager", "Research complete")
        await self.sio.emit("research_complete", {
            "summary": self._research_summary[:500],
            "agentCount": len(planner_ids),
        }, room=self._room)
        await self._clog("stage_complete", "Stage 1: Research complete")

    # ══════════════════════════════════════════════════════════════════════════
    # Stage 2: Plan
    # ══════════════════════════════════════════════════════════════════════════

    async def _run_stage_plan(
        self, brief: str, planners: list[dict],
        planner_ids: list[str], executor_ids: list[str], manifest: str,
    ) -> None:
        await self._emit_agent("manager", "thinking")
        await self._emit_log("manager", "Stage 2: Plan — creating architecture…")

        # No planner agents → Manager does solo plan (existing Phase 1 logic)
        if not planner_ids:
            await self._manager_create_task_plan(
                brief, executor_ids, manifest,
                extra_context=self._research_summary or "",
            )
            await self._emit_agent("manager", "done")
            await self._emit_log("manager", "Plan complete (solo)")
            await self.sio.emit("plan_complete", {
                "feature": "",
                "taskCount": len(await self._task_list.all_tasks()),
                "agentCount": 0,
            }, room=self._room)
            await self._clog("stage_complete", "Stage 2: Plan complete (solo)")
            return

        # Concurrent planner specs
        async def _run_planner_spec(agent_id: str) -> tuple[str, str]:
            agent = self._agents.get(agent_id)
            if not agent:
                return agent_id, ""
            agent_cfg = next((a for a in self.config.agents if a.get("id") == agent_id), {})
            role = agent_cfg.get("role", agent_id)
            prompt = (
                f"Project brief: {brief}\n\n"
                f"{manifest}\n"
                f"Your role: {role}\n\n"
                f"Research summary:\n{self._research_summary}\n\n"
                "You are in the Plan stage. Produce a detailed technical specification "
                f"for your domain ({role}). Include:\n"
                "- Architecture decisions\n"
                "- Component/module layout\n"
                "- Data models / API contracts / UI component hierarchy (based on role)\n"
                "- Implementation order\n\n"
                "Use <search> blocks to reference the existing codebase if relevant. "
                "Output as plain text, not JSON."
            )
            try:
                spec = await self._run_with_search(agent, prompt, agent_id)
            except Exception:
                spec = ""
            self._plan_artifacts[agent_id] = spec
            # Write spec to disk
            try:
                plans_dir = self._cwd / ".taskmesh" / "plans"
                plans_dir.mkdir(parents=True, exist_ok=True)
                (plans_dir / f"{agent_id}.md").write_text(spec, encoding="utf-8")
            except Exception:
                pass
            await self.sio.emit("plan_report", {
                "agentId": agent_id,
                "spec": spec[:500],
            }, room=self._room)
            return agent_id, spec

        spec_tasks = [asyncio.create_task(_run_planner_spec(aid)) for aid in planner_ids]
        await asyncio.gather(*spec_tasks, return_exceptions=True)

        # Manager creates task plan from enriched context
        plan_context = "\n\n".join(
            f"=== {aid} Technical Spec ===\n{text}"
            for aid, text in self._plan_artifacts.items()
            if text
        )
        extra = f"{self._research_summary}\n\n{plan_context}"
        await self._manager_create_task_plan(brief, executor_ids, manifest, extra_context=extra)

        # Multi-turn planning (capped at MAX_PLAN_ROUNDS)
        for _round in range(MAX_PLAN_ROUNDS):
            tasks = await self._task_list.all_tasks()
            task_list_str = "\n".join(
                f"  [{t['status']}] {t['id']} — {t['title']}" for t in tasks
            )
            follow_prompt = (
                f"Task plan:\n{task_list_str}\n\n"
                "Review the task plan above. Are any tasks unclear, missing, or overlapping? "
                "If yes, write ONE question per planner agent prefixed with "
                "'Q {agent_id}: ...'. "
                "If the plan looks complete, respond with just 'DONE'."
            )
            _res = await self.manager.run(follow_prompt)
            asyncio.create_task(self._deduct_credits(_res))
            content = _res["content"]
            if content.strip().upper().startswith("DONE"):
                break
            questions = re.findall(r'Q\s+(\w+)\s*:\s*(.+)', content)
            if not questions:
                break
            for target_id, question in questions:
                agent = self._agents.get(target_id)
                if not agent:
                    continue
                try:
                    ans = await self._run_with_search(
                        agent,
                        f"Project brief: {brief}\n\n"
                        f"Manager question about the plan:\n{question.strip()}\n\n"
                        "Answer concisely.",
                        target_id,
                    )
                except Exception:
                    ans = f"(unable to answer: {question})"
                extra = f"{extra}\n\n{target_id} clarification: {ans}"
            # Re-create tasks with updated context
            await self._manager_create_task_plan(
                brief, executor_ids, manifest, extra_context=extra,
            )

        await self._emit_agent("manager", "done")
        task_count = len(await self._task_list.all_tasks())
        await self._emit_log("manager", f"Plan complete — {task_count} tasks")
        self._task_list.save_to_disk(run_id=self._run_id, cwd=self._cwd)
        await self.sio.emit("plan_complete", {
            "feature": "",
            "taskCount": task_count,
            "agentCount": len(planner_ids),
        }, room=self._room)
        await self._clog("stage_complete", "Stage 2: Plan complete")

    async def _manager_create_task_plan(
        self, brief: str, executor_ids: list[str],
        manifest: str, extra_context: str = "",
    ) -> None:
        """Run the Manager to produce a task plan and dispatch to SharedTaskList."""
        agent_roster = "\n".join(
            f'- {a.get("id", "?")}: {a.get("role", a.get("id", "?"))}'
            for a in self.config.agents
            if a.get("id") != "manager"
        )
        manager_prompt = (
            f"Project brief: {brief}\n\n"
            f"Available agents:\n{agent_roster}\n\n"
            f"{manifest}\n"
        )
        if extra_context:
            manager_prompt += f"\nAdditional context:\n{extra_context}\n\n"
        manager_prompt += (
            "Create a task breakdown for the agents to execute. "
            "Return ONLY valid JSON — no markdown, no code fences:\n"
            '{"feature": "3-5 word name", "analysis": "1-2 sentence overview", '
            '"tasks": [{"id": "t1", "title": "<task>", "description": "<details>", '
            '"tag": "3-char tag", "acceptance": ["<criterion>", ...]}]}\n'
        )

        _mgr_res = await self.manager.run(manager_prompt)
        asyncio.create_task(self._deduct_credits(_mgr_res))
        asyncio.create_task(self._record_tool_call("manager", _mgr_res))
        raw = _mgr_res["content"]

        json_match = re.search(r'\{.*\}', raw, re.DOTALL)
        plan: dict = {}
        if json_match:
            try:
                plan = json.loads(json_match.group())
            except json.JSONDecodeError:
                pass

        feature = plan.get("feature", "")
        analysis = plan.get("analysis", "Decomposing project into subtasks…")
        tasks_list = plan.get("tasks", [])

        await self._emit_log("manager", _truncate(analysis))
        if feature:
            await self.sio.emit("feature_set", {"feature": feature}, room=self._room)
            await self._emit_log("manager", f"Operation: {feature}")

        if tasks_list:
            for t in tasks_list:
                desc = t.get("description", "")
                title = t.get("title", "Untitled task")
                acceptance = t.get("acceptance", [])
                if not isinstance(acceptance, list):
                    acceptance = []
                await self._task_list.add_task(
                    title=title,
                    description=desc,
                    created_by="manager",
                    status="available",
                    acceptance=acceptance,
                )
            await self.sio.emit("tasks_init", {"tasks": await self._task_list.all_tasks()}, room=self._room)
            await self._clog("task_created", f"Created {len(tasks_list)} tasks")
        else:
            await self._task_list.add_task(
                title="Implement the project",
                description=brief[:200],
                created_by="manager",
            )
            await self.sio.emit("tasks_init", {"tasks": await self._task_list.all_tasks()}, room=self._room)

        await self.sio.emit("tasks_init", {"tasks": await self._task_list.all_tasks()}, room=self._room)

    # ══════════════════════════════════════════════════════════════════════════
    # Stage 3a: Production (Execution)
    # ══════════════════════════════════════════════════════════════════════════

    async def _run_stage_production(
        self, brief: str, run_id: str,
        executor_ids: list[str],
    ) -> None:
        self._team_active = True
        start_time = datetime.now(timezone.utc)
        timeout_seconds = getattr(self, "_run_timeout_seconds", 600)
        await self._emit_log("manager", f"Stage 3 — launching {len(executor_ids)} executor(s)…")
        await self._clog("phase_start", f"Stage 3: {len(executor_ids)} agents running agent loops")

        async def launch_agent(aid: str, delay: float) -> None:
            await asyncio.sleep(delay)
            await self._run_agent_loop(aid, brief, run_id)

        agent_tasks = [launch_agent(aid, i * 0.5) for i, aid in enumerate(executor_ids)]
        self._agent_loops = [asyncio.create_task(t) for t in agent_tasks]

        # Monitor loop
        while self._team_active:
            await asyncio.sleep(2)
            if self._task_list.is_dirty():
                await self.sio.emit("tasks_init", {"tasks": await self._task_list.all_tasks()}, room=self._room)
                self._task_list.mark_clean()
                asyncio.create_task(self._write_current_md_snapshot())
            self._task_list.save_to_disk(run_id, self._cwd)
            asyncio.create_task(self._task_list.recover_stale_claims(300))
            all_loops_done = all(t.done() for t in self._agent_loops) if self._agent_loops else True
            all_tasks_done = await self._task_list.is_all_done()
            if all_loops_done and all_tasks_done:
                self._team_active = False
            if self._cancel_requested:
                self._team_active = False
            # Timeout check
            elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
            if elapsed > timeout_seconds:
                await self._emit_terminal(f"⏱ Run timed out after {int(elapsed)}s")
                await self.sio.emit("run_timeout", {
                    "run_id": self._run_id,
                    "elapsed_seconds": int(elapsed),
                }, room=self._room)
                self._cancel_requested = True
                self._team_active = False

        await self._clog("stage_complete", "Stage 3a: Execution complete")

    # ══════════════════════════════════════════════════════════════════════════
    # Stage 3b: Validation (multi-agent verdict)
    # ══════════════════════════════════════════════════════════════════════════

    async def _run_stage_validation(self, brief: str) -> bool:
        """Run two-tier validation. Returns True if overall approved."""
        # Build common context for all validators
        tasks = await self._task_list.all_tasks()
        files_written: list[str] = []
        for aid, paths in self._agent_written_files.items():
            files_written.extend(paths)

        # Tier 1: Reviewer + Researcher concurrently
        verdicts: list[dict] = []

        async def _get_verdict(agent_id: str, role_prompt: str) -> dict | None:
            agent = self._agents.get(agent_id)
            if not agent:
                return None
            prompt = self._build_validation_prompt(
                brief, tasks, files_written, role_prompt,
            )
            try:
                raw = await self._run_with_search(agent, prompt, agent_id, max_rounds=1)
            except Exception:
                return None
            verdict = self._parse_verdict(raw)
            if verdict:
                verdict["agentId"] = agent_id
                asyncio.create_task(self._record_tool_call(
                    agent_id,
                    {"prompt_tokens": 0, "completion_tokens": 0, "_status": "ok",
                     "_error": json.dumps(verdict)},
                    tool_name="validation",
                ))
                await self.sio.emit("validation_verdict", verdict, room=self._room)
                # Update acceptance criteria from verdict
                for cid, cr in (verdict.get("criteria_results") or {}).items():
                    if isinstance(cr, dict):
                        await self._task_list.set_acceptance_met(
                            cid, bool(cr.get("met", False)), checked_by=agent_id,
                        )
            return verdict

        reviewer_verdict = await _get_verdict(
            "reviewer",
            "You are the Reviewer. Evaluate code quality, acceptance criteria, "
            "edge cases, and completeness of the delivered code.",
        )
        if reviewer_verdict:
            verdicts.append(reviewer_verdict)

        # Run researcher if it exists and is a planner
        researcher_id = next(
            (a["id"] for a in self.config.agents
             if a.get("planner") and a.get("id") != "manager"
             and a.get("role", "").lower().startswith(("research", "tech"))),
            None,
        )
        if researcher_id:
            researcher_verdict = await _get_verdict(
                researcher_id,
                "You are the Researcher. Verify that the delivered code follows "
                "the research recommendations (tools, libraries, approaches). "
                "Check for compliance with the research summary.",
            )
            if researcher_verdict:
                verdicts.append(researcher_verdict)

        # Check agreement for Tier 1
        tier1_approved = all(v.get("approved", True) for v in verdicts) if verdicts else True
        has_blocker = any(
            any(i.get("severity") == "blocker" for i in v.get("issues", []))
            for v in verdicts
        )

        # Tier 2: Manager tiebreaker if Tier 1 disagrees
        if not tier1_approved or has_blocker:
            manager_verdict = await _get_verdict(
                "manager",
                "You are the Manager. Cast the final verdict. Below are the "
                "validation reports from Reviewer and Researcher. You must decide "
                'whether the output is acceptable. If you find a "blocker" issue, '
                "the run will be rejected and require rework.",
            )
            if manager_verdict:
                verdicts.append(manager_verdict)
                overall = bool(manager_verdict.get("approved", False))
            else:
                overall = tier1_approved
        else:
            overall = tier1_approved

        # Collect issues for rework
        all_issues: list[dict] = []
        all_criteria: dict = {}
        for v in verdicts:
            all_issues.extend(v.get("issues", []) or [])
            for cid, cr in (v.get("criteria_results") or {}).items():
                all_criteria[cid] = cr

        # Emit validation result
        await self.sio.emit("validation_complete", {
            "overallApproved": overall,
            "verdicts": verdicts,
        }, room=self._room)

        # Write verdicts to disk
        try:
            val_dir = self._cwd / ".taskmesh"
            val_dir.mkdir(parents=True, exist_ok=True)
            (val_dir / "validation.json").write_text(
                json.dumps({"overallApproved": overall, "verdicts": verdicts}, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass

        if not overall and self._rework_iteration < MAX_REWORK_ITERATIONS:
            # Create rework tasks via Manager
            issue_text = "\n".join(
                f"[{i.get('severity', 'minor')}] {i.get('description', '')}"
                for i in all_issues
            )
            rework_brief = (
                f"Original brief: {brief}\n\n"
                f"Validation found these issues that need fixing:\n{issue_text}\n\n"
                "Create a new task plan addressing ONLY these issues. "
                "Return valid JSON with tasks."
            )
            await self._manager_create_task_plan(
                rework_brief, [], self._build_upload_manifest_context(),
                extra_context=f"Rework iteration {self._rework_iteration + 1}/{MAX_REWORK_ITERATIONS}",
            )
            await self.sio.emit("rework_needed", {
                "issues": all_issues,
                "reworkTaskCount": len(await self._task_list.all_tasks()),
            }, room=self._room)
            await self._clog("rework_needed", f"Rework iteration {self._rework_iteration + 1}: {len(all_issues)} issues")

        return overall

    def _build_validation_prompt(
        self, brief: str, tasks: list[dict],
        files_written: list[str], role_instruction: str,
    ) -> str:
        """Build a validation prompt for a single agent."""
        task_lines: list[str] = []
        for t in tasks:
            agent = t.get("assigned_to") or "unassigned"
            output = ", ".join(t.get("output_files", [])[:5]) or "none"
            task_lines.append(
                f"  [{t['status']}] {t['id']} — {t['title']} (by {agent}, output: {output})"
            )

        return (
            f"Project brief: {brief[:500]}\n\n"
            f"## Completed Tasks\n" + "\n".join(task_lines) + "\n\n"
            f"## Files Written ({len(files_written)} total)\n"
            + "\n".join(f"  {f}" for f in files_written[:100]) + "\n\n"
            f"## Your Role\n{role_instruction}\n\n"
            "Return ONLY valid JSON — no markdown, no code fences:\n\n"
            '{"approved": true/false, "summary": "<1-3 sentences>", '
            '"issues": [{"severity": "blocker"|"major"|"minor", "description": "..."}], '
            '"criteria_results": {"<criterion_id>": {"met": true/false, "note": "..."}}}'
        )

    @staticmethod
    def _parse_verdict(raw: str) -> dict | None:
        """Parse validation JSON from agent output. Returns None on failure."""
        json_match = re.search(r'\{.*\}', raw, re.DOTALL)
        if not json_match:
            return None
        try:
            return json.loads(json_match.group())
        except json.JSONDecodeError:
            return None

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
            task = await self._task_list.claim_task(agent_id)
            if task is None:
                if await self._task_list.is_all_done():
                    break
                await asyncio.sleep(1)
                continue

            task_id = task["id"]
            await self._emit_agent(agent_id, "coding")
            await self._emit_log(agent_id, f"Claimed: {task['title']}")
            await self._clog("task_claimed", f"{agent_id} claimed '{task['title']}'", {
                "agent": agent_id, "task": task_id,
            })

            await self._task_list.start_task(task_id, agent_id)

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

            # Planner spec references (Stage 2 output)
            if self._plan_artifacts:
                plan_refs = "\n".join(
                    f"  .taskmesh/plans/{aid}.md"
                    for aid in self._plan_artifacts
                )
                context_parts.append(
                    f"Planning references — read these spec files if relevant:\n{plan_refs}"
                )

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
            asyncio.create_task(self._emit_thinking(agent_id, _exec_res.get("thinking_content", "")))
            _task_id_int = task["id"] if isinstance(task.get("id"), int) else None

            # Run with search blocks — returns final content after all searches resolved
            result = await self._run_with_search(
                agent, prompt, agent_id, task_id=_task_id_int, max_rounds=3,
            )

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
            await self._task_list.complete_task(task_id, agent_id, written)
            await self._emit_task_done(task_id)
            asyncio.create_task(self._write_current_md_snapshot())

            await self._emit_agent(agent_id, "done")
            await self._clog("task_completed", f"{agent_id} completed '{task['title']}'", {
                "agent": agent_id, "task": task_id, "files": len(written),
            })

            await asyncio.sleep(0.3)

        await self._emit_agent(agent_id, "idle")
        await self._emit_log(agent_id, "Agent finished — no more tasks")
        await self._clog("agent_finished", f"{agent_id} exited agent loop")
