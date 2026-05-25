# TaskMesh — CLAUDE.md

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

## Skills

| Skill | Source | Purpose |
|-------|--------|---------|
| **brainstorming** | superpowers | Socratic design refinement |
| **writing-plans** | superpowers | Detailed implementation plans |
| **executing-plans** | superpowers | Batch execution with checkpoints |
| **subagent-driven-development** | superpowers | Fast iteration with two-stage review |
| **test-driven-development** | superpowers | RED-GREEN-REFACTOR cycle |
| **systematic-debugging** | superpowers | 4-phase root cause process |
| **verification-before-completion** | superpowers | Verify before declaring success |
| **using-git-worktrees** | superpowers | Parallel development branches |
| **requesting-code-review** | superpowers | Pre-review checklist |
| **receiving-code-review** | superpowers | Responding to feedback |
| **dispatching-parallel-agents** | superpowers | Concurrent subagent workflows |
| **finishing-a-development-branch** | superpowers | Merge/PR decision workflow |
| **writing-skills** | superpowers | Create new skills |
| **billing-automation** | claude-skills | Build automated billing systems |
| **deploy-to-vercel** | claude-skills | Deploy apps to Vercel |
| **fastapi-templates** | claude-skills | Production FastAPI backends |
| **frontend-design** | claude-skills | Production-grade frontend UI |
| **git-commit** | claude-skills | Conventional git commits |
| **prompt-master** | claude-skills | Generate optimized prompts |
| **python-testing-patterns** | claude-skills | Pytest strategies |
| **vercel-react-best-practices** | claude-skills | React performance optimization |
| **web-design-guidelines** | claude-skills | UI/UX accessibility audit |
| **webapp-testing** | claude-skills | Playwright browser testing |

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


<!-- BEGIN BEADS INTEGRATION v:1 profile:minimal hash:7510c1e2 -->
## Beads Issue Tracker

This project uses **bd (beads)** for issue tracking. Run `bd prime` to see full workflow context and commands.

### Quick Reference

```bash
bd ready              # Find available work
bd show <id>          # View issue details
bd update <id> --claim  # Claim work
bd close <id>         # Complete work
```

### Rules

- Use `bd` for ALL task tracking — do NOT use TodoWrite, TaskCreate, or markdown TODO lists
- Run `bd prime` for detailed command reference and session close protocol
- Use `bd remember` for persistent knowledge — do NOT use MEMORY.md files

**Architecture in one line:** issues live in a local Dolt DB; sync uses `refs/dolt/data` on your git remote; `.beads/issues.jsonl` is a passive export. See https://github.com/gastownhall/beads/blob/main/docs/SYNC_CONCEPTS.md for details and anti-patterns.

## Session Completion

**When ending a work session**, you MUST complete ALL steps below. Work is NOT complete until `git push` succeeds.

**MANDATORY WORKFLOW:**

1. **File issues for remaining work** - Create issues for anything that needs follow-up
2. **Run quality gates** (if code changed) - Tests, linters, builds
3. **Update issue status** - Close finished work, update in-progress items
4. **PUSH TO REMOTE** - This is MANDATORY:
   ```bash
   git pull --rebase
   git push
   git status  # MUST show "up to date with origin"
   ```
5. **Clean up** - Clear stashes, prune remote branches
6. **Verify** - All changes committed AND pushed
7. **Hand off** - Provide context for next session

**CRITICAL RULES:**
- Work is NOT complete until `git push` succeeds
- NEVER stop before pushing - that leaves work stranded locally
- NEVER say "ready to push when you are" - YOU must push
- If push fails, resolve and retry until it succeeds
<!-- END BEADS INTEGRATION -->
