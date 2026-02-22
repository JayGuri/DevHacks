# backend/auth/dependencies.py — FastAPI dependencies for authentication
"""
Provides FastAPI dependency functions for route protection.

Layer 1 — RBAC (always enforced):
  get_current_user      — any authenticated user
  require_team_lead     — TEAM_LEAD role only

Layer 2 — Subscription Tier (bypassed when ENFORCE_TIER_RESTRICTIONS=False):
  require_pro_tier      — authenticated user with PRO tier
  require_team_lead_pro — TEAM_LEAD role AND PRO tier (most restrictive)

Developer bypass:
  Set ENFORCE_TIER_RESTRICTIONS=false in .env to skip all tier checks.
  RBAC (role) checks are NEVER bypassed regardless of this setting.
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

import jwt as pyjwt

from auth.utils import decode_token
from auth.settings import ENFORCE_TIER_RESTRICTIONS
from db.database import get_db
from db.models import User

security = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    """Decode Bearer token and return the User ORM object."""
    try:
        payload = decode_token(credentials.credentials)
    except pyjwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    except pyjwt.InvalidTokenError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Invalid token: {e}")

    user = db.query(User).filter(User.id == payload["sub"]).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


def require_team_lead(current_user: User = Depends(get_current_user)) -> User:
    """Only allow TEAM_LEAD users. Always enforced regardless of bypass flag."""
    if current_user.role != "TEAM_LEAD":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Team Lead access required",
        )
    return current_user


def require_pro_tier(current_user: User = Depends(get_current_user)) -> User:
    """Require PRO subscription tier.

    Fully bypassed when ENFORCE_TIER_RESTRICTIONS=False in environment.
    Does NOT enforce role — any authenticated PRO user passes.
    """
    if ENFORCE_TIER_RESTRICTIONS and current_user.subscription_tier != "PRO":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Pro subscription required. Upgrade at /admin/billing.",
        )
    return current_user


def require_team_lead_pro(current_user: User = Depends(get_current_user)) -> User:
    """Require TEAM_LEAD role (always enforced) AND PRO tier (bypassed by flag).

    Use this for features that are both admin-only AND Pro-tier gated,
    such as advanced aggregation configuration and deep telemetry export.
    """
    if current_user.role != "TEAM_LEAD":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Team Lead access required",
        )
    if ENFORCE_TIER_RESTRICTIONS and current_user.subscription_tier != "PRO":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Pro subscription required. Upgrade at /admin/billing.",
        )
    return current_user
