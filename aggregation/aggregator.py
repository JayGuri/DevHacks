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
from aggregation.trimmed_mean import trimmed_mean
from detection.anomaly import check_l2_norm
from detection.sabd import run_sabd

logger = logging.getLogger(__name__)

_AVAILABLE_METHODS = ["coordinate_median", "fedavg", "reputation", "trimmed_mean"]


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
        logger.info("Aggregator initialized: strategy=%s", self.strategy)

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

        # --- Layer 1: L2 Norm Gatekeeper ---
        threshold = getattr(self.config, 'L2_NORM_THRESHOLD', 500.0)
        passed_updates = []
        for u in updates:
            client_id = u.get("client_id", "unknown")
            weights = u.get("weights", {})
            ok, norm_val = check_l2_norm(weights, threshold)
            if ok:
                result.gatekeeper_passed.append(client_id)
                passed_updates.append(u)
            else:
                result.gatekeeper_rejected.append(client_id)
                logger.warning(
                    "Gatekeeper REJECTED client=%s (norm=%.4f > threshold=%.4f)",
                    client_id, norm_val, threshold,
                )

        if not passed_updates:
            logger.warning("All updates rejected by gatekeeper")
            result.elapsed_ms = (time.time() - start) * 1000
            return result

        # --- Layer 2: Strategy-specific aggregation ---
        weight_dicts = [u["weights"] for u in passed_updates]
        client_ids = [u.get("client_id", "unknown") for u in passed_updates]

        if self.strategy == "krum":
            sabd_result = run_sabd(
                passed_updates,
                byzantine_fraction=getattr(self.config, 'KRUM_BYZANTINE_FRACTION', 0.3),
            )
            selected_updates = [weight_dicts[i] for i in sabd_result.selected_indices]
            result.accepted_clients = [client_ids[i] for i in sabd_result.selected_indices]
            result.rejected_clients = [client_ids[i] for i in sabd_result.rejected_indices]
            result.trust_scores = sabd_result.trust_scores
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
        else:
            logger.warning("Unknown strategy '%s', falling back to fedavg", self.strategy)
            result.aggregated_weights = fedavg(weight_dicts)
            result.accepted_clients = client_ids

        result.elapsed_ms = (time.time() - start) * 1000
        logger.info(
            "Aggregation complete: strategy=%s, accepted=%d, rejected=%d, elapsed=%.1fms",
            self.strategy, len(result.accepted_clients),
            len(result.rejected_clients), result.elapsed_ms,
        )
        return result
