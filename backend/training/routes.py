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

from auth.dependencies import get_current_user, require_team_lead, require_team_lead_pro
from db.models import User, Project, ProjectMember, ActivityLog, Notification
from training.coordinator import get_coordinator, create_coordinator
from training.schemas import TrainingConfigUpdate, GradientSubmission
from ws.manager import ws_manager

# Tier enforcement constants (previously in auth.settings)
ENFORCE_TIER_RESTRICTIONS = True
FREE_TIER_MAX_NODES = 5
PRO_ADVANCED_AGGREGATIONS = {"multi_krum", "trimmed_mean", "coordinate_median"}

router = APIRouter()


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

async def _get_project_and_coordinator(project_id: str, current_user: User):
    """Get project from DB and its coordinator, creating one if needed."""
    project = await Project.find_one(Project.id == project_id)
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
    current_user: User = Depends(get_current_user),
):
    """Start FL training for a project.

    Tier enforcement: FREE users are capped at FREE_TIER_MAX_NODES (5) connected nodes.
    The coordinator is created with the capped config when ENFORCE_TIER_RESTRICTIONS=True.
    """
    project, coordinator = await _get_project_and_coordinator(project_id, current_user)

    # Free-tier node cap: silently clamp numClients so training still starts
    tier = getattr(current_user, "subscription_tier", None)
    if ENFORCE_TIER_RESTRICTIONS and tier != "PRO":
        config = project.config or {}
        if config.get("numClients", 0) > FREE_TIER_MAX_NODES:
            capped_config = {**config, "numClients": FREE_TIER_MAX_NODES}
            coordinator = create_coordinator(project_id, capped_config, ws_manager)
            project.config = capped_config
            await project.save()

    result = await coordinator.start()

    # Log activity
    log = ActivityLog(type="round_complete", project_id=project_id)
    await log.insert()

    return result


@router.post("/projects/{project_id}/training/pause")
async def pause_training(
    project_id: str,
    current_user: User = Depends(get_current_user),
):
    """Pause FL training."""
    project, coordinator = await _get_project_and_coordinator(project_id, current_user)
    return await coordinator.pause()


@router.post("/projects/{project_id}/training/resume")
async def resume_training(
    project_id: str,
    current_user: User = Depends(get_current_user),
):
    """Resume paused FL training."""
    project, coordinator = await _get_project_and_coordinator(project_id, current_user)
    return await coordinator.resume()


@router.post("/projects/{project_id}/training/reset")
async def reset_training(
    project_id: str,
    current_user: User = Depends(get_current_user),
):
    """Reset training to round 0."""
    project, coordinator = await _get_project_and_coordinator(project_id, current_user)
    return await coordinator.reset()


