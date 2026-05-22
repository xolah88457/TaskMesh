# TaskMesh — TODO
> Last updated: 2026-05-22 (Second full-codebase audit). Status legend: ✅ done · 🔄 in progress · ⬜ not started · ❌ blocked

---

## Milestone: SaaS MVP — End-to-End Working Product

---

## ✅ Completed

### Second Full Codebase Audit (2026-05-22)
- ✅ **Duplicate LLM call removed** — `_run_agent_loop` was calling `agent.run()` twice per task (once directly, once through `_run_with_search`). Cut credit burn ~50% per executor task.
- ✅ **`docs_search` no longer blocks event loop** — now offloaded via `asyncio.to_thread`; skips `.git`, `node_modules`, `venv`, `.taskmesh`, `dist`, `build`, `__pycache__`, etc. New `search_docs_async()` helper.
- ✅ **Dead Socket.IO listeners removed** — `reviewer_started` / `reviewer_result` / `reviewer_retry` never emitted by backend; deleted handlers, reducer cases, action variants.
- ✅ **BillingPage WebSocket dependency removed** — was opening a duplicate Socket.IO connection just to read `state.running`; replaced with a flat 30s usage poll.
- ✅ **File-upload dotfile bug** — `validate_filename` rejected all dotfiles even though `ALLOWED_EXTENSIONS` listed `.gitignore` / `.env.example`; now explicitly whitelisted.
- ✅ **`load_config(user_id)` event-loop landmine** — removed `asyncio.get_event_loop().run_until_complete` from a sync function that could be invoked under an active loop. Per-user config now exclusively async via `_load_user_config`.
- ✅ **SharedTaskList ID drift** — `add_task` now stores the DB row id as the canonical id in memory too; `start_task` / `complete_task` lookups no longer miss when handles mix.
- ✅ **DB claim state matches memory** — `_claim_db` sets `status="claimed"` (not `in_progress`); `start_task` performs the documented `claimed → in_progress` transition. `recover_stale_claims` now also catches rows that crashed before `start_task` ran.
- ✅ **OAuth state cookie cleanup** — Google callback was leaking the one-shot `oauth_state` cookie; now `delete_cookie`'d like GitHub.
- ✅ **`_run_with_retry` NameError fix** — initialised `attempt = 0` before the for-loop so `max_retries=0` no longer crashes.
- ✅ **docs.search audit row semantics clarified** — comment + explicit telemetry fields (`_attempts`, `_duration_ms`) so the ActionTool row no longer looks like a failure.
- ✅ **`LiveActivity` key={i} → composite key** — removes React anti-pattern that caused unnecessary remounts when the rolling 60-event window evicted entries.
- ✅ **`startProject` confirm dialog fix** — the confirm was misleading (the backend had already started). Replaced with a non-blocking `alert` + improved error messages for `no_subscription` / `no_credits` / `already running`.
- ✅ **Account deletion cascade fix** — `delete_account` now also removes `ActionFile`, `ActionTool`, `Task`, `CoordinatorEvent`, `TaskAcceptance`, `Notification` rows scoped to the user's runs.
- ✅ **Cookie SameSite configurable** — new `COOKIE_SAMESITE` env var; defaults to `strict` (local dev), set to `none` for split-origin Vercel↔Render deploys so Socket.IO can authenticate.
- ✅ **`Sidebar` memoisation** — `flattenAcceptance` and `mergedVerdicts` wrapped in `useMemo`.
- ✅ **`ReviewerPanel` no longer hides itself** when reviewer state is empty but acceptance criteria exist.
- ✅ ruff clean (0 errors), TypeScript build clean, `pytest tests/test_improvements.py -v` → 66 passed, 3 integration skipped.
- ✅ `.env.example` updated to document `COOKIE_SAMESITE`, `CORS_ALLOWED_ORIGINS`, `ENVIRONMENT`, `ADMIN_BYPASS_KEY`.

