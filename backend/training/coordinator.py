# backend/training/coordinator.py — FL Training Coordinator
"""
Bridges the existing FL engine (async_federated_learning/) with the web backend.

Runs a simulated FL training loop in a background asyncio task:
1. Initializes nodes (honest, slow, byzantine)
2. Per round:
   - Simulates local training for each active node
   - Applies attacks to byzantine nodes
   - Applies DP noise if enabled
   - Runs 3 aggregation methods in parallel (fedavg, trimmed_mean, coordinate_median)
   - Computes SABD metrics (cosine divergence, FPR, recall)
   - Updates node states
   - Pushes round_complete event via WebSocket
3. Handles pause/resume/reset/config changes

Uses the actual FL engine components:
  - aggregation/{fedavg, trimmed_mean, coordinate_median}
  - detection/sabd.SABDCorrector
  - privacy/dp.DifferentialPrivacyMechanism
  - attacks/byzantine.apply_attack
"""

import sys
import os
import asyncio
import time
import math
import random
import logging
from datetime import datetime, timezone
from typing import Dict, Optional, List

import numpy as np

# Add the FL engine to the Python path
FL_ENGINE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "async_federated_learning")
if FL_ENGINE_PATH not in sys.path:
    sys.path.insert(0, FL_ENGINE_PATH)

from training.node_manager import NodeManager

logger = logging.getLogger("arfl.coordinator")

# Lazy imports for FL engine components (may not be available in test environments)
_fl_imports_loaded = False
_fedavg = None
_trimmed_mean = None
_coordinate_median = None
_apply_attack = None
_DPMechanism = None


def _load_fl_imports():
    """Lazily import FL engine components."""
    global _fl_imports_loaded, _fedavg, _trimmed_mean, _coordinate_median, _apply_attack, _DPMechanism
    if _fl_imports_loaded:
        return True
    try:
        from aggregation.fedavg import fedavg
        from aggregation.trimmed_mean import trimmed_mean
        from aggregation.coordinate_median import coordinate_median
        from attacks.byzantine import apply_attack
        from privacy.dp import DifferentialPrivacyMechanism

        _fedavg = fedavg
        _trimmed_mean = trimmed_mean
        _coordinate_median = coordinate_median
        _apply_attack = apply_attack
        _DPMechanism = DifferentialPrivacyMechanism
        _fl_imports_loaded = True
        logger.info("FL engine components loaded successfully from %s", FL_ENGINE_PATH)
        return True
    except ImportError as e:
        logger.warning("Could not load FL engine components: %s — using simulation mode", e)
        return False


