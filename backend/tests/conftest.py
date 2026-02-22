# backend/tests/conftest.py — Shared fixtures for all test modules
"""
Sets up:
  - In-memory SQLite database with StaticPool (critical: avoids per-connection isolation)
  - Patches db.database.engine and SessionLocal so ALL code paths share one DB
  - FastAPI dependency override for get_db
  - User / project / membership fixtures
  - Coordinator + processor registry cleanup between tests
  - Synchronous TestClient (starlette) for REST + WebSocket tests
"""

import os
import base64
import json

# ──────────────────────────────────────────────────────────────────────────────
# Set DATABASE_URL before any backend imports.
# ──────────────────────────────────────────────────────────────────────────────
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

import pytest
import numpy as np
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.testclient import TestClient

# ──────────────────────────────────────────────────────────────────────────────
# Create the test engine with StaticPool.
#
# WHY StaticPool?
# SQLite in-memory databases are per-connection. Without StaticPool, SQLAlchemy
# may hand out different connections from its pool — each with an empty DB.
# StaticPool forces all sessions to reuse a single underlying connection, so
# tables created in one session are visible in all others.
# ──────────────────────────────────────────────────────────────────────────────

_TEST_ENGINE = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
_TestSession = sessionmaker(autocommit=False, autoflush=False, bind=_TEST_ENGINE)

# ──────────────────────────────────────────────────────────────────────────────
# Patch db.database BEFORE importing the app.
# This redirects init_db() and all internal SessionLocal usage to _TEST_ENGINE.
# ──────────────────────────────────────────────────────────────────────────────

import db.database as _db_module

_db_module.engine = _TEST_ENGINE
_db_module.SessionLocal = _TestSession

# Now import the rest of the app (all modules that import from db.database will
# still get the patched engine if they access it via the module, not a copy)
from db.database import Base, get_db
from db.models import User, Project, ProjectMember
from auth.utils import hash_password, create_token
from app import app


def _override_get_db():
    db = _TestSession()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = _override_get_db


# ──────────────────────────────────────────────────────────────────────────────
# Auto-reset DB + module-level registries between each test
# ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def reset_db_and_registries():
    """Create tables before each test, drop after; also clear FL registries."""
    Base.metadata.create_all(bind=_TEST_ENGINE)

    from training.coordinator import _coordinators
    from training.fl_processor import _processors

    _coordinators.clear()
    _processors.clear()

    yield

    # Cancel any lingering coordinator tasks before dropping tables
    from training.coordinator import _coordinators as coords
    from training.fl_processor import _processors as procs

    for coord in list(coords.values()):
        if coord._task and not coord._task.done():
            coord._task.cancel()
    coords.clear()
    procs.clear()

    Base.metadata.drop_all(bind=_TEST_ENGINE)


# ──────────────────────────────────────────────────────────────────────────────
# DB session fixture
# ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def db():
    session = _TestSession()
    try:
        yield session
    finally:
        session.close()


# ──────────────────────────────────────────────────────────────────────────────
# User / auth fixtures
# ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def lead_user(db):
    """A TEAM_LEAD PRO user."""
    user = User(
        name="Lead User",
        email="lead@test.com",
        hashed_password=hash_password("password"),
        role="TEAM_LEAD",
        subscription_tier="PRO",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def free_user(db):
    """A CONTRIBUTOR FREE-tier user."""
    user = User(
        name="Free Contributor",
        email="free@test.com",
        hashed_password=hash_password("password"),
        role="CONTRIBUTOR",
        subscription_tier="FREE",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def lead_token(lead_user):
    return create_token(lead_user.id, lead_user.role, lead_user.subscription_tier)


@pytest.fixture
def free_token(free_user):
    return create_token(free_user.id, free_user.role, free_user.subscription_tier)


# ──────────────────────────────────────────────────────────────────────────────
# Project + membership fixtures
# ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def project(db, lead_user):
    """A test FL project with a small config."""
    proj = Project(
        name="Test FL Project",
        description="Created for testing",
        created_by=lead_user.id,
        config={
            "numClients": 4,
            "byzantineFraction": 0.2,
            "attackType": "sign_flipping",
            "aggregationMethod": "trimmed_mean",
            "numRounds": 3,
            "l2GatekeeperThreshold": 10.0,
            "personalizationAlpha": 0.0,
            "useDifferentialPrivacy": False,
        },
    )
    db.add(proj)
    db.commit()
    db.refresh(proj)
    return proj


@pytest.fixture
def membership(db, lead_user, project):
    """Membership row for lead_user in the test project."""
    m = ProjectMember(
        user_id=lead_user.id,
        project_id=project.id,
        node_id="NODE_T1",
        role="lead",
    )
    db.add(m)
    db.commit()
    db.refresh(m)
    return m


@pytest.fixture
def free_membership(db, free_user, project):
    """Membership row for free_user in the test project."""
    m = ProjectMember(
        user_id=free_user.id,
        project_id=project.id,
        node_id="NODE_T2",
        role="contributor",
    )
    db.add(m)
    db.commit()
    db.refresh(m)
    return m


# ──────────────────────────────────────────────────────────────────────────────
# HTTP / WebSocket test client
# ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def client():
    """Starlette synchronous TestClient (supports both REST and WebSocket)."""
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


# ──────────────────────────────────────────────────────────────────────────────
# Weight encoding helpers (import directly in test files as plain functions)
# ──────────────────────────────────────────────────────────────────────────────

def encode_weights(weight_dict: dict) -> str:
    """Encode {layer: list[float]} → base64 msgpack/JSON string."""
    try:
        import msgpack
        packed = msgpack.packb(weight_dict)
    except ImportError:
        packed = json.dumps(weight_dict).encode("utf-8")
    return base64.b64encode(packed).decode("utf-8")


def small_norm_weights_b64() -> str:
    """Weights with L2 norm ≈ 1.73 (well below default threshold 10.0)."""
    return encode_weights({"layer1": [1.0, 1.0, 1.0]})


def large_norm_weights_b64() -> str:
    """Weights with L2 norm ≈ 1000 (far above default threshold 10.0)."""
    return encode_weights({"layer1": [100.0] * 100})
