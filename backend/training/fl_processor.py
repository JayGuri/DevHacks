# backend/training/fl_processor.py — FL Weight Update Processing Pipeline
"""
Implements the two-layer defense pipeline defined in WEBSOCKET_SCHEMA.md.

  Layer 1: L2 Norm Gatekeeper
    - ||update||_2 > threshold  → emit `rejected`, record in gatekeeper_rejected
    - ||update||_2 ≤ threshold  → queue for Layer 2

  Layer 2: SABD Statistical Outlier Filter
    - cosine_distance(update, mean) > 0.45 → trust_score = 0.0, add to rejected_clients
    - Otherwise → accepted for aggregation

After each training round:
  - build_trust_report_msg()  → `trust_report` broadcast
  - build_global_model_msg()  → `global_model` broadcast
"""

import base64
import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import numpy as np

try:
    import msgpack
    _HAS_MSGPACK = True
except ImportError:
    _HAS_MSGPACK = False
    logging.getLogger("arfl.fl_processor").warning(
        "msgpack not installed — weight encoding will use JSON fallback. "
        "Run: pip install msgpack"
    )

logger = logging.getLogger("arfl.fl_processor")

# SABD cosine distance threshold for Layer 2 outlier detection
_SABD_THRESHOLD = 0.45

# EMA smoothing factor for trust score updates (alpha)
_TRUST_EMA_ALPHA = 0.3

# Staleness decay base factor  (weight = 1 / (1 + base * staleness))
_STALENESS_DECAY_BASE = 0.1

# Maximum concurrent FL clients per project (enforced at WS handshake)
MAX_FL_CLIENTS = 10