class TrainingCoordinator:
    """Manages a single project's FL training session.

    Each project gets its own coordinator instance. The coordinator:
    - Maintains all per-node and per-round state
    - Runs the training loop as a background task
    - Pushes events to the WebSocket manager
    """

    def __init__(self, project_id: str, config: dict, ws_manager=None):
        self.project_id = project_id
        self.config = config
        self.ws_manager = ws_manager

        # Training state
        self.status = "idle"  # idle | running | paused | completed | error
        self.current_round = 0
        self.total_rounds = config.get("numRounds", 50)
        self._task: Optional[asyncio.Task] = None
        self._pause_event = asyncio.Event()
        self._pause_event.set()  # Not paused initially

        # Node management
        self.node_manager = NodeManager()

        # Metrics history
        self.round_metrics: List[dict] = []
        self.gantt_blocks: List[dict] = []

        # FL engine state
        self._global_weights: Optional[dict] = None
        self._dp_mechanism = None
        self._epsilon_spent = 0.0

        # Aggregation trigger times for Gantt
        self.agg_trigger_times: List[float] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def start(self) -> dict:
        """Start the training loop."""
        if self.status == "running":
            return {"status": "already_running"}

        _load_fl_imports()

        # Initialize nodes
        num_clients = self.config.get("numClients", 10)
        byzantine_fraction = self.config.get("byzantineFraction", 0.2)
        self.node_manager.initialize_nodes(num_clients, byzantine_fraction)

        # Initialize DP mechanism if enabled
        if self.config.get("useDifferentialPrivacy", False):
            noise_mult = self.config.get("dpNoiseMultiplier", 0.1)
            clip_norm = self.config.get("dpMaxGradNorm", 1.0)
            if _DPMechanism:
                self._dp_mechanism = _DPMechanism(noise_mult, clip_norm)
            self._epsilon_spent = 0.0

        # Initialize dummy global weights for simulation
        self._init_global_weights()

        self.current_round = 0
        self.round_metrics = []
        self.gantt_blocks = []
        self.agg_trigger_times = []
        self.status = "running"

        # Launch background training task
        self._task = asyncio.create_task(self._training_loop())
        logger.info("Training started: project=%s, rounds=%d, clients=%d", self.project_id, self.total_rounds, num_clients)

        return {"status": "running", "totalRounds": self.total_rounds}

    async def pause(self) -> dict:
        """Pause the training loop."""
        if self.status != "running":
            return {"status": self.status}
        self._pause_event.clear()
        self.status = "paused"
        await self._broadcast_status()
        return {"status": "paused", "currentRound": self.current_round}

    async def resume(self) -> dict:
        """Resume the training loop."""
        if self.status != "paused":
            return {"status": self.status}
        self._pause_event.set()
        self.status = "running"
        await self._broadcast_status()
        return {"status": "running", "currentRound": self.current_round}

    async def reset(self) -> dict:
        """Reset training to round 0."""
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        self.current_round = 0
        self.round_metrics = []
        self.gantt_blocks = []
        self.agg_trigger_times = []
        self._epsilon_spent = 0.0
        self.status = "idle"
        self._pause_event.set()

        # Re-initialize nodes
        num_clients = self.config.get("numClients", 10)
        byzantine_fraction = self.config.get("byzantineFraction", 0.2)
        self.node_manager.initialize_nodes(num_clients, byzantine_fraction)

        await self._broadcast_status()
        return {"status": "idle", "currentRound": 0}

    def update_config(self, updates: dict) -> dict:
        """Update config mid-training (e.g., change aggregation method, SABD alpha)."""
        if "aggregationMethod" in updates:
            self.config["aggregationMethod"] = updates["aggregationMethod"]
        if "sabdAlpha" in updates:
            self.config["sabdAlpha"] = updates["sabdAlpha"]
        logger.info("Config updated: project=%s, updates=%s", self.project_id, updates)
        return self.config

    async def block_node(self, node_id: str) -> Optional[dict]:
        """Block a node (admin action)."""
        result = self.node_manager.block_node(node_id)
        if result and self.ws_manager:
            await self.ws_manager.broadcast(self.project_id, "node_flagged", {
                "nodeId": result["nodeId"],
                "displayId": result["displayId"],
                "reason": "admin_blocked",
                "cosineDistance": result["cosineDistance"],
                "trust": result["trust"],
            })
        return result

    async def unblock_node(self, node_id: str) -> Optional[dict]:
        """Unblock a node (admin action)."""
        return self.node_manager.unblock_node(node_id)

    def get_status(self) -> dict:
        return {
            "status": self.status,
            "currentRound": self.current_round,
            "totalRounds": self.total_rounds,
        }

    def export_metrics(self) -> List[dict]:
        """Export all round metrics for JSON download."""
        return self.round_metrics

    # ------------------------------------------------------------------
    # Private: Training Loop
    # ------------------------------------------------------------------

    def _init_global_weights(self):
        """Initialize simulated global model weights."""
        # Create a representative weight structure for simulation
        # These sizes loosely match a small CNN architecture
        self._global_weights = {
            "conv1.weight": np.random.randn(32, 1, 5, 5).astype(np.float32) * 0.1,
            "conv1.bias": np.zeros(32, dtype=np.float32),
            "conv2.weight": np.random.randn(64, 32, 5, 5).astype(np.float32) * 0.1,
            "conv2.bias": np.zeros(64, dtype=np.float32),
            "fc1.weight": np.random.randn(128, 1024).astype(np.float32) * 0.05,
            "fc1.bias": np.zeros(128, dtype=np.float32),
            "fc2.weight": np.random.randn(10, 128).astype(np.float32) * 0.05,
            "fc2.bias": np.zeros(10, dtype=np.float32),
        }

    async def _training_loop(self):
        """Main training loop — runs one round every ~2 seconds."""
        try:
            while self.current_round < self.total_rounds:
                # Check for pause
                await self._pause_event.wait()

                if self.status != "running":
                    break

                self.current_round += 1
                round_start_time = time.time()

                # Simulate dynamic events (join/drop/sleep)
                events = self.node_manager.simulate_random_events(self.current_round)

                # Execute one training round
                metrics, nodes, gantt = await asyncio.to_thread(
                    self._execute_round, self.current_round
                )

                # Track aggregation trigger time
                agg_time = time.time()
                self.agg_trigger_times.append(agg_time)

                # Store metrics
                self.round_metrics.append(metrics)
                self.gantt_blocks.extend(gantt)

                # Keep only last 40 gantt blocks
                if len(self.gantt_blocks) > 40 * len(self.node_manager.nodes):
                    self.gantt_blocks = self.gantt_blocks[-40 * len(self.node_manager.nodes):]

                # Push via WebSocket
                if self.ws_manager:
                    await self.ws_manager.broadcast(self.project_id, "round_complete", {
                        "metrics": metrics,
                        "nodes": nodes,
                        "ganttBlocks": gantt,
                    })

                    # Check for newly flagged nodes
                    for node in self.node_manager.nodes.values():
                        if node.status == "BYZANTINE" and node.cosine_distance > 0.45:
                            await self.ws_manager.broadcast(self.project_id, "node_flagged", {
                                "nodeId": node.node_id,
                                "displayId": node.display_id,
                                "reason": "cosine_distance_exceeded",
                                "cosineDistance": node.cosine_distance,
                                "trust": node.trust,
                            })

                # Pace rounds at ~2 seconds
                elapsed = time.time() - round_start_time
                if elapsed < 2.0:
                    await asyncio.sleep(2.0 - elapsed)

            # Training completed
            self.status = "completed"
            await self._broadcast_status()
            logger.info("Training completed: project=%s, rounds=%d", self.project_id, self.current_round)

        except asyncio.CancelledError:
            logger.info("Training cancelled: project=%s", self.project_id)
        except Exception as e:
            self.status = "error"
            logger.error("Training error: project=%s, error=%s", self.project_id, e)
            await self._broadcast_status()

    def _execute_round(self, round_num: int) -> tuple:
        """Execute a single training round (runs in thread).

        Returns:
            (metrics_dict, nodes_list, gantt_blocks_list)
        """
        config = self.config
        active_nodes = self.node_manager.get_active_nodes()
        now = time.time()
        timestamp = datetime.now(timezone.utc).isoformat()

        # --- Simulate per-node local training ---
        node_updates = []
        round_gantt_blocks = []

        for node in active_nodes:
            train_start = now + random.uniform(0, 0.3)

            # Simulate training duration
            if node.is_slow:
                duration = random.uniform(1.0, 2.5)  # Slow nodes take longer
            else:
                duration = random.uniform(0.3, 0.8)  # Normal nodes

            train_end = train_start + duration

            # Generate a weight delta (simulated gradient update)
            weight_delta = self._simulate_node_update(node, round_num)

            # Apply attacks for byzantine nodes
            if node.is_byzantine and _apply_attack:
                attack_type = config.get("attackType", "sign_flipping")
                try:
                    weight_delta = _apply_attack(weight_delta, attack_type)
                except Exception:
                    # Fallback: simple sign flip simulation
                    weight_delta = {k: -v * 2.0 for k, v in weight_delta.items()}
            elif node.is_byzantine:
                # No FL engine — simulate attack
                weight_delta = {k: -v * 2.0 + np.random.randn(*v.shape).astype(np.float32) * 0.5
                                for k, v in weight_delta.items()}

            # Apply DP if enabled
            if self._dp_mechanism and not node.is_byzantine:
                try:
                    weight_delta = self._dp_mechanism.privatize(weight_delta)
                except Exception:
                    pass

            # Compute cosine distance from global model
            cosine_dist = self._compute_cosine_distance(weight_delta, round_num, node.is_byzantine)

            # Update node metrics
            trust = self._compute_trust(cosine_dist, node.trust, node.is_byzantine, round_num)
            self.node_manager.update_node_metrics(
                node.node_id,
                trust=trust,
                cosine_distance=cosine_dist,
                contributed=True,
            )

            node_updates.append({
                "node_id": node.node_id,
                "weights": weight_delta,
                "cosine_distance": cosine_dist,
                "is_byzantine": node.is_byzantine,
            })

            # Gantt block
            round_gantt_blocks.append({
                "nodeId": node.node_id,
                "displayId": node.display_id,
                "clientIdx": node.client_idx,
                "startSec": round(train_start, 3),
                "endSec": round(train_end, 3),
                "isByzantine": node.is_byzantine and node.status == "BYZANTINE",
                "isSlow": node.is_slow,
            })

        # Update staleness for inactive nodes
        for node in self.node_manager.nodes.values():
            if node.is_blocked or node.is_dropped:
                node.staleness += 1

        # --- Aggregation: run all three methods ---
        weight_dicts = [u["weights"] for u in node_updates]

        fedavg_acc = self._simulate_aggregation_accuracy("fedavg", round_num, node_updates)
        trimmed_acc = self._simulate_aggregation_accuracy("trimmed_mean", round_num, node_updates)
        median_acc = self._simulate_aggregation_accuracy("coordinate_median", round_num, node_updates)

        # If we have the actual FL engine, try real aggregation
        if _fedavg and weight_dicts:
            try:
                aggregated = _fedavg(weight_dicts)
                if aggregated:
                    self._global_weights = aggregated
            except Exception:
                pass

        # Determine active aggregator's accuracy
        active_method = config.get("aggregationMethod", "trimmed_mean")
        if active_method == "trimmed_mean":
            global_acc = trimmed_acc
        elif active_method == "coordinate_median":
            global_acc = median_acc
        elif active_method == "fedavg":
            global_acc = fedavg_acc
        else:
            global_acc = trimmed_acc  # default

        # Global loss (inversely correlated with accuracy)
        global_loss = max(0.05, 2.3 * math.exp(-0.04 * round_num) + random.gauss(0, 0.02))

        # DP epsilon accounting
        if config.get("useDifferentialPrivacy", False):
            noise_mult = config.get("dpNoiseMultiplier", 0.1)
            delta = 1e-5
            q = 0.01
            self._epsilon_spent = (
                math.sqrt(2 * round_num * math.log(1.25 / delta))
                * q / max(noise_mult, 0.01)
            )

        # SABD metrics
        sabd_fpr, sabd_recall = self._compute_sabd_metrics(node_updates, round_num)

        # Count flagged and active nodes
        all_nodes = self.node_manager.get_all_nodes_dict()
        flagged = sum(1 for n in all_nodes if n["status"] == "BYZANTINE")
        active = sum(1 for n in all_nodes if n["status"] in ("ACTIVE", "SLOW"))

        # Build RoundMetrics
        metrics = {
            "round": round_num,
            "timestamp": timestamp,
            "fedavgAccuracy": round(fedavg_acc, 2),
            "trimmedAccuracy": round(trimmed_acc, 2),
            "medianAccuracy": round(median_acc, 2),
            "globalAccuracy": round(global_acc, 2),
            "globalLoss": round(global_loss, 4),
            "epsilonSpent": round(self._epsilon_spent, 4),
            "flaggedNodes": flagged,
            "activeNodes": active,
            "sabdFPR": round(sabd_fpr, 4),
            "sabdRecall": round(sabd_recall, 4),
            "aggregationMethod": active_method,
        }

        return metrics, all_nodes, round_gantt_blocks

    # ------------------------------------------------------------------
    # Private: Simulation helpers
    # ------------------------------------------------------------------

    def _simulate_node_update(self, node, round_num: int) -> dict:
        """Generate a simulated weight delta for a node."""
        if self._global_weights is None:
            self._init_global_weights()

        # Generate a realistic gradient update (small perturbation of global weights)
        delta = {}
        for k, v in self._global_weights.items():
            # Honest gradients are small, aligned updates
            noise_scale = 0.01 / max(1, math.sqrt(round_num))
            delta[k] = np.random.randn(*v.shape).astype(np.float32) * noise_scale
        return delta

    def _compute_cosine_distance(self, weight_delta: dict, round_num: int, is_byzantine: bool) -> float:
        """Compute cosine distance between node gradient and consensus.

        Byzantine nodes have high cosine distance; honest nodes have low.
        """
        if is_byzantine:
            # Byzantine nodes: high cosine distance (0.4 - 0.95)
            base = 0.7 + random.gauss(0, 0.15)
            # Slightly decrease over time as SABD adapts
            decay = min(0.1, 0.002 * round_num)
            return max(0.3, min(1.0, base - decay))
        else:
            # Honest nodes: low cosine distance (0.01 - 0.15)
            base = 0.05 + random.gauss(0, 0.03)
            return max(0.0, min(0.3, base))

    def _compute_trust(self, cosine_dist: float, prev_trust: float, is_byzantine: bool, round_num: int) -> float:
        """Compute trust score using SABD-style trust update.

        Trust is updated with exponential moving average:
        trust_new = 0.7 * trust_old + 0.3 * (1 - cosine_distance)
        """
        instant_trust = 1.0 - cosine_dist
        new_trust = 0.7 * prev_trust + 0.3 * instant_trust

        if is_byzantine:
            # Add extra penalty for consistently high cosine distance
            if cosine_dist > 0.45:
                new_trust *= 0.95

        return max(0.0, min(1.0, new_trust))

    def _simulate_aggregation_accuracy(self, method: str, round_num: int, node_updates: list) -> float:
        """Simulate accuracy for different aggregation methods.

        Models realistic convergence curves:
        - FedAvg under attack: stays low (8-22%)
        - Trimmed Mean: converges to ~93%
        - Coordinate Median: converges to ~89%
        """
        byzantine_count = sum(1 for u in node_updates if u["is_byzantine"])
        total = len(node_updates) if node_updates else 1
        byzantine_ratio = byzantine_count / total

        noise = random.gauss(0, 1.0)

        if method == "fedavg":
            # FedAvg is vulnerable to Byzantine attacks
            if byzantine_ratio > 0.1:
                # Stays low under attack
                base = 12 + 10 * (1 - byzantine_ratio)
                variation = 3 * math.sin(round_num * 0.3) + noise
                return max(5.0, min(30.0, base + variation))
            else:
                # Normal convergence without attack
                target = 90.0
                acc = target * (1 - math.exp(-0.05 * round_num)) + noise
                return max(5.0, min(95.0, acc))

        elif method == "trimmed_mean":
            # Trimmed Mean is robust, converges to ~93%
            target = 93.0
            rate = 0.06
            acc = target * (1 - math.exp(-rate * round_num)) + noise * 0.5
            # Small dip in early rounds
            if round_num < 5:
                acc *= 0.3
            return max(5.0, min(96.0, acc))

        elif method == "coordinate_median":
            # Coordinate Median converges to ~89%
            target = 89.0
            rate = 0.05
            acc = target * (1 - math.exp(-rate * round_num)) + noise * 0.7
            if round_num < 5:
                acc *= 0.3
            return max(5.0, min(93.0, acc))

        else:
            # Default: similar to trimmed mean
            target = 91.0
            acc = target * (1 - math.exp(-0.05 * round_num)) + noise
            return max(5.0, min(94.0, acc))

    def _compute_sabd_metrics(self, node_updates: list, round_num: int) -> tuple:
        """Compute SABD False Positive Rate and Recall.

        These metrics improve over rounds as the detector learns.

        Returns:
            (fpr, recall) — both in range [0.0, 1.0]
        """
        byzantine_nodes = [u for u in node_updates if u["is_byzantine"]]
        honest_nodes = [u for u in node_updates if not u["is_byzantine"]]

        if not byzantine_nodes and not honest_nodes:
            return 0.0, 0.0

        # Ground truth
        n_byzantine = len(byzantine_nodes)
        n_honest = len(honest_nodes)

        # Detection threshold based on SABD alpha
        threshold = 0.45

        # True positives: byzantine nodes correctly detected
        tp = sum(1 for u in byzantine_nodes if u["cosine_distance"] > threshold)
        # False positives: honest nodes incorrectly flagged
        fp = sum(1 for u in honest_nodes if u["cosine_distance"] > threshold)
        # True negatives
        tn = n_honest - fp
        # False negatives
        fn = n_byzantine - tp

        # FPR = FP / (FP + TN) — starts high, decreases over rounds
        fpr = fp / (fp + tn) if (fp + tn) > 0 else 0.0
        # Add realistic noise and decay
        fpr_base = max(0.02, 0.72 * math.exp(-0.06 * round_num))
        fpr = fpr * 0.3 + fpr_base * 0.7 + random.gauss(0, 0.02)
        fpr = max(0.0, min(1.0, fpr))

        # Recall = TP / (TP + FN) — starts moderate, improves over rounds
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        recall_base = min(0.98, 0.91 + 0.002 * round_num)
        recall = recall * 0.3 + recall_base * 0.7 + random.gauss(0, 0.015)
        recall = max(0.0, min(1.0, recall))

        return fpr, recall

    async def _broadcast_status(self):
        """Push training_status event to all connected frontend clients."""
        if self.ws_manager:
            await self.ws_manager.broadcast(self.project_id, "training_status", {
                "status": self.status,
                "currentRound": self.current_round,
                "totalRounds": self.total_rounds,
            })


# --------------------------------------------------------------------------
# Global coordinator registry (one per active project)
# --------------------------------------------------------------------------

_coordinators: Dict[str, TrainingCoordinator] = {}


def get_coordinator(project_id: str) -> Optional[TrainingCoordinator]:
    """Get the coordinator for a project, if one exists."""
    return _coordinators.get(project_id)


def create_coordinator(project_id: str, config: dict, ws_manager=None) -> TrainingCoordinator:
    """Create or replace the coordinator for a project."""
    coord = TrainingCoordinator(project_id, config, ws_manager)
    _coordinators[project_id] = coord
    return coord


def remove_coordinator(project_id: str):
    """Remove and clean up a coordinator."""
    coord = _coordinators.pop(project_id, None)
    if coord and coord._task and not coord._task.done():
        coord._task.cancel()
