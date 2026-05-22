# Plan: Write HARNESS_REVIEW.md — audit of agent-harness-kit features for TaskMesh

## Context

The user has a separate project at `/Users/rta.juice/Downloads/agent-harness-kit-main`
(agent-harness-kit, "ahk") — a CLI runtime for structured multi-agent coordination that uses
SQLite + MCP + a real-time dashboard. They want to know which of its features would
meaningfully improve TaskMesh.

After exploring the harness-kit repo (README, AGENTS.md, src/, dashboard/, docs/, configs) and
mapping each feature against TaskMesh's current state (from the recent full-codebase audit
recorded in `AUDIT_REMAINING.md`), the review will recommend which patterns to adopt, adapt,
or skip. The deliverable is a single new file `HARNESS_REVIEW.md` at the repo root.

This plan describes the structure and contents of that review file — no other code or config
changes will be made in this turn.

---

## Why this is worth doing

Three of TaskMesh's loudest unresolved issues from `AUDIT_REMAINING.md` map cleanly onto
patterns ahk has already solved:

1. **Singleton orchestrator blocks concurrent users** — ahk has DB-backed atomic task claiming
   via SQL transactions. Postgres `UPDATE ... WHERE status='available' RETURNING *` would do
   exactly the same job for TaskMesh and allow multiple simultaneous runs per user.
2. **CoordinatorLog is in-memory only, lost on restart** — ahk has a 4-table persistent audit
   model (`actions`, `action_sections`, `action_files`, `action_tools`). TaskMesh has Runs
   and RunFiles but no per-action granularity.
3. **No retrieval for agents** — ahk exposes `docs.search` as an MCP tool. TaskMesh agents
   receive a brief + manager plan and nothing else; they cannot look up patterns in the
   uploaded design files or previously written code.

The review file gives the user a single artifact they can scan to decide what to actually
adopt next, with effort estimates so they can prioritise.

---

## Critical files

- **CREATE:** `HARNESS_REVIEW.md` at the repo root (new file, ~300 lines markdown).
- No other files touched in this turn.
- Re-uses concepts surfaced by the audit in `AUDIT_REMAINING.md` (read-only reference).

---

## Structure of HARNESS_REVIEW.md

```
# Agent-Harness-Kit Review for TaskMesh
> Date, source path, one-line purpose.

## Summary
Top 5 recommendations, ranked by impact-vs-effort.

## How ahk and TaskMesh differ at a glance
3-row table: deployment model, persistence, RBAC model.

## Feature-by-feature comparison
The main table the user asked for. Columns:
| Feature | Description | Relevance | Effort | Recommendation |
where Relevance ∈ {High, Medium, Low}, Effort ∈ {Small, Medium, Large},
Recommendation ∈ {Adopt, Adapt, Skip}.

Rows below — ordered Adopt → Adapt → Skip.

## Notes on the patterns the user explicitly asked about
A short paragraph per pattern (atomic task claiming, health gate, audit trail,
acceptance criteria, markdown fallback, docs search, role-based permissions)
explaining what ahk does and the closest TaskMesh equivalent, with file paths
on both sides for reference.

## Things NOT to adopt
Brief list with reasons (MCP protocol, multi-DB abstraction, .claude/.codex
file generation, CLI commands as primary UX).

## Suggested implementation order
3 numbered phases — what to build first, what builds on top.
```

---

## Row contents for the comparison table (drafted)

Each row will have its full row data ready in the plan so the deliverable is mechanical to
write. Order matches what will appear in the final file.

### Adopt (High relevance)

| # | Feature | Description | Relevance | Effort | Rec |
|---|---|---|---|---|---|
| 1 | DB-backed atomic task claiming | Postgres `UPDATE tasks SET status='in_progress', claimed_by=$1 WHERE id=$2 AND status='available' RETURNING *`. Replaces in-memory `SharedTaskList`. Survives restarts; allows multiple concurrent runs across users. | High | Medium | Adopt |
| 2 | Persistent coordinator audit trail | New `coordinator_events` table (run_id, event_type, agent_id, content, metadata, created_at). Replaces in-memory `CoordinatorLog`. Backs the existing frontend coordinator-log panel with a real query endpoint. | High | Small | Adopt |
| 3 | Acceptance criteria per task | Add `acceptance_criteria: list[str]` to the task schema. Manager generates them. Reviewer (currently dead code) walks them and approves/rejects. Activates the unused `ReviewerPanel` UI. | High | Medium | Adopt |
| 4 | Docs / context search exposed to agents | Grep-based search over uploaded files + already-written run files. Agents call it via a tool block in their prompt format. ahk uses MCP; TaskMesh can do it with a simple function-call pattern in the agent prompt. | High | Medium | Adopt |
| 5 | Pre-run health check | `GET /api/health` plus a startup probe: validates Zen API key reachability, DB connectivity, `PROJECT_DIR` writable. Returns structured status. Surface as a banner if any fails. | High | Small | Adopt |
| 6 | Stale-claim recovery | Background job that resets `tasks.status='available'` for claims older than N minutes when the run is still active. Needs #1 first. | High | Small | Adopt |

### Adapt (Medium relevance — lighter version)

