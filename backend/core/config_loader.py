import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

_PROVIDER = os.environ.get("PROVIDER", "zen").lower()

if _PROVIDER == "openrouter":
    DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
    _API_KEY_ENV = "OPENROUTER_API_KEY"
else:
    DEFAULT_BASE_URL = "https://opencode.ai/zen/v1"
    _API_KEY_ENV = "OPENCODE_GO_API_KEY"

# Default agent layout — manager only. Users add executors via Settings.
# The manager is always required as the pipeline coordinator.
DEFAULT_AGENTS = [
    {
        "id": "manager",    "name": "Manager",    "role": "Coordinator",
        "model": "deepseek-v4-pro",
        "temperature": 0.6, "top_p": 0.9, "top_k": 0, "thinking_budget": 0,
        "color": "#6366f1", "icon": "👔", "planner": False,
    },
]

DEFAULT_PROVIDER = {
    "name": "OpenCode Zen",
    "baseURL": DEFAULT_BASE_URL,
    "apiKey": "",
}


@dataclass
class ProviderConfig:
    name: str = "OpenCode Zen"
    baseURL: str = DEFAULT_BASE_URL
    apiKey: str = ""


@dataclass
class ProjectConfig:
    project: str
    sprint: str
    agents: List[dict]
    provider: ProviderConfig = field(default_factory=ProviderConfig)


def get_project_dir(slug: str | None = None, user_id: str | None = None) -> Path:
    """Return the active project directory.

    Layouts:
      get_project_dir()                  -> PROJECT_DIR
      get_project_dir(user_id=u)         -> PROJECT_DIR/{u}
      get_project_dir(slug=s)            -> PROJECT_DIR/{s}           (legacy)
      get_project_dir(slug=s, user_id=u) -> PROJECT_DIR/{u}/{s}       (recommended)

    The slug-only layout is preserved so older callers continue to function
    during the multi-tenant filesystem migration. New code should pass user_id
    — two users with the same slug collide on the slug-only layout, which is
    a cross-tenant data-leak risk on the filesystem layer.
    """
    env = os.environ.get("PROJECT_DIR")
    base = Path(env).resolve() if env else Path(os.getcwd())
    if user_id:
        # Sanitize: only allow filesystem-safe characters in the tenant key.
        # user_id is a UUID in production but we defend in depth.
        safe = "".join(c for c in user_id if c.isalnum() or c in "-_")
        base = base / (safe or "anonymous")
    if slug:
        target = base / slug
        target.mkdir(parents=True, exist_ok=True)
        return target
    if user_id:
        base.mkdir(parents=True, exist_ok=True)
    return base


def load_config(config_path: str | None = None, project_name: str | None = None) -> ProjectConfig:
    """Load agent config from disk. Per-user DB-backed config is handled by
    the async helper `_load_user_config` in `api/routes.py` — call that
    directly from FastAPI handlers.

    If config_path is provided, loads from that path. Otherwise loads from
    the default agent-team.config.json in the project directory.
    """
    cwd = get_project_dir()
    name = project_name if project_name else cwd.name

    sprint = "Sprint #1"
    agents = [a.copy() for a in DEFAULT_AGENTS]
    provider = ProviderConfig()

    # Fall back to disk file if no per-user config loaded
    if agents == [a.copy() for a in DEFAULT_AGENTS]:
        cfg_path = Path(config_path) if config_path else cwd / "agent-team.config.json"
        if cfg_path.exists():
            try:
                data = json.loads(cfg_path.read_text())
                sprint = data.get("sprint", sprint)
                if isinstance(data.get("agents"), list) and data["agents"]:
                    agents = data["agents"]
                if isinstance(data.get("provider"), dict):
                    p = data["provider"]
                    provider = ProviderConfig(
                        name=p.get("name", provider.name),
                        baseURL=p.get("baseURL", provider.baseURL),
                        apiKey=p.get("apiKey", provider.apiKey),
                    )
            except (json.JSONDecodeError, OSError):
                pass

    # Fall back to env var for API key if not in config
    if not provider.apiKey:
        provider.apiKey = os.environ.get(_API_KEY_ENV, "")
        # OpenRouter switch: replace line above with:
        # provider.apiKey = os.environ.get("OPENROUTER_API_KEY", "")

    # Always ensure manager is first
    mgr = next((a for a in agents if a.get("id") == "manager"), DEFAULT_AGENTS[0].copy())
    others = [a for a in agents if a.get("id") != "manager"]
    agents = [mgr] + others

    return ProjectConfig(project=name, sprint=sprint, agents=agents, provider=provider)


async def save_config(data: dict, user_id: str = "") -> None:
    """Save agent config — per-user in DB if user_id provided, else disk file."""
    if user_id:
        from ..db.session import get_session
        from ..db.models import User
        async with get_session() as session:
            if session is not None:
                user_row = await session.get(User, user_id)
                if user_row is not None:
                    user_row.config_json = json.dumps(data, ensure_ascii=False)
                    return
    # Fallback: write to disk file (global default)
    config_path = Path(os.getcwd()) / "agent-team.config.json"
    config_path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
