# TaskMesh — Project State
> Fast-recovery document. Update whenever work shifts. Last updated: 2026-05-23 (Project creation pipeline + UX fixes shipped).
> Full reference: `AGENT_CONTEXT.md`. Deep task list: `TODO.md`. Open items: `AUDIT_REMAINING.md`.

---

## Current Goal
Ship a working SaaS product: users sign up, pay via Paddle, and a team of AI agents builds
software for them in real time — writing real files, visible in the browser as they work.

**Active milestone:** Project creation pipeline complete. Users can create named projects
with per-project agent selection, each isolated to `PROJECT_DIR/{slug}/`. Dashboard
reflects real DB data. OAuth remember-me persists across browser restarts.

---

## Architecture

```
Browser (React + Socket.IO)
    │
    ▼
Vite dev server :5173  ──proxy /api, /socket.io──▶  FastAPI + python-socketio :8000
                                                           │
                                                   ┌───────┴────────┐
                                                     │  Orchestrator  │   (3-stage: Research→Plan→Production)
                                                     │  (core/orchestrator.py)
                                                     │  runs in PROJECT_DIR/{slug}/
                                                     └───────┬────────┘
                                                            │  spawns
                                            ┌────────────────┼────────────────┐
                                    Stage 1-2: Planners    Stage 3: Executors + Validators
                                    (research, specs)     (claim tasks,         (reviewer,
                                                            write files)         manager tiebreak)
                                          ▼
                                    OpenCode Zen API  (OpenAI-compatible)
                                   https://opencode.ai/zen/v1
                                   Auth: OPENCODE_GO_API_KEY
                                          │
                                   returns {content, prompt_tokens, completion_tokens, model}
                                          │
                                   billing.calc_cost_cents()  ──▶  UserCredits.balance_cents -= cost
                                                                    (fire-and-forget, never blocks)
```

**Auth flow:** custom JWT (PyJWT + bcrypt). Google OAuth + GitHub OAuth for social login.
OAuth remember-me persists via `POST /api/auth/exchange` — cookie set on JSON response
(not redirect) to survive Vercel proxy; explicit domain and max_age/expires headers.
**Payments:** Paddle → webhook → `user_credits` table (plan + balance_cents).
**DB:** Google Cloud SQL (PostgreSQL) via asyncpg. New `projects` table for project
identity. `runs.project_id` links runs to projects. All ops no-op gracefully if DATABASE_URL unset.
**Frontend state:** Socket.IO events drive a `useReducer` in `useSocket.ts`. No Redux.
**Provider migration path:** OpenCode Zen (active) | OpenRouter (toggleable via `PROVIDER=openrouter` env var).

---

## Repo Structure

