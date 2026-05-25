"""
SQLAlchemy ORM models for the Agent Teams feature.

Kept in a separate module from `models.py` so the Teams subsystem can be
read and reviewed in isolation. Shares the `Base` declarative class so
`Base.metadata.create_all` picks up every table in a single sweep.

Tables:
  agent_teams      — top-level team, owned by a user
  team_members     — individual teammate (LLM session) inside a team
  team_tasks       — shared task list; supports dependencies
  team_messages    — inter-agent messages (mailbox)
"""
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey, Index, Integer, String, Text,
)
from sqlalchemy.orm import relationship

from .models import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Team(Base):
    """A user-owned team of cooperating agents."""
    __tablename__ = "agent_teams"

    id          = Column(String(36),  primary_key=True)   # UUID
    user_id     = Column(String(128), nullable=False)
    name        = Column(String(256), nullable=False)
    description = Column(Text,        nullable=True)
    status      = Column(String(20),  nullable=False, default="active")
    # status values: active | cleaning_up | archived
    created_at  = Column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at  = Column(DateTime(timezone=True), nullable=False, default=_now)

    members  = relationship(
        "TeamMember",
        back_populates="team",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    tasks    = relationship(
        "TeamTask",
        back_populates="team",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    messages = relationship(
        "TeamMessage",
        back_populates="team",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        Index("ix_agent_teams_user_id", "user_id"),
        Index("ix_agent_teams_status",  "status"),
    )


class TeamMember(Base):
    """A single teammate. Identified by `name` within a team."""
    __tablename__ = "team_members"

    id            = Column(String(36),  primary_key=True)   # UUID
    team_id       = Column(
        String(36),
        ForeignKey("agent_teams.id", ondelete="CASCADE"),
        nullable=False,
    )
    name          = Column(String(64),  nullable=False)
    # Role / agent type — e.g. "researcher", "implementer", "reviewer".
    agent_type    = Column(String(64),  nullable=False, default="generic")
    model         = Column(String(64),  nullable=True)
    spawn_prompt  = Column(Text,        nullable=True)
    status        = Column(String(20),  nullable=False, default="idle")
    # status values: idle | busy | offline | shutdown
    is_lead       = Column(Boolean,     nullable=False, default=False)
    created_at    = Column(DateTime(timezone=True), nullable=False, default=_now)
    last_active_at = Column(DateTime(timezone=True), nullable=True)

    team = relationship("Team", back_populates="members")

    __table_args__ = (
        # Names must be unique inside a team so that messages can target by name.
        Index("ix_team_members_team_name", "team_id", "name", unique=True),
        Index("ix_team_members_status",     "status"),
    )


class TeamTask(Base):
    """A unit of work claimable by any teammate.

    `depends_on` is a JSON-encoded list of task IDs (as strings). A task is
    only claimable once every dependency has status='done'.
    """
    __tablename__ = "team_tasks"

    id           = Column(String(36),  primary_key=True)
    team_id      = Column(
        String(36),
        ForeignKey("agent_teams.id", ondelete="CASCADE"),
        nullable=False,
    )
    title        = Column(String(256), nullable=False)
    description  = Column(Text,        nullable=True)
    status       = Column(String(20),  nullable=False, default="pending")
    # status values: pending | in_progress | done | blocked | failed
    assigned_to  = Column(String(36),  nullable=True)   # TeamMember.id
    depends_on   = Column(Text,        nullable=True)   # JSON list of task ids
    result       = Column(Text,        nullable=True)
    created_by   = Column(String(36),  nullable=True)   # TeamMember.id or 'user'
    created_at   = Column(DateTime(timezone=True), nullable=False, default=_now)
    started_at   = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    team = relationship("Team", back_populates="tasks")

    __table_args__ = (
        Index("ix_team_tasks_team_id",  "team_id"),
        Index("ix_team_tasks_status",   "status"),
        Index("ix_team_tasks_assignee", "assigned_to"),
    )


class TeamMessage(Base):
    """Append-only inter-agent message.

    Either `to_member` is the name of one specific teammate, or it equals
    'all' for a broadcast. `from_member` is either the sender's TeamMember
    name, or one of the reserved sentinels 'user' / 'lead'.
    """
    __tablename__ = "team_messages"

    id          = Column(Integer,     primary_key=True, autoincrement=True)
    team_id     = Column(
        String(36),
        ForeignKey("agent_teams.id", ondelete="CASCADE"),
        nullable=False,
    )
    from_member = Column(String(64),  nullable=False)
    to_member   = Column(String(64),  nullable=False, default="all")
    content     = Column(Text,        nullable=False)
    created_at  = Column(DateTime(timezone=True), nullable=False, default=_now)

    team = relationship("Team", back_populates="messages")

    __table_args__ = (
        Index("ix_team_messages_team_id",    "team_id"),
        Index("ix_team_messages_created_at", "created_at"),
    )
