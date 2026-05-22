# Agent-Harness-Kit Review for TaskMesh

> Date: 2026-05-21
> Source repo audited: `/Users/rta.juice/Downloads/agent-harness-kit-main` (will be copied into this repo at `./agent-harness-kit-main/` for direct reference — all file paths below reference that future location).
> Purpose: catalogue every feature of agent-harness-kit ("ahk") that could be extracted into TaskMesh, with effort estimates and a clear adopt / adapt / skip recommendation.

---

## Summary — top 5 picks, ranked by impact-vs-effort

1. **Persist the coordinator audit trail to Postgres.** TaskMesh's `CoordinatorLog` is in-memory only and lost on every restart; ahk's append-only `actions` / `action_sections` table model is exactly the shape you want. Small-to-medium effort, makes the run history actually queryable, unblocks better analytics. **(High / Small)**
2. **DB-backed atomic task claiming.** Replace `SharedTaskList` with a Postgres-backed `tasks` table and claim with `UPDATE … WHERE status='available' RETURNING *`. This is the missing primitive that lets multiple users run concurrently and lets a single run survive a backend restart. Both are real production gaps called out in `AUDIT_REMAINING.md`. **(High / Medium)**
3. **Acceptance criteria per task.** Manager generates a small list of checks per task; reviewer (currently dead code on the frontend and inert on the backend) evaluates them. This single change activates the dormant `ReviewerPanel` UI and the reviewer agent at the same time. **(High / Medium)**
4. **Pre-run health gate.** A small `/api/health` endpoint that probes the Zen API key, DB, and `PROJECT_DIR` writability before the orchestrator accepts a run. Today, broken config produces silent mid-run failures. **(High / Small)**
5. **Docs / context search exposed to agents.** ahk gives agents a `docs.search(query)` MCP tool. TaskMesh agents have no retrieval at all — they get the brief, the manager plan, and a couple of last-write summaries. A grep-style search over the upload directory and previously written run files would meaningfully improve output quality. Skip MCP — implement as a tool block in the agent prompt format. **(High / Medium)**

---

## How ahk and TaskMesh differ at a glance

| Dimension | agent-harness-kit | TaskMesh |
|---|---|---|
| Deployment | Local CLI runtime, single developer | Hosted SaaS, multi-user (Render + Vercel) |
| Persistence | SQLite (Drizzle, multi-DB optional) | Postgres on Cloud SQL via SQLAlchemy async |
| Coordination | Peer agents poll DB, no orchestrator | One orchestrator instance, 5-phase pipeline |
| Agent transport | MCP stdio server, tools per agent | Direct OpenAI / Anthropic SDK calls |
| Auth | None (trusted local env) | Custom JWT + bcrypt + Google/GitHub OAuth |
| Audit | Persisted to DB tables | In-memory `CoordinatorLog`, lost on restart |
| Acceptance | Per-task criteria with met/unmet | None — tasks are title + description |
| Health | Mandatory shell script before run | None |
| Retrieval | `docs.search` MCP tool | None |
| RBAC | Prompt-only (soft) | Prompt-only (soft) |

---

## Feature-by-feature comparison

