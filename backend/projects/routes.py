# backend/projects/routes.py — Projects REST API
"""
Project CRUD operations using Beanie ODM.
"""

from fastapi import APIRouter, HTTPException, Depends
from typing import List

from auth.dependencies import get_current_user
from db.models import User, Project, ProjectMember, _uuid, _invite_code
from projects.schemas import (
    ProjectCreateRequest,
    ProjectUpdateRequest,
    JoinByCodeRequest,
    ValidateCodeRequest,
)

router = APIRouter()


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

async def _format_project(project: Project) -> dict:
    """Convert Project document to frontend JSON format."""
    # Fetch members
    members_list = []
    members = await ProjectMember.find(ProjectMember.project_id == project.id).to_list()
    
    for m in members:
        user = await User.find_one(User.id == m.user_id)
        members_list.append({
            "userId": m.user_id,
            "userName": user.name if user else "Unknown",
            "nodeId": m.node_id,
            "role": m.role,
            "joinedAt": m.joined_at.isoformat() if m.joined_at else "",
        })

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
        "config": project.config or {},
        "joinRequests": [],
    }


def _assign_node_id(index: int) -> str:
    """Generate display node ID like NODE_A1."""
    row = chr(65 + (index // 4))
    col = (index % 4) + 1
    return f"NODE_{row}{col}"


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------

@router.get("/projects")
async def list_projects(current_user: User = Depends(get_current_user)):
    """List all projects."""
    projects = await Project.find_all().to_list()
    return [await _format_project(p) for p in projects]


@router.get("/projects/{project_id}")
async def get_project(
    project_id: str,
    current_user: User = Depends(get_current_user),
):
    """Get single project with members."""
    project = await Project.find_one(Project.id == project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return await _format_project(project)


@router.post("/projects")
async def create_project(
    body: ProjectCreateRequest,
    current_user: User = Depends(get_current_user),
):
    """Create new project."""
    project = Project(
        name=body.name,
        description=body.description or "",
        created_by=current_user.id,
        visibility=body.visibility,
        invite_code=_invite_code() if body.visibility == "private" else None,
        max_members=body.maxMembers or 10,
        config=body.config.dict() if body.config else {},
    )
    await project.insert()

    # Add creator as first member (lead role)
    member = ProjectMember(
        user_id=current_user.id,
        project_id=project.id,
        node_id="NODE_A1",
        role="lead",
    )
    await member.insert()

    return await _format_project(project)


@router.patch("/projects/{project_id}")
async def update_project(
    project_id: str,
    body: ProjectUpdateRequest,
    current_user: User = Depends(get_current_user),
):
    """Update project."""
    project = await Project.find_one(Project.id == project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if project.created_by != current_user.id:
        raise HTTPException(status_code=403, detail="Only project creator can update")

    # Update fields
    if body.name is not None:
        project.name = body.name
    if body.description is not None:
        project.description = body.description
    if body.visibility is not None:
        project.visibility = body.visibility
        if body.visibility == "private" and not project.invite_code:
            project.invite_code = _invite_code()
    if body.config is not None:
        project.config = body.config.dict()

    await project.save()
    return await _format_project(project)


@router.delete("/projects/{project_id}")
async def delete_project(
    project_id: str,
    current_user: User = Depends(get_current_user),
):
    """Delete project."""
    project = await Project.find_one(Project.id == project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if project.created_by != current_user.id:
        raise HTTPException(status_code=403, detail="Only project creator can delete")

    # Delete all members
    members = await ProjectMember.find(ProjectMember.project_id == project_id).to_list()
    for m in members:
        await m.delete()

    await project.delete()
    return {"message": "Project deleted successfully"}


@router.post("/projects/{project_id}/join")
async def join_project(
    project_id: str,
    current_user: User = Depends(get_current_user),
):
    """Join a public project directly."""
    project = await Project.find_one(Project.id == project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Check if already member
    existing = await ProjectMember.find_one(
        ProjectMember.user_id == current_user.id,
        ProjectMember.project_id == project_id,
    )
    if existing:
        raise HTTPException(status_code=409, detail="Already a member")

    # Check member limit
    members_count = await ProjectMember.find(ProjectMember.project_id == project_id).count()
    if members_count >= project.max_members:
        raise HTTPException(status_code=409, detail="Project is full")

    # Add member
    node_id = _assign_node_id(members_count)
    member = ProjectMember(
        user_id=current_user.id,
        project_id=project_id,
        node_id=node_id,
        role="contributor",
    )
    await member.insert()

    return {"message": "Joined project successfully", "nodeId": node_id}


@router.post("/projects/validate-code")
async def validate_code(
    body: ValidateCodeRequest,
    current_user: User = Depends(get_current_user),
):
    """Validate invite code and return project."""
    project = await Project.find_one(Project.invite_code == body.inviteCode)
    if not project:
        raise HTTPException(status_code=404, detail="Invalid invite code")

    return {"project": await _format_project(project)}
