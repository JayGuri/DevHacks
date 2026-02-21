# backend/join_requests/routes_mongo.py — MongoDB JoinRequests REST API
"""
MongoDB version of join request operations.
"""

from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime, timezone

from auth.dependencies_mongo import get_current_user, require_team_lead
from db.mongo_models import User, Project, ProjectMember, JoinRequest, Notification
from join_requests.routes import JoinRequestCreate

router = APIRouter()


@router.get("/join-requests")
async def list_join_requests(current_user: User = Depends(require_team_lead)):
    """List all pending join requests (admin only)."""
    requests = await JoinRequest.find(JoinRequest.status == "pending").to_list()
    
    result = []
    for req in requests:
        user = await User.find_one(User.id == req.user_id)
        project = await Project.find_one(Project.id == req.project_id)
        
        result.append({
            "id": req.id,
            "userId": req.user_id,
            "userName": user.name if user else "Unknown",
            "projectId": req.project_id,
            "projectName": project.name if project else "Unknown",
            "message": req.message,
            "status": req.status,
            "requestedAt": req.requested_at.isoformat() if req.requested_at else "",
        })
    
    return result


@router.post("/join-requests")
async def create_join_request(
    body: JoinRequestCreate,
    current_user: User = Depends(get_current_user),
):
    """Create new join request."""
    # Check if project exists
    project = await Project.find_one(Project.id == body.projectId)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Check if already member
    existing_member = await ProjectMember.find_one(
        ProjectMember.user_id == current_user.id,
        ProjectMember.project_id == body.projectId,
    )
    if existing_member:
        raise HTTPException(status_code=409, detail="Already a member")

    # Check if already requested
    existing_request = await JoinRequest.find_one(
        JoinRequest.user_id == current_user.id,
        JoinRequest.project_id == body.projectId,
        JoinRequest.status == "pending",
    )
    if existing_request:
        raise HTTPException(status_code=409, detail="Join request already pending")

    # Create request
    request = JoinRequest(
        user_id=current_user.id,
        project_id=body.projectId,
        message=body.message or "",
    )
    await request.insert()

    return {"message": "Join request submitted", "requestId": request.id}


@router.patch("/join-requests/{request_id}/approve")
async def approve_join_request(
    request_id: str,
    current_user: User = Depends(require_team_lead),
):
    """Approve join request."""
    request = await JoinRequest.find_one(JoinRequest.id == request_id)
    if not request:
        raise HTTPException(status_code=404, detail="Request not found")

    if request.status != "pending":
        raise HTTPException(status_code=400, detail="Request already resolved")

    # Add member
    members_count = await ProjectMember.find(ProjectMember.project_id == request.project_id).count()
    node_id = _assign_node_id(members_count)
    
    member = ProjectMember(
        user_id=request.user_id,
        project_id=request.project_id,
        node_id=node_id,
        role="contributor",
    )
    await member.insert()

    # Update request
    request.status = "approved"
    request.resolved_at = datetime.now(timezone.utc)
    request.resolved_by = current_user.id
    await request.save()

    # Create notification
    notification = Notification(
        user_id=request.user_id,
        type="info",
        message=f"Your join request was approved. Node ID: {node_id}",
        project_id=request.project_id,
    )
    await notification.insert()

    return {"message": "Request approved", "nodeId": node_id}


@router.patch("/join-requests/{request_id}/reject")
async def reject_join_request(
    request_id: str,
    current_user: User = Depends(require_team_lead),
):
    """Reject join request."""
    request = await JoinRequest.find_one(JoinRequest.id == request_id)
    if not request:
        raise HTTPException(status_code=404, detail="Request not found")

    if request.status != "pending":
        raise HTTPException(status_code=400, detail="Request already resolved")

    request.status = "rejected"
    request.resolved_at = datetime.now(timezone.utc)
    request.resolved_by = current_user.id
    await request.save()

    # Create notification
    notification = Notification(
        user_id=request.user_id,
        type="info",
        message="Your join request was rejected.",
        project_id=request.project_id,
    )
    await notification.insert()

    return {"message": "Request rejected"}


def _assign_node_id(index: int) -> str:
    """Generate display node ID."""
    row = chr(65 + (index // 4))
    col = (index % 4) + 1
    return f"NODE_{row}{col}"
