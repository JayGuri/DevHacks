# evaluation/metrics.py — Prometheus metrics, SSE broadcaster, evaluation utilities
import asyncio
import json
import logging
import numpy as np
from datetime import datetime, timezone

from prometheus_client import Gauge, Counter, Histogram

logger = logging.getLogger("fedbuff.evaluation.metrics")

# Prometheus metrics
fl_connected_clients = Gauge(
    "fl_connected_clients", "Total connected clients"
)
fl_global_round = Gauge(
    "fl_global_round", "Current FL round", ["task"]
)
fl_updates_received_total = Counter(
    "fl_updates_received_total", "Updates received", ["client_id", "task"]
)
fl_updates_rejected_total = Counter(
    "fl_updates_rejected_total", "Updates rejected", ["client_id", "task", "reason"]
)
fl_global_loss = Gauge(
    "fl_global_loss", "Current global loss", ["task"]
)
fl_buffer_size = Gauge(
    "fl_buffer_size", "Buffer occupancy", ["task"]
)
fl_aggregation_duration = Histogram(
    "fl_aggregation_duration_seconds", "Aggregation time", ["task"]
)
fl_client_trust_score = Gauge(
    "fl_client_trust_score", "Client trust score", ["client_id", "task"]
)

# SSE broadcaster
sse_subscribers: list = []


async def subscribe_sse() -> asyncio.Queue:
    """Create and register a new SSE subscriber queue."""
    q = asyncio.Queue()
    sse_subscribers.append(q)
    logger.debug("SSE subscriber added. Total subscribers: %d", len(sse_subscribers))
    return q


async def unsubscribe_sse(q: asyncio.Queue) -> None:
    """Remove an SSE subscriber queue."""
    if q in sse_subscribers:
        sse_subscribers.remove(q)
        logger.debug("SSE subscriber removed. Total subscribers: %d", len(sse_subscribers))


async def emit_event(event_type: str, data: dict) -> None:
    """
    Serialises the event and puts it in every SSE subscriber's queue.
    Updates Prometheus metrics based on event_type.
    """
    event = {
        "event": event_type,
        "data": data,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    event_json = json.dumps(event, default=str)

    # Distribute to all SSE subscribers
    for q in list(sse_subscribers):
        try:
            q.put_nowait(event_json)
        except asyncio.QueueFull:
            logger.warning("SSE subscriber queue full, dropping event")
        except Exception as e:
            logger.warning("Failed to put event to SSE subscriber: %s", e)

    # Update Prometheus metrics based on event_type
    try:
        if event_type == "update_received":
            client_id = data.get("client_id", "unknown")
            task = data.get("task", "unknown")
            fl_updates_received_total.labels(client_id=client_id, task=task).inc()

        elif event_type == "update_rejected":
            client_id = data.get("client_id", "unknown")
            task = data.get("task", "unknown")
            reason = data.get("reason", "unknown")
            fl_updates_rejected_total.labels(
                client_id=client_id, task=task, reason=reason
            ).inc()

        elif event_type == "round_complete":
            task = data.get("task", "unknown")
            round_num = data.get("round", 0)
            loss = data.get("loss", 0.0)
            fl_global_round.labels(task=task).set(round_num)
            fl_global_loss.labels(task=task).set(loss)

        elif event_type == "client_joined":
            fl_connected_clients.inc()

        elif event_type == "client_left":
            fl_connected_clients.dec()

        elif event_type == "trust_score":
            client_id = data.get("client_id", "unknown")
            task = data.get("task", "unknown")
            score = data.get("score", 0.0)
            fl_client_trust_score.labels(client_id=client_id, task=task).set(score)

        elif event_type == "buffer_size":
            task = data.get("task", "unknown")
            size = data.get("size", 0)
            fl_buffer_size.labels(task=task).set(size)

    except Exception as e:
        logger.warning("Failed to update Prometheus metric for %s: %s", event_type, e)


def compute_accuracy(logits: np.ndarray, labels: np.ndarray) -> float:
    """Returns top-1 accuracy as a float in [0.0, 1.0]."""
    predictions = np.argmax(logits, axis=-1)
    return float(np.mean(predictions == labels))
