"""
Paddle billing integration — Starter + Pro subscriptions and pay-as-you-go packs.

Plans
-----
  starter  — $30/mo  → $15 credits (1500 cents, 50% allocation) each billing cycle
  pro      — $80/mo  → $48 credits (4800 cents, 60% allocation) each billing cycle
  none     — no active subscription (cannot start runs)

Pay-as-you-go packs (one-time, no expiry)
-----------------------------------------
  pack_s   — $20 one-time  → $10.00 credits (1000 cents, 50% allocation)
  pack_m   — $50 one-time  → $27.50 credits (2750 cents, 55% allocation)
  pack_l   — $100 one-time → $60.00 credits (6000 cents, 60% allocation)

Credit depletion
----------------
Credits deplete based on actual LLM token usage after each agent call.
calc_cost_cents() converts token counts to integer cents using the pricing table.
The orchestrator calls this after every agent.run() and writes a non-blocking
DB update via asyncio.create_task().

Model tier gating (Option B)
-----------------------------
PRO_ONLY_MODELS contains models costing >$0.010/1K prompt tokens.
The orchestrator swaps these to STARTER_MODEL_FALLBACK for Starter users,
so agents still run but on cheaper/faster models.

Environment variables required
-------------------------------
  PADDLE_API_KEY         — Paddle secret key (live_ or sandbox_)
  PADDLE_WEBHOOK_SECRET  — used to verify incoming Paddle webhook signatures
  PADDLE_PRICE_STARTER   — Paddle price ID for the Starter subscription
  PADDLE_PRICE_PRO       — Paddle price ID for the Pro subscription
  PADDLE_PRICE_PACK_S    — Paddle price ID for Credit Pack S ($20)
  PADDLE_PRICE_PACK_M    — Paddle price ID for Credit Pack M ($50)
  PADDLE_PRICE_PACK_L    — Paddle price ID for Credit Pack L ($100)
"""
import hashlib
import hmac
import json
import os
import time
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, HTTPException, Request, Depends
from pydantic import BaseModel

from ..auth.auth import require_auth

router = APIRouter(prefix="/billing")

# ── Paddle config ──────────────────────────────────────────────────────────────
PADDLE_API_KEY        = os.environ.get("PADDLE_API_KEY", "")
PADDLE_WEBHOOK_SECRET = os.environ.get("PADDLE_WEBHOOK_SECRET", "")

PADDLE_PRICE_STARTER = os.environ.get("PADDLE_PRICE_STARTER", "")
PADDLE_PRICE_PRO     = os.environ.get("PADDLE_PRICE_PRO", "")
PADDLE_PRICE_PACK_S  = os.environ.get("PADDLE_PRICE_PACK_S", "")
PADDLE_PRICE_PACK_M  = os.environ.get("PADDLE_PRICE_PACK_M", "")
PADDLE_PRICE_PACK_L  = os.environ.get("PADDLE_PRICE_PACK_L", "")

_PADDLE_BASE = "https://api.paddle.com"

# ── Credit constants (cents) ───────────────────────────────────────────────────
STARTER_CREDITS_CENTS = 1500   # $15.00 per billing cycle (50% of $30)
PRO_CREDITS_CENTS     = 4800   # $48.00 per billing cycle (60% of $80)

PACK_CREDITS: dict[str, int] = {}  # populated after env vars are loaded

def _build_pack_credits() -> dict[str, int]:
    """Map Paddle price ID → credits in cents for one-time packs."""
    m: dict[str, int] = {}
    if PADDLE_PRICE_PACK_S:
        m[PADDLE_PRICE_PACK_S] = 1000   # $10.00 (50%  of $20)
    if PADDLE_PRICE_PACK_M:
        m[PADDLE_PRICE_PACK_M] = 2750   # $27.50 (55%  of $50)
    if PADDLE_PRICE_PACK_L:
        m[PADDLE_PRICE_PACK_L] = 6000   # $60.00 (60%  of $100)
    return m