| # | Feature | Description | Relevance | Effort | Recommendation |
|---|---|---|---|---|---|
| 1 | DB-backed atomic task claiming | `UPDATE tasks SET status='in_progress', claimed_by=$1 WHERE id=$2 AND status='available' RETURNING *` against Postgres. Replaces in-memory `SharedTaskList`. Survives restarts; lets multiple users run concurrently. | High | Medium | **Adopt** |
| 2 | Persistent coordinator audit trail | New `coordinator_events` table (run_id, event_type, agent_id, content, metadata, created_at). Replaces in-memory `CoordinatorLog`. Backs the existing `CoordLog` frontend panel with a real query endpoint. | High | Small | **Adopt** |
| 3 | Acceptance criteria per task | Add `acceptance_criteria: list[str]` to the task row. Manager generates them as part of task plan. Reviewer agent walks them and approves / rejects. Activates the dormant `ReviewerPanel` UI. | High | Medium | **Adopt** — shipped 2026-05-21 |
| 4 | Docs / context search exposed to agents | Grep-based search over `upload_dir/` and `PROJECT_DIR/`. Agents call it via a tool block (e.g. `<search>foo</search>`) parsed before the FILE blocks. ahk uses MCP; TaskMesh can do it without MCP using a simple in-prompt convention. | High | Medium | **Adopt** — shipped 2026-05-21 |
| 5 | Pre-run health gate | `GET /api/health` returns structured status for: Zen API reachable, DB pingable, `PROJECT_DIR` writable. Surface as a banner on the dashboard when degraded. Orchestrator refuses to start runs while red. | High | Small | **Adopt** |
| 6 | Stale-claim recovery | Background loop that resets `tasks.status='available'` when `claimed_at < now() - 5min` and the agent hasn't heartbeated. Depends on #1. | High | Small | **Adopt** |
| 7 | Per-action file/tool tracking | ahk records `action_files` and `action_tools` as separate rows. TaskMesh already parses FILE blocks during a run; extending that to also write `action_files(action_id, path, op)` would back a richer per-agent timeline on the Projects dashboard. | Medium | Medium | **Adapt** |
| 8 | `current.md` crash-recovery snapshot | ahk regenerates a markdown checkpoint on every state change. TaskMesh already calls `SharedTaskList.save_to_disk()`; formalising it as `.taskmesh/current.md` and reading it on startup gives interrupted runs a resume path. | Medium | Small | **Adapt** — shipped 2026-05-21 |
| 9 | Acceptance progress in the UI | Once #3 ships, add met/total counts and per-criterion checkboxes to `TasksList` and `ReviewerPanel`. The shape of the data already matches the existing component patterns. | Medium | Small | **Adapt** — shipped 2026-05-21 |
| 10 | Tool-call recording for retries | When a Zen API call fails, log model + token count + error to `action_tools`. Gives the upcoming retry helper (already on TODO.md) visibility into which agents are flaky. | Medium | Small | **Adapt** |
| 11 | MCP protocol | TaskMesh agents call OpenCode Zen directly via OpenAI / Anthropic SDKs. Wrapping in MCP would be a major refactor with no end-user payoff — TaskMesh is not a generic agent platform. | Low | Large | **Skip** |
| 12 | Multi-DB abstraction (SQLite / Postgres / MySQL via Drizzle) | TaskMesh is committed to Postgres on Cloud SQL. SQLAlchemy already abstracts the dialect cleanly. | Low | Large | **Skip** |
| 13 | Provider-agnostic agent template generation (`.claude/`, `.opencode/`, `.codex/`) | TaskMesh agents are LLM API calls, not editor-integrated tools. Not applicable. | Low | Medium | **Skip** |
| 14 | CLI commands as primary UX (`ahk task add`, `ahk serve`, `ahk dashboard`) | TaskMesh's primary UX is the web app. A small admin CLI is fine eventually, but it isn't from ahk that you'd copy the design. | Low | Medium | **Skip** |
| 15 | Explicit `actions.record_file` MCP call | TaskMesh auto-parses FILE blocks from agent output. Simpler, requires no extra agent discipline, already works. | Low | Small | **Skip** |
| 16 | Markdown fallback when MCP is down | TaskMesh doesn't use MCP. Failure mode doesn't apply. (The crash-recovery use of the same file is covered by #8.) | Low | — | **Skip** |
| 17 | Role-based permission enforcement | ahk's RBAC is prompt-only with no system-level enforcement — same as TaskMesh today. Copying it changes nothing; real enforcement (sandboxed file ACLs, tool gating) would be a separate, much larger project. | Low | Large | **Skip** |
| 18 | Config hot-reload (`ahk build --watch`) | TaskMesh already reloads `agent-team.config.json` at the start of every run. Effectively equivalent. | Low | — | **Skip** |

---

## Notes on the patterns the prompt explicitly called out

For each pattern, the ahk file path is rooted at `./agent-harness-kit-main/` (once the user has copied the source into the repo). TaskMesh paths are absolute from the repo root.

### Atomic task claiming via transactions
- ahk: `agent-harness-kit-main/src/core/repositories/TaskRepository.ts` wraps the claim in a SQLite `BEGIN IMMEDIATE` transaction and runs `UPDATE tasks … WHERE status='pending'`. The UPDATE matches zero rows when another agent already claimed, and the MCP server reports `task_already_claimed`.
- TaskMesh: `backend/core/task_list.py` exposes `SharedTaskList.claim_task` — a synchronous dict op in a single process. There's no cross-process coordination; restarts wipe state.
- Verdict: same primitive, move to Postgres. Recommended row #1.

### Health gate
- ahk: `agent-harness-kit-main/src/commands/health.ts` runs harness-level checks (config, DB, agent files, MCP wiring), then shells out to `health.sh` (template runs `npm run build && npm run test`). Lead agent invokes it before starting work.
- TaskMesh: nothing. A bad Zen key surfaces mid-run as an empty agent response.
- Verdict: add a minimal `/api/health` endpoint. Recommended row #5.

### Audit trail data model
- ahk: four append-only tables — `actions` (one row per agent invocation), `action_sections` (named text blocks), `action_files`, `action_tools`. All queryable from the dashboard.
- TaskMesh: `backend/core/orchestrator.py` `CoordinatorLog` — a Python list, never persisted. The frontend `coordLog` reducer accumulates events live but loses them on disconnect.
- Verdict: collapse to one or two tables and adopt. Recommended rows #2 and #7.

### Acceptance criteria system
- ahk: `task_acceptance` rows; agents self-report `met=1` via `tasks.acceptance.update`. UI shows progress bars. No automatic validation — the executing agent decides.
- TaskMesh: tasks are just `{id, title, description, status}`. No criteria. The Reviewer agent exists in `agent-team.config.json` but is never given tasks (build_manager_system explicitly excludes it).
- Verdict: adopt. Manager generates criteria as part of the task plan; reviewer becomes the agent that walks them at the end of execution. Recommended rows #3 and #9.

### Markdown fallback for agents
- ahk: `.harness/current.md` is regenerated after every state change so agents can read task state without MCP if the server is down. One-way write — agents read the file but never parse-modify it.
- TaskMesh: doesn't use MCP, so the "MCP server down" fallback doesn't apply. But the same artefact (a snapshot file) is a useful crash-recovery aid: if uvicorn crashes mid-run, the next start could read it to summarise what was already done.
- Verdict: adapt for resume-from-crash, not for fallback. Recommended row #8.

### Docs search tool
- ahk: `docs.search(query)` walks `docs/`, splits the query into lowercase terms, returns up to 10 lines where all terms appear (AND semantics). No index, no embeddings.
- TaskMesh: no retrieval surface for agents.
- Verdict: adopt the simple grep version. Target the upload directory (already collected by `backend/core/file_upload.py`) and the current `PROJECT_DIR`. Recommended row #4.

### Role-based permission enforcement
- ahk: `.claude/agents/*.md` lists each agent's `read` / `write` permissions and `allowedPaths`. These are **prompt-only** — the MCP layer doesn't reject calls from the wrong role; agents are expected to self-enforce.
- TaskMesh: same — `manager_agent.build_manager_system` writes role boundaries into the manager's system prompt, but the underlying SDK calls aren't gated.
- Verdict: nothing to gain. Real enforcement (tool gating, file ACLs) is a separate, much larger project than copying anything from ahk. **Skip.**

---

## Things NOT to adopt — short rationale

- **MCP transport.** TaskMesh's agents are LLM API calls, not editor tools. MCP would be a huge wrapper with no end-user benefit.
- **Multi-DB abstraction.** TaskMesh is Postgres-committed; SQLAlchemy already handles the dialect.
- **Provider-agnostic file generation (`.claude/`, `.opencode/`, `.codex/`).** TaskMesh doesn't run inside an editor.
- **CLI as primary UX.** TaskMesh is a web app. A future admin CLI is fine but won't take its shape from ahk.
- **Explicit `actions.record_file` requirement.** TaskMesh auto-parses FILE blocks — no need to require agents to also log them.
- **Hard RBAC.** ahk's is soft too; copying changes nothing.

---

## Suggested implementation order

These three phases assume each one is its own PR. Phases are ordered so the later work has the schema it needs.

**Phase A — Persistence layer for tasks and coordinator events.** Items #1, #2, #6.
- New `tasks` and `coordinator_events` tables in `backend/db/models.py`.
- Replace `SharedTaskList` and `CoordinatorLog` with thin DB-backed adapters that keep their existing public methods so the orchestrator and frontend reducers don't need to change.
- Add the stale-claim recovery loop in `backend/core/orchestrator.py`.
- Tests: extend `tests/test_improvements.py` with concurrency tests for `claim_task` against a real DB.

**Phase B — Health, observability, and resilience.** Items #5, #7, #10, plus the existing TODO retry helper.
- `GET /api/health` in `backend/api/routes.py` and a `<HealthBanner>` component on the dashboard.
- `action_files` + `action_tools` tables wired in `_write_files_from_parsed` and `_deduct_credits`.
- Retry helper in `backend/agents/base_agent.py` that uses `action_tools` for backoff visibility.

**Phase C — Acceptance criteria and reviewer reactivation.** Items #3, #4, #8, #9.
- `task_acceptance` column or table; manager prompt updated to generate criteria.
- Re-include reviewer in the executor loop (or run it as a Phase-4 step) and feed it the criteria.
- `docs.search` tool exposed via the agent prompt format, scoped to upload dir + PROJECT_DIR.
- `.taskmesh/current.md` snapshot regenerated on every state change.
- Frontend: progress bars in `TasksList`, real content in `ReviewerPanel`.

**Status: Shipped 2026-05-21**
