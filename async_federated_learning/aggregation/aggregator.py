# aggregation/aggregator.py — Factory and router for aggregation strategies
"""
aggregation/aggregator.py
=========================
Contains:
- get_aggregator(): returns a callable matching the unified interface
  (updates, weights=None) -> dict for a given method name string.
- list_available_methods(): returns sorted list of valid method names.
- Aggregator: legacy class kept for backward compatibility with tests.
"""

import logging
import math
import time

import numpy as np

from aggregation.coordinate_median import coordinate_median
from aggregation.fedavg import fedavg
from aggregation.reputation import reputation_aggregated
from aggregation.staleness import compute_staleness_weights, combine_trust_weights
from aggregation.trimmed_mean import trimmed_mean
from detection.gatekeeper import Gatekeeper
from detection.sabd import run_sabd
from detection.outlier_filter import OutlierFilter

logger = logging.getLogger(__name__)

_AVAILABLE_METHODS = ["coordinate_median", "fedavg", "reputation", "staleness_aware", "trimmed_mean"]


def get_aggregator(method_name: str, config=None):
    """Return the aggregation callable for the requested strategy.

    All returned callables conform to:
        aggregator(updates: list, weights: list = None) -> dict

    Parameters
    ----------
    method_name : str — one of list_available_methods()
    config      : Config | None — used for strategy-specific hyperparameters

    Returns
    -------
    callable — fn(updates, weights=None) -> dict
    """
    name = method_name.strip().lower()

    if name == "fedavg":
        logger.info("Aggregator: fedavg (not Byzantine-robust).")
        return fedavg

    if name == "trimmed_mean":
        beta = getattr(config, 'TRIMMED_MEAN_BETA', None) or getattr(config, 'trimmed_mean_beta', 0.1)
        logger.info("Aggregator: trimmed_mean (beta=%.2f).", beta)
        def _trimmed(updates, weights=None):
            return trimmed_mean(updates, beta=beta, _weights=weights)
        return _trimmed

    if name == "coordinate_median":
        logger.info("Aggregator: coordinate_median (breakdown point 50%%).")
        return coordinate_median

    if name == "reputation":
        logger.info("Aggregator: reputation_aggregated (SABD-aware).")
        return reputation_aggregated

    if name == "staleness_aware":
        logger.info("Aggregator: staleness_aware (staleness decay + reputation blend).")
        def _staleness_aware(updates, weights=None):
            staleness_ws = compute_staleness_weights(updates, current_round=0)
            sample_counts = [
                u.get("num_samples", 1) if isinstance(u, dict) else 1
                for u in updates
            ]
            rep_ws = weights if weights is not None else [1.0 / max(len(updates), 1)] * len(updates)
            combined = combine_trust_weights(staleness_ws, rep_ws, sample_counts)
            weight_dicts = [u["weights"] if isinstance(u, dict) else u for u in updates]
            return fedavg(weight_dicts, weights=combined)
        return _staleness_aware

    raise ValueError(
        f"Unknown aggregation method '{method_name}'. "
        f"Available: {_AVAILABLE_METHODS}"
    )


def list_available_methods() -> list:
    """Return a sorted list of all valid aggregation method name strings."""
    return list(_AVAILABLE_METHODS)


# ---------------------------------------------------------------------------
# Legacy Aggregator class (from akshat — backward compat for tests & main.py)
# ---------------------------------------------------------------------------

class AggregationResult:
    """Result of the two-layer aggregation pipeline."""
    def __init__(self, aggregated_weights=None, accepted_clients=None,
                 rejected_clients=None, strategy_used="",
                 gatekeeper_passed=None, gatekeeper_rejected=None,
                 trust_scores=None, elapsed_ms=0.0, metadata=None):
        self.aggregated_weights = aggregated_weights or {}
        self.accepted_clients = accepted_clients or []
        self.rejected_clients = rejected_clients or []
        self.strategy_used = strategy_used
        self.gatekeeper_passed = gatekeeper_passed or []
        self.gatekeeper_rejected = gatekeeper_rejected or []
        self.trust_scores = trust_scores or {}
        self.elapsed_ms = elapsed_ms
        self.metadata = metadata or {}

    @property
    def accepted_count(self):
        return len(self.accepted_clients)


