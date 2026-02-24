# backend/db/models.py — Beanie ODM models for MongoDB
"""
MongoDB Document Models using Beanie ODM
========================================
Maps to the same schema as SQLAlchemy models for API compatibility.

Beanie provides:
  - Async CRUD operations
  - Pydantic validation
  - MongoDB indexing
  - Relationship simulation via references
"""

import uuid
import string
import random
from datetime import datetime, timezone
from typing import Optional, List

from beanie import Document, Indexed
from pydantic import Field, EmailStr


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _invite_code() -> str:
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=6))


# --------------------------------------------------------------------------
# User Document
# --------------------------------------------------------------------------

class User(Document):
    """User account document."""

    id: str = Field(default_factory=_uuid, alias="_id")
    name: str = Field(max_length=120)
    email: Indexed(EmailStr, unique=True)  # Unique index on email
    hashed_password: str
    role: str = Field(default="CONTRIBUTOR")  # TEAM_LEAD | CONTRIBUTOR
    created_at: datetime = Field(default_factory=_utcnow)

    class Settings:
        name = "users"
        indexes = [
            "email",  # Unique index for fast lookups
        ]

    class Config:
        json_schema_extra = {
            "example": {
                "name": "Alice Smith",
                "email": "alice@example.com",
                "role": "TEAM_LEAD",
            }
        }


# --------------------------------------------------------------------------
# Project Document
# --------------------------------------------------------------------------

class Project(Document):
    """Federated learning project document."""

    id: str = Field(default_factory=_uuid, alias="_id")
    name: str = Field(max_length=200)
    description: str = ""
    created_by: str  # User ID (foreign key simulation)
    created_at: datetime = Field(default_factory=_utcnow)
    is_active: bool = True
    visibility: str = "public"  # public | private
    invite_code: Optional[str] = None
    max_members: int = 10

    # FL training configuration
    config: dict = Field(default_factory=lambda: {
        "numClients": 10,
        "byzantineFraction": 0.2,
        "attackType": "sign_flipping",
        "aggregationMethod": "trimmed_mean",
        "numRounds": 50,
        "dirichletAlpha": 0.5,
        "useDifferentialPrivacy": True,
        "dpNoiseMultiplier": 0.1,
        "dpMaxGradNorm": 1.0,
        "sabdAlpha": 0.5,
        "localEpochs": 3,
    })

    class Settings:
        name = "projects"
        indexes = [
            "created_by",
            "invite_code",
        ]


# --------------------------------------------------------------------------
# ProjectMember Document
# --------------------------------------------------------------------------

class ProjectMember(Document):
    """Project membership document."""

    id: str = Field(default_factory=_uuid, alias="_id")
    user_id: str  # User ID
    project_id: str  # Project ID
    node_id: Optional[str] = None  # e.g. "NODE_B2"
    role: str = "contributor"  # lead | contributor
    joined_at: datetime = Field(default_factory=_utcnow)

    class Settings:
        name = "project_members"
        indexes = [
            [("user_id", 1), ("project_id", 1)],  # Compound index
        ]


# --------------------------------------------------------------------------
# JoinRequest Document
# --------------------------------------------------------------------------

class JoinRequest(Document):
    """Project join request document."""

    id: str = Field(default_factory=lambda: f"req-{int(_utcnow().timestamp() * 1000)}", alias="_id")
    user_id: str  # User ID
    project_id: str  # Project ID
    message: str = ""
    status: str = "pending"  # pending | approved | rejected
    requested_at: datetime = Field(default_factory=_utcnow)
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[str] = None  # User ID

    class Settings:
        name = "join_requests"
        indexes = [
            [("project_id", 1), ("status", 1)],
        ]


# --------------------------------------------------------------------------
# Notification Document
# --------------------------------------------------------------------------

class Notification(Document):
    """User notification document."""

    id: str = Field(default_factory=lambda: f"notif-{int(_utcnow().timestamp() * 1000)}", alias="_id")
    user_id: str  # User ID
    type: str = "info"  # alert | node_blocked | config | info
    message: str
    project_id: Optional[str] = None
    read: bool = False
    created_at: datetime = Field(default_factory=_utcnow)

    class Settings:
        name = "notifications"
        indexes = [
            [("user_id", 1), ("read", 1)],
        ]


# --------------------------------------------------------------------------
# ActivityLog Document
# --------------------------------------------------------------------------

class ActivityLog(Document):
    """System activity log document."""

    id: str = Field(default_factory=_uuid, alias="_id")
    type: str  # block | unblock | config_change | round_complete
    node_id: Optional[str] = None
    display_id: Optional[str] = None
    project_id: str  # Project ID
    timestamp: datetime = Field(default_factory=_utcnow)

    class Settings:
        name = "activity_logs"
        indexes = [
            [("project_id", 1), ("timestamp", -1)],  # Sorted by timestamp
        ]
