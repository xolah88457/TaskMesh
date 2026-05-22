import asyncio
import os
import random
import time
from openai import APIStatusError, APITimeoutError, APIConnectionError, AsyncOpenAI
from anthropic import AsyncAnthropic

# ── OpenRouter (inactive — switch when ready) ──────────────────────────────────
# To activate OpenRouter:
#   1. Set OPENROUTER_API_KEY in your .env
#   2. Uncomment the block below
#   3. Update DEFAULT_BASE_URL in config_loader.py to OPENROUTER_BASE_URL
#   4. Re-enable thinking budgets in THINKING_MODEL_IDS below (OpenRouter exposes them)
#
# OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
# OPENROUTER_EXTRA_HEADERS = {
#     "HTTP-Referer": os.environ.get("FRONTEND_URL", "http://localhost:5173"),
#     "X-Title": "TaskMesh",
# }
#
# def _get_openrouter_client(api_key: str) -> AsyncOpenAI:
#     return AsyncOpenAI(
#         api_key=api_key or os.environ.get("OPENROUTER_API_KEY", "no-key-set"),
#         base_url=OPENROUTER_BASE_URL,
#         default_headers=OPENROUTER_EXTRA_HEADERS,
#     )
# ── End OpenRouter ─────────────────────────────────────────────────────────────

# Models supporting thinking via chat_template_kwargs (OpenAI Chat Completions).
# Per OpenCode Zen: Kimi, Qwen, MiniMax/MiMo, GLM, and DeepSeek accept
# chat_template_kwargs: {"enable_thinking": bool} with optional thinking_budget.
THINKING_MODEL_IDS: set[str] = {
    # Kimi — chat_template_kwargs + thinking_budget
    "kimi-k2.5", "kimi-k2.6",
    # Qwen — chat_template_kwargs only
    "qwen3.5-plus", "qwen3.6-plus",
    # MiniMax / MiMo — chat_template_kwargs only
    "minimax-m2.7", "minimax-m2.5", "minimax-m2.5-free",
    "mimo-v2.5-pro", "mimo-v2.5",
    # GLM — chat_template_kwargs only
    "glm-5", "glm-5.1",
    # DeepSeek — chat_template_kwargs + thinking_budget
    "deepseek-v4-pro", "deepseek-v4-flash", "deepseek-v4-flash-free",
}

# Claude models support thinking via Anthropic Messages API (top-level parameter).
ANTHROPIC_THINKING_MODEL_IDS: set[str] = {
    "claude-haiku-4-5",
    "claude-opus-4-1", "claude-opus-4-5", "claude-opus-4-6", "claude-opus-4-7",
    "claude-sonnet-4", "claude-sonnet-4-5", "claude-sonnet-4-6",
}

# Models that use the Anthropic Messages API (/v1/messages).
ANTHROPIC_MODEL_IDS: set[str] = {
    "minimax-m2.7",
    "minimax-m2.5",
    "minimax-m2.5-free",
    "claude-haiku-4-5",
    "claude-opus-4-1",
    "claude-opus-4-5",
    "claude-opus-4-6",
    "claude-opus-4-7",
    "claude-sonnet-4",
    "claude-sonnet-4-5",
    "claude-sonnet-4-6",
}

# Models that use the OpenAI Responses API.
# NOTE: responses.create() requires openai >= 1.59.0 — currently on 1.57.0.
# For now, GPT models fall through to the Chat Completions path.
# Uncomment the dispatch in run() after upgrading the openai SDK.
GPT_MODEL_IDS: set[str] = {
    "gpt-5",
    "gpt-5-codex",
    "gpt-5-nano",
    "gpt-5.1",
    "gpt-5.1-codex",
    "gpt-5.1-codex-max",
    "gpt-5.1-codex-mini",
    "gpt-5.2",
    "gpt-5.2-codex",
    "gpt-5.3-codex",
    "gpt-5.3-codex-spark",
    "gpt-5.4",
    "gpt-5.4-mini",
    "gpt-5.4-nano",
    "gpt-5.4-pro",
    "gpt-5.5",
    "gpt-5.5-pro",
}


