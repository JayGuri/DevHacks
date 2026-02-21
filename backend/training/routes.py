# backend/training/routes.py — FL Training control API + WebSocket endpoint
"""
POST   /api/projects/:id/training/start    → Start training
POST   /api/projects/:id/training/pause    → Pause
POST   /api/projects/:id/training/resume   → Resume
POST   /api/projects/:id/training/reset    → Reset to round 0
PATCH  /api/projects/:id/config            → Update config mid-training
POST   /api/projects/:id/nodes/:nodeId/block   → Block node
POST   /api/projects/:id/nodes/:nodeId/unblock → Unblock node
GET    /api/projects/:id/export            → Download round metrics JSON
GET    /api/projects/:id/training/status   → Current training status
WS     /ws                                 → WebSocket for frontend real-time events
"""

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, Query
from sqlalchemy.orm import Session

from auth.dependencies import get_current_user
from db.database import get_db
from db.models import User, Project, ActivityLog, Notification
from training.coordinator import get_coordinator, create_coordinator
from training.schemas import TrainingConfigUpdate
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
    """Start FL training for a project."""
    project, coordinator = _get_project_and_coordinator(project_id, db, current_user)
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
    """Update training configuration mid-training."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    updates = body.model_dump(exclude_none=True)
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
    current_user: User = Depends(get_current_user),
):
    """Admin blocks a node."""
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
    current_user: User = Depends(get_current_user),
):
    """Admin unblocks a node."""
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


@router.get("/projects/{project_id}/export")
async def export_metrics(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Export all round metrics as JSON for download."""
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
