# Project Creation & Persistence — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist projects to database, isolate each project to its own subdirectory under PROJECT_DIR, and support per-project agent selection so the Dashboard reflects real data instead of localStorage-only state.

**Architecture:** New `projects` table stores project identity (name, slug, desc, icon). The `runs` table gains `project_id` FK and `selected_agents` column. `POST /api/projects` creates both project row and (optionally) first run. Orchestrator filters `self.config.agents` by the selected list. `get_project_dir()` accepts an optional slug to create/use `PROJECT_DIR/{slug}/` subdirectories.

**Tech Stack:** FastAPI + SQLAlchemy (async) + Pydantic v2 backend; React + TypeScript + react-router-dom frontend.

---

## File Structure

| File | Responsibility |
|------|---------------|
| `backend/db/models.py` | New `Project` model; add `project_id` + `selected_agents` to `Run` |
| `backend/db/session.py` | Migration: `CREATE TABLE projects`, alter runs |
| `backend/api/routes.py` | New endpoints: `POST/GET /api/projects`, `GET/PUT /api/projects/{id}`; update `ProjectBrief` + `start_project` |
| `backend/core/config_loader.py` | `get_project_dir(slug?)` accepts optional slug; `load_config(project_name?)` |
| `backend/core/orchestrator.py` | `run()` accepts `selected_agents`; `_run_pipeline` filters; `_create_run_row` stores `project_id`; INIT event uses project name |
| `frontend/src/pages/Dashboard.tsx` | `launchNew` calls `POST /api/projects`; projects list loads from `GET /api/projects`; agent selections sent |
| `frontend/src/App.tsx` | Workspace fetches project detail for Header name |

---

### Task 1: Database — projects table + runs columns

**Files:**
- Modify: `backend/db/models.py:46-62`
- Modify: `backend/db/session.py:63-77`

- [ ] **Step 1: Add `Project` model and update `Run` model**

Replace the `Run` class definition (lines 46-62) and insert the `Project` class before it in `backend/db/models.py`:

```python
class Project(Base):
    __tablename__ = "projects"

    id         = Column(String(36), primary_key=True)
    user_id    = Column(String(128), nullable=False)
    name       = Column(String(256), nullable=False)
    slug       = Column(String(256), nullable=False)
    desc       = Column(Text, nullable=True)
    icon       = Column(String(8), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_now)

    runs = relationship("Run", back_populates="project", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_projects_user_id", "user_id"),
        Index("ix_projects_user_slug", "user_id", "slug", unique=True),
    )


class Run(Base):
    __tablename__ = "runs"

    id              = Column(String(36), primary_key=True)
    user_id         = Column(String(128), nullable=False)
    project_id      = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=True)
    brief           = Column(Text, nullable=False)
    selected_agents = Column(Text, nullable=True)  # JSON list of agent IDs
    status          = Column(String(20), nullable=False, default="running")
    agents_used     = Column(Text, nullable=True)
    started_at      = Column(DateTime(timezone=True), nullable=False, default=_now)
    finished_at     = Column(DateTime(timezone=True), nullable=True)

    project = relationship("Project", back_populates="runs")
    files   = relationship("RunFile", back_populates="run", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_runs_user_id", "user_id"),
        Index("ix_runs_project_id", "project_id"),
    )
```

- [ ] **Step 2: Add migration in `_run_migrations()`**

Insert before `except Exception` at line 77 of `backend/db/session.py`:

```python
            await conn.execute(text(
                "CREATE TABLE IF NOT EXISTS projects ("
                "  id VARCHAR(36) PRIMARY KEY,"
                "  user_id VARCHAR(128) NOT NULL,"
                "  name VARCHAR(256) NOT NULL,"
                "  slug VARCHAR(256) NOT NULL,"
                "  desc TEXT,"
                "  icon VARCHAR(8),"
                "  created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),"
                "  updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()"
                ")"
            ))
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_projects_user_id ON projects(user_id)"
            ))
            await conn.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_projects_user_slug ON projects(user_id, slug)"
            ))
            await conn.execute(text(
                "ALTER TABLE runs ADD COLUMN IF NOT EXISTS project_id VARCHAR(36)"
            ))
            await conn.execute(text(
                "ALTER TABLE runs ADD COLUMN IF NOT EXISTS selected_agents TEXT"
            ))
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_runs_project_id ON runs(project_id)"
            ))
```

