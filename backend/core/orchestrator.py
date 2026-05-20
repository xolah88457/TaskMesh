"""
Multi-agent orchestrator — four-phase pipeline + coordination layer.

Phases:
  0  Manager selects which agents are needed for this brief.
  1  Planners (webdev, researcher, …) draft specs in parallel.
  2  Manager synthesises specs into a JSON task breakdown.
  3  Executors run concurrently; each writes [FILE:…] blocks to PROJECT_DIR.
  4  Reviewer checks all output; sends feedback if revision needed (1 retry).

Coordination improvements:
  - FileLockRegistry  : exclusive file ownership per agent during a run.
  - AgentMailbox      : typed async message store for cross-agent comms.
  - CoordinatorLog    : structured log of every coordinator decision.
  - Auto-commit       : git commit after each executor task's files land.
"""

from __future__ import annotations

import asyncio
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

import socketio

from ..agents.base_agent import BaseAgent
from ..agents.manager_agent import ManagerAgent
from ..core.config_loader import ProjectConfig, get_project_dir, load_config
from ..db.session import get_session
from ..db.models import Run, RunFile, UserUsage

# ─── regex for [FILE: path] blocks ────────────────────────────────────────────
_FILE_BLOCK_RE = re.compile(r'\[FILE:\s*([^\]\n]+)\]\n?(.*?)\n?\[/FILE\]', re.DOTALL)

_FILE_FORMAT_INSTRUCTION = """

For every file you create or modify, output it using this exact format — no exceptions:

[FILE: relative/path/from/project/root]
complete file contents here
[/FILE]

Rules:
- Paths are relative to the project root (e.g. src/app.py, tests/test_auth.py, README.md)
- Write COMPLETE, RUNNABLE code — no pseudocode, no "# TODO implement", no "..." placeholders
- Multiple files are allowed; write each as its own [FILE]...[/FILE] block
- Do not truncate or summarise — write the full file every time
"""


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

    Decision types: task_created, agent_assigned, file_locked, file_conflict,
                    blocker_raised, reviewer_started, reviewer_approved,
                    reviewer_rejected, retry_started, run_complete.
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


# ─── agent role helpers ────────────────────────────────────────────────────────

def _is_planner(agent_cfg: dict) -> bool:
    return bool(agent_cfg.get("planner", False))

def _is_reviewer(agent_cfg: dict) -> bool:
    return (
        agent_cfg.get("id") == "reviewer"
        or agent_cfg.get("role", "").lower() in ("reviewer", "code reviewer", "code review")
    )

def _is_scout(agent_cfg: dict) -> bool:
    return (
        agent_cfg.get("id") == "scout"
        or agent_cfg.get("role", "").lower() in ("scout", "researcher", "tech lead")
    )


# ─── misc helpers ──────────────────────────────────────────────────────────────

def _now() -> str:
    t = datetime.now()
    return f"{t.minute:02d}:{t.second:02d}"


def _truncate(s: str, n: int = 100) -> str:
    s = s.strip()
    return s[:n] + "…" if len(s) > n else s


def _build_manager_input(brief: str, planner_outputs: dict[str, str]) -> str:
    if not planner_outputs:
        return brief
    sections = "\n\n".join(
        f"== {aid.upper()} SPEC ==\n{output}"
        for aid, output in planner_outputs.items()
    )
    return (
        f"Project brief: {brief}\n\n"
        "The following planning specialists have already analysed this brief "
        "and submitted their specs. Use their output to produce a more informed task breakdown.\n\n"
        f"{sections}"
    )


# ─── orchestrator ─────────────────────────────────────────────────────────────

