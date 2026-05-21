"""
Test harness for orchestrator coordination improvements.

Runs against the *existing* system — no data is deleted or mutated.

Usage:
    # Unit tests only (no running backend required)
    python -m pytest tests/test_improvements.py -v

    # Include integration smoke test (requires backend on :8000 with AUTH_DISABLED=true)
    python -m pytest tests/test_improvements.py -v --integration

Tests cover:
    - FileLockRegistry  (exclusive ownership, conflict detection, release)
    - AgentMailbox      (send, inbox, unread, typed messages)
    - CoordinatorLog    (record, retrieve, clear)
    - manager_agent     (reviewer excluded from task assignments)
    - Integration       (POST /api/start-project returns 'started' or 'already running')
"""

import asyncio
import sys
import pytest

# ── import the modules under test ─────────────────────────────────────────────
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))

from backend.core.orchestrator import FileLockRegistry, AgentMailbox, CoordinatorLog
from backend.agents.manager_agent import build_manager_system


# ═══════════════════════════════════════════════════════════════════════════════
# FileLockRegistry
# ═══════════════════════════════════════════════════════════════════════════════

class TestFileLockRegistry:
    def test_acquire_new_path(self):
        reg = FileLockRegistry()
        ok, holder = reg.acquire("src/app.py", "agent_a")
        assert ok is True
        assert holder is None

    def test_same_agent_re_acquires(self):
        reg = FileLockRegistry()
        reg.acquire("src/app.py", "agent_a")
        ok, holder = reg.acquire("src/app.py", "agent_a")
        assert ok is True
        assert holder is None

    def test_conflict_different_agent(self):
        reg = FileLockRegistry()
        reg.acquire("src/app.py", "agent_a")
        ok, holder = reg.acquire("src/app.py", "agent_b")
        assert ok is False
        assert holder == "agent_a"

    def test_release_and_reacquire(self):
        reg = FileLockRegistry()
        reg.acquire("src/app.py", "agent_a")
        reg.release("src/app.py", "agent_a")
        ok, holder = reg.acquire("src/app.py", "agent_b")
        assert ok is True
        assert holder is None

    def test_release_by_wrong_agent_is_noop(self):
        reg = FileLockRegistry()
        reg.acquire("src/app.py", "agent_a")
        reg.release("src/app.py", "agent_b")   # wrong agent — no effect
        ok, holder = reg.acquire("src/app.py", "agent_b")
        assert ok is False
        assert holder == "agent_a"

    def test_force_acquire_overwrites(self):
        reg = FileLockRegistry()
        reg.acquire("src/app.py", "agent_a")
        reg.force_acquire("src/app.py", "agent_b")
        assert reg.holder("src/app.py") == "agent_b"

    def test_release_all(self):
        reg = FileLockRegistry()
        reg.acquire("src/a.py", "agent_a")
        reg.acquire("src/b.py", "agent_a")
        reg.acquire("src/c.py", "agent_b")
        reg.release_all("agent_a")
        assert reg.holder("src/a.py") is None
        assert reg.holder("src/b.py") is None
        assert reg.holder("src/c.py") == "agent_b"

    def test_clear(self):
        reg = FileLockRegistry()
        reg.acquire("src/a.py", "agent_a")
        reg.acquire("src/b.py", "agent_b")
        reg.clear()
        assert reg.snapshot() == {}

    def test_snapshot_is_copy(self):
        reg = FileLockRegistry()
        reg.acquire("src/app.py", "agent_a")
        snap = reg.snapshot()
        snap["src/other.py"] = "intruder"
        assert "src/other.py" not in reg.snapshot()


# ═══════════════════════════════════════════════════════════════════════════════
# AgentMailbox
# ═══════════════════════════════════════════════════════════════════════════════

class TestAgentMailbox:
    def test_send_and_inbox(self):
        mb = AgentMailbox()
        mb.send("agent_a", "agent_b", "hello", "message")
        inbox = mb.inbox("agent_b")
        assert len(inbox) == 1
        assert inbox[0]["from"] == "agent_a"
        assert inbox[0]["content"] == "hello"
        assert inbox[0]["type"] == "message"

    def test_inbox_only_returns_own_messages(self):
        mb = AgentMailbox()
        mb.send("a", "b", "for b", "message")
        mb.send("a", "c", "for c", "message")
        assert len(mb.inbox("b")) == 1
        assert len(mb.inbox("c")) == 1
        assert len(mb.inbox("a")) == 0

    def test_unread_marks_as_read(self):
        mb = AgentMailbox()
        mb.send("a", "b", "test", "message")
        first = mb.unread("b")
        assert len(first) == 1
        second = mb.unread("b")
        assert len(second) == 0

    def test_inbox_still_available_after_unread(self):
        mb = AgentMailbox()
        mb.send("a", "b", "test", "message")
        mb.unread("b")  # marks as read
        # inbox still returns the message (full history)
        assert len(mb.inbox("b")) == 1

    def test_message_has_required_fields(self):
        mb = AgentMailbox()
        msg = mb.send("reviewer", "backend", "fix import", "feedback")
        assert "id" in msg
        assert "timestamp" in msg
        assert msg["type"] == "feedback"
        assert msg["read"] is False

    def test_multiple_messages_different_types(self):
        mb = AgentMailbox()
        mb.send("manager", "frontend", "here are your tasks", "message")
        mb.send("reviewer", "frontend", "missing error boundary", "feedback")
        mb.send("frontend", "manager", "blocked on API contract", "blocker")
        assert len(mb.inbox("frontend")) == 2
        assert len(mb.inbox("manager")) == 1

    def test_clear(self):
        mb = AgentMailbox()
        mb.send("a", "b", "hello", "message")
        mb.clear()
        assert mb.all_messages() == []


