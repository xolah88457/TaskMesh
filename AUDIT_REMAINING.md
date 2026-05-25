# TaskMesh — Audit Remaining

Open items from the **2026-05-22** full codebase audit (second pass) and items
inherited from the 2026-05-21 audit. All items marked ✅ have been resolved.

**Last updated:** 2026-05-24 (Multi-tenant hardening Phase 1 — filesystem scoping + pool tuning + GitHub App + Teams gate).

---

## Multi-tenant hardening — Phase 1 (2026-05-24, second pass)

### Closed in this pass

| # | Issue | Status |
|---|------|--------|
| 24 | Filesystem tenant collision (two users with same slug shared a directory) | **Closed.** `get_project_dir(slug, user_id)` now scopes to `PROJECT_DIR/{user_id}/{slug}`. Health probe and root callers retain the legacy zero-arg form. |
| (new) | Agent Teams accessible to free / Starter users | **Closed.** `require_teams_access` enforces `plan == 'pro'` and `UserGitHubInstall.default_repo` on every `/api/teams*` route. Pack purchasers pass via the existing `_handle_transaction_completed` upsert. |
| (new) | Long-lived OAuth `repo` token stored plaintext | **Mitigated.** New GitHub App flow stores only the public `installation_id`; access tokens are minted on demand and cached in process memory for 50 min. The legacy OAuth path is preserved for the one-shot `/api/github/push` PR endpoint. |
| (new) | DB connection pool too small for multi-agent concurrency | **Closed.** `create_async_engine` now uses `pool_size=20`, `max_overflow=20`, `pool_recycle=1800`; all env-overridable. |

### Still open (deferred from Phase 1)

| # | Issue | Status | Suggested next step |
|---|------|--------|---------------------|
| 25 | Postgres Row-Level Security | Open | Migration 0003 adds RLS policies; `get_session(user_id=...)` sets `app.current_user_id`. Risk: every existing route needs the user_id passed through. |
| 26 | `_orchestrators` dict is per-process | Open | Partial unique index `runs(user_id) WHERE status='running'`. |
| 27 | Audit tables lack direct `user_id` | Open | Migration 0004 adds tenant_id; backfill from `runs.user_id` and `agent_teams.user_id`. |
| 28 | `agent-team.config.json` holds an operator API key | Open | Move to a service-only path, drop the disk fallback once every user has a `users.config_json`. |
| 29 | `TeamOrchestrator._inflight` in-process | Open | Same shape as #26; same fix. |
| 30 | Append-only logs not partitioned | Open | Migration 0005 — monthly RANGE partition by `created_at`. |
| 31 | Billing decrement + ZenUsage not transactional | Open | Wrap in a single `async with session.begin()` block; add `CHECK (balance_cents >= 0)`. |
| (new) | `run_files.content` / `action_*` blobs still in PG | Open | Phase 2 will dual-write to GitHub via `GitHubSink`, then drop columns. |


---

## 2026-05-22 audit — findings & fixes

### Fixed in this pass

