# backend/db/models.py — ORM models for Users, Projects, JoinRequests, Notifications, ActivityLogs
"""
All ORM models map 1:1 to the frontend spec entities.
ProjectConfig is stored as a JSON column inside the Project table.
"""

import uuid
import string
import random
from datetime import datetime, timezone

from sqlalchemy import (
    Column, String, Boolean, Integer, Float, Text, DateTime, ForeignKey, JSON,
    Enum as SAEnum,
)
from sqlalchemy.orm import relationship

from db.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _invite_code() -> str:
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=6))


# --------------------------------------------------------------------------
# User
# --------------------------------------------------------------------------

class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=_uuid)
    name = Column(String(120), nullable=False)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False, default="CONTRIBUTOR")  # TEAM_LEAD | CONTRIBUTOR
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    # Relationships
    projects_created = relationship("Project", back_populates="creator", lazy="dynamic")
    memberships = relationship("ProjectMember", back_populates="user", lazy="dynamic")


# --------------------------------------------------------------------------
# Project
# --------------------------------------------------------------------------

class Project(Base):
    __tablename__ = "projects"

    id = Column(String, primary_key=True, default=_uuid)
    name = Column(String(200), nullable=False)
    description = Column(Text, default="")
    created_by = Column(String, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    is_active = Column(Boolean, default=True)
    visibility = Column(String(10), default="public")  # public | private
    invite_code = Column(String(6), nullable=True, default=None)
    max_members = Column(Integer, default=10)

    # FL training configuration — stored as JSON
    config = Column(JSON, default=lambda: {
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

    # Relationships
    creator = relationship("User", back_populates="projects_created")
    members = relationship("ProjectMember", back_populates="project", cascade="all, delete-orphan")
    join_requests = relationship("JoinRequest", back_populates="project", cascade="all, delete-orphan")


# --------------------------------------------------------------------------
# ProjectMember
# --------------------------------------------------------------------------

class ProjectMember(Base):
    __tablename__ = "project_members"

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    project_id = Column(String, ForeignKey("projects.id"), nullable=False)
    node_id = Column(String(20), nullable=True)  # e.g. "NODE_B2"
    role = Column(String(20), default="contributor")  # lead | contributor
    joined_at = Column(DateTime(timezone=True), default=_utcnow)

    # Relationships
    user = relationship("User", back_populates="memberships")
    project = relationship("Project", back_populates="members")


# --------------------------------------------------------------------------
# JoinRequest
# --------------------------------------------------------------------------

class JoinRequest(Base):
    __tablename__ = "join_requests"

    id = Column(String, primary_key=True, default=lambda: f"req-{int(_utcnow().timestamp() * 1000)}")
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    project_id = Column(String, ForeignKey("projects.id"), nullable=False)
    message = Column(Text, default="")
    status = Column(String(10), default="pending")  # pending | approved | rejected
    requested_at = Column(DateTime(timezone=True), default=_utcnow)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    resolved_by = Column(String, ForeignKey("users.id"), nullable=True)

    # Relationships
    user = relationship("User", foreign_keys=[user_id])
    project = relationship("Project", back_populates="join_requests")
    resolver = relationship("User", foreign_keys=[resolved_by])


# --------------------------------------------------------------------------
# Notification
# --------------------------------------------------------------------------

class Notification(Base):
    __tablename__ = "notifications"

    id = Column(String, primary_key=True, default=lambda: f"notif-{int(_utcnow().timestamp() * 1000)}")
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    type = Column(String(20), default="info")  # alert | node_blocked | config | info
    message = Column(Text, nullable=False)
    project_id = Column(String, nullable=True)
    read = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=_utcnow)


# --------------------------------------------------------------------------
# ActivityLog
# --------------------------------------------------------------------------

class ActivityLog(Base):
    __tablename__ = "activity_logs"

    id = Column(String, primary_key=True, default=_uuid)
    type = Column(String(30), nullable=False)  # block | unblock | config_change | round_complete
    node_id = Column(String, nullable=True)
    display_id = Column(String, nullable=True)
    project_id = Column(String, ForeignKey("projects.id"), nullable=False)
    timestamp = Column(DateTime(timezone=True), default=_utcnow)
