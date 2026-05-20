# TaskMesh — Project State
> Fast-recovery document. Update whenever work shifts. Last updated: 2026-05-20 (Dashboard UX + Agent Layout session).
> Full reference: `AGENT_CONTEXT.md`. Deep task list: `TODO.md`.

---

## Current Goal
Ship a working SaaS product: users sign up, pay via Paddle, and a team of AI agents builds
software for them in real time — writing real files, visible in the browser as they work.

**Active milestone:** Billing + account management complete (code done); external services
(Paddle, GitHub OAuth) not yet wired up. Next: connect those services and test end-to-end.

---

## Architecture

```
Browser (React + Socket.IO)
    │
    ▼
Vite dev server :5173  ──proxy /api, /socket.io──▶  FastAPI + python-socketio :8000
                                                           │
                                                   ┌───────┴────────┐
                                                   │   Orchestrator  │   (5-phase pipeline)
                                                   │  (core/orchestrator.py)
                                                   └───────┬────────┘
                                                           │  spawns
                                          ┌────────────────┼────────────────┐
                                       Selector         Planner         Manager
                                       Executor         Reviewer
                                          │  (all BaseAgent subclasses)
                                          ▼
                                   OpenCode Go API  (OpenAI-compatible)
                                   https://opencode.ai/zen/go/v1
                                   Auth: OPENCODE_GO_API_KEY
                                          │
                                   returns {content, prompt_tokens, completion_tokens, model}
                                          │
                                   billing.calc_cost_cents()  ──▶  UserCredits.balance_cents -= cost
                                                                    (fire-and-forget, never blocks)
```

**Auth flow:** custom JWT (PyJWT + bcrypt). Google OAuth + GitHub OAuth for social login.
**Payments:** Paddle → webhook → `user_credits` table (plan + balance_cents).
**DB:** Google Cloud SQL (PostgreSQL) via asyncpg. All ops no-op gracefully if `DATABASE_URL` unset.
**Frontend state:** Socket.IO events drive a `useReducer` in `useSocket.ts`. No Redux.
**Provider migration path:** OpenCode Go (now, flat $10/mo) → OpenRouter (next, pay-per-token).
Switch instructions in `base_agent.py` and `config_loader.py` comment blocks.

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
│   ├── requirements.txt          pip dependencies (NOTE: PyJWT + bcrypt not listed yet)
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
│   │   ├── orchestrator.py       5-phase pipeline, model gating, credit deduction, agent cap
│   │   └── config_loader.py      loads agent-team.config.json; defines DEFAULT_AGENTS
│   └── db/
│       ├── models.py             ORM: User, Run, RunFile, UserUsage, UserCredits, UserGitHub
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
pip install PyJWT bcrypt          # not in requirements.txt yet

# 2. Environment
cp .env.example .env
# Edit .env — minimum required for local dev:
#   NVIDIA_API_KEY=nvapi-...
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
| Starter: 3 agents, standard models only | Cheaper API cost. Flagship models (deepseek-v4-pro, kimi-k2, etc.) are Pro-only. Starter falls back to `deepseek-v4-flash`. |
| Balance shown as percentage, not dollars | Usage amounts should never show dollar values. Only payment-related items (plan prices, pack costs) use dollars. Percentages are clearer for credit depletion tracking. |
| BillingPage centered layout | Previous left-aligned layout left half the screen as dead space. Centered layout with `maxWidth: 780` uses screen real estate better. |
| Admin bypass redirects to dashboard | After entering valid admin key, user should be taken directly to the main app, not left on the billing page. `navigate('/')` after `fetchUsage()` ensures BillingGate sees the updated plan. |
| Default agent layout is manager-only | Fresh installs start empty — only the Manager coordinator. Avoids overwhelming new users. Workers added via Settings "+ Add" or "Recommended layout". |
| Settings API key section relabeled to OpenCode | Provider is OpenCode Go (not NVIDIA NIM). Settings label, placeholder, and helper text updated. |
| "Recommended layout" button one-click agent setup | Applies a tested 9-agent configuration with specific model assignments. Replaces current agents with confirmation. |
| "+ Add agents" button in sidebar | Quick access from the main dashboard to agent configuration, reducing friction for new users with an empty agent list. |

---

## Open Questions / Assumptions