### Full Codebase Audit (2026-05-21)
- ✅ Three-pass audit complete (efficiency, bugs/security, UX); see AUDIT_REMAINING.md for surviving design questions
- ✅ **CSRF in GitHub OAuth callback fixed** — state now HMAC-signed with SECRET_KEY (was `base64(user_id)`, forgeable)
- ✅ **CORS lockdown** — `CORS_ALLOWED_ORIGINS` env var feeds both FastAPI middleware and Socket.IO; defaults to `*` for dev only
- ✅ **SECRET_KEY default warning** — emits RuntimeWarning when the dev fallback is used outside AUTH_DISABLED mode
- ✅ **Configurable JWT lifetime** via `JWT_TOKEN_DAYS` env var (default 30)
- ✅ **Orchestrator cancellation** — replaced broken `_run_task.cancelled()` polling with explicit `_cancel_requested` flag
- ✅ **Reviewer excluded from executor loop** — was spinning forever waiting for tasks the manager never assigned
- ✅ **Dead reviewer Socket.IO listeners removed** — backend never emitted `reviewer_started/result/retry`
- ✅ **Header upload removeFile stale-closure bug** — was nulling token after removing one of two files
- ✅ **Settings Account-tab forms wired** — email and password updates now call real `/api/account/*` endpoints (were stubs)
- ✅ **Dead code purged** — removed `backend/auth/clerk.py`, `python-jose` dependency, unused imports across backend
- ✅ **Provider name unification** — `OpenCode Go` references reconciled to `OpenCode Zen` in config JSON files
- ✅ **Fallback model fixed** — `meta/llama-3.1-8b-instruct` (dead NVIDIA ID) → `deepseek-v4-flash` in orchestrator + SettingsPanel
- ✅ **Manager agent max_tokens** — was missing from manager constructor; now passes through to BaseAgent
- ✅ **file_upload mime_map hoisted** — was rebuilt per file
- ✅ **Test fixes** — `asyncio.get_event_loop()` → `asyncio.run()`; removed stale `reviewer in config` assertion
- ✅ ruff clean (0 errors), TypeScript build clean (0 errors), pytest 25 passed / 3 integration skipped

### Remaining Medium Improvements (2026-05-21)
- ✅ **Per-user agent config** — `users.config_json` replaces shared `agent-team.config.json` for Pro users. Disk file is now a global default only.
- ✅ **Retry on Zen failures** — `_run_with_retry()` in base_agent.py: 3 attempts, exponential backoff 2/4/8s + jitter, handles 429/5xx/timeout
- ✅ **Logo optimized** — 3.2 MB PNG → 300-byte SVG
- ✅ **Postgres to_char() replaced** — `ZenUsage.year_month` column precomputed; queries use portable equality
- ✅ **tasks_init emits only on change** — dirty flag on SharedTaskList; frontend no longer re-renders on every 2s tick
- ✅ **git polling optimized** — removed redundant git_status from monitor loop; file polling reduced to 5s
- ✅ ruff clean, TypeScript build clean, pytest 25 passed

### Low-Priority & UX Improvements (2026-05-21)
- ✅ **SettingsPanel Account tab deduplicated** — removed `AccountSettingsPanel` + `OAuthRow`; Account tab navigates to /account
- ✅ **Dead ThinkingSlider purged** — removed `THINKING_MODELS`, `budgetToLevel`, `levelToBudget`, `ThinkingSlider`; documented re-activation path for OpenRouter
- ✅ **AUTH_DISABLED=false default** — `.env.example` flipped with warning; `auth.py` emits `RuntimeWarning`
- ✅ **Stray UUID files deleted** from repo root
- ✅ **CORS hardening** — `RuntimeWarning` when `CORS_ALLOWED_ORIGINS` defaults to `*` outside dev mode
- ✅ **OAuth state validated** — Google + GitHub callbacks verify anti-CSRF state via HttpOnly cookie
- ✅ **MatrixRain battery** — pauses requestAnimationFrame on visibilitychange (tab hidden)

### Dashboard UX & Agent Layout (2026-05-20)
- ✅ **Default agent layout is empty (manager only) on fresh install / first login**
  - Backend `DEFAULT_AGENTS` in `config_loader.py` reduced to manager-only
  - Frontend `DEFAULT_CONFIG` in `SettingsPanel.tsx` reduced to manager-only
  - Users see an empty dashboard and must explicitly add agents via Settings or "+ Add agents" button
  - The manager agent is always present as the required pipeline coordinator
- ✅ **API key settings relabeled for OpenCode Zen**
  - Settings panel provider section now labeled "OpenCode Zen API Key" (was "NVIDIA NIM")
  - Placeholder text: "Paste your OpenCode Zen API key…"
  - Provider name default changed from "NVIDIA NIM" → "OpenCode Zen" in DEFAULT_PROVIDER and frontend config
- ✅ **Save & Apply button overlap fixed**
  - Button now uses distinct visual states: normal (accent border), saving (muted+wait cursor), saved (green)
  - No more ghosting/overlap when transitioning between states
  - Disabled when saving or saved
