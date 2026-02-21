# backend/auth/dependencies_mongo.py — MongoDB dependency injection
"""
FastAPI dependencies for MongoDB-based authentication.
Extracts and validates JWT from Authorization header.
"""

from fastapi import Depends, HTTPException, Header
from typing import Annotated

from core.jwt_auth import decode_token
from db.mongo_models import User


async def get_current_user(authorization: Annotated[str, Header()] = None) -> User:
    """Extract and validate JWT, return the current user document."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

    token = authorization[7:]  # Remove "Bearer " prefix

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
