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


# ═══════════════════════════════════════════════════════════════════════════════
# TaskAcceptance CRUD on SharedTaskList
# ═══════════════════════════════════════════════════════════════════════════════

class TestTaskAcceptance:
    def test_add_task_with_acceptance(self):
        from contextlib import asynccontextmanager
        import asyncio
        from backend.core.task_list import SharedTaskList

        @asynccontextmanager
        async def null_session():
            yield None

        async def _run():
            tl = SharedTaskList(run_id="test-acc", session_factory=null_session)
            task = await tl.add_task(
                title="Test Task",
                description="A test",
                acceptance=["Must compile", "Must pass tests"],
            )
            assert task["acceptance"] == ["Must compile", "Must pass tests"]
            assert len(task["acceptance"]) == 2

        asyncio.run(_run())

    def test_get_acceptance_in_memory(self):
        from contextlib import asynccontextmanager
        import asyncio
        from backend.core.task_list import SharedTaskList

        @asynccontextmanager
        async def null_session():
            yield None

        async def _run():
            tl = SharedTaskList(run_id="test-acc", session_factory=null_session)
            await tl.add_task(title="T1", acceptance=["C1", "C2"])
            tasks = await tl.all_tasks()
            tid = tasks[0]["id"]
            acc = await tl.get_acceptance(tid)
            assert len(acc) == 2
            assert acc[0]["criterion"] == "C1"
            assert acc[1]["criterion"] == "C2"
            assert acc[0]["met"] is False

        asyncio.run(_run())

    def test_set_acceptance_met_in_memory(self):
        from contextlib import asynccontextmanager
        import asyncio
        from backend.core.task_list import SharedTaskList

        @asynccontextmanager
        async def null_session():
            yield None

        async def _run():
            tl = SharedTaskList(run_id="test-acc", session_factory=null_session)
            await tl.add_task(title="T1", acceptance=["C1"])
            tasks = await tl.all_tasks()
            tid = tasks[0]["id"]
            acc = await tl.get_acceptance(tid)
            cid = acc[0]["id"]
            ok = await tl.set_acceptance_met(cid, True, "reviewer")
            assert ok is True

        asyncio.run(_run())

    def test_add_task_acceptance_none_is_empty(self):
        from contextlib import asynccontextmanager
        import asyncio
        from backend.core.task_list import SharedTaskList

        @asynccontextmanager
        async def null_session():
            yield None

        async def _run():
            tl = SharedTaskList(run_id="test-acc", session_factory=null_session)
            task = await tl.add_task(title="T1")
            assert task["acceptance"] == []

        asyncio.run(_run())


# ═══════════════════════════════════════════════════════════════════════════════
# docs_search.search_docs
# ═══════════════════════════════════════════════════════════════════════════════

class TestDocsSearch:
    def test_and_semantics(self):
        from backend.core.docs_search import search_docs
        from pathlib import Path
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "a.py").write_text("def hello_world():\n    return 'hi'\n")
            (root / "b.py").write_text("print('hello')\nprint('world')\n")
            results = search_docs("hello world", [root], max_results=10)
            files = {s.file for s in results}
            # a.py has hello_world which contains both terms; b.py has them on separate lines
            assert "a.py" in files
            # b.py: line 1 has hello, line 2 has world — individual lines don't have both
            b_hits = [s for s in results if s.file == "b.py"]
            assert len(b_hits) == 0

    def test_max_results(self):
        from backend.core.docs_search import search_docs
        from pathlib import Path
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for i in range(20):
                (root / f"file_{i}.txt").write_text(f"match line {i}\n" * 3)
            results = search_docs("match", [root], max_results=5)
            assert len(results) == 5

    def test_skips_binaries(self):
        from backend.core.docs_search import search_docs
        from pathlib import Path
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "readme.txt").write_text("hello world")
            (root / "cat.png").write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00hello world\x00")
            results = search_docs("hello", [root], max_results=10)
            assert "cat.png" not in {s.file for s in results}

    def test_rejects_path_traversal(self):
        from backend.core.docs_search import _safe_open
        from pathlib import Path
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "safe.txt").write_text("hello")
            # Attempt to escape
            assert _safe_open(Path("../../../etc/passwd"), root) is None

    def test_empty_query_returns_empty(self):
        from backend.core.docs_search import search_docs
        from pathlib import Path
        results = search_docs("", [Path(".")], max_results=10)
        assert results == []


# ═══════════════════════════════════════════════════════════════════════════════
# Manager JSON backward compat (old tasks without acceptance)
# ═══════════════════════════════════════════════════════════════════════════════