- ✅ **"+ Add agents" button in sidebar AGENTS heading**
  - Located next to the "AGENTS" text in the sidebar (right panel)
  - Clicking opens the Settings panel to the Project tab where agents can be configured
  - Styled with accent border matching existing UI
  - Prop chain: App.tsx → Sidebar → AgentsList
- ✅ **"Recommended layout" button in dashboard Settings**
  - Button in the Agents section of Settings panel
  - Clicking shows a confirmation prompt: "Apply the recommended 9-agent layout? This will replace all current agents."
  - On confirm, replaces all agents with the recommended set:
    | Agent | Model |
    |---|---|
    | Manager | deepseek-v4-pro |
    | WebDev | kimi-k2.6 |
    | Researcher | kimi-k2.5 |
    | Backend | deepseek-v4-flash |
    | Frontend | mimo-v2.5 |
    | Tester | qwen3.5-plus |
    | Docs | qwen3.5-plus |
    | Logger | qwen3.5-plus |
    | Reviewer | deepseek-v4-pro |
  - Warns if no API key is configured (agents will fail to run)
  - Confirmation has "Apply and replace" and "Cancel" buttons
  - Replaces (not merges) existing agent config

### Model List Overhaul (2026-05-20)
- ✅ **All models replaced with curated 46-model set across 3 tiers**
  - Flagship Pro (16): 6 original Flagship + Claude Opus/Sonnet + GPT-5.4/5.5/5.4-pro/5.5-pro + Gemini 3.1 Pro + others
  - Balanced (22): 6 original Balanced + DeepSeek V4 Flash + Claude Haiku + GPT-5/5.1/5.2 + GPT Codex + Gemini Flash + others
  - Budget (8): nemotron-3-super + deepseek-v4-flash-free + big-pickle + mini variants + grok
- ✅ **Old models completely removed** — all Llama, Mistral, GPT OSS, Phi, Jamba, Granite, Codestral, CodeLlama, Gemma, Seed, StarCoder, and old NVIDIA/Router IDs purged
- ✅ **MODEL_GROUPS** in SettingsPanel.tsx — 3 groups: Flagship (Pro), Balanced, Budget
- ✅ **MODEL_RECOMMENDATIONS** in SettingsPanel.tsx — sampling defaults for all 46 models
- ✅ **MODEL_PRICING** in billing.py — per-token rates for all 46 models
- ✅ **PRO_ONLY_MODELS** in billing.py — 26 models (threshold: prompt >0.2¢/1K)
- ✅ **GPT_MODEL_IDS** (17) + **ANTHROPIC_MODEL_IDS** (12) in base_agent.py for model routing
- ✅ Existing agent-team.config.json models already matched new IDs — no migration needed
- ✅ TypeScript build passes clean (0 errors)

### Infrastructure
- ✅ Provider switched NVIDIA NIM → OpenCode Zen (2026-05-20)
  - base_url: `https://opencode.ai/zen/v1`, env var: `OPENCODE_GO_API_KEY`
  - All 9 agent model IDs updated to OpenCode Zen short IDs
  - MiniMax models supported via Anthropic Messages API (ANTHROPIC_MODEL_IDS in base_agent.py)
  - OpenRouter migration path preserved in comment blocks in base_agent.py + config_loader.py
- ✅ FastAPI + Socket.IO backend running
- ✅ React + Vite frontend running, proxies to backend
- ✅ Google Cloud SQL (PostgreSQL) connected and auto-migrating tables
- ✅ Custom JWT auth (PyJWT + bcrypt) — no Clerk dependency
- ✅ Google OAuth login — works end-to-end
- ✅ `AUTH_DISABLED=true` dev bypass — skips all auth and billing gates

### Billing System (2026-05-20)
- ✅ `user_credits` table — persistent plan + balance_cents per user
- ✅ Starter plan: $30/mo, 3-agent cap, standard models only
- ✅ Pro plan: $80/mo, all 9 agents, flagship models, GitHub push, shared config
- ✅ 3 PAYG credit packs ($20/$50/$100 one-time)
- ✅ `base_agent.run()` returns token counts for cost calculation
- ✅ Orchestrator deducts credits after every agent call (fire-and-forget)
- ✅ Plan-based model gating: `PRO_ONLY_MODELS` → `STARTER_MODEL_FALLBACK` for Starter
- ✅ Agent cap: `agent_limit=3` enforced in Phase 0 for Starter
- ✅ `calc_cost_cents()` with full model pricing table
- ✅ Paddle webhook handler (subscription.activated/updated/cancelled, transaction.completed)
- ✅ `/api/billing/checkout` → Paddle transaction URL
- ✅ `/api/billing/usage` → plan + balance_cents + run_count
- ✅ BillingPage: credit balance bar, plan cards, PAYG pack buttons, no-plan banner
- ✅ Live credit polling every 30s while run is active

