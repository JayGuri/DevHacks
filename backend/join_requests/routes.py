# backend/join_requests/routes.py — Join Request management API
"""
GET    /api/join-requests  (filter by projectId, userId, status)
POST   /api/join-requests
PATCH  /api/join-requests/:id/approve
PATCH  /api/join-requests/:id/reject
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional

from auth.dependencies import get_current_user
from db.database import get_db
from db.models import User, Project, ProjectMember, JoinRequest, Notification

router = APIRouter()


# --------------------------------------------------------------------------
# Schemas
# --------------------------------------------------------------------------

class JoinRequestCreate(BaseModel):
    projectId: str
    message: str = ""


def _format_request(jr: JoinRequest, db: Session) -> dict:
    user = db.query(User).filter(User.id == jr.user_id).first()
    project = db.query(Project).filter(Project.id == jr.project_id).first()
    return {
        "id": jr.id,
        "userId": jr.user_id,
        "userName": user.name if user else "Unknown",
        "userEmail": user.email if user else "",
        "projectId": jr.project_id,
        "projectName": project.name if project else "Unknown",
        "message": jr.message,
        "status": jr.status,
        "requestedAt": jr.requested_at.isoformat() if jr.requested_at else "",
        "resolvedAt": jr.resolved_at.isoformat() if jr.resolved_at else None,
        "resolvedBy": jr.resolved_by,
    }


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------

@router.get("/join-requests")
def list_join_requests(
    projectId: Optional[str] = Query(default=None),
    userId: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List join requests with optional filters."""
    query = db.query(JoinRequest)
    if projectId:
        query = query.filter(JoinRequest.project_id == projectId)
    if userId:
        query = query.filter(JoinRequest.user_id == userId)
    if status:
        query = query.filter(JoinRequest.status == status)

    requests = query.order_by(JoinRequest.requested_at.desc()).all()
    return [_format_request(jr, db) for jr in requests]


@router.post("/join-requests")
def create_join_request(
    body: JoinRequestCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Submit a new join request."""
    project = db.query(Project).filter(Project.id == body.projectId).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Check for existing pending request
    existing = db.query(JoinRequest).filter(
        JoinRequest.user_id == current_user.id,
        JoinRequest.project_id == body.projectId,
        JoinRequest.status == "pending",
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="A pending request already exists")

    jr = JoinRequest(
        user_id=current_user.id,
        project_id=body.projectId,
        message=body.message,
    )
    db.add(jr)

    # Notify project creator
    notif = Notification(
        user_id=project.created_by,
        type="info",
        message=f"{current_user.name} requested to join {project.name}",
        project_id=project.id,
    )
    db.add(notif)
    db.commit()
    db.refresh(jr)

    return _format_request(jr, db)


@router.patch("/join-requests/{request_id}/approve")
def approve_request(
    request_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Approve a join request — adds user as project member."""
    jr = db.query(JoinRequest).filter(JoinRequest.id == request_id).first()
    if not jr:
        raise HTTPException(status_code=404, detail="Request not found")
    if jr.status != "pending":
        raise HTTPException(status_code=400, detail="Request already resolved")

    project = db.query(Project).filter(Project.id == jr.project_id).first()

    # Check capacity
    member_count = db.query(ProjectMember).filter(
        ProjectMember.project_id == jr.project_id
    ).count()
    if project and member_count >= project.max_members:
        raise HTTPException(status_code=409, detail="Project is full")

    jr.status = "approved"
    jr.resolved_at = datetime.now(timezone.utc)
    jr.resolved_by = current_user.id

    # Add as member
    row = chr(65 + (member_count // 4))
    col = (member_count % 4) + 1
    member = ProjectMember(
        user_id=jr.user_id,
        project_id=jr.project_id,
        node_id=f"NODE_{row}{col}",
        role="contributor",
    )
    db.add(member)

    # Notify the requester
    notif = Notification(
        user_id=jr.user_id,
        type="info",
        message=f"Your request to join {project.name} was approved!",
        project_id=jr.project_id,
    )
    db.add(notif)
    db.commit()
    db.refresh(jr)

    return _format_request(jr, db)


@router.patch("/join-requests/{request_id}/reject")
def reject_request(
    request_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Reject a join request."""
    jr = db.query(JoinRequest).filter(JoinRequest.id == request_id).first()
    if not jr:
        raise HTTPException(status_code=404, detail="Request not found")
    if jr.status != "pending":
        raise HTTPException(status_code=400, detail="Request already resolved")

    project = db.query(Project).filter(Project.id == jr.project_id).first()

    jr.status = "rejected"
    jr.resolved_at = datetime.now(timezone.utc)
    jr.resolved_by = current_user.id

    notif = Notification(
        user_id=jr.user_id,
        type="alert",
        message=f"Your request to join {project.name if project else 'a project'} was rejected.",
        project_id=jr.project_id,
    )
    db.add(notif)
    db.commit()
    db.refresh(jr)

    return _format_request(jr, db)
