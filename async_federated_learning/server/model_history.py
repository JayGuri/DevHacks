# server/model_history.py — Rolling buffer of versioned model snapshots + legacy ModelHistory
"""
server/model_history.py
=======================
Contains:
- ModelHistoryBuffer: SABD-compatible rolling snapshot buffer keyed by version_id.
- ModelHistory: akshat's legacy model history for WebSocket server (serialisation, rounds).

ModelHistoryBuffer is used by SABD to compute per-parameter drift between versions.
ModelHistory is used by the FastAPI WebSocket server for round tracking and model serving.
"""

import logging
import time
import hashlib
import base64
from collections import deque
from datetime import datetime, timezone

import numpy as np
import msgpack

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# SABD-compatible rolling buffer (from ayush)
# ---------------------------------------------------------------------------

class ModelHistoryBuffer:
    """Rolling buffer of versioned global model snapshots for SABD drift computation.

    Parameters
    ----------
    max_size : int
        Maximum number of model snapshots to retain (default 15).
    """

    def __init__(self, max_size: int) -> None:
        self._history: dict = {}
        self._order: deque = deque(maxlen=max_size)
        self.max_size = max_size
        logger.debug("ModelHistoryBuffer initialised (max_size=%d).", max_size)

    def record(self, version_id: int, weights_dict: dict) -> None:
        """Snapshot and store the global model at version_id."""
        if len(self._history) >= self.max_size:
            oldest = self._order[0]
            del self._history[oldest]
            logger.debug("Evicted model snapshot version %d from history.", oldest)

        self._history[version_id] = {k: v.copy() for k, v in weights_dict.items()}
        self._order.append(version_id)

        logger.info(
            "Recorded model version %d. Buffer size: %d / %d.",
            version_id, len(self._history), self.max_size,
        )

    def get_drift(self, from_version: int, to_weights: dict) -> dict:
        """Compute per-parameter drift: delta[k] = theta_t[k] - theta_s[k]."""
        if from_version not in self._history:
            available = sorted(self._history.keys())
            raise ValueError(
                f"Model version {from_version} is not in the history buffer. "
                f"Available versions: {available}. "
                f"The snapshot may have been evicted (max_size={self.max_size}). "
                "Consider increasing Config.model_history_size."
            )

        base = self._history[from_version]
        drift = {k: to_weights[k] - base[k] for k in to_weights}

        drift_norm = float(np.sqrt(sum(np.sum(d ** 2) for d in drift.values())))
        logger.debug("Drift from version %d -> current: L2 norm = %.6f", from_version, drift_norm)
        return drift

    def has_version(self, version_id: int) -> bool:
        """Return True if version_id is currently in the buffer."""
        return version_id in self._history

    def get_oldest_version(self):
        """Return the version_id of the oldest retained snapshot, or None if empty."""
        return self._order[0] if self._order else None

    def get_latest_version(self):
        """Return the version_id of the most recently recorded snapshot, or None."""
        return self._order[-1] if self._order else None

    def __len__(self) -> int:
        return len(self._history)

    def __repr__(self) -> str:
        return (
            f"ModelHistoryBuffer(max_size={self.max_size}, "
            f"len={len(self)}, "
            f"versions={list(self._order)})"
        )


# ---------------------------------------------------------------------------
# Legacy akshat ModelHistory for WebSocket server
# ---------------------------------------------------------------------------

