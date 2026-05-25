import logging
import os
import re
from contextlib import asynccontextmanager

from dotenv import load_dotenv

# Load .env BEFORE importing any module that reads env vars at import time
# (auth.auth, billing, github, etc. all read os.environ at module load).
load_dotenv()

import socketio  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

from .auth.auth import decode_token, AUTH_DISABLED  # noqa: E402
from .api.routes import router, get_default_config, get_orchestrators, _init_sio, start_upload_cleanup  # noqa: E402
from .api.routes import _cleanup_expired_tokens as _cleanup_upload_tokens  # noqa: E402
from .api.billing import router as billing_router  # noqa: E402
from .api.github import router as github_router  # noqa: E402
from .api.auth import router as auth_router  # noqa: E402
from .api.account import router as account_router  # noqa: E402
from .api.teams import router as teams_router, _bind_sio as _bind_teams_sio  # noqa: E402
from .db.session import create_tables  # noqa: E402

# Allowed origins for CORS / Socket.IO. Comma-separated env var, or "*" for dev.
# In production set CORS_ALLOWED_ORIGINS to the actual frontend URL(s) — using "*"
# with cookie/credential-bearing requests is unsafe.
_cors_env = os.environ.get("CORS_ALLOWED_ORIGINS", "*").strip()
_CORS_ORIGINS: list[str] | str = (
    "*" if _cors_env == "*" else [o.strip() for o in _cors_env.split(",") if o.strip()]
)

sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins=_CORS_ORIGINS)
_init_sio(sio)
_bind_teams_sio(sio)

# Warn if CORS is wide open outside dev mode — production risk.
if _cors_env == "*" and not AUTH_DISABLED:
    import warnings
    warnings.warn(
        "CORS_ALLOWED_ORIGINS is unset (defaulting to '*'). In production this "
        "allows any origin to call your API. Set CORS_ALLOWED_ORIGINS to your "
        "frontend URL(s).",
        RuntimeWarning,
        stacklevel=2,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        await create_tables()
    except Exception:
        logging.getLogger(__name__).exception(
            "create_tables failed — continuing with existing schema"
        )
    start_upload_cleanup()          # background task: clean expired uploads every 5 min
    yield
    await _cleanup_upload_tokens()  # final sweep before shutdown
    # Cancel any active orchestrators on shutdown
    for user_id, orch in list(get_orchestrators().items()):
        orch.cancel()


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS if isinstance(_CORS_ORIGINS, list) else ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router, prefix="/api")
app.include_router(billing_router, prefix="/api")
app.include_router(github_router, prefix="/api")
app.include_router(auth_router, prefix="/api")
app.include_router(account_router, prefix="/api")
app.include_router(teams_router, prefix="/api")

_default_config = get_default_config()
socket_app = socketio.ASGIApp(sio, other_asgi_app=app)


@sio.event
async def connect(sid, environ):
    print(f"Client connected: {sid}")

    # Authenticate from HttpOnly cookie (XSS-safe). No separate 'auth' event needed.
    if not AUTH_DISABLED:
        cookie_str = environ.get("HTTP_COOKIE", "")
        match = re.search(r'(?:^|;\s*)token=([^;]+)', cookie_str)
        if match:
            try:
                payload = decode_token(match.group(1))
                user_id = payload.get("sub", "")
                if user_id:
                    sio.enter_room(sid, f"user:{user_id}")
            except Exception:
                pass  # unauthenticated socket — still receives public init event

    await sio.emit("init", {
        "project": _default_config.project,
        "sprint":  _default_config.sprint,
        "agents":  _default_config.agents,
    }, to=sid)


@sio.event
async def disconnect(sid):
    print(f"Client disconnected: {sid}")


# ── Agent Teams: per-team room subscription ──────────────────────────────────
#
# The client emits 'team_subscribe' with a team_id after navigating to a team
# workspace. We verify the caller actually owns the team before joining the
# team:<id> room — otherwise any logged-in user could listen in on another
# user's team events.

async def _sid_user_id(sid) -> str | None:
    rooms = sio.rooms(sid)
    for r in rooms:
        if r.startswith("user:"):
            return r[len("user:"):]
    return None


@sio.event
async def team_subscribe(sid, data):
    team_id = (data or {}).get("team_id", "")
    if not team_id or not isinstance(team_id, str):
        return {"status": "error", "code": "invalid_team_id"}
    if AUTH_DISABLED:
        sio.enter_room(sid, f"team:{team_id}")
        return {"status": "ok"}
    user_id = await _sid_user_id(sid)
    if not user_id:
        return {"status": "error", "code": "not_authenticated"}
    # Verify ownership against the DB.
    from sqlalchemy import select
    from .db.session import get_session
    from .db.models_teams import Team
    async with get_session() as session:
        if session is None:
            return {"status": "error", "code": "db_unavailable"}
        row = (await session.execute(
            select(Team.id).where(Team.id == team_id, Team.user_id == user_id)
        )).scalar_one_or_none()
        if row is None:
            return {"status": "error", "code": "not_found"}
    sio.enter_room(sid, f"team:{team_id}")
    return {"status": "ok"}


@sio.event
async def team_unsubscribe(sid, data):
    team_id = (data or {}).get("team_id", "")
    if team_id and isinstance(team_id, str):
        sio.leave_room(sid, f"team:{team_id}")
    return {"status": "ok"}