### Auth & Account (2026-05-20)
- ✅ Login page (email/password + Google + GitHub buttons)
- ✅ Register page
- ✅ OAuth callback page (reads JWT from URL hash)
- ✅ `BillingGate` component — redirects plan="none" users to /billing before app access
- ✅ Header user pill → links to /account (never calls logout)
- ✅ Account page at /account:
  - Display name / profile update (issues fresh JWT, updates header pill instantly)
  - Email change
  - Password change
  - Connected OAuth providers (Google/GitHub status)
  - Danger zone: delete account (requires typing "DELETE")
- ✅ `/api/account/profile` (GET + PUT)
- ✅ `/api/account/email` (PUT)
- ✅ `/api/account/password` (PUT)
- ✅ `/api/account` (DELETE — cascades all user data)

### Plan Gates
- ✅ `POST /api/start-project` — blocks if plan="none" or balance_cents <= 0
- ✅ `PUT /api/config` — Pro only (403 for Starter)
- ✅ `POST /api/github/push` — Pro only (403 for Starter)
- ✅ Dev bypass: AUTH_DISABLED skips all gates in routes.py and billing.py

### Multi-Agent Pipeline
- ✅ 3-stage pipeline: Research → Plan → Production (with multi-agent validation)
- ✅ Stage 1 (Research): Manager + Researcher(s) converse to discover tools/libraries/constraints
- ✅ Stage 2 (Plan): Manager + Planner(s) produce architecture specs → Manager creates task plan
- ✅ Stage 3a (Production): Executor agents run concurrently via SharedTaskList
- ✅ Stage 3b (Validation): Multi-agent verdicts (Reviewer + Researcher → Manager tiebreaker) with 1 rework iteration
- ✅ Agents can search uploaded + generated files via `<search>` blocks (capped 3 rounds)
- ✅ SharedTaskList — DB-backed task queue with claim/start/complete workflow + crash persistence
- ✅ FileLockRegistry — exclusive file ownership per agent
- ✅ AgentMailbox — async cross-agent messaging
- ✅ CoordinatorLog — structured run log
- ✅ Agent loop — each agent claims tasks, executes, writes files, auto-commits, loops
- ✅ File parsing — `--- FILE: path ---` format with regex parsing and path traversal protection
- ✅ Auto-commit after each task
- ✅ Crash-recovery snapshots — `.taskmesh/current.md` regenerated on every state change

### Projects Dashboard
- ✅ Run history list (all past runs for authenticated user)
- ✅ File viewer — browse output files from any past run
- ✅ Download individual files
- ✅ GitHub push button (Pro only, calls /api/github/push)

### Billing UI Polish (2026-05-20)
- ✅ BillingPage centered layout — content horizontally centered with balanced whitespace
- ✅ Balance display changed to percentage only — no dollar amounts shown for usage/credits anywhere
- ✅ Plan prices ($30/mo, $80/mo, Add $10, etc.) remain in dollars (payment-related, not usage)
- ✅ Admin bypass redirect fixed — entering valid key now redirects to dashboard after granting access
- ✅ BalanceBar component: large `{pct}%` display with colored fill bar (green → amber < 25% → red < 10%)
- ✅ TypeScript build passes clean (0 errors)