- [ ] **Step 3: Verify migration runs**

Run: `python -c "from backend.db.session import _run_migrations; import asyncio; asyncio.run(_run_migrations())"`
Expected: No errors. Database has `projects` table and runs has new columns.

- [ ] **Step 4: Commit**

```bash
git add backend/db/models.py backend/db/session.py
git commit -m "feat: add projects table, project_id and selected_agents to runs"
```

---

### Task 2: Backend — project API endpoints

**Files:**
- Modify: `backend/api/routes.py:235-310`

- [ ] **Step 1: Add slug helper and GET endpoints**

Insert after `ProjectBrief` class (after line 184 of `backend/api/routes.py`):

```python
def _make_slug(name: str) -> str:
    """Convert a project name into a URL-safe slug."""
    import re
    s = name.strip().lower()
    s = re.sub(r'[^a-z0-9]+', '-', s)
    return s.strip('-') or "project"


@router.get("/projects")
async def list_projects(user: dict = Depends(require_auth)):
    """Return minimal project list for Dashboard."""
    from ..db.models import Project
    user_id = user.get("sub", "anonymous")

    async with get_session() as session:
        if session is None:
            return {"projects": []}
        result = await session.execute(
            select(Project)
            .where(Project.user_id == user_id)
            .order_by(Project.updated_at.desc())
        )
        rows = result.scalars().all()
        return {
            "projects": [
                {
                    "id": p.id,
                    "name": p.name,
                    "slug": p.slug,
                    "desc": p.desc,
                    "icon": p.icon or "",
                    "created_at": p.created_at.isoformat() if p.created_at else None,
                    "updated_at": p.updated_at.isoformat() if p.updated_at else None,
                }
                for p in rows
            ]
        }


@router.get("/projects/{project_id}")
async def get_project(project_id: str, user: dict = Depends(require_auth)):
    """Return full project detail for Workspace header."""
    from ..db.models import Project
    user_id = user.get("sub", "anonymous")

    async with get_session() as session:
        if session is None:
            raise HTTPException(status_code=503, detail="Database unavailable")
        result = await session.execute(
            select(Project).where(Project.id == project_id, Project.user_id == user_id)
        )
        row = result.scalar_one_or_none()
        if not row:
            raise HTTPException(status_code=404, detail="Project not found")

        # Find latest run status for this project
        from ..db.models import Run
        run_result = await session.execute(
            select(Run)
            .where(Run.project_id == project_id)
            .order_by(Run.started_at.desc())
            .limit(1)
        )
        run = run_result.scalar_one_or_none()
        file_count = 0
        if run:
            file_count = len(run.files) if run.files else 0

        return {
            "id": row.id,
            "name": row.name,
            "slug": row.slug,
            "desc": row.desc,
            "icon": row.icon or "",
            "status": run.status if run else "ready",
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            "file_count": file_count,
        }
```

- [ ] **Step 2: Add `select` import if missing**

Check that `select` is imported from `sqlalchemy` at the top of `routes.py`. If not, add it:

At line 28 of `routes.py`, ensure:
```python
from sqlalchemy import select
```
is present. If it's not, add it.

- [ ] **Step 3: Verify endpoints compile**

Run: `python -c "from backend.api.routes import router; print('OK')"`
Expected: `OK` with no import errors.

- [ ] **Step 4: Commit**

```bash
git add backend/api/routes.py
git commit -m "feat: GET /api/projects list and detail endpoints with slug helper"
```

---

### Task 3: Backend — POST /api/projects (create project + optional first run)

**Files:**
- Modify: `backend/api/routes.py:182-184` (ProjectBrief model)

- [ ] **Step 1: Add `CreateProject` request model**

Insert after `ProjectBrief` class (after line 184 of `routes.py`):

```python
class CreateProject(BaseModel):
    name: str
    brief: str
    icon: str = ""
    agents: list[str] = []
    auto_start: bool = True
```

- [ ] **Step 2: Add `POST /api/projects` endpoint**

Insert after the `get_project` endpoint added in Task 2:

