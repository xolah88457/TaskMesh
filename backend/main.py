import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv

# Load .env BEFORE importing any module that reads env vars at import time
# (auth.auth, billing, github, etc. all read os.environ at module load).
load_dotenv()

import socketio  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

from .core.config_loader import load_config  # noqa: E402
from .core.orchestrator import Orchestrator  # noqa: E402
from .api.routes import router, set_orchestrator  # noqa: E402
from .api.billing import router as billing_router  # noqa: E402
from .api.github import router as github_router  # noqa: E402
from .api.auth import router as auth_router  # noqa: E402
from .api.account import router as account_router  # noqa: E402
from .db.session import create_tables  # noqa: E402

# Allowed origins for CORS / Socket.IO. Comma-separated env var, or "*" for dev.
# In production set CORS_ALLOWED_ORIGINS to the actual frontend URL(s) — using "*"
# with cookie/credential-bearing requests is unsafe.
_cors_env = os.environ.get("CORS_ALLOWED_ORIGINS", "*").strip()
_CORS_ORIGINS: list[str] | str = (
    "*" if _cors_env == "*" else [o.strip() for o in _cors_env.split(",") if o.strip()]
)

sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins=_CORS_ORIGINS)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_tables()
    yield


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

orchestrator = Orchestrator(sio, load_config())
set_orchestrator(orchestrator)

socket_app = socketio.ASGIApp(sio, other_asgi_app=app)


@sio.event
async def connect(sid, environ):
    print(f"Client connected: {sid}")
    await sio.emit("init", {
        "project": orchestrator.config.project,
        "sprint":  orchestrator.config.sprint,
        "agents":  orchestrator.config.agents,
    }, to=sid)


@sio.event
async def disconnect(sid):
    print(f"Client disconnected: {sid}")