| # | Issue | File(s) | Severity |
|---|------|---------|----------|
| 1 | **Duplicate `agent.run()` call per task** — `_run_agent_loop` invoked the LLM twice (once directly, once via `_run_with_search`); doubled token spend on every executor task | `backend/core/orchestrator.py` | **Critical** |
| 2 | **`docs_search` walked `.git`/`node_modules`/`venv` etc.** synchronously on the event loop; on a real repo this stalled all Socket.IO emits for seconds | `backend/core/docs_search.py`, orchestrator wired to `search_docs_async` | High |
| 3 | **Dead Socket.IO listeners** `reviewer_started` / `reviewer_result` / `reviewer_retry` were registered on the client but never emitted by the backend (replaced by `validation_verdict` / `validation_complete`) | `frontend/src/hooks/useSocket.ts` | Medium |
| 4 | **BillingPage opened a duplicate WebSocket** just to read `state.running`; replaced with a plain 30s usage poll | `frontend/src/pages/BillingPage.tsx` | Medium |
| 5 | **`validate_filename` rejected all dotfiles** despite `.gitignore` / `.env.example` being listed in `ALLOWED_EXTENSIONS` — silent user-facing bug on upload | `backend/core/file_upload.py` | Medium |
| 6 | **`load_config(user_id)` used `asyncio.get_event_loop().run_until_complete`** inside an already-running loop → RuntimeError landmine | `backend/core/config_loader.py` | Medium |
| 7 | **`SharedTaskList.add_task` set two different IDs** — memory copy used `id(...)[-8:]`, DB row used auto-increment; `start_task` / `complete_task` lookups failed when the orchestrator mixed handles | `backend/core/task_list.py` | High |
| 8 | **`_claim_db` skipped the "claimed" state** and went straight to "in_progress"; the orchestrator's subsequent `start_task()` call became a no-op and `recover_stale_claims` lost rows that crashed pre-`start` | `backend/core/task_list.py` | Medium |
| 9 | **Google OAuth `oauth_state` cookie leaked** — only the GitHub callback cleared it post-verification | `backend/api/auth.py` | Low |
| 10 | **`_run_with_retry` NameError when `max_retries=0`** — referenced loop var `attempt` outside the for-loop body | `backend/agents/base_agent.py` | Low |
| 11 | **docs.search audit row reported `_status="ok"`** but encoded its payload via `_error` (misleading column semantics) — clarified intent with comment + telemetry fields | `backend/core/orchestrator.py` | Low |
| 12 | **`LiveActivity` used `key={i}`** for log items — React anti-pattern; broke key stability when the rolling 60-event window evicted items | `frontend/src/components/LiveActivity.tsx` | Low |
| 13 | **`startProject` used `window.confirm`** mid-handler to gate `dispatch({type:'START'})` — the backend had already started, so the confirm was misleading | `frontend/src/hooks/useSocket.ts` | Medium |
| 14 | **Account deletion missed audit tables** (`ActionFile`, `ActionTool`, `Task`, `CoordinatorEvent`, `TaskAcceptance`, `Notification`) → orphaned rows in DB after delete | `backend/api/account.py` | Medium |
| 15 | **Auth cookie SameSite=strict was hard-coded** — broke Socket.IO auth on split-origin deploys (Vercel ⇄ Render); WebSocket couldn't send the cookie | `backend/auth/auth.py`, `backend/api/auth.py`, `.env.example` | High |
| 16 | **Sidebar recomputed `_all_acceptance` on every render** — wrapped in `useMemo` | `frontend/src/components/Sidebar.tsx` | Low |
| 17 | **`ReviewerPanel` hid the acceptance-criteria list** when `active`/`result` were empty, even though acceptance is now the panel's only live content | `frontend/src/components/ReviewerPanel.tsx` | Low |
| 18 | **Misleading error messages** when `/start-project` returned `no_subscription`, `no_credits`, `already running` — frontend just showed `"Could not start: <code>"` | `frontend/src/hooks/useSocket.ts` | Low |

### Still open (not fixed in this pass)

| # | Issue | Why deferred | Suggested fix |
|---|------|--------------|---------------|
| A | **`_orchestrators` dict is per-process** — running multiple uvicorn workers lets the same user start two parallel runs | Render's default Render single-worker; would require Redis or DB-backed orchestrator registry to fix | Add `WORKERS=1` to docs OR move the registry to Redis when scaling |
| B | **`calc_cost_cents` rounds <0.5¢ usage up to 1¢** — every call on a cheap model costs at least 1 cent | Intentional minimum-billable-unit; revisit when MODEL_PRICING gets re-tuned | Track `cost_cents_micros` (×10⁴) and only round at month-end |
| C | **`agent-team.config.json` is committed** and may contain a real API key | Risky to delete without consent; user keeps wanting to edit it as the dev default | Add to `.gitignore`, ship example only, document migration |
| D | **Stale `agent-team.config.json` vs DB drift** — disk file is global default, DB stores per-user; if a Pro user clears `users.config_json` they fall back to the disk file's potentially-stale API key | Acceptable trade-off; documented in PROJECT.md decisions log | If we ship a managed/cloud version, drop the disk file fallback entirely |
| E | **`MODEL_PRICING` table is hand-maintained** — drifts from real Zen pricing | No public Zen pricing API yet | When Zen exposes `/v1/models` with cost metadata, pull it dynamically and cache |
| F | **`SettingsPanel.tsx` duplicates model metadata** (PRO_ONLY_MODELS, THINKING_MODELS, MODEL_GROUPS) already on the backend | Frontend has no `/api/models` endpoint yet; adding one is a small feature, not a bug | Add `GET /api/models` returning grouped metadata, drop duplication |
| G | **Single-region Cloud SQL** — no read replica or fail-over | Not a code bug; infra decision | Documented in PROJECT.md for when scaling matters |
| H | **`useSocket` reducer has dead `reviewerActive` / `reviewerResult` fields** in `ProjectState` after the dead handler removal | Cascading rename would touch Sidebar + ReviewerPanel; left as `null` defaults for now | Optional: remove the fields when the next major UI refactor happens |
| I | **No rate limit on `/api/start-project`** — a user could open dozens of orchestrators in tight loop until the per-user single-runner check kicks in | Existing single-runner guard mitigates abuse; production rate limit is infra, not app | Add `slowapi` middleware in prod |