class ModelHistory:
    """Per-task model management: round tracking, versioning, serialisation.
    Used by the FastAPI WebSocket server to serve models and track rounds.
    """

    def __init__(self, initial_models: dict, checkpoint_dir: str = "./results/checkpoints"):
        self.models = {}
        self.checkpoint_dir = checkpoint_dir
        # Per-client personalized model storage: {client_id: {"weights", "task", "updated_at"}}
        self._client_models: dict = {}
        # A/B version tags: {task: {"A": version_hash, "B": version_hash}}
        self._ab_versions: dict = {}

        import os
        os.makedirs(checkpoint_dir, exist_ok=True)

        for task, model in initial_models.items():
            weights = {}
            for name, param in model.named_parameters():
                weights[name] = param.data.cpu().numpy().copy()

            serialized_weights = self.serialize_weights(weights)

            self.models[task] = {
                "weights": weights,
                "weights_serialized": serialized_weights,
                "round": 0,
                "version": self._compute_version(weights),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "loss_history": [],
            }
            logger.info(
                "ModelHistory: initialized task=%s, params=%d, version=%s",
                task, sum(w.size for w in weights.values()),
                self.models[task]["version"][:8],
            )

    def _compute_version(self, weights: dict) -> str:
        """Compute a hash-based version string for a set of weights."""
        flat = np.concatenate([v.flatten() for v in weights.values()])
        hash_bytes = hashlib.sha256(flat.tobytes()).digest()
        return base64.b64encode(hash_bytes).decode("utf-8")[:16]

    def get_round(self, task: str) -> int:
        """Get current round number for a task."""
        if task not in self.models:
            return 0
        return self.models[task]["round"]

    def get_latest(self, task: str) -> dict:
        """Get the latest model info for a task (weights, round, version, timestamp)."""
        if task not in self.models:
            return {"weights": {}, "round": 0, "version": "", "timestamp": ""}

        model_info = self.models[task]
        # Use cached serialization to keep connect-time path fast.
        serialized = model_info.get("weights_serialized")
        if not serialized:
            serialized = self.serialize_weights(model_info["weights"])
            model_info["weights_serialized"] = serialized
        return {
            "weights": serialized,
            "round": model_info["round"],
            "version": model_info["version"],
            "timestamp": model_info["timestamp"],
        }

    def update(self, task: str, new_weights: dict, loss: float = 0.0) -> None:
        """Update the global model for a task after aggregation."""
        if task not in self.models:
            logger.warning("ModelHistory.update: unknown task=%s", task)
            return

        # new_weights is the aggregated weight_diff. We must add it to the current global model.
        old_weights = self.models[task]["weights"]
        # Use key intersection so mismatched schemas don't crash aggregation
        common_keys = set(old_weights.keys()) & set(new_weights.keys())
        missing_in_new = set(old_weights.keys()) - common_keys
        extra_in_new = set(new_weights.keys()) - common_keys
        if missing_in_new:
            logger.warning(
                "ModelHistory.update: keys in global model but missing from update (kept unchanged): %s",
                missing_in_new,
            )
        if extra_in_new:
            logger.warning(
                "ModelHistory.update: extra keys in update ignored: %s", extra_in_new,
            )
        self.models[task]["weights"] = {
            k: old_weights[k] + new_weights[k] if k in common_keys else old_weights[k]
            for k in old_weights
        }
        self.models[task]["weights_serialized"] = self.serialize_weights(self.models[task]["weights"])
        self.models[task]["round"] += 1
        self.models[task]["version"] = self._compute_version(new_weights)
        self.models[task]["timestamp"] = datetime.now(timezone.utc).isoformat()
        self.models[task]["loss_history"].append(loss)

        logger.info(
            "ModelHistory: updated task=%s, round=%d, loss=%.6f, version=%s",
            task, self.models[task]["round"], loss,
            self.models[task]["version"][:8],
        )

    def get_personalized(self, client_id: str, task: str, alpha: float = 0.2) -> dict:
        """Return a personalized model for a client.

        w_personalized = (1 - alpha) * w_global + alpha * w_local

        Falls back to global model if no local model exists yet for this client.
        alpha=0 → pure global model; alpha=1 → pure local model.
        """
        global_weights = self.models[task]["weights"]
        local_state = self._client_models.get(client_id)
        if local_state is None or local_state.get("task") != task:
            return {k: v.copy() for k, v in global_weights.items()}
        local_weights = local_state["weights"]
        return {
            k: (1.0 - alpha) * global_weights[k] + alpha * local_weights[k]
            for k in global_weights
        }

    def update_client_local(self, client_id: str, weight_delta: dict, task: str) -> None:
        """Store a client's local model (global weights + their update delta)."""
        if task not in self.models:
            return
        global_weights = self.models[task]["weights"]
        local_weights = {k: global_weights[k] + weight_delta[k] for k in global_weights}
        self._client_models[client_id] = {
            "weights": local_weights,
            "task": task,
            "updated_at": time.time(),
        }

    def tag_ab_version(self, task: str, slot: str) -> None:
        """Tag current model version as 'A' or 'B' for A/B testing."""
        if task not in self.models:
            return
        version = self.models[task]["version"]
        self._ab_versions.setdefault(task, {})[slot] = version
        logger.info("Tagged %s-%s as version %s", task, slot, version[:8])

    def serialize_weights(self, weights: dict) -> str:
        """numpy arrays -> lists -> msgpack bytes -> zlib compress -> base64 string."""
        import zlib
        serializable = {}
        for key, val in weights.items():
            serializable[key] = val.tolist()
        packed = msgpack.packb(serializable, use_bin_type=True)
        compressed = zlib.compress(packed, level=6)
        return base64.b64encode(compressed).decode("utf-8")

    def deserialize_weights(self, b64_str: str) -> dict:
        """Reverses serialize_weights. Auto-detects zlib compression."""
        import zlib
        MAX_WEIGHT_ELEMENTS = 100_000_000  # ~400 MB at float32

        raw = base64.b64decode(b64_str)
        # Auto-detect zlib compression (magic byte 0x78)
        try:
            raw = zlib.decompress(raw)
        except zlib.error:
            pass  # Not compressed — treat as raw msgpack
        unpacked = msgpack.unpackb(raw, raw=False)

        # Security: cap total element count to prevent memory exhaustion
        total_elements = 0
        for val in unpacked.values():
            if isinstance(val, list):
                total_elements += _count_elements(val)
            else:
                total_elements += 1
            if total_elements > MAX_WEIGHT_ELEMENTS:
                raise ValueError(
                    f"Deserialized weights exceed {MAX_WEIGHT_ELEMENTS} elements. "
                    "Possible decompression bomb — rejecting."
                )

        weights = {}
        for key, val in unpacked.items():
            k = key if isinstance(key, str) else key.decode("utf-8")
            weights[k] = np.array(val, dtype=np.float32)
        return weights


def _count_elements(lst) -> int:
    """Recursively count leaf elements in a nested list."""
    if not isinstance(lst, list):
        return 1
    if not lst:
        return 0
    # Optimization: if first element is not a list, assume flat
    if not isinstance(lst[0], list):
        return len(lst)
    return sum(_count_elements(item) for item in lst)