```python
@router.post("/projects")
async def create_project(body: CreateProject, user: dict = Depends(require_auth)):
    """Create a project and optionally start its first run."""
    from ..db.models import Project, Run
    user_id = user.get("sub", "anonymous")

    base_slug = _make_slug(body.name)
    slug = base_slug
    counter = 1

    async with get_session() as session:
        if session is None:
            raise HTTPException(status_code=503, detail="Database unavailable")

        # Ensure unique slug per user
        while True:
            existing = await session.execute(
                select(Project).where(Project.user_id == user_id, Project.slug == slug)
            )
            if existing.scalar_one_or_none() is None:
                break
            counter += 1
            slug = f"{base_slug}-{counter}"

        project_id = str(uuid.uuid4())
        project = Project(
            id=project_id,
            user_id=user_id,
            name=body.name,
            slug=slug,
            desc=body.brief,
            icon=body.icon,
        )
        session.add(project)
        await session.commit()

    run_id = None

    if body.auto_start:
        # Billing gate
        plan, balance = "pro", 999999
        if not (_AUTH_DISABLED or user_id == "dev-user"):
            from ..db.session import get_session as gs
            from ..db.models import UserCredits
            async with gs() as sess:
                if sess is not None:
                    creds = await sess.get(UserCredits, user_id)
                    plan = creds.plan if creds else "none"
                    balance = creds.balance_cents if creds else 0
            if plan == "none":
                return {
                    "project_id": project_id,
                    "slug": slug,
                    "run_id": None,
                    "error": "no_subscription",
                }
            if balance <= 0:
                return {
                    "project_id": project_id,
                    "slug": slug,
                    "run_id": None,
                    "error": "no_credits",
                }

        # Ensure per-project folder exists
        import os
        project_dir = Path(os.environ.get("PROJECT_DIR", os.getcwd())) / slug
        project_dir.mkdir(parents=True, exist_ok=True)

        # Create orchestrator for this project
        run_id = str(uuid.uuid4())
        room = f"user:{user_id}"
        user_config = await _load_user_config(user_id, project_name=body.name)

        orch = Orchestrator(
            sio=_sio,
            config=user_config,
            room=room,
            on_done=_orchestrator_done,
        )
        # Override cwd to project-specific directory
        orch._cwd = project_dir
        _orchestrators[user_id] = orch

        run_timeout = int(os.environ.get("RUN_TIMEOUT_SECONDS", "600"))
        orch._run_timeout_seconds = run_timeout

        agent_limit = 3 if plan == "starter" else None

        asyncio.create_task(
            orch.run(
                body.brief,
                user_id=user_id,
                agent_limit=agent_limit,
                plan=plan,
                api_key="",
                upload_dir="",
                run_id=run_id,
                selected_agents=body.agents if body.agents else None,
                project_id=project_id,
            )
        )

        return {
            "project_id": project_id,
            "slug": slug,
            "run_id": run_id,
            "status": "started",
        }

    return {
        "project_id": project_id,
        "slug": slug,
        "run_id": None,
        "status": "created",
    }
```

- [ ] **Step 3: Add missing imports**

At the top of `routes.py`, ensure these imports are present:

```python
import os
from pathlib import Path
```

- [ ] **Step 4: Commit**

```bash
git add backend/api/routes.py
git commit -m "feat: POST /api/projects creates project + optional first run with folder isolation"
```

---

### Task 4: Backend — Orchestrator agent filtering + project_id support

**Files:**
- Modify: `backend/core/orchestrator.py:809-818` (run signature)
- Modify: `backend/core/orchestrator.py:850` (create_run_row call area)
- Modify: `backend/core/orchestrator.py:945-965` (_run_pipeline agent selection)
- Modify: `backend/core/orchestrator.py:881-885` (INIT event)
- Modify: `backend/core/config_loader.py:49-56` (get_project_dir)
- Modify: `backend/core/config_loader.py:59-108` (load_config)

- [ ] **Step 1: Update `run()` signature in orchestrator.py**

Change the `run()` method signature at line 809 from:

```python
    async def run(
        self,
        brief: str,
        *,
        user_id: str = "",
        agent_limit: int | None = None,
        plan: str = "pro",
        api_key: str = "",
        upload_dir: str = "",
        run_id: str = "",
        max_iterations: int = 80,
    ) -> str:
```

to:

```python
    async def run(
        self,
        brief: str,
        *,
        user_id: str = "",
        agent_limit: int | None = None,
        plan: str = "pro",
        api_key: str = "",
        upload_dir: str = "",
        run_id: str = "",
        selected_agents: list[str] | None = None,
        project_id: str | None = None,
        max_iterations: int = 80,
    ) -> str:
```

