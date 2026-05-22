TASKMESH — COMPLETE PROJECT CONTEXT
====================================
Last updated: 2026-05-22 (Second full-codebase audit — 18 fixes shipped + 9 architectural items deferred to AUDIT_REMAINING.md)
Written for: any agent or developer who has never seen this project before.
Purpose: read this file in full before touching any code. It is the single authoritative reference.


================================================================================
SECTION 1: WHAT THIS PROJECT IS
================================================================================

TaskMesh is a real-time multi-agent AI coding assistant delivered as a web application.
A user types a natural-language project brief (e.g. "Build a REST API for a todo list app
with PostgreSQL"). A configurable team of AI agents then plans, architects, codes, tests,
and documents the project live in the browser — each agent occupies a node on a visual
network graph, animating as it works.

The agents actually write real files to disk using a structured protocol. When a run
finishes, the user can browse all output files, download them individually, or push
the entire output as a GitHub pull request with one click (Pro plan only).

The target user is a non-developer who wants to build working software. The UX must be
approachable and the output must be real, runnable code — not pseudocode or scaffolding.

The product is a SaaS business. Users sign up (email/password, Google, or GitHub).
There is no free tier. Two paid subscription plans are offered via Paddle:

  Starter — $30/month → $15 API credits/month, max 3 agents/run, standard models only
  Pro     — $80/month → $40 API credits/month, all 9 agents, flagship models, GitHub push,
                        shared agent config

Pay-as-you-go credit packs (no subscription required, but a subscription is needed to run):
  Pack S  — $20 one-time → $10 credits
  Pack M  — $50 one-time → $25 credits
  Pack L  — $100 one-time → $50 credits

Credits deplete based on actual LLM token usage after each agent call (not a fixed per-run
fee). The balance display shows a percentage of remaining credits that shrinks as agents
consume tokens. No dollar amounts are shown for usage anywhere in the application — only
plan prices and pack costs use dollar values.
50% of every payment goes to the user's internal credit balance in TaskMesh for Zen API usage; 50% is profit.

Users with no subscription and $0 balance cannot start runs.


================================================================================
SECTION 2: TECH STACK
================================================================================

Frontend:
  - React 19.2.6 with TypeScript
  - Vite 8.0.12 (bundler and dev server)
  - Tailwind CSS 3.4.19 (utility classes)
  - Framer Motion 12.38.0 (animations)
  - Socket.IO client 4.8.3 (real-time updates)
  - React Router DOM 7.15.1 (client-side routing)
  - No Clerk — auth is fully custom

Backend:
  - Python 3.11+
  - FastAPI 0.115.5
  - uvicorn 0.32.1 with standard extras
  - python-socketio 5.11.4 (Socket.IO ASGI server)
  - openai 1.57.0 (used as OpenAI-compatible SDK for OpenCode Zen)
  - anthropic >= 0.45.0 (Anthropic Messages API for Claude + MiniMax)
  - python-dotenv 1.0.1
  - httpx 0.27.0 (OAuth HTTP calls)
  - sqlalchemy[asyncio] 2.0.41
  - asyncpg 0.30.0 (PostgreSQL async driver)
  - PyJWT >= 2.8.0 (JWT signing, imported as `jwt`)
  - bcrypt >= 4.0.0 (password hashing)

AI provider (active):
  OpenCode Zen — full model catalog via OpenAI-compatible API.
  Endpoint: https://opencode.ai/zen/v1
  Accessed via the openai Python SDK with a custom base_url.
  Single master API key: OPENCODE_GO_API_KEY env var.
  Curated model set: 46 models across 3 tiers — Flagship Pro (16), Balanced (22), Budget (8).
  See Section 15 for full pricing/PRO_ONLY_MODELS table.
  Note: Claude models + MiniMax use Anthropic Messages API (ANTHROPIC_MODEL_IDS in base_agent.py).
  Note: GPT models use Chat Completions (Responses API after openai SDK >= 1.59.0).
  Note: BYOK (per-user API keys) fully removed — single master Zen key only.

AI provider (next step — code ready but inactive):
  OpenRouter at https://openrouter.ai/api/v1
  All switch instructions in base_agent.py and config_loader.py comment blocks.
  To activate: set OPENROUTER_API_KEY, update DEFAULT_BASE_URL, swap model IDs.

Database:
  Google Cloud SQL (PostgreSQL), accessed via asyncpg driver.
  In local dev without DATABASE_URL set, all DB operations are no-ops — the app runs
  without a database, users are anonymous, and runs are not persisted.

Payments:
  Paddle (https://api.paddle.com) — creates checkout transactions and receives webhooks.
  Supports subscriptions (monthly recurring) and one-time transactions (PAYG packs).

GitHub integration (two separate OAuth flows):
  1. Login: GitHub OAuth for user authentication. Scope: user:email.
     Stores github_id on the users table.
  2. Code push: GitHub OAuth for push access to the user's repos. Scope: repo.
     Stores access_token in the user_github table. Used to create branches and PRs.
     Gated to Pro plan only.
  Both can share one GitHub OAuth App by registering two redirect URIs.


================================================================================
SECTION 3: REPOSITORY LAYOUT
================================================================================

MiniMaxClone/                          project root
  AGENT_CONTEXT.md                     this file
  README.md                            brief public readme
  .env                                 secret keys — never commit
  .env.example                         template with all variable names
  agent-team.config.json               runtime agent configuration — hot-loaded before each run
  agent-team.config.example.json       reference config with all fields documented
  pytest.ini                           test configuration (marks registration)
  package.json                         root-level (not the frontend package.json)

  backend/
    __init__.py
    main.py                            FastAPI app entry point + Socket.IO server + startup
    requirements.txt                   Python dependencies

    api/
      __init__.py
      account.py                       Account management: profile, email, password, delete
      auth.py                          Auth REST endpoints: register, login, OAuth callbacks
      billing.py                       Paddle checkout, webhook, credit balance, usage
      github.py                        GitHub code-push OAuth + push-to-PR flow (Pro only)
      routes.py                        Core REST endpoints: start-project, cancel, config, runs

    auth/
      __init__.py
      auth.py                          JWT create/verify, bcrypt, require_auth dependency

    agents/
      __init__.py
      base_agent.py                    BaseAgent class — run() returns dict with token counts
      manager_agent.py                 ManagerAgent — builds manager system prompt dynamically

    core/
      __init__.py
      orchestrator.py                  3-stage pipeline + coordination layer (main file)
      config_loader.py                 Loads agent-team.config.json; defines DEFAULT_AGENTS
      task_list.py                     SharedTaskList — DB-backed task queue with in-memory fallback
      file_upload.py                   File upload validation, storage, text preview
      docs_search.py                   NEW — grep-based search over upload_dir + PROJECT_DIR

    db/
      __init__.py
      models.py                        SQLAlchemy ORM models (all tables)
      session.py                       Async session factory; no-op if DATABASE_URL unset

  frontend/
    index.html                         HTML shell — <title>TaskMesh</title>
    package.json                       NPM manifest — lists all frontend dependencies
    vite.config.ts                     Proxies /api and /socket.io to localhost:8000
    tailwind.config.js
    postcss.config.js
    tsconfig.json
    tsconfig.app.json
    tsconfig.node.json
    eslint.config.js
    .env.local.example                 Template for VITE_AUTH_DISABLED
    public/
      favicon.svg
      icons.svg

    src/
      main.tsx                         App entry — BrowserRouter + AuthProvider + App
      App.tsx                          Route definitions + ProtectedRoute + BillingGate + MainApp
      App.css
      index.css                        Base styles
      themes.ts                        Theme definitions and CSS variable maps

      context/
        auth.tsx                       AuthContext — user, token, login, logout, getToken

      hooks/
        useSocket.ts                   Socket.IO event handling, state reducer, startProject
        useAuthFetch.ts                Fetch wrapper that automatically adds Bearer token

      types/
        index.ts                       TypeScript types for all state: Agent, Task, ProjectState, etc.

      pages/
        LoginPage.tsx                  Email/password login + Google OAuth + GitHub OAuth buttons
        RegisterPage.tsx               Registration form + same OAuth buttons
        AuthCallback.tsx               Reads JWT from URL hash after OAuth redirect
        ProjectsDashboard.tsx          /projects — run history list + file viewer + GitHub push
        BillingPage.tsx                /billing — credit bar, Starter/Pro plan cards, PAYG packs
        AccountPage.tsx                /account — profile, password, OAuth providers, delete account

      components/
        Header.tsx                     Top bar: wordmark, brief input, Start/Stop, nav icons, user pill
        AgentNetwork.tsx               Canvas: animated hub-and-spoke network of agents
        AgentsList.tsx                 Sidebar list of agents with status badges
        LiveActivity.tsx               Scrolling event log (last 60 entries)
        MatrixRain.tsx                 Animated green rain background (default theme only)
        Sidebar.tsx                    Right panel container: agents + tasks + files + terminal
        SettingsPanel.tsx              Slide-in panel: agent config, models, thinking budget, themes
        ReviewerPanel.tsx              Stage 3b validation results and acceptance criteria
        TasksList.tsx                  Task list with completion tracking
        Terminal.tsx                   Terminal output panel (last 30 lines)

  tests/
    __init__.py
    test_improvements.py               Unit + integration tests for coordination layer


================================================================================
SECTION 4: ENVIRONMENT VARIABLES
================================================================================

All backend variables go in /.env (root of the MiniMaxClone directory).
All frontend variables go in /frontend/.env.local.
Never commit .env or .env.local. Use .env.example and .env.local.example as templates.

BACKEND VARIABLES:

  OPENCODE_GO_API_KEY
    Single master API key for the entire app. BYOK (per-user keys) was removed.
    Obtained from https://opencode.ai/zen after subscribing to Zen.
    (Future: replace with OPENROUTER_API_KEY when switching to OpenRouter.)

  SECRET_KEY
    Required in production. Signs all JWTs. Generate with:
      python3 -c "import secrets; print(secrets.token_hex(32))"
    Default in code: "dev-secret-change-in-production" (only safe with AUTH_DISABLED=true)
    Emits RuntimeWarning when the default is used outside AUTH_DISABLED mode.

  JWT_TOKEN_DAYS
    Optional. JWT expiry duration in days. Default: 30.
    Set via env: JWT_TOKEN_DAYS=7

  CORS_ALLOWED_ORIGINS
    Comma-separated list of allowed frontend origins for CORS and Socket.IO.
    Default: "*" (dev only — permits all origins). Production: set to your frontend URL(s).

  AUTH_DISABLED
    Set to "true", "1", or "yes" to bypass all JWT verification AND billing gates.
    Backend returns a stub user {sub: "dev-user", email: "dev@local", name: "Dev User"}.
    Billing gate is skipped — runs start with plan="pro", no credit check.
    NEVER set this in production.

  GOOGLE_CLIENT_ID
    GCP Console > APIs & Services > Credentials > OAuth 2.0 Client IDs.
    Required for Google OAuth login.

  GOOGLE_CLIENT_SECRET
    Same location as above.

  GOOGLE_REDIRECT_URI
    Must be registered in GCP Console. Default: http://localhost:8000/api/auth/google/callback
    In production: https://yourdomain.com/api/auth/google/callback

  GITHUB_AUTH_CLIENT_ID
    GitHub OAuth App client ID for LOGIN (scope: user:email).
    Can be the same GitHub App as push if you register both redirect URIs.

  GITHUB_AUTH_CLIENT_SECRET
    Secret for the above.

  GITHUB_AUTH_REDIRECT_URI
    Must be registered in the GitHub App. Default: http://localhost:8000/api/auth/github/callback

  GITHUB_CLIENT_ID
    GitHub OAuth App client ID for CODE PUSH (scope: repo).

  GITHUB_CLIENT_SECRET
    Secret for the above.

  GITHUB_REDIRECT_URI
    Must be registered. Default: http://localhost:8000/api/github/callback

  DATABASE_URL
    PostgreSQL connection string. If not set, all DB operations are silent no-ops.
    Local Postgres: postgresql+asyncpg://user:password@localhost:5432/taskmesh
    Cloud SQL via socket: postgresql+asyncpg://user:pass@/dbname?host=/cloudsql/project:region:instance

  PADDLE_API_KEY
    Paddle API secret key. Format: live_... or sandbox_...

  PADDLE_WEBHOOK_SECRET
    Paddle webhook signing secret. Format: pdl_ntf_...

  PADDLE_PRICE_STARTER
    Paddle price ID for the Starter subscription ($30/mo). Format: pri_...

  PADDLE_PRICE_PRO
    Paddle price ID for the Pro subscription ($80/mo). Format: pri_...

  PADDLE_PRICE_PACK_S
    Paddle price ID for Credit Pack S ($20 one-time → $10 credits). Format: pri_...

  PADDLE_PRICE_PACK_M
    Paddle price ID for Credit Pack M ($50 one-time → $25 credits). Format: pri_...

  PADDLE_PRICE_PACK_L
    Paddle price ID for Credit Pack L ($100 one-time → $50 credits). Format: pri_...

  FRONTEND_URL
    Where the frontend runs. Used in OAuth redirects.
    Default: http://localhost:5173
    Production: https://yourdomain.com

  PROJECT_DIR
    Directory where agents write output files. Defaults to current working directory.
    Example: /Users/you/projects/my-output

  UPLOAD_TOKEN_TTL
    Maximum age for upload tokens in seconds before auto-cleanup. Default: 3600 (1 hour).
    Tokens expire after this duration; background task cleans every 5 minutes.

  OPENROUTER_API_KEY
    Used when PROVIDER=openrouter. If set, takes precedence over OPENCODE_GO_API_KEY.
    Both keys are checked at runtime; the provider determines which one is used.

  PROVIDER
    Provider toggle: "zen" (default, OpenCode Zen) or "openrouter" (OpenRouter).
    When set to "openrouter", config_loader.py switches base_url and api_key env var.

  RUN_TIMEOUT_SECONDS
    Per-run timeout in seconds. Runs exceeding this are cancelled automatically.
    Default: 600 (10 minutes). Set to 0 to disable timeout.
    Emits run_timeout Socket.IO event on expiry.

  COOKIE_SAMESITE
    Optional. SameSite policy for the auth cookie. One of "strict" (default,
    local dev), "lax", or "none". Use "none" for split-origin deploys
    (e.g. Vercel frontend + Render backend) so Socket.IO's cross-site
    WebSocket can carry the cookie. "none" forces Secure=true regardless
    of ENVIRONMENT.

  ENVIRONMENT
    Optional. Set to "production" to force the auth cookie's Secure=true
    flag and silence several dev-only RuntimeWarnings. Any other value
    (including unset) is treated as non-production.

  ADMIN_BYPASS_KEY
    Optional. Master key for /api/billing/admin-bypass — granting the
    authenticated user a Pro plan + $9999 credit balance without touching
    Paddle. Used for internal testing only. Generate with:
      python3 -c "import secrets; print(secrets.token_urlsafe(32))"

FRONTEND VARIABLES:

  VITE_AUTH_DISABLED
    Set to "true" to bypass frontend auth check (no redirect to /login) AND onboarding gate
    (BillingGate skips the /api/billing/usage check entirely).
    Backend must also have AUTH_DISABLED=true for API calls to work.
    Only for local development.

  VITE_SOCKET_URL
    Optional. Direct URL for Socket.IO WebSocket connections in production.
    Set in Vercel dashboard to your backend URL so WebSockets bypass Vercel's HTTP-only
    proxy and get true real-time push instead of fallback long-polling.
    Example: VITE_SOCKET_URL=https://taskmesh-api.onrender.com
    In local dev, leave empty — the Vite dev server proxies /socket.io to localhost:8000.


================================================================================
SECTION 5: LOCAL DEVELOPMENT SETUP (NEW DEVELOPER)
================================================================================

Prerequisites:
  - Python 3.11 or higher
  - Node.js 18 or higher
  - npm 9 or higher
  - Git

Step 1: Clone and enter the project
  git clone <repo-url>
  cd MiniMaxClone

Step 2: Set up the backend Python environment
  cd MiniMaxClone  (project root)
  python3 -m venv venv
  source venv/bin/activate       (macOS/Linux)
  venv\Scripts\activate          (Windows)
  pip install -r backend/requirements.txt

Step 3: Configure environment
  cp .env.example .env
  Open .env and fill in at minimum:
    OPENCODE_GO_API_KEY=your-zen-key-here
    AUTH_DISABLED=true
    SECRET_KEY=any-random-string-for-dev

Step 4: Set up the frontend
  cd frontend
  npm install
  cp .env.local.example .env.local
  Open frontend/.env.local and set:
    VITE_AUTH_DISABLED=true

Step 5: Start the backend (Terminal 1)
  From the MiniMaxClone root directory:
  python3 -m uvicorn backend.main:socket_app --reload --port 8000

  CRITICAL: You MUST use "backend.main:socket_app" not "backend.main:app".
  Using app instead of socket_app causes all WebSocket connections to fail with 403.

Step 6: Start the frontend (Terminal 2)
  cd frontend
  npm run dev
  
  Frontend is available at http://localhost:5173
  It proxies /api/* and /socket.io/* to http://localhost:8000

Step 7: Verify it works
  Open http://localhost:5173 in a browser.
  With VITE_AUTH_DISABLED=true you will not be asked to log in, and the billing gate
  is bypassed — you go directly to the main app.
  Type a brief in the input field at the top, click Start.
  You should see agents appearing in the network canvas and activity in the log.

Step 8: (Optional) Enable database persistence
  Install Postgres locally or use a cloud instance.
  Set DATABASE_URL in .env.
  Tables are created automatically at startup via create_tables() in db/session.py.

Step 9: (Optional) Enable OAuth login
  For Google: create an OAuth 2.0 Client ID in GCP Console. Set GOOGLE_CLIENT_ID,
    GOOGLE_CLIENT_SECRET, GOOGLE_REDIRECT_URI. Also set AUTH_DISABLED=false and
    VITE_AUTH_DISABLED=false (or remove them).
  For GitHub login: create a GitHub OAuth App with redirect URI
    http://localhost:8000/api/auth/github/callback. Set GITHUB_AUTH_CLIENT_ID,
    GITHUB_AUTH_CLIENT_SECRET, GITHUB_AUTH_REDIRECT_URI.
  Restart the backend after changing .env.


================================================================================
SECTION 6: RUNNING TESTS
================================================================================

Unit tests (no backend required):
  cd MiniMaxClone
  python -m pytest tests/test_improvements.py -v

  25 tests, all unit tests. Covers:
    - FileLockRegistry (9 tests): acquire, re-acquire, conflict, release, force_acquire,
      release_all, clear, snapshot copy isolation
    - AgentMailbox (7 tests): send, inbox isolation, unread marks as read, full inbox history,
      required fields, multiple types, clear
    - CoordinatorLog (5 tests): record, all entries, copy isolation, clear, default metadata
    - ManagerReviewerExclusion (4 tests): reviewer tag not in prompt, executor tags present,
      planners noted, reviewer excluded by role variant

Integration tests (backend must be running with AUTH_DISABLED=true):
  python -m pytest tests/test_improvements.py -v --integration

  3 integration tests:
    - POST /api/start-project returns "started" or "already running"
    - GET /api/config returns agents list including "reviewer" and "manager"
    - POST /api/cancel returns status or error (idempotent)

Frontend type check:
  cd frontend
  npm run build

  This runs TypeScript compilation then Vite build. Must pass with zero errors.
  There will be a chunk size advisory warning — this is expected and not an error.

ESLint:
  cd frontend
  npm run lint


================================================================================
SECTION 7: DATABASE SCHEMA
================================================================================

All tables are created automatically via SQLAlchemy create_all() at startup.
The DB is accessed via an async session factory. If DATABASE_URL is not set,
get_session() yields None and all DB blocks are skipped silently.

TABLE: users
  Purpose: One row per registered user. Supports email/password and OAuth login.
  Columns:
    id           String(36)   PRIMARY KEY   UUID generated by Python uuid.uuid4()
    email        String(256)  UNIQUE NOT NULL  Stored lowercase, stripped
    name         String(256)  NULLABLE   Display name; defaults to email prefix if blank
    password_hash Text        NULLABLE   bcrypt hash. NULL for OAuth-only accounts.
    google_id    String(128)  UNIQUE NULLABLE  Google user ID from OAuth
    github_id    String(64)   UNIQUE NULLABLE  GitHub user ID (numeric, stored as string) for login OAuth
    created_at   DateTime(tz) NOT NULL   UTC timestamp
  Indexes:
    ix_users_email     on email
    ix_users_google_id on google_id
    ix_users_github_id on github_id
  Notes:
    A user can have a password_hash AND google_id AND github_id simultaneously.
    OAuth callbacks try to link by OAuth ID first, then by email match.
    This lets a user who registered with email/password later log in via Google
    and have their runs merged under the same account.

TABLE: runs
  Purpose: One row per pipeline execution (one "Start" click by a user).
  Columns:
    id          String(36)   PRIMARY KEY   UUID
    user_id     String(128)  NOT NULL      References users.id (no FK constraint — simpler)
    brief       Text         NOT NULL      The user's original input text
    status      String(20)   NOT NULL      Values: running | done | cancelled | error | timeout
    agents_used Text         NULLABLE      JSON array of agent IDs selected in Phase 0
    started_at  DateTime(tz) NOT NULL      UTC timestamp (default: now at insert time)
    finished_at DateTime(tz) NULLABLE      Set when run ends (done, cancelled, or error)
  Relationships:
    files: list of RunFile, cascade delete
  Indexes:
    ix_runs_user_id on user_id

TABLE: run_files
  Purpose: One row per file written by an agent during a run.
  Columns:
    id         Integer     PRIMARY KEY AUTOINCREMENT
    run_id     String(36)  NOT NULL   FK to runs.id with CASCADE DELETE
    path       String(512) NOT NULL   Relative path within PROJECT_DIR (e.g. "src/app.py")
    content    Text        NOT NULL   Full file contents as a string
    size       Integer     NOT NULL   Byte length of content (len(content.encode()))
    created_at DateTime(tz) NOT NULL
  Indexes:
    ix_run_files_run_id on run_id

TABLE: user_usage
  Purpose: Monthly run counter per user. Used for analytics and run count display.
  Columns:
    user_id    String(128)  PRIMARY KEY (composite with year_month)
    year_month String(7)    PRIMARY KEY   Format: "YYYY-MM" (e.g. "2026-05")
    run_count  Integer      NOT NULL DEFAULT 0
    plan       String(20)   NOT NULL DEFAULT "free"   (legacy field — plan gating is now in user_credits)
  Notes:
    Composite primary key (user_id, year_month).
    A new row is created each month per user when they first run.
    run_count is incremented at the start of Orchestrator.run(), not after completion.
    The plan field is legacy from the old billing system. Billing gating now uses user_credits.
    This table is kept for analytics (run counts shown on BillingPage) but no longer gates access.

TABLE: user_credits
  Purpose: Persistent credit balance and plan per user. This is the authoritative billing state.
  Columns:
    user_id         String(128)  PRIMARY KEY   References users.id
    plan            String(20)   NOT NULL DEFAULT "none"   Values: none | starter | pro
    balance_cents   Integer      NOT NULL DEFAULT 0   Credit balance in integer cents
    subscription_id String(128)  NULLABLE   Paddle subscription ID
    updated_at      DateTime(tz) NOT NULL
  Notes:
    balance_cents carries over month-to-month — NOT reset monthly like user_usage.
    It is topped up when a subscription renews (Paddle webhook) or a PAYG pack is purchased.
    It is depleted by actual LLM token usage after each agent.run() call in the orchestrator.
    Users with plan="none" OR balance_cents <= 0 cannot start runs.
    Dev mode (AUTH_DISABLED=true): this table is bypassed; runs always proceed.

TABLE: user_github
  Purpose: Stores GitHub push OAuth tokens. Separate from login OAuth.
  Columns:
    user_id      String(128)  PRIMARY KEY   References users.id
    github_login String(128)  NOT NULL      GitHub username (e.g. "octocat")
    access_token String(256)  NOT NULL      OAuth access token with "repo" scope
    connected_at DateTime(tz) NOT NULL
  Notes:
    This table is for CODE PUSH only (scope: repo). Pro plan only.
    Login OAuth uses users.github_id (scope: user:email).
    access_token is stored in plaintext — encrypt with cryptography.fernet before production.
    One row per user. Overwritten on reconnect.

THERE ARE NO ADDITIONAL TABLES for the multi-agent coordination layer.
FileLockRegistry, AgentMailbox, and CoordinatorLog are in-memory Python objects
created per run in the Orchestrator class. They reset at the start of every run
and are never persisted to the database.

TABLE: tasks (Phase A — DB-backed coordination)
  Purpose: Persisted task queue. Replaces the in-memory SharedTaskList when DATABASE_URL is set.
  Columns: id (int PK), run_id (str, idx), title, description, status (available|claimed|in_progress|completed|blocked|failed),
           assigned_to, created_by, output_files (JSON list), created_at, started_at, completed_at
  Notes: Uses SELECT FOR UPDATE SKIP LOCKED for atomic claiming. Falls back to in-memory list in dev mode.

TABLE: coordinator_events (Phase A)
  Purpose: Persistent audit log. Replaces in-memory CoordinatorLog when DATABASE_URL is set.
  Columns: id (int PK), run_id (str, idx), event_type (str), agent_id, content, metadata_json (JSON), created_at
  Notes: Append-only. Fire-and-forget insert via asyncio.create_task(). Never raises.

TABLE: action_files (Phase B)
  Purpose: Per-agent file operation log. Append-only.
  Columns: id (int PK), run_id, agent_id, task_id, path, op (written|overwritten|conflict|skipped), size_bytes, notes, created_at

TABLE: action_tools (Phase B)
  Purpose: Per-agent LLM call log with retry visibility.
  Columns: id (int PK), run_id, agent_id, task_id, tool_name, model, prompt_tokens, completion_tokens,
           status (ok|retried|failed), attempts, error, duration_ms, created_at

TABLE: task_acceptance (Phase C)
  Purpose: Per-task acceptance criteria evaluated by the reviewer agent.
  Columns: id (int PK), task_id (str), run_id (str, idx), criterion (text), met (bool, default false),
           met_order (int), checked_by, checked_at
  Notes: Append-only except for met/checked_by/checked_at flip during Stage 3b validation.

TABLE: notifications (Polish)
  Purpose: Per-user notification preferences. Stub — no email integration yet.
  Columns: id (int PK), user_id (str), type (subscription_started | credit_low),
           channel (str, default "email"), enabled (bool, default false), created_at
  Index: ix_notif_user_type on (user_id, type) — unique
  Notes: Toggle switches on AccountPage. GET/PUT /api/account/notifications endpoints.


================================================================================
SECTION 8: AUTHENTICATION SYSTEM
================================================================================

BACKEND AUTH (backend/auth/auth.py):

  Algorithm: HS256 JWT signed with SECRET_KEY env var.
  Token expiry: 30 days.
  Token payload: {sub: user_id, email: email, name: name, exp: timestamp, iat: timestamp}

  Functions:
    hash_password(password: str) -> str
      bcrypt.hashpw with auto-generated salt. Returns decoded string for DB storage.

    verify_password(password: str, hashed: str) -> bool
      bcrypt.checkpw comparison.

    create_token(user_id: str, email: str, name: str = "") -> str
      PyJWT encode with HS256 algorithm.

    decode_token(token: str) -> dict
      PyJWT decode. Raises HTTP 401 on ExpiredSignatureError or InvalidTokenError.

    require_auth(credentials: HTTPAuthorizationCredentials = Security(_bearer)) -> dict
      FastAPI Security dependency used on all protected routes.
      If AUTH_DISABLED=true: returns stub {sub: "dev-user", email: "dev@local", name: "Dev User"}
      If credentials missing: raises HTTP 401.
      Otherwise: calls decode_token and returns the payload dict.
      Protected routes access user_id via user.get("sub").

  AUTH DISABLED MODE:
    Backend: AUTH_DISABLED env var set to "true", "1", or "yes".
    Frontend: VITE_AUTH_DISABLED=true in .env.local.
    Both must be set for end-to-end dev mode without real auth.
    When AUTH_DISABLED=true: billing gate in routes.py is also bypassed (plan="pro" assumed).

FRONTEND AUTH (frontend/src/context/auth.tsx):

  Token storage key: localStorage key "agentteam_token"

  AuthProvider wraps the entire app. Provides AuthContext with:
    user: AuthUser | null      {id, email, name} parsed from JWT, or null if not logged in
    token: string | null       Raw JWT string
    getToken() -> Promise<string | null>   Returns current token
    login(token: string)       Validates token, stores to localStorage, updates state
    logout()                   Clears localStorage and resets state

  parseToken(token: string) -> AuthUser | null
    Decodes base64 payload from JWT (atob(token.split('.')[1])).
    Checks exp field: if exp * 1000 < Date.now(), returns null (expired).
    Returns {id: payload.sub, email: payload.email, name: payload.name}.

  On mount: checks localStorage for stored token, calls parseToken.
    If token is expired, removes it and sets user to null.

  Dev mode (VITE_AUTH_DISABLED=true):
    token is set to "dev-token" string.
    user is set to {id: "dev-user", email: "dev@local", name: "Dev User"}.
    No localStorage interaction.

OAUTH FLOWS:

  Google Login:
    Frontend calls GET /api/auth/google/url -> returns {auth_url: string}
    Frontend sets window.location.href = auth_url (full page navigation to Google)
    Google redirects to GOOGLE_REDIRECT_URI with ?code=...
    Backend (GET /api/auth/google/callback):
      1. POST https://oauth2.googleapis.com/token with code + client_id + client_secret
      2. GET https://www.googleapis.com/oauth2/v2/userinfo with access_token
      3. Extract google_id, email, name from userinfo response
      4. Try to find user by google_id in users table
      5. If not found, try by email (links existing email/password account)
      6. If not found, create new user with UUID
      7. Update google_id on user if not already set
      8. create_token(user.id, email, name)
      9. RedirectResponse to FRONTEND_URL/auth/callback#{jwt_token}
    Frontend (AuthCallback.tsx):
      Reads window.location.hash.slice(1) to extract token
      Calls login(token)
      Replaces URL hash with empty string (window.history.replaceState)
      Navigates to / via React Router

  GitHub Login:
    Same flow but different endpoints:
    Frontend calls GET /api/auth/github/url -> returns {auth_url}
    GitHub OAuth scope: user:email
    Backend (GET /api/auth/github/callback):
      1. POST https://github.com/login/oauth/access_token
      2. GET https://api.github.com/user to get id, name, login
      3. GET https://api.github.com/user/emails to get primary verified email
         Picks first email where primary=true AND verified=true
         Falls back to first email in list
         Falls back to login@users.noreply.github.com
      4. Try to find user by github_id, then by email
      5. Create or update user, set github_id
      6. Issue JWT, redirect to /auth/callback#{token}

  Email/Password Registration:
    POST /api/auth/register with {email, password, name}
    Validates: email not empty, password >= 8 chars, email not already registered
    Creates User with bcrypt hash
    Returns {token, user: {id, email, name}}

  Email/Password Login:
    POST /api/auth/login with {email, password}
    Looks up user by lowercase email
    If no user or no password_hash: HTTP 401 (same message for both cases, to prevent enumeration)
    verify_password check
    Returns {token, user: {id, email, name}}

ROUTE PROTECTION:

  Frontend ProtectedRoute component:
    Reads user from useAuthContext()
    If user is null AND VITE_AUTH_DISABLED is not "true": <Navigate to="/login" replace />
    Otherwise: renders children

  Frontend BillingGate component (wraps MainApp only):
    Skipped entirely if VITE_AUTH_DISABLED=true (checked=true immediately, no fetch)
    On mount: fetches GET /api/billing/usage
    If plan === "none": redirects to /billing (user must subscribe before using the app)
    Otherwise: renders children
    On network error: lets user through (fail-open)

  Public routes (no auth needed): /login, /register, /auth/callback
  Protected routes: / (main app, also behind BillingGate), /projects, /billing, /account

  Backend: all routes that use Depends(require_auth) or Security(require_auth) check the JWT.
  Routes without require_auth: /api/auth/register, /api/auth/login, /api/auth/*/url,
    /api/auth/*/callback, /api/billing/webhook, /api/github/callback

GITHUB CODE PUSH OAUTH (separate from login):
  This is a different OAuth flow for getting "repo" scope to push to user repos.
  Frontend (in ProjectsDashboard): calls authFetch('/api/github/auth') -> {auth_url}
  Then sets window.location.href = auth_url (must use authFetch, not a bare link,
    because the endpoint requires a valid JWT to know which user to associate the token with)
  Callback stores token in user_github table.
  The access_token in user_github is separate from any login token.


================================================================================
SECTION 9: API ROUTES — COMPLETE REFERENCE
================================================================================

All routes are prefixed /api/ and served on port 8000.
Auth: "required" means the route checks Authorization: Bearer <jwt> via require_auth.
      "none" means no auth required.

AUTH ROUTES (prefix /api/auth):

  POST /api/auth/register
    Auth: none
    Request body: {email: string, password: string, name?: string}
    Validates: email not empty, password >= 8 chars, email not already in DB
    On success: 200 {token: string, user: {id, email, name}}
    On error: 400 {detail: "Email already registered"} or similar
    On DB unavailable: 503

  POST /api/auth/login
    Auth: none
    Request body: {email: string, password: string}
    On success: 200 {token: string, user: {id, email, name}}
    On failure: 401 {detail: "Invalid email or password"}
    On DB unavailable: 503

  GET /api/auth/google/url
    Auth: none
    Returns: {auth_url: string}  — the Google OAuth authorization URL
    Error if GOOGLE_CLIENT_ID not set: 503

  GET /api/auth/google/callback?code=...&state=...
    Auth: none (called by Google redirect, no JWT)
    Exchanges code, upserts user, issues JWT
    Returns: HTTP 302 redirect to FRONTEND_URL/auth/callback#{jwt}
    Error: 400 if Google token exchange fails

  GET /api/auth/github/url
    Auth: none
    Returns: {auth_url: string}  — GitHub OAuth URL for login (scope: user:email)
    Error if GITHUB_AUTH_CLIENT_ID not set: 503

  GET /api/auth/github/callback?code=...&state=...
    Auth: none
    Exchanges code, gets user + emails, upserts user, issues JWT
    Returns: HTTP 302 redirect to FRONTEND_URL/auth/callback#{jwt}

  GET /api/auth/me
    Auth: required
    Returns: {id: string, email: string, name: string}

ACCOUNT ROUTES (prefix /api/account):

  GET /api/account/profile
    Auth: required
    Returns: {id, name, email, has_password: bool, google_linked: bool, github_linked: bool,
              github_login: string|null, created_at: ISO string|null}
    If DB unavailable: returns data from JWT payload only (no has_password/linked info).

  PUT /api/account/profile
    Auth: required
    Request body: {name: string}
    Updates display name. Issues a fresh JWT with the new name.
    Returns: {status: "updated", name: string, token: string}
    400 if name is empty. 404 if user not found. 503 if DB unavailable.

  PUT /api/account/email
    Auth: required
    Request body: {email: string, password: string}
    Changes email address. Password confirmation required.
    Only works if the account has a password_hash set.
    Issues a fresh JWT with the new email.
    Returns: {status: "updated", email: string, token: string}
    400 if email invalid or account has no password. 401 if wrong password. 400 if email taken.

  PUT /api/account/password
    Auth: required
    Request body: {current_password: string, new_password: string}
    Changes password. If account has no password yet (OAuth-only), current_password is ignored
    and a new password is set directly (effectively "set password" for OAuth users).
    Returns: {status: "updated"}
    400 if new_password < 8 chars. 401 if current_password wrong.

  DELETE /api/account
    Auth: required
    Permanently deletes the account and all associated data:
      Deletes all Run rows (RunFiles cascade). Deletes UserUsage, UserCredits, UserGitHub, User rows.
    Returns: {status: "deleted"}
    Frontend should call logout() and navigate to /login after this.

CORE ROUTES (no prefix beyond /api):

  POST /api/start-project
    Auth: required
    Request body: {brief: string}
    Checks if orchestrator is already running — returns {error: "already running"} if so.
    DEV BYPASS: if AUTH_DISABLED=true OR user_id="dev-user", skips billing gate entirely
      and starts run with plan="pro", agent_limit=None.
    BILLING GATE (production only):
      Loads UserCredits row for the user.
      If plan="none": returns {error: "no_subscription"}
      If balance_cents <= 0: returns {error: "no_credits"}
    Sets agent_limit=3 for Starter plan, None for Pro.
    Creates asyncio.create_task for orchestrator.run(brief, user_id, agent_limit, plan).
    Returns: {status: "started"}

  POST /api/cancel
    Auth: required
    Calls orchestrator.cancel() which cancels the asyncio task.
    Returns: {status: "cancelling"}
    Idempotent — safe to call when nothing is running.

  GET /api/config
    Auth: required
    Returns the contents of agent-team.config.json if it exists.
    Falls back to {sprint, provider: DEFAULT_PROVIDER, agents: DEFAULT_AGENTS}.

  PUT /api/config
    Auth: required — PRO PLAN ONLY
    Request body: any JSON object (the new config)
    If user plan != "pro": 403 {detail: "Shared agent config requires Pro plan"}
    Writes to agent-team.config.json in os.getcwd()
    Returns: {status: "saved"}
    Dev bypass: if AUTH_DISABLED or DB unavailable, gate is skipped.

  GET /api/runs
    Auth: required
    Returns last 50 runs for the authenticated user, ordered by started_at descending.
    Response: array of {id, brief (truncated to 120 chars), status, agents_used (array),
      started_at (ISO string), finished_at (ISO string or null), file_count}
    Returns [] if DB not configured.

  GET /api/runs/{run_id}
    Auth: required
    Returns run with all files. Verifies run.user_id matches authenticated user.
    Response: {id, brief, status, agents_used, started_at, finished_at,
      files: [{path, size, content}]}
    404 if not found or belongs to another user.
    503 if DB not configured.

BILLING ROUTES (prefix /api/billing):

  GET /api/billing/usage
    Auth: required
    DEV BYPASS: if AUTH_DISABLED=true or user_id="dev-user", returns
      {plan: "pro", balance_cents: 4000, run_count: 0}
    Returns: {plan: "none"|"starter"|"pro", balance_cents: int, run_count: int}
    plan and balance_cents come from UserCredits table.
    run_count comes from UserUsage table (current month).
    Returns {plan: "none", balance_cents: 0, run_count: 0} if DB not configured.

  POST /api/billing/checkout
    Auth: required
    Request body: {plan: "starter" | "pro" | "pack_s" | "pack_m" | "pack_l"}
    Creates a Paddle transaction via POST https://api.paddle.com/transactions.
    Passes custom_data.user_id so webhook can identify the user.
    Returns: {checkout_url: string}  — open this in a new tab/window.
    503 if PADDLE_API_KEY not set. 503 if relevant price ID not configured.
    400 if unknown plan value.

  POST /api/billing/webhook
    Auth: none (Paddle calls this)
    Verifies Paddle-Signature header using HMAC-SHA256 with PADDLE_WEBHOOK_SECRET.
    Rejects signatures older than 5 minutes.
    Handles event_type:
      subscription.activated:
        Sets plan to "starter" or "pro" (based on price_id match).
        Adds STARTER_CREDITS_CENTS (1500) or PRO_CREDITS_CENTS (4000) to balance.
        Stores Paddle subscription ID.
      subscription.updated (renewals and plan changes, status=="active"):
        Same as activated — adds another month's credits to balance.
      subscription.cancelled or subscription.paused:
        Sets plan to "none". Remaining balance is preserved.
      transaction.completed (one-time PAYG packs):
        Matches price_id against PADDLE_PRICE_PACK_S/M/L.
        Adds 1000/2500/5000 cents to balance respectively.
    All updates go to user_credits table via _upsert_credits() helper.
    Returns: {ok: true}

GITHUB CODE PUSH ROUTES (prefix /api/github):

  GET /api/github/auth
    Auth: required
    Returns: {auth_url: string}  — GitHub OAuth URL for code push (scope: repo)
    Must be called via authFetch (requires JWT). The auth_url embeds user_id in state param.
    503 if GITHUB_CLIENT_ID not set.

  GET /api/github/callback?code=...&state=...
    Auth: none (GitHub calls this)
    Decodes user_id from state param (base64).
    Exchanges code for access_token.
    Calls GET https://api.github.com/user to get github_login.
    Upserts UserGitHub row with user_id, github_login, access_token.
    Returns: HTTP 302 redirect to FRONTEND_URL/?github=connected

  GET /api/github/status
    Auth: required
    Looks up UserGitHub row for authenticated user.
    Returns: {connected: true, github_login: string} or {connected: false}

  DELETE /api/github/disconnect
    Auth: required
    Deletes UserGitHub row for authenticated user.
    Returns: {status: "disconnected"}

  POST /api/github/push
    Auth: required — PRO PLAN ONLY
    If user plan != "pro": 403 {detail: "GitHub push requires Pro plan"}
    Request body: {run_id: string, repo: string, branch: string}
      repo format: "owner/repo"
      branch: base branch to create PR against (usually "main")
    Verifies GitHub is connected for this user.
    Loads run + files from DB. Errors if run not found or has no files.
    Uses GitHub API (with stored access_token) to:
      1. GET refs/heads/{branch} to get base SHA
      2. POST git/refs to create new branch "taskmesh/{run_id[:8]}"
      3. GET git/commits/{base_sha} to get base tree SHA
      4. POST git/trees with all files as tree items
      5. POST git/commits with message "taskmesh: {brief[:72]}\n\nRun ID: {run_id}"
      6. PATCH git/refs/heads/{branch_name} to update branch to new commit
      7. POST pulls to create PR titled "[TaskMesh] {brief[:60]}"
    Returns: {status: "pushed", branch: string, pr_url: string}
    If PR already exists (422): returns {status: "branch_pushed", branch, pr_url: null}


================================================================================
SECTION 10: SOCKET.IO REAL-TIME PROTOCOL
================================================================================

Socket.IO runs on the same port as FastAPI (8000) via socketio.ASGIApp(sio, other_asgi_app=app).
The frontend connects to path "/socket.io" with transports ["websocket", "polling"].
Vite dev server proxies /socket.io to http://localhost:8000 with ws: true.

On client connect, the backend emits "init" immediately with current config.
All subsequent events are emitted during a pipeline run.

SERVER-TO-CLIENT EVENTS:

  init
    Payload: {project: string, sprint: string, agents: Agent[]}
    Emitted: on connect, and again at the start of each run (after config reload)
    Frontend: INIT action — sets project/sprint/agents

  feature_set
    Payload: {feature: string}
    Emitted: after Phase 2 synthesis, the manager's chosen 3-5 word operation name
    Frontend: FEATURE_SET action — displayed in the header

  tasks_init
    Payload: {tasks: Task[]}  each task: {id, title, tag, done}
    Emitted: after Phase 2, once the manager produces a task breakdown JSON
    Frontend: TASKS_INIT action — populates TasksList sidebar

  agent_update
    Payload: {agentId: string, status: string}
    Status values: idle | thinking | coding | delegating | waiting | done
    Emitted: frequently as each agent changes state
    Frontend: AGENT_UPDATE action — updates individual agent status, drives canvas animations

  task_update
    Payload: {taskId: string}
    Emitted: when an executor completes a task
    Frontend: TASK_UPDATE action — marks task done, updates progress bar

  log_update
    Payload: {time: string, agentId: string, message: string}
    Emitted: for all agent activity messages (truncated to 100 chars)
    Frontend: LOG action — appends to activity feed (capped at 60 entries)
    Also checked for "→ recipient:" pattern — triggers MSG action for network particle animation

  file_update
    Payload: {count: int, files: string[]}
    Emitted: every 2 seconds by the file polling task, also immediately after each file write
    Frontend: FILE_UPDATE action — shows file count and names in sidebar

  terminal_line
    Payload: {line: string}
    Emitted: for git commands, file write confirmations, errors, cancel message
    Frontend: TERMINAL action — appends to terminal panel (capped at 30 lines)

  agents_selected
    Payload: {agentIds: string[]}
    Emitted: after Phase 0 — which agents the manager selected for this run
    Note: for Starter plan, this list is capped at 3 agents before emission.
    Frontend: AGENTS_SELECTED action — dims non-selected agents to 22% opacity on canvas

  run_done
    Payload: {} (empty)
    Emitted: when run finishes (done, cancelled, or error)
    Frontend: DONE action — sets running=false, clears messages/locks, resets selectedAgentIds

  reviewer_started
    Payload: {} (empty)
    Emitted: at the start of Phase 4
    Frontend: REVIEWER_STARTED action — sets reviewerActive=true

  reviewer_result
    Payload: {approved: bool, summary: string, issues: ReviewerIssue[]}
    ReviewerIssue: {file, issue, severity: "Blocker"|"Major"|"Minor", agent}
    Emitted: after reviewer returns its JSON verdict
    Frontend: REVIEWER_RESULT action — sets reviewerActive=false, reviewerResult

  reviewer_retry
    Payload: {agents: string[]}
    Emitted: when reviewer rejects and triggers retry for specific agents
    Frontend: logs a visible entry in LiveActivity

  coordinator_log
    Payload: {entry: {type, content, timestamp, metadata}}
    Decision types: phase_start, agent_assigned, task_created, file_locked, file_conflict,
      auto_commit, reviewer_started, reviewer_approved, reviewer_rejected, feedback_sent,
      retry_started, run_complete
    Frontend: COORD_LOG action — appended to coordLog array (capped at 100 entries)

  file_locked
    Payload: {path: string, agentId: string}
    Emitted: when an agent successfully acquires a file lock
    Frontend: FILE_LOCKED action — adds to fileLocks map

  file_unlocked
    Payload: {path: string, agentId: string}
    Emitted: when an agent releases a file lock after writing
    Frontend: FILE_UNLOCKED action — removes from fileLocks map

  file_conflict
    Payload: {path: string, requestingAgent: string, holdingAgent: string}
    Emitted: when two agents want the same file (last-write wins)
    Frontend: TERMINAL action — shows conflict notice in terminal panel

  mailbox_msg
    Payload: {id, from, to, content, type, timestamp, read}
    Types: message | blocker | feedback | approval
    Emitted: whenever _bus_send() is called in the orchestrator
    Frontend: MAILBOX_MSG action — appended to mailbox array (capped at 50 entries)

  run_resumable (Phase C)
    Payload: {runId: string, brief: string, startedAt: string}
    Emitted: on orchestrator startup if DB has a stale running run
    Frontend: RUN_RESUMABLE action — logs to terminal (future: "Resume?" prompt)

CLIENT-TO-SERVER:
  auth — Emitted immediately after connection with {token: JWT-string}.
    Backend verifies JWT, enters socket into room "user:{user_id}".
    All run-scoped events are emitted only to that room, isolating users.
    Returns {ok: true, room: "user:..."} on success or {ok: false, error: "..."} on failure.


================================================================================
SECTION 11: MULTI-AGENT PIPELINE — COMPLETE FLOW
================================================================================

ENTRY POINT: POST /api/start-project creates a per-user Orchestrator, generates a run_id,
and spawns orchestrator.run(brief, user_id, agent_limit, plan, upload_dir, run_id) via
asyncio.create_task(). Each user gets their own orchestrator + agents — no queueing.
Multiple users can run concurrently (dict[user_id, Orchestrator] singleton replaced).

ARCHITECTURE (3-stage pipeline):
  Stage 1 — Research. The Manager and any planner agents (agents with planner: true)
    concurrently research the project brief. Each planner produces a research report;
    the Manager consolidates them into a research summary. Multi-turn follow-up allowed
    (capped at 2 rounds via AgentMailbox). If no planner agents exist, Manager does
    solo research. Emits stage_start, research_report, research_complete events.
  Stage 2 — Plan. All planner agents concurrently produce domain-specific technical
    specs (architecture, data model, API contracts). Specs are written to
    .taskmesh/plans/{agent_id}.md. The Manager reads all specs + research summary and
    produces a JSON task plan with acceptance criteria per task. Tasks are dispatched
    to SharedTaskList. Multi-turn planning allowed (capped at 2 rounds). Emits
    stage_start, plan_report, plan_complete events.
  Stage 3a — Production (Execution). Executor agents (non-manager, non-reviewer,
    non-planner) run concurrently via SharedTaskList. Each agent: claims a task →
    builds prompt with context (brief, mailbox, planner specs, file summaries) →
    optionally issues <search> blocks → runs agent → parses FILE blocks → writes
    files with lock tracking → auto-commits → marks task complete → loops.
    Monitor loop polls every 2s: task updates (dirty flag), crash snapshots,
    stale claim recovery, run timeout check (RUN_TIMEOUT_SECONDS, default 600s).
  Stage 3b — Validation. Two-tier multi-agent verdict:
    Tier 1: Reviewer + Researcher concurrently evaluate output against acceptance criteria.
    Tier 2: Manager casts tiebreaker if Tier 1 disagrees or finds blocker issues.
    Each agent returns {approved, summary, issues, criteria_results}. If rejected
    and rework_iteration < 1: Manager creates rework tasks, increments rework counter,
    loops back to Stage 3a. If approved: flips task_acceptance.met per verdict,
    writes .taskmesh/validation.json, marks run complete. Emits validation_verdict,
    validation_complete, rework_needed events.

COORDINATION OBJECTS (reset at start of each run, one per-per-user orchestrator):
  SharedTaskList: DB-backed task queue (in-memory fallback when DATABASE_URL unset).
    Agents call claim_task(), start_task(), complete_task() autonomously.
    Status flow: pending → available → claimed → in_progress → completed.
    Persisted to .taskmesh/ for crash recovery. Acceptance criteria stored per task.
  FileLockRegistry: tracks which agent holds exclusive ownership of each file path.
  AgentMailbox: stores typed messages between agents (in-memory list). Used by
    Research and Plan stages for multi-turn conversation between Manager and planners.
  CoordinatorLog: structured log of every coordinator decision. Persisted to DB
    as coordinator_events table (fire-and-forget).

PLAN-BASED RESTRICTIONS (applied before pipeline runs):
  If plan != "pro", models in PRO_ONLY_MODELS are swapped to STARTER_MODEL_FALLBACK
    before _setup_agents() is called.
  agent_limit=3 for Starter; None for Pro.

CREDIT DEDUCTION (fire-and-forget after every agent.run() call):
  base_agent.run() returns dict: {content, thinking_content, prompt_tokens, completion_tokens, model}
  After every agent call: asyncio.create_task(self._deduct_credits(result))
  _deduct_credits() calls billing.calc_cost_cents() and subtracts from UserCredits.balance_cents.
  Also logs a ZenUsage row per call for analytics/spend tracking.
  Pre-run credit estimate returned in start-project response as credit_warning field.

RUN TIMEOUT:
  Configurable via RUN_TIMEOUT_SECONDS env var (default 600s = 10 minutes).
  Monitor loop checks elapsed time; cancels run and emits run_timeout event.

RENAMING NOTE: The old terminology "Phase 1–5" was replaced with "Stage 1–3" in May 2026.
  Old Phase 1 = Stage 2 (Plan), old Phase 2+3 = Stage 3a (Production),
  old Phase 4 = Stage 3b (Validation), old Phase 5 = Finalize.
  The coordinator log still uses event_type "phase_start" for backward compatibility.

FILE WRITING (_write_files_from_parsed):
  Agents output files in the format: --- FILE: path --- / content / --- END FILE ---
  Parsed by regex. Path traversal protection. FileLockRegistry acquires/releases per file.
  RunFile rows stored in DB.

AUTO-COMMIT (_auto_commit):
  git add -- {files} then git commit -m "feat({agent_id[:6]}): {task_title[:60]}"
  Silently swallowed if git not initialized or fails. Run continues regardless.

CANCELLATION:
  Frontend POST /api/cancel → routes.py looks up user's orchestrator by user_id →
  orchestrator.cancel() sets _cancel_requested=True, then cancels _run_task.
  Agent loops check _cancel_requested on each iteration and exit cleanly.
  asyncio.CancelledError propagates, run sets status to "cancelled", emits run_done.


================================================================================
SECTION 12: AGENT CONFIGURATION
================================================================================

The runtime config is hot-loaded at the start of each run from the per-user `users.config_json`
column (Pro users) or the disk file `agent-team.config.json` (Starter users / global default).
Users can edit their config via the Settings panel in the UI (GET /api/config, PUT /api/config).
PUT /api/config is Pro plan only; writes to the user's DB row, not the shared file.

Top-level fields:
  sprint: string  — displayed in the header (e.g. "Sprint #1")
  provider.name: string  — display name (e.g. "OpenCode Zen")
  provider.baseURL: string  — OpenAI-compatible API base URL
  provider.apiKey: string  — API key; if empty, fallback to OPENCODE_GO_API_KEY env var
  agents: array of agent config objects

Per-agent fields:
  id: string          — unique identifier; controls routing in the pipeline
  name: string        — display name shown in the UI
  role: string        — role label shown in the UI
  model: string       — model ID string passed directly to the API
  temperature: float  — 0.0 to 1.0
  top_p: float        — nucleus sampling
  top_k: int          — top-k sampling (0 = disabled)
  thinking_budget: int — 0 = thinking disabled; >0 = thinking token limit
  planner: bool       — true = runs in Stages 1-2 (research + plan) instead of Stage 3a (execution)
  color: string       — hex color for canvas node
  icon: string        — emoji for canvas node
  system_prompt: string — override system prompt; if empty, uses built-in defaults

SPECIAL ID RULES:
  id == "manager"    — runs Stage 2 (creates task plan); participates in Stage 1 (research)
                       and Stage 3b (validation tiebreaker). Excluded from executors.
  id == "reviewer"   — runs Stage 3b (validation) only. Excluded from executors.
  planner: true      — runs Stages 1-2 (research + plan specs) concurrently with other planners.
                       Excluded from Stage 3a executors.

THINKING BUDGET (active — 2026-05-21):
  THINKING_MODEL_IDS: 14 models (Kimi, Qwen, MiMo, GLM, DeepSeek). Uses chat_template_kwargs
    via extra_body: {"enable_thinking": bool} with optional thinking_budget for Kimi/DeepSeek.
  ANTHROPIC_THINKING_MODEL_IDS: 8 Claude models. Uses top-level thinking parameter:
    {"type": "enabled", "budget_tokens": N} in messages.create().
  When thinking_budget=0 but model is in thinking set: explicitly disables thinking
    (prevents default-on behavior). When thinking_budget=0 and model not in set: silently skipped.
  Thinking content extracted separately from Anthropic responses (content blocks of type "thinking").
  Emitted via thinking_content Socket.IO event. Slider available in SettingsPanel.

BASE_AGENT.RUN() RETURN VALUE:
  run() returns a dict, NOT a bare string:
    {"content": str, "prompt_tokens": int, "completion_tokens": int, "model": str}
  All callers in orchestrator.py unpack this: result["content"] for the LLM text.
  Token counts are passed to _deduct_credits() for billing.


================================================================================
SECTION 13: OPENROUTER INTEGRATION (INACTIVE)
================================================================================

OpenRouter is written but commented out. It is NOT the active provider.

To switch from OpenCode Zen to OpenRouter:

Step 1: Set OPENROUTER_API_KEY in .env

Step 2: In backend/agents/base_agent.py:
  Uncomment the block between "── OpenRouter (inactive" and "── End OpenRouter ──"
  This block defines:
    OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
    OPENROUTER_EXTRA_HEADERS = {"HTTP-Referer": ..., "X-Title": "TaskMesh"}
    _get_openrouter_client() function

Step 3: In backend/core/config_loader.py:
  Uncomment the OPENROUTER_BASE_URL and OPENROUTER_DEFAULT_AGENTS lists.
  Replace DEFAULT_BASE_URL with OPENROUTER_BASE_URL.
  Replace DEFAULT_AGENTS model IDs with OpenRouter equivalents.
  Change the env var lookup line from OPENCODE_GO_API_KEY to OPENROUTER_API_KEY.

Note: The MODEL_PRICING table in billing.py uses Zen model IDs. A mapping to
  OpenRouter equivalents would need to be added when switching.


================================================================================
SECTION 14: FRONTEND ARCHITECTURE
================================================================================

ENTRY POINT (frontend/src/main.tsx):
  Renders: <BrowserRouter><AuthProvider><App /></AuthProvider></BrowserRouter>
  No Clerk. No other providers. Straightforward.

APP ROUTING (frontend/src/App.tsx):
  ProtectedRoute: reads user from useAuthContext(). If null and not AUTH_DISABLED, navigates to /login.
  BillingGate: wraps Dashboard only. Fetches /api/billing/usage on mount. If plan="none", redirects
    to /billing. Skipped entirely if VITE_AUTH_DISABLED=true. Renders null while checking.

  Routes (post 2026-05-22 dashboard refactor):
    /login         -> LoginPage (public)
    /register      -> RegisterPage (public)
    /auth/callback -> AuthCallback (public)
    /              -> ProtectedRoute > BillingGate > Dashboard (new TM dash landing page)
    /project/:id   -> ProtectedRoute > Workspace (project-specific agent view, was MainApp)
    /billing       -> BillingPage (protected)
    /settings      -> AccountPage (protected, was /account)

  Workspace (was MainApp) is a function inside App.tsx.
  Workspace layout:
    Back to Dashboard link · breadcrumb · project controls · AgentNetwork · Sidebar · Activity
    No billing/account navigation (those live on Dashboard).
    Header at top (includes account pill → /account)
    Horizontal split: canvas area (flex-1) + resizable Sidebar (180-520px, default 240px)
    Resize handle between canvas and sidebar (drag left-right)
    LiveActivity panel at bottom (50-360px, default 88px, drag up-down)
    SettingsPanel as an overlay (hidden by default, opened from ⚙ Settings button in Header)

HEADER (Header.tsx):
  Left: TASKMESH breadcrumb (project › sprint › feature)
  Center: expandable brief textarea + Start/Stop button
  Right: progress bar + timer + ⚙ Settings button + 📁 projects link + ✦ billing link
         + user pill (displays user.name or email prefix, links to /account)
  The user pill always navigates to /account and never calls logout().
  logout() is only called from AccountPage (sign out button) or AuthContext explicitly.

STATE MANAGEMENT (frontend/src/hooks/useSocket.ts):
  useReducer with ProjectState as state shape.
  All state transitions go through the reducer.
  Socket events dispatch typed actions.

THEMES (frontend/src/themes.ts):
  Themes set CSS custom properties on :root via JavaScript.
  Stored in localStorage under "agentteam-theme".
  CRITICAL RULE: Input backgrounds MUST use --c-input-bg (solid color), NEVER --c-surface-3
    (which is rgba(255,255,255,0.04) — 4% opacity, causes invisible white text on dark themes).
  This applies to inputs, textareas, dropdowns, and any popup that needs an opaque background.

BILLING PAGE (BillingPage.tsx):
  Fetches GET /api/billing/usage on mount.
  Polls every 30 seconds while a run is active (state.running) for live balance updates.
  Layout: centered horizontally with maxWidth 780px, balanced whitespace on both sides.
  Structure:
    No-plan yellow banner (if plan="none")
    Credit balance card (if on a plan):
      Shows large percentage (e.g. "87%") with colored fill bar
      Green → amber (< 25%) → red (< 10%)
      Low/warning messages shown when credits are running low
      NO dollar amounts — usage is percentage-only
    Plan cards (Starter / Pro side-by-side, responsive grid):
      Shows features list, price in dollars, CTA button if not current plan, "CURRENT" badge if current
    Pay-as-you-go packs section:
      3 buttons: Add $10 ($20), Add $25 ($50), Add $50 ($100) — prices in dollars (payment-related)
      Disabled if plan="none" (requires subscription to top up)
    Admin bypass (hidden trigger at bottom):
      Invisible "·" button opens key input
      On valid key: grants pro plan with 999999 cents, redirects to dashboard (/)

ACCOUNT PAGE (AccountPage.tsx):
  Route: /account (protected). Accessed via user pill in Header.
  Sections:
    Profile: display name (editable), email + join date
    Email address: change email (requires password confirmation; hidden if no password set)
    Security: change password or set first password (for OAuth-only accounts)
    Connected accounts: Google and GitHub linked status with badges
    Session: Sign out button
    Danger zone: type "DELETE" to confirm account deletion (calls DELETE /api/account)
  On successful name/email change: calls login(new_token) to refresh JWT and update header pill.

SIDEBAR (Sidebar.tsx):
  Right panel container: agents + tasks + files + terminal.
  The AGENTS heading has a "+ Add agents" button that opens the Settings panel.
  All sections have borders separating them. Reviewer panel appears when active or results exist.

SETTINGS PANEL (SettingsPanel.tsx):
  Opens as a slide-in overlay from the right.
  Loads current config via GET /api/config (per-user, from DB).
  Two tabs: "Project Settings" and "Account".
  Project Settings tab: theme picker, sprint label, OpenCode Zen API key, agent roster.
  Account tab: navigates to the dedicated /account page.
  Footer: Close button, Save & Apply button (project tab only).

PROJECTS DASHBOARD (ProjectsDashboard.tsx):
  Three-column layout: run list | file list | file content viewer
  GitHub push bar: appears for "done" runs with files.
    If not connected: shows "Connect GitHub" → calls /api/github/auth → redirect.
    If connected: shows repo/branch inputs + "Push to GitHub" button.
    Note: /api/github/push requires Pro plan (403 for Starter).

LOGIN PAGE (LoginPage.tsx):
  Email/password form + Google OAuth + GitHub OAuth buttons.

REGISTER PAGE (RegisterPage.tsx):
  Name + email + password + confirm password + Google/GitHub OAuth.

AUTH CALLBACK PAGE (AuthCallback.tsx):
  Reads JWT from window.location.hash, calls login(), navigates to /.


================================================================================
SECTION 15: BILLING AND SUBSCRIPTION LOGIC
================================================================================

PLAN SYSTEM:
  No free tier. Every user must have an active subscription to start runs.
  Plans stored in user_credits.plan (not user_usage.plan which is legacy).

  Starter ($30/mo):
    $15 credits (1500 cents) added to balance on subscription.activated
    Max 3 agents per run (agent_limit=3 passed to orchestrator)
    Standard models only (Pro-only models downgraded to STARTER_MODEL_FALLBACK)
    PUT /api/config blocked (403)
    POST /api/github/push blocked (403)

  Pro ($80/mo):
    $40 credits (4000 cents) added to balance on subscription.activated
    All 9 agents per run (agent_limit=None)
    All models including flagship
    Full feature access

  Renewals: subscription.updated with status="active" adds another month's credits (same amounts).
  Cancellation: plan set to "none", remaining balance preserved.

PAYG PACKS (one-time, no expiry):
  Pack S: $20 → +$10 (1000 cents)
  Pack M: $50 → +$25 (2500 cents)
  Pack L: $100 → +$50 (5000 cents)
  Packs add to the balance of an existing subscription. Subscription still required to run.
  Handled by transaction.completed webhook event matching PADDLE_PRICE_PACK_S/M/L.

CREDIT DEPLETION:
  base_agent.run() returns {content, prompt_tokens, completion_tokens, model}.
  orchestrator._deduct_credits(result) calculates cost and subtracts from balance_cents.
  Formula (in billing.calc_cost_cents):
    p, c = MODEL_PRICING.get(model, DEFAULT_PRICING)  # cents per 1000 tokens
    cost  = max(1, int((prompt_tokens * p + completion_tokens * c) / 1000))
  Called after every agent call (selector, planners, manager, executors, reviewer).
  Fire-and-forget via asyncio.create_task — never blocks a run.
  balance_cents is floored at 0 (never goes negative).

  DISPLAY RULE: Balance is shown as a percentage on the frontend (BillingPage BalanceBar
  component). The percentage is calculated as (balance_cents / allocatedCents) * 100.
  NO dollar amounts are displayed for usage/credits anywhere in the application.
  Only payment-related items (plan prices like "$30/mo", pack costs like "Add $10") use
  dollar values. This policy ensures users think in terms of credit consumption rate, not
  absolute dollar values.

MODEL PRICING TABLE (billing.py — cents per 1000 tokens, prompt / completion):
  46 models across 3 tiers. Full table in backend/api/billing.py.

  Flagship / Pro-only (prompt >0.2¢/1K → ~$2/M+):
    deepseek-v4-pro   (0.014, 0.028) · glm-5.1 (0.010, 0.020) · kimi-k2.6 (0.014, 0.028)
    mimo-v2.5-pro     (0.012, 0.024) · minimax-m2.7 (0.014, 0.028) · qwen3.6-plus (0.006, 0.012)
    claude-opus-4-1   (1.500, 7.500) · claude-opus-4-5/4-6/4-7 (0.500, 2.500)
    claude-sonnet-4/4-5/4-6          (0.300, 1.500)
    gpt-5/5.1/5.2/5.5                (0.250, 1.000)
    gpt-5-codex / 5.1-codex / max / 5.2-codex / 5.3-codex (0.300, 1.200)
    gpt-5.4-pro / gpt-5.5-pro        (0.500, 2.000) · gpt-5.4 (0.250, 1.000)
    gemini-3.1-pro                    (0.350, 1.400)

  Balanced (Starter OK):
    deepseek-v4-flash (0.174, 0.348) · glm-5 (0.008, 0.016) · kimi-k2.5 (0.010, 0.020)
    mimo-v2.5 (0.008, 0.016) · minimax-m2.5 (0.030, 0.240) · qwen3.5-plus (0.004, 0.008)
    claude-haiku-4-5  (0.100, 0.500)
    gpt-5.1-codex-mini (0.100, 0.400) · gpt-5.3-codex-spark (0.100, 0.400)
    gpt-5.4-mini (0.050, 0.200)
    gemini-3-flash / gemini-3.5-flash (0.015, 0.060)

  Budget (Starter OK):
    nemotron-3-super (0.010, 0.050) · deepseek-v4-flash-free (0.174, 0.348)
    big-pickle (0.010, 0.050) · nemotron-3-super-free (0.010, 0.050)
    minimax-m2.5-free (0.030, 0.240) · gpt-5-nano / gpt-5.4-nano (0.025, 0.100)
    grok-build-0-1 (0.0005, 0.0010) [unconfirmed]

  DEFAULT (unknown): (0.020, 0.020)

PRO_ONLY_MODELS (frozenset in billing.py):
  26 models total. Threshold: prompt cost > 0.2¢/1K (~$2/M input).
  All Flagship models + claude-sonnet-* + gpt-5/5.1/5.2 + gpt-*-codex +
  gpt-5.4-pro/5.5-pro/5.4/5.5 + gemini-3.1-pro.

DEV BYPASS:
  When AUTH_DISABLED=true OR user_id="dev-user":
    routes.py: skips billing gate, starts run with plan="pro", agent_limit=None
    billing.py GET /usage: returns {plan: "pro", balance_cents: 4000, run_count: 0}
    Frontend BillingGate: skips check entirely (VITE_AUTH_DISABLED=true)

BILLING GATE ERRORS (from POST /api/start-project):
  {error: "no_subscription"} — user has plan="none"
  {error: "no_credits"}      — user has plan but balance_cents <= 0

WEBHOOK SECURITY:
  HMAC-SHA256 with PADDLE_WEBHOOK_SECRET.
  Signature format in Paddle-Signature header: "ts=1234567890;h1=hexdigest"
  Signed string: "{ts}:{raw_body}"
  Rejects webhooks older than 5 minutes (|time.time() - ts| > 300).


================================================================================
SECTION 16: GITHUB CODE PUSH WORKFLOW
================================================================================

After a run completes, Pro users can push all output files to a GitHub repository as a PR.
Starter users get 403 when attempting to push.

Prerequisites:
  User must have Pro plan.
  User must connect GitHub push OAuth (separate from login).
  The connected token needs "repo" scope.
  Run must have status "done" and at least one output file.

Push flow:
  1. User enters "owner/repo" and target branch in ProjectsDashboard
  2. POST /api/github/push {run_id, repo, branch}
  3. Backend checks plan (403 if not Pro)
  4. Loads all run files from DB
  5. Creates branch "taskmesh/{run_id[:8]}" from base branch
  6. Builds git tree from all files
  7. Creates commit: "taskmesh: {brief[:72]}\n\nRun ID: {run_id}"
  8. Updates branch to point at new commit
  9. Creates PR titled "[TaskMesh] {brief[:60]}" with body showing file count, date, run ID
  10. Returns {status: "pushed", branch, pr_url}

If PR already exists (422 from GitHub): returns {status: "branch_pushed", pr_url: null}
GitHub API version header: X-GitHub-Api-Version: 2022-11-28


================================================================================
SECTION 17: SETUP FOR EXTERNAL SERVICES
================================================================================

GOOGLE CLOUD SQL SETUP:
  1. Go to GCP Console -> SQL -> Create Instance -> PostgreSQL
  2. Choose instance ID, region, password for "postgres" user
  3. In Connections tab: enable Public IP (or use Private for production)
  4. Create a database: GCP Console -> SQL instance -> Databases -> Create
  5. Create a user: Users -> Add user account
  6. For local dev connection (with public IP):
     DATABASE_URL=postgresql+asyncpg://username:password@<public-ip>:5432/dbname
     You may need to add your IP to "Authorized networks" in the Connections tab.
  7. For Cloud Run / GKE connection (Cloud SQL socket):
     Enable Cloud SQL Admin API in GCP.
     Add the Cloud SQL Client IAM role to the service account running your app.
     DATABASE_URL=postgresql+asyncpg://user:pass@/dbname?host=/cloudsql/project:region:instance
  8. Tables are created automatically at startup — no manual migrations needed.
  IMPORTANT: asyncpg with special characters in password requires keyword args, not a URL string.
    The db/session.py file handles this correctly.

GOOGLE OAUTH SETUP:
  1. GCP Console -> APIs & Services -> OAuth consent screen
     Choose "External", fill in app name, support email, developer contact.
     Add scopes: email, profile, openid.
     Add test users if in testing mode.
  2. GCP Console -> APIs & Services -> Credentials -> Create Credentials -> OAuth client ID
     Application type: Web application
     Authorized redirect URIs: http://localhost:8000/api/auth/google/callback
  3. Copy client ID and client secret to .env as GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET.

GITHUB OAUTH APP SETUP (for login and/or push):
  1. GitHub.com -> Settings -> Developer settings -> OAuth Apps -> New OAuth App
  2. Application name: TaskMesh
  3. Homepage URL: http://localhost:5173
  4. Authorization callback URL: add both:
     http://localhost:8000/api/auth/github/callback  (for login)
     http://localhost:8000/api/github/callback       (for push)
  5. Register application. Copy Client ID and generate Client Secret.
  6. For login: set GITHUB_AUTH_CLIENT_ID, GITHUB_AUTH_CLIENT_SECRET, GITHUB_AUTH_REDIRECT_URI
  7. For push: set GITHUB_CLIENT_ID, GITHUB_CLIENT_SECRET, GITHUB_REDIRECT_URI
  8. Both can use the same GitHub OAuth App if both redirect URIs are registered.

PADDLE SETUP (5 products required):
  1. Create account at paddle.com. Use sandbox for testing.
  2. Create 2 subscription products:
     "TaskMesh Starter" — recurring, $30/month → note price ID → PADDLE_PRICE_STARTER=pri_...
     "TaskMesh Pro"     — recurring, $80/month → note price ID → PADDLE_PRICE_PRO=pri_...
  3. Create 3 one-time products:
     "Credit Pack S" — one-time, $20 → PADDLE_PRICE_PACK_S=pri_...
     "Credit Pack M" — one-time, $50 → PADDLE_PRICE_PACK_M=pri_...
     "Credit Pack L" — one-time, $100 → PADDLE_PRICE_PACK_L=pri_...
  4. Developer Tools -> Authentication -> API Keys -> Create API key. Set as PADDLE_API_KEY.
  5. Developer Tools -> Notifications -> New destination:
     URL: https://yourdomain.com/api/billing/webhook
     Events to send: subscription.activated, subscription.updated, subscription.cancelled,
       subscription.paused, transaction.completed
  6. Copy webhook signing secret (format: pdl_ntf_...) to PADDLE_WEBHOOK_SECRET.
  7. For local webhook testing: use ngrok tunnel and register that URL in Paddle dashboard.


================================================================================
SECTION 18: DEPLOYMENT
================================================================================

The app is designed to run on Google Cloud Run or GKE, but any platform that supports
Docker containers and can connect to Cloud SQL will work.

BACKEND DEPLOYMENT:
  Serve with: uvicorn backend.main:socket_app --host 0.0.0.0 --port 8080

  Docker build (write your own Dockerfile):
    FROM python:3.11-slim
    WORKDIR /app
    COPY backend/requirements.txt .
    RUN pip install -r requirements.txt
    COPY . .
    CMD ["python", "-m", "uvicorn", "backend.main:socket_app", "--host", "0.0.0.0", "--port", "8080"]

  Environment variables must be set in Cloud Run via GCP Console or gcloud CLI.
  For Cloud SQL: add Cloud SQL connection in Cloud Run settings, not just the socket path.

FRONTEND DEPLOYMENT:
  Build: cd frontend && npm run build
  Output: frontend/dist/ (static HTML/JS/CSS)
  Deploy to Firebase Hosting, Vercel, GCP Cloud Storage + CDN, or any static host.
  The built frontend must have VITE_AUTH_DISABLED not set (or set to "false").
  The /api proxy only works in development. In production, CORS allows the frontend
  to call the backend directly.

CORS IN PRODUCTION:
  CORS_ALLOWED_ORIGINS env var controls both FastAPI CORSMiddleware and Socket.IO origins.
  Defaults to "*" for dev; set to comma-separated frontend URL(s) in production.

ROLLBACK:
  No automated rollback. Database schema is additive (create_all with checkfirst).
  Always use nullable columns or provide defaults for safe forward-only migrations.


================================================================================
SECTION 19: LOGGING AND MONITORING
================================================================================

BACKEND LOGS:
  print() statements for Socket.IO connection events.
  Error messages emitted to frontend via terminal_line events.
  Uvicorn logs all HTTP requests to stdout.
  No structured logging (no JSON format, no request IDs). Known gap for production.

FRONTEND LOGS:
  console.error in useSocket.ts for startProject and cancelProject network failures.

MONITORING:
  No monitoring configured. For production:
  - Add GET /api/health -> {status: "ok"} health check endpoint
  - Cloud Monitoring uptime checks
  - Cloud Monitoring alert on 5xx response rate
  - Error Reporting for Python exceptions in Cloud Run


================================================================================
SECTION 20: CODE CONVENTIONS
================================================================================

COMMIT MESSAGE FORMAT:
  Conventional commits: feat({scope}): {description}
  The orchestrator auto-generates: feat({agent_id[:6]}): {task_title[:60]}

PYTHON STYLE:
  Python 3.11+ features (union types with |, type hints).
  from __future__ import annotations used in auth.py and orchestrator.py.
  Async/await throughout. SQLAlchemy ORM with async sessions only.
  All DB access: "async with get_session() as session: if session is not None:"
  Billing failures MUST be wrapped in try/except and must never block runs.

TYPESCRIPT STYLE:
  Strict mode. TypeScript 6.0.2.
  useReducer for complex state (useSocket.ts). useState for local component state.
  No prop drilling — useAuthContext() and useAuthFetch() are used via context/hooks.

TAILWIND:
  Utility classes for layout. CSS custom properties (var(--c-*)) for all colors.
  Exception: status badge colors in ProjectsDashboard are hardcoded hex.

INPUT BACKGROUNDS:
  Always use inputStyle() in SettingsPanel and similar components:
    { background: 'var(--c-input-bg)', border: '1px solid var(--c-border)', color: 'var(--c-text-1)' }
  NEVER use var(--c-surface-3) for backgrounds — it is 4% opacity and causes invisible text.

FILE WRITING PROTOCOL:
  [FILE: path/relative/to/project/root]
  ...complete file content...
  [/FILE]
  Regex: r'\[FILE:\s*([^\]\n]+)\]\n?(.*?)\n?\[/FILE\]' with DOTALL flag.
  Path traversal protection: target.resolve() must start with PROJECT_DIR.resolve().

EXCLUSIVE FILE OWNERSHIP:
  FileLockRegistry tracks which agent holds each path.
  Last-write wins on conflict. Conflicts logged and emitted as file_conflict events.
  Locks acquired before writing, released immediately after.

MAILBOX CONVENTION:
  All cross-agent communication goes through _bus_send().
  Executor prompts include mailbox.unread(agent_id) before calling the LLM.
  This is how reviewer feedback reaches executors in the retry phase.


================================================================================
SECTION 21: KNOWN ISSUES, EDGE CASES, AND LIMITATIONS
================================================================================

FIXED ISSUES (listed for historical awareness):
  1. max_tokens was 512 in BaseAgent — caused truncated output. Fixed to 8192.
  2. GitHub connect button was a plain anchor — fixed to use authFetch().
  3. startProject dispatched START before backend responded. Fixed to check data.status.
  4. @app.on_event("startup") deprecated in FastAPI 0.115+. Fixed to use lifespan.
  5. JSX inline comment syntax error in ProjectsDashboard.tsx. Fixed.
  6. TypeScript TS6133: LiveActivity unused "height" prop. Fixed.
  7. TypeScript TS2783: SettingsPanel duplicate keys in spread. Fixed.
  8. TypeScript TS2322: updateAgents type mismatch. Fixed.
  9. Settings dropdown invisible on dark themes (--c-surface-3 was 4% opacity). Fixed.
 10. Sprint/API key inputs had white backgrounds on dark themes (missing inputStyle). Fixed.
 11. Settings button showed a dropdown — simplified to a direct button opening the panel. Done.
 12. Clicking account name in header caused logout (old Clerk UserButton remnant). Fixed:
     Header now shows a user pill that links to /account. logout() only in AccountPage.
 13. BillingPage showed old Free/Pro/Team plans. Replaced with Starter/Pro + PAYG packs.
 14. base_agent.run() discarded response.usage. Fixed: now returns token counts in dict.
 15. BillingPage left-aligned with dead space on right. Fixed: centered layout with
     `flex justify-center items-start` and `maxWidth: 780`.
 16. Balance displayed as dollar amount (e.g. "$9999.99 remaining"). Fixed: now shows
     percentage only (e.g. "87%"). No dollar amounts for usage anywhere in the app.
 17. Admin bypass did not redirect after granting access. Fixed: `navigate('/')` called
     after `fetchUsage()` so BillingGate sees updated plan and allows passage.

OPEN ISSUES:
   1. GitHub access_token in user_github stored in plaintext. Encrypt before production.
   2. File locks are last-write-wins, not true mutual exclusion.
   3. Auto-commit only works if PROJECT_DIR is inside a git repository.
   4. No health check endpoint (GET /api/health).
   5. run_count in user_usage is incremented at run start, not completion.
   6. No persistent mailbox — messages lost on server restart.
   7. No rate limiting on any API endpoints.
   8. No email verification for email/password registration.
   9. Agent config (agent-team.config.json) is per-server, not per-user.
      Two users changing config simultaneously: one's change wins.
  10. Upload tokens are in-memory only — lost on backend restart.

LIMITATIONS:
   - Agent LLM calls are sequential within an agent; agents within the team run concurrently.
   - Coordinator does not read existing codebase before planning.
   - Theme is stored in localStorage, not in user profile.
   - PAYG packs require an active subscription to use (packs alone don't unlock runs).
   - No reviewer phase in current pipeline (reviewer agent is excluded from executor loop).
   - Socket.IO events are scoped to user:{id} rooms for multi-user isolation.


================================================================================
SECTION 22: FILE REFERENCE INDEX
================================================================================

Read these files in this order when exploring the codebase:

1. backend/main.py
   FastAPI app construction. Socket.IO server. Lifespan for DB init.
   Router includes: auth, billing, github, account, core routes.

2. backend/core/orchestrator.py
   The heart of the system. FileLockRegistry, AgentMailbox, CoordinatorLog classes.
   Orchestrator.run() with agent_limit and plan params.
   _deduct_credits() fire-and-forget billing after each agent call.
   All 5 pipeline phases. File writing with lock tracking. Auto-commit.

3. backend/core/config_loader.py
   DEFAULT_AGENTS list with all 9 agents and their default models.
   ProjectConfig and ProviderConfig dataclasses. load_config() and save_config().

4. backend/agents/base_agent.py
   BaseAgent class. run() returns dict with {content, prompt_tokens, completion_tokens, model}.
   THINKING_MODEL_IDS set. thinking_budget and top_k via extra_body.

5. backend/agents/manager_agent.py
   ManagerAgent subclass. build_manager_system() function.

6. backend/auth/auth.py
   JWT signing and verification. bcrypt helpers. require_auth dependency.
   AUTH_DISABLED returns stub user AND skips billing gates.

7. backend/api/auth.py
   All auth endpoints. Google OAuth callback. GitHub login OAuth callback.
   User upsert logic. Hash-fragment JWT redirect pattern.

8. backend/api/routes.py
   Core REST endpoints. Billing gate (no_subscription / no_credits) with dev bypass.
   PUT /api/config gated to Pro plan.

9. backend/api/billing.py
   MODEL_PRICING table. PRO_ONLY_MODELS frozenset. STARTER_MODEL_FALLBACK.
   calc_cost_cents() function. Paddle checkout (5 plan types). Webhook handler.
   GET /usage returns plan + balance_cents + run_count. Dev bypass.

10. backend/api/account.py
    Account management: GET/PUT profile, PUT email, PUT password, DELETE account.
    Updates issue fresh JWTs with login() on name/email change.

11. backend/api/github.py
    Code-push OAuth. Push-to-PR flow using GitHub Trees API.
    POST /push gated to Pro plan (403 for Starter).

12. backend/db/models.py
    All SQLAlchemy models. UserCredits is the authoritative billing state.

13. backend/db/session.py
    Async session factory. No-op when DATABASE_URL not set. create_tables().

14. frontend/src/context/auth.tsx
    AuthProvider and AuthContext. parseToken. Login/logout. Dev mode.

15. frontend/src/hooks/useSocket.ts
    All Socket.IO event handlers. State reducer with all actions.
    startProject and cancelProject functions.

16. frontend/src/App.tsx
    Route structure. ProtectedRoute. BillingGate. MainApp layout with drag-resize panels.

17. frontend/src/types/index.ts
    Complete TypeScript type definitions for all state.

18. frontend/src/pages/BillingPage.tsx
    Credit balance bar, Starter/Pro plan cards, PAYG pack buttons, live polling.

19. frontend/src/pages/AccountPage.tsx
    Profile, email, password, OAuth providers, sign out, delete account.

20. frontend/src/pages/ProjectsDashboard.tsx
    Run history UI. File browser. GitHub push integration (Pro only).

 21. frontend/src/components/SettingsPanel.tsx
     Most frequently edited file. Agent configuration UI. All inputs use inputStyle().
     Contains RECOMMENDED_LAYOUT constant with the 9-agent recommended mapping.
     "+ Add" button adds preset agents. "Recommended layout" button replaces all agents.

22. tests/test_improvements.py
    25 unit tests. Good examples of how coordination classes work.

23. agent-team.config.json
    Current runtime config with all 9 agents and their actual system prompts.


================================================================================
SECTION 23: QUICK COMMANDS
================================================================================

Start backend (dev):
  cd MiniMaxClone
  source venv/bin/activate
  python3 -m uvicorn backend.main:socket_app --reload --port 8000

Start frontend (dev):
  cd MiniMaxClone/frontend
  npm run dev

Run tests:
  cd MiniMaxClone
  python -m pytest tests/test_improvements.py -v

Run integration tests (backend must be running):
  python -m pytest tests/test_improvements.py -v --integration

TypeScript check and build:
  cd MiniMaxClone/frontend
  npm run build

Create a new user (local dev with DB configured):
  curl -X POST http://localhost:8000/api/auth/register \
    -H "Content-Type: application/json" \
    -d '{"email": "test@example.com", "password": "password123", "name": "Test User"}'

Start a run (with AUTH_DISABLED=true):
  curl -X POST http://localhost:8000/api/start-project \
    -H "Content-Type: application/json" \
    -d '{"brief": "Build a REST API for a todo list"}'

Check billing/plan status:
  curl http://localhost:8000/api/billing/usage

Get account profile:
  curl -H "Authorization: Bearer <token>" http://localhost:8000/api/account/profile

Cancel a running run:
  curl -X POST http://localhost:8000/api/cancel

Get current config:
  curl http://localhost:8000/api/config

Check GitHub connection:
  curl http://localhost:8000/api/github/status


================================================================================
SECTION 24: CURRENT STATUS — WHAT IS DONE AND WHAT REMAINS
================================================================================

Last updated: 2026-05-22 (Second full-codebase audit — 18 fixes shipped + 9 architectural items deferred to AUDIT_REMAINING.md)
This section tracks the real-world setup state for this specific deployment.
Read this section first in a new session to know exactly where to pick up.

--------------------------------------------------------------------------------
DONE — Second full-codebase audit (2026-05-22)
--------------------------------------------------------------------------------

This pass was a three-pass walk over every backend, frontend, config, and test
file. 18 concrete fixes landed; 9 architectural items were deferred to
AUDIT_REMAINING.md with explicit notes on why.

Critical
[x] Duplicate `agent.run()` call per task removed from `_run_agent_loop`
    (Was hitting Zen 2× per executor task — direct call + the call inside
    `_run_with_search` — doubling token spend.)
[x] `SharedTaskList.add_task` id consistency — memory copy now uses the DB
    row id so `start_task` / `complete_task` lookups don't silently miss.
[x] `_claim_db` sets status="claimed" (not "in_progress") to match the
    documented state-machine; `recover_stale_claims` now also catches rows
    that crashed before `start_task` ran (started_at IS NULL + created_at
    older than cutoff).
[x] `docs_search` non-blocking — `search_docs_async()` runs via
    `asyncio.to_thread`; skip-list excludes `.git`, `node_modules`,
    `venv`, `.taskmesh`, `dist`, `build`, `__pycache__`, etc.

High
[x] Auth cookie SameSite configurable — `COOKIE_SAMESITE` env var,
    defaults to `strict` (local dev), set to `none` for split-origin
    deploys (Vercel↔Render) so Socket.IO can authenticate the WebSocket.
[x] Account deletion cascade — `delete_account` now scrubs the run-scoped
    audit tables (`ActionFile`, `ActionTool`, `Task`, `CoordinatorEvent`,
    `TaskAcceptance`) plus `Notification`. No more orphaned rows.
[x] Dead Socket.IO listeners removed — `reviewer_started`,
    `reviewer_result`, `reviewer_retry` were never emitted (replaced by
    `validation_verdict` / `validation_complete`).

Medium
[x] BillingPage no longer opens a duplicate WebSocket — flat 30s usage
    poll covers the same UX. The `useSocket` import is gone.
[x] `validate_filename` accepts whitelisted dotfiles (`.gitignore`,
    `.env.example`) — they were blocked despite being in
    `ALLOWED_EXTENSIONS`.
[x] `load_config(user_id)` event-loop landmine removed — was calling
    `asyncio.get_event_loop().run_until_complete` from a sync function
    that could be invoked under an active loop. Per-user DB config now
    exclusively async via `_load_user_config` in routes.py.
[x] `startProject` confirm dialog replaced with non-blocking alert; error
    messages added for `no_subscription`, `no_credits`, `already running`.

Low
[x] Google OAuth `oauth_state` cookie now deleted post-verification
    (GitHub callback already did this).
[x] `_run_with_retry` no longer NameErrors when `max_retries=0`.
[x] `LiveActivity` uses composite key (time + agent + index) — fixes
    React anti-pattern that caused unnecessary remounts.
[x] `Sidebar` memoises `flattenAcceptance` and `mergedVerdicts`.
[x] `ReviewerPanel` no longer hides itself when reviewer state is empty
    but acceptance criteria exist (the panel's only live content today).
[x] docs.search audit row now logs explicit `_status="ok"` /
    `_attempts=1` telemetry so it doesn't look like a failure.

Verification
[x] ruff check backend tests → All checks passed!
[x] cd frontend && npx tsc --noEmit → 0 errors
[x] cd frontend && npm run build → built in ~600ms (475 modules)
[x] pytest tests/test_improvements.py -v → 66 passed, 3 integration
    skipped (as expected — need running backend)

Deferred to AUDIT_REMAINING.md (architectural — not defects)
- _orchestrators dict is per-process (not multi-worker safe)
- calc_cost_cents rounds <0.5¢ to 1¢ (minimum-billable-unit)
- agent-team.config.json committed with API key risk
- MODEL_PRICING hand-maintained, drifts from Zen
- SettingsPanel duplicates backend model metadata
- Single-region Cloud SQL (infra, not code)
- Bundle size 527 KB pre-gzip (over Vite's 500 KB warning)
- ProjectState has dead `reviewerActive` / `reviewerResult` fields
- No app-level rate limit on /start-project

--------------------------------------------------------------------------------
DONE — Core infrastructure
--------------------------------------------------------------------------------

[x] Backend runs cleanly
    Command: python3 -m uvicorn backend.main:socket_app --reload --port 8000
    Virtualenv at MiniMaxClone/venv. Activate with: source venv/bin/activate

[x] Frontend runs cleanly
    Command: cd frontend && npm run dev
    Runs at http://localhost:5173
    Kill existing: lsof -ti:5173 | xargs kill -9

[x] Google Cloud SQL (PostgreSQL 18.3) — connected and verified

[x] Google OAuth (login) — GCP OAuth consent screen configured, works end-to-end

[x] Clerk fully removed — no @clerk imports anywhere

[x] SECRET_KEY set to a valid 64-hex-char value in .env

[x] AUTH_DISABLED removed from .env (real auth enabled in production)

[x] PyJWT and bcrypt added to requirements.txt

[x] Billing system redesigned (completed 2026-05-20)
    - New user_credits table (plan + balance_cents, persists across months)
    - Starter ($30/mo, 3 agents, standard models) + Pro ($80/mo, all features)
    - 3 PAYG credit packs ($20/$50/$100)
    - base_agent.run() returns token counts for cost calculation
    - orchestrator deducts credits after every agent call (fire-and-forget)
    - Plan-based model downgrade: PRO_ONLY_MODELS → STARTER_MODEL_FALLBACK for Starter
    - Agent cap: agent_limit=3 for Starter, enforced in Phase 0 selection
    - Dev bypass: AUTH_DISABLED skips billing gate entirely
    - BillingPage rewritten with credit balance bar + plan cards + PAYG buttons

[x] Header account pill (completed 2026-05-20)
    - User name/email shown in top-right corner
    - Links to /account (never calls logout)

[x] Account settings page at /account (completed 2026-05-20)
    - Frontend: AccountPage.tsx with profile, email, password, OAuth status, delete
    - Backend: api/account.py with GET/PUT profile, PUT email, PUT password, DELETE
    - Name/email changes issue a fresh JWT via login()

[x] Onboarding gate (completed 2026-05-20)
    - BillingGate component wraps MainApp
    - Fetches /api/billing/usage on mount; redirects to /billing if plan="none"
    - Completely skipped when VITE_AUTH_DISABLED=true

[x] Route additions
    - /account route added to App.tsx (protected)
    - PUT /api/config gated to Pro plan (403 for Starter)
    - POST /api/github/push gated to Pro plan (403 for Starter)

[x] SettingsPanel fixes
    - Sprint input and API key input now use inputStyle() (opaque backgrounds)
    - Settings dropdown removed — replaced with a direct Settings button

[x] BillingPage UI polish (completed 2026-05-20)
    - Centered layout: content horizontally centered with balanced whitespace
    - Balance display: percentage only (e.g. "87%"), no dollar amounts for usage
    - BalanceBar: large percentage number with colored fill bar
    - Admin bypass redirect: entering valid key now redirects to dashboard (/)
    - TypeScript build passes clean (0 errors)

--------------------------------------------------------------------------------
DONE — Dashboard UX & Agent Layout (2026-05-20)
--------------------------------------------------------------------------------

[x] Empty default agent layout on fresh install / first login
    - Backend DEFAULT_AGENTS in config_loader.py reduced to manager-only
    - Frontend DEFAULT_CONFIG in SettingsPanel.tsx reduced to manager-only
    - Users see an empty dashboard (only the Manager pipeline coordinator)
    - Users must explicitly add agents via Settings or "+ Add agents" button

[x] OpenCode API key relabel in Settings
    - Section title changed from "NVIDIA NIM" to "OpenCode Zen API Key"
    - Placeholder: "Paste your OpenCode Zen API key…"
    - Helper text references opencode.ai/zen
    - Provider name defaults updated in both backend and frontend configs

[x] Save & Apply button overlap fixed
    - Three distinct visual states: normal (accent), saving (muted + wait cursor), saved (green)
    - No ghosting or overlapping between state transitions
    - Button is properly disabled during saving/saved

[x] "+ Add agents" button in sidebar AGENTS heading
    - Located next to the "AGENTS" text in the right panel
    - Clicking opens the Settings panel to the Project tab
    - Styled with accent border matching existing UI
    - Prop chain: App.tsx → Sidebar → AgentsList

[x] "Recommended layout" button in Settings Panel
    - One-click 9-agent configuration button
    - Confirmation dialog: "Apply and replace" vs "Cancel"
    - Replaces all current agents with the recommended set:
      Manager → deepseek-v4-pro, WebDev → kimi-k2.6, Researcher → kimi-k2.5,
      Backend → deepseek-v4-flash, Frontend → mimo-v2.5, Tester → qwen3.5-plus,
      Docs → qwen3.5-plus, Logger → qwen3.5-plus, Reviewer → deepseek-v4-pro
    - Warns if no API key is configured
    - Saves via the regular Save & Apply flow

[x] TypeScript build passes clean (0 errors)

--------------------------------------------------------------------------------
DONE — Model List Overhaul (2026-05-20)
--------------------------------------------------------------------------------

[x] Curated 46-model set replacing 13 + 40+ old models
    Flagship Pro (16): 6 original Flagship + claude-opus-4-{1,5,6,7} + claude-sonnet-4/{5,6} +
      gpt-5.4-pro / gpt-5.5-pro / gpt-5.4 / gpt-5.5 + gemini-3.1-pro
    Balanced (22): 6 original Balanced + DeepSeek V4 Flash + claude-haiku-4-5 +
      gpt-5/5.1/5.2 + gpt-*-codex + gemini-3-flash / 3.5-flash + others
    Budget (8): nemotron-3-super + deepseek-v4-flash-free + big-pickle +
      nemotron-3-super-free + minimax-m2.5-free + gpt-5-nano/5.4-nano + grok-build-0-1

[x] MODEL_GROUPS in SettingsPanel.tsx — 3 categories: Flagship (Pro), Balanced, Budget

[x] MODEL_RECOMMENDATIONS in SettingsPanel.tsx — sampling defaults for all 46 models

[x] MODEL_PRICING in billing.py — per-token rates for all 46 models

[x] PRO_ONLY_MODELS in billing.py — 26 models (threshold: prompt >0.2¢/1K ~$2/M input)

[x] GPT_MODEL_IDS (17) + ANTHROPIC_MODEL_IDS (12) in base_agent.py for model routing

[x] ZenUsage table in models.py for per-call token usage logging

[x] /api/account/zen-summary endpoint for monthly spend analytics

[x] AccountPage "Usage & Billing" section — monthly spend, runs, lifetime, balance

--------------------------------------------------------------------------------

[x] Multi-user concurrent orchestrator (completed 2026-05-21)
    - _orchestrators: dict[str, Orchestrator] replaces singleton
    - Per-user start_project creates fresh orchestrator; cancel targets caller only
    - Socket.IO 'auth' event enters user into "user:{id}" room
    - All 20+ sio.emit() calls scoped to room=self._room
    - On run completion, orchestrator removed from dict via on_done callback
    - Lifespan shutdown cancels all active orchestrators

[x] Vercel WebSocket bypass (completed 2026-05-21)
    - VITE_SOCKET_URL env var for direct backend WebSocket connection
    - Bypasses Vercel's HTTP-only proxy; production gets true real-time push
    - Frontend emits 'auth' event on connect for JWT-based room joining

[x] Per-user agent config (completed 2026-05-21)
    - `users.config_json` column stores per-user config for Pro users
    - `PUT /api/config` writes to DB row, not shared disk file
    - `GET /api/config` returns calling user's config (DB → disk fallback)
    - `start_project` passes per-user config to orchestrator
    - Disk file remains as global default template (never overwritten by Pro users)

[x] Retry on Zen API failures (completed 2026-05-21)
    - `_run_with_retry()` wrapper: 3 attempts, exponential backoff (2/4/8s + jitter)
    - Wraps both Anthropic Messages API and OpenAI Chat Completions paths
    - Handles APIStatusError, APITimeoutError, APIConnectionError
    - Returns empty content result on total failure — never crashes agent loop

[x] Logo optimized (completed 2026-05-21)
    - Replaced 3.2 MB PNG (1567×1536) with 300-byte SVG
    - Cuts ~3 MB from the frontend bundle

[x] Postgres to_char() replaced (completed 2026-05-21)
    - `ZenUsage.year_month` column precomputed on insert
    - Queries use portable equality instead of Postgres-specific to_char()

[x] tasks_init emits only on change (completed 2026-05-21)
    - `SharedTaskList._dirty` flag tracks task mutations
    - Monitor loop only emits `tasks_init` when dirty, then marks clean

[x] git polling reduced from 2s to 5s (completed 2026-05-21)
    - Removed redundant git_status call from monitor loop
    - File polling task now runs every 5s instead of 2s
    - _upload_tokens entries timestamped with time.monotonic()
    - Token consumed on start_project (popped from dict)
    - Background task cleans expired tokens + disk dirs every 5 min
    - UPLOAD_TOKEN_TTL env var configurable (default 3600s = 1 hour)
    - Opportunistic cleanup on each start_project call

[x] Full Zen model catalog (46 models, 3 tiers) — completed 2026-05-20

[x] BYOK removal — completed 2026-05-20

[x] 3-Stage pipeline (completed 2026-05-21)
    - Stage 1 (Research): Manager + planners research tools/approaches
    - Stage 2 (Plan): Planners produce specs → Manager creates task plan
    - Stage 3a (Production): Executors run via SharedTaskList
    - Stage 3b (Validation): Reviewer+Researcher evaluate → Manager tiebreaker
    - Rework: 1 iteration on rejection, rework_tasks created via Manager
    - Planner agents now actually run (were config-only dead weight)
    - All stage events: stage_start, research_report/complete, plan_report/complete, validation_verdict/complete

[x] LLM thinking budget activated (completed 2026-05-21)
    - THINKING_MODEL_IDS: 14 models (Kimi, Qwen, MiMo, GLM, DeepSeek) via chat_template_kwargs
    - ANTHROPIC_THINKING_MODEL_IDS: 8 Claude models via Anthropic thinking parameter
    - Thinking content extracted separately; emitted via thinking_content Socket.IO event
    - ThinkingSlider re-added to SettingsPanel with model-aware enable/disable
    - Max 16000 budget, 256 step. Disabled on non-thinking models (GPT, Gemini, etc.)
    - Anthropic max_tokens auto-bumps to thinking_budget + 1024 when needed

[x] Medium-priority features (completed 2026-05-21)
    - Balance low warning: header pill at $2.50 threshold, red at $0.00, polls /api/billing/usage every 60s
    - Credit estimate: /start-project returns credit_warning when estimated cost exceeds balance
    - Subscription management: "Manage Subscription" button on AccountPage + BillingPage → Paddle portal
    - Run timeout: RUN_TIMEOUT_SECONDS env var (600s default), monitor loop checks, run_timeout event

[x] Polish items (completed 2026-05-21)
    - Notifications stub: notifications table, GET/PUT /api/account/notifications, AccountPage toggles
    - OpenRouter: toggleable via PROVIDER=openrouter env var, config_loader switches automatically
    - Mobile layout: sidebar hidden < 1024px, hamburger toggle, header stacks on narrow screens
    - Theme CSS variables on BillingPage and AccountPage (was hardcoded colors)
    - Heartbeat: Agent.lastActivity timestamp, detect >30s agent silence
    - Vercel WebSocket: VITE_SOCKET_URL env var already documented for production

[x] All 22 AUDIT_REMAINING items resolved

[x] ruff: 0 errors · TypeScript: 0 errors · pytest: 66 passed, 3 skipped

--------------------------------------------------------------------------------
TODO — External services not yet configured
--------------------------------------------------------------------------------

[x] BYOK (per-user API keys) removed — system uses single master Zen key (2026-05-20)
    OPENCODE_GO_API_KEY env var is the sole provider key
    All per-user key infrastructure deleted: User.opencode_api_key column,
    SetApiKeyRequest model, GET/PUT/DELETE /api/account/apikey endpoints,
    AccountPage "Provider API key" section
    Key fetch removed from /api/start-project — always passes api_key=""
    All agents fall back to the env var via config_loader.py

[ ] Paddle — create 5 products and configure
    See Section 17 for full setup instructions.
    Until done: all /api/billing/checkout calls return 503.
    Note: billing page UI and backend logic are fully built — just needs price IDs.

[ ] Initialize git repo in PROJECT_DIR for auto-commit to work
    cd $PROJECT_DIR && git init && git commit --allow-empty -m "init"

[ ] OpenCode Zen API key
    Subscribe at https://opencode.ai/zen → set OPENCODE_GO_API_KEY in .env

-------------------------------------------------------------------------------
NOT NEEDED — Confirmed unnecessary
-------------------------------------------------------------------------------

[-] Clerk — fully removed. Do not reinstall.
[-] Free tier — replaced by subscription-only model.
[-] PADDLE_PRICE_TEAM — old plan removed, replaced by Starter/Pro.
[-] statement_timeout flag in Cloud SQL — not available, skip it.
[-] Dollar amounts for balance/usage — replaced by percentage display.
[-] NVIDIA NIM labels — replaced with "OpenCode Zen" / "OpenCode Zen API Key" throughout.
[-] PyJWT + bcrypt manual install — now in requirements.txt.
[-] Old 2-phase pipeline — replaced by 3-stage model.


================================================================================
END OF DOCUMENT
================================================================================
