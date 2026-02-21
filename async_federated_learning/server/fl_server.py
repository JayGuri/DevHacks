# server/fl_server.py — Connection manager, task-aware async buffer, WebSocket router
import asyncio
import json
import time
import logging
from datetime import datetime, timezone

import jwt
import numpy as np
from fastapi import HTTPException

from detection.anomaly import check_l2_norm

logger = logging.getLogger("fedbuff.server")

# Module-level auth state
_jwt_secret: str = None
_user_registry: dict = {}
connected_clients: dict = {}
# {client_id: {"websocket": ws, "role": str, "display_name": str,
#              "participant": str, "task": str, "connected_at": float}}


def load_users(filepath: str) -> None:
    """Reads users.json, stores jwt_secret and user registry in module state."""
    global _jwt_secret, _user_registry
    with open(filepath, "r") as f:
        data = json.load(f)
    _jwt_secret = data["jwt_secret"]
    _user_registry = data["users"]
    logger.info("Loaded %d users from %s", len(_user_registry), filepath)


def verify_token(token: str) -> dict:
    """Decodes and validates JWT. Raises HTTPException(403) on failure. Returns full payload."""
    global _jwt_secret
    if not _jwt_secret:
        raise HTTPException(status_code=500, detail="JWT secret not configured")
    try:
        payload = jwt.decode(token, _jwt_secret, algorithms=["HS256"])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=403, detail="Token expired")
    except jwt.InvalidTokenError as e:
        raise HTTPException(status_code=403, detail=f"Invalid token: {e}")


def register_client(client_id: str, websocket, role: str, display_name: str,
                     participant: str, task: str) -> None:
    """Register a client connection."""
    connected_clients[client_id] = {
        "websocket": websocket,
        "role": role,
        "display_name": display_name,
        "participant": participant,
        "task": task,
        "connected_at": time.time(),
    }
    logger.info(
        "Client registered: %s (%s) participant=%s task=%s",
        client_id, display_name, participant, task,
    )


def deregister_client(client_id: str) -> None:
    """Remove a client connection."""
    if client_id in connected_clients:
        del connected_clients[client_id]
        logger.info("Client deregistered: %s", client_id)


def require_role(required_role: str):
    """FastAPI dependency. Reads Authorization: Bearer header. Returns payload if role matches."""
    from fastapi import Depends, Request

    async def _dependency(request: Request):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Missing Bearer token")
        token = auth_header[7:]
        payload = verify_token(token)
        if payload.get("role") != required_role:
            raise HTTPException(
                status_code=403,
                detail=f"Required role: {required_role}, got: {payload.get('role')}",
            )
        return payload

    return _dependency


class AsyncBuffer:
    """Task-aware asyncio.Queue-based staging buffer for FedBuff."""

    def __init__(self, buffer_size_k: int, supported_tasks: list, aggregation_callback):
        self.buffer_size_k = buffer_size_k
        self.queues = {task: asyncio.Queue() for task in supported_tasks}
        self._locks = {task: asyncio.Lock() for task in supported_tasks}
        self._queued_clients = {task: set() for task in supported_tasks}
        self.aggregation_callback = aggregation_callback

    async def put(self, update: dict, task: str) -> None:
        """
        Enqueues an update into the task-specific buffer queue.
        update structure: {"client_id", "task", "round_num", "global_round_received",
                           "weights" (numpy dict), "num_samples", "local_loss", "timestamp"}
        """
        if task not in self.queues:
            logger.error("Unknown task for buffer: %s", task)
            return

        client_id = update.get("client_id", "unknown")

        async with self._locks[task]:
            if client_id in self._queued_clients[task]:
                logger.warning("Duplicate update discarded: client=%s task=%s", client_id, task)
                return
            self._queued_clients[task].add(client_id)
            await self.queues[task].put(update)
            current_size = self.queues[task].qsize()

        logger.debug(
            "Buffer put: task=%s, client=%s, buffer_size=%d/%d",
            task, client_id, current_size, self.buffer_size_k,
        )

        # Emit buffer_size telemetry event
        try:
            from evaluation.metrics import emit_event
            asyncio.create_task(emit_event("buffer_size", {
                "task": task,
                "size": current_size,
                "capacity": self.buffer_size_k,
            }))
        except Exception:
            pass

    async def drain(self, task: str) -> list:
        """
        Acquires lock. If qsize >= buffer_size_k: dequeues exactly buffer_size_k items atomically.
        Returns the list or [] if insufficient items.
        """
        if task not in self.queues:
            return []

        async with self._locks[task]:
            if self.queues[task].qsize() < self.buffer_size_k:
                return []

            items = []
            for _ in range(self.buffer_size_k):
                item = self.queues[task].get_nowait()
                client_id = item.get("client_id", "unknown")
                if client_id in self._queued_clients[task]:
                    self._queued_clients[task].remove(client_id)
                items.append(item)

            logger.info(
                "Buffer drained: task=%s, items=%d, remaining=%d",
                task, len(items), self.queues[task].qsize(),
            )
            return items

    async def buffer_watcher(self) -> None:
        """
        Infinite loop, 0.5s sleep between cycles.
        For each task: if qsize >= buffer_size_k, drain, then call aggregation_callback.
        Both tasks checked independently per cycle.
        """
        logger.info("Buffer watcher started (K=%d)", self.buffer_size_k)
        while True:
            for task in self.queues:
                if self.queues[task].qsize() >= self.buffer_size_k:
                    updates = await self.drain(task)
                    if updates:
                        try:
                            await self.aggregation_callback(updates, task)
                        except Exception as e:
                            logger.error(
                                "Aggregation callback failed: task=%s, error=%s",
                                task, e,
                            )
            await asyncio.sleep(0.5)

    def size(self, task: str) -> int:
        """Returns current queue size for a task."""
        if task not in self.queues:
            return 0
        return self.queues[task].qsize()


