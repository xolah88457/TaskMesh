# TaskMesh — Audit Remaining

Open items from the 2026-05-21 full codebase audit that were **not** fixed in code, because they
need a design decision, a deployment-level change, or are scope-too-large for a single audit pass.
Items are grouped by severity. Each entry has the file/location, the concrete problem, and the
proposed fix.

---

## High — likely to bite production users

### Singleton orchestrator blocks concurrent users
**Location:** `backend/api/routes.py:14` + `backend/core/orchestrator.py` (entire class)

There is exactly **one** `_orchestrator` instance per process, with a single `_run_task`,
`_file_locks`, `_mailbox`, `_coord_log`, and `_task_list`. When user A starts a run,
`is_running()` returns true and user B receives `{"error": "already running"}`. Socket.IO
events also fan out to every connected client, so any user watching the dashboard sees
another user's agents move on the network graph.

**Proposed fix:** keep a `dict[user_id, Orchestrator]` keyed by user, and use Socket.IO rooms
so each user only receives their own run's events. Touches `routes.py`, `orchestrator.py`, and
`main.py` socket handlers. Medium effort.

**Why not fixed now:** large refactor that changes the architecture. The system was clearly
designed as single-tenant; until that contract is renegotiated, the safer move is to flag this
and let the maintainer scope the change explicitly.

### Vercel HTTP rewrites do not proxy WebSockets
**Location:** `frontend/vercel.json` + `frontend/src/hooks/useSocket.ts:188`

The Socket.IO client connects to `window.location.origin` (Vercel). `vercel.json` rewrites
`/api/*` to Render, but **Vercel rewrites don't forward WebSocket upgrade frames**.
Socket.IO falls back to long polling, which works but is slower and uses more requests.
For runs longer than a couple of minutes this can multiply API costs and laggy UI.

**Proposed fix:** point Socket.IO at the Render origin directly:
```ts
const SOCKET_URL = import.meta.env.VITE_SOCKET_URL ?? '/'
const socket = io(SOCKET_URL, { path: '/socket.io', transports: ['websocket', 'polling'] })
```
Set `VITE_SOCKET_URL=https://taskmesh-api.onrender.com` on Vercel. Backend CORS env already
supports this.

**Why not fixed now:** requires the Vercel env var change at deploy time. Documenting so the
operator can do it next deploy.

### `agent-team.config.json` is shared global state
**Location:** `backend/api/routes.py:152` (`put_config`) + `backend/core/config_loader.py:103` (`save_config`)

`PUT /api/config` writes to a single file on disk. Any user with a Pro plan can overwrite the
provider URL, API key, or every other user's agent roster. Worse, the file is also loaded by
`load_config()` at the start of every run — including runs by users who didn't change it.

**Proposed fix:** make agent config per-user. Move the JSON contents into the `users` table
(or a sibling `user_configs` table) keyed by `user_id`. Pro users can override their own row;
runs use only the calling user's config. The disk file becomes a global default template.

**Why not fixed now:** schema migration plus auth-aware load_config plumbing; want maintainer
sign-off on the table shape first.

---

## Medium — fix before a real launch

### `_upload_tokens` grows without bound
**Location:** `backend/api/routes.py:21`

Upload tokens are stored in a process-level dict (`_upload_tokens`) and never expired. Long-
running processes accumulate them forever. Also lost on every backend restart, breaking any
upload in flight.

**Proposed fix:** either (a) persist tokens in a small DB table with `expires_at`, or (b) keep
them in-process but with a TTL (~1 hour) and a periodic cleanup task. (b) is simpler if you
accept "upload, then start within the hour".

### JWT in localStorage is XSS-exfiltrable
**Location:** `frontend/src/context/auth.tsx:10` + `frontend/src/hooks/useAuthFetch.ts`

Standard SPA trade-off, but worth knowing: any XSS payload that runs on the page can read the
token and impersonate the user for `_TOKEN_DAYS` (default 30).

**Proposed fix:** switch to HttpOnly cookie session. Requires backend changes (set cookie,
read from request) and CSRF protection. Significant lift; only justified when launching to
real users.

### Cloud SQL queries use Postgres-specific functions
**Location:** `backend/api/account.py:198` (`func.to_char(ZenUsage.created_at, "YYYY-MM")`)

The "month spend" query uses `to_char()`, a Postgres function. Won't work on SQLite, MySQL,
or any portable test fixture. We're committed to Postgres so this is fine in production but
makes local-DB testing painful.

**Proposed fix:** replace with a SQLAlchemy-portable expression:
```python
from sqlalchemy import extract, and_
.where(and_(
    extract('year', ZenUsage.created_at) == year,
    extract('month', ZenUsage.created_at) == month,
))
```
Or precompute `year_month` as a separate column on insert.

### No retry on OpenCode Zen failures
**Location:** `backend/agents/base_agent.py:113-204` (`_run_anthropic`, `run`)

A single 429/500/timeout from the provider produces empty `content` and the affected agent
silently writes no files. Already on TODO.md as a code task; mentioning here for completeness.

**Proposed fix:** wrap the SDK calls in a small retry helper (3 attempts, exponential backoff,
only on 429/5xx).

### `frontend/src/assets/logo.png` is 3.2 MB
**Location:** build output `dist/assets/logo-Dh9vHB7r.png`

The shipped logo is a 3.2 MB PNG. On a 4G connection this is ~5 seconds of blocking transfer
on first paint. Easy win.

**Proposed fix:** export the logo as a 64×64 SVG (or 256×256 PNG, optimised). Replace
`frontend/src/assets/logo.png` and `frontend/public/favicon.png`. Cuts ~3 MB off the bundle.

### `tasks_init` fires every 2 seconds during a run
**Location:** `backend/core/orchestrator.py:716` inside the monitor loop

