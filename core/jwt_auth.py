# core/jwt_auth.py — Shared JWT + password utilities for all backends
"""
Single source of truth for JWT creation/verification and password hashing.
Both `async_federated_learning/` and `backend/` import from here.

Configuration:
  JWT_SECRET        — Required env var (no hardcoded fallback)
  JWT_EXPIRY_HOURS  — Optional, default 24
"""

import os
from datetime import datetime, timedelta, timezone

import jwt
import bcrypt

_JWT_ALGORITHM = "HS256"


# ---------------------------------------------------------------------------
# JWT Secret
# ---------------------------------------------------------------------------

def get_jwt_secret() -> str:
    """Return the JWT secret from the environment.

    Raises RuntimeError if JWT_SECRET is not set, preventing silent use of
    an insecure default in production.
    """
    secret = os.getenv("JWT_SECRET", "")
    if not secret:
        raise RuntimeError(
            "JWT_SECRET environment variable is required. "
            "Set it in your .env file or export it before starting the server."
        )
    return secret


# ---------------------------------------------------------------------------
# Token creation / verification
# ---------------------------------------------------------------------------

def create_token(
    sub: str,
    role: str,
    extra_claims: dict | None = None,
    expiry_hours: int | None = None,
) -> str:
    """Create an HS256 JWT.

    Args:
        sub: Subject (user/node ID).
        role: Role string (e.g. "legitimate_client", "TEAM_LEAD").
        extra_claims: Additional payload fields (display_name, task, etc.).
        expiry_hours: Token lifetime in hours. Defaults to JWT_EXPIRY_HOURS env
                      var or 24.
    """
    if expiry_hours is None:
        expiry_hours = int(os.getenv("JWT_EXPIRY_HOURS", "24"))

    now = datetime.now(timezone.utc)
    payload = {
        "sub": sub,
        "role": role,
        "iat": now,
        "exp": now + timedelta(hours=expiry_hours),
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, get_jwt_secret(), algorithm=_JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    """Decode and validate a JWT. Raises jwt.InvalidTokenError on failure."""
    return jwt.decode(token, get_jwt_secret(), algorithms=[_JWT_ALGORITHM])


# ---------------------------------------------------------------------------
# Password hashing (used by backend/ web auth)
# ---------------------------------------------------------------------------

def hash_password(plain: str) -> str:
    """Hash a plaintext password with bcrypt."""
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a plaintext password against a bcrypt hash."""
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
