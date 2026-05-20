import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

DEFAULT_BASE_URL = "https://opencode.ai/zen/go/v1"

# ── OpenRouter (inactive — switch when ready) ──────────────────────────────────
# When switching to OpenRouter:
#   1. Replace DEFAULT_BASE_URL above with OPENROUTER_BASE_URL
#   2. Replace DEFAULT_AGENTS model IDs with OPENROUTER_DEFAULT_AGENTS below
#   3. Replace OPENCODE_GO_API_KEY env var with OPENROUTER_API_KEY in config load
#   4. Re-enable THINKING_MODEL_IDS in base_agent.py
#
# OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
#
# OPENROUTER_DEFAULT_AGENTS = [
#     {"id": "manager",    "model": "deepseek/deepseek-chat",             "temperature": 0.6},
#     {"id": "webdev",     "model": "moonshotai/kimi-k2",                 "temperature": 0.6},
#     {"id": "researcher", "model": "moonshotai/kimi-k2",                 "temperature": 0.6},
#     {"id": "backend",    "model": "deepseek/deepseek-chat",             "temperature": 0.5},
#     {"id": "frontend",   "model": "qwen/qwen-2.5-coder-32b-instruct",  "temperature": 0.6},
#     {"id": "tester",     "model": "qwen/qwen-2.5-coder-32b-instruct",  "temperature": 0.5},
#     {"id": "docs",       "model": "mistralai/mistral-7b-instruct",      "temperature": 0.4},
#     {"id": "logger",     "model": "meta-llama/llama-3.1-8b-instruct",   "temperature": 0.3},
#     {"id": "reviewer",   "model": "deepseek/deepseek-chat",             "temperature": 0.6},
# ]
# ── End OpenRouter ─────────────────────────────────────────────────────────────

DEFAULT_AGENTS = [
    {
        "id": "manager",    "name": "Manager",    "role": "Coordinator",
        "model": "deepseek-v4-pro",
        "temperature": 0.6, "top_p": 0.9, "top_k": 0, "thinking_budget": 0,
        "color": "#6366f1", "icon": "👔", "planner": False,
    },
    {
        "id": "webdev",     "name": "WebDev",     "role": "Architect",
        "model": "kimi-k2.6",
        "temperature": 0.6, "top_p": 0.9, "top_k": 0, "thinking_budget": 0,
        "color": "#8b5cf6", "icon": "🏗", "planner": True,
    },
    {
        "id": "researcher", "name": "Researcher", "role": "Tech Lead",
        "model": "kimi-k2.5",
        "temperature": 0.6, "top_p": 0.9, "top_k": 0, "thinking_budget": 0,
        "color": "#67e8f9", "icon": "🧠", "planner": True,
    },
    {
        "id": "backend",    "name": "Backend",    "role": "API",
        "model": "deepseek-v4-flash",
        "temperature": 0.5, "top_p": 0.85, "top_k": 0, "thinking_budget": 0,
        "color": "#f97316", "icon": "⚙️", "planner": False,
    },
    {
        "id": "frontend",   "name": "Frontend",   "role": "UI/UX",
        "model": "mimo-v2.5",
        "temperature": 0.6, "top_p": 0.9, "top_k": 0, "thinking_budget": 0,
        "color": "#22c55e", "icon": "🎨", "planner": False,
    },
    {
        "id": "tester",     "name": "Tester",     "role": "QA",
        "model": "qwen3.5-plus",
        "temperature": 0.5, "top_p": 0.85, "top_k": 0, "thinking_budget": 0,
        "color": "#ef4444", "icon": "🧪", "planner": False,
    },
    {
        "id": "docs",       "name": "Docs",       "role": "Writer",
        "model": "qwen3.5-plus",
        "temperature": 0.4, "top_p": 0.85, "top_k": 0, "thinking_budget": 0,
        "color": "#84cc16", "icon": "📝", "planner": False,
    },
    {
        "id": "logger",     "name": "Logger",     "role": "Chronicler",
        "model": "qwen3.5-plus",
        "temperature": 0.3, "top_p": 0.9, "top_k": 0, "thinking_budget": 0,
        "color": "#f59e0b", "icon": "🪵", "planner": False,
    },
    {
        "id": "reviewer",   "name": "Reviewer",   "role": "Code Review",
        "model": "deepseek-v4-pro",
        "temperature": 0.6, "top_p": 0.9, "top_k": 0, "thinking_budget": 0,
        "color": "#e879f9", "icon": "🔍", "planner": False,
    },
]

DEFAULT_PROVIDER = {
    "name": "OpenCode Go",
    "baseURL": DEFAULT_BASE_URL,
    "apiKey": "",
}


@dataclass
class ProviderConfig:
    name: str = "OpenCode Go"
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


def load_config() -> ProjectConfig:
    cwd = get_project_dir()
    project_name = cwd.name
    config_path = cwd / "agent-team.config.json"

    sprint = "Sprint #1"
    agents = [a.copy() for a in DEFAULT_AGENTS]
    provider = ProviderConfig()

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


def save_config(data: dict) -> None:
    config_path = Path(os.getcwd()) / "agent-team.config.json"
    config_path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