```
MiniMaxClone/
├── .env                          secret keys (never commit)
├── .env.example                  template — all var names
├── agent-team.config.json        runtime agent roster (hot-loaded before each run)
├── AGENT_CONTEXT.md              full technical reference (authoritative)
├── PROJECT.md                    this file — fast recovery
├── TODO.md                       task tracking
│
├── backend/
│   ├── main.py                   FastAPI app + socket_app entry point + startup
│   ├── requirements.txt          pip dependencies
│   ├── api/
│   │   ├── account.py            GET/PUT profile, PUT email, PUT password, DELETE /account
│   │   ├── auth.py               register, login, Google OAuth, GitHub OAuth
│   │   ├── billing.py            Paddle checkout, webhook handler, /usage, credit constants
│   │   ├── github.py             repo OAuth + push-to-PR (Pro only)
│   │   └── routes.py             start-project (billing gate here), cancel, config, run history
│   ├── auth/
│   │   └── auth.py               create_token(), verify_token(), require_auth dependency
│   ├── agents/
│   │   ├── base_agent.py         BaseAgent.run() → {content, prompt_tokens, completion_tokens, model}
│   │   └── manager_agent.py      builds manager system prompt from agent roster
│   ├── core/
│   │   ├── orchestrator.py       shared-task-list agent loop, model gating, credit deduction
│   │   ├── config_loader.py      loads agent-team.config.json; defines DEFAULT_AGENTS
│   │   ├── task_list.py          SharedTaskList — in-memory task queue for agents
│   │   └── file_upload.py        file upload validation, storage, text preview
│   └── db/
│       ├── models.py             ORM: User, Run, RunFile, UserUsage, UserCredits, UserGitHub, ZenUsage
│       └── session.py            async session factory; no-op if DATABASE_URL unset
│
├── frontend/src/
│   ├── App.tsx                   routes, ProtectedRoute, BillingGate, MainApp
│   ├── main.tsx                  BrowserRouter + AuthProvider + App
│   ├── context/auth.tsx          AuthContext: user, token, login(), logout(), getToken()
│   ├── hooks/
│   │   ├── useSocket.ts          Socket.IO ↔ React state bridge
│   │   └── useAuthFetch.ts       fetch wrapper that injects Bearer token
│   ├── pages/
│   │   ├── LoginPage.tsx         email/password + Google + GitHub
│   │   ├── RegisterPage.tsx      same
│   │   ├── AuthCallback.tsx      reads JWT from URL hash after OAuth
│   │   ├── ProjectsDashboard.tsx run history + file viewer + GitHub push
│   │   ├── BillingPage.tsx       credit bar + plan cards + PAYG packs (fully built)
│   │   └── AccountPage.tsx       profile, email, password, OAuth status, danger zone
│   └── components/
│       ├── Header.tsx            brief input, Start/Stop, nav icons, user pill → /account
│       ├── AgentNetwork.tsx      canvas: animated hub-and-spoke
│       ├── Sidebar.tsx           agents + tasks + files + terminal tabs
│       ├── LiveActivity.tsx      scrolling event log
│       └── SettingsPanel.tsx     agent config, models, themes
│
└── tests/
    └── test_improvements.py      25 unit tests + 3 integration tests
```

---

## Setup (New Developer)

```bash
# 1. Backend
cd MiniMaxClone
python3 -m venv venv && source venv/bin/activate
pip install -r backend/requirements.txt

# 2. Environment
cp .env.example .env
# Edit .env — minimum required for local dev:
#   OPENCODE_GO_API_KEY=your-zen-key
#   AUTH_DISABLED=true
#   SECRET_KEY=any-random-string

# 3. Frontend
cd frontend && npm install
cp .env.local.example .env.local
# Edit frontend/.env.local:
#   VITE_AUTH_DISABLED=true

# 4. Run (two terminals)
# Terminal 1 — backend:
python3 -m uvicorn backend.main:socket_app --reload --port 8000
# CRITICAL: use "socket_app" not "app" — wrong entry point breaks all WebSockets

# Terminal 2 — frontend:
cd frontend && npm run dev
# → http://localhost:5173
```

With `AUTH_DISABLED=true` + `VITE_AUTH_DISABLED=true`, you go straight to the main app.
No login, no billing gate. Runs as a fake "pro" user with full credits.

---

## Key Commands

```bash
# Kill port conflicts
lsof -ti:5173 | xargs kill -9
lsof -ti:8000 | xargs kill -9

# Run unit tests
python -m pytest tests/test_improvements.py -v

# Run integration tests (backend must be running)
python -m pytest tests/test_improvements.py -v --integration

# TypeScript build check (must pass 0 errors)
cd frontend && npm run build

# Lint
cd frontend && npm run lint

# Quick smoke test — start a run (AUTH_DISABLED=true required)
curl -X POST http://localhost:8000/api/start-project \
  -H "Content-Type: application/json" \
  -d '{"brief": "Build a REST API"}'

# Check billing status
curl http://localhost:8000/api/billing/usage

# Register a test user
curl -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"test@x.com","password":"pass123","name":"Test"}'
```

---

## Recent Decisions