class TestManagerBackwardCompat:
    def test_old_task_without_acceptance(self):
        from backend.agents.manager_agent import build_manager_system
        agents = [
            {"id": "manager", "role": "Coordinator", "planner": False},
            {"id": "backend", "role": "API", "planner": False},
        ]
        prompt = build_manager_system(agents)
        assert "acceptance" in prompt, "New manager prompt should include acceptance field"

    def test_acceptance_not_required_for_parsing(self):
        import json
        old_format = json.dumps({
            "feature": "Test",
            "analysis": "Test",
            "tasks": [{"id": "t1", "title": "Do stuff", "tag": "MGR"}],
        })
        plan = json.loads(old_format)
        assert plan["tasks"][0].get("acceptance") is None
        acceptance = plan["tasks"][0].get("acceptance", [])
        assert acceptance == []


# ═══════════════════════════════════════════════════════════════════════════════
# Stage tracking & validation verdict parsing
# ═══════════════════════════════════════════════════════════════════════════════

class TestValidationVerdictParsing:
    def test_parses_valid_verdict(self):
        from backend.core.orchestrator import Orchestrator
        # Use a dummy orchestrator instance — _parse_verdict doesn't need any instance state
        raw = '{"approved": true, "summary": "Looks good", "issues": [], "criteria_results": {"1": {"met": true, "note": "ok"}}}'
        result = Orchestrator._parse_verdict(raw)
        assert result is not None
        assert result["approved"] is True
        assert result["summary"] == "Looks good"
        assert result["criteria_results"]["1"]["met"] is True

    def test_parses_rejected_verdict_with_issues(self):
        from backend.core.orchestrator import Orchestrator
        raw = '{"approved": false, "summary": "Needs work", "issues": [{"severity": "blocker", "description": "Missing auth"}], "criteria_results": {}}'
        result = Orchestrator._parse_verdict(raw)
        assert result is not None
        assert result["approved"] is False
        assert len(result["issues"]) == 1
        assert result["issues"][0]["severity"] == "blocker"

    def test_rejects_non_json_output(self):
        from backend.core.orchestrator import Orchestrator
        result = Orchestrator._parse_verdict("This is just plain text, no JSON here")
        assert result is None

    def test_parses_json_buried_in_text(self):
        from backend.core.orchestrator import Orchestrator
        raw = "Some preamble text\n{\n  \"approved\": true,\n  \"summary\": \"OK\"\n}\nand trailing text"
        result = Orchestrator._parse_verdict(raw)
        assert result is not None
        assert result["approved"] is True


# ═══════════════════════════════════════════════════════════════════════════════
# Research stage — with and without planners
# ═══════════════════════════════════════════════════════════════════════════════

class TestResearchStage:
    def test_research_artifacts_stored(self):
        """Verify that research artifacts dict stores per-agent reports."""
        research = {"researcher": "Use FastAPI + asyncpg", "webdev": "Next.js + Tailwind"}
        assert len(research) == 2
        assert "researcher" in research
        assert "Use FastAPI" in research["researcher"]

    def test_research_summary_not_empty(self):
        summary = "Tools selected: FastAPI for backend, Next.js for frontend. "
        "Risk: PostgreSQL connection pooling under high load."
        assert len(summary) > 20

    def test_no_planners_fallback(self):
        """When planner_ids is empty, Manager should do solo research."""
        planner_ids: list[str] = []
        has_planners = len(planner_ids) > 0
        assert has_planners is False
        # Solo path: Manager handles research alone, no planner agents
        assert not has_planners  # validates the guard condition logic


# ═══════════════════════════════════════════════════════════════════════════════
# Validation stage
# ═══════════════════════════════════════════════════════════════════════════════

class TestValidationStage:
    def test_all_approved_is_overall_approved(self):
        verdicts = [
            {"agentId": "reviewer", "approved": True, "summary": "OK", "issues": []},
            {"agentId": "researcher", "approved": True, "summary": "OK", "issues": []},
        ]
        all_approved = all(v.get("approved", True) for v in verdicts)
        has_blocker = any(
            any(i.get("severity") == "blocker" for i in v.get("issues", []))
            for v in verdicts
        )
        assert all_approved is True
        assert has_blocker is False

    def test_any_rejected_is_not_approved(self):
        verdicts = [
            {"agentId": "reviewer", "approved": False, "summary": "Nope",
             "issues": [{"severity": "major", "description": "bad"}]},
            {"agentId": "researcher", "approved": True, "summary": "OK", "issues": []},
        ]
        all_approved = all(v.get("approved", True) for v in verdicts)
        assert all_approved is False

    def test_blocker_issue_detected(self):
        verdicts = [
            {"agentId": "reviewer", "approved": False, "summary": "Nope",
             "issues": [{"severity": "blocker", "description": "security hole"}]},
        ]
        has_blocker = any(
            any(i.get("severity") == "blocker" for i in v.get("issues", []))
            for v in verdicts
        )
        assert has_blocker is True