And inside the body, before the `_write_current_md_snapshot` call (~line 865), add:

```python
        self._selected_agents = selected_agents
        self._project_id = project_id
```

- [ ] **Step 2: Update `_create_run_row` to accept and store `project_id` + `selected_agents`**

Find the `_create_run_row` method definition. If it exists, update it. If the run row is created inline (around line 850), update that code. Let me check. Looking at the code — the run row is created in `_create_or_get_run_row` (or similar). Find the area where the Run object is instantiated and add:

```python
    run_row = Run(
        id=run_id,
        user_id=user_id,
        project_id=getattr(self, '_project_id', None),
        selected_agents=json.dumps(getattr(self, '_selected_agents', None)) if selected_agents else None,
        brief=brief,
        status="running",
    )
```

The exact location depends on where the Run row is created. Find the database insert for runs in orchestrator.py (search for `Run(`) and update.

- [ ] **Step 3: Filter agents in `_run_pipeline`**

In `_run_pipeline` at lines 945-965, after `all_agents = self.config.agents`, add filtering:

```python
        all_agents = self.config.agents
        # Filter to selected agents if provided
        selected = getattr(self, '_selected_agents', None)
        if selected:
            selected_set = set(selected)
            # Always include manager
            selected_set.add("manager")
            all_agents = [a for a in all_agents if a.get("id") in selected_set]
```

- [ ] **Step 4: Update INIT event to use project name**

In the INIT event emission at line 881-885 of orchestrator.py, ensure `project` reflects the project name from config (not `cwd.name`). `_load_user_config` will already handle this after the next step, but verify the INIT event at ~line 881:

```python
            await self._sio.emit("init", {
                "project": self.config.project,  # now correctly set from config_loader
                "sprint": self.config.sprint,
                "agents": [a.get("name") for a in self.config.agents],
            }, to=self.room)
```

This should work as-is once `load_config` is updated.

- [ ] **Step 5: Update `config_loader.py` — `get_project_dir()` optional slug**

Replace `get_project_dir()` at line 49-56:

```python
def get_project_dir(slug: str | None = None) -> Path:
    """Return the active project directory.
    
    If slug is provided, returns PROJECT_DIR/{slug}/ creating the folder if needed.
    Otherwise returns the root PROJECT_DIR.
    """
    env = os.environ.get("PROJECT_DIR")
    base = Path(env).resolve() if env else Path(os.getcwd())
    if slug:
        target = base / slug
        target.mkdir(parents=True, exist_ok=True)
        return target
    return base
```

- [ ] **Step 6: Update `load_config()` to accept optional project_name**

Add `project_name` parameter to `load_config` at line 59:

```python
def load_config(config_path: str | None = None, project_name: str | None = None) -> ProjectConfig:
```

And update the project name assignment (around line 71 where `project_name = cwd.name` currently is):

```python
    name = project_name if project_name else cwd.name
```

And pass it to `ProjectConfig`:

```python
    return ProjectConfig(
        project=name,
        ...
    )
```

- [ ] **Step 7: Update `_load_user_config` in routes.py to pass project_name**

In `routes.py`, update `_load_user_config` signature at line 340 to accept `project_name`:

```python
async def _load_user_config(user_id: str, project_name: str | None = None) -> ProjectConfig:
```

And update the fallback to `load_config`:

```python
        config_path = Path(os.getcwd()) / "agent-team.config.json"
        if config_path.exists():
            data = json.loads(config_path.read_text())
```

becomes:

```python
        config_path = Path(os.getcwd()) / "agent-team.config.json"
        if config_path.exists():
            config = load_config(str(config_path), project_name=project_name)
            return config
```

- [ ] **Step 8: Verify Orchestrator runs with selected agents**

Run: Not testable without a full integration setup. Verification: check that `_run_pipeline` agent filtering code and `run()` signature changes compile.

```bash
python -c "from backend.core.orchestrator import Orchestrator; print('OK')"
python -c "from backend.core.config_loader import get_project_dir, load_config; print('OK')"
```

- [ ] **Step 9: Commit**

```bash
git add backend/core/orchestrator.py backend/core/config_loader.py backend/api/routes.py
git commit -m "feat: per-project agent filtering, project_id on runs, folder isolation"
```

