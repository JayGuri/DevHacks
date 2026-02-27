# main.py — FastAPI entrypoint: WebSocket, REST, SSE, startup
import os
import sys
from dotenv import load_dotenv

env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
if os.path.exists(env_path):
    load_dotenv(env_path, override=True)

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
# from data.shakespeare_loader import ShakespearePartitioner  # Not needed for MNIST MongoDB test
from server.model_history import ModelHistory
from server.fl_server import (
    verify_token,
    connected_clients,
    require_role,
    AsyncBuffer,
    handle_websocket,
    heartbeat_checker,
    update_client_trust,
    send_global_model_message,
)
from server.node_registry import NodeRegistry
from aggregation.aggregator import Aggregator
from server.chunk_manager import ChunkManager
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
chunk_manager: ChunkManager = None   # MongoDB-backed chunk registry
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

    # Emit aggregation_triggered event for realtime CLI dashboard
    await emit_event("aggregation_triggered", {
        "task": task,
        "round": current_round + 1,
        "updates_count": len(updates),
        "active_clients": active_count,
        "strategy": settings.AGGREGATION_STRATEGY,
    })

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

        # Emit trust scores and persist to connected_clients state
        for client_id, score in result.trust_scores.items():
            await emit_event("trust_score", {
                "client_id": client_id,
                "task": task,
                "score": score,
                "round": new_round,
            })
            update_client_trust(client_id, score)
            logger.info(
                "Trust score: client=%s, task=%s, round=%d, trust=%.4f",
                client_id, task, new_round, score,
            )

        if result.trust_scores:
            scores_summary = ", ".join(
                f"{cid}: {s:.2f}" for cid, s in result.trust_scores.items()
            )
            logger.info(
                "Trust summary: task=%s, round=%d, scores={%s}",
                task, new_round, scores_summary,
            )

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
        # Build trust report to send alongside the global model
        trust_report_msg = {
            "type": "trust_report",
            "task": task,
            "round": new_round,
            "trust_scores": result.trust_scores,
            "staleness_values": staleness_values,
            "staleness_weights": staleness_weights_map,
            "rejected_clients": result.rejected_clients,
            "gatekeeper_rejected": result.gatekeeper_rejected,
        }
        for cid, client_info in list(connected_clients.items()):
            if client_info.get("task") == task:
                try:
                    await send_global_model_message(
                        client_info["websocket"],
                        task=task,
                        round_num=latest["round"],
                        weights=latest["weights"],
                        version=latest["version"],
                        timestamp=latest["timestamp"],
                        assigned_chunk=client_info.get("chunk_id", -1),
                        client_id=cid,
                    )
                    await client_info["websocket"].send_json(trust_report_msg)
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
    global model_history, fl_buffer, aggregator, _test_dataloaders, network_simulator, node_registry, chunk_manager

    logger.info("FedBuff server starting up...")

    # Step 1: Initialize JWT and NodeRegistry
    # JWT_SECRET is read from environment by core.jwt_auth (via .env)
    logger.info("JWT auth via core.jwt_auth (JWT_SECRET from environment)")

    node_registry = NodeRegistry(
        registry_file=settings.NODE_REGISTRY_FILE,
        jwt_secret=settings.JWT_SECRET,
        max_nodes_per_task=settings.MAX_NODES_PER_TASK,
    )
    # Clear stale nodes from previous sessions so slots are freed.
    # In-memory connected_clients is already empty on startup, so old registry
    # entries are orphaned and would permanently block new registrations.
    node_registry.clear_all()
    logger.info(
        "NodeRegistry initialized: file=%s, max_nodes_per_task=%d, existing_nodes=%d",
        settings.NODE_REGISTRY_FILE,
        settings.MAX_NODES_PER_TASK,
        len(node_registry.list_nodes()),
    )

    # Step 1b: Initialize ChunkManager (MongoDB-backed chunk tracking)
    mongo_uri = os.environ.get("MONGO_URI", "")
    mongo_db = os.environ.get("MONGO_DB", "fedbuff_db")
    if mongo_uri:
        chunk_manager = ChunkManager(
            mongo_uri=mongo_uri,
            db_name=mongo_db,
            total_chunks=settings.MAX_NODES_PER_TASK,
            max_clients=settings.MAX_NODES_PER_TASK,
        )
        logger.info(
            "ChunkManager initialised: total=%d, available=%d",
            chunk_manager.total_chunks, chunk_manager.available_count,
        )
    else:
        chunk_manager = None
        logger.info("ChunkManager skipped (MONGO_URI not set) — chunk tracking disabled.")

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
            chunk_manager=chunk_manager,
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

# CORS — restrict origins to configured whitelist (fixes wildcard + credentials vuln)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
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
                           network_simulator=network_simulator,
                           chunk_manager=chunk_manager)


