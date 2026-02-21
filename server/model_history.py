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

        import os
        os.makedirs(checkpoint_dir, exist_ok=True)

        for task, model in initial_models.items():
            weights = {}
            for name, param in model.named_parameters():
                weights[name] = param.data.cpu().numpy().copy()

            self.models[task] = {
                "weights": weights,
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
        # Serialize weights for WebSocket transmission
        serialized = self.serialize_weights(model_info["weights"])
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

        self.models[task]["weights"] = {k: v.copy() for k, v in new_weights.items()}
        self.models[task]["round"] += 1
        self.models[task]["version"] = self._compute_version(new_weights)
        self.models[task]["timestamp"] = datetime.now(timezone.utc).isoformat()
        self.models[task]["loss_history"].append(loss)

        logger.info(
            "ModelHistory: updated task=%s, round=%d, loss=%.6f, version=%s",
            task, self.models[task]["round"], loss,
            self.models[task]["version"][:8],
        )

    def serialize_weights(self, weights: dict) -> str:
        """numpy arrays -> lists -> msgpack bytes -> base64 string."""
        serializable = {}
        for key, val in weights.items():
            serializable[key] = val.tolist()
        packed = msgpack.packb(serializable, use_bin_type=True)
        return base64.b64encode(packed).decode("utf-8")

    def deserialize_weights(self, b64_str: str) -> dict:
        """Reverses serialize_weights. Returns dict of numpy arrays."""
        packed = base64.b64decode(b64_str)
        unpacked = msgpack.unpackb(packed, raw=False)
        weights = {}
        for key, val in unpacked.items():
            k = key if isinstance(key, str) else key.decode("utf-8")
            weights[k] = np.array(val, dtype=np.float32)
        return weights