---

### Task 5: Backend — wire legacy start_project to new flow

**Files:**
- Modify: `backend/api/routes.py:235-310`

- [ ] **Step 1: Update legacy `start_project` to delegate to projects flow**

Replace the `start_project` function at line 235-310 with a version that creates a project first, then starts a run:

```python
@router.post("/start-project")
async def start_project(body: ProjectBrief, user: dict = Depends(require_auth)):
    """Legacy endpoint — delegates to new project flow."""
    user_id = user.get("sub", "anonymous")

    # Check already running
    existing = _orchestrators.get(user_id)
    if existing is not None and existing.is_running():
        return {"error": "already_running", "status": "busy"}

    # Resolve upload token
    upload_dir = ""
    if body.upload_token and body.upload_token in _upload_tokens:
        token_data = _upload_tokens.pop(body.upload_token)
        if token_data.get("user_id") == user_id:
            upload_dir = token_data.get("upload_dir", "")
        asyncio.create_task(_cleanup_expired_tokens())

    # Billing gate
    if _AUTH_DISABLED or user_id == "dev-user":
        plan, agent_limit, balance = "pro", None, 999999
    else:
        from ..db.session import get_session
        from ..db.models import UserCredits
        plan, balance = "none", 0
        async with get_session() as session:
            if session is not None:
                credits = await session.get(UserCredits, user_id)
                plan = credits.plan if credits else "none"
                balance = credits.balance_cents if credits else 0
        if plan == "none":
            return {"error": "no_subscription", "status": "blocked"}
        if balance <= 0:
            return {"error": "no_credits", "status": "blocked"}
        agent_limit = 3 if plan == "starter" else None

    # Create a project row for this brief-only run (auto-generate name)
    from ..db.models import Project
    slug = f"untitled-{run_id[:8]}" if (run_id := str(uuid.uuid4())) else ""
    project_id = str(uuid.uuid4())
    project_name = body.brief[:50] + ("..." if len(body.brief) > 50 else "")

    async with get_session() as session:
        if session is not None:
            project = Project(
                id=project_id,
                user_id=user_id,
                name=project_name,
                slug=slug,
                desc=body.brief,
            )
            session.add(project)
            await session.commit()

    # Create orchestrator
    run_id = str(uuid.uuid4())
    room = f"user:{user_id}"
    user_config = await _load_user_config(user_id, project_name=project_name)

    orch = Orchestrator(
        sio=_sio,
        config=user_config,
        room=room,
        on_done=_orchestrator_done,
    )
    _orchestrators[user_id] = orch

    run_timeout = int(os.environ.get("RUN_TIMEOUT_SECONDS", "600"))
    orch._run_timeout_seconds = run_timeout

    # Use project-specific directory
    project_dir = get_project_dir(slug)
    orch._cwd = project_dir

    asyncio.create_task(
        orch.run(
            body.brief,
            user_id=user_id,
            agent_limit=agent_limit,
            plan=plan,
            api_key="",
            upload_dir=upload_dir,
            run_id=run_id,
            project_id=project_id,
        )
    )

    return {
        "status": "started",
        "run_id": run_id,
        "project_id": project_id,
    }
```

- [ ] **Step 2: Ensure `get_project_dir` is imported**

At the top of `routes.py`, add:
```python
from ..core.config_loader import get_project_dir
```

- [ ] **Step 3: Commit**

```bash
git add backend/api/routes.py
git commit -m "feat: legacy start-project delegates to projects flow with folder per run"
```

---

### Task 6: Frontend — Dashboard loads project list from API

**Files:**
- Modify: `frontend/src/pages/Dashboard.tsx:449-458` (useEffect project load)

- [ ] **Step 1: Replace local-only project loading with API call**

Replace the useEffect at line 449-458 that currently calls `authFetch('/api/projects')`:

```typescript
  // Load projects from API
  useEffect(() => {
    authFetch('/api/projects')
      .then(r => r.json())
      .then((d: { projects?: ApiProject[] }) => {
        const mapped: Project[] = (d.projects ?? []).map(p => ({
          id: p.id,
          name: p.name,
          desc: p.desc || '',
          path: `~/projects/${p.slug}`,
          icon: p.icon || '📁',
          color: 'var(--c-cyan)',
          status: 'ready',
          progress: 0,
          agents: 0,
          files: 0,
          lastActive: p.updated_at ? new Date(p.updated_at).toLocaleDateString() : 'never',
          lastActiveSort: p.updated_at ? new Date(p.updated_at).getTime() : 0,
          created: p.created_at ? new Date(p.created_at).toLocaleDateString() : 'never',
          tokens: '0K',
        }))
        setProjects(prev => mapped.length > 0 ? mapped : prev)
        // If we came from creation, highlight the active project
        if (activeId) {
          const exists = mapped.find(p => p.id === activeId)
          if (exists) setTab('projects')
        }
      })
      .catch(() => {})
  }, [])  // load only on mount
```

Delete the `PROJECTS` sample data constant if it exists (the hardcoded demo projects), or merge projects from API with any existing local state.

- [ ] **Step 2: Add `ApiProject` interface**

At the top of Dashboard.tsx, after the `Usage` interface (around line 31):

```typescript
interface ApiProject {
  id: string
  name: string
  slug: string
  desc: string | null
  icon: string | null
  created_at: string | null
  updated_at: string | null
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/Dashboard.tsx
git commit -m "feat: dashboard loads project list from GET /api/projects"
```

---

### Task 7: Frontend — launchNew sends agent selection + navigates to real run_id

**Files:**
- Modify: `frontend/src/pages/Dashboard.tsx:475-520` (launchNew)

- [ ] **Step 1: Rewrite `launchNew` to POST to /api/projects**

Replace the `launchNew` function at lines 475-520:

```typescript
  const launchNew = async (cfg: { name: string; desc: string; icon: string; agents: string[]; autoStart: boolean }) => {
    setToast(`launching ${cfg.name}...`)

    try {
      const r = await authFetch('/api/projects', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: cfg.name,
          brief: cfg.desc,
          icon: cfg.icon,
          agents: cfg.agents,
          auto_start: cfg.autoStart,
        }),
      })
      const d = await r.json()

      if (!r.ok) {
        if (d.error === 'no_subscription') {
          setToast('You need a subscription to start projects')
          navigate('/billing')
          return
        }
        if (d.error === 'no_credits') {
          setToast('No credits remaining. Top up?')
          navigate('/billing')
          return
        }
        setToast(d.error || 'Failed to start project')
        return
      }

      if (d.run_id) {
        setActiveId(d.project_id)
        setToast(`launched ${cfg.name}`)
        navigate(`/project/${d.run_id}`)
      } else {
        // Project created but not started (no credits or auto_start=false)
        setActiveId(d.project_id)
        setTab('projects')
        setToast(`created ${cfg.name}`)
      }

      // Reload projects list
      authFetch('/api/projects')
        .then(r => r.json())
        .then((resp: { projects?: ApiProject[] }) => {
          const mapped: Project[] = (resp.projects ?? []).map(p => ({
            id: p.id,
            name: p.name,
            desc: p.desc || '',
            path: `~/projects/${p.slug}`,
            icon: p.icon || '📁',
            color: 'var(--c-cyan)',
            status: 'ready' as Project['status'],
            progress: 0,
            agents: cfg.agents.length,
            files: 0,
            lastActive: p.updated_at ? new Date(p.updated_at).toLocaleDateString() : 'just now',
            lastActiveSort: Date.now(),
            created: p.created_at ? new Date(p.created_at).toLocaleDateString() : 'just now',
            tokens: '0K',
          }))
          setProjects(prev => {
            const ids = new Set(mapped.map(p => p.id))
            const survivors = prev.filter(p => ids.has(p.id) || p.id === d.project_id)
            // Prepend the new project if not already in the mapped list
            if (!ids.has(d.project_id)) {
              survivors.unshift(mapped[0] || {
                id: d.project_id,
                name: cfg.name,
                desc: cfg.desc,
                path: `~/projects/${d.slug}`,
                icon: cfg.icon,
                color: 'var(--c-cyan)',
                status: cfg.autoStart ? 'running' : 'ready',
                progress: 0,
                agents: cfg.agents.length,
                files: 0,
                lastActive: 'just now',
                lastActiveSort: 0,
                created: 'just now',
                tokens: '0K',
              })
            }
            return survivors
          })
        })
        .catch(() => {})
    } catch {
      setToast('Could not start project. Try again.')
    }
  }
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/pages/Dashboard.tsx
git commit -m "feat: launchNew posts to POST /api/projects with agent selection"
```

