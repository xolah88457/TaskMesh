# TaskMesh — AGENTS.md

**Project:** TaskMesh — a multi-agent AI software development platform. Users describe a project in natural language, and an orchestrated team of specialized AI agents researches, plans, implements, tests, and reviews the code.

## Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 19 + TypeScript + Vite |
| Backend | FastAPI (Python 3.11+) + uvicorn |
| Database | PostgreSQL (async SQLAlchemy) |
| Realtime | Socket.IO (python-socketio) |
| Billing | Paddle |
| Auth | JWT (pyjwt) + Google/GitHub OAuth |
| Deployment | Render (backend), Vercel (frontend) |

## Run Commands

```bash
# Backend (from project root)
uvicorn backend.main:app --host 0.0.0.0 --port 8888 --reload

# Frontend (from frontend/)
cd frontend && npx vite --port 5173

# TypeScript typecheck
cd frontend && npx tsc --noEmit -p tsconfig.app.json

# Python tests
pytest backend/tests/

# Full dev (both servers)
./start.sh
```

## Skill Activation Guide

| Task Type | Skills to Invoke (in order) |
|-----------|---------------------------|
| **New feature / component** | brainstorming → writing-plans → executing-plans or subagent-driven-development → verification-before-completion → finishing-a-development-branch |
| **Bug fix** | systematic-debugging → test-driven-development → requesting-code-review |
| **UI / frontend work** | frontend-design → web-design-guidelines → webapp-testing |
| **Backend / API work** | fastapi-templates → python-testing-patterns |
| **Deployment** | deploy-to-vercel |
| **Billing / payments** | billing-automation |
| **React performance** | vercel-react-best-practices |
| **Code review request** | requesting-code-review |
| **Receiving code review** | receiving-code-review |

**Always invoke `using-superpowers` first** — it establishes how to find and use skills.

## Plugins

This project uses 6 OpenCode plugins:

| Plugin | Purpose |
|--------|---------|
| **opencode-beads** | Beads task management — tracks ready/doing/done tasks |
| **caveman-opencode-plugin** | Caveman — terminal-style productivity tools |
| **@tarquinen/opencode-dcp** | DCP — conversation context management (compression) |
| **superpowers** | 15 skills for brainstorming, planning, TDD, debugging, code review, and workflow management |
| **oc-tps** (TUI) | Terminal UI plugin for enhanced CLI experience |

## Conventions

- **No comments** in code unless the user explicitly asks
- **Git commits** use conventional commit format (feat:, fix:, refactor:)
- **Status markers** in plans/docs: ✅ done · ⬜ not started · ❌ blocked
- **Toast notifications** use `setToast()` for user feedback
- **Auth fetching** uses `useAuthFetch()` hook (auto-attaches JWT cookie)

## Key Files

| File | Purpose |
|------|---------|
| `frontend/src/App.tsx` | Router + Workspace component + route guards |
| `frontend/src/pages/Dashboard.tsx` | Landing page with project list, create, quick actions |
| `frontend/src/components/Header.tsx` | Top nav bar with mode support (dashboard vs workspace) |
| `backend/api/routes.py` | All REST endpoints (auth, projects, billing, config) |
| `backend/core/orchestrator.py` | Agent pipeline — coordinates research, plan, build, review |
| `backend/core/config_loader.py` | Loads agent team config from DB or disk |
| `backend/db/models.py` | SQLAlchemy models (User, Run, Project, UserCredits) |
| `backend/db/session.py` | DB session factory + migrations |
| `backend/auth/auth.py` | JWT create/verify + cookie helpers |
| `frontend/src/TMdash.css` | TM Dash design system (1313 lines) |
| `frontend/src/themes.ts` | Theme definitions with CSS variable tokens |