class BaseAgent:
    def __init__(
        self,
        name: str,
        model: str,
        system_prompt: str,
        base_url: str = "https://opencode.ai/zen/v1",
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
            key = self._api_key or os.environ.get("OPENROUTER_API_KEY") or os.environ.get("OPENCODE_GO_API_KEY", "no-key-set")
            self._client = AsyncOpenAI(api_key=key, base_url=self._base_url)
        return self._client

    def _get_anthropic_client(self) -> AsyncAnthropic:
        if self._anthropic_client is None:
            key = self._api_key or os.environ.get("OPENROUTER_API_KEY") or os.environ.get("OPENCODE_GO_API_KEY", "no-key-set")
            # Anthropic SDK appends /v1/messages to base_url.
            # Strip /v1 suffix so Anthropic's own /v1/messages is used.
            base = self._base_url[:-3] if self._base_url.endswith("/v1") else self._base_url
            self._anthropic_client = AsyncAnthropic(api_key=key, base_url=base)
        return self._anthropic_client

    async def _run_with_retry(self, call_fn, max_retries: int = 3) -> dict:
        """Execute an API call with exponential backoff on transient failures.

        Retries on: APIStatusError (includes 429), APITimeoutError,
        APIConnectionError. Non-transient errors (e.g. authentication) fail
        immediately. Returns an empty content dict on total failure — never raises.

        The returned dict always carries telemetry the orchestrator logs to
        ActionTool:
          - "_attempts":   number of attempts actually made (1 = first call succeeded)
          - "_status":     "ok" | "retried" | "failed"
          - "_error":      last error message if status != "ok", else ""
          - "_duration_ms": wall-clock duration of the whole call (including backoff)
        """
        started = time.monotonic()
        last_error = ""
        for attempt in range(max_retries):
            try:
                result = await call_fn()
                result["_attempts"]    = attempt + 1
                result["_status"]      = "ok" if attempt == 0 else "retried"
                result["_error"]       = ""
                result["_duration_ms"] = int((time.monotonic() - started) * 1000)
                return result
            except (APIStatusError, APITimeoutError, APIConnectionError) as e:
                last_error = f"{type(e).__name__}: {e}"
                if attempt == max_retries - 1:
                    break
                delay = (2 ** attempt) + random.uniform(0, 0.5)
                await asyncio.sleep(delay)
            except Exception as e:  # noqa: BLE001 — auth/etc. shouldn't retry
                last_error = f"{type(e).__name__}: {e}"
                break
        return {
            "content":           "",
            "prompt_tokens":     0,
            "completion_tokens": 0,
            "model":             self.model,
            "_attempts":         attempt + 1,
            "_status":           "failed",
            "_error":            last_error,
            "_duration_ms":      int((time.monotonic() - started) * 1000),
        }

    async def _run_anthropic(self, user_message: str) -> dict:
        """Call an Anthropic-format model with retry on transient failures."""
        return await self._run_with_retry(lambda: self._do_anthropic_call(user_message))

    async def _do_anthropic_call(self, user_message: str) -> dict:
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

    async def _run_responses(self, user_message: str) -> dict:
        """Call a GPT model via the OpenAI Responses API.
        
        NOTE: responses.create() requires openai >= 1.59.0 — currently on 1.57.0.
        GPT models fall through to Chat Completions until SDK is upgraded.
        """
        # TODO: after `pip install openai --upgrade`:
        # response = await self._get_client().responses.create(
        #     model=self.model,
        #     input=user_message,
        #     instructions=self.system_prompt,
        #     temperature=self.temperature,
        #     max_output_tokens=self.max_tokens,
        # )
        # usage = response.usage
        # return {
        #     "content":           response.output_text,
        #     "prompt_tokens":     usage.input_tokens  if usage else 0,
        #     "completion_tokens": usage.output_tokens if usage else 0,
        #     "model":             self.model,
        # }
        raise NotImplementedError("Responses API requires openai >= 1.59.0")

    async def run(self, user_message: str) -> dict:
        """Call the LLM and return content + token usage.

        Dispatches based on model ID:
          - ANTHROPIC_MODEL_IDS → Anthropic Messages API
          - GPT_MODEL_IDS       → Chat Completions (Responses API after SDK upgrade)
          - Everything else      → Chat Completions

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

        # GPT_MODEL_IDS dispatch — would call _run_responses() after SDK upgrade.
        # Currently falls through to chat completions (same path).

        extra_body: dict = {}

        if self.top_k and self.top_k > 0:
            extra_body["top_k"] = self.top_k

        if self.model in THINKING_MODEL_IDS:
            if self.thinking_budget > 0:
                extra_body["thinking_budget"] = self.thinking_budget
                extra_body["chat_template_kwargs"] = {"enable_thinking": True}
            else:
                extra_body["chat_template_kwargs"] = {"enable_thinking": False}

        async def _do_chat_completion():
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

        return await self._run_with_retry(_do_chat_completion)
