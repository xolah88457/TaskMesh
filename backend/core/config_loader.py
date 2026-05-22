import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

DEFAULT_BASE_URL = "https://opencode.ai/zen/v1"

# ── OpenRouter (inactive — switch when ready) ──────────────────────────────────
# When switching to OpenRouter:
#   1. Replace DEFAULT_BASE_URL above with OPENROUTER_BASE_URL
#   2. Replace DEFAULT_AGENTS model IDs with OPENROUTER equivalents
#   3. Replace OPENCODE_GO_API_KEY env var with OPENROUTER_API_KEY in config load
#   4. Re-enable THINKING_MODEL_IDS in base_agent.py
#
# OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
# ── End OpenRouter ─────────────────────────────────────────────────────────────

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


def get_project_dir() -> Path:
    """Return the active project directory.

    Defaults to cwd, but PROJECT_DIR env var lets you run the backend from
    the MiniMaxClone repo root while targeting a completely different folder.
    """
    env = os.environ.get("PROJECT_DIR")
    return Path(env).resolve() if env else Path(os.getcwd())


def load_config(user_id: str = "") -> ProjectConfig:
    """Load agent config for a user. Falls back to disk file if no per-user config."""
    cwd = get_project_dir()
    project_name = cwd.name

    sprint = "Sprint #1"
    agents = [a.copy() for a in DEFAULT_AGENTS]
    provider = ProviderConfig()

    # Try per-user config from DB first
    if user_id:
        try:
            from ..db.session import get_session
            from ..db.models import User
            import asyncio as _asyncio
            async def _load():
                async with get_session() as session:
                    if session is not None:
                        user_row = await session.get(User, user_id)
                        if user_row and user_row.config_json:
                            return json.loads(user_row.config_json)
                    return None
            data = _asyncio.get_event_loop().run_until_complete(_load())
            if data:
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
        except Exception:
            pass

    # Fall back to disk file if no per-user config loaded
    if agents == [a.copy() for a in DEFAULT_AGENTS]:
        config_path = cwd / "agent-team.config.json"
        if config_path.exists():
            try:
                data = json.loads(config_path.read_text())
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
        provider.apiKey = os.environ.get("OPENCODE_GO_API_KEY", "")
        # OpenRouter switch: replace line above with:
        # provider.apiKey = os.environ.get("OPENROUTER_API_KEY", "")

    # Always ensure manager is first
    mgr = next((a for a in agents if a.get("id") == "manager"), DEFAULT_AGENTS[0].copy())
    others = [a for a in agents if a.get("id") != "manager"]
    agents = [mgr] + others

    return ProjectConfig(project=project_name, sprint=sprint, agents=agents, provider=provider)


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