| Decision | Why |
|---|---|
| Separate `user_credits` table (not a column on `user_usage`) | `user_usage` is keyed by `(user_id, year_month)`. A persistent balance that doesn't reset monthly needs its own row. |
| `base_agent.run()` returns dict with token counts | Required for usage-based billing. Token counts are only available from the API response at call time; can't be computed later. |
| Fire-and-forget credit deduction with `asyncio.create_task()` | Billing failures must never interrupt a run. Wrapped in bare `except Exception: pass`. |
| Model gating as config mutation before `_setup_agents()` | Cleaner than swapping models at runtime. The patched config is per-run and doesn't touch disk. |
| Header user pill links to /account, never calls logout | Logout was being triggered by the pill on every navigation. Logout is now only in AccountPage. |
| BillingGate initialized with `checked = AUTH_DISABLED` | Prevents a render flicker in dev mode — component never shows `null` when auth is disabled. |
| JWT refresh after name/email update | The user pill in the header reads from the JWT. Without a new token, the display doesn't update until page reload. |
| `socket_app` not `app` as uvicorn entry point | `python-socketio` wraps FastAPI in an ASGI middleware. Using `app` bypasses the Socket.IO layer, causing 403 on all WebSocket connections. |
| No free tier | Every payment is 50% API cost. Free tier bleeds money. All users must be on a paid plan to start runs. |
| Starter: 3 agents, standard models only | Cheaper API cost. 26 Pro-only models (Flagship + expensive Claude/GPT/Gemini). Starter falls back to `deepseek-v4-flash`. |
| Balance shown as percentage, not dollars | Usage amounts should never show dollar values. Only payment-related items (plan prices, pack costs) use dollars. Percentages are clearer for credit depletion tracking. |
| BillingPage centered layout | Previous left-aligned layout left half the screen as dead space. Centered layout with `maxWidth: 780` uses screen real estate better. |
| Admin bypass redirects to dashboard | After entering valid admin key, user should be taken directly to the main app, not left on the billing page. `navigate('/')` after `fetchUsage()` ensures BillingGate sees the updated plan. |
| Default agent layout is manager-only | Fresh installs start empty — only the Manager coordinator. Avoids overwhelming new users. Workers added via Settings "+ Add" or "Recommended layout". |
| Settings API key section relabeled to Zen | Provider is OpenCode Zen (not NVIDIA NIM). Settings label, placeholder, and helper text updated. |
| "Recommended layout" button one-click agent setup | Applies a tested 9-agent configuration with specific model assignments. Replaces current agents with confirmation. |
| "+ Add agents" button in sidebar | Quick access from the main dashboard to agent configuration, reducing friction for new users with an empty agent list. |
| Curated 46-model set (Flagship/Balanced/Budget) | Full 46-model OpenCode Zen catalog. PRO_ONLY_MODELS: 26 models. Per-user config storage for Pro users. |
| Per-user agent config | `users.config_json` stores per-user config. Pro users' edits don't affect others. Disk file is global default. |
| Retry on Zen failures | 3-attempt exponential backoff with jitter on 429/5xx/timeout. Returns empty content on exhaustion — never crashes run. |
| Logo optimized | 3.2 MB PNG replaced with 300-byte SVG. |
| Event-driven tasks_init + polling reduction | Dirty flag prevents redundant frontend re-renders. Git polling reduced from 2s→5s. |
| Phase C: DB-backed acceptance criteria | `task_acceptance` table (not in-task column). Enables per-criterion reviewer evaluation with notes. |
| Phase C: Reviewer as dedicated Phase 4 | Reviewer runs AFTER all executors complete (not alongside). One pass only; no retry loop. |
| Phase C: Search via prompt blocks (not MCP) | `<search>` blocks parsed before FILE blocks. Capped at 3 rounds. Logged via ActionTool.error (metadata store). |
| 3-Stage pipeline over 2-phase | Planner agents were config-only dead weight. Multi-turn research gives better task plans. Validation catches issues before delivery. |
| Thinking budget activated on Zen (not OpenRouter) | OpenCode Zen supports thinking via `chat_template_kwargs` for most models. No need to wait for OpenRouter switch. |
| Two-tier validation (not all-agents) | Running 6+ agents for validation costs too much. Reviewer+Researcher first, Manager as tiebreaker only when needed. |
| Rework capped at 1 iteration | Infinite rework loops waste credits. One retry gives a second chance without runaway costs. |
| Balance warning at $2.50 threshold | Early enough to prompt top-up; not so aggressive it annoys users. Turns red at $0.00. Absolute values never shown — just "Low balance" / "No credits". |
| Run timeout at 600s default | Most runs complete in 2-5 minutes. 10 minutes is a generous ceiling that prevents credit drain from stuck agents. Configurable via RUN_TIMEOUT_SECONDS. |
| OpenRouter as env toggle, not replacement | Keeps Zen as default. Operators can switch with `PROVIDER=openrouter` without code changes. Both API keys checked at runtime. |
| **Cookie SameSite configurable (2026-05-22)** | Split-origin deploys (Vercel↔Render) need `SameSite=None` so Socket.IO can carry the cookie. `COOKIE_SAMESITE` env var defaults to `strict` for local dev. |
| **Removed duplicate LLM call (2026-05-22)** | `_run_agent_loop` was hitting OpenCode Zen twice per task (direct + via `_run_with_search`). Halves credit burn on executors. The search wrapper is now the single entry point. |
| **DB task id = canonical id (2026-05-22)** | `SharedTaskList.add_task` overrides the memory copy's id with the DB row id when DB-backed; `_claim_db` sets `status="claimed"` (not `in_progress`) so `start_task`'s documented transition is real. |
| **Project creation pipeline (2026-05-23)** | New `projects` table. `POST/GET /api/projects` endpoints. Per-project folder at `PROJECT_DIR/{slug}/`. Per-project agent selection (selected_agents on run row). Dashboard loads real projects from API. Launch creates project then navigates to workspace (autoStart off → SettingsPanel opens). Default agent selection is manager-only. |
| **OAuth remember-me (2026-05-23)** | Cookie set via `POST /api/auth/exchange` on JSON response (not redirect) to survive Vercel proxy. Explicit domain from FRONTEND_URL, max_age + expires headers. |
| **Logo + UX polish (2026-05-23)** | Transparent SVG logo with currentColor. Notifications toggle improved. Matrix rain scoped to authenticated pages. Credit footer shows percentage on both Dashboard + Workspace. |