### Phase C — Acceptance criteria, reviewer, docs search (2026-05-21)
- ✅ **Acceptance criteria per task** — `task_acceptance` table (id, task_id, run_id, criterion, met, checked_by, checked_at). Manager prompt extended with `"acceptance": [...]` field per task.
- ✅ **Reviewer reactivation (Phase 4)** — Reviewer agent runs after all executors finish. Gets full task list, acceptance criteria, files written. Emits `reviewer_started`/`reviewer_result` Socket.IO events. Flips `task_acceptance.met` per criterion.
- ✅ **Docs search tool for agents** — New `backend/core/docs_search.py` module. Agents issue `<search>query</search>` blocks; orchestrator runs grep-based search over upload_dir + PROJECT_DIR. Capped at 3 search rounds per task. Logged to `ActionTool` table as `docs.search`.
- ✅ **Crash-recovery snapshots** — `.taskmesh/current.md` regenerated on every coordinator event and task state change. Records run_id, brief, phase, task statuses with acceptance progress. `.taskmesh/` added to `.gitignore`.
- ✅ **Run resumable detection** — On orchestrator startup, checks DB for stale `running`-status runs. Emits `run_resumable` Socket.IO event if one is found (no auto-resume).
- ✅ **UI: acceptance criteria in TasksList** — Per-task badge showing `2/3 criteria` with accent color when all met.
- ✅ **UI: acceptance criteria in ReviewerPanel** — New "Acceptance Criteria" section above the issues list with ✓/✗ per criterion + reviewer note.
- ✅ ruff clean (0 errors), TypeScript build clean (0 errors), pytest 47 passed / 3 integration skipped

### 3-Stage Pipeline + Thinking Budget + Polish (2026-05-21)
- ... (15 items, see previous)

### New Dashboard + Routing Refactor (2026-05-22)
- ✅ New Dashboard page — TM dash design system: project cards grid, create form, widgets, credit display, activity feed
- ✅ Routing refactor: `/` → Dashboard (landing page), `/project/:id` → Workspace (old MainApp)
- ✅ Workspace mode: back-to-dashboard link, no billing/account navigation
- ✅ TM dash design tokens added to all 5 themes (--bg-elev, --bg-elev-2, --bg-hover, --border-strong, etc.)
- ✅ Global font: JetBrains Mono 13px, antialiased, stylistic sets ss01/ss02
- ✅ Header.tsx supports `mode="workspace"` to conditionally hide billing/account links
- ✅ Settings panel renamed to "Project Settings", second tab removed
- ✅ Billing button removed from dashboard header

### 💳 Paddle Setup
- ⬜ Create Paddle account at paddle.com
- ⬜ Create 2 subscription products: Starter ($30/mo) and Pro ($80/mo)
- ⬜ Create 3 one-time products: Pack S ($20), Pack M ($50), Pack L ($100)
- ⬜ Get 5 price IDs (format: `pri_...`) and add to `.env`:
  ```
  PADDLE_PRICE_STARTER=pri_...
  PADDLE_PRICE_PRO=pri_...
  PADDLE_PRICE_PACK_S=pri_...
  PADDLE_PRICE_PACK_M=pri_...
  PADDLE_PRICE_PACK_L=pri_...
  ```
- ⬜ Add Paddle API key and webhook secret to `.env`:
  ```
  PADDLE_API_KEY=live_...   (or sandbox_...)
  PADDLE_WEBHOOK_SECRET=pdl_ntf_...
  ```
- ⬜ Register webhook URL in Paddle dashboard:
  `https://yourdomain.com/api/billing/webhook`
  Events to enable: `subscription.activated`, `subscription.updated`,
  `subscription.cancelled`, `subscription.paused`, `transaction.completed`
- ⬜ Test with Paddle sandbox before going live

### 🐙 GitHub OAuth App — Login
- ⬜ Create GitHub OAuth App at github.com → Settings → Developer settings → OAuth Apps
  - Application name: TaskMesh
  - Homepage URL: http://localhost:5173 (or your domain)
  - Callback URL: http://localhost:8000/api/auth/github/callback
- ⬜ Add to `.env`:
  ```
  GITHUB_AUTH_CLIENT_ID=...
  GITHUB_AUTH_CLIENT_SECRET=...
  GITHUB_AUTH_REDIRECT_URI=http://localhost:8000/api/auth/github/callback
  ```
- ⬜ Test: "Continue with GitHub" on login page → should redirect and sign in

### 🐙 GitHub OAuth App — Code Push (can be same app as login)
- ⬜ Register additional callback URL in the same OAuth App:
  `http://localhost:8000/api/github/callback`
- ⬜ Add to `.env`:
  ```
  GITHUB_CLIENT_ID=...   (same as GITHUB_AUTH_CLIENT_ID if using one app)
  GITHUB_CLIENT_SECRET=...
  GITHUB_REDIRECT_URI=http://localhost:8000/api/github/callback
  ```
- ⬜ Test: connect GitHub on /account page → push to GitHub from /projects