| # | Feature | Description | Relevance | Effort | Rec |
|---|---|---|---|---|---|
| 7 | Per-action file/tool tracking | ahk records files and tools as separate rows. TaskMesh already parses FILE blocks; extending to write `action_files(action_id, path, op)` rows would feed a richer Projects dashboard timeline. | Medium | Medium | Adapt |
| 8 | `current.md` crash-recovery snapshot | ahk regenerates a markdown checkpoint on every state change. TaskMesh's `SharedTaskList.save_to_disk()` is close; formalising it as `.taskmesh/current.md` and reading it on startup gives interrupted runs a resume path. | Medium | Small | Adapt |
| 9 | Acceptance progress in the UI | Once #3 exists, add met/total counts and per-criterion checkboxes to `TasksList` and `ReviewerPanel`. | Medium | Small | Adapt |
| 10 | Tool-call recording for retries | When a Zen API call fails, log the model + prompt token count + error to `action_tools` so the upcoming retry helper has visibility. | Medium | Small | Adapt |

### Skip (Low / no relevance)

| # | Feature | Reason to skip | Recommendation |
|---|---|---|---|
| 11 | MCP protocol | TaskMesh agents talk directly to OpenCode Zen via OpenAI SDK. MCP would be a huge refactor with no payoff since TaskMesh is not a generic agent platform. | Skip |
| 12 | Multi-DB abstraction (SQLite/Postgres/MySQL via Drizzle) | TaskMesh is committed to Postgres on Cloud SQL. SQLAlchemy already covers this. | Skip |
| 13 | Provider-agnostic agent template generation (.claude/.opencode/.codex) | TaskMesh agents are LLM API calls, not editor-integrated tools. N/A. | Skip |
| 14 | CLI commands as primary UX (`ahk task add`, `ahk serve`) | TaskMesh's primary UX is the web app. A small admin CLI is in scope eventually, but not from this review. | Skip |
| 15 | Explicit `actions.record_file` MCP call | TaskMesh auto-parses FILE blocks from agent output. Simpler and already works. | Skip |
| 16 | Markdown fallback when MCP is down | TaskMesh doesn't use MCP. N/A. | Skip |
| 17 | Role-based permission enforcement (hard ACLs) | ahk's RBAC is also prompt-only with no real enforcement. Nothing to gain by copying it; real enforcement would be a separate, much larger project. | Skip |
| 18 | Config hot-reload (`ahk build --watch`) | TaskMesh reloads `agent-team.config.json` at the start of every run already. Effectively equivalent. | Skip |

---

## "Patterns the user explicitly asked about" section — content sketch

Each gets a 3–5 line paragraph + file paths:

- **Atomic task claiming via transactions**
  ahk: `src/core/repositories/TaskRepository.ts` uses SQLite `BEGIN IMMEDIATE` + UPDATE with status filter.
  TaskMesh: `backend/core/task_list.py` `SharedTaskList.claim_task` — single-process dict.
  Verdict: adopt the pattern, move to Postgres.

- **Health gate**
  ahk: `src/commands/health.ts` + user-provided `health.sh`. Blocks task start.
  TaskMesh: none.
  Verdict: small useful addition.

- **Audit trail data model**
  ahk: 4-table hierarchy `actions/action_sections/action_files/action_tools`, append-only.
  TaskMesh: in-memory `CoordinatorLog` only.
  Verdict: collapse to 1-2 tables and adopt.

- **Acceptance criteria**
  ahk: `task_acceptance` rows, agent self-reports met/unmet, dashboard shows progress.
  TaskMesh: tasks are just title+description.
  Verdict: adopt; gives the dormant reviewer agent something to do.

- **Markdown fallback**
  ahk: `.harness/current.md` regenerated on every state change as a server-down fallback.
  TaskMesh: doesn't use MCP, so the failure mode doesn't apply, but the pattern as a
  resume-from-crash mechanism is useful.
  Verdict: adapt, not for fallback but for crash recovery.

- **Docs search tool**
  ahk: MCP `docs.search(query)` — grep-based, no index, scans `docs/`.
  TaskMesh: agents have no retrieval beyond prompt context.
  Verdict: adopt the simple grep version against uploaded files + run output dir.

- **Role-based permission enforcement**
  ahk: prompt-level only.
  TaskMesh: prompt-level only.
  Verdict: nothing to gain by copying.

---

## "Things NOT to adopt" — short list with rationale

(Same items as the Skip rows in the table, but written as prose for skimmability.)

---

## Suggested implementation order (final section of the file)

1. **Phase A — DB migration of task list and coordinator log** (#1, #2).
   Blocks everything else. Adds two Postgres tables, swaps `SharedTaskList` and
   `CoordinatorLog` over, adds basic stale-claim recovery (#6).
2. **Phase B — Health and observability** (#5, #7, #10).
   Health endpoint, action_files tracking, retry visibility.
3. **Phase C — Acceptance criteria + reviewer reactivation** (#3, #4, #9).
   Manager generates criteria, reviewer evaluates, ReviewerPanel becomes functional.
   Docs search is bundled here because the reviewer needs it more than anyone.

---

## Verification

This task only writes a markdown document, so verification is:

1. After exiting plan mode, `HARNESS_REVIEW.md` exists at the repo root.
2. The Summary section at the top lists 5 ranked recommendations.
3. The main table has columns `Feature | Description | Relevance | Effort | Recommendation`
   with at least 18 rows.
4. Every file path mentioned in the review actually exists in either the harness-kit folder
   or the TaskMesh repo (sanity check with a few `ls` calls before committing).
5. `git diff --stat` shows only `HARNESS_REVIEW.md` was added; no other files changed.