# ── Model pricing table — cents per 1 000 tokens (prompt, completion) ─────────
# User-provided $/M rates are converted: cents/1K = ($/M * 100) / 1000
MODEL_PRICING: dict[str, tuple[float, float]] = {
    # ── Existing Flagship (unchanged) ──────────────────────────────────────
    "deepseek-v4-pro":   (0.014, 0.028),
    "glm-5.1":           (0.010, 0.020),
    "kimi-k2.6":         (0.014, 0.028),
    "mimo-v2.5-pro":     (0.012, 0.024),
    "minimax-m2.7":      (0.014, 0.028),
    "qwen3.6-plus":      (0.006, 0.012),
    # ── Existing Balanced (partially updated) ──────────────────────────────
    "deepseek-v4-flash": (0.174, 0.348),   # updated: $1.74/M in, $3.48/M out
    "glm-5":             (0.008, 0.016),
    "kimi-k2.5":         (0.010, 0.020),
    "mimo-v2.5":         (0.008, 0.016),
    "minimax-m2.5":      (0.030, 0.240),   # updated: $0.30/M in, $2.40/M out
    "qwen3.5-plus":      (0.004, 0.008),
    # ── Existing Fast (updated) ────────────────────────────────────────────
    "nemotron-3-super":  (0.010, 0.050),   # updated: $0.10/M in, $0.50/M out
    # ── Budget / Economy variants ──────────────────────────────────────────
    "deepseek-v4-flash-free": (0.174, 0.348),
    "big-pickle":             (0.010, 0.050),
    "nemotron-3-super-free":  (0.010, 0.050),
    "minimax-m2.5-free":      (0.030, 0.240),
    # ── Claude (Anthropic) — OpenCode Zen pricing ──────────────────────────
    "claude-haiku-4-5":  (0.100, 0.500),   # ~$1/M in, $5/M out
    "claude-opus-4-1":   (1.500, 7.500),   # ~$15/M in, $75/M out
    "claude-opus-4-5":   (0.500, 2.500),   # ~$5/M in, $25/M out
    "claude-opus-4-6":   (0.500, 2.500),
    "claude-opus-4-7":   (0.500, 2.500),
    "claude-sonnet-4":   (0.300, 1.500),   # ~$3/M in, $15/M out
    "claude-sonnet-4-5": (0.300, 1.500),
    "claude-sonnet-4-6": (0.300, 1.500),
    # ── GPT (OpenAI) — OpenCode Zen pricing estimates ──────────────────────
    "gpt-5":             (0.250, 1.000),   # ~$2.50/M in, $10/M out
    "gpt-5-codex":       (0.300, 1.200),
    "gpt-5-nano":        (0.025, 0.100),   # ~$0.25/M in, $1/M out
    "gpt-5.1":           (0.250, 1.000),
    "gpt-5.1-codex":     (0.300, 1.200),
    "gpt-5.1-codex-max": (0.300, 1.200),
    "gpt-5.1-codex-mini":(0.100, 0.400),
    "gpt-5.2":           (0.250, 1.000),
    "gpt-5.2-codex":     (0.300, 1.200),
    "gpt-5.3-codex":     (0.300, 1.200),
    "gpt-5.3-codex-spark":(0.100, 0.400),
    "gpt-5.4":           (0.250, 1.000),
    "gpt-5.4-mini":      (0.050, 0.200),
    "gpt-5.4-nano":      (0.025, 0.100),
    "gpt-5.4-pro":       (0.500, 2.000),   # ~$5/M in, $20/M out
    "gpt-5.5":           (0.250, 1.000),
    "gpt-5.5-pro":       (0.500, 2.000),
    # ── Gemini (Google) — OpenCode Zen pricing estimates ───────────────────
    "gemini-3-flash":    (0.015, 0.060),   # ~$0.15/M in, $0.60/M out
    "gemini-3.1-pro":    (0.350, 1.400),   # ~$3.50/M in, $14/M out
    "gemini-3.5-flash":  (0.015, 0.060),
    # ── Other ──────────────────────────────────────────────────────────────
    "grok-build-0-1":    (0.0005, 0.0010), # unconfirmed estimate
}
DEFAULT_PRICING: tuple[float, float] = (0.020, 0.020)  # fallback for unknown models