class Orchestrator:
    def __init__(self, sio: socketio.AsyncServer, config: ProjectConfig):
        self.sio = sio
        self.config = config
        self._cwd = get_project_dir()
        self._agents: dict[str, BaseAgent] = {}
        self._file_poll_task: asyncio.Task | None = None
        self._run_task: asyncio.Task | None = None

        # coordination state — cleared at start of each run
        self._file_locks   = FileLockRegistry()
        self._mailbox      = AgentMailbox()
        self._coord_log    = CoordinatorLog()

        # per-run execution tracking
        self._executor_outputs: dict[str, str] = {}   # agent_id -> raw LLM output
        self._executor_files:   dict[str, list[str]] = {}  # agent_id -> [paths]

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
                model=a.get("model", "meta/llama-3.1-8b-instruct"),
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
        if self._run_task and not self._run_task.done():
            self._run_task.cancel()

    # ── emit helpers ───────────────────────────────────────────────────────────

    async def _emit_agent(self, agent_id: str, status: str) -> None:
        await self.sio.emit("agent_update", {"agentId": agent_id, "status": status})

    async def _emit_log(self, agent_id: str, message: str) -> None:
        await self.sio.emit("log_update", {
            "time":    _now(),
            "agentId": agent_id,
            "message": _truncate(message),
        })

    async def _emit_task_done(self, task_id: str) -> None:
        await self.sio.emit("task_update", {"taskId": task_id})

    async def _emit_terminal(self, line: str) -> None:
        await self.sio.emit("terminal_line", {"line": _truncate(line, 120)})

    async def _emit_files(self, count: int, filenames: list) -> None:
        await self.sio.emit("file_update", {"count": count, "files": filenames})

    async def _emit_coordinator_log(self, entry: dict) -> None:
        await self.sio.emit("coordinator_log", {"entry": entry})

    async def _emit_mailbox_msg(self, msg: dict) -> None:
        await self.sio.emit("mailbox_msg", msg)

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
        """Conventional commit after each executor task (non-blocking if git fails)."""
        if not files:
            return
        try:
            # Stage only the files this agent wrote
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

    async def _write_agent_files(
        self, agent_id: str, output: str, run_id: str = ""
    ) -> list[str]:
        written: list[str] = []

        for match in _FILE_BLOCK_RE.finditer(output):
            rel_path = match.group(1).strip().lstrip("/")
            content  = match.group(2)

            # Guard against path traversal
            target = (self._cwd / rel_path).resolve()
            if not str(target).startswith(str(self._cwd.resolve())):
                await self._emit_terminal(f"  [skipped] unsafe path: {rel_path}")
                continue

            # File-lock check
            acquired, holder = self._file_locks.acquire(rel_path, agent_id)
            if not acquired:
                # Conflict — log it, take over (last-write wins)
                await self._emit_terminal(
                    f"  [conflict] {rel_path} held by {holder}, {agent_id} taking over"
                )
                await self.sio.emit("file_conflict", {
                    "path": rel_path,
                    "requestingAgent": agent_id,
                    "holdingAgent": holder,
                })
                await self._clog("file_conflict", f"{agent_id} overwrote {rel_path} (was {holder})", {
                    "path": rel_path, "winner": agent_id, "loser": holder or "",
                })
                self._file_locks.force_acquire(rel_path, agent_id)
            else:
                await self.sio.emit("file_locked", {"path": rel_path, "agentId": agent_id})

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
            await self.sio.emit("file_unlocked", {"path": path, "agentId": agent_id})

        return written

    # ── credit deduction (fire-and-forget) ────────────────────────────────────

    async def _deduct_credits(self, result: dict) -> None:
        """Deduct token cost from UserCredits after an agent call. Never raises."""
        user_id = getattr(self, "_current_user_id", "anonymous")
        if user_id == "anonymous":
            return
        try:
            from ..api.billing import calc_cost_cents
            from ..db.models import UserCredits
            cost = calc_cost_cents(
                result.get("model", ""),
                result.get("prompt_tokens", 0),
                result.get("completion_tokens", 0),
            )
            if cost <= 0:
                return
            async with get_session() as session:
                if session is None:
                    return
                creds = await session.get(UserCredits, user_id)
                if creds is not None:
                    creds.balance_cents = max(0, creds.balance_cents - cost)
                    creds.updated_at    = datetime.now(timezone.utc)
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
    ) -> None:
        self._run_task = asyncio.current_task()
        self._current_user_id = user_id
        self._agent_limit     = agent_limit
        self._plan            = plan
        self._api_key         = api_key
        cancelled = False
        run_id    = str(uuid.uuid4())
        year_month = datetime.now(timezone.utc).strftime("%Y-%m")

        # Clear per-run coordination state
        self._file_locks.clear()
        self._mailbox.clear()
        self._coord_log.clear()
        self._executor_outputs.clear()
        self._executor_files.clear()

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

            # Apply user-scoped API key (overrides env var / config file key)
            if api_key:
                self.config.provider.apiKey = api_key

            # Apply Starter plan model restrictions (Option B)
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
            })

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

            await self.sio.emit("run_done", {})

        except asyncio.CancelledError:
            self._stop_file_polling()
            async with get_session() as session:
                if session is not None:
                    run_row = await session.get(Run, run_id)
                    if run_row is not None:
                        run_row.status = "cancelled"
                        run_row.finished_at = datetime.now(timezone.utc)
            await self.sio.emit("run_done", {})

        except Exception as e:
            self._stop_file_polling()
            async with get_session() as session:
                if session is not None:
                    run_row = await session.get(Run, run_id)
                    if run_row is not None:
                        run_row.status = "error"
                        run_row.finished_at = datetime.now(timezone.utc)
            await self._emit_terminal(f"[error] {e}")
            await self.sio.emit("run_done", {})

        finally:
            self._run_task = None
            self._file_locks.clear()

    # ── Phase 0: manager selects agents ───────────────────────────────────────

    async def _select_agents(
        self, brief: str, non_mgr: list[dict]
    ) -> tuple[list[str], str]:
        agent_list = "\n".join(
            f'- {a["id"]}: {a.get("role", a["id"])} ({"Planner" if a.get("planner") else "Executor"})'
            for a in non_mgr
        )
        prompt = (
            f"Project brief: {brief}\n\n"
            f"Available agents:\n{agent_list}\n\n"
            "Select only the agents needed. Return ONLY valid JSON:\n"
            '{"selected":["id1","id2"],"reason":"one sentence why"}'
        )

        mgr_cfg = next((a for a in self.config.agents if a.get("id") == "manager"), {})
        selector = BaseAgent(
            name="selector",
            model=mgr_cfg.get("model", "deepseek-ai/deepseek-v4-pro"),
            system_prompt=(
                "You are a project coordinator. Given a project brief and a list of agents, "
                "select only the agents actually needed. Return ONLY valid JSON with keys "
                "'selected' (array of agent IDs from the list) and 'reason' (one sentence). "
                "Be selective — small projects don't need every specialist."
            ),
            base_url=self.config.provider.baseURL,
            api_key=self.config.provider.apiKey,
            temperature=0.3,
            max_tokens=256,
        )

        _sel_res = await selector.run(prompt)
        asyncio.create_task(self._deduct_credits(_sel_res))
        raw = _sel_res["content"]
        json_match = re.search(r'\{.*\}', raw, re.DOTALL)
        if json_match:
            try:
                data     = json.loads(json_match.group())
                selected = data.get("selected", [])
                reason   = data.get("reason", "")
                valid_ids = {a["id"] for a in non_mgr}
                selected  = [s for s in selected if s in valid_ids]
                if selected:
                    return selected, reason
            except json.JSONDecodeError:
                pass

        return [a["id"] for a in non_mgr], "Using full team for this project."

    # ── three+one-phase pipeline ───────────────────────────────────────────────

    async def _run_pipeline(self, brief: str, run_id: str = "") -> None:
        # Separate reviewer from the selectable pool — it always runs Phase 4 if present
        reviewer_cfg = next(
            (a for a in self.config.agents if _is_reviewer(a)), None
        )
        non_mgr_all = [
            a for a in self.config.agents
            if a.get("id") != "manager" and not _is_reviewer(a)
        ]

        await self._emit_terminal("$ agent-team start")

        # ── Phase 0: manager selects the right team ────────────────────────────
        await self._emit_agent("manager", "thinking")
        await self._emit_log("manager", "Analyzing project brief — selecting the right team…")
        await self._clog("phase_start", "Phase 0: agent selection", {"brief": brief[:120]})

        selected_ids, reason = await self._select_agents(brief, non_mgr_all)

        # Apply Starter plan agent cap (3 max)
        agent_limit = getattr(self, "_agent_limit", None)
        if agent_limit is not None and len(selected_ids) > agent_limit:
            selected_ids = selected_ids[:agent_limit]
            reason += f" (capped at {agent_limit} for Starter plan)"

        await self.sio.emit("agents_selected", {"agentIds": selected_ids})
        await self._emit_log("manager", f"Team: {', '.join(selected_ids)}. {reason}")
        await self._emit_agent("manager", "idle")
        await self._clog("agent_assigned", f"Selected: {', '.join(selected_ids)}", {"reason": reason})

        non_mgr   = [a for a in non_mgr_all if a["id"] in selected_ids]
        planners  = [a for a in non_mgr if _is_planner(a)]
        executors = [a for a in non_mgr if not _is_planner(a)]

        # ── Phase 1: planners draft their specs independently ──────────────────
        planner_outputs: dict[str, str] = {}
        if planners:
            await self._emit_log("manager", f"Phase 1 — {len(planners)} planner(s) drafting specs in parallel…")
            await self._clog("phase_start", f"Phase 1: {len(planners)} planners running")
            planner_outputs = await self._run_planners(brief, planners)
            await self._emit_log("manager", "All planner specs received. Starting synthesis…")

        # ── Phase 2: manager synthesises plans into task breakdown ─────────────
        await self._emit_agent("manager", "thinking")
        await self._emit_log("manager", "Analysing brief and synthesising plans…")
        await self._clog("phase_start", "Phase 2: manager synthesis")

        manager_input = _build_manager_input(brief, planner_outputs)
        _mgr_res = await self.manager.run(manager_input)
        asyncio.create_task(self._deduct_credits(_mgr_res))
        raw = _mgr_res["content"]

        json_match = re.search(r'\{.*\}', raw, re.DOTALL)
        plan: dict = {}
        if json_match:
            try:
                plan = json.loads(json_match.group())
            except json.JSONDecodeError:
                pass

        feature  = plan.get("feature",  "")
        analysis = plan.get("analysis", "Decomposing project into subtasks…")
        tasks    = plan.get("tasks", [])

        await self._emit_log("manager", _truncate(analysis))

        if feature:
            await self.sio.emit("feature_set", {"feature": feature})
            await self._emit_log("manager", f"Operation: {feature}")

        if tasks:
            await self.sio.emit("tasks_init", {"tasks": tasks})
            await self._clog("task_created", f"Created {len(tasks)} tasks: {[t.get('title','') for t in tasks]}")

        await self._emit_agent("manager", "delegating")
        await self._emit_log("manager", f"Delegating {len(tasks)} tasks across {len(executors)} executor(s).")

        mgr_task = next((t for t in tasks if t.get("tag") == "MGR"), None)
        if mgr_task:
            await self._emit_task_done(mgr_task["id"])

        await self._emit_agent("manager", "done")

        for a in executors:
            short = a["id"].upper()[:3]
            agent_tasks = [t for t in tasks if t.get("tag") == short]
            if agent_tasks:
                summary = "; ".join(t["title"] for t in agent_tasks)
                await self._bus_send("manager", a["id"], f"Your tasks: {summary}")
                await self._clog("agent_assigned", f"Assigned to {a['id']}: {summary}", {"agent": a["id"]})

        # ── Phase 3: executors run concurrently ────────────────────────────────
        if executors:
            await self._emit_log("manager", f"Phase 3 — launching {len(executors)} executor(s)…")
            await self._clog("phase_start", f"Phase 3: {len(executors)} executors running concurrently")

        async def staggered(agent_cfg: dict, delay: float) -> None:
            await asyncio.sleep(delay)
            await self._run_executor(agent_cfg, tasks, brief, planner_outputs, run_id)

        await asyncio.gather(*(staggered(a, i * 0.5) for i, a in enumerate(executors)))

        # Persist which agents were selected
        async with get_session() as session:
            if session is not None:
                run_row = await session.get(Run, run_id)
                if run_row is not None:
                    run_row.agents_used = json.dumps(selected_ids)

        # ── Phase 4: reviewer quality gate (if reviewer agent present) ─────────
        if reviewer_cfg:
            await self._run_reviewer(reviewer_cfg, brief, tasks, run_id)

    # ── Phase 1: run planners in parallel ─────────────────────────────────────

    async def _run_planners(self, brief: str, planners: list[dict]) -> dict[str, str]:
        results: dict[str, str] = {}

        async def run_one(agent_cfg: dict) -> None:
            agent_id = agent_cfg["id"]
            agent    = self._agents.get(agent_id)
            if not agent:
                return

            await self._emit_agent(agent_id, "thinking")
            await self._emit_log(agent_id, "Drafting planning spec…")

            if _is_scout(agent_cfg):
                prompt = (
                    f"Project brief: {brief}\n\n"
                    "You are a Scout. Research the project context, identify relevant patterns, "
                    "and provide structured findings that will guide the implementation team.\n\n"
                    "Output format (use these exact headers):\n"
                    "## Research Summary\n[key findings — what the brief implies technically]\n\n"
                    "## Relevant Patterns\n[patterns and conventions the team should follow]\n\n"
                    "## Recommendations\n[specific, actionable technical recommendations]\n\n"
                    "## Potential Issues\n[gotchas, edge cases, and risks to watch]\n\n"
                    "Be specific and actionable. Do NOT write implementation code."
                )
            else:
                prompt = (
                    f"Project brief: {brief}\n\n"
                    "Produce your planning spec for this project. "
                    "Be specific, actionable, and stay within your domain. "
                    "Your output will be given to the Manager to build the final task plan."
                )

            _plan_res = await agent.run(prompt)
            asyncio.create_task(self._deduct_credits(_plan_res))
            output = _plan_res["content"]
            results[agent_id] = output

            await self._bus_send(agent_id, "manager", _truncate(output, 120))
            await self._emit_agent(agent_id, "done")
            await self._emit_log(agent_id, "Spec submitted to Manager.")

        await asyncio.gather(*(run_one(a) for a in planners))
        return results

    # ── Phase 3: run a single executor ────────────────────────────────────────

    async def _run_executor(
        self,
        agent_cfg: dict,
        tasks: list,
        brief: str,
        planner_outputs: dict[str, str],
        run_id: str = "",
        retry_for_feedback: bool = False,
    ) -> None:
        agent_id = agent_cfg["id"]
        short    = agent_id.upper()[:3]
        agent    = self._agents.get(agent_id)
        if not agent:
            return

        my_tasks = [t for t in tasks if t.get("tag") == short]
        if not my_tasks:
            return

        await self._emit_agent(agent_id, "thinking")
        log_prefix = "Re-running with reviewer feedback." if retry_for_feedback else f"Received {len(my_tasks)} task(s) from Manager."
        await self._emit_log(agent_id, log_prefix)

        # Build context: brief + planner specs
        context_parts = [f"Project context: {brief[:300]}"]
        if planner_outputs:
            specs = "\n\n".join(
                f"[{aid.upper()} SPEC]\n{_truncate(out, 400)}"
                for aid, out in planner_outputs.items()
            )
            context_parts.append(f"Planning specs from earlier phase:\n{specs}")

        # Include mailbox inbox (e.g. reviewer feedback from previous attempt)
        unread = self._mailbox.unread(agent_id)
        if unread:
            inbox_text = "\n".join(
                f"[{m['type'].upper()} from {m['from']}]: {m['content']}"
                for m in unread
            )
            context_parts.append(f"Messages in your mailbox:\n{inbox_text}")
            if retry_for_feedback:
                await self._emit_log(agent_id, f"Reviewer feedback received — revising output.")

        context = "\n\n".join(context_parts)

        if agent_id not in self._executor_files:
            self._executor_files[agent_id] = []

        for task in my_tasks:
            await self._emit_log(agent_id, f"Working on: {task['title']}")
            await self._emit_agent(agent_id, "coding")

            prompt    = f"Task: {task['title']}\n\n{context}{_FILE_FORMAT_INSTRUCTION}"
            _exec_res = await agent.run(prompt)
            asyncio.create_task(self._deduct_credits(_exec_res))
            result  = _exec_res["content"]
            summary = _truncate(result)

            # Store raw output for reviewer
            self._executor_outputs[agent_id] = result

            # Write files
            written = await self._write_agent_files(agent_id, result, run_id)
            self._executor_files[agent_id].extend(written)

            if written:
                await self._emit_log(agent_id, f"Wrote {len(written)} file(s): {', '.join(written[:3])}")
                count, names = await self._git_status()
                await self._emit_files(count, names)
                # Auto-commit after each task
                await self._auto_commit(agent_id, task["title"], written)

            await self._bus_send(agent_id, "manager", f"Completed '{task['title']}': {summary}")
            await self._emit_task_done(task["id"])
            await asyncio.sleep(0.3)

        await self._emit_agent(agent_id, "done")
        await self._emit_log(agent_id, "All tasks complete.")

    # ── Phase 4: reviewer quality gate ────────────────────────────────────────

    async def _run_reviewer(
        self,
        reviewer_cfg: dict,
        brief: str,
        tasks: list,
        run_id: str,
    ) -> None:
        reviewer = self._agents.get("reviewer")
        if not reviewer:
            return

        await self._emit_agent("reviewer", "thinking")
        await self._emit_log("reviewer", "Phase 4 — reviewing all executor output…")
        await self._clog("reviewer_started", "Phase 4: reviewer beginning quality gate")
        await self.sio.emit("reviewer_started", {})

        review_result = await self._do_review(reviewer, brief, tasks)

        approved    = review_result.get("approved", True)
        summary     = review_result.get("summary", "")
        issues      = review_result.get("issues", [])

        await self._emit_log("reviewer", f"{'APPROVED' if approved else 'NEEDS REVISION'}: {summary}")
        await self.sio.emit("reviewer_result", {
            "approved": approved,
            "summary":  summary,
            "issues":   issues,
        })

        if approved:
            await self._emit_agent("reviewer", "done")
            await self._clog("reviewer_approved", summary)
            self._mailbox.send("reviewer", "manager", summary, "approval")
        else:
            await self._clog("reviewer_rejected", summary, {"issue_count": str(len(issues))})

            # Group issues by responsible agent
            agent_issues: dict[str, list[dict]] = {}
            for issue in issues:
                responsible = issue.get("agent", "")
                if responsible and responsible in self._executor_files:
                    agent_issues.setdefault(responsible, []).append(issue)

            # Send feedback to each affected agent via mailbox
            for agent_id, agent_issue_list in agent_issues.items():
                feedback_lines = [
                    f"- [{i.get('severity','Major')}] {i.get('file','')}: {i.get('issue','')}"
                    for i in agent_issue_list
                ]
                feedback = "Reviewer feedback — please revise:\n" + "\n".join(feedback_lines)
                msg = self._mailbox.send("reviewer", agent_id, feedback, "feedback")
                await self._emit_mailbox_msg(msg)
                await self._emit_log("reviewer", f"Sent feedback to {agent_id} ({len(agent_issue_list)} issue(s))")
                await self._clog("feedback_sent", f"Reviewer sent feedback to {agent_id}", {
                    "agent": agent_id, "issues": str(len(agent_issue_list)),
                })

            # One retry for affected agents
            affected = list(agent_issues.keys())
            if affected:
                await self._emit_log("reviewer", f"Retry: {', '.join(affected)}")
                await self._clog("retry_started", f"Retry for: {', '.join(affected)}")
                await self.sio.emit("reviewer_retry", {"agents": affected})

                # Find the original agent configs
                affected_cfgs = [
                    a for a in self.config.agents
                    if a.get("id") in affected
                ]
                # Re-run the config we have (planner_outputs stored separately)
                # We need to pass the same brief and tasks — use empty planner_outputs for retry
                async def staggered_retry(agent_cfg: dict, delay: float) -> None:
                    await asyncio.sleep(delay)
                    await self._run_executor(
                        agent_cfg, tasks, brief, {},
                        run_id, retry_for_feedback=True,
                    )

                await asyncio.gather(*(staggered_retry(a, i * 0.5) for i, a in enumerate(affected_cfgs)))

            await self._emit_agent("reviewer", "done")
            await self._emit_log("reviewer", "Review cycle complete.")

    async def _do_review(
        self,
        reviewer: BaseAgent,
        brief: str,
        tasks: list,
    ) -> dict:
        """Build reviewer context and call the reviewer model. Returns parsed JSON."""
        # Build file summary (truncated)
        file_sections: list[str] = []
        for agent_id, file_paths in self._executor_files.items():
            for path in file_paths:
                full_path = self._cwd / path
                try:
                    content = full_path.read_text(encoding="utf-8")
                    preview = content[:600] + ("…" if len(content) > 600 else "")
                    file_sections.append(f"[FILE: {path}] (by {agent_id})\n{preview}")
                except OSError:
                    file_sections.append(f"[FILE: {path}] (by {agent_id}) — could not read")

        files_text = "\n\n".join(file_sections) if file_sections else "(no files written)"

        # Build executor summaries (truncated)
        exec_summaries = "\n\n".join(
            f"[{agent_id.upper()} OUTPUT]\n{_truncate(output, 300)}"
            for agent_id, output in self._executor_outputs.items()
        )

        task_list = "\n".join(
            f"- [{t.get('tag','')}] {t.get('title','')} (done={t.get('done',False)})"
            for t in tasks
        )

        prompt = f"""You are reviewing the output of a multi-agent coding run.

Brief: {brief[:400]}

Tasks assigned:
{task_list}

Files written:
{files_text}

Executor summaries:
{exec_summaries or "(none)"}

Review checklist:
1. Do all files contain complete, runnable code (no placeholders, no TODOs, no "...")?
2. Do the files cover all assigned tasks?
3. Are there obvious bugs, missing imports, or broken logic?
4. Are external inputs validated? Are secrets hardcoded?
5. Do the files follow consistent naming and style conventions?

Return ONLY valid JSON — no prose, no markdown fences:
{{
  "approved": true,
  "summary": "one-sentence verdict",
  "issues": []
}}

If issues exist, set approved to false and list them:
{{
  "approved": false,
  "summary": "one-sentence verdict",
  "issues": [
    {{"file": "path/to/file", "issue": "description", "severity": "Blocker|Major|Minor", "agent": "agent_id"}}
  ]
}}
"""
        _rev_res = await reviewer.run(prompt)
        asyncio.create_task(self._deduct_credits(_rev_res))
        raw = _rev_res["content"]

        # Extract JSON
        json_match = re.search(r'\{.*\}', raw, re.DOTALL)
        if json_match:
            try:
                result = json.loads(json_match.group())
                # Validate structure
                result.setdefault("approved", True)
                result.setdefault("summary", "Review complete.")
                result.setdefault("issues", [])
                return result
            except json.JSONDecodeError:
                pass

        # Fallback: if we can't parse JSON, assume approved to avoid blocking the run
        return {"approved": True, "summary": "Review complete (output not parseable).", "issues": []}
