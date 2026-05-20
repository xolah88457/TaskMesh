import os
from openai import AsyncOpenAI
from anthropic import AsyncAnthropic

# ── OpenRouter (inactive — switch when ready) ──────────────────────────────────
# To activate OpenRouter:
#   1. Set OPENROUTER_API_KEY in your .env
#   2. Uncomment the block below
#   3. Update DEFAULT_BASE_URL in config_loader.py to OPENROUTER_BASE_URL
#   4. Switch DEFAULT_AGENTS model IDs to OPENROUTER_MODEL_MAP values
#   5. Re-enable thinking budgets in THINKING_MODEL_IDS below (OpenRouter exposes them)
#
# OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
# OPENROUTER_EXTRA_HEADERS = {
#     "HTTP-Referer": os.environ.get("FRONTEND_URL", "http://localhost:5173"),
#     "X-Title": "TaskMesh",
# }
#
# OpenRouter model IDs for each agent role:
# OPENROUTER_MODEL_MAP = {
#     "manager":    "deepseek/deepseek-chat",           # DeepSeek V4 — coordinator
#     "webdev":     "moonshotai/kimi-k2",               # Kimi K2 — architect/planner
#     "researcher": "moonshotai/kimi-k2",               # Kimi K2 — tech lead
#     "backend":    "deepseek/deepseek-chat",           # DeepSeek V4 — API builder
#     "frontend":   "qwen/qwen-2.5-coder-32b-instruct", # Qwen Coder — UI/UX
#     "tester":     "qwen/qwen-2.5-coder-32b-instruct", # Qwen Coder — QA
#     "docs":       "mistralai/mistral-7b-instruct",    # Mistral 7B — writer
#     "logger":     "meta-llama/llama-3.1-8b-instruct", # Llama 8B — chronicler
#     "reviewer":   "deepseek/deepseek-chat",           # DeepSeek V4 — reviewer
# }
#
# def _get_openrouter_client(api_key: str) -> AsyncOpenAI:
#     return AsyncOpenAI(
#         api_key=api_key or os.environ.get("OPENROUTER_API_KEY", "no-key-set"),
#         base_url=OPENROUTER_BASE_URL,
#         default_headers=OPENROUTER_EXTRA_HEADERS,
#     )
# ── End OpenRouter ─────────────────────────────────────────────────────────────

# Thinking budgets disabled for OpenCode Go — the extra_body format is provider-specific
# and OpenCode Go does not document a supported parameter for it.
# Will re-enable with confirmed values when switching to OpenRouter.
THINKING_MODEL_IDS: set[str] = set()

# Models that use the Anthropic Messages API (/v1/messages) instead of
# the OpenAI Chat Completions API (/v1/chat/completions).
# The Anthropic SDK is used automatically for these model IDs.
ANTHROPIC_MODEL_IDS: set[str] = {
    "minimax-m2.7",
    "minimax-m2.5",
}


class BaseAgent:
    def __init__(
        self,
        name: str,
        model: str,
        system_prompt: str,
        base_url: str = "https://opencode.ai/zen/go/v1",
        api_key: str = "",
        temperature: float = 0.7,
        top_p: float = 0.9,
        top_k: int = 0,
        thinking_budget: int = 0,
        max_tokens: int = 8192,
    ):
        self.name = name
        self.model = model
        self.system_prompt = system_prompt
        self._base_url = base_url
        self._api_key = api_key
        self.temperature = temperature
        self.top_p = top_p
        self.top_k = top_k
        self.thinking_budget = thinking_budget
        self.max_tokens = max_tokens
        self._client: AsyncOpenAI | None = None
        self._anthropic_client: AsyncAnthropic | None = None

    def _get_client(self) -> AsyncOpenAI:
        if self._client is None:
            key = self._api_key or os.environ.get("OPENCODE_GO_API_KEY", "no-key-set")
            self._client = AsyncOpenAI(api_key=key, base_url=self._base_url)
        return self._client

    def _get_anthropic_client(self) -> AsyncAnthropic:
        if self._anthropic_client is None:
            key = self._api_key or os.environ.get("OPENCODE_GO_API_KEY", "no-key-set")
            # Anthropic SDK appends /v1/messages to base_url.
            # OpenCode Go OpenAI base is .../zen/go/v1 → strip /v1 for Anthropic.
            base = self._base_url[:-3] if self._base_url.endswith("/v1") else self._base_url
            self._anthropic_client = AsyncAnthropic(api_key=key, base_url=base)
        return self._anthropic_client

    async def _run_anthropic(self, user_message: str) -> dict:
        """Call an Anthropic-format model (e.g. MiniMax via OpenCode Go /v1/messages)."""
        response = await self._get_anthropic_client().messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=self.system_prompt,
            messages=[{"role": "user", "content": user_message}],
            temperature=self.temperature,
        )
        content = response.content[0].text if response.content else ""
        return {
            "content":           content,
            "prompt_tokens":     response.usage.input_tokens  if response.usage else 0,
            "completion_tokens": response.usage.output_tokens if response.usage else 0,
            "model":             self.model,
        }

    async def run(self, user_message: str) -> dict:
        """Call the LLM and return content + token usage.

        Dispatches to the Anthropic Messages API for models in ANTHROPIC_MODEL_IDS,
        and to the OpenAI Chat Completions API for all others.

        Returns:
            {
                "content": str,
                "prompt_tokens": int,
                "completion_tokens": int,
                "model": str,
            }
        """
        if self.model in ANTHROPIC_MODEL_IDS:
            return await self._run_anthropic(user_message)

        extra_body: dict = {}

        if self.top_k and self.top_k > 0:
            extra_body["top_k"] = self.top_k

        if self.model in THINKING_MODEL_IDS:
            if self.thinking_budget > 0:
                extra_body["thinking_budget"] = self.thinking_budget
                extra_body["chat_template_kwargs"] = {"enable_thinking": True}
            else:
                extra_body["chat_template_kwargs"] = {"enable_thinking": False}

        extra = {"extra_body": extra_body} if extra_body else {}

        response = await self._get_client().chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": self.system_prompt},
                {"role": "user",   "content": user_message},
            ],
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            top_p=self.top_p,
            **extra,
        )
        usage = response.usage
        return {
            "content":           response.choices[0].message.content or "",
            "prompt_tokens":     usage.prompt_tokens     if usage else 0,
            "completion_tokens": usage.completion_tokens if usage else 0,
            "model":             self.model,
        }