---

## Open Questions / Assumptions

- **Paddle webhook delivery:** Local dev has no public URL for Paddle to hit. To test
  webhooks locally, use Paddle's webhook simulator or a tunnel (ngrok). This is not set up yet.
- **OpenCode Zen rate limits:** Unknown. Retry helper added (3 attempts, exponential backoff)
  so transient 429s are handled gracefully.
- **PostgreSQL on Cloud SQL:** Assumed to be PostgreSQL 15+. Async driver is asyncpg.
- **Agent output directory:** `PROJECT_DIR` env var. No default enforced — agents write
  to cwd if unset. This is intentional for local dev flexibility.
- **GitHub push concurrent access:** If two runs try to push to the same repo simultaneously,
  there is no locking. Assumed to be rare in practice.
- **Thinking on Zen:** `chat_template_kwargs` confirmed working for Kimi, Qwen, MiniMax, GLM, DeepSeek. GPT and Gemini thinking support needs provider documentation confirmation.
- **Anthropic thinking content:** Extracted from `response.content` blocks of type "thinking". Only text blocks returned as main content; thinking blocks surfaced separately.

---

## Definition of Done — Current Milestone

The current milestone is "working SaaS product, end-to-end":

- [x] New user can sign up (email or OAuth)
- [ ] New user is redirected to /billing, picks Starter or Pro, pays
- [ ] Paddle webhook sets `plan` and `balance_cents` in `user_credits`
- [x] User returns to app, BillingGate passes, main app loads
- [x] User types a brief, clicks Start, agents run, output appears
- [x] Credits deplete in real time (or on next /billing visit)
- [x] User can view run history at /projects
- [ ] Pro user can push output to GitHub
- [x] User can update profile, change password, disconnect OAuth at /account
- [x] All backend routes protected by JWT
- [x] Billing gates enforced (no_subscription, no_credits)
- [x] Dev bypass works (AUTH_DISABLED=true skips all gates)
- [x] Low balance warning appears in header when credits < $2.50
- [x] Run timeout prevents credit drain from stuck agents
- [x] Thinking budget available for 22+ models

