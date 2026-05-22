"""
Account management API.

Endpoints:
  GET  /api/account/profile          — return profile info + linked providers
  PUT  /api/account/profile          — update display name
  PUT  /api/account/email            — change email address
  PUT  /api/account/password         — change password (requires current password)
  DELETE /api/account                — permanently delete account + all data
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..auth.auth import require_auth, hash_password, verify_password, create_token, set_token_cookie

router = APIRouter(prefix="/account")


# ── Request bodies ─────────────────────────────────────────────────────────────

class UpdateProfileRequest(BaseModel):
    name: str


class UpdateEmailRequest(BaseModel):
    email: str
    password: str        # required to confirm identity


class UpdatePasswordRequest(BaseModel):
    current_password: str
    new_password: str


# ── Routes ─────────────────────────────────────────────────────────────────────

@router.get("/profile")
async def get_profile(user: dict = Depends(require_auth)):
    """Return the current user's profile info and linked OAuth providers."""
    from ..db.session import get_session
    from ..db.models import User, UserGitHub

    user_id = user.get("sub", "")

    async with get_session() as session:
        if session is None:
            # No DB — return JWT data only
            return {
                "id":             user_id,
                "name":           user.get("name", ""),
                "email":          user.get("email", ""),
                "has_password":   False,
                "google_linked":  False,
                "github_linked":  False,
                "created_at":     None,
            }

        user_row = await session.get(User, user_id)
        if user_row is None:
            raise HTTPException(status_code=404, detail="User not found")

        gh_row = await session.get(UserGitHub, user_id)

        return {
            "id":            user_row.id,
            "name":          user_row.name or "",
            "email":         user_row.email,
            "has_password":  bool(user_row.password_hash),
            "google_linked": bool(user_row.google_id),
            "github_linked": bool(user_row.github_id),
            "github_login":  gh_row.github_login if gh_row else None,
            "created_at":    user_row.created_at.isoformat() if user_row.created_at else None,
        }


@router.put("/profile")
async def update_profile(body: UpdateProfileRequest, user: dict = Depends(require_auth)):
    """Update display name."""
    from ..db.session import get_session
    from ..db.models import User

    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name cannot be empty")

    user_id = user.get("sub", "")

    async with get_session() as session:
        if session is None:
            raise HTTPException(status_code=503, detail="Database not configured")
        user_row = await session.get(User, user_id)
        if user_row is None:
            raise HTTPException(status_code=404, detail="User not found")
        user_row.name = name

    # Issue a fresh token with the updated name
    new_token = create_token(user_id, user.get("email", ""), name)
    response = JSONResponse({"status": "updated", "name": name, "token": new_token})
    set_token_cookie(response, new_token)
    return response


@router.put("/email")
async def update_email(body: UpdateEmailRequest, user: dict = Depends(require_auth)):
    """Change email address. Password required to confirm."""
    from sqlalchemy import select
    from ..db.session import get_session
    from ..db.models import User

    new_email = body.email.lower().strip()
    if not new_email or "@" not in new_email:
        raise HTTPException(status_code=400, detail="Invalid email address")

    user_id = user.get("sub", "")

    async with get_session() as session:
        if session is None:
            raise HTTPException(status_code=503, detail="Database not configured")

        user_row = await session.get(User, user_id)
        if user_row is None:
            raise HTTPException(status_code=404, detail="User not found")

        # Must have a password to confirm identity this way
        if not user_row.password_hash:
            raise HTTPException(
                status_code=400,
                detail="Password confirmation required — set a password first",
            )
        if not verify_password(body.password, user_row.password_hash):
            raise HTTPException(status_code=401, detail="Incorrect password")

        # Check email not already taken
        existing = await session.execute(select(User).where(User.email == new_email))
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Email already in use")

        user_row.email = new_email

    new_token = create_token(user_id, new_email, user.get("name", ""))
    response = JSONResponse({"status": "updated", "email": new_email, "token": new_token})
    set_token_cookie(response, new_token)
    return response


