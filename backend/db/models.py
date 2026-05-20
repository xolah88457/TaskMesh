"""
SQLAlchemy ORM models for Agent Team.

Tables:
  users      — registered users (email/password or Google OAuth)
  runs       — one row per pipeline execution
  run_files  — one row per [FILE: path] written during a run
  user_usage — monthly run counts per user ID (for billing gates)
  user_github — GitHub OAuth tokens per user
"""
from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Integer, Text, Boolean, DateTime, ForeignKey, Index
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    """Registered user — email/password or Google OAuth."""
    __tablename__ = "users"

    id               = Column(String(36),  primary_key=True)   # UUID
    email            = Column(String(256), unique=True, nullable=False)
    name             = Column(String(256), nullable=True)
    password_hash    = Column(Text, nullable=True)             # NULL for OAuth-only users
    google_id        = Column(String(128), unique=True, nullable=True)
    github_id        = Column(String(64),  unique=True, nullable=True)  # GitHub user ID for login
    opencode_api_key = Column(String(256), nullable=True)     # OpenCode Go key (user-scoped)
    created_at       = Column(DateTime(timezone=True), nullable=False, default=_now)

    __table_args__ = (
        Index("ix_users_email",     "email"),
        Index("ix_users_google_id", "google_id"),
        Index("ix_users_github_id", "github_id"),
    )


class Run(Base):
    __tablename__ = "runs"

    id          = Column(String(36), primary_key=True)   # UUID
    user_id     = Column(String(128), nullable=False)    # UUID from users table
    brief       = Column(Text, nullable=False)
    status      = Column(String(20), nullable=False, default="running")
    # status values: running | done | cancelled | error
    agents_used = Column(Text, nullable=True)            # JSON list of agent IDs selected
    started_at  = Column(DateTime(timezone=True), nullable=False, default=_now)
    finished_at = Column(DateTime(timezone=True), nullable=True)

    files = relationship("RunFile", back_populates="run", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_runs_user_id", "user_id"),
    )


class RunFile(Base):
    __tablename__ = "run_files"

    id       = Column(Integer, primary_key=True, autoincrement=True)
    run_id   = Column(String(36), ForeignKey("runs.id", ondelete="CASCADE"), nullable=False)
    path     = Column(String(512), nullable=False)   # relative path within PROJECT_DIR
    content  = Column(Text, nullable=False)
    size     = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)

    run = relationship("Run", back_populates="files")

    __table_args__ = (
        Index("ix_run_files_run_id", "run_id"),
    )


class UserUsage(Base):
    """Monthly run counter — used to gate free-tier users."""
    __tablename__ = "user_usage"

    user_id    = Column(String(128), primary_key=True)  # UUID from users table
    year_month = Column(String(7),   primary_key=True)  # "YYYY-MM"
    run_count  = Column(Integer, nullable=False, default=0)
    plan       = Column(String(20), nullable=False, default="free")
    # plan values: free | pro | team


class UserGitHub(Base):
    """GitHub OAuth token per user."""
    __tablename__ = "user_github"

    user_id      = Column(String(128), primary_key=True)  # UUID from users table
    github_login = Column(String(128), nullable=False)
    access_token = Column(String(256), nullable=False)    # TODO: encrypt before prod
    connected_at = Column(DateTime(timezone=True), nullable=False)


class UserCredits(Base):
    """Persistent credit balance + plan per user (not keyed by month).

    balance_cents carries over month-to-month and is depleted by actual
    token usage. It is topped up when a subscription renews or a one-time
    pack is purchased.
    """
    __tablename__ = "user_credits"

    user_id         = Column(String(128), primary_key=True)  # UUID from users table
    plan            = Column(String(20),  nullable=False, default="none")
    # plan values: none | starter | pro
    balance_cents   = Column(Integer,     nullable=False, default=0)
    subscription_id = Column(String(128), nullable=True)     # Paddle subscription ID
    updated_at      = Column(DateTime(timezone=True), nullable=False, default=_now)
