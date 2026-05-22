# TaskMesh — Audit Remaining

Open items from the 2026-05-21 full codebase audit. Items marked ✅ have been resolved since the audit was written.
**Last updated: 2026-05-21 (remaining items only; resolved items moved to Resolved section below)**

---

## ✅ Resolved (since audit — 2026-05-21)

| # | Item | When resolved |
|---|------|--------------|
| 1 | Singleton orchestrator blocks concurrent users | 2026-05-21 — `dict[user_id, Orchestrator]` + per-user Socket.IO rooms |
| 2 | Vercel HTTP rewrites do not proxy WebSockets | 2026-05-21 — `VITE_SOCKET_URL` env var → direct Render WebSocket connection |
| 3 | `agent-team.config.json` is shared global state | 2026-05-21 — `users.config_json` per-user config; disk file is global default |
| 4 | `_upload_tokens` grows without bound | 2026-05-21 — TTL-based cleanup (UPLOAD_TOKEN_TTL env var, 3600s default); background cleanup every 5 min |
| 5 | JWT in localStorage is XSS-exfiltrable | 2026-05-21 — switched to HttpOnly cookie (auth.py sets/strips token cookie) |
| 6 | Cloud SQL queries use Postgres-specific functions | 2026-05-21 — replaced `to_char()` with precomputed `year_month` column |
| 7 | No retry on OpenCode Zen failures | 2026-05-21 — `_run_with_retry()` wrapper: 3 attempts, exponential backoff |
| 8 | Logo is 3.2 MB | 2026-05-21 — replaced with 300-byte SVG |
| 9 | `tasks_init` fires every 2 seconds during a run | 2026-05-21 — dirty flag on SharedTaskList |
| 10 | `_file_poll_task` shells out to `git status` every 2s | 2026-05-21 — reduced to 5s; removed redundant call from monitor loop |
| 11 | SettingsPanel Account tab is a near-duplicate of AccountPage | 2026-05-21 — removed AccountSettingsPanel + OAuthRow; Account tab → /account |
| 12 | `run_limit` field mismatch (frontend expects, backend returns nothing) | 2026-05-21 — added `run_limit: None` to /api/billing/usage response |
| 13 | Empty `THINKING_MODELS` makes ThinkingSlider dead code | 2026-05-21 — thinking activated: THINKING_MODEL_IDS populated (24 models), slider re-added to SettingsPanel |
| 14 | Default `AUTH_DISABLED=true` in `.env.example` | 2026-05-21 — flipped to `false` with warning comment |
| 15 | Stray UUID-named files in repo root | 2026-05-21 — deleted |
| 16 | `python-socketio` `cors_allowed_origins="*"` even with our list | 2026-05-21 — hardened: `RuntimeWarning` when `*` is used outside dev mode |
| 17 | OAuth `state` parameter not validated | 2026-05-21 — Google + GitHub callbacks verify anti-CSRF state via HttpOnly cookie |
| 18 | MatrixRain canvas always runs at 60fps | 2026-05-21 — pauses requestAnimationFrame on visibilitychange |
| 19 | Mobile layout broken | 2026-05-21 — sidebar collapses on <1024px (`hidden lg:flex`); hamburger toggle added |
| 20 | Long agent run has no "still working" indicator | 2026-05-21 — Agent.lastActivity timestamp; heartbeat after 30s silence |
| 21 | Dark/light theme on billing and account pages | 2026-05-21 — hardcoded colors replaced with theme CSS variables |
| 22 | OpenRouter commented-out code | 2026-05-21 — uncommented; toggleable via `PROVIDER=openrouter` env var |

---

## High — likely to bite production users

*(All High items resolved — see table above)*

---

## Medium — fix before a real launch

*(All Medium items resolved — see table above)*

---

## Low — nice-to-haves

*(All Low items resolved — see table above)*

---

## UX notes (Pass 3)

| Observation | Status |
|---|---|
| Billing page now shows balance as % everywhere (was $ amounts) | ✅ already done before audit |
| Settings Account tab forms looked functional but quietly did nothing | ✅ fixed |
| Admin bypass redirects to dashboard after success | ✅ already done |
| The `Manage subscription` / `Cancel subscription` / `Delete account` buttons in SettingsPanel just `alert(...)` | ✅ fixed — Manage Subscription portal button on AccountPage and BillingPage; Delete works via AccountPage |
| `OAuthRow` always shows `Not connected` regardless of state | ✅ fixed — whole AccountSettingsPanel removed; AccountPage shows real status |
| ReviewerPanel renders nothing until a reviewer phase exists | ✅ reviewer is now active as part of 3-stage validation |
| MatrixRain canvas always runs at 60fps when the default theme is active | ✅ pauses on visibilitychange |
| Mobile layout broken (flex columns + sidebar assume ≥1024 px) | ✅ sidebar collapses on mobile; hamburger toggle added |
| Long agent run with no output has no "still working / heartbeat" indicator beyond the elapsed timer | ✅ heartbeat after 30s agent silence |
| Dark/light theme on billing and account pages uses hardcoded colors | ✅ replaced with theme CSS variables |

---

## Verification status

- `ruff check .` → `All checks passed!`
- `cd frontend && npx tsc --noEmit` → 0 errors
- `cd frontend && npm run build` → built successfully
- `pytest tests/test_improvements.py -v` → **66 passed, 3 integration skipped**

---

## No remaining unresolved items

All 22 items identified in the 2026-05-21 audit have been resolved. The audit is complete.
