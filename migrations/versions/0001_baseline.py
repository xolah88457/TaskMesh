"""baseline — current model state, idempotent

Revision ID: 0001_baseline
Revises:
Create Date: 2026-05-24

Idempotent baseline. On a fresh database this creates the full schema by
running ``Base.metadata.create_all``. On an existing database that was
previously bootstrapped via ``_run_migrations`` (see backend/db/session.py)
this is effectively a no-op because every CREATE / ALTER is checked with
``IF NOT EXISTS`` semantics.

After this migration ships, future schema changes go through ordinary
Alembic revision files. ``_run_migrations`` will be retired in a follow-up
once every environment is stamped to this revision.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0001_baseline"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create all tables defined in the current model metadata.

    Uses checkfirst=True so the migration is safe to run on any
    database — fresh or one already provisioned by _run_migrations.
    """
    from backend.db.models import Base
    from backend.db import models_teams  # noqa: F401 — register Team tables on Base.metadata

    bind = op.get_bind()
    Base.metadata.create_all(bind, checkfirst=True)


def downgrade() -> None:
    """Drop the entire schema.

    Reversing the baseline is a destructive operation — only use this on a
    throwaway database. Production downgrades use targeted revisions.
    """
    from backend.db.models import Base
    from backend.db import models_teams  # noqa: F401

    bind = op.get_bind()
    Base.metadata.drop_all(bind, checkfirst=True)
