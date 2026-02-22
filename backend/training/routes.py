# backend/training/routes.py — FL Training control API + WebSocket endpoint
"""
POST   /api/projects/:id/training/start    → Start training
POST   /api/projects/:id/training/pause    → Pause
POST   /api/projects/:id/training/resume   → Resume
POST   /api/projects/:id/training/reset    → Reset to round 0
PATCH  /api/projects/:id/config            → Update config mid-training (PRO: advanced agg methods)
POST   /api/projects/:id/nodes/:nodeId/block   → Block node (TEAM_LEAD only)
POST   /api/projects/:id/nodes/:nodeId/unblock → Unblock node (TEAM_LEAD only)
GET    /api/projects/:id/export            → Download round metrics JSON (PRO only)
GET    /api/projects/:id/training/status   → Current training status
WS     /ws                                 → WebSocket for frontend real-time events
"""

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, Query
from sqlalchemy.orm import Session

from auth.dependencies import get_current_user, require_team_lead, require_team_lead_pro
from auth.settings import ENFORCE_TIER_RESTRICTIONS, FREE_TIER_MAX_NODES, PRO_ADVANCED_AGGREGATIONS
from db.database import get_db
from db.models import User, Project, ProjectMember, ActivityLog, Notification
from training.coordinator import get_coordinator, create_coordinator
from training.schemas import TrainingConfigUpdate, GradientSubmission
from ws.manager import ws_manager

router = APIRouter()


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def _get_project_and_coordinator(project_id: str, db: Session, current_user: User):
    """Get project from DB and its coordinator, creating one if needed."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    coordinator = get_coordinator(project_id)
    if not coordinator:
        coordinator = create_coordinator(project_id, project.config or {}, ws_manager)

    return project, coordinator


# --------------------------------------------------------------------------
# Training Control Routes
# --------------------------------------------------------------------------

@router.post("/projects/{project_id}/training/start")
async def start_training(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Start FL training for a project.

    Tier enforcement: FREE users are capped at FREE_TIER_MAX_NODES (5) connected nodes.
    The coordinator is created with the capped config when ENFORCE_TIER_RESTRICTIONS=True.
    """
    project, coordinator = _get_project_and_coordinator(project_id, db, current_user)

    # Free-tier node cap: silently clamp numClients so training still starts
    if ENFORCE_TIER_RESTRICTIONS and current_user.subscription_tier != "PRO":
        config = project.config or {}
        if config.get("numClients", 0) > FREE_TIER_MAX_NODES:
            # Update the in-memory coordinator config and the DB record
            capped_config = {**config, "numClients": FREE_TIER_MAX_NODES}
            coordinator = create_coordinator(project_id, capped_config, ws_manager)
            project.config = capped_config
            db.commit()

    result = await coordinator.start()

    # Log activity
    log = ActivityLog(type="round_complete", project_id=project_id)
    db.add(log)
    db.commit()

    return result