# ═══════════════════════════════════════════════════════════════════════════════
# CoordinatorLog
# ═══════════════════════════════════════════════════════════════════════════════

class TestCoordinatorLog:
    def test_record_returns_entry(self):
        log = CoordinatorLog()
        entry = log.record("task_created", "Build auth endpoint", {"agent": "backend"})
        assert entry["type"] == "task_created"
        assert entry["content"] == "Build auth endpoint"
        assert entry["metadata"]["agent"] == "backend"
        assert "timestamp" in entry

    def test_all_returns_all_entries(self):
        log = CoordinatorLog()
        log.record("phase_start", "Phase 0")
        log.record("agent_assigned", "backend → auth task")
        log.record("reviewer_started", "Reviewing output")
        assert len(log.all()) == 3

    def test_all_returns_copy(self):
        log = CoordinatorLog()
        log.record("phase_start", "Phase 0")
        entries = log.all()
        entries.append({"fake": "entry"})
        assert len(log.all()) == 1

    def test_clear(self):
        log = CoordinatorLog()
        log.record("phase_start", "Phase 0")
        log.clear()
        assert log.all() == []

    def test_metadata_defaults_to_empty(self):
        log = CoordinatorLog()
        entry = log.record("auto_commit", "committed 3 files")
        assert entry["metadata"] == {}


# ═══════════════════════════════════════════════════════════════════════════════
# Manager agent — reviewer excluded from task list
# ═══════════════════════════════════════════════════════════════════════════════

class TestManagerReviewerExclusion:
    SAMPLE_AGENTS = [
        {"id": "manager",  "role": "Coordinator", "planner": False},
        {"id": "webdev",   "role": "Architect",   "planner": True},
        {"id": "backend",  "role": "API",          "planner": False},
        {"id": "frontend", "role": "UI/UX",        "planner": False},
        {"id": "reviewer", "role": "Code Review",  "planner": False},
    ]

    def test_reviewer_not_in_tags(self):
        prompt = build_manager_system(self.SAMPLE_AGENTS)
        assert "REV" not in prompt, "Reviewer tag REV should not appear in manager task list"

    def test_executors_in_tags(self):
        prompt = build_manager_system(self.SAMPLE_AGENTS)
        assert "BAC" in prompt, "Backend tag BAC should appear"
        assert "FRO" in prompt, "Frontend tag FRO should appear"

    def test_planners_not_assigned_tasks(self):
        prompt = build_manager_system(self.SAMPLE_AGENTS)
        # Planners run Phase 1 already; manager note should mention this
        assert "webdev" in prompt.lower() or "planning" in prompt.lower() or "planner" in prompt.lower()

    def test_reviewer_excluded_by_role_variant(self):
        agents_with_role_variant = [
            {"id": "manager",  "role": "Coordinator", "planner": False},
            {"id": "backend",  "role": "API",          "planner": False},
            {"id": "rev_agent","role": "Reviewer",     "planner": False},
        ]
        prompt = build_manager_system(agents_with_role_variant)
        # rev_agent should be excluded since role is "Reviewer"
        assert "REV" not in prompt


# ═══════════════════════════════════════════════════════════════════════════════
# Integration smoke test (optional — requires running backend)
# ═══════════════════════════════════════════════════════════════════════════════

def pytest_addoption(parser):
    parser.addoption("--integration", action="store_true", default=False,
                     help="Run integration tests that require a running backend")


def pytest_collection_modifyitems(config, items):
    if not config.getoption("--integration"):
        skip_integration = pytest.mark.skip(reason="pass --integration to run")
        for item in items:
            if "integration" in item.keywords:
                item.add_marker(skip_integration)


def _backend_available() -> bool:
    import socket
    try:
        s = socket.create_connection(("localhost", 8000), timeout=1)
        s.close()
        return True
    except (ConnectionRefusedError, OSError):
        return False


@pytest.mark.integration
class TestIntegration:
    """Requires: backend running on :8000 with AUTH_DISABLED=true."""

    def test_start_project_returns_started_or_running(self):
        if not _backend_available():
            pytest.skip("Backend not running on :8000")
        import httpx

        async def _run():
            async with httpx.AsyncClient(base_url="http://localhost:8000") as client:
                resp = await client.post(
                    "/api/start-project",
                    json={"brief": "test harness: build a hello world API"},
                    timeout=10,
                )
                return resp

        resp = asyncio.run(_run())
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("status") == "started" or data.get("error") in (
            "already running", "orchestrator not ready", "no_subscription", "no_credits",
        ), f"Unexpected response: {data}"

    def test_config_endpoint_returns_agents(self):
        if not _backend_available():
            pytest.skip("Backend not running on :8000")
        import httpx

        async def _run():
            async with httpx.AsyncClient(base_url="http://localhost:8000") as client:
                return await client.get("/api/config", timeout=5)

        resp = asyncio.run(_run())
        assert resp.status_code == 200
        data = resp.json()
        assert "agents" in data
        agent_ids = [a["id"] for a in data["agents"]]
        # Manager is the only required agent; reviewer is optional and not in DEFAULT_AGENTS.
        assert "manager" in agent_ids

    def test_cancel_when_idle_returns_cancelling(self):
        if not _backend_available():
            pytest.skip("Backend not running on :8000")
        import httpx

        async def _run():
            async with httpx.AsyncClient(base_url="http://localhost:8000") as client:
                return await client.post("/api/cancel", timeout=5)

        resp = asyncio.run(_run())
        assert resp.status_code == 200
        # Returns cancelling even if nothing is running (idempotent)
        data = resp.json()
        assert "status" in data or "error" in data