---

## ✅ Resolved (2026-05-21 audit — kept for traceability)

| # | Item | When resolved |
|---|------|--------------|
| 1 | Singleton orchestrator blocks concurrent users | 2026-05-21 — per-user dict + Socket.IO rooms |
| 2 | Vercel HTTP rewrites do not proxy WebSockets | 2026-05-21 — `VITE_SOCKET_URL` env var bypasses rewrites |
| 3 | `agent-team.config.json` shared global state | 2026-05-21 — `users.config_json` per-user config |
| 4 | `_upload_tokens` unbounded | 2026-05-21 — TTL cleanup background task |
| 5 | JWT in localStorage XSS-exfiltrable | 2026-05-21 — HttpOnly cookie |
| 6 | Cloud SQL Postgres-only `to_char()` | 2026-05-21 — precomputed `year_month` column |
| 7 | No retry on OpenCode Zen failures | 2026-05-21 — `_run_with_retry` w/ telemetry |
| 8 | Logo 3.2 MB | 2026-05-21 — SVG |
| 9 | `tasks_init` every 2s | 2026-05-21 — dirty flag |
| 10 | `git status` every 2s | 2026-05-21 — reduced to 5s |
| 11 | SettingsPanel Account tab duplication | 2026-05-21 — removed; navigates to /account |
| 12 | `run_limit` field mismatch | 2026-05-21 — added to response |
| 13 | Empty `THINKING_MODELS` | 2026-05-21 — populated (24 models) |
| 14 | Default `AUTH_DISABLED=true` | 2026-05-21 — flipped to false |
| 15 | Stray UUID files | 2026-05-21 — deleted |
| 16 | `cors_allowed_origins="*"` | 2026-05-21 — RuntimeWarning |
| 17 | OAuth state CSRF | 2026-05-21 — HMAC-signed state |
| 18 | MatrixRain 60fps | 2026-05-21 — pauses on visibilitychange |
| 19 | Mobile layout | 2026-05-21 — `hidden lg:flex` + hamburger |
| 20 | No "still working" indicator | 2026-05-21 — Agent.lastActivity heartbeat |
| 21 | Hardcoded billing/account colors | 2026-05-21 — CSS variables |
| 22 | OpenRouter dead code | 2026-05-21 — toggleable via `PROVIDER=openrouter` |

---

## Verification status (2026-05-22)

- `ruff check backend tests` → **All checks passed!**
- `cd frontend && npx tsc --noEmit` → 0 errors
- `cd frontend && npm run build` → **built successfully (475 modules)**
- `pytest tests/test_improvements.py -v` → **66 passed, 3 integration skipped**

Bundle size: 527 KB un-gzipped / 158 KB gzipped — over Vite's 500 KB warning
threshold but acceptable for this app; left for a later code-splitting pass.

---

## Notes for the next agent

- Phase B (observability) is shipped: `ActionFile` and `ActionTool` rows are
  written for every file write and LLM call. `GET /api/health` covers
  Zen/DB/PROJECT_DIR. `HealthBanner` surfaces degraded state.
- All known "obvious" bugs from this round are fixed. Remaining items in the
  *Still open* table are architectural choices, not defects.
- Before launch, walk the 9-item "Still open" list and decide which ones are
  pre-launch blockers and which are post-launch toil.
