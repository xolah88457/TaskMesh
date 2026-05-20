# TaskMesh — TODO
> Last updated: 2026-05-20 (Model List Overhaul session). Status legend: ✅ done · 🔄 in progress · ⬜ not started · ❌ blocked

---

## Milestone: SaaS MVP — End-to-End Working Product

---

## ✅ Completed

### Dashboard UX & Agent Layout (2026-05-20)
- ✅ **Default agent layout is empty (manager only) on fresh install / first login**
  - Backend `DEFAULT_AGENTS` in `config_loader.py` reduced to manager-only
  - Frontend `DEFAULT_CONFIG` in `SettingsPanel.tsx` reduced to manager-only
  - Users see an empty dashboard and must explicitly add agents via Settings or "+ Add agents" button
  - The manager agent is always present as the required pipeline coordinator
- ✅ **API key settings relabeled for OpenCode Go / Zen**
  - Settings panel provider section now labeled "OpenCode API Key" (was "NVIDIA NIM")
  - Placeholder text: "Paste your OpenCode Go or Zen API key…"
  - Helper text references opencode.ai/zen
  - Provider name default changed from "NVIDIA NIM" → "OpenCode Go" in DEFAULT_PROVIDER and frontend config
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
- ✅ **All models replaced with curated 13-model set across 3 tiers**
  - Flagship (6): DeepSeek V4 Pro, GLM-5.1, Kimi K2.6, MiMo V2.5 Pro, MiniMax M2.7, Qwen3.6 Plus
  - Balanced (6): DeepSeek V4 Flash, GLM-5, Kimi K2.5, MiMo V2.5, MiniMax M2.5, Qwen3.5 Plus
  - Fast (1): Nemotron 3 Super
- ✅ **Old models completely removed** — all Llama, Mistral, GPT OSS, Phi, Jamba, Granite, Codestral, CodeLlama, Gemma, Seed, StarCoder, and old NVIDIA/Router IDs purged
- ✅ **Fourth category "Code" removed**; "Fast / Small" renamed to "Fast"
- ✅ **MODEL_GROUPS** in SettingsPanel.tsx — 4 groups → 3 groups with only the 13 new models
- ✅ **MODEL_RECOMMENDATIONS** in SettingsPanel.tsx — sampling defaults (temperature, top_p, top_k) set for all 13 models
- ✅ **MODEL_PRICING** in billing.py — per-token rates for all 13 models, old OpenRouter rates removed
- ✅ **PRO_ONLY_MODELS** in billing.py — all 6 Flagship models are Pro-only; Balanced + Fast available to Starter
- ✅ **OpenRouter comments cleaned** in base_agent.py and config_loader.py — old model ID maps removed
- ✅ Existing agent-team.config.json models already matched new IDs — no migration needed
- ✅ TypeScript build passes clean (0 errors)

### Infrastructure
- ✅ Provider switched NVIDIA NIM → OpenCode Go (2026-05-20)
  - base_url: `https://opencode.ai/zen/go/v1`, env var: `OPENCODE_GO_API_KEY`
  - All 9 agent model IDs updated to OpenCode Go short IDs
  - Thinking budgets disabled (NVIDIA-specific format); ready to re-enable for OpenRouter
  - MiniMax models excluded (use Anthropic message format, incompatible with AsyncOpenAI)
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
- ✅ 5-phase orchestration: select → plan → manage → execute → review
- ✅ FileLockRegistry — exclusive file ownership per agent
- ✅ AgentMailbox — async cross-agent messaging
- ✅ CoordinatorLog — structured run log
- ✅ Reviewer quality gate — Phase 4 approval before Phase 5
- ✅ Auto-commit after each atomic task
- ✅ Selector agent — picks agents from roster based on brief
- ✅ Planner agent — breaks brief into atomic tasks
- ✅ Manager agent — assigns tasks with file exclusivity
- ✅ Executor agents — parallel workers with file lock awareness
- ✅ Reviewer agent — audits all changes, returns pass/fail

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

---

## ⬜ Not Started — Your Action Required

These items require manual steps outside the codebase.