---

## Where I Left Off (Agent Recovery)

**Session ended:** 2026-05-23 (Project creation pipeline shipped)
**Last actions:**
- Built full project creation + persistence pipeline: `projects` DB table, `POST/GET /api/projects`
  API endpoints, per-project `PROJECT_DIR/{slug}/` folder isolation, per-project agent selection
  (selected_agents filters orchestrator pipeline, manager always included).
- Dashboard now loads projects from API (not local-only state). launchNew POSTs to `/api/projects`
  with name, brief, icon, agent selection. Navigates to workspace with settings pre-filled.
- Fixed OAuth remember-me: cookie now set via `POST /api/auth/exchange` on JSON response
  (not redirect), with explicit domain + max_age + expires to survive Vercel proxy.
- Logo replaced with transparent currentColor SVG (inline in Dashboard, asset file for Header).
  Notifications toggle redesigned for clear on/off state. Credit footer shows percentage.
  - Made `docs_search` non-blocking (`asyncio.to_thread` + skip-list of noise dirs)
  - Made auth cookie SameSite configurable so split-origin deploys (Vercel↔Render)
    can authenticate Socket.IO
- **Bug fixes**: dotfile uploads, OAuth state cookie leak, `_run_with_retry`
  NameError with `max_retries=0`, account delete missing audit-table cascade,
  dead Socket.IO listeners removed.
- **Perf**: `Sidebar` memoised, `LiveActivity` key bug, BillingPage's wasteful
  duplicate Socket.IO connection removed.

**State of the codebase:**
- ruff: 0 errors across `backend/` and `tests/`
- TypeScript: `tsc --noEmit` clean, `npm run build` builds in ~600ms
- Python tests: 66 passed, 3 integration skipped (need running backend)
- HARNESS_REVIEW.md: Phases A, B, C all shipped
- 18 audit items from the 2026-05-22 pass resolved inline
- 9 architectural items deferred in `AUDIT_REMAINING.md` "Still open" table —
  most are launch-blockers worth a discussion (multi-worker orchestrator dict,
  config.json git-tracking, MODEL_PRICING drift, etc.) rather than defects

**Next 3 concrete tasks:**
1. Wire Paddle checkout (PADDLE_PRICE_*) + webhook → test full sign-up → pay → run → credit deduction flow
2. Wire GitHub OAuth for login + code push (GITHUB_AUTH_CLIENT_ID, GITHUB_CLIENT_ID)
3. Fix remaining blocked items in TODO.md (agent runs need OPENCODE_GO_API_KEY, etc.)

**Known broken flows:**
- Agent runs → auth error (OPENCODE_GO_API_KEY not yet set in .env)
- `Upgrade plan` checkout → 503 (PADDLE_PRICE_* not set)
- `Manage Subscription` portal → 503 (PADDLE_API_KEY not set)
- Auto-commit after run → silently fails (PROJECT_DIR git repo not initialized)
- GitHub login → unconfigured (GITHUB_AUTH_CLIENT_ID/GITHUB_AUTH_CLIENT_SECRET not set)

**Constraints:**
- Do NOT enable auth in production without setting a strong `SECRET_KEY` (a startup warning fires)
- Set `CORS_ALLOWED_ORIGINS` in prod to your frontend URL(s); the default is `*` (dev only)
- Do NOT commit `.env` — it contains SECRET_KEY
- `agent-team.config.json` may contain API keys — do not commit it
- Starter users must NEVER get access to models in `PRO_ONLY_MODELS`
- Credit deduction in `_deduct_credits()` must always be fire-and-forget — do not await it inline
- Balance display must NEVER show dollar amounts for usage — only percentages

**Prompts that reliably get an agent back on track:**
> "Read PROJECT.md, AGENT_CONTEXT.md Section 24, AUDIT_REMAINING.md, and TODO.md. Pick up the next task."
