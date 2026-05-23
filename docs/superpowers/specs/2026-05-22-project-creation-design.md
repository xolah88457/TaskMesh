# Project Creation & Persistence — Design Spec

**Date:** 2026-05-22
**Status:** Approved

## Problem

When a user creates a project from the Dashboard (name, goal/brief, agent selection), none of this information reaches the backend properly. The project name isn't stored or used as folder name. Agent selections are ignored — the backend uses whatever agents are in the config file. Projects are local-only React state and vanish on refresh. There is no `/api/projects` endpoint.

## Decisions

| Decision | Choice |
|----------|--------|
| Agent selection scope | Per-project (not global config) |
| Project storage | Separate `projects` table |
| Folder structure | `PROJECT_DIR/{slug}` per project |
| API style | Minimal list + detail endpoint |

## Architecture

### Approach A — Projects table + per-run agent overrides

A new `projects` table stores project identity (name, desc, slug, icon). The existing `runs` table gains a `project_id` FK and `selected_agents` column. Projects and runs are separate concerns: a project is a named workspace, a run is one execution within it.

### Database Schema

#### New table: `projects`

| Column | Type | Notes |
|--------|------|-------|
| `id` | String(36) PK | UUID |
| `user_id` | String(128) FK → users | Indexed |
| `name` | String(256) | User-provided project name |
| `slug` | String(256) | URL-safe version of name. Unique per user. |
| `desc` | Text | Goal/brief from creation form |
| `icon` | String(8) | Emoji/icon character |
| `created_at` | DateTime(timezone=True) | Set at creation |
| `updated_at` | DateTime(timezone=True) | Last touched |

#### Changes to existing `runs` table

| Column | Type | Notes |
|--------|------|-------|
| `project_id` | String(36) FK → projects | Nullable (backward compat for old runs) |
| `selected_agents` | Text(JSON) | Agent IDs chosen at creation. Null = use all config agents |

### API Endpoints

#### `POST /api/projects` — Create project (+ optionally first run)

Request:
```json
{
  "name": "My Chat App",
  "brief": "Build a real-time chat app",
  "icon": "💬",
  "agents": ["manager", "webdev", "backend", "frontend"],
  "auto_start": true
}
```

Flow:
1. Generate UUID, make slug from name (`my-chat-app`)
2. INSERT into projects table
3. If `auto_start`: create run row, set `PROJECT_DIR/{slug}` as working directory, filter orchestrator agents to selected list, start execution
4. Return `{ project_id, run_id?, slug }`

#### `GET /api/projects` — List (minimal)

```json
{
  "projects": [{
    "id": "uuid",
    "name": "My Chat App",
    "status": "running",
    "created_at": "ISO",
    "updated_at": "ISO"
  }]
}
```

#### `GET /api/projects/{project_id}` — Detail

Returns full card data: name, desc, icon, status, agent_count, file_count, slug, last_active, progress, tokens estimate.

#### `PUT /api/projects/{project_id}` — Re-launch

Re-run a project with optionally different brief or agents.

#### `POST /api/start-project` — Legacy

Kept for backward compat. Internally delegates to the new projects endpoint or returns the same shape. Gains `project_id` in response.

### Agent Filtering in Orchestrator

1. `Orchestrator.run()` accepts `selected_agents: list[str] | None`
2. When provided, filter `self._config.agents` to only matching IDs
3. Manager agent is always force-included
4. Executors, planners, and reviewer are all filtered by the selected list
5. `selected_agents` is persisted on the run row

### Folder Structure

- Projects get `PROJECT_DIR/{slug}/` as working directory
- Old behavior (single flat directory) only applies when no project_id exists on a run
- `get_project_dir()` becomes `get_project_dir(slug: str | None = None)` — returns `PROJECT_DIR/{slug}` if slug provided, `PROJECT_DIR` otherwise

### Frontend Changes

#### Dashboard — `launchNew`
Replaces local fake-project creation with `POST /api/projects`. Navigates to `/project/{run_id}` after response.

#### Dashboard — Projects list
`GET /api/projects` on mount. Projects rendered from API data, not local state.

#### Workspace (App.tsx) — Project name
Header reads project name from project detail API. No longer shows raw folder name.

#### CreateTab
Agent toggle selections are sent to the backend and become the `agents` array in the POST body.

### Database Migration

`_run_migrations()` in `backend/db/session.py`:
- `CREATE TABLE IF NOT EXISTS projects (...)`
- `ALTER TABLE runs ADD COLUMN IF NOT EXISTS project_id VARCHAR(36)`
- `ALTER TABLE runs ADD COLUMN IF NOT EXISTS selected_agents TEXT`

### Error Handling

- **Duplicate slug**: Append `-2`, `-3` etc.
- **Unknown agent ID in selection**: Skip silently, log warning
- **Manager not in selection**: Force-add manager
- **Old runs without project_id**: Exclude from dashboard (or show as "Legacy" with fallback)

### Testing

- Unit: `_make_slug()` helper, agent filter in orchestrator
- Integration: POST `/api/projects` → verify DB row, folder on disk, orchestrator starts with filtered agents
- Frontend: Dashboard loads from API, project creation navigates to workspace with correct name
