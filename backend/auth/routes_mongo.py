# backend/auth/routes_mongo.py — MongoDB Authentication REST API
"""
POST /api/auth/signup  — Register new user
POST /api/auth/login   — Authenticate user
GET  /api/auth/me      — Get current user from JWT
GET  /api/users        — List all users (admin)
PATCH /api/users/:id/role — Change user role (admin)

MongoDB version using Beanie ODM (async)
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from auth.utils import hash_password, verify_password, create_token
from auth.dependencies_mongo import get_current_user, require_team_lead
from db.mongo_models import User

router = APIRouter()


# --------------------------------------------------------------------------
# Request / Response schemas
# --------------------------------------------------------------------------

class SignupRequest(BaseModel):
    name: str
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


class UserResponse(BaseModel):
    id: str
    name: str
    email: str
    role: str
    createdAt: str


class AuthResponse(BaseModel):
    user: UserResponse
    token: str


class RoleUpdateRequest(BaseModel):
    role: str  # "TEAM_LEAD" | "CONTRIBUTOR"


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def _user_to_response(user: User) -> dict:
    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "role": user.role,
        "createdAt": user.created_at.isoformat() if user.created_at else "",
    }


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------

@router.post("/auth/signup", response_model=AuthResponse)
async def signup(body: SignupRequest):
    """Register a new user."""
    # Check if email already exists
    existing = await User.find_one(User.email == body.email)
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")

    # Create new user
    user = User(
        name=body.name,
        email=body.email,
        hashed_password=hash_password(body.password),
    )
    await user.insert()

    token = create_token(user.id, user.role)
    return {"user": _user_to_response(user), "token": token}


@router.post("/auth/login", response_model=AuthResponse)
async def login(body: LoginRequest):
    """Authenticate and return user + JWT."""
    user = await User.find_one(User.email == body.email)
    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = create_token(user.id, user.role)
    return {"user": _user_to_response(user), "token": token}


@router.get("/auth/me")
async def get_me(current_user: User = get_current_user):
    """Return the current authenticated user."""
    return {"user": _user_to_response(current_user)}


@router.get("/users")
async def list_users(team_lead_user: User = require_team_lead):
    """List all users (admin only)."""
    users = await User.find_all().to_list()
    return [_user_to_response(u) for u in users]


@router.patch("/users/{user_id}/role")
async def update_role(
    user_id: str,
    body: RoleUpdateRequest,
    team_lead_user: User = require_team_lead,
):
    """Change a user's role (admin only)."""
    if body.role not in ("TEAM_LEAD", "CONTRIBUTOR"):
        raise HTTPException(status_code=400, detail="Invalid role")

    user = await User.find_one(User.id == user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.role = body.role
    await user.save()
    return _user_to_response(user)