class Aggregator:
    """Legacy two-layer aggregation pipeline (check_l2_norm -> strategy).

    Kept for backward compatibility with existing tests and main.py.
    New code should use get_aggregator() factory instead.
    """

    def __init__(self, strategy: str, config):
        self.strategy = strategy.lower()
        self.config = config
        self._trust_history = {}
        
        # Initialize the stateful Gatekeeper
        l2_factor = getattr(self.config, 'gatekeeper_l2_factor', 3.0)
        max_l2 = getattr(self.config, 'gatekeeper_max_threshold', 1000.0)
        self.gatekeeper = Gatekeeper(l2_threshold_factor=l2_factor, max_l2_threshold=max_l2)
        
        logger.info("Aggregator initialized: strategy=%s", self.strategy)

    @staticmethod
    def _clamp01(value: float) -> float:
        return float(max(0.0, min(1.0, value)))

    def _compute_behavior_trust(self, passed_updates: list, client_ids: list) -> dict:
        """Compute per-client behavioral trust in [0,1] from update norms.

        Lower robust z-score => higher trust.
        """
        if not passed_updates:
            return {}

        norms = []
        for u in passed_updates:
            w = u.get("weights", {})
            if not w:
                norms.append(0.0)
                continue
            flat = np.concatenate([v.flatten() for v in w.values()])
            norms.append(float(np.linalg.norm(flat)))

        n_arr = np.array(norms, dtype=float)
        median = float(np.median(n_arr))
        mad = float(np.median(np.abs(n_arr - median)))
        robust_sigma = max(1.4826 * mad, 1e-8)

        trust = {}
        for cid, norm in zip(client_ids, norms):
            z = abs(norm - median) / robust_sigma
            trust[cid] = self._clamp01(1.0 / (1.0 + z))
        return trust

    def _compose_trust_scores(
        self,
        updates: list,
        current_round: int,
        staleness_ws: list,
        behavior_trust: dict,
        rejected_ids: set,
        gatekeeper_rejected_ids: set,
    ) -> dict:
        """Unified trust score for all strategies.

        trust = EMA( (1-rho)*staleness + rho*behavior )
        where rho = STALENESS_REPUTATION_WEIGHT.
        """
        rho = float(getattr(self.config, 'STALENESS_REPUTATION_WEIGHT', 0.5))
        rho = self._clamp01(rho)
        ema_beta = float(getattr(self.config, 'TRUST_EMA_BETA', 0.7))
        ema_beta = self._clamp01(ema_beta)

        staleness_map = {
            u.get("client_id", f"c{i}"): float(staleness_ws[i])
            for i, u in enumerate(updates)
            if i < len(staleness_ws)
        }

        trust_scores = {}
        for i, u in enumerate(updates):
            cid = u.get("client_id", f"c{i}")

            if cid in gatekeeper_rejected_ids or cid in rejected_ids:
                trust_scores[cid] = 0.0
                prev = float(self._trust_history.get(cid, 0.0))
                self._trust_history[cid] = self._clamp01(prev * 0.5)
                continue

            stale = float(staleness_map.get(cid, 1.0))
            behavior = float(behavior_trust.get(cid, 1.0))
            instant = self._clamp01((1.0 - rho) * stale + rho * behavior)

            prev = float(self._trust_history.get(cid, instant))
            smoothed = self._clamp01(ema_beta * prev + (1.0 - ema_beta) * instant)
            self._trust_history[cid] = smoothed
            trust_scores[cid] = smoothed

        return trust_scores

    def aggregate(self, updates: list, current_round: int, task: str) -> AggregationResult:
        """Two-layer defense pipeline:
        Layer 1: check_l2_norm gatekeeper
        Layer 2: strategy-specific aggregation (krum, trimmed_mean, coordinate_median, fedavg)
        """
        start = time.time()
        result = AggregationResult(strategy_used=self.strategy)

        if not updates:
            logger.warning("Aggregator.aggregate: no updates to process")
            return result

        # --- Layer 1: Adaptive L2 Norm Gatekeeper ---
        # Format updates for gatekeeper
        gk_updates = [
            {'client_id': u.get("client_id", "unknown"), 'model_update': u.get("weights", {}), 'raw_update': u}
            for u in updates
        ]
        
        if getattr(self.config, 'use_gatekeeper', True):
            accepted_gk, rejected_gk, _ = self.gatekeeper.inspect_updates(gk_updates, current_round)
            passed_updates = [u['raw_update'] for u in accepted_gk]
            for u in accepted_gk:
                result.gatekeeper_passed.append(u['client_id'])
            for u in rejected_gk:
                result.gatekeeper_rejected.append(u['client_id'])
        else:
            passed_updates = updates
            for u in updates:
                result.gatekeeper_passed.append(u.get("client_id", "unknown"))

        if not passed_updates:
            logger.warning("All updates rejected by gatekeeper")
            result.elapsed_ms = (time.time() - start) * 1000
            return result

        # --- Layer 1.5: Statistical Outlier Filter ---
        if len(passed_updates) >= 3:
            outlier_filter = OutlierFilter(method='ensemble')
            _filtered, accepted_idx, rejected_idx = outlier_filter.filter_updates(
                [u["weights"] for u in passed_updates],
                client_ids=[u.get("client_id", f"c{i}") for i, u in enumerate(passed_updates)],
            )
            if rejected_idx:
                for idx in sorted(rejected_idx, reverse=True):
                    cid = passed_updates[idx].get("client_id", "unknown")
                    result.rejected_clients.append(cid)
                    logger.warning(
                        "OutlierFilter REJECTED client=%s (method=ensemble)", cid,
                    )
                passed_updates = [passed_updates[i] for i in accepted_idx]
            if not passed_updates:
                logger.warning("All updates rejected by OutlierFilter")
                result.elapsed_ms = (time.time() - start) * 1000
                return result

        # --- Staleness weights (computed for all strategies, used selectively) ---
        staleness_ws = compute_staleness_weights(
            passed_updates,
            current_round,
            decay_fn=getattr(self.config, 'STALENESS_DECAY_FN', 'polynomial'),
            lam=getattr(self.config, 'STALENESS_LAMBDA', 0.1),
            alpha=getattr(self.config, 'STALENESS_ALPHA', 0.5),
        )
        result.metadata["staleness_weights"] = {
            u.get("client_id", f"c{i}"): round(w, 4)
            for i, (u, w) in enumerate(zip(passed_updates, staleness_ws))
        }
        result.metadata["staleness_values"] = {
            u.get("client_id", f"c{i}"): max(0, current_round - u.get("global_round_received", 0))
            for i, u in enumerate(passed_updates)
        }

        # --- Layer 2: Strategy-specific aggregation ---
        weight_dicts = [u["weights"] for u in passed_updates]
        client_ids = [u.get("client_id", "unknown") for u in passed_updates]
        behavior_trust = self._compute_behavior_trust(passed_updates, client_ids)

        if self.strategy == "krum":
            sabd_result = run_sabd(
                passed_updates,
                byzantine_fraction=getattr(self.config, 'KRUM_BYZANTINE_FRACTION', 0.3),
            )
            selected_updates = [weight_dicts[i] for i in sabd_result.selected_indices]
            result.accepted_clients = [client_ids[i] for i in sabd_result.selected_indices]
            result.rejected_clients = [client_ids[i] for i in sabd_result.rejected_indices]

            if sabd_result.krum_scores:
                krum_scores = {
                    cid: float(sabd_result.krum_scores[cid])
                    for cid in client_ids
                    if cid in sabd_result.krum_scores
                }
                if krum_scores:
                    vals = list(krum_scores.values())
                    lo, hi = min(vals), max(vals)
                    if hi > lo:
                        for cid, score in krum_scores.items():
                            krum_trust = 1.0 - ((score - lo) / (hi - lo))
                            behavior_trust[cid] = self._clamp01(
                                0.5 * behavior_trust.get(cid, 1.0) + 0.5 * krum_trust
                            )
            if selected_updates:
                result.aggregated_weights = fedavg(selected_updates)
        elif self.strategy == "trimmed_mean":
            beta = getattr(self.config, 'TRIMMED_MEAN_BETA',
                          getattr(self.config, 'TRIM_FRACTION', 0.1))
            result.aggregated_weights = trimmed_mean(weight_dicts, beta=beta)
            result.accepted_clients = client_ids
        elif self.strategy == "coordinate_median":
            result.aggregated_weights = coordinate_median(weight_dicts)
            result.accepted_clients = client_ids
        elif self.strategy == "fedavg":
            sample_weights = [u.get("num_samples", 1) for u in passed_updates]
            result.aggregated_weights = fedavg(weight_dicts, weights=sample_weights)
            result.accepted_clients = client_ids
        elif self.strategy == "staleness_aware":
            rep_weights = [
                max(0.01, behavior_trust.get(cid, 1.0))
                for cid in client_ids
            ]
            sample_counts = [u.get("num_samples", 1) for u in passed_updates]
            rep_blend = getattr(self.config, 'STALENESS_REPUTATION_WEIGHT', 0.5)
            combined_weights = combine_trust_weights(
                staleness_ws, rep_weights, sample_counts, rep_blend=rep_blend
            )
            total = sum(combined_weights)
            if total <= 0:
                logger.warning("staleness_aware: combined weights sum to zero, falling back to fedavg")
                result.aggregated_weights = fedavg(weight_dicts)
            else:
                result.aggregated_weights = fedavg(weight_dicts, weights=combined_weights)
            result.accepted_clients = client_ids
            result.metadata["reputation_weights"] = {
                cid: round(w, 4)
                for cid, w in zip(client_ids, rep_weights)
            }
        elif self.strategy == "reputation":
            rep_weights = [
                max(0.01, behavior_trust.get(cid, 1.0))
                for cid in client_ids
            ]
            sample_counts = [u.get("num_samples", 1) for u in passed_updates]
            rep_blend = getattr(self.config, 'STALENESS_REPUTATION_WEIGHT', 0.5)
            combined_weights = combine_trust_weights(
                staleness_ws, rep_weights, sample_counts, rep_blend=rep_blend
            )
            total = sum(combined_weights)
            if total <= 0:
                logger.warning("reputation: combined weights sum to zero, falling back to fedavg")
                result.aggregated_weights = fedavg(weight_dicts)
            else:
                result.aggregated_weights = fedavg(weight_dicts, weights=combined_weights)
            result.accepted_clients = client_ids
            result.metadata["reputation_weights"] = {
                cid: round(w, 4)
                for cid, w in zip(client_ids, rep_weights)
            }
        else:
            logger.warning("Unknown strategy '%s', falling back to fedavg", self.strategy)
            result.aggregated_weights = fedavg(weight_dicts)
            result.accepted_clients = client_ids

        result.trust_scores = self._compose_trust_scores(
            updates=updates,
            current_round=current_round,
            staleness_ws=staleness_ws,
            behavior_trust=behavior_trust,
            rejected_ids=set(result.rejected_clients),
            gatekeeper_rejected_ids=set(result.gatekeeper_rejected),
        )

        result.elapsed_ms = (time.time() - start) * 1000
        logger.info(
            "Aggregation complete: strategy=%s, accepted=%d, rejected=%d, elapsed=%.1fms",
            self.strategy, len(result.accepted_clients),
            len(result.rejected_clients), result.elapsed_ms,
        )
        return result
