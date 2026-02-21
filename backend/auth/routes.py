# backend/auth/routes.py — Authentication REST API
"""
POST /api/auth/signup  — Register new user
POST /api/auth/login   — Authenticate user
GET  /api/auth/me      — Get current user from JWT
GET  /api/users        — List all users (admin)
PATCH /api/users/:id/role — Change user role (admin)
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from auth.utils import hash_password, verify_password, create_token
from auth.dependencies import get_current_user, require_team_lead
from db.database import get_db
from db.models import User

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

    class Config:
        from_attributes = True


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
def signup(body: SignupRequest, db: Session = Depends(get_db)):
    """Register a new user."""
    existing = db.query(User).filter(User.email == body.email).first()
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")

    user = User(
        name=body.name,
        email=body.email,
        hashed_password=hash_password(body.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_token(user.id, user.role)
    return {"user": _user_to_response(user), "token": token}


@router.post("/auth/login", response_model=AuthResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)):
    """Authenticate and return user + JWT."""
    user = db.query(User).filter(User.email == body.email).first()
    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = create_token(user.id, user.role)
    return {"user": _user_to_response(user), "token": token}


@router.get("/auth/me")
def get_me(current_user: User = Depends(get_current_user)):
    """Return the current authenticated user."""
    return {"user": _user_to_response(current_user)}


@router.get("/users")
def list_users(
    db: Session = Depends(get_db),
    _: User = Depends(require_team_lead),
):
    """List all users (admin only)."""
    users = db.query(User).all()
    return [_user_to_response(u) for u in users]


@router.patch("/users/{user_id}/role")
def update_role(
    user_id: str,
    body: RoleUpdateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_team_lead),
):
    """Change a user's role (admin only)."""
    if body.role not in ("TEAM_LEAD", "CONTRIBUTOR"):
        raise HTTPException(status_code=400, detail="Invalid role")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.role = body.role
    db.commit()
    db.refresh(user)
    return _user_to_response(user)