@router.put("/password")
async def update_password(body: UpdatePasswordRequest, user: dict = Depends(require_auth)):
    """Change password. Requires the current password."""
    from ..db.session import get_session
    from ..db.models import User

    if len(body.new_password) < 8:
        raise HTTPException(status_code=400, detail="New password must be at least 8 characters")

    user_id = user.get("sub", "")

    async with get_session() as session:
        if session is None:
            raise HTTPException(status_code=503, detail="Database not configured")

        user_row = await session.get(User, user_id)
        if user_row is None:
            raise HTTPException(status_code=404, detail="User not found")

        # If the account has no password yet (OAuth-only), allow setting one without current_password
        if user_row.password_hash:
            if not verify_password(body.current_password, user_row.password_hash):
                raise HTTPException(status_code=401, detail="Current password is incorrect")

        user_row.password_hash = hash_password(body.new_password)

    return {"status": "updated"}


@router.get("/zen-summary")
async def get_zen_summary(user: dict = Depends(require_auth)):
    """Return monthly and lifetime spend summaries from ZenUsage."""
    from sqlalchemy import select, func
    from ..db.session import get_session
    from ..db.models import ZenUsage, UserCredits

    user_id = user.get("sub", "")
    year_month = datetime.now(timezone.utc).strftime("%Y-%m")

    async with get_session() as session:
        if session is None:
            return {
                "month_spent_cents": 0,
                "lifetime_spent_cents": 0,
                "balance_cents": 0,
                "month_run_count": 0,
            }

        # Monthly spend
        month_result = await session.execute(
            select(func.sum(ZenUsage.cost_cents))
            .where(ZenUsage.user_id == user_id)
            .where(ZenUsage.year_month == year_month)
        )
        month_spent = month_result.scalar() or 0

        # Lifetime spend
        lifetime_result = await session.execute(
            select(func.sum(ZenUsage.cost_cents))
            .where(ZenUsage.user_id == user_id)
        )
        lifetime_spent = lifetime_result.scalar() or 0

        # Monthly distinct run count
        run_count_result = await session.execute(
            select(func.count(func.distinct(ZenUsage.run_id)))
            .where(ZenUsage.user_id == user_id)
            .where(ZenUsage.year_month == year_month)
        )
        month_runs = run_count_result.scalar() or 0

        # Current balance
        creds = await session.get(UserCredits, user_id)
        balance = creds.balance_cents if creds else 0

    return {
        "month_spent_cents": int(month_spent),
        "lifetime_spent_cents": int(lifetime_spent),
        "balance_cents": balance,
        "month_run_count": month_runs,
    }


@router.delete("")
async def delete_account(user: dict = Depends(require_auth)):
    """Permanently delete the account and all associated data."""
    from sqlalchemy import delete as sql_delete
    from ..db.session import get_session
    from ..db.models import User, UserUsage, UserCredits, UserGitHub, Run, ZenUsage

    user_id = user.get("sub", "")

    async with get_session() as session:
        if session is None:
            raise HTTPException(status_code=503, detail="Database not configured")

        # Delete in dependency order
        # RunFiles are cascade-deleted with Runs via FK
        await session.execute(sql_delete(Run).where(Run.user_id == user_id))
        await session.execute(sql_delete(UserUsage).where(UserUsage.user_id == user_id))
        await session.execute(sql_delete(UserCredits).where(UserCredits.user_id == user_id))
        await session.execute(sql_delete(UserGitHub).where(UserGitHub.user_id == user_id))
        await session.execute(sql_delete(ZenUsage).where(ZenUsage.user_id == user_id))

        user_row = await session.get(User, user_id)
        if user_row:
            await session.delete(user_row)

    response = JSONResponse({"status": "deleted"})
    response.delete_cookie("token", path="/")
    return response
