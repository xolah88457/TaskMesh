"""
SharedTaskList — DB-backed task queue with in-memory fallback.

When DATABASE_URL is set, tasks are persisted to the Postgres `tasks` table
with atomic claiming via SELECT ... FOR UPDATE SKIP LOCKED.
When the DB is unavailable, falls back to an in-memory list behind an
asyncio.Lock for safe single-process coordination (dev mode).

The public API is async. The orchestrator always awaits calls regardless
of which storage back the callers use.

Phase A of the agent-harness-kit review: replaces the old in-memory-only version.
"""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Callable
from copy import deepcopy
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import select, update


class SharedTaskList:
    """Async task queue for atomic multi-agent coordination.

    Constructor takes a run_id (UUID string) and a session_factory (the same
    ``get_session`` async context manager used everywhere in the backend).
    When the factory yields None (DATABASE_URL unset), all operations fall
    back to an in-memory list protected by an asyncio lock.
    """

    def __init__(
        self,
        run_id: str,
        session_factory: Callable[..., Any],
    ) -> None:
        self._run_id = run_id
        self._sessions = session_factory
        self._memory: list[dict] = []       # used only when DB unavailable
        self._order: int = 0
        self._dirty: bool = False
        self._lock = asyncio.Lock()          # protects _memory in dev mode

    # ── public API ────────────────────────────────────────────────────────

    async def add_task(
        self,
        title: str,
        description: str = "",
        created_by: str = "manager",
        status: str = "available",
        acceptance: list[str] | None = None,
    ) -> dict:
        self._order += 1
        self._dirty = True
        # Fallback id used when no DB is configured. Includes a strictly
        # increasing counter to guarantee uniqueness within a run.
        fallback_id = f"mem-{self._order}"

        now = datetime.now(timezone.utc).isoformat()
        task: dict = {
            "id": fallback_id, "order": self._order,
            "title": title, "description": description,
            "status": status, "assigned_to": None,
            "created_by": created_by, "output_files": [],
            "created_at": now, "started_at": None, "completed_at": None,
            "acceptance": acceptance or [],
        }
        async with self._sessions() as session:
            if session is not None:
                from ..db.models import Task as TaskModel
                from ..db.models import TaskAcceptance
                db_task = TaskModel(
                    run_id=self._run_id,
                    title=task["title"],
                    description=task.get("description", ""),
                    status=task["status"],
                    assigned_to=task.get("assigned_to"),
                    created_by=task.get("created_by", "manager"),
                )
                session.add(db_task)
                await session.flush()  # get task.id
                # Use the DB id as the canonical id. Without this the in-memory
                # copy and the DB row had different ids and complete_task /
                # start_task lookups would silently miss when the orchestrator
                # mixed memory-cached and DB-claimed task handles.
                task["id"] = str(db_task.id)
                for i, criterion in enumerate(acceptance or [], start=1):
                    session.add(TaskAcceptance(
                        task_id=str(db_task.id),
                        run_id=self._run_id,
                        criterion=criterion,
                        met=False,
                        met_order=i,
                    ))
        async with self._lock:
            self._memory.append(task)
        return task

    async def claim_task(self, agent_id: str) -> dict | None:
        async with self._sessions() as session:
            if session is not None:
                task = await self._claim_db(session, agent_id)
                if task is not None:
                    self._dirty = True
                    return task
        async with self._lock:
            task = self._claim_memory(agent_id)
            if task is not None:
                self._dirty = True
            return task

    async def start_task(self, task_id: str, agent_id: str) -> bool:
        async with self._sessions() as session:
            if session is not None and task_id.isdigit():
                ok = await self._start_db(session, int(task_id), agent_id)
                if ok:
                    self._dirty = True
                    return True
        async with self._lock:
            return self._start_memory(task_id, agent_id)

    async def complete_task(
        self, task_id: str, agent_id: str,
        output_files: list[str] | None = None,
    ) -> bool:
        async with self._sessions() as session:
            if session is not None and task_id.isdigit():
                ok = await self._complete_db(session, int(task_id), agent_id, output_files)
                if ok:
                    self._dirty = True
                    return True
        async with self._lock:
            return self._complete_memory(task_id, agent_id, output_files)

    async def block_task(self, task_id: str, reason: str = "") -> bool:
        self._dirty = True
        async with self._lock:
            return self._block_memory(task_id, reason)

    async def fail_task(self, task_id: str, error: str = "") -> bool:
        self._dirty = True
        async with self._lock:
            return self._fail_memory(task_id, error)

    async def get_task(self, task_id: str) -> dict | None:
        async with self._sessions() as session:
            if session is not None and task_id.isdigit():
                t = await self._get_db(session, int(task_id))
                if t is not None:
                    return t
        for t in self._memory:
            if t["id"] == task_id:
                return deepcopy(t)
        return None

    async def all_tasks(self) -> list[dict]:
        async with self._sessions() as session:
            if session is not None:
                tasks = await self._all_db(session)
                if tasks:
                    return tasks
        return deepcopy(self._memory)

    async def summary(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for t in await self.all_tasks():
            s = t["status"]
            counts[s] = counts.get(s, 0) + 1
        return counts

    async def snapshot(self) -> list[dict]:
        return deepcopy(await self.all_tasks())

    def is_dirty(self) -> bool:
        return self._dirty

    def mark_clean(self) -> None:
        self._dirty = False

    async def is_all_done(self) -> bool:
        tasks = await self.all_tasks()
        return len(tasks) > 0 and all(
            t["status"] in ("completed", "failed", "blocked") for t in tasks
        )

    def clear(self) -> None:
        self._memory.clear()
        self._order = 0
        self._dirty = False

    # ── persistence ───────────────────────────────────────────────────────

    def save_to_disk(self, run_id: str, cwd: Path | None = None) -> None:
        base = cwd or Path(os.getcwd())
        dir_path = base / ".taskmesh"
        dir_path.mkdir(parents=True, exist_ok=True)
        file_path = dir_path / f"tasks-{run_id}.json"
        # Sync version of all_tasks — just use memory for crash snapshots
        data = deepcopy(self._memory)
        file_path.write_text(json.dumps(data, indent=2, ensure_ascii=False))

    def load_from_disk(self, run_id: str, cwd: Path | None = None) -> bool:
        base = cwd or Path(os.getcwd())
        file_path = base / ".taskmesh" / f"tasks-{run_id}.json"
        if not file_path.exists():
            return False
        try:
            self._memory = json.loads(file_path.read_text())
            self._order = len(self._memory)
            self._dirty = False
            return True
        except (json.JSONDecodeError, OSError):
            return False

    # ── acceptance criteria ─────────────────────────────────────────────────

    async def get_acceptance(self, task_id: str) -> list[dict]:
        """Return acceptance criteria rows for a task."""
        async with self._sessions() as session:
            if session is not None:
                return await self._get_acceptance_db(session, task_id)
        for t in self._memory:
            if t["id"] == task_id:
                return [
                    {"id": f"{task_id}_c{i+1}", "criterion": c, "met": False,
                     "met_order": i + 1, "checked_by": None, "checked_at": None}
                    for i, c in enumerate(t.get("acceptance", []))
                ]
        return []

    async def set_acceptance_met(self, criterion_id: str, met: bool,
                                  checked_by: str = "reviewer") -> bool:
        """Flip a single criterion row to met/unmet and stamp checked_by/checked_at."""
        now = datetime.now(timezone.utc).isoformat()
        async with self._sessions() as session:
            if session is not None:
                return await self._set_acceptance_met_db(
                    session, criterion_id, met, checked_by, now)
        return self._set_acceptance_met_memory(criterion_id, met, checked_by, now)

    async def _get_acceptance_db(self, session, task_id: str) -> list[dict]:
        from ..db.models import TaskAcceptance
        result = await session.execute(
            select(TaskAcceptance).where(
                TaskAcceptance.run_id == self._run_id,
                TaskAcceptance.task_id == task_id,
            ).order_by(TaskAcceptance.met_order)
        )
        return [
            {
                "id": str(row.id),
                "criterion": row.criterion,
                "met": bool(row.met),
                "met_order": row.met_order,
                "checked_by": row.checked_by,
                "checked_at": row.checked_at.isoformat() if row.checked_at else None,
            }
            for row in result.scalars().all()
        ]

    async def _set_acceptance_met_db(self, session, criterion_id: str,
                                      met: bool, checked_by: str,
                                      checked_at: str) -> bool:
        from ..db.models import TaskAcceptance
        from datetime import datetime as dt
        result = await session.execute(
            update(TaskAcceptance)
            .where(TaskAcceptance.id == int(criterion_id))
            .values(
                met=met,
                checked_by=checked_by,
                checked_at=dt.fromisoformat(checked_at),
            )
        )
        return result.rowcount > 0

    def _set_acceptance_met_memory(self, criterion_id: str, met: bool,
                                    checked_by: str, checked_at: str) -> bool:
        for t in self._memory:
            for i, _ in enumerate(t.get("acceptance", [])):
                cid = f"{t['id']}_c{i + 1}"
                if cid == criterion_id:
                    t.setdefault("_acceptance_met", {})
                    t["_acceptance_met"][str(i)] = {
                        "met": met, "checked_by": checked_by, "checked_at": checked_at,
                    }
                    self._dirty = True
                    return True
        return False

    # ── stale-claim recovery ──────────────────────────────────────────────

    async def recover_stale_claims(self, max_age_seconds: int = 300) -> int:
        """Reset tasks stuck in 'claimed' state for longer than max_age_seconds.

        Now that `_claim_db` leaves `started_at = NULL` (start_task sets it),
        a crashed agent that claimed but never started would have NULL there.
        We treat any "claimed" row with a NULL started_at as immediately stale
        once its claim is older than the cutoff via created_at.
        """
        from sqlalchemy import or_, and_
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=max_age_seconds)
        async with self._sessions() as session:
            if session is not None:
                from ..db.models import Task as TaskModel
                result = await session.execute(
                    update(TaskModel)
                    .where(
                        TaskModel.run_id == self._run_id,
                        TaskModel.status == "claimed",
                        or_(
                            TaskModel.started_at < cutoff,
                            and_(
                                TaskModel.started_at.is_(None),
                                TaskModel.created_at < cutoff,
                            ),
                        ),
                    )
                    .values(status="available", assigned_to=None, started_at=None)
                )
                if result.rowcount:
                    self._dirty = True
                return result.rowcount or 0
        return 0

    # ── DB helpers ────────────────────────────────────────────────────────

    async def _claim_db(self, session, agent_id: str) -> dict | None:
        from ..db.models import Task as TaskModel
        result = await session.execute(
            select(TaskModel)
            .where(TaskModel.run_id == self._run_id, TaskModel.status == "available")
            .order_by(TaskModel.id)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None
        # Mark "claimed" not "in_progress". The orchestrator immediately follows
        # with start_task() which flips claimed → in_progress; that two-step
        # state flow mirrors the in-memory path and matches the comment block
        # at the top of `add_task` (available → claimed → in_progress → done).
        row.status = "claimed"
        row.assigned_to = agent_id
        return _row_to_task(row)

    def _claim_memory(self, agent_id: str) -> dict | None:
        for t in self._memory:
            if t["status"] == "available":
                t["status"] = "claimed"
                t["assigned_to"] = agent_id
                self._dirty = True
                return deepcopy(t)
        return None

    async def _start_db(self, session, task_id: int, agent_id: str) -> bool:
        from ..db.models import Task as TaskModel
        result = await session.execute(
            update(TaskModel)
            .where(
                TaskModel.run_id == self._run_id, TaskModel.id == task_id,
                TaskModel.status == "claimed", TaskModel.assigned_to == agent_id,
            )
            .values(status="in_progress", started_at=datetime.now(timezone.utc))
        )
        return result.rowcount > 0

    def _start_memory(self, task_id: str, agent_id: str) -> bool:
        for t in self._memory:
            if t["id"] == task_id and t["assigned_to"] == agent_id and t["status"] == "claimed":
                t["status"] = "in_progress"
                t["started_at"] = datetime.now(timezone.utc).isoformat()
                self._dirty = True
                return True
        return False

    async def _complete_db(self, session, task_id: int, agent_id: str,
                            output_files: list[str] | None) -> bool:
        from ..db.models import Task as TaskModel
        values = {"status": "completed", "completed_at": datetime.now(timezone.utc)}
        if output_files:
            values["output_files"] = json.dumps(output_files)
        result = await session.execute(
            update(TaskModel)
            .where(
                TaskModel.run_id == self._run_id, TaskModel.id == task_id,
                TaskModel.assigned_to == agent_id,
            )
            .values(**values)
        )
        return result.rowcount > 0

    def _complete_memory(self, task_id: str, agent_id: str,
                          output_files: list[str] | None = None) -> bool:
        for t in self._memory:
            if t["id"] == task_id and t["assigned_to"] == agent_id:
                t["status"] = "completed"
                t["completed_at"] = datetime.now(timezone.utc).isoformat()
                if output_files:
                    t["output_files"] = list(output_files)
                self._dirty = True
                return True
        return False

    def _block_memory(self, task_id: str, reason: str = "") -> bool:
        for t in self._memory:
            if t["id"] == task_id:
                t["status"] = "blocked"
                if reason:
                    t["description"] = (t.get("description", "") +
                                        f" [BLOCKED: {reason}]").strip()
                self._dirty = True
                return True
        return False

    def _fail_memory(self, task_id: str, error: str = "") -> bool:
        for t in self._memory:
            if t["id"] == task_id:
                t["status"] = "failed"
                t["completed_at"] = datetime.now(timezone.utc).isoformat()
                if error:
                    t["description"] = (t.get("description", "") +
                                        f" [FAILED: {error}]").strip()
                self._dirty = True
                return True
        return False

    async def _get_db(self, session, task_id: int) -> dict | None:
        from ..db.models import Task as TaskModel
        result = await session.execute(
            select(TaskModel).where(TaskModel.run_id == self._run_id, TaskModel.id == task_id)
        )
        row = result.scalar_one_or_none()
        return _row_to_task(row) if row else None

    async def _all_db(self, session) -> list[dict]:
        from ..db.models import Task as TaskModel
        result = await session.execute(
            select(TaskModel).where(TaskModel.run_id == self._run_id).order_by(TaskModel.id)
        )
        return [_row_to_task(r) for r in result.scalars().all()]


# ── helpers ──────────────────────────────────────────────────────────────

def _row_to_task(row) -> dict:
    return {
        "id": str(row.id),
        "order": row.id,
        "title": row.title,
        "description": row.description or "",
        "status": row.status,
        "assigned_to": row.assigned_to,
        "created_by": row.created_by or "manager",
        "output_files": json.loads(row.output_files) if row.output_files else [],
        "created_at": row.created_at.isoformat() if row.created_at else "",
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "completed_at": row.completed_at.isoformat() if row.completed_at else None,
    }