# ── Pro-only model IDs ─────────────────────────────────────────────────────────
# Any agent using these models will be downgraded to STARTER_MODEL_FALLBACK
# when the user's plan is "starter".
# Threshold: prompt cost > 0.2 cents/1K tokens (~$2/M input).
PRO_ONLY_MODELS: frozenset[str] = frozenset({
    # Existing Flagship (6)
    "deepseek-v4-pro",
    "glm-5.1",
    "kimi-k2.6",
    "mimo-v2.5-pro",
    "minimax-m2.7",
    "qwen3.6-plus",
    # Claude Opus (4)
    "claude-opus-4-1",
    "claude-opus-4-5",
    "claude-opus-4-6",
    "claude-opus-4-7",
    # Claude Sonnet (3)
    "claude-sonnet-4",
    "claude-sonnet-4-5",
    "claude-sonnet-4-6",
    # GPT standard tier (3)
    "gpt-5",
    "gpt-5.1",
    "gpt-5.2",
    # GPT Codex (5)
    "gpt-5-codex",
    "gpt-5.1-codex",
    "gpt-5.1-codex-max",
    "gpt-5.2-codex",
    "gpt-5.3-codex",
    # GPT Pro / top-tier (4)
    "gpt-5.4-pro",
    "gpt-5.5-pro",
    "gpt-5.5",
    "gpt-5.4",
    # Gemini Pro (1)
    "gemini-3.1-pro",
})

STARTER_MODEL_FALLBACK = "deepseek-v4-flash"

# Map of plan name → subscription price ID
_PLAN_PRICE_MAP = {
    "starter": lambda: PADDLE_PRICE_STARTER,
    "pro":     lambda: PADDLE_PRICE_PRO,
}

# Map of pack name → (price_id_getter, credits_cents)
_PACK_MAP = {
    "pack_s": (lambda: PADDLE_PRICE_PACK_S, 1000),
    "pack_m": (lambda: PADDLE_PRICE_PACK_M, 2750),
    "pack_l": (lambda: PADDLE_PRICE_PACK_L, 6000),
}


def calc_cost_cents(model: str, prompt_tokens: int, completion_tokens: int) -> int:
    """Convert token counts to integer cents using the pricing table."""
    p, c = MODEL_PRICING.get(model, DEFAULT_PRICING)
    return max(1, int((prompt_tokens * p + completion_tokens * c) / 1000)) if (
        prompt_tokens + completion_tokens > 0
    ) else 0


# ── HTTP helpers ───────────────────────────────────────────────────────────────

async def _paddle_post(path: str, body: dict) -> dict:
    if not PADDLE_API_KEY:
        raise HTTPException(status_code=503, detail="Paddle not configured")
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{_PADDLE_BASE}{path}",
            json=body,
            headers={
                "Authorization": f"Bearer {PADDLE_API_KEY}",
                "Content-Type": "application/json",
            },
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()


# ── API routes ─────────────────────────────────────────────────────────────────

class CheckoutRequest(BaseModel):
    plan: str  # "starter" | "pro" | "pack_s" | "pack_m" | "pack_l"


@router.post("/checkout")
async def create_checkout(body: CheckoutRequest, user: dict = Depends(require_auth)):
    """Return a Paddle checkout URL for a plan or credit pack."""
    user_id = user.get("sub", "")

    if body.plan in _PLAN_PRICE_MAP:
        price_id = _PLAN_PRICE_MAP[body.plan]()
        if not price_id:
            raise HTTPException(status_code=503, detail=f"Price ID for '{body.plan}' not configured")
        data = await _paddle_post("/transactions", {
            "items": [{"price_id": price_id, "quantity": 1}],
            "customer": {"email": user.get("email", "")},
            "custom_data": {"user_id": user_id},
            "collection_mode": "automatic",
        })
    elif body.plan in _PACK_MAP:
        get_price_id, _ = _PACK_MAP[body.plan]
        price_id = get_price_id()
        if not price_id:
            raise HTTPException(status_code=503, detail=f"Price ID for '{body.plan}' not configured")
        data = await _paddle_post("/transactions", {
            "items": [{"price_id": price_id, "quantity": 1}],
            "customer": {"email": user.get("email", "")},
            "custom_data": {"user_id": user_id},
            "collection_mode": "automatic",
        })
    else:
        raise HTTPException(status_code=400, detail=f"Unknown plan: '{body.plan}'")

    checkout_url = data.get("data", {}).get("checkout", {}).get("url")
    if not checkout_url:
        raise HTTPException(status_code=500, detail="Failed to get checkout URL from Paddle")
    return {"checkout_url": checkout_url}


_AUTH_DISABLED = os.environ.get("AUTH_DISABLED", "").lower() in ("1", "true", "yes")


