# main.py — FastAPI entrypoint: WebSocket, REST, SSE, startup
import os
import sys
import json
import asyncio
import logging
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import numpy as np
import torch
from fastapi import FastAPI, WebSocket, Query, Depends, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

from config import settings
from models.cnn import get_model, evaluate_model
from models.lstm import evaluate_text_model
from data.shakespeare_loader import ShakespearePartitioner
from server.model_history import ModelHistory
from server.fl_server import (
    load_users,
    init_jwt,
    verify_token,
    connected_clients,
    require_role,
    AsyncBuffer,
    handle_websocket,
    heartbeat_checker,
)
from server.node_registry import NodeRegistry
from aggregation.aggregator import Aggregator
from evaluation.metrics import (
    emit_event,
    subscribe_sse,
    unsubscribe_sse,
    fl_aggregation_duration,
)

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(name)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("fedbuff.main")

# Global state
model_history: ModelHistory = None
fl_buffer: AsyncBuffer = None
aggregator: Aggregator = None
network_simulator = None   # NetworkSimulator | None
node_registry: NodeRegistry = None
# Test DataLoaders for server-side evaluation (loaded once at startup)
_test_dataloaders: dict = {}   # task -> DataLoader | None
_eval_device: str = "cpu"


async def aggregation_callback(updates: list, task: str) -> None:
    """Called by AsyncBuffer.buffer_watcher when a task buffer fills."""
    global model_history, aggregator, _test_dataloaders, _eval_device

    start_time = time.time()
    current_round = model_history.get_round(task)

    # MIN_CLIENTS gate: don't aggregate if too few active (non-joining) clients
    active_count = sum(
        1 for info in connected_clients.values()
        if info.get("task") == task and not info.get("is_joining", False)
    )
    if len(updates) < settings.MIN_CLIENTS_FOR_AGGREGATION:
        logger.warning(
            "Skipping aggregation: updates=%d < min=%d, task=%s. Re-queuing.",
            len(updates), settings.MIN_CLIENTS_FOR_AGGREGATION, task,
        )
        for u in updates:
            await fl_buffer.queues[task].put(u)
            fl_buffer._queued_clients[task].add(u.get("client_id", "unknown"))
        return

    logger.info(
        "Aggregation triggered: task=%s, round=%d, updates=%d, active_clients=%d",
        task, current_round + 1, len(updates), active_count,
    )

    # Run aggregation
    result = aggregator.aggregate(updates, current_round, task)

    if result.aggregated_weights:
        # Compute average loss from accepted updates
        avg_loss = np.mean([u["local_loss"] for u in updates]) if updates else 0.0

        # Update model history
        model_history.update(task, result.aggregated_weights, avg_loss)
        new_round = model_history.get_round(task)

        duration = time.time() - start_time
        fl_aggregation_duration.labels(task=task).observe(duration)

        # Emit round_complete event
        await emit_event("round_complete", {
            "task": task,
            "round": new_round,
            "loss": avg_loss,
            "accepted_count": result.accepted_count,
            "gatekeeper_rejected": result.gatekeeper_rejected,
            "rejected_clients": result.rejected_clients,
            "strategy": result.strategy_used,
            "duration": round(duration, 4),
        })

        # Emit trust scores
        for client_id, score in result.trust_scores.items():
            await emit_event("trust_score", {
                "client_id": client_id,
                "task": task,
                "score": score,
                "round": new_round,
            })

        # Emit per-client staleness report
        staleness_values = result.metadata.get("staleness_values", {})
        staleness_weights_map = result.metadata.get("staleness_weights", {})
        if staleness_values:
            await emit_event("staleness_report", {
                "task": task,
                "round": new_round,
                "staleness_values": staleness_values,
                "staleness_weights": staleness_weights_map,
            })

        # Broadcast updated global model to all connected clients for this task
        latest = model_history.get_latest(task)
        global_model_msg = {
            "type": "global_model",
            "task": task,
            "round_num": latest["round"],
            "weights": latest["weights"],
            "version": latest["version"],
            "timestamp": latest["timestamp"],
            "personalization_alpha": settings.PERSONALIZATION_ALPHA if settings.PERSONALIZATION_ENABLED else 0.0,
        }
        for cid, client_info in list(connected_clients.items()):
            if client_info.get("task") == task:
                try:
                    await client_info["websocket"].send_json(global_model_msg)
                except Exception as e:
                    logger.warning("Failed to send global model to %s: %s", cid, e)

        logger.info(
            "Aggregation complete: task=%s, round=%d, loss=%.6f, "
            "accepted=%d, duration=%.4fs",
            task, new_round, avg_loss, result.accepted_count, duration,
        )

        # Server-side model evaluation on held-out test set
        test_dl = _test_dataloaders.get(task)
        if test_dl is not None:
            try:
                eval_model = get_model(task)
                # Load aggregated weights into eval model
                state = {
                    k: torch.tensor(v, dtype=torch.float32)
                    for k, v in result.aggregated_weights.items()
                }
                eval_model.load_state_dict(state, strict=False)
                eval_model.to(_eval_device)

                if task == "shakespeare":
                    char_acc, eval_loss, perplexity = evaluate_text_model(
                        eval_model, test_dl, _eval_device
                    )
                    await emit_event("eval_metrics", {
                        "task": task,
                        "round": new_round,
                        "char_accuracy": round(char_acc, 6),
                        "loss": round(eval_loss, 6),
                        "perplexity": round(perplexity, 4),
                    })
                    logger.info(
                        "Shakespeare eval: round=%d, char_acc=%.4f, perplexity=%.4f",
                        new_round, char_acc, perplexity,
                    )
                else:
                    accuracy, eval_loss = evaluate_model(
                        eval_model, test_dl, _eval_device
                    )
                    await emit_event("eval_metrics", {
                        "task": task,
                        "round": new_round,
                        "accuracy": round(accuracy, 6),
                        "loss": round(eval_loss, 6),
                    })
                    logger.info(
                        "FEMNIST eval: round=%d, accuracy=%.4f",
                        new_round, accuracy,
                    )
            except Exception as exc:
                logger.warning("Server-side eval failed for %s: %s", task, exc)
    else:
        logger.warning(
            "Aggregation produced no weights: task=%s, round=%d", task, current_round
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle handler."""
    global model_history, fl_buffer, aggregator, _test_dataloaders, network_simulator, node_registry

    logger.info("FedBuff server starting up...")

    # Step 1: Initialize JWT and NodeRegistry (replaces legacy load_users)
    if settings.JWT_SECRET:
        init_jwt(settings.JWT_SECRET)
        logger.info("JWT initialized from settings.JWT_SECRET")
    else:
        # Fallback for backwards compatibility — try legacy users.json
        try:
            load_users(settings.USERS_FILE)
            logger.warning("Loaded JWT from legacy users.json — migrate to setup_server.py")
        except Exception as e:
            logger.warning("No JWT_SECRET configured and no users.json: %s", e)

    node_registry = NodeRegistry(
        registry_file=settings.NODE_REGISTRY_FILE,
        jwt_secret=settings.JWT_SECRET,
        max_nodes_per_task=settings.MAX_NODES_PER_TASK,
    )
    logger.info(
        "NodeRegistry initialized: file=%s, max_nodes_per_task=%d, existing_nodes=%d",
        settings.NODE_REGISTRY_FILE,
        settings.MAX_NODES_PER_TASK,
        len(node_registry.list_nodes()),
    )

    # Step 2: Instantiate ModelHistory with initial models
    models = {
        "femnist": get_model("femnist"),
        "shakespeare": get_model("shakespeare"),
    }
    model_history = ModelHistory(models, settings.MODEL_CHECKPOINT_DIR)

    # Step 3: Instantiate Aggregator
    aggregator = Aggregator(settings.AGGREGATION_STRATEGY, settings)

    # Step 4: Instantiate AsyncBuffer with event-driven + staleness params
    fl_buffer = AsyncBuffer(
        buffer_size_k=settings.BUFFER_SIZE_K,
        supported_tasks=settings.SUPPORTED_TASKS,
        aggregation_callback=aggregation_callback,
        get_current_round=model_history.get_round,
        max_staleness=settings.MAX_STALENESS,
        min_updates=settings.MIN_UPDATES_FOR_AGGREGATION,
        max_wait_seconds=settings.MAX_WAIT_SECONDS,
        max_updates_per_batch=settings.MAX_UPDATES_PER_BATCH,
    )
    watcher_task = asyncio.create_task(fl_buffer.buffer_watcher())

    # Step 4b: Start heartbeat checker for client dropout detection
    heartbeat_task = asyncio.create_task(
        heartbeat_checker(
            fl_buffer,
            timeout=settings.CLIENT_HEARTBEAT_TIMEOUT,
            check_interval=settings.HEARTBEAT_CHECK_INTERVAL,
        )
    )

    # Step 4c: Instantiate network simulator if enabled
    if settings.NETWORK_SIMULATION_ENABLED:
        from network.simulator import NetworkSimulator
        network_simulator = NetworkSimulator(
            packet_loss_prob=settings.PACKET_LOSS_PROB,
            min_latency_ms=settings.MIN_LATENCY_MS,
            max_latency_ms=settings.MAX_LATENCY_MS,
            partition_enabled=settings.NETWORK_PARTITION_ENABLED,
            partition_clients=settings.PARTITION_CLIENTS,
        )
        logger.info("Network simulator enabled (loss=%.2f%%)", settings.PACKET_LOSS_PROB * 100)
    else:
        network_simulator = None

    # Step 5: Create results/checkpoints directory
    os.makedirs(settings.MODEL_CHECKPOINT_DIR, exist_ok=True)
    os.makedirs(settings.RESULTS_DIR, exist_ok=True)

    # Step 6: Load server-side test DataLoaders for evaluation
    # Shakespeare — load from raw text file (held-out last 10% of corpus)
    try:
        shk_partitioner = ShakespearePartitioner(seq_length=80)
        shk_text = shk_partitioner.load_dataset()
        shk_partitioner.build_vocabulary(shk_text)
        # Hold out last 10% of text as server test set
        holdout_start = int(len(shk_text) * 0.9)
        shk_test_dl = shk_partitioner.get_test_dataloader(
            shk_text[holdout_start:], batch_size=256
        )
        _test_dataloaders["shakespeare"] = shk_test_dl
        logger.info(
            "Shakespeare test set loaded: %d chars, %d batches",
            len(shk_text) - holdout_start, len(shk_test_dl),
        )
    except Exception as exc:
        logger.warning("Could not load Shakespeare test data: %s", exc)
        _test_dataloaders["shakespeare"] = None

    logger.info(
        "FedBuff server ready: host=%s, port=%d, strategy=%s, buffer_k=%d",
        settings.SERVER_HOST, settings.SERVER_PORT,
        settings.AGGREGATION_STRATEGY, settings.BUFFER_SIZE_K,
    )

    yield

    # Shutdown
    watcher_task.cancel()
    heartbeat_task.cancel()
    try:
        await asyncio.gather(watcher_task, heartbeat_task, return_exceptions=True)
    except asyncio.CancelledError:
        pass
    logger.info("FedBuff server shutting down.")


# Create FastAPI app
app = FastAPI(
    title="FedBuff — Buffered Async Federated Learning",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- WebSocket endpoint ---
@app.websocket("/ws/fl")
async def websocket_fl(
    websocket: WebSocket,
    token: str = Query(...),
    task: str = Query(...),
):
    """WebSocket endpoint for FL clients."""
    await websocket.accept()

    if task not in settings.SUPPORTED_TASKS:
        await websocket.close(code=1008, reason=f"Unsupported task: {task}")
        return

    await handle_websocket(websocket, token, task, fl_buffer, model_history, settings,
                           network_simulator=network_simulator)


# --- REST endpoints ---
@app.get("/health")
async def health():
    """Health check endpoint."""
    tasks_info = {}
    for task in settings.SUPPORTED_TASKS:
        tasks_info[task] = {
            "round": model_history.get_round(task) if model_history else 0,
            "buffer_size": fl_buffer.size(task) if fl_buffer else 0,
        }

    return {
        "status": "ok",
        "tasks": tasks_info,
        "connected_clients": len(connected_clients),
    }


@app.get("/model/latest")
async def get_latest_model(task: str = Query(...)):
    """Get the latest model weights for a specific task."""
    if task not in settings.SUPPORTED_TASKS:
        return JSONResponse(
            status_code=400,
            content={"error": f"Unsupported task: {task}"},
        )
    if not model_history:
        return JSONResponse(
            status_code=503,
            content={"error": "Model history not initialized"},
        )
    return model_history.get_latest(task)


@app.get("/metrics")
async def prometheus_metrics():
    """Prometheus scrape endpoint."""
    return StreamingResponse(
        iter([generate_latest()]),
        media_type=CONTENT_TYPE_LATEST,
    )


@app.post("/nodes/register")
async def register_node(body: dict):
    """Register a new dynamic FL node. Returns node credentials and JWT token."""
    task = body.get("task")
    role = body.get("role", "legitimate_client")
    display_name = body.get("display_name", "Node")
    attack_type = body.get("attack_type")
    attack_scale = body.get("attack_scale")

    if not task:
        return JSONResponse(status_code=400, content={"error": "task is required"})
    if task not in settings.SUPPORTED_TASKS:
        return JSONResponse(
            status_code=400,
            content={"error": f"Unsupported task: {task}. Supported: {settings.SUPPORTED_TASKS}"},
        )

    try:
        result = node_registry.register(
            task=task,
            role=role,
            display_name=display_name,
            attack_type=attack_type,
            attack_scale=attack_scale,
        )
        return result
    except ValueError as e:
        return JSONResponse(status_code=409, content={"error": str(e)})


@app.get("/nodes")
async def list_nodes(task: str = Query(default=None)):
    """List all registered nodes, optionally filtered by task."""
    nodes = node_registry.list_nodes(task=task)
    return {"nodes": nodes, "count": len(nodes)}


@app.get("/admin/clients")
async def admin_clients(payload: dict = Depends(require_role("server"))):
    """List all connected clients. Requires server role."""
    clients_list = []
    for cid, info in connected_clients.items():
        clients_list.append({
            "client_id": cid,
            "display_name": info["display_name"],
            "role": info["role"],
            "participant": info["participant"],
            "task": info["task"],
            "connected_at": info["connected_at"],
        })
    return {"clients": clients_list, "count": len(clients_list)}


@app.get("/telemetry/stream")
async def telemetry_stream():
    """SSE endpoint — streams all events from evaluation/metrics.py."""
    queue = await subscribe_sse()

    async def event_generator():
        try:
            while True:
                try:
                    event_data = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield f"data: {event_data}\n\n"
                except asyncio.TimeoutError:
                    # Send keepalive
                    yield f": keepalive\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            await unsubscribe_sse(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.SERVER_HOST,
        port=settings.SERVER_PORT,
        log_level=settings.LOG_LEVEL.lower(),
        ws_ping_interval=20,
        ws_ping_timeout=20,
    )