### 🗂️ Git Repo in PROJECT_DIR
- ⬜ Initialize a git repo in the agent output directory so auto-commit works:
  ```bash
  cd $PROJECT_DIR
  git init
  git commit --allow-empty -m "init"
  ```
- ⬜ Until done: commits after each task silently fail, but runs complete normally

---

## ⬜ Not Started — Code Tasks

These are improvements to build next when external services are wired up.

### High Priority
- ⬜ **End-to-end test: full sign-up → subscribe → run → view output**
  After Paddle and GitHub OAuth are configured, walk through the complete flow once manually
  and document any gaps found.

- ⬜ **Paddle webhook local testing setup**
  Use Paddle's webhook simulator or an ngrok tunnel to test credit allocation locally without a deployed server.

- ⬜ **Run timeout DB status** — currently timeout sets status to "cancelled" in DB. Add "timeout" to the Run status enum if needed.

### Medium Priority
- ⬜ **Run cost estimate based on actual model pricing**
  Current credit estimate uses rough $0.01/1K token heuristic. Replace with per-model pricing from `billing.MODEL_PRICING`.

- ⬜ **Pipeline stages visible in ProjectsDashboard**
  Run history currently shows status + file count. Add stage timeline (research/plan/production split).

### Low Priority / Nice to Have
- ⬜ **Email notifications**: wire up actual email sending (SendGrid, Resend, or similar) for subscription_started and credit_low.
- ⬜ **OpenRouter model ID mapping** — populate OpenRouter-specific model IDs when switching providers.

---

##  Blocked

| Task | Blocker |
|---|---|
| Agent runs | OPENCODE_GO_API_KEY not set in .env |
| GitHub login | GITHUB_AUTH_CLIENT_ID not set in .env |
| GitHub code push | GITHUB_CLIENT_ID not set in .env |
| Paddle checkout | PADDLE_PRICE_* not set in .env |
| Paddle webhook | No public URL (local dev only) |
| Auto-commit after run | PROJECT_DIR git repo not initialized |

---

## Decisions Log

| Date | Decision | Rationale |
|---|---|---|
| 2026-05-20 | Dropped free tier entirely | 50/50 revenue split means free users cost money. Starter at $30/mo is the floor. |
| 2026-05-20 | Separate `user_credits` table | `user_usage` is month-keyed for analytics; a persistent balance needs a separate PK. |
| 2026-05-20 | Fire-and-forget credit deduction | Billing failures cannot interrupt runs. Wrapped in `try/except Exception: pass`. |
| 2026-05-20 | Pro-only models gated at orchestrator level, not agent level | Config is read once per run. Gating during config mutation (not at API call time) is simpler and testable. |
| 2026-05-20 | Logout removed from Header | Caused accidental logouts. Logout lives only on AccountPage Danger Zone section. |
| 2026-05-20 | OpenCode Zen over OpenRouter | Single master key, full 46-model catalog. OpenRouter code preserved (commented) as a fallback option. |
| 2026-05-20 | Custom auth over Clerk | Clerk added complexity and external dependency. Custom JWT is simpler, faster, and works offline. |
| 2026-05-20 | Balance shown as percentage, not dollars | Usage amounts should never show dollar values. Only payment-related items (plan prices, pack costs) use dollars. Percentages are clearer for credit depletion tracking. |
| 2026-05-20 | BillingPage centered layout | Previous left-aligned layout left half the screen as dead space. Centered layout with `maxWidth: 780` uses screen real estate better. |
| 2026-05-20 | Admin bypass redirects to dashboard | After entering valid admin key, user should be taken directly to the main app, not left on the billing page. `navigate('/')` after `fetchUsage()` ensures BillingGate sees the updated plan. |
| 2026-05-20 | Default agent layout is manager-only | Fresh installs start with only the Manager coordinator. Users explicitly add workers via Settings or "+ Add agents" button. Avoids overwhelming new users with 9 agents before they understand the system. |
| 2026-05-20 | "Recommended layout" button in Settings | One-click setup of all 9 agents with tested Zen model assignments. Replaces all current agents. Includes confirmation dialog and API key warning. |
| 2026-05-20 | "+ Add agents" direct shortcut in sidebar | Quick access from the main dashboard to the agent configuration pane, reducing friction for new users who see an empty agent list. |
| 2026-05-20 | Curated 46-model set (Flagship/Balanced/Budget) | Expanded to full OpenCode Zen catalog: 6 Flagship → 46 models across 3 tiers. PRO_ONLY_MODELS covers all expensive models (>$2/M input). |