### 🔑 API Key Setup (Do First)
- ⬜ **Set up OpenCode Go API key**
  - Subscribe at https://opencode.ai/zen → Go → copy your API key
  - Set `OPENCODE_GO_API_KEY=<key>` in `.env`
  - `provider.apiKey` in `agent-team.config.json` is already `""` — falls back to env var
  - Until done: all agent runs fail with authentication error

### 📦 Dependencies
- ✅ PyJWT and bcrypt added to `backend/requirements.txt` (2026-05-20)

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
  Use [Paddle's webhook simulator](https://developer.paddle.com/webhooks/overview) or
  an ngrok tunnel to test credit allocation locally without a deployed server.

- ⬜ **Balance low warning in the app**
  BillingPage already shows amber/red credit bar. Consider also showing a banner in the
  main app header when balance < $1.00 to prompt top-up before credits run out mid-run.

### Medium Priority
- ⬜ **Retry logic in `base_agent.py` for NVIDIA NIM 429 rate limits**
  Currently no retry — a 429 propagates as empty content and silently corrupts the run.
  Add exponential backoff (3 retries, 2s/4s/8s) before giving up.

- ⬜ **Run-level credit estimate before starting**
  Before calling `asyncio.create_task(orchestrator.run(...))`, calculate an estimate of
  worst-case cost (e.g., 9 agents × avg token use × model rate) and warn user if it would
  exhaust their balance.

- ⬜ **Subscription management in AccountPage**
  Currently AccountPage has no link to manage/cancel Paddle subscription.
  Add a "Manage subscription" link that opens the Paddle billing portal (use
  `GET /api/billing/portal` → Paddle customer portal URL).

- ⬜ **Run timeout**
  Long runs can consume a lot of credits unexpectedly. Add a configurable per-run timeout
  (e.g., 10 minutes) that cancels the run and emits a `run:timeout` Socket.IO event.

### Low Priority / Nice to Have
- ⬜ **Email notifications**: send confirmation on subscription start and credit low
- ⬜ **OpenRouter activation**: code is written and commented out in `base_agent.py` and
  `config_loader.py`. To activate, set `OPENROUTER_API_KEY` and uncomment the blocks.
- ⬜ **Mobile layout**: current layout is desktop-only (flex columns, canvas, sidebar)
- ⬜ **Dark/light theme toggle on /billing and /account pages**
  These pages use hardcoded styles, not CSS variables. Should adopt the theme system.

---

## ❌ Blocked

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
| 2026-05-20 | NVIDIA NIM over OpenRouter | Faster cold start, better rate limits for current usage. OpenRouter code preserved (commented) as a fallback option. |
| 2026-05-20 | Custom auth over Clerk | Clerk added complexity and external dependency. Custom JWT is simpler, faster, and works offline. |
| 2026-05-20 | Balance shown as percentage, not dollars | Usage amounts should never show dollar values. Only payment-related items (plan prices, pack costs) use dollars. Percentages are clearer for credit depletion tracking. |
| 2026-05-20 | BillingPage centered layout | Previous left-aligned layout left half the screen as dead space. Centered layout with `maxWidth: 780` uses screen real estate better. |
| 2026-05-20 | Admin bypass redirects to dashboard | After entering valid admin key, user should be taken directly to the main app, not left on the billing page. `navigate('/')` after `fetchUsage()` ensures BillingGate sees the updated plan. |
| 2026-05-20 | Default agent layout is manager-only | Fresh installs start with only the Manager coordinator. Users explicitly add workers via Settings or "+ Add agents" button. Avoids overwhelming new users with 9 agents before they understand the system. |
| 2026-05-20 | "Recommended layout" button in Settings | One-click setup of all 9 agents with tested OpenCode Go model assignments. Replaces all current agents. Includes confirmation dialog and API key warning. |
| 2026-05-20 | "+ Add agents" direct shortcut in sidebar | Quick access from the main dashboard to the agent configuration pane, reducing friction for new users who see an empty agent list. |
| 2026-05-20 | Curated 13-model set (Flagship/Balanced/Fast) | Replaced 40+ disjoint models with a focused set of 13. 6 Flagship (Pro-only), 6 Balanced, 1 Fast. Removed old Llama/Mistral/Phi/Gemma/etc. Cleaner UX, easier pricing, consistent with OpenCode Go catalog. |
