# TaskMesh — TODO
> Last updated: 2026-05-20. Status legend: ✅ done · 🔄 in progress · ⬜ not started · ❌ blocked

---

## Milestone: SaaS MVP — End-to-End Working Product

---

## ✅ Completed

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
- ⬜ **Add PyJWT and bcrypt to `backend/requirements.txt`**
  - Add: `PyJWT>=2.8.0` and `bcrypt>=4.0.0`
  - Currently must be `pip install`ed manually after `pip install -r requirements.txt`
  - This will break fresh installs until fixed

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
| Fresh `pip install` success | PyJWT + bcrypt missing from requirements.txt |

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
