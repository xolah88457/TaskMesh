import os
from contextlib import asynccontextmanager
from dotenv import load_dotenv
load_dotenv()

import socketio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .core.config_loader import load_config
from .core.orchestrator import Orchestrator
from .api.routes import router, set_orchestrator
from .api.billing import router as billing_router
from .api.github import router as github_router
from .api.auth import router as auth_router
from .api.account import router as account_router
from .db.session import create_tables

sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins="*")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_tables()
    yield


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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