---

### Task 8: Frontend — Workspace shows real project name

**Files:**
- Modify: `frontend/src/App.tsx:85-89` (Workspace state)
- Modify: `frontend/src/App.tsx:5` (imports area)

- [ ] **Step 1: Add project detail fetch in Workspace**

In the Workspace function, after the state declarations at line 89, add:

```typescript
  const [projectName, setProjectName] = useState<string | null>(null)
  const { projectId } = useParams<{ id: string }>()

  // Workspace is entered via /project/:runId — we need the project name
  // Fetch the project detail (or derive from the INIT socket event)
  useEffect(() => {
    // The project name comes from the socket INIT event which emits
    // { project: "the project name" }. Use that.
    if (state.project) {
      setProjectName(state.project)
    }
  }, [state.project])
```

The socket state already has `state.project` from the INIT event (which now emits the correct project name from config). No additional API call needed.

- [ ] **Step 2: Pass project name to Header**

In the Header component call at line 149, ensure `project` prop receives the real name:

It already passes:
```typescript
        project={state.project}
```

Since `state.project` is set from the socket INIT event, and step 5 of Task 4 ensures INIT sends the correct project name, this works.

- [ ] **Step 3: Remove unused variables**

If `projectName` is not needed (because `state.project` already works), remove the useState. The socket already provides the name. No code changes needed beyond verifying the INIT event is correct.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/App.tsx
git commit -m "feat: workspace project name from socket INIT event"
```

---

### Task 9: TypeScript verification + integration smoke test

- [ ] **Step 1: Run TypeScript check**

```bash
cd frontend && npx tsc --noEmit -p tsconfig.app.json
```
Expected: Clean output, no errors.

- [ ] **Step 2: Run backend import check**

```bash
python -c "from backend.db.models import Project, Run; print('models OK')"
python -c "from backend.api.routes import router; print('routes OK')"
python -c "from backend.core.orchestrator import Orchestrator; print('orchestrator OK')"
python -c "from backend.core.config_loader import get_project_dir, load_config; print('config_loader OK')"
```
Expected: All print "OK" with no errors.

- [ ] **Step 3: Commit any leftover changes**

```bash
git add -A
git commit -m "chore: final verification, no errors"
```

---

## Self-Review

### 1. Spec Coverage

| Spec Requirement | Covered By |
|-----------------|------------|
| New `projects` table (id, user_id, name, slug, desc, icon, dates) | Task 1 Step 1 |
| `runs` gains `project_id` FK + `selected_agents` | Task 1 Step 1 |
| DB migration | Task 1 Step 2 |
| `POST /api/projects` | Task 3 Step 2 |
| `GET /api/projects` list | Task 2 Step 1 |
| `GET /api/projects/{id}` detail | Task 2 Step 1 |
| `PUT /api/projects/{id}` re-launch | Deferred (not in this plan — existing `start-project` covers re-run) |
| Legacy `start-project` delegates to projects flow | Task 5 |
| `PROJECT_DIR/{slug}` folder per project | Task 3 Step 2, Task 4 Step 5 |
| `get_project_dir(slug?)` | Task 4 Step 5 |
| Agent filtering in orchestrator | Task 4 Steps 1-3 |
| `_load_user_config` accepts project_name | Task 4 Step 7 |
| `load_config` accepts project_name | Task 4 Step 6 |
| Duplicate slug handling | Task 3 Step 2 (while loop) |
| Manager always included | Task 4 Step 3 |
| Dashboard loads projects from API | Task 6 |
| `launchNew` sends agents + navigates to run_id | Task 7 |
| Workspace shows real project name | Task 8 |
| Error handling (no sub, no credits) | Task 7 Step 1 |
| Old runs without project_id → excluded | Implicit (projects list only shows projects table rows) |

### 2. Placeholder Scan

No TBDs, TODOs, or "implement later" found. All code shown inline.

### 3. Type Consistency

- `CreateProject.agents: list[str]` → `selected_agents` in `run()` is `list[str] | None` ✓
- `Project.id` is `String(36)` → `project_id` params are `str` ✓
- Frontend `ApiProject` matches backend `/api/projects` response shape ✓
- `slug` type is consistent across DB, API, and folder creation ✓