@router.get("/usage")
async def get_usage(user: dict = Depends(require_auth)):
    """Return the current user's plan, credit balance, and monthly run count."""
    from ..db.session import get_session
    from ..db.models import UserCredits, UserUsage

    user_id    = user.get("sub", "anonymous")
    year_month = datetime.now(timezone.utc).strftime("%Y-%m")

    # Dev bypass — return a generous fake "pro" balance in local dev mode
    if _AUTH_DISABLED or user_id == "dev-user":
        return {
            "plan": "pro", "balance_cents": 4800, "run_count": 0,
            "run_limit": None, "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    async with get_session() as session:
        if session is None:
            return {"plan": "none", "balance_cents": 0, "run_count": 0}

        credits = await session.get(UserCredits, user_id)
        usage   = await session.get(UserUsage, (user_id, year_month))

    plan          = credits.plan          if credits else "none"
    balance_cents = credits.balance_cents if credits else 0
    run_count     = usage.run_count       if usage   else 0
    updated_at    = credits.updated_at.isoformat() if credits and credits.updated_at else None

    return {
        "plan":          plan,
        "balance_cents": balance_cents,
        "run_count":     run_count,
        "run_limit":     None,   # no run cap for pro/starter (reserved for future)
        "updated_at":    updated_at,
    }


ADMIN_BYPASS_KEY = os.environ.get("ADMIN_BYPASS_KEY", "")


class AdminBypassRequest(BaseModel):
    key: str


@router.post("/admin-bypass")
async def admin_bypass(body: AdminBypassRequest, user: dict = Depends(require_auth)):
    """Grant the authenticated user a pro plan with generous credits using the admin key."""
    if not ADMIN_BYPASS_KEY:
        raise HTTPException(status_code=503, detail="Not configured")
    if not hmac.compare_digest(body.key.encode(), ADMIN_BYPASS_KEY.encode()):
        raise HTTPException(status_code=403, detail="Invalid key")

    user_id = user.get("sub", "")
    await _upsert_credits(user_id=user_id, plan="pro", add_cents=999999)
    return {"status": "ok", "plan": "pro"}


@router.get("/portal")
async def get_portal(user: dict = Depends(require_auth)):
    """Generate a Paddle customer portal URL for subscription management."""
    import logging
    _log = logging.getLogger(__name__)
    user_id = user.get("sub", "anonymous")
    if _AUTH_DISABLED or user_id == "dev-user":
        raise HTTPException(status_code=400, detail="Not available in dev mode")

    from ..db.session import get_session
    from ..db.models import UserCredits
    async with get_session() as session:
        if session is None:
            raise HTTPException(status_code=503, detail="Database not configured")
        credits = await session.get(UserCredits, user_id)
        if not credits or not credits.customer_id:
            _log.warning("Portal unavailable: user=%s plan=%s sub=%s cust=%s",
                         user_id, credits.plan if credits else "none",
                         credits.subscription_id if credits else "none",
                         credits.customer_id if credits else "none")
            raise HTTPException(status_code=400, detail="No active subscription")

        try:
            portal_data = await _paddle_post(f"/customers/{credits.customer_id}/portal-sessions", {
                "subscription_id": credits.subscription_id,
            })
            portal_url = portal_data.get("data", {}).get("urls", {}).get("general", {}).get("url")
            if portal_url:
                return {"portal_url": portal_url}
            _log.error("Paddle portal response missing URL: %s", portal_data)
        except Exception:
            _log.exception("Paddle portal request failed")

    raise HTTPException(status_code=503, detail="Could not generate portal URL")


@router.post("/webhook")
async def paddle_webhook(request: Request):
    """Receive Paddle payment events and update user plan / credits."""
    body = await request.body()
    sig  = request.headers.get("Paddle-Signature", "")

    # Verify signature
    if PADDLE_WEBHOOK_SECRET:
        ts_part, h1_part = "", ""
        for part in sig.split(";"):
            if part.startswith("ts="):
                ts_part = part[3:]
            elif part.startswith("h1="):
                h1_part = part[3:]
        signed   = f"{ts_part}:{body.decode()}"
        expected = hmac.new(
            PADDLE_WEBHOOK_SECRET.encode(), signed.encode(), hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(expected, h1_part):
            raise HTTPException(status_code=400, detail="Invalid webhook signature")
        if abs(time.time() - int(ts_part)) > 300:
            raise HTTPException(status_code=400, detail="Webhook timestamp too old")

    event      = json.loads(body)
    event_type = event.get("event_type", "")

    if event_type == "subscription.activated":
        await _handle_subscription_activated(event)
    elif event_type == "subscription.updated":
        await _handle_subscription_updated(event)
    elif event_type in ("subscription.cancelled", "subscription.paused"):
        await _handle_cancellation(event)
    elif event_type == "transaction.completed":
        await _handle_transaction_completed(event)

    return {"ok": True}


# ── Webhook helpers ────────────────────────────────────────────────────────────

async def _upsert_credits(
    user_id: str,
    plan: str | None = None,
    add_cents: int = 0,
    subscription_id: str | None = None,
    customer_id: str | None = None,
) -> None:
    """Create or update UserCredits for a user atomically."""
    from ..db.session import get_session
    from ..db.models import UserCredits

    async with get_session() as session:
        if session is None:
            return
        creds = await session.get(UserCredits, user_id)
        if creds is None:
            creds = UserCredits(
                user_id=user_id,
                plan=plan or "none",
                balance_cents=add_cents,
                subscription_id=subscription_id,
                customer_id=customer_id,
                updated_at=datetime.now(timezone.utc),
            )
            session.add(creds)
        else:
            if plan is not None:
                creds.plan = plan
            if add_cents:
                creds.balance_cents += add_cents
            if subscription_id is not None:
                creds.subscription_id = subscription_id
            if customer_id is not None:
                creds.customer_id = customer_id
            creds.updated_at = datetime.now(timezone.utc)


def _plan_from_price_id(price_id: str) -> str | None:
    if price_id == PADDLE_PRICE_STARTER:
        return "starter"
    if price_id == PADDLE_PRICE_PRO:
        return "pro"
    return None


def _credits_for_plan(plan: str) -> int:
    return STARTER_CREDITS_CENTS if plan == "starter" else PRO_CREDITS_CENTS


async def _handle_subscription_activated(event: dict) -> None:
    data     = event.get("data", {})
    custom   = data.get("custom_data", {})
    user_id  = custom.get("user_id", "")
    sub_id   = data.get("id", "")
    price_id = (data.get("items") or [{}])[0].get("price", {}).get("id", "")
    cust_id  = data.get("customer_id", "")

    if not user_id:
        return

    plan = _plan_from_price_id(price_id)
    if not plan:
        return

    await _upsert_credits(
        user_id=user_id,
        plan=plan,
        add_cents=_credits_for_plan(plan),
        subscription_id=sub_id,
        customer_id=cust_id,
    )


async def _handle_subscription_updated(event: dict) -> None:
    """Handles renewals and plan changes. Adds credits if subscription is active."""
    data     = event.get("data", {})
    custom   = data.get("custom_data", {})
    user_id  = custom.get("user_id", "")
    sub_id   = data.get("id", "")
    status   = data.get("status", "")
    price_id = (data.get("items") or [{}])[0].get("price", {}).get("id", "")
    cust_id  = data.get("customer_id", "")

    if not user_id or status != "active":
        return

    plan = _plan_from_price_id(price_id)
    if not plan:
        return

    await _upsert_credits(
        user_id=user_id,
        plan=plan,
        add_cents=_credits_for_plan(plan),
        subscription_id=sub_id,
        customer_id=cust_id,
    )


async def _handle_cancellation(event: dict) -> None:
    data    = event.get("data", {})
    custom  = data.get("custom_data", {})
    user_id = custom.get("user_id", "")

    if not user_id:
        return

    # Downgrade plan to none; keep remaining balance
    await _upsert_credits(user_id=user_id, plan="none")


async def _handle_transaction_completed(event: dict) -> None:
    """One-time credit pack purchase. Pack buyers get Pro-level access."""
    pack_map = _build_pack_credits()
    if not pack_map:
        return

    data    = event.get("data", {})
    custom  = data.get("custom_data", {})
    user_id = custom.get("user_id", "")
    items   = data.get("items", [])

    if not user_id:
        return

    for item in items:
        price_id = item.get("price", {}).get("id", "")
        credits  = pack_map.get(price_id, 0)
        if credits > 0:
            await _upsert_credits(user_id=user_id, plan="pro", add_cents=credits)
            break  # one pack per transaction
