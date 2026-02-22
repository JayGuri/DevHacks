# backend/projects/routes.py — Project CRUD REST API
"""
GET    /api/projects                    → Project[]
GET    /api/projects/:id                → Project
POST   /api/projects                    → Project (create new)
PATCH  /api/projects/:id                → Project (update)
DELETE /api/projects/:id                → void
POST   /api/projects/:id/join           → void
POST   /api/projects/validate-code      → { project }
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from auth.dependencies import get_current_user
from auth.settings import ENFORCE_TIER_RESTRICTIONS, FREE_TIER_MAX_NODES, PRO_ADVANCED_AGGREGATIONS
from db.database import get_db
from db.models import User, Project, ProjectMember, _invite_code, _uuid
from projects.schemas import (
    ProjectCreateRequest,
    ProjectUpdateRequest,
    JoinByCodeRequest,
    ValidateCodeRequest,
    MemberResponse,
    ProjectResponse,
    ProjectConfigSchema,
)

router = APIRouter()


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def _format_project(project: Project, db: Session) -> dict:
    """Convert a Project ORM to the frontend-expected JSON shape."""
    members_list = []
    for m in project.members:
        user = db.query(User).filter(User.id == m.user_id).first()
        members_list.append({
            "userId": m.user_id,
            "userName": user.name if user else "Unknown",
            "nodeId": m.node_id,
            "role": m.role,
            "joinedAt": m.joined_at.isoformat() if m.joined_at else "",
        })

    config = project.config or {}

    return {
        "id": project.id,
        "name": project.name,
        "description": project.description or "",
        "createdBy": project.created_by,
        "createdAt": project.created_at.isoformat() if project.created_at else "",
        "isActive": project.is_active,
        "visibility": project.visibility,
        "inviteCode": project.invite_code,
        "maxMembers": project.max_members,
        "members": members_list,
        "config": config,
        "joinRequests": [],
    }


def _assign_node_id(index: int) -> str:
    """Generate a display node ID like NODE_A1, NODE_B2, etc."""
    row = chr(65 + (index // 4))  # A, B, C, D...
    col = (index % 4) + 1
    return f"NODE_{row}{col}"


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------

@router.get("/projects")
def list_projects(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all projects (public + private where user is a member)."""
    projects = db.query(Project).all()
    return [_format_project(p, db) for p in projects]


@router.get("/projects/{project_id}")
def get_project(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a single project with members and config."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return _format_project(project, db)


@router.post("/projects")
def create_project(
    body: ProjectCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new project with FL training configuration.

    Tier enforcement:
      - FREE users: numClients and max_members capped at FREE_TIER_MAX_NODES (5).
      - FREE users: advanced aggregation methods (multi_krum, trimmed_mean,
        coordinate_median) are rejected — defaulted to fedavg.
    """
    # Clamp node count and block advanced aggregation for FREE tier
    num_clients = body.numClients
    aggregation_method = body.aggregationMethod
    if ENFORCE_TIER_RESTRICTIONS and current_user.subscription_tier != "PRO":
        if num_clients > FREE_TIER_MAX_NODES:
            num_clients = FREE_TIER_MAX_NODES
        if aggregation_method in PRO_ADVANCED_AGGREGATIONS:
            aggregation_method = "fedavg"

    config = {
        "numClients": num_clients,
        "byzantineFraction": body.byzantineFraction,
        "attackType": body.attackType,
        "aggregationMethod": aggregation_method,
        "numRounds": body.numRounds,
        "dirichletAlpha": body.dirichletAlpha,
        "useDifferentialPrivacy": body.useDifferentialPrivacy,
        "dpNoiseMultiplier": body.dpNoiseMultiplier,
        "dpMaxGradNorm": body.dpMaxGradNorm,
        "sabdAlpha": body.sabdAlpha,
        "localEpochs": body.localEpochs,
    }

    project = Project(
        name=body.name,
        description=body.description,
        created_by=current_user.id,
        visibility=body.visibility,
        invite_code=_invite_code() if body.visibility == "private" else None,
        max_members=num_clients,
        config=config,
    )
    db.add(project)
    db.flush()

    # Add creator as lead member
    member = ProjectMember(
        user_id=current_user.id,
        project_id=project.id,
        node_id=_assign_node_id(0),
        role="lead",
    )
    db.add(member)
    db.commit()
    db.refresh(project)

    return _format_project(project, db)


@router.patch("/projects/{project_id}")
def update_project(
    project_id: str,
    body: ProjectUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update project properties or config."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if body.name is not None:
        project.name = body.name
    if body.description is not None:
        project.description = body.description
    if body.isActive is not None:
        project.is_active = body.isActive
    if body.visibility is not None:
        project.visibility = body.visibility
        if body.visibility == "private" and not project.invite_code:
            project.invite_code = _invite_code()
    if body.config is not None:
        new_config = body.config.model_dump()
        # Free-tier guard: cap node count and block advanced aggregation on update
        if ENFORCE_TIER_RESTRICTIONS and current_user.subscription_tier != "PRO":
            if new_config.get("numClients", 0) > FREE_TIER_MAX_NODES:
                new_config["numClients"] = FREE_TIER_MAX_NODES
            if new_config.get("aggregationMethod") in PRO_ADVANCED_AGGREGATIONS:
                new_config["aggregationMethod"] = "fedavg"
        project.config = new_config

    db.commit()
    db.refresh(project)
    return _format_project(project, db)


@router.delete("/projects/{project_id}")
def delete_project(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete (archive) a project."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    project.is_active = False
    db.commit()
    return {"message": "Project archived"}


@router.post("/projects/{project_id}/join")
def join_project(
    project_id: str,
    body: JoinByCodeRequest = JoinByCodeRequest(),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Join a project (public or via invite code)."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Check if already a member
    existing = db.query(ProjectMember).filter(
        ProjectMember.project_id == project_id,
        ProjectMember.user_id == current_user.id,
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="Already a member")

    # Check capacity
    member_count = db.query(ProjectMember).filter(
        ProjectMember.project_id == project_id
    ).count()
    if member_count >= project.max_members:
        raise HTTPException(status_code=409, detail="Project is full")

    # For private projects, validate invite code
    if project.visibility == "private":
        if not body.inviteCode or body.inviteCode != project.invite_code:
            raise HTTPException(status_code=403, detail="Invalid invite code")

    member = ProjectMember(
        user_id=current_user.id,
        project_id=project_id,
        node_id=_assign_node_id(member_count),
        role="contributor",
    )
    db.add(member)
    db.commit()
    return {"message": "Joined project", "nodeId": member.node_id}


@router.post("/projects/validate-code")
def validate_code(
    body: ValidateCodeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Validate an invite code and return the project if valid."""
    project = db.query(Project).filter(Project.invite_code == body.code).first()
    if not project:
        return {"project": None}
    return {"project": _format_project(project, db)}
