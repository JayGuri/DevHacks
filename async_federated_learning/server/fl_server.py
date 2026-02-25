# server/fl_server.py — Connection manager, task-aware async buffer, WebSocket router
import asyncio
import json
import os
import sys
import time
import logging
from datetime import datetime, timezone

import numpy as np
from fastapi import HTTPException

# Ensure repo root is on sys.path for core.jwt_auth
_repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

from core.jwt_auth import decode_token as _core_decode_token  # noqa: E402
from detection.anomaly import check_l2_norm

logger = logging.getLogger("fedbuff.server")

connected_clients: dict = {}
# {client_id: {"websocket": ws, "role": str, "display_name": str,
#              "participant": str, "task": str, "connected_at": float,
#              "last_heartbeat": float, "is_joining": bool,
#              "trust_score": float | None, "trust_updated_at": float | None}}


def verify_token(token: str) -> dict:
    """Decodes and validates JWT. Raises HTTPException(403) on failure. Returns full payload."""
    import jwt as _pyjwt
    try:
        return _core_decode_token(token)
    except _pyjwt.ExpiredSignatureError:
        raise HTTPException(status_code=403, detail="Token expired")
    except _pyjwt.InvalidTokenError as e:
        raise HTTPException(status_code=403, detail=f"Invalid token: {e}")
    except RuntimeError as e:
        # JWT_SECRET not set
        raise HTTPException(status_code=500, detail=str(e))


def register_client(client_id: str, websocket, role: str, display_name: str,
                     participant: str, task: str, chunk_id: int = -1) -> None:
    """Register a client connection with optional chunk assignment."""
    connected_clients[client_id] = {
        "websocket": websocket,
        "role": role,
        "display_name": display_name,
        "participant": participant,
        "task": task,
        "chunk_id": chunk_id,
        "connected_at": time.time(),
        "last_heartbeat": time.time(),
        "is_joining": True,   # grace period until first weight_update received
        "trust_score": None,
        "trust_updated_at": None,
    }
    logger.info(
        "Client registered: %s (%s) participant=%s task=%s chunk=%d",
        client_id, display_name, participant, task, chunk_id,
    )


def update_heartbeat(client_id: str) -> None:
    """Touch the heartbeat timestamp and clear the joining grace period."""
    if client_id in connected_clients:
        connected_clients[client_id]["last_heartbeat"] = time.time()
        connected_clients[client_id]["is_joining"] = False


def update_client_trust(client_id: str, score: float) -> None:
    """Store post-aggregation trust score on the client's connection record."""
    if client_id in connected_clients:
        connected_clients[client_id]["trust_score"] = score
        connected_clients[client_id]["trust_updated_at"] = time.time()


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


async def heartbeat_checker(
    buffer: "AsyncBuffer",
    timeout: float = 60.0,
    check_interval: float = 10.0,
    chunk_manager=None,
) -> None:
    """Periodic task: scans connected_clients for stale entries.

    If a client's last_heartbeat is older than `timeout` seconds:
      1. Remove from buffer's _queued_clients (prevent permanent block)
      2. Release assigned chunk via ChunkManager (if available)
      3. Deregister from connected_clients
      4. Emit client_timeout SSE event
    """
    from evaluation.metrics import emit_event

    logger.info(
        "Heartbeat checker started (timeout=%.1fs, interval=%.1fs)",
        timeout, check_interval,
    )
    while True:
        await asyncio.sleep(check_interval)
        now = time.time()
        stale = [
            (cid, info)
            for cid, info in list(connected_clients.items())
            if now - info.get("last_heartbeat", now) > timeout
        ]
        for client_id, info in stale:
            task = info.get("task", "")
            logger.warning(
                "Client timeout detected: %s (task=%s, last_seen=%.1fs ago)",
                client_id, task, now - info["last_heartbeat"],
            )
            if task and task in buffer._queued_clients:
                buffer._queued_clients[task].discard(client_id)

            # Release chunk on timeout (same as disconnect)
            if chunk_manager is not None:
                released = await asyncio.to_thread(chunk_manager.release_chunk, client_id)
                if released is not None:
                    logger.info(
                        "[SERVER] Timeout: %s → chunk_%d released → available again",
                        client_id, released,
                    )

            deregister_client(client_id)
            asyncio.create_task(emit_event("client_timeout", {
                "client_id": client_id,
                "task": task,
                "last_heartbeat": info["last_heartbeat"],
            }))