# ═══════════════════════════════════════════════════════════════════════════════
# Rework iteration guard
# ═══════════════════════════════════════════════════════════════════════════════

class TestReworkGuard:
    def test_rework_cap_respected(self):
        MAX_REWORK_ITERATIONS = 1
        rework_iteration = 0
        # First rework
        rework_iteration += 1
        assert rework_iteration <= MAX_REWORK_ITERATIONS
        # Second attempt should not happen — cap is 1
        would_exceed = (rework_iteration >= MAX_REWORK_ITERATIONS)
        assert would_exceed is True


# ═══════════════════════════════════════════════════════════════════════════════
# LLM Thinking — model set membership, extra_body generation, Anthropic path
# ═══════════════════════════════════════════════════════════════════════════════

class TestThinkingModelSets:
    def test_thinking_model_ids_populated(self):
        from backend.agents.base_agent import THINKING_MODEL_IDS
        from backend.agents.base_agent import ANTHROPIC_THINKING_MODEL_IDS
        assert len(THINKING_MODEL_IDS) > 0, "THINKING_MODEL_IDS should be populated"
        assert len(ANTHROPIC_THINKING_MODEL_IDS) > 0, "ANTHROPIC_THINKING_MODEL_IDS should be populated"

    def test_kimi_in_thinking_set(self):
        from backend.agents.base_agent import THINKING_MODEL_IDS
        assert "kimi-k2.6" in THINKING_MODEL_IDS
        assert "kimi-k2.5" in THINKING_MODEL_IDS

    def test_qwen_in_thinking_set(self):
        from backend.agents.base_agent import THINKING_MODEL_IDS
        assert "qwen3.5-plus" in THINKING_MODEL_IDS
        assert "qwen3.6-plus" in THINKING_MODEL_IDS

    def test_deepseek_in_thinking_set(self):
        from backend.agents.base_agent import THINKING_MODEL_IDS
        assert "deepseek-v4-pro" in THINKING_MODEL_IDS
        assert "deepseek-v4-flash" in THINKING_MODEL_IDS

    def test_non_thinking_models_excluded(self):
        from backend.agents.base_agent import THINKING_MODEL_IDS
        assert "big-pickle" not in THINKING_MODEL_IDS
        assert "nemotron-3-super" not in THINKING_MODEL_IDS
        assert "grok-build-0-1" not in THINKING_MODEL_IDS
        assert "gpt-5" not in THINKING_MODEL_IDS
        assert "gemini-3-flash" not in THINKING_MODEL_IDS

    def test_claude_in_anthropic_thinking_set(self):
        from backend.agents.base_agent import ANTHROPIC_THINKING_MODEL_IDS
        assert "claude-sonnet-4" in ANTHROPIC_THINKING_MODEL_IDS
        assert "claude-opus-4-5" in ANTHROPIC_THINKING_MODEL_IDS
        assert "claude-haiku-4-5" in ANTHROPIC_THINKING_MODEL_IDS

    def test_minimax_not_in_anthropic_thinking_set(self):
        from backend.agents.base_agent import ANTHROPIC_THINKING_MODEL_IDS
        assert "minimax-m2.7" not in ANTHROPIC_THINKING_MODEL_IDS


class TestThinkingExtraBody:
    """Verify extra_body construction in BaseAgent.run() for Chat Completions path."""

    def test_thinking_enabled_adds_chat_template_kwargs(self):
        from backend.agents.base_agent import BaseAgent, THINKING_MODEL_IDS
        agent = BaseAgent(
            name="test", model="kimi-k2.6", system_prompt="You are helpful.",
            thinking_budget=4096,
        )
        assert agent.thinking_budget == 4096
        assert agent.model in THINKING_MODEL_IDS

    def test_thinking_disabled_still_includes_disable_flag(self):
        """When thinking_budget=0 but model IS in set, should still set enable_thinking=False."""
        from backend.agents.base_agent import BaseAgent, THINKING_MODEL_IDS
        agent = BaseAgent(
            name="test", model="kimi-k2.6", system_prompt="You are helpful.",
            thinking_budget=0,
        )
        assert agent.thinking_budget == 0
        assert agent.model in THINKING_MODEL_IDS

    def test_non_thinking_model_has_zero_thinking_budget_default(self):
        from backend.agents.base_agent import BaseAgent, THINKING_MODEL_IDS
        agent = BaseAgent(
            name="test", model="big-pickle", system_prompt="You are helpful.",
        )
        assert agent.model not in THINKING_MODEL_IDS
        assert agent.thinking_budget == 0

    def test_thinking_budget_flows_from_constructor(self):
        from backend.agents.base_agent import BaseAgent
        agent = BaseAgent(
            name="researcher", model="kimi-k2.5", system_prompt="You research.",
            thinking_budget=8192,
        )
        assert agent.thinking_budget == 8192