@router.get("/projects/{project_id}/training/status")
async def training_status(
    project_id: str,
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
    current_user: User = Depends(get_current_user),
):
    """Update training configuration mid-training.

    Tier enforcement: switching to PRO-only aggregation methods (multi_krum,
    trimmed_mean, coordinate_median) requires PRO subscription.
    """
    project = await Project.find_one(Project.id == project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    updates = body.model_dump(exclude_none=True)

    # Block FREE users from selecting advanced aggregation methods
    requested_agg = updates.get("aggregationMethod")
    tier = getattr(current_user, "subscription_tier", None)
    if requested_agg and requested_agg in PRO_ADVANCED_AGGREGATIONS:
        if ENFORCE_TIER_RESTRICTIONS and tier != "PRO":
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
    await project.save()

    # Log activity
    log = ActivityLog(type="config_change", project_id=project_id)
    await log.insert()

    return config


@router.post("/projects/{project_id}/nodes/{node_id}/block")
async def block_node(
    project_id: str,
    node_id: str,
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
    await log.insert()

    # Create notification for project creator
    project = await Project.find_one(Project.id == project_id)
    if project:
        notif = Notification(
            user_id=project.created_by,
            type="node_blocked",
            message=f"Node {result.get('displayId', node_id)} was blocked by {current_user.name}",
            project_id=project_id,
        )
        await notif.insert()

    return result


@router.post("/projects/{project_id}/nodes/{node_id}/unblock")
async def unblock_node(
    project_id: str,
    node_id: str,
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
    await log.insert()

    return result


@router.post("/projects/{project_id}/training/submit-update")
async def submit_gradient_update(
    project_id: str,
    body: GradientSubmission,
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
    project = await Project.find_one(Project.id == project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Verify the caller is a member of this project
    membership = await ProjectMember.find_one(
        ProjectMember.project_id == project_id,
        ProjectMember.user_id == current_user.id,
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
    current_user: User = Depends(require_team_lead_pro),
):
    """Export all round metrics as JSON. Requires TEAM_LEAD role + PRO tier (deep telemetry)."""
    coordinator = get_coordinator(project_id)
    if not coordinator:
        return []
    return coordinator.export_metrics()


# --------------------------------------------------------------------------
# WebSocket endpoint — dashboard viewers AND FL training clients
# --------------------------------------------------------------------------

@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    projectId: str = Query(...),
    token: str = Query(default=""),
    clientId: str = Query(default=""),
    task: str = Query(default=""),
):
    """Unified WebSocket endpoint for two client types.

    Dashboard viewers (no clientId):
      Connection: ws://backend/ws?projectId=<id>&token=<jwt>
      Receive: round_complete, node_flagged, training_status, trust_report, global_model

    FL training clients (clientId provided):
      Connection: ws://backend/ws?projectId=<id>&clientId=<id>&task=<task>&token=<jwt>
      Send:    weight_update  — local training result (base64 msgpack weights)
      Receive: global_model   — aggregated model after each round
               trust_report  — trust scores, rejected lists
               rejected       — directed rejection message (Layer 1 gatekeeper)

    Client limit: at most MAX_FL_CLIENTS (10) FL clients per project.
    Connections beyond the limit are closed immediately with code 1008.
    """
    import json
    from training.fl_processor import get_fl_processor

    is_fl_client = bool(clientId)

    # --- Enforce FL client limit before accepting ---
    if is_fl_client and ws_manager.get_fl_client_count(projectId) >= 10:
        await websocket.accept()
        await websocket.close(code=1008, reason="Client limit reached (max 10 FL clients)")
        return

    await ws_manager.connect(websocket, projectId)

    # Register as FL client (second limit check inside the lock)
    if is_fl_client:
        registered = await ws_manager.register_fl_client(clientId, projectId, websocket)
        if not registered:
            await ws_manager.disconnect(websocket, projectId)
            await websocket.close(code=1008, reason="Client limit reached (max 10 FL clients)")
            return

    try:
        coordinator = get_coordinator(projectId)
        if not coordinator:
            coordinator = create_coordinator(projectId, {}, ws_manager)

        # Send initial state to dashboard viewers
        if not is_fl_client:
            await ws_manager.send_personal(websocket, "training_status", coordinator.get_status())
            nodes = coordinator.node_manager.get_all_nodes_dict()
            if nodes:
                await ws_manager.send_personal(websocket, "initial_state", {
                    "nodes": nodes,
                    "metrics": coordinator.round_metrics[-10:] if coordinator.round_metrics else [],
                    "status": coordinator.get_status(),
                })

        # Keep connection alive — process incoming messages
        while True:
            try:
                data = await websocket.receive_text()
                msg = json.loads(data)
                msg_type = msg.get("type")

                if msg_type == "ping":
                    await websocket.send_text('{"event":"pong"}')

                elif msg_type == "weight_update":
                    await _handle_weight_update(
                        websocket=websocket,
                        project_id=projectId,
                        msg=msg,
                        coordinator=coordinator,
                        task=task or msg.get("task", ""),
                    )

            except WebSocketDisconnect:
                break
            except Exception:
                break

    finally:
        if is_fl_client:
            await ws_manager.unregister_fl_client(clientId, projectId)
        await ws_manager.disconnect(websocket, projectId)


async def _handle_weight_update(
    websocket,
    project_id: str,
    msg: dict,
    coordinator,
    task: str,
) -> None:
    """Process an incoming weight_update message through the defense pipeline.

    Layer 1 (L2 Norm Gatekeeper) runs immediately — rejected updates receive a
    `rejected` directed message and are dropped.  Updates that pass Layer 1 are
    queued in the FLWeightProcessor pending list; Layer 2 (SABD) and aggregation
    run at the next round boundary inside the coordinator's training loop.
    """
    import json
    from training.fl_processor import get_fl_processor

    client_id = msg.get("client_id", "unknown")
    round_num = int(msg.get("round_num", 0))

    processor = get_fl_processor(project_id, coordinator.config)
    result = processor.process_weight_update(msg)

    if result["status"] == "rejected_l1":
        rejected_msg = processor.build_rejected_msg(
            client_id=client_id,
            task=task,
            round_num=round_num,
            norm=result["norm"],
            threshold=result["threshold"],
        )
        try:
            await websocket.send_text(json.dumps(rejected_msg))
        except Exception:
            pass
