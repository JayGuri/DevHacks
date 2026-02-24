# backend/auth/dependencies.py — Dependency injection
"""
FastAPI dependencies for authentication.
Extracts and validates JWT from Authorization header.
"""

from fastapi import Depends, HTTPException, Request

from core.jwt_auth import decode_token
from db.models import User


async def get_current_user(request: Request) -> User:
    """Extract and validate JWT from cookie, return the current user document."""
    token = request.cookies.get("arfl-token")
    if not token:
        raise HTTPException(status_code=401, detail="Missing or invalid authentication cookie")

    try:
        payload = decode_token(token)
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token payload")

        user = await User.find_one(User.id == user_id)
        if not user:
            raise HTTPException(status_code=401, detail="User not found")

        return user

    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}")


async def require_team_lead(current_user: User = Depends(get_current_user)) -> User:
    """Require TEAM_LEAD role."""
    if current_user.role != "TEAM_LEAD":
        raise HTTPException(
            status_code=403,
            detail="This operation requires TEAM_LEAD role"
        )
    return current_user


async def require_team_lead_pro(current_user: User = Depends(require_team_lead)) -> User:
    """Require TEAM_LEAD role + PRO subscription tier."""
    tier = getattr(current_user, "subscription_tier", None)
    if tier != "PRO":
        raise HTTPException(
            status_code=403,
            detail="This operation requires a Pro subscription"
        )
    return current_user
