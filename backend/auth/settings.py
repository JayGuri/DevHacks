# backend/auth/settings.py — Tier enforcement configuration
"""
Central config constants for Access Control and Feature Gating.

ENFORCE_TIER_RESTRICTIONS controls whether subscription tier limits are applied.
  - true  (default): FREE users are blocked from PRO-only features.
  - false (dev bypass): ALL tier checks are skipped; even FREE users get full PRO access.

NOTE: This bypass does NOT affect RBAC. A CONTRIBUTOR role can never access
Team Lead routes regardless of this toggle.
"""

import os

# Developer bypass toggle — set ENFORCE_TIER_RESTRICTIONS=false in .env to disable tier gating
ENFORCE_TIER_RESTRICTIONS: bool = os.getenv("ENFORCE_TIER_RESTRICTIONS", "true").lower() == "true"

# Free tier hard limits
FREE_TIER_MAX_NODES: int = 5

# Aggregation methods restricted to PRO tier
PRO_ADVANCED_AGGREGATIONS: frozenset = frozenset({"multi_krum", "trimmed_mean", "coordinate_median"})