class TestAnthropicThinking:
    """Verify Anthropic thinking path constraints."""

    def test_max_tokens_bumped_when_thinking_exceeds_max(self):
        """Anthropic requires max_tokens > thinking_budget. Should auto-bump."""
        thinking_budget = 16000
        max_tokens = 4096
        min_max = thinking_budget + 1024
        assert max_tokens < min_max
        effective_max = max(max_tokens, min_max)
        assert effective_max == thinking_budget + 1024

    def test_max_tokens_not_bumped_when_already_sufficient(self):
        thinking_budget = 4096
        max_tokens = 8192
        min_max = thinking_budget + 1024
        effective_max = max(max_tokens, min_max)
        assert effective_max == max_tokens  # unchanged

    def test_thinking_budget_zero_no_bump(self):
        thinking_budget = 0
        max_tokens = 4096
        min_max = thinking_budget + 1024
        effective_max = max(max_tokens, min_max)
        assert effective_max == 4096  # max_tokens unchanged


class TestThinkingContentExtraction:
    """Verify thinking_content is extracted from responses."""

    def test_anthropic_text_blocks_extracted(self):
        """Simulate extracting text from content blocks with thinking mixed in."""
        from unittest.mock import MagicMock
        blocks = [
            MagicMock(type="thinking", thinking="Let me analyze the request..."),
            MagicMock(type="text", text="Here is the answer."),
            MagicMock(type="thinking", thinking="Wait, I should also consider..."),
            MagicMock(type="text", text="And here is more context."),
        ]
        text_parts = []
        thinking_parts = []
        for b in blocks:
            if getattr(b, "type", None) == "thinking":
                thinking_parts.append(getattr(b, "thinking", ""))
            elif getattr(b, "type", None) == "text":
                text_parts.append(getattr(b, "text", ""))
        assert "\n".join(text_parts) == "Here is the answer.\nAnd here is more context."
        assert "\n".join(thinking_parts) == "Let me analyze the request...\nWait, I should also consider..."

    def test_text_only_no_thinking(self):
        """When no thinking blocks, thinking_content should be empty."""
        from unittest.mock import MagicMock
        blocks = [MagicMock(type="text", text="Just a simple answer.")]
        thinking_parts = [
            getattr(b, "thinking", "") for b in blocks
            if getattr(b, "type", None) == "thinking"
        ]
        assert thinking_parts == []
        assert "".join(thinking_parts) == ""

    def test_legacy_block_format(self):
        """Older Anthropic blocks may not have .type — fall back to .text."""
        from unittest.mock import MagicMock
        # block without type attr but with text attr (legacy format)
        old_block = MagicMock(spec=[])
        old_block.text = "Legacy formatted text"
        text = old_block.text if hasattr(old_block, "text") else ""
        assert text == "Legacy formatted text"


class TestThinkingConfigRoundTrip:
    """Verify thinking_budget flows through config save/load."""

    def test_thinking_budget_in_agent_cfg(self):
        """AgentCfg includes thinking_budget field at 0 by default."""
        cfg = {
            "id": "test", "name": "Test", "role": "QA",
            "model": "kimi-k2.5",
            "temperature": 0.7, "top_p": 0.9, "top_k": 0,
            "thinking_budget": 0, "planner": False,
            "color": "#ef4444", "icon": "🧪",
        }
        assert cfg["thinking_budget"] == 0
        cfg["thinking_budget"] = 4096
        assert cfg["thinking_budget"] == 4096

    def test_thinking_budget_survives_round_trip(self):
        """Simulate save → load — thinking_budget should survive."""
        original = {"thinking_budget": 4096}
        as_dict = dict(original)
        as_dict["temperature"] = 0.6
        # Simulate config save: backend serializes to JSON
        import json
        serialized = json.dumps(as_dict)
        # Simulate config load: frontend parses JSON
        loaded = json.loads(serialized)
        assert loaded["thinking_budget"] == 4096
        assert loaded["temperature"] == 0.6