@router.post("/projects/{project_id}/training/pause")
async def pause_training(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Pause FL training."""
    project, coordinator = _get_project_and_coordinator(project_id, db, current_user)
    return await coordinator.pause()


@router.post("/projects/{project_id}/training/resume")
async def resume_training(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Resume paused FL training."""
    project, coordinator = _get_project_and_coordinator(project_id, db, current_user)
    return await coordinator.resume()


@router.post("/projects/{project_id}/training/reset")
async def reset_training(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Reset training to round 0."""
    project, coordinator = _get_project_and_coordinator(project_id, db, current_user)
    return await coordinator.reset()


@router.get("/projects/{project_id}/training/status")
async def training_status(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get current training status."""
    coordinator = get_coordinator(project_id)
    if not coordinator:
        return {"status": "idle", "currentRound": 0, "totalRounds": 0}
    return coordinator.get_status()


@router.patch("/projects/{project_id}/config")
async def update_training_config(
    project_id: str,
    body: TrainingConfigUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update training configuration mid-training.

    Tier enforcement: switching to PRO-only aggregation methods (multi_krum,
    trimmed_mean, coordinate_median) requires PRO subscription.
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    updates = body.model_dump(exclude_none=True)

    # Block FREE users from selecting advanced aggregation methods
    requested_agg = updates.get("aggregationMethod")
    if requested_agg and requested_agg in PRO_ADVANCED_AGGREGATIONS:
        if ENFORCE_TIER_RESTRICTIONS and current_user.subscription_tier != "PRO":
            raise HTTPException(
                status_code=403,
                detail=f"Aggregation method '{requested_agg}' requires a Pro subscription.",
            )

    coordinator = get_coordinator(project_id)
    if coordinator:
        config = coordinator.update_config(updates)
    else:
        config = project.config or {}
        config.update(updates)

    # Persist config changes to DB
    db_config = project.config or {}
    db_config.update(updates)
    project.config = db_config
    db.commit()

    # Log activity
    log = ActivityLog(type="config_change", project_id=project_id)
    db.add(log)
    db.commit()

    return config


@router.post("/projects/{project_id}/nodes/{node_id}/block")
async def block_node(
    project_id: str,
    node_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_team_lead),
):
    """Block a node. Requires TEAM_LEAD role (RBAC only — not tier gated)."""
    coordinator = get_coordinator(project_id)
    if not coordinator:
        raise HTTPException(status_code=404, detail="No active training session")

    result = await coordinator.block_node(node_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Node not found")

    # Log activity
    log = ActivityLog(
        type="block", node_id=node_id,
        display_id=result.get("displayId"), project_id=project_id,
    )
    db.add(log)

    # Create notification for project creator
    project = db.query(Project).filter(Project.id == project_id).first()
    if project:
        notif = Notification(
            user_id=project.created_by,
            type="node_blocked",
            message=f"Node {result.get('displayId', node_id)} was blocked by {current_user.name}",
            project_id=project_id,
        )
        db.add(notif)

    db.commit()
    return result


@router.post("/projects/{project_id}/nodes/{node_id}/unblock")
async def unblock_node(
    project_id: str,
    node_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_team_lead),
):
    """Unblock a node. Requires TEAM_LEAD role (RBAC only — not tier gated)."""
    coordinator = get_coordinator(project_id)
    if not coordinator:
        raise HTTPException(status_code=404, detail="No active training session")

    result = await coordinator.unblock_node(node_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Node not found")

    # Log activity
    log = ActivityLog(
        type="unblock", node_id=node_id,
        display_id=result.get("displayId"), project_id=project_id,
    )
    db.add(log)
    db.commit()

    return result


@router.post("/projects/{project_id}/training/submit-update")
async def submit_gradient_update(
    project_id: str,
    body: GradientSubmission,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Submit a gradient update from a contributor node into the FL pipeline.

    FL data flow:
      contributor local training → L2 norm clipping → zero-sum masking
      → coordinator pending queue → aggregated on next round

    Only project members can submit. The submitted gradients (not the training
    code itself) enter the pipeline.  Trust scores and SABD results are NEVER
    returned to contributors — only the sanitised submission receipt.
    """
    # Verify the project exists
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Verify the caller is a member of this project
    membership = (
        db.query(ProjectMember)
        .filter(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == current_user.id,
        )
        .first()
    )
    if not membership:
        raise HTTPException(status_code=403, detail="You are not a member of this project")

    coordinator = get_coordinator(project_id)
    if not coordinator:
        raise HTTPException(status_code=400, detail="No active training session for this project")

    if coordinator.status not in ("running", "paused"):
        raise HTTPException(
            status_code=400,
            detail=f"Training is not active (status: {coordinator.status}). Start training first.",
        )

    # Resolve node ID from membership record; fall back to body-supplied ID
    node_id = membership.node_id or body.nodeId

    result = coordinator.submit_contributor_update(
        node_id=node_id,
        gradients=body.gradients,
        data_size=body.dataSize or 100,
    )

    # Strip internal fields — contributors must not see trust/SABD data
    return {
        "status": result["status"],
        "round": result.get("round"),
        "l2Norm": result.get("l2Norm"),
        "clippedNorm": result.get("clippedNorm"),
        "clipFactor": result.get("clipFactor"),
        "message": "Gradient update accepted and queued for aggregation.",
    }


@router.get("/projects/{project_id}/export")
async def export_metrics(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_team_lead_pro),
):
    """Export all round metrics as JSON. Requires TEAM_LEAD role + PRO tier (deep telemetry)."""
    coordinator = get_coordinator(project_id)
    if not coordinator:
        return []
    return coordinator.export_metrics()


# --------------------------------------------------------------------------
# WebSocket endpoint for frontend real-time events
# --------------------------------------------------------------------------

@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    projectId: str = Query(...),
    token: str = Query(default=""),
):
    """WebSocket for frontend clients to receive real-time training events.

    Connection: ws://backend/ws?projectId=<id>&token=<jwt>

    Events pushed:
      - round_complete: { metrics, nodes, ganttBlocks }
      - node_flagged: { nodeId, displayId, reason, cosineDistance, trust }
      - training_status: { status, currentRound, totalRounds }
    """
    await ws_manager.connect(websocket, projectId)

    try:
        # Send initial status
        coordinator = get_coordinator(projectId)
        if coordinator:
            await ws_manager.send_personal(websocket, "training_status", coordinator.get_status())
            # Send current nodes
            nodes = coordinator.node_manager.get_all_nodes_dict()
            if nodes:
                await ws_manager.send_personal(websocket, "initial_state", {
                    "nodes": nodes,
                    "metrics": coordinator.round_metrics[-10:] if coordinator.round_metrics else [],
                    "status": coordinator.get_status(),
                })

        # Keep connection alive — listen for client messages
        while True:
            try:
                data = await websocket.receive_text()
                # Client can send ping/pong or config updates
                import json
                msg = json.loads(data)
                if msg.get("type") == "ping":
                    await websocket.send_text('{"event":"pong"}')
            except WebSocketDisconnect:
                break
            except Exception:
                break
    finally:
        await ws_manager.disconnect(websocket, projectId)
