"""
SharedTaskList — in-memory shared task queue for multi-agent coordination.

Agents claim tasks from this list autonomously. The manager creates tasks;
executors claim, execute, and complete them. The orchestrator monitors progress.

Task states:
  pending    → not yet ready for agents to claim
  available  → ready to be claimed
  claimed    → an agent has taken it but not started
  in_progress→ agent is actively working on it
  completed  → agent finished successfully
  blocked    → agent hit a blocker (needs coordinator intervention)
  failed     → agent could not complete the task
"""

from __future__ import annotations

import json
import os
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path


class SharedTaskList:
    def __init__(self) -> None:
        self._tasks: list[dict] = []
        self._order: int = 0

    def add_task(
        self,
        title: str,
        description: str = "",
        created_by: str = "manager",
        status: str = "available",
    ) -> dict:
        self._order += 1
        task: dict = {
            "id": str(uuid.uuid4())[:8],
            "order": self._order,
            "title": title,
            "description": description,
            "status": status,
            "assigned_to": None,
            "created_by": created_by,
            "output_files": [],
            "created_at": datetime.now(timezone.utc).isoformat(),
            "started_at": None,
            "completed_at": None,
        }
        self._tasks.append(task)
        return task

    def claim_task(self, agent_id: str) -> dict | None:
        for t in self._tasks:
            if t["status"] == "available":
                t["status"] = "claimed"
                t["assigned_to"] = agent_id
                return deepcopy(t)
        return None

    def start_task(self, task_id: str, agent_id: str) -> bool:
        for t in self._tasks:
            if t["id"] == task_id and t["assigned_to"] == agent_id and t["status"] == "claimed":
                t["status"] = "in_progress"
                t["started_at"] = datetime.now(timezone.utc).isoformat()
                return True
        return False

    def complete_task(self, task_id: str, agent_id: str, output_files: list[str] | None = None) -> bool:
        for t in self._tasks:
            if t["id"] == task_id and t["assigned_to"] == agent_id:
                t["status"] = "completed"
                t["completed_at"] = datetime.now(timezone.utc).isoformat()
                if output_files:
                    t["output_files"] = list(output_files)
                return True
        return False

    def block_task(self, task_id: str, reason: str = "") -> bool:
        for t in self._tasks:
            if t["id"] == task_id:
                t["status"] = "blocked"
                if reason:
                    t["description"] = (t.get("description", "") + f" [BLOCKED: {reason}]").strip()
                return True
        return False

    def fail_task(self, task_id: str, error: str = "") -> bool:
        for t in self._tasks:
            if t["id"] == task_id:
                t["status"] = "failed"
                t["completed_at"] = datetime.now(timezone.utc).isoformat()
                if error:
                    t["description"] = (t.get("description", "") + f" [FAILED: {error}]").strip()
                return True
        return False

    def get_task(self, task_id: str) -> dict | None:
        for t in self._tasks:
            if t["id"] == task_id:
                return deepcopy(t)
        return None

    def all_tasks(self) -> list[dict]:
        return deepcopy(self._tasks)

    def summary(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for t in self._tasks:
            s = t["status"]
            counts[s] = counts.get(s, 0) + 1
        return counts

    def snapshot(self) -> list[dict]:
        return deepcopy(self._tasks)

    def has_pending_work(self) -> bool:
        """Return True if any task is pending, available, claimed, or in_progress."""
        return any(t["status"] in ("pending", "available", "claimed", "in_progress") for t in self._tasks)

    def is_all_done(self) -> bool:
        return all(t["status"] in ("completed", "failed", "blocked") for t in self._tasks) and len(self._tasks) > 0

    def clear(self) -> None:
        self._tasks.clear()
        self._order = 0

    # ── persistence (optional crash recovery) ────────────────────────────────

    def save_to_disk(self, run_id: str, cwd: Path | None = None) -> None:
        base = cwd or Path(os.getcwd())
        dir_path = base / ".taskmesh"
        dir_path.mkdir(parents=True, exist_ok=True)
        file_path = dir_path / f"tasks-{run_id}.json"
        file_path.write_text(json.dumps(self._tasks, indent=2, ensure_ascii=False))

    def load_from_disk(self, run_id: str, cwd: Path | None = None) -> bool:
        base = cwd or Path(os.getcwd())
        file_path = base / ".taskmesh" / f"tasks-{run_id}.json"
        if not file_path.exists():
            return False
        try:
            self._tasks = json.loads(file_path.read_text())
            self._order = len(self._tasks)
            return True
        except (json.JSONDecodeError, OSError):
            return False
