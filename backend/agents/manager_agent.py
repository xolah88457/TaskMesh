from .base_agent import BaseAgent


_REVIEWER_ROLES = {"reviewer", "code reviewer", "code review"}

def build_manager_system(agents: list) -> str:
    non_mgr   = [a for a in agents if a.get("id") != "manager"]
    # Exclude reviewer from task list — it runs as Phase 4, not an executor
    non_mgr   = [
        a for a in non_mgr
        if a.get("id") != "reviewer" and a.get("role", "").lower() not in _REVIEWER_ROLES
    ]
    planners  = [a for a in non_mgr if a.get("planner", False)]
    executors = [a for a in non_mgr if not a.get("planner", False)]

    # Only assign tasks to executors — planners already ran in Phase 1
    tag_lines = "\n".join(
        f'    {{"id": "t{i+2}", "title": "<task>", "tag": "{a["id"].upper()[:3]}"}}'
        for i, a in enumerate(executors)
    )
    all_tags = "MGR, " + ", ".join(a["id"].upper()[:3] for a in executors)

    planner_note = ""
    if planners:
        names = ", ".join(a["id"] for a in planners)
        planner_note = (
            f"\nIMPORTANT: {names} are planning agents that already ran in Phase 1 and submitted "
            f"their specs above. Do NOT assign tasks to them. Only assign tasks to: {all_tags}.\n"
        )

    return f"""You are the Manager agent in a multi-agent software team.{planner_note}
Your ONLY job is to:
1. Read the project brief and any planner specs provided above.
2. Choose a concise feature/operation name (3-5 words, e.g. "User Auth Overhaul").
3. Write a 1-2 sentence analysis that incorporates the planner inputs.
4. Decompose into {len(executors) + 1} concrete subtasks mapped to these roles: {all_tags}.
5. Return ONLY valid JSON — no markdown, no prose, no code fences:

{{
  "feature": "<3-5 word operation name>",
  "analysis": "<1-2 sentence overview>",
  "tasks": [
    {{"id": "t1", "title": "<manager task>", "tag": "MGR"}},
{tag_lines}
  ]
}}

Do NOT write code. Do NOT deviate from this JSON structure."""


class ManagerAgent(BaseAgent):
    def __init__(self, agents: list, base_url: str = "https://opencode.ai/zen/v1", api_key: str = ""):
        mgr = next((a for a in agents if a.get("id") == "manager"), {})
        super().__init__(
            name="manager",
            model=mgr.get("model", "deepseek-v4-pro"),
            system_prompt=build_manager_system(agents),
            base_url=base_url,
            api_key=api_key,
            temperature=float(mgr.get("temperature", 0.7)),
            top_p=float(mgr.get("top_p", 0.9)),
            max_tokens=int(mgr.get("max_tokens", 8192)),
        )
