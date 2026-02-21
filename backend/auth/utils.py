# backend/auth/utils.py — JWT creation/verification and password hashing
"""
Thin re-export layer: delegates to core.jwt_auth for shared JWT + bcrypt logic.
This file exists so that existing imports in backend/auth/ continue to work.
"""

import sys
from pathlib import Path

# Ensure the repo root is on sys.path so `core.jwt_auth` is importable
_repo_root = str(Path(__file__).resolve().parents[2])
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

from core.jwt_auth import (  # noqa: E402
    create_token,
    decode_token,
    hash_password,
    verify_password,
)

__all__ = ["create_token", "decode_token", "hash_password", "verify_password"]
