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
    Column, String, Integer, Boolean, Text, DateTime, ForeignKey, Index
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
    config_json      = Column(Text, nullable=True)                      # per-user agent config (Pro users)
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


class Notification(Base):
    """Per-user notification preferences. Stub — no email integration yet."""
    __tablename__ = "notifications"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    user_id    = Column(String(128), nullable=False)
    type       = Column(String(32),  nullable=False)
    # notification types: subscription_started, credit_low
    channel    = Column(String(16),  nullable=False, default="email")
    enabled    = Column(Boolean,     nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)

    __table_args__ = (
        Index("ix_notif_user_type", "user_id", "type", unique=True),
    )


class ZenUsage(Base):
    """Per-agent-call token usage log for analytics and spend tracking.

    One row per agent.run() call. Cost is calculated at TaskMesh's
    MODEL_PRICING rates (not Zen's underlying provider cost).
    """
    __tablename__ = "zen_usage"

    id                = Column(Integer, primary_key=True, autoincrement=True)
    user_id           = Column(String(128), nullable=False, index=True)
    run_id            = Column(String(36),  nullable=False)
    model             = Column(String(64),  nullable=False)
    prompt_tokens     = Column(Integer,     nullable=False, default=0)
    completion_tokens = Column(Integer,     nullable=False, default=0)
    cost_cents        = Column(Integer,     nullable=False, default=0)
    year_month        = Column(String(7),   nullable=False, default="")
    created_at        = Column(DateTime(timezone=True), nullable=False, default=_now)


class Task(Base):
    """DB-backed task queue for atomic multi-agent coordination.

    Replaces the in-memory SharedTaskList when DATABASE_URL is set.
    Falls back to in-memory when the database is unavailable.
    """
    __tablename__ = "tasks"

    id              = Column(Integer,     primary_key=True, autoincrement=True)
    run_id          = Column(String(36),  nullable=False, index=True)
    title           = Column(String(256), nullable=False)
    description     = Column(Text,        nullable=False, default="")
    status          = Column(String(20),  nullable=False, default="available")
    # status flow: pending → available → claimed → in_progress → completed | blocked | failed
    assigned_to     = Column(String(64),  nullable=True)
    created_by      = Column(String(64),  nullable=False, default="manager")
    output_files    = Column(Text,        nullable=True)  # JSON list of file paths
    created_at      = Column(DateTime(timezone=True), nullable=False, default=_now)
    started_at      = Column(DateTime(timezone=True), nullable=True)
    completed_at    = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_tasks_run_id", "run_id"),
        Index("ix_tasks_status", "status"),
    )


class CoordinatorEvent(Base):
    """Persistent audit log for coordinator decisions during a run.

    Replaces the in-memory CoordinatorLog when DATABASE_URL is set.
    Append-only — events are never updated after insert.
    """
    __tablename__ = "coordinator_events"

    id              = Column(Integer,     primary_key=True, autoincrement=True)
    run_id          = Column(String(36),  nullable=False, index=True)
    event_type      = Column(String(32),  nullable=False)
    # event types: task_created, task_claimed, task_completed, agent_online,
    #   agent_finished, file_locked, file_conflict, auto_commit, run_complete,
    #   phase_start, agent_assigned, feedback_sent, retry_started
    agent_id        = Column(String(64),  nullable=True)
    content         = Column(Text,        nullable=False, default="")
    metadata_json   = Column(Text,        nullable=True)  # JSON object
    created_at      = Column(DateTime(timezone=True), nullable=False, default=_now)

    __table_args__ = (
        Index("ix_ce_run_id", "run_id"),
        Index("ix_ce_type", "event_type"),
    )


class ActionFile(Base):
    """Append-only per-agent file operation log.

    One row per file written, overwritten, or conflicted during a run.
    Backs the Projects dashboard timeline (who touched what, when).

    Distinct from RunFile (which stores final content): ActionFile records
    *events* and is keyed by agent + task, while RunFile is keyed by path.
    """
    __tablename__ = "action_files"

    id           = Column(Integer,     primary_key=True, autoincrement=True)
    run_id       = Column(String(36),  nullable=False, index=True)
    agent_id     = Column(String(64),  nullable=False)
    task_id      = Column(Integer,     nullable=True)  # references tasks.id when available
    path         = Column(String(512), nullable=False)
    op           = Column(String(16),  nullable=False, default="written")
    # op values: written | overwritten | conflict | skipped
    size_bytes   = Column(Integer,     nullable=False, default=0)
    notes        = Column(Text,        nullable=True)
    created_at   = Column(DateTime(timezone=True), nullable=False, default=_now)

    __table_args__ = (
        Index("ix_action_files_run_id",   "run_id"),
        Index("ix_action_files_agent_id", "agent_id"),
    )


class TaskAcceptance(Base):
    """Per-task acceptance criteria, evaluated by the reviewer agent.

    One row per criterion. Append-only except for the met/checked_by/checked_at
    flip during Phase 4 reviewer pass.
    """
    __tablename__ = "task_acceptance"

    id         = Column(Integer,     primary_key=True, autoincrement=True)
    task_id    = Column(String(36),  nullable=False, index=True)  # FK → tasks.id (string handle)
    run_id     = Column(String(36),  nullable=False, index=True)
    criterion  = Column(Text,        nullable=False)
    met        = Column(Boolean,     nullable=False, default=False)
    met_order  = Column(Integer,     nullable=True)               # 1-based order within task
    checked_by = Column(String(64),  nullable=True)
    checked_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_task_acc_task_id", "task_id"),
        Index("ix_task_acc_run_id",  "run_id"),
    )


class ActionTool(Base):
    """Append-only per-agent LLM call log.

    One row per attempted API call — successful and failed retries alike.
    Lets ops see which agents are flaky, which models are returning empty
    content, and how often the retry path is being exercised.
    """
    __tablename__ = "action_tools"

    id                = Column(Integer,     primary_key=True, autoincrement=True)
    run_id            = Column(String(36),  nullable=False, index=True)
    agent_id          = Column(String(64),  nullable=False)
    task_id           = Column(Integer,     nullable=True)
    tool_name         = Column(String(64),  nullable=False, default="llm.call")
    # tool_name values: llm.call | docs.search | (future tool extensions)
    model             = Column(String(64),  nullable=True)
    prompt_tokens     = Column(Integer,     nullable=False, default=0)
    completion_tokens = Column(Integer,     nullable=False, default=0)
    status            = Column(String(16),  nullable=False, default="ok")
    # status values: ok | retried | failed
    attempts          = Column(Integer,     nullable=False, default=1)
    error             = Column(Text,        nullable=True)
    duration_ms       = Column(Integer,     nullable=False, default=0)
    created_at        = Column(DateTime(timezone=True), nullable=False, default=_now)

    __table_args__ = (
        Index("ix_action_tools_run_id",   "run_id"),
        Index("ix_action_tools_agent_id", "agent_id"),
        Index("ix_action_tools_status",   "status"),
    )
