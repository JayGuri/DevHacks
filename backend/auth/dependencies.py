# backend/auth/dependencies.py — FastAPI dependencies for authentication
"""
Provides get_current_user and require_role dependencies for route protection.
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

import jwt as pyjwt

from auth.utils import decode_token
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
    """Only allow TEAM_LEAD users."""
    if current_user.role != "TEAM_LEAD":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Team Lead access required",
        )
    return current_user
