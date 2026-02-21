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
from fastapi import FastAPI, WebSocket, Query, Depends, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

from config import settings
from models.cnn import get_model
from server.model_history import ModelHistory
from server.fl_server import (
    load_users,
    verify_token,
    connected_clients,
    require_role,
    AsyncBuffer,
    handle_websocket,
)
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


async def aggregation_callback(updates: list, task: str) -> None:
    """Called by AsyncBuffer.buffer_watcher when a task buffer fills."""
    global model_history, aggregator

    start_time = time.time()
    current_round = model_history.get_round(task)

    logger.info(
        "Aggregation triggered: task=%s, round=%d, updates=%d",
        task, current_round + 1, len(updates),
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

        # Broadcast updated global model to all connected clients for this task
        latest = model_history.get_latest(task)
        global_model_msg = {
            "type": "global_model",
            "task": task,
            "round_num": latest["round"],
            "weights": latest["weights"],
            "version": latest["version"],
            "timestamp": latest["timestamp"],
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
    else:
        logger.warning(
            "Aggregation produced no weights: task=%s, round=%d", task, current_round
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle handler."""
    global model_history, fl_buffer, aggregator

    logger.info("FedBuff server starting up...")

    # Step 1: Load users
    try:
        load_users(settings.USERS_FILE)
    except FileNotFoundError:
        logger.warning(
            "Users file not found: %s. Run scripts/create_users.py first.",
            settings.USERS_FILE,
        )
    except Exception as e:
        logger.error("Failed to load users: %s", e)

    # Step 2: Instantiate ModelHistory with initial models
    models = {
        "femnist": get_model("femnist"),
        "shakespeare": get_model("shakespeare"),
    }
    model_history = ModelHistory(models, settings.MODEL_CHECKPOINT_DIR)

    # Step 3: Instantiate Aggregator
    aggregator = Aggregator(settings.AGGREGATION_STRATEGY, settings)

    # Step 4: Instantiate AsyncBuffer and start buffer watcher
    fl_buffer = AsyncBuffer(
        settings.BUFFER_SIZE_K, settings.SUPPORTED_TASKS, aggregation_callback
    )
    watcher_task = asyncio.create_task(fl_buffer.buffer_watcher())

    # Step 5: Create results/checkpoints directory
    os.makedirs(settings.MODEL_CHECKPOINT_DIR, exist_ok=True)
    os.makedirs(settings.RESULTS_DIR, exist_ok=True)

    logger.info(
        "FedBuff server ready: host=%s, port=%d, strategy=%s, buffer_k=%d",
        settings.SERVER_HOST, settings.SERVER_PORT,
        settings.AGGREGATION_STRATEGY, settings.BUFFER_SIZE_K,
    )

    yield

    # Shutdown
    watcher_task.cancel()
    try:
        await watcher_task
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

    await handle_websocket(websocket, token, task, fl_buffer, model_history, settings)


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
