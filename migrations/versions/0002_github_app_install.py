"""github app installation table

Revision ID: 0002_github_app_install
Revises: 0001_baseline
Create Date: 2026-05-24

Adds `user_github_install` — one row per user that installed the TaskMesh
GitHub App. We store only public identifiers; installation tokens are minted
on demand from the App's private key. The legacy `user_github` table (long-
lived OAuth bearer token) is preserved during the transition.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_github_app_install"
down_revision: Union[str, Sequence[str], None] = "0001_baseline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_github_install",
        sa.Column("user_id",         sa.String(length=128), primary_key=True),
        sa.Column("installation_id", sa.String(length=64),  nullable=False),
        sa.Column("github_login",    sa.String(length=128), nullable=True),
        sa.Column("default_repo",    sa.String(length=256), nullable=True),
        sa.Column("default_branch",  sa.String(length=128), nullable=False, server_default="main"),
        sa.Column("scopes",          sa.Text(),             nullable=True),
        sa.Column("installed_at",    sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at",      sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "ix_user_github_install_installation",
        "user_github_install",
        ["installation_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_user_github_install_installation", table_name="user_github_install")
    op.drop_table("user_github_install")
