# backend/auth/utils.py — JWT creation/verification and password hashing
"""
Stateless auth utilities using PyJWT + bcrypt.
JWT tokens carry user_id and role in the payload.
"""

import os
from datetime import datetime, timedelta, timezone

import jwt
import bcrypt

JWT_SECRET = os.getenv("JWT_SECRET", "arfl-dev-secret-change-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = int(os.getenv("JWT_EXPIRY_HOURS", "24"))


# --------------------------------------------------------------------------
# Password hashing
# --------------------------------------------------------------------------

def hash_password(plain: str) -> str:
    """Hash a plaintext password with bcrypt."""
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a plaintext password against a bcrypt hash."""
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


# --------------------------------------------------------------------------
# JWT
# --------------------------------------------------------------------------

def create_token(user_id: str, role: str, tier: str = "FREE") -> str:
    """Create a JWT with user_id, role, and subscription_tier in the payload."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "role": role,
        "tier": tier,
        "iat": now,
        "exp": now + timedelta(hours=JWT_EXPIRY_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    """Decode and validate a JWT. Raises jwt.InvalidTokenError on failure."""
    return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