# --- REST endpoints ---
@app.get("/health")
async def health():
    """Health check endpoint."""
    tasks_info = {}
    for task in settings.SUPPORTED_TASKS:
        task_clients = [
            cid for cid, info in connected_clients.items()
            if info.get("task") == task
        ]
        trust_map = {}
        if aggregator is not None:
            trust_map = {
                cid: aggregator._trust_history[cid]
                for cid in task_clients
                if cid in aggregator._trust_history
            }
        avg_trust = (sum(trust_map.values()) / len(trust_map)) if trust_map else None
        tasks_info[task] = {
            "round": model_history.get_round(task) if model_history else 0,
            "buffer_size": fl_buffer.size(task) if fl_buffer else 0,
            "trust_scores": trust_map,
            "avg_trust": round(avg_trust, 4) if avg_trust is not None else None,
        }

    result = {
        "status": "ok",
        "tasks": tasks_info,
        "connected_clients": len(connected_clients),
    }

    if chunk_manager is not None:
        result["chunks"] = chunk_manager.status_summary

    return result


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

    # Security: whitelist allowed roles to prevent privilege escalation
    if role not in settings.ALLOWED_REGISTRATION_ROLES:
        return JSONResponse(
            status_code=400,
            content={"error": f"Invalid role: {role}. Allowed: {settings.ALLOWED_REGISTRATION_ROLES}"},
        )

    # Security: validate attack parameters
    VALID_ATTACK_TYPES = {"sign_flip_amplified", "sign_flipping", "gaussian_noise", "label_flip", None}
    if attack_type not in VALID_ATTACK_TYPES:
        return JSONResponse(
            status_code=400,
            content={"error": f"Invalid attack_type: {attack_type}. Allowed: {VALID_ATTACK_TYPES - {None}}"},
        )
    if attack_scale is not None:
        try:
            attack_scale = float(attack_scale)
            attack_scale = max(-100.0, min(100.0, attack_scale))
        except (TypeError, ValueError):
            return JSONResponse(
                status_code=400, content={"error": "attack_scale must be a number in [-100, 100]"},
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
async def list_nodes(task: str = Query(default=None), payload: dict = Depends(require_role("server"))):
    """List all registered nodes, optionally filtered by task. Requires server role."""
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
            "chunk_id": info.get("chunk_id", -1),
            "connected_at": info["connected_at"],
            "trust_score": info.get("trust_score"),
            "trust_updated_at": info.get("trust_updated_at"),
        })
    return {"clients": clients_list, "count": len(clients_list)}


@app.get("/trust/scores")
async def trust_scores(task: str = Query(default=None)):
    """Return per-client trust scores from the aggregator trust history.

    Optional ?task= filter returns only clients registered for that task.
    """
    if aggregator is None:
        return JSONResponse(status_code=503, content={"error": "Aggregator not initialised"})

    scores = dict(aggregator._trust_history)

    if task is not None:
        if task not in settings.SUPPORTED_TASKS:
            return JSONResponse(
                status_code=400,
                content={"error": f"Unsupported task: {task}. Supported: {settings.SUPPORTED_TASKS}"},
            )
        task_clients = {
            cid for cid, info in connected_clients.items()
            if info.get("task") == task
        }
        scores = {cid: s for cid, s in scores.items() if cid in task_clients}

    return {
        "trust_scores": scores,
        "round": model_history.get_round(task) if (task and model_history) else None,
        "task": task,
    }


@app.get("/chunks/status")
async def chunks_status():
    """Return chunk assignment status (available / in_use for each chunk)."""
    if chunk_manager is None:
        return JSONResponse(
            status_code=503,
            content={"error": "ChunkManager not initialised (MONGO_URI not set)"},
        )
    summary = chunk_manager.status_summary
    # Add per-chunk detail
    chunks_detail = []
    for cid in range(chunk_manager.total_chunks):
        info = chunk_manager.get_chunk_info(cid)
        if info:
            info.pop("_id", None)
            chunks_detail.append(info)
    summary["chunks"] = chunks_detail
    return summary


@app.get("/chunks/{chunk_id}")
async def chunk_detail(chunk_id: int):
    """Return detailed info for a single chunk."""
    if chunk_manager is None:
        return JSONResponse(
            status_code=503,
            content={"error": "ChunkManager not initialised (MONGO_URI not set)"},
        )
    info = chunk_manager.get_chunk_info(chunk_id)
    if info is None:
        return JSONResponse(status_code=404, content={"error": f"Chunk {chunk_id} not found"})
    info.pop("_id", None)
    return info


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
        ws="wsproto",  # Use wsproto instead of websockets — avoids legacy protocol's concurrent-write AssertionError when proxy PINGs arrive during chunk delivery
        ws_ping_interval=None,  # Disabled — no server pings; avoids write contention
        ws_ping_timeout=None,   # Disabled — no server-initiated pings to timeout
        ws_max_size=2**28,  # 256 MB — compressed weights are much smaller
    )