async def handle_websocket(websocket, token: str, task: str,
                            buffer: "AsyncBuffer", model_history, config) -> None:
    """
    Full WebSocket session handler for one client connection.
    """
    from evaluation.metrics import emit_event

    # Step 1: Verify token
    try:
        payload = verify_token(token)
    except HTTPException:
        await websocket.close(code=1008, reason="Authentication failed")
        return

    client_id = payload.get("sub", "unknown")
    role = payload.get("role", "unknown")
    display_name = payload.get("display_name", client_id)
    participant = payload.get("participant", "unknown")
    token_task = payload.get("task", task)

    # Step 2: Validate task
    if task not in config.SUPPORTED_TASKS:
        await websocket.close(code=1008, reason=f"Unsupported task: {task}")
        return

    # Step 3: Register client
    register_client(client_id, websocket, role, display_name, participant, task)

    # Step 4: Emit client_joined event
    await emit_event("client_joined", {
        "client_id": client_id,
        "participant": participant,
        "task": task,
        "display_name": display_name,
    })

    try:
        # Step 5: Send current global model for this task
        latest = model_history.get_latest(task)
        await websocket.send_json({
            "type": "global_model",
            "task": task,
            "round_num": latest["round"],
            "weights": latest["weights"],
            "version": latest["version"],
            "timestamp": latest["timestamp"],
        })
        logger.info(
            "Sent global model to %s: task=%s, round=%d",
            client_id, task, latest["round"],
        )

        # Message dispatch loop
        async for message in websocket.iter_text():
            try:
                data = json.loads(message)
                msg_type = data.get("type", "")

                if msg_type == "weight_update":
                    # Parse and validate
                    update_client_id = data.get("client_id", client_id)
                    update_task = data.get("task", task)
                    round_num = data.get("round_num", 0)
                    global_round_received = data.get("global_round_received", 0)
                    weights_b64 = data.get("weights", "")
                    num_samples = data.get("num_samples", 0)
                    local_loss = data.get("local_loss", 0.0)
                    privacy_budget = data.get("privacy_budget", {})
                    timestamp = data.get("timestamp", datetime.now(timezone.utc).isoformat())

                    # Deserialize weights
                    weights = model_history.deserialize_weights(weights_b64)

                    # Layer 1: Gatekeeper L2 norm check
                    passed, norm = check_l2_norm(weights, config.L2_NORM_THRESHOLD)

                    if not passed:
                        # Rejected by gatekeeper
                        await websocket.send_json({
                            "type": "rejected",
                            "client_id": client_id,
                            "task": task,
                            "reason": "l2_norm_exceeded",
                            "round_num": round_num,
                            "norm": norm,
                            "threshold": config.L2_NORM_THRESHOLD,
                        })
                        await emit_event("update_rejected", {
                            "client_id": client_id,
                            "task": task,
                            "reason": "l2_norm_exceeded",
                            "norm": norm,
                            "round_num": round_num,
                        })
                        logger.warning(
                            "Update rejected (L2 norm): client=%s, task=%s, norm=%.4f",
                            client_id, task, norm,
                        )
                    else:
                        # Passed gatekeeper — enqueue
                        update = {
                            "client_id": client_id,
                            "task": task,
                            "round_num": round_num,
                            "global_round_received": global_round_received,
                            "weights": weights,
                            "num_samples": num_samples,
                            "local_loss": local_loss,
                            "timestamp": timestamp,
                        }
                        await buffer.put(update, task)
                        await emit_event("update_received", {
                            "client_id": client_id,
                            "task": task,
                            "round_num": round_num,
                            "num_samples": num_samples,
                            "local_loss": local_loss,
                            "norm": norm,
                        })
                        logger.info(
                            "Update received: client=%s, task=%s, round=%d, "
                            "norm=%.4f, samples=%d, loss=%.6f",
                            client_id, task, round_num, norm, num_samples, local_loss,
                        )

                elif msg_type == "ping":
                    await websocket.send_json({"type": "pong"})

                else:
                    logger.warning(
                        "Unknown message type from %s: %s", client_id, msg_type
                    )

            except json.JSONDecodeError:
                logger.warning("Invalid JSON from %s", client_id)
            except Exception as e:
                logger.error("Error processing message from %s: %s", client_id, e)

    except Exception as e:
        logger.info("WebSocket disconnected: %s (%s)", client_id, e)
    finally:
        # Cleanup on disconnect
        deregister_client(client_id)
        await emit_event("client_left", {
            "client_id": client_id,
            "participant": participant,
            "task": task,
        })
        logger.info("Client disconnected: %s (task=%s)", client_id, task)