class FLWeightProcessor:
    """Per-project FL weight update processor.

    Maintains per-client trust scores, staleness, and a pending update queue.
    Thread-safety note: methods are called from asyncio context; the pending
    list is drained synchronously in _training_loop before _execute_round, so
    no locking is required.
    """

    def __init__(self, project_id: str, config: dict):
        self.project_id = project_id
        self.config = config

        # Per-client persistent state
        self._trust_scores: Dict[str, float] = {}
        self._staleness_values: Dict[str, int] = {}
        self._staleness_weights: Dict[str, float] = {}

        # Current-round transient state (cleared each round)
        self._gatekeeper_rejected: List[str] = []   # Layer 1 rejections
        self._outlier_rejected: List[str] = []       # Layer 2 rejections
        self._pending_updates: List[dict] = []       # Passed Layer 1, await round

        # Global round counter — updated by coordinator each round
        self._global_round: int = 0

    # ------------------------------------------------------------------
    # Weight encoding / decoding
    # ------------------------------------------------------------------

    def decode_weights(self, weights_b64: str) -> Optional[Dict[str, np.ndarray]]:
        """Decode base64-encoded msgpack (or JSON fallback) → numpy arrays."""
        if not weights_b64:
            return None
        try:
            raw = base64.b64decode(weights_b64)
            if _HAS_MSGPACK:
                data = msgpack.unpackb(raw, raw=False)
            else:
                import json
                data = json.loads(raw.decode("utf-8"))
            return {k: np.array(v, dtype=np.float32) for k, v in data.items()}
        except Exception as exc:
            logger.warning("decode_weights failed for project=%s: %s", self.project_id, exc)
            return None

    def encode_weights(self, weights: Dict[str, np.ndarray]) -> str:
        """Encode numpy weight arrays → base64-encoded msgpack (or JSON fallback)."""
        try:
            data = {k: v.tolist() for k, v in weights.items()}
            if _HAS_MSGPACK:
                packed = msgpack.packb(data)
            else:
                import json
                packed = json.dumps(data).encode("utf-8")
            return base64.b64encode(packed).decode("utf-8")
        except Exception as exc:
            logger.warning("encode_weights failed for project=%s: %s", self.project_id, exc)
            return ""

    # ------------------------------------------------------------------
    # L2 norm helper
    # ------------------------------------------------------------------

    def compute_l2_norm(self, weights: Dict[str, np.ndarray]) -> float:
        """Compute the L2 norm of the concatenated flattened weight arrays."""
        try:
            flat = np.concatenate([v.flatten() for v in weights.values()])
            return float(np.linalg.norm(flat))
        except Exception:
            return 0.0

    def get_l2_threshold(self) -> float:
        """Return the configured L2 gatekeeper threshold (default 10.0)."""
        return float(self.config.get("l2GatekeeperThreshold", 10.0))

    # ------------------------------------------------------------------
    # Layer 1: L2 Norm Gatekeeper
    # ------------------------------------------------------------------

    def layer1_gatekeeper(
        self,
        client_id: str,
        weights: Dict[str, np.ndarray],
    ) -> Tuple[bool, float]:
        """Check whether a client's update passes the L2 norm gate.

        Returns:
            (passes, norm)  — passes=True means the update proceeds to Layer 2.
        """
        threshold = self.get_l2_threshold()
        norm = self.compute_l2_norm(weights)
        passes = norm <= threshold

        if not passes:
            if client_id not in self._gatekeeper_rejected:
                self._gatekeeper_rejected.append(client_id)
            logger.info(
                "Layer 1 REJECTED: project=%s client=%s norm=%.4f threshold=%.4f",
                self.project_id, client_id, norm, threshold,
            )

        return passes, norm

    # ------------------------------------------------------------------
    # Layer 2: SABD Statistical Outlier Filter
    # ------------------------------------------------------------------

    def layer2_sabd(
        self,
        updates: List[dict],
    ) -> Tuple[List[dict], List[str]]:
        """Filter outlier updates via cosine distance from the mean gradient.

        Args:
            updates: Pending updates that passed Layer 1. Each dict must contain
                     'client_id' (str) and 'weights' (Dict[str, np.ndarray]).

        Returns:
            (accepted_updates, rejected_client_ids)
        """
        if not updates:
            return [], []

        if len(updates) == 1:
            # Cannot compute meaningful cosine distance with a single update
            return updates, []

        try:
            # Flatten each update into a single vector
            flat_vecs: List[np.ndarray] = []
            for u in updates:
                flat = np.concatenate([v.flatten() for v in u["weights"].values()])
                flat_vecs.append(flat)

            # Truncate to shortest vector length to handle heterogeneous models
            min_len = min(v.shape[0] for v in flat_vecs)
            flat_vecs = [v[:min_len] for v in flat_vecs]

            mean_flat = np.mean(flat_vecs, axis=0)
            norm_mean = float(np.linalg.norm(mean_flat))

            accepted: List[dict] = []
            rejected_ids: List[str] = []

            for i, u in enumerate(updates):
                client_id = u["client_id"]
                flat = flat_vecs[i]
                norm_u = float(np.linalg.norm(flat))

                if norm_u < 1e-10 or norm_mean < 1e-10:
                    cosine_dist = 0.0
                else:
                    cosine_sim = float(np.dot(flat, mean_flat) / (norm_u * norm_mean))
                    cosine_dist = 1.0 - float(np.clip(cosine_sim, -1.0, 1.0))

                # Update client trust via EMA
                self.compute_trust_ema(client_id, cosine_dist)

                if cosine_dist > _SABD_THRESHOLD:
                    # Outlier: set trust to 0, mark rejected
                    self._trust_scores[client_id] = 0.0
                    rejected_ids.append(client_id)
                    logger.info(
                        "Layer 2 REJECTED: project=%s client=%s cosine_dist=%.4f",
                        self.project_id, client_id, cosine_dist,
                    )
                else:
                    accepted.append(u)

            self._outlier_rejected = rejected_ids
            return accepted, rejected_ids

        except Exception as exc:
            logger.error("layer2_sabd error: project=%s err=%s", self.project_id, exc)
            # On error, pass everything through (fail-open)
            return updates, []

    # ------------------------------------------------------------------
    # Trust & staleness tracking
    # ------------------------------------------------------------------

    def compute_trust_ema(self, client_id: str, cosine_dist: float) -> float:
        """Update and return the EMA trust score for a client.

        trust_new = (1 - alpha) * trust_old + alpha * (1 - cosine_dist)
        Clamped to [0.0, 1.0].
        """
        instant_trust = max(0.0, 1.0 - cosine_dist)
        prev = self._trust_scores.get(client_id, 1.0)
        new_trust = (1.0 - _TRUST_EMA_ALPHA) * prev + _TRUST_EMA_ALPHA * instant_trust
        new_trust = max(0.0, min(1.0, new_trust))
        self._trust_scores[client_id] = new_trust
        return new_trust

    def compute_staleness(
        self,
        client_id: str,
        global_round_received: int,
    ) -> Tuple[int, float]:
        """Compute staleness and decay weight for an incoming update.

        staleness       = max(0, global_round - global_round_received)
        staleness_weight = 1 / (1 + decay_base * staleness)

        Returns:
            (staleness, staleness_weight)
        """
        staleness = max(0, self._global_round - global_round_received)
        weight = 1.0 / (1.0 + _STALENESS_DECAY_BASE * staleness)
        self._staleness_values[client_id] = staleness
        self._staleness_weights[client_id] = round(weight, 6)
        return staleness, weight

    def set_global_round(self, round_num: int) -> None:
        """Called by the coordinator at the start of each round."""
        self._global_round = round_num

    # ------------------------------------------------------------------
    # Main entry point: process_weight_update (runs through Layer 1)
    # ------------------------------------------------------------------

    def process_weight_update(self, msg: dict) -> dict:
        """Process an incoming weight_update WebSocket message through Layer 1.

        Layer 2 runs at round boundary when all pending updates are collected.

        Args:
            msg: Parsed weight_update dict from the WebSocket message.

        Returns:
            dict with:
              status    : "accepted" | "rejected_l1" | "error"
              client_id : str
              norm      : float
              threshold : float
              reason    : str  (only on rejection/error)
        """
        client_id = msg.get("client_id", "unknown")
        weights_b64 = msg.get("weights", "")
        global_round_received = int(msg.get("global_round_received", self._global_round))
        num_samples = int(msg.get("num_samples", 100))
        local_loss = float(msg.get("local_loss", 0.0))
        task = msg.get("task", "")
        round_num = int(msg.get("round_num", 0))

        # Compute staleness metadata
        staleness, staleness_weight = self.compute_staleness(client_id, global_round_received)

        # Decode weights
        weights = self.decode_weights(weights_b64)
        if weights is None:
            logger.warning("Could not decode weights: project=%s client=%s", self.project_id, client_id)
            return {
                "status": "error",
                "client_id": client_id,
                "norm": 0.0,
                "threshold": self.get_l2_threshold(),
                "reason": "weight_decode_failed",
            }

        # --- Layer 1: L2 Norm Gatekeeper ---
        passes, norm = self.layer1_gatekeeper(client_id, weights)
        threshold = self.get_l2_threshold()

        if not passes:
            return {
                "status": "rejected_l1",
                "client_id": client_id,
                "norm": round(norm, 6),
                "threshold": threshold,
                "reason": "l2_norm_exceeded",
            }

        # Passes Layer 1 — queue for Layer 2 + aggregation at round boundary
        self._pending_updates.append({
            "client_id": client_id,
            "weights": weights,
            "num_samples": num_samples,
            "local_loss": local_loss,
            "staleness": staleness,
            "staleness_weight": staleness_weight,
            "task": task,
            "round_num": round_num,
            "norm": norm,
        })

        logger.info(
            "Layer 1 ACCEPTED: project=%s client=%s norm=%.4f staleness=%d pending=%d",
            self.project_id, client_id, norm, staleness, len(self._pending_updates),
        )

        return {
            "status": "accepted",
            "client_id": client_id,
            "norm": round(norm, 6),
            "threshold": threshold,
        }

    # ------------------------------------------------------------------
    # Round boundary helpers
    # ------------------------------------------------------------------

    def drain_pending_updates(self) -> List[dict]:
        """Return and clear the list of updates that passed Layer 1."""
        updates = self._pending_updates[:]
        self._pending_updates = []
        return updates

    def get_and_clear_gatekeeper_rejected(self) -> List[str]:
        """Return and clear the current round's Layer 1 rejection list."""
        rejected = self._gatekeeper_rejected[:]
        self._gatekeeper_rejected = []
        return rejected

    def clear_round_state(self) -> None:
        """Reset transient round-level state (call at start of each round)."""
        self._outlier_rejected = []

    # ------------------------------------------------------------------
    # Message builders
    # ------------------------------------------------------------------

    def build_rejected_msg(
        self,
        client_id: str,
        task: str,
        round_num: int,
        norm: float,
        threshold: float,
    ) -> dict:
        """Build the `rejected` direct message for an offending client."""
        return {
            "type": "rejected",
            "client_id": client_id,
            "task": task,
            "reason": "l2_norm_exceeded",
            "round_num": round_num,
            "norm": round(norm, 6),
            "threshold": round(threshold, 6),
        }

    def build_trust_report_msg(
        self,
        task: str,
        round_num: int,
        node_updates: List[dict],
        gatekeeper_rejected: List[str],
    ) -> dict:
        """Build the `trust_report` broadcast message.

        Merges trust data from real FL clients (tracked in _trust_scores) with
        simulated node data from the coordinator's node_updates list.

        Args:
            task:                Task identifier (e.g. "femnist").
            round_num:           Current global round number.
            node_updates:        List of per-node dicts from _execute_round
                                 (each has 'node_id', 'cosine_distance', 'is_byzantine').
            gatekeeper_rejected: Client IDs rejected by Layer 1 this round.

        Returns:
            trust_report message dict matching WEBSOCKET_SCHEMA.md.
        """
        trust_scores: Dict[str, float] = {}
        staleness_values: Dict[str, int] = {}
        staleness_weights: Dict[str, float] = {}
        rejected_clients: List[str] = list(self._outlier_rejected)

        # Populate from simulated node_updates (coordinator data)
        for upd in node_updates:
            nid = upd.get("node_id", "")
            if not nid:
                continue

            cosine_dist = float(upd.get("cosine_distance", 0.0))

            # Use processor's EMA trust if we have it, else derive from cosine distance
            trust = self._trust_scores.get(nid, max(0.0, 1.0 - cosine_dist))
            trust_scores[nid] = round(trust, 4)
            staleness_values[nid] = self._staleness_values.get(nid, 0)
            staleness_weights[nid] = self._staleness_weights.get(nid, 1.0)

            # Flag simulated outlier nodes in rejected_clients too
            if cosine_dist > _SABD_THRESHOLD and nid not in rejected_clients:
                rejected_clients.append(nid)

        # Overlay with real FL client state (overrides simulated values when they match)
        for client_id, trust in self._trust_scores.items():
            trust_scores[client_id] = round(trust, 4)
        for client_id, staleness in self._staleness_values.items():
            staleness_values[client_id] = staleness
        for client_id, weight in self._staleness_weights.items():
            staleness_weights[client_id] = weight

        return {
            "type": "trust_report",
            "task": task,
            "round": round_num,
            "trust_scores": trust_scores,
            "staleness_values": staleness_values,
            "staleness_weights": staleness_weights,
            "rejected_clients": rejected_clients,
            "gatekeeper_rejected": gatekeeper_rejected,
        }

    def build_global_model_msg(
        self,
        task: str,
        round_num: int,
        global_weights: Dict[str, np.ndarray],
        personalization_alpha: float = 0.0,
        assigned_chunk: Optional[int] = None,
    ) -> dict:
        """Build the `global_model` broadcast message.

        Args:
            task:                  Task identifier.
            round_num:             Current global round number.
            global_weights:        Aggregated model weights from the coordinator.
            personalization_alpha: Blend coefficient (0=pure global, 1=pure local).
            assigned_chunk:        Optional data-chunk index assigned to client.

        Returns:
            global_model message dict matching WEBSOCKET_SCHEMA.md.
        """
        return {
            "type": "global_model",
            "task": task,
            "round_num": round_num,
            "weights": self.encode_weights(global_weights),
            "version": str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "assigned_chunk": assigned_chunk,
            "personalization_alpha": round(personalization_alpha, 4),
        }


# --------------------------------------------------------------------------
# Module-level per-project registry
# --------------------------------------------------------------------------

_processors: Dict[str, FLWeightProcessor] = {}


def get_fl_processor(
    project_id: str,
    config: Optional[dict] = None,
) -> FLWeightProcessor:
    """Return (lazily creating) the FLWeightProcessor for a project."""
    if project_id not in _processors:
        _processors[project_id] = FLWeightProcessor(project_id, config or {})
    elif config is not None:
        _processors[project_id].config = config
    return _processors[project_id]


def remove_fl_processor(project_id: str) -> None:
    """Remove the processor for a project (call on project reset/delete)."""
    _processors.pop(project_id, None)