class AsyncBuffer:
    """Task-aware asyncio.Queue-based staging buffer for FedBuff.

    Supports:
    - Event-driven aggregation: wakes immediately when min_updates threshold is
      reached and max_wait_seconds has elapsed, rather than polling every 0.5s.
    - Per-task independent watcher coroutines for zero cross-task interference.
    - Staleness gate: updates with staleness > max_staleness are rejected before
      enqueueing, keeping the buffer free of dangerously stale updates.
    """

    def __init__(
        self,
        buffer_size_k: int,
        supported_tasks: list,
        aggregation_callback,
        get_current_round=None,
        max_staleness: int = 10,
        min_updates: int = None,
        max_wait_seconds: float = 10.0,
        max_updates_per_batch: int = 20,
    ):
        self.buffer_size_k = buffer_size_k
        self.min_updates = min_updates if min_updates is not None else buffer_size_k
        self.max_wait_seconds = max_wait_seconds
        self.max_updates_per_batch = max_updates_per_batch
        self.queues = {task: asyncio.Queue() for task in supported_tasks}
        self._locks = {task: asyncio.Lock() for task in supported_tasks}
        self._queued_clients = {task: set() for task in supported_tasks}
        self.aggregation_callback = aggregation_callback
        self._get_current_round = get_current_round
        self._max_staleness = max_staleness
        # Event-driven: one asyncio.Event per task, signalled by put()
        self._new_update_events = {task: asyncio.Event() for task in supported_tasks}
        # Timer: tracks when min_updates threshold was first reached per task
        self._timer_started_at = {task: None for task in supported_tasks}

    async def put(self, update: dict, task: str) -> None:
        """Enqueues an update into the task-specific buffer queue.

        Staleness gate: if get_current_round is provided and the update's
        staleness exceeds max_staleness, the update is silently rejected
        and an SSE event is emitted.
        """
        if task not in self.queues:
            logger.error("Unknown task for buffer: %s", task)
            return

        client_id = update.get("client_id", "unknown")

        # --- Staleness gate ---
        if self._get_current_round is not None:
            current_round = self._get_current_round(task)
            global_round_received = update.get("global_round_received", 0)
            staleness = max(0, current_round - global_round_received)
            if staleness > self._max_staleness:
                logger.warning(
                    "Update REJECTED (staleness=%d > max=%d): client=%s task=%s",
                    staleness, self._max_staleness, client_id, task,
                )
                try:
                    from evaluation.metrics import emit_event
                    asyncio.create_task(emit_event("update_rejected", {
                        "client_id": client_id,
                        "task": task,
                        "reason": "staleness_exceeded",
                        "staleness": staleness,
                        "max_staleness": self._max_staleness,
                    }))
                except Exception:
                    pass
                return

        async with self._locks[task]:
            if client_id in self._queued_clients[task]:
                logger.warning("Duplicate update discarded: client=%s task=%s", client_id, task)
                return
            self._queued_clients[task].add(client_id)
            await self.queues[task].put(update)
            current_size = self.queues[task].qsize()
            # Start timer when min_updates threshold is first reached
            if current_size >= self.min_updates and self._timer_started_at[task] is None:
                self._timer_started_at[task] = asyncio.get_event_loop().time()
                logger.debug("Timer started for task=%s at size=%d", task, current_size)

        logger.debug(
            "Buffer put: task=%s, client=%s, buffer_size=%d/%d",
            task, client_id, current_size, self.buffer_size_k,
        )

        # Signal the per-task watcher
        self._new_update_events[task].set()

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

    async def drain_partial(self, task: str, max_items: int) -> list:
        """Drain up to max_items from queue atomically. Returns all available up to cap."""
        if task not in self.queues:
            return []
        async with self._locks[task]:
            n = min(self.queues[task].qsize(), max_items)
            if n == 0:
                return []
            items = []
            for _ in range(n):
                item = self.queues[task].get_nowait()
                cid = item.get("client_id", "unknown")
                self._queued_clients[task].discard(cid)
                items.append(item)
            self._timer_started_at[task] = None  # reset timer after drain
            logger.info(
                "Buffer partial drain: task=%s, items=%d, remaining=%d",
                task, len(items), self.queues[task].qsize(),
            )
            return items

    async def drain(self, task: str) -> list:
        """Legacy drain: dequeues exactly buffer_size_k if available.
        Kept for backward compatibility with existing tests.
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
            self._timer_started_at[task] = None

            logger.info(
                "Buffer drained: task=%s, items=%d, remaining=%d",
                task, len(items), self.queues[task].qsize(),
            )
            return items

    async def _task_watcher(self, task: str) -> None:
        """Per-task event-driven watcher loop.

        Wakes up when:
        - A new update event fires (from put()), or
        - max_wait_seconds has elapsed (ceiling timer).

        Aggregates when:
        - max_updates_per_batch items queued (batch cap), or
        - min_updates met AND max_wait_seconds elapsed since threshold was reached.
        """
        event = self._new_update_events[task]
        while True:
            try:
                await asyncio.wait_for(event.wait(), timeout=self.max_wait_seconds)
            except asyncio.TimeoutError:
                pass  # ceiling timer hit — fall through to check condition
            finally:
                event.clear()

            current_size = self.queues[task].qsize()
            if current_size == 0:
                continue

            now = asyncio.get_event_loop().time()
            timer_started = self._timer_started_at[task]
            time_elapsed = (now - timer_started) if timer_started is not None else 0.0

            should_aggregate = (
                current_size >= self.max_updates_per_batch  # batch cap
                or (current_size >= self.min_updates and time_elapsed >= self.max_wait_seconds)
            )

            if should_aggregate:
                updates = await self.drain_partial(task, self.max_updates_per_batch)
                if updates:
                    try:
                        await self.aggregation_callback(updates, task)
                    except Exception as e:
                        logger.error(
                            "Aggregation callback failed: task=%s, error=%s", task, e,
                        )

    async def buffer_watcher(self) -> None:
        """Spawns one _task_watcher coroutine per task via asyncio.gather().

        Replaces the old 0.5s polling loop with an event-driven design where
        each task wakes immediately when new updates arrive.
        """
        logger.info(
            "Event-driven buffer watcher started "
            "(min_updates=%d, max_wait=%.1fs, max_batch=%d)",
            self.min_updates, self.max_wait_seconds, self.max_updates_per_batch,
        )
        watchers = [
            asyncio.create_task(self._task_watcher(task))
            for task in self.queues
        ]
        try:
            await asyncio.gather(*watchers)
        except asyncio.CancelledError:
            for w in watchers:
                w.cancel()
            raise

    def size(self, task: str) -> int:
        """Returns current queue size for a task."""
        if task not in self.queues:
            return 0
        return self.queues[task].qsize()


async def handle_websocket(
    websocket,
    token: str,
    task: str,
    buffer: "AsyncBuffer",
    model_history,
    config,
    network_simulator=None,
    chunk_manager=None,
) -> None:
    """Full WebSocket session handler for one client connection.

    When *chunk_manager* is provided the handler will:
      1. Atomically assign an available data chunk to this client.
      2. Log structured chunk-assignment / per-round messages.
      3. Release the chunk in the ``finally`` block (disconnect / crash).
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

    # Step 2b: Chunk assignment (if ChunkManager available)
    assigned_chunk = -1
    if chunk_manager is not None:
        success, assigned_chunk, msg = await asyncio.to_thread(
            chunk_manager.assign_chunk,
            client_id=client_id, dataset=task,
        )
        if not success:
            logger.warning(
                "[SERVER] Chunk assignment failed for %s: %s", client_id, msg,
            )
            await websocket.close(code=1008, reason=msg)
            return
        # Log chunk load details (sample_count filled later by client/loader)
        chunk_info = await asyncio.to_thread(chunk_manager.get_chunk_info, assigned_chunk)
        if chunk_info:
            logger.info(
                "[SERVER] Chunk %d loaded from MongoDB: %d samples (%s)",
                assigned_chunk,
                chunk_info.get("sample_count", 0),
                chunk_info.get("dataset", task),
            )
            logger.info(
                "[SERVER] Chunk %d: %d samples, classes=%s, loaded_from=%s",
                assigned_chunk,
                chunk_info.get("sample_count", 0),
                chunk_info.get("classes", []),
                chunk_info.get("loaded_from", "mongodb"),
            )
        # Duplicate validation
        dup_errors = await asyncio.to_thread(chunk_manager.validate_no_duplicates)
        for err in dup_errors:
            logger.error("[SERVER] %s", err)

    # Step 3: Register client (with chunk_id)
    register_client(client_id, websocket, role, display_name, participant, task,
                    chunk_id=assigned_chunk)

    # Step 4: Emit client_joined event
    await emit_event("client_joined", {
        "client_id": client_id,
        "participant": participant,
        "task": task,
        "display_name": display_name,
        "chunk_id": assigned_chunk,
    })

    try:
        # Step 5: Send current global model for this task (include chunk assignment)
        latest = model_history.get_latest(task)
        await websocket.send_json({
            "type": "global_model",
            "task": task,
            "round_num": latest["round"],
            "weights": latest["weights"],
            "version": latest["version"],
            "timestamp": latest["timestamp"],
            "assigned_chunk": assigned_chunk,
        })
        logger.info(
            "Sent global model to %s: task=%s, round=%d, chunk=%d",
            client_id, task, latest["round"], assigned_chunk,
        )

        # Message dispatch loop
        # Security: reject messages exceeding 50 MB to prevent OOM DoS
        MAX_MESSAGE_SIZE = 50 * 1024 * 1024  # 50 MB
        async for message in websocket.iter_text():
            try:
                if len(message) > MAX_MESSAGE_SIZE:
                    logger.warning(
                        "Message too large from %s: %d bytes (max=%d). Dropping.",
                        client_id, len(message), MAX_MESSAGE_SIZE,
                    )
                    continue
                # Offload JSON deserialization to a thread to prevent event loop blocking with large/nested payloads
                data = await asyncio.to_thread(json.loads, message)
                msg_type = data.get("type", "")

                if msg_type == "weight_update":
                    # Update heartbeat — clears is_joining grace period
                    update_heartbeat(client_id)

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
                        # Passed gatekeeper — build update dict
                        update = {
                            "client_id": client_id,
                            "task": task,
                            "round_num": round_num,
                            "global_round_received": global_round_received,
                            "weights": weights,
                            "num_samples": num_samples,
                            "local_loss": local_loss,
                            "timestamp": timestamp,
                            "chunk_id": assigned_chunk,
                        }

                        # ── Per-round chunk log ──
                        privacy_epsilon = privacy_budget.get("epsilon", 0.0) if isinstance(privacy_budget, dict) else 0.0
                        logger.info(
                            "[%s] Chunk %d | Round %d | Loss %.4f | Samples %d | Epsilon %.4f",
                            client_id, assigned_chunk, round_num,
                            local_loss, num_samples, privacy_epsilon,
                        )

                        # Network simulation (if enabled)
                        if network_simulator is not None:
                            update = await network_simulator.simulate_client_upload(
                                update, client_id
                            )
                            if update is None:
                                logger.info(
                                    "Update dropped by network simulator: client=%s", client_id
                                )
                                continue

                        await buffer.put(update, task)
                        current_trust = connected_clients.get(client_id, {}).get("trust_score")
                        await emit_event("update_received", {
                            "client_id": client_id,
                            "task": task,
                            "round_num": round_num,
                            "num_samples": num_samples,
                            "local_loss": local_loss,
                            "norm": norm,
                            "trust_score": current_trust,
                        })
                        trust_fmt = f"{current_trust:.4f}" if current_trust is not None else "N/A"
                        logger.info(
                            "Update received: client=%s, task=%s, round=%d, "
                            "norm=%.4f, samples=%d, loss=%.6f, trust=%s",
                            client_id, task, round_num, norm, num_samples, local_loss, trust_fmt,
                        )

                elif msg_type == "heartbeat":
                    update_heartbeat(client_id)
                    await websocket.send_json({"type": "heartbeat_ack", "client_id": client_id})
                    logger.debug("Heartbeat from %s", client_id)

                elif msg_type == "ping":
                    update_heartbeat(client_id)
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
        # Prevent a stale/duplicate connection that drops from releasing the chunk
        # of the actively registered connection.
        is_active_connection = (
            client_id in connected_clients and
            connected_clients[client_id].get("websocket") == websocket
        )

        # Remove from buffer's pending set to prevent permanent block on reconnect
        if task in buffer._queued_clients:
            buffer._queued_clients[task].discard(client_id)

        # ── Release chunk back to available pool ──
        released_chunk = None
        if chunk_manager is not None and is_active_connection:
            released_chunk = await asyncio.to_thread(chunk_manager.release_chunk, client_id)
            if released_chunk is not None:
                logger.info(
                    "[SERVER] %s disconnected → chunk_%d released → available again",
                    client_id, released_chunk,
                )

        if is_active_connection:
            deregister_client(client_id)
            await emit_event("client_left", {
                "client_id": client_id,
                "participant": participant,
                "task": task,
                "chunk_released": released_chunk,
            })
            logger.info("Client disconnected: %s (task=%s, chunk_released=%s)",
                         client_id, task, released_chunk)
        else:
            logger.info("Duplicate connection dropped for %s (chunk and registration maintained for active connection)", client_id)