The orchestrator emits the full task-list on every 2-second tick, even when nothing changed.
The frontend re-renders the TasksList component each time. For 10 tasks × 60 ticks/min ×
several agents, this is noisy but not a real perf issue today.

**Proposed fix:** track a `_tasks_dirty` flag and only emit when something changed
(claim/start/complete/block/fail). Or hash the task list and skip if unchanged.

### `_file_poll_task` shells out to `git status` every 2s
**Location:** `backend/core/orchestrator.py:349-356`

Same pattern: spawns a subprocess every 2 seconds. Cheap, but stacks up on shared hosting
and produces churn in process counters.

**Proposed fix:** only re-poll when a write happens (event-driven), or back off to 5s.

---

## Low — nice-to-haves

### `SettingsPanel` Account tab is a near-duplicate of `AccountPage`
**Location:** `frontend/src/components/SettingsPanel.tsx:1297-1498` (`AccountSettingsPanel`)

Two implementations of the same forms (display name, email, password, OAuth status). Now that
the SettingsPanel version is wired to real endpoints, the duplication is functional but still
duplication. The `OAuthRow` rendered in SettingsPanel is hardcoded to `connected={false}`,
so it shows "Not connected" even when the user IS connected.

**Proposed fix:** delete the AccountSettingsPanel implementation and replace the Account tab
with a single button that navigates to `/account`. Keeps one source of truth.

### `AccountSettingsPanel.usage` has a `run_limit` field the backend doesn't return
**Location:** `frontend/src/components/SettingsPanel.tsx:1305`

```ts
const [usage, setUsage] = useState<{ plan: string; run_count: number; run_limit: number | null } | null>(null)
```

Backend's `/api/billing/usage` returns `{plan, balance_cents, run_count}` — no `run_limit`.
The `usage.run_limit !== null` check at line 1423 will always be false-y for undefined,
making the conditional render confusingly always show "(unlimited)".

**Proposed fix:** drop `run_limit` from the type and the conditional, or add it to the
backend response if there's a real per-plan run cap.

### Empty `THINKING_MODELS` makes `ThinkingSlider` dead code
**Location:** `frontend/src/components/SettingsPanel.tsx:27, 589-627`

`THINKING_MODELS = {}` so `ThinkingSlider` always returns null. The component and the
budget→level helpers exist purely for the OpenRouter migration. They're harmless but obscure.

**Proposed fix:** leave for now; document next to the empty dict that the slider re-activates
when OpenRouter ships.

### Default `AUTH_DISABLED=true` in `.env.example`
**Location:** `.env.example:12`

If someone copies `.env.example` to `.env` on a production box and forgets to flip the flag,
auth is silently disabled and every endpoint returns "dev-user". The startup warning we
added only fires for SECRET_KEY, not for AUTH_DISABLED.

**Proposed fix:** flip the default to `AUTH_DISABLED=false` in `.env.example` and add a clear
"only set true in local dev" comment. Optionally also emit a warning when AUTH_DISABLED=true
is detected outside `localhost`.

### Stray UUID-named files in repo root
**Location:** `7e396012-3888-4057-957c-d2b20e55a153.gif` and `.jpeg`

Unreferenced binary files at the repo root. If they're old screenshots, delete them; if they
were meant as assets, move them to `frontend/src/assets/`.

### `python-socketio` `cors_allowed_origins="*"` even with our list
**Location:** `backend/main.py:25-29`

We pass the list to Socket.IO when configured, but Socket.IO's default still treats `"*"` as
permissive. If someone forgets `CORS_ALLOWED_ORIGINS` in prod, both CORS and Socket.IO are
wide open. Documented behaviour, but a hardening pass could fail fast when no origins are
set and `AUTH_DISABLED=false`.

### `backend/api/auth.py` Google OAuth callback ignores `state`
**Location:** `backend/api/auth.py:134-213`

The login OAuth flow accepts `state` but never validates it. Standard OAuth recommendation is
to send a random nonce in `/google/url`, store it in a short-lived session/cookie, and verify
on callback. Without it, a malicious site can initiate the flow on a victim's behalf (limited
impact for login-only OAuth, but still best practice).

**Proposed fix:** issue a `state` cookie on `/google/url`, verify on `/google/callback`.
Same for GitHub login flow.

---

## UX notes (Pass 3) — handled inline or deferred

| Observation | Status |
|---|---|
| Billing page now shows balance as % everywhere (was $ amounts) | ✅ already done before audit |
| Settings Account tab forms looked functional but quietly did nothing | ✅ fixed |
| Admin bypass redirects to dashboard after success | ✅ already done |
| The `Manage subscription` / `Cancel subscription` / `Delete account` buttons in SettingsPanel just `alert(...)` | ⬜ stub — the real Delete works in AccountPage; remove these or wire them |
| `OAuthRow` always shows `Not connected` regardless of state | ⬜ tied to "delete SettingsPanel.AccountSettingsPanel" above |
| ReviewerPanel renders nothing until a reviewer phase exists | ⬜ keep as scaffolding for future Phase 4 |
| MatrixRain canvas always runs at 60fps when the default theme is active — burns battery on laptops | ⬜ consider pausing on `visibilitychange` |
| Mobile layout broken (flex columns + sidebar assume ≥1024 px) | ⬜ desktop-first by design |
| Long agent run with no output has no "still working / heartbeat" indicator beyond the elapsed timer | ⬜ minor |

---

## Verification status at end of audit

- `ruff check backend tests` → `All checks passed!`
- `cd frontend && npx tsc --noEmit` → 0 errors
- `cd frontend && npm run build` → built successfully (warning only about 521 KB JS chunk)
- `pytest tests/test_improvements.py -v` → 25 passed, 3 integration skipped