- **Paddle webhook delivery:** Local dev has no public URL for Paddle to hit. To test
  webhooks locally, use [Paddle's webhook simulator](https://developer.paddle.com/webhooks/overview)
  or a tunnel (ngrok). This is not set up yet.
- **NVIDIA NIM rate limits:** Unknown. If runs start failing with 429s, add retry logic
  to `base_agent.py`. Currently no retry — failures propagate as empty content.
- **PostgreSQL on Cloud SQL:** Assumed to be PostgreSQL 15+. Async driver is asyncpg.
  Connection string format for Cloud SQL socket: `postgresql+asyncpg://user:pass@/dbname?host=/cloudsql/...`
- **Agent output directory:** `PROJECT_DIR` env var. No default enforced — agents write
  to cwd if unset. This is intentional for local dev flexibility.
- **GitHub push concurrent access:** If two runs try to push to the same repo simultaneously,
  there is no locking. Assumed to be rare in practice.

---

## Definition of Done — Current Milestone

The current milestone is "working SaaS product, end-to-end":

- [ ] New user can sign up (email or OAuth)
- [ ] New user is redirected to /billing, picks Starter or Pro, pays
- [ ] Paddle webhook sets `plan` and `balance_cents` in `user_credits`
- [ ] User returns to app, BillingGate passes, main app loads
- [ ] User types a brief, clicks Start, agents run, output appears
- [ ] Credits deplete in real time (or on next /billing visit)
- [ ] User can view run history at /projects
- [ ] Pro user can push output to GitHub
- [ ] User can update profile, change password, disconnect OAuth at /account
- [x] All backend routes protected by JWT
- [x] Billing gates enforced (no_subscription, no_credits)
- [x] Dev bypass works (AUTH_DISABLED=true skips all gates)

---

## Where I Left Off (Agent Recovery)

**Session ended:** 2026-05-20 (Dashboard UX + Agent Layout)  
**Last action:** Implemented 4 dashboard UX fixes — empty default agent layout, OpenCode API key relabeling, "+ Add agents" sidebar button, "Recommended layout" settings button. Updated TODO.md, PROJECT.md, AGENT_CONTEXT.md. TypeScript build passed (0 errors).

**State of the codebase:**
- All code for billing redesign, account page, onboarding gate, and dev bypass is complete
- BillingPage UI polished: centered layout, percentage-only balance, admin bypass redirect
- Dashboard agent layout now starts empty (manager only); users explicitly add agents
- Settings panel: API key section now labeled for OpenCode Go/Zen, Save & Apply button no longer ghosts
- Sidebar: "+ Add agents" button opens Settings for agent configuration
- Settings: "Recommended layout" button applies a one-click 9-agent configuration
- TypeScript build passes clean (0 errors)
- Python syntax clean
- Google OAuth works end-to-end
- Paddle UI is fully built — just needs real price IDs from Paddle dashboard
- GitHub OAuth is fully built — just needs OAuth App credentials

**Files changed most recently (this session):**
```
backend/core/config_loader.py      DEFAULT_AGENTS reduced to manager-only
frontend/src/components/SettingsPanel.tsx   API key relabel, Save&Apply fix, Recommended layout button
frontend/src/components/AgentsList.tsx      "+ Add agents" button
frontend/src/components/Sidebar.tsx         onAddAgents prop passthrough
frontend/src/App.tsx                        onAddAgents callback to Sidebar
TODO.md                                    added Dashboard UX section + decisions
PROJECT.md                                 added decisions, updated recovery section
AGENT_CONTEXT.md                           updated Sections 1, 12, 14, 22, 24
```

**Next 3 concrete tasks:**
1. Subscribe to OpenCode Go at https://opencode.ai/zen → set `OPENCODE_GO_API_KEY` in `.env`
2. Add `PyJWT>=2.8.0` and `bcrypt>=4.0.0` to `backend/requirements.txt`
3. Create GitHub OAuth App + set `GITHUB_AUTH_*` vars → test GitHub login end-to-end

**Known broken flows:**
- All agent runs → auth error (OPENCODE_GO_API_KEY not yet set in .env)
- `GitHub login` button → 503 (GITHUB_AUTH_CLIENT_ID not set)
- `Push to GitHub` → 503 (GITHUB_CLIENT_ID not set)
- `Upgrade plan` checkout → 503 (PADDLE_PRICE_* not set)
- Auto-commit after run → silently fails (PROJECT_DIR git repo not initialized)

**Constraints:**
- Do NOT enable auth in production without setting a strong `SECRET_KEY`
- Do NOT commit `.env` — it contains API keys and SECRET_KEY
- `agent-team.config.json` may contain API keys — do not commit it
- Starter users must NEVER get access to models in `PRO_ONLY_MODELS`
- Credit deduction in `_deduct_credits()` must always be fire-and-forget — do not await it inline
- Balance display must NEVER show dollar amounts for usage — only percentages

**Prompts that reliably get an agent back on track:**
> "Read PROJECT.md, AGENT_CONTEXT.md Section 24, and TODO.md. Pick up the next task."
