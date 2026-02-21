# aggregation/aggregator.py — Orchestrator: calls Gatekeeper, then selected strategy
import logging
import numpy as np
from dataclasses import dataclass, field

from detection.anomaly import check_l2_norm
from detection.sabd import run_sabd
from aggregation.fedavg import fedavg
from aggregation.coordinate_median import coordinate_median
from aggregation.trimmed_mean import trimmed_mean
from aggregation.reputation import compute_staleness_weight, compute_combined_weights

logger = logging.getLogger("fedbuff.aggregation")


@dataclass
class AggregationResult:
    aggregated_weights: dict = field(default_factory=dict)
    trust_scores: dict = field(default_factory=dict)
    rejected_clients: list = field(default_factory=list)
    gatekeeper_rejected: list = field(default_factory=list)
    accepted_count: int = 0
    round_num: int = 0
    task: str = ""
    strategy_used: str = ""


class Aggregator:
    """Central aggregation orchestrator with two-layer defense pipeline."""

    def __init__(self, strategy: str, config):
        """
        strategy: one of "krum", "trimmed_mean", "coordinate_median", "fedavg"
        config: the global Settings object from config.py
        """
        self.strategy = strategy
        self.config = config

    def aggregate(self, updates: list, current_round: int, task: str) -> AggregationResult:
        """
        Two-layer defense pipeline:

        LAYER 1 — Gatekeeper (detection/anomaly.py):
          For each update, call check_l2_norm(). Failed updates are rejected.

        LAYER 2 — Strategy:
          "krum"             -> run_sabd() then fedavg() on accepted subset
          "trimmed_mean"     -> trimmed_mean()
          "coordinate_median"-> coordinate_median()
          "fedavg"           -> fedavg() (no Byzantine defense)

        Returns AggregationResult.
        """
        result = AggregationResult(
            round_num=current_round,
            task=task,
            strategy_used=self.strategy,
        )
        all_trust_scores = {}

        # LAYER 1 — Gatekeeper: L2 norm pre-filter
        passed_updates = []
        for update in updates:
            client_id = update["client_id"]
            passed, norm = check_l2_norm(
                update["weights"], self.config.L2_NORM_THRESHOLD
            )
            if not passed:
                result.gatekeeper_rejected.append(client_id)
                all_trust_scores[client_id] = 0.0
                logger.warning(
                    "Gatekeeper REJECTED %s: L2 norm=%.4f > threshold=%.4f (task=%s, round=%d)",
                    client_id, norm, self.config.L2_NORM_THRESHOLD, task, current_round,
                )
            else:
                passed_updates.append(update)
                logger.debug(
                    "Gatekeeper PASSED %s: L2 norm=%.4f (task=%s)", client_id, norm, task
                )

        # Handle edge case: fewer than 3 updates after gatekeeper
        if len(passed_updates) < 3:
            logger.warning(
                "Only %d updates passed Gatekeeper (< 3). task=%s, round=%d",
                len(passed_updates), task, current_round,
            )
            if len(passed_updates) == 0:
                result.accepted_count = 0
                result.trust_scores = all_trust_scores
                return result

            # IF strategy is not fedavg, we CANNOT safely fallback to fedavg. Reject the round.
            if self.strategy != "fedavg":
                logger.error("Rejecting round: Insufficient updates for robust aggregation '%s'", self.strategy)
                for u in passed_updates:
                    cid = u["client_id"]
                    all_trust_scores[cid] = 0.0
                    result.rejected_clients.append(cid)
                result.accepted_count = 0
                result.trust_scores = all_trust_scores
                return result

            # Simple weighted average for the remaining updates ONLY if strategy is fedavg
            aggregated = fedavg(
                passed_updates, current_round,
                self.config.STALENESS_ALPHA,
                self.config.MAX_STALENESS,
            )
            for u in passed_updates:
                all_trust_scores[u["client_id"]] = 1.0

            result.aggregated_weights = aggregated
            result.accepted_count = len(passed_updates)
            result.trust_scores = all_trust_scores
            return result

        # LAYER 2 — Strategy-specific aggregation
        if self.strategy == "krum":
            # Run SABD (Multi-Krum) to identify trusted updates
            sabd_result = run_sabd(
                passed_updates, self.config.KRUM_BYZANTINE_FRACTION
            )

            # Collect selected updates only
            selected_updates = [passed_updates[i] for i in sabd_result.selected_indices]
            rejected_by_sabd = [
                passed_updates[i]["client_id"] for i in sabd_result.rejected_indices
            ]

            # Trust scores from SABD
            for cid, score in sabd_result.trust_scores.items():
                all_trust_scores[cid] = score

            result.rejected_clients = rejected_by_sabd

            if selected_updates:
                aggregated = fedavg(
                    selected_updates, current_round,
                    self.config.STALENESS_ALPHA,
                    self.config.MAX_STALENESS,
                )
            else:
                aggregated = {}

        elif self.strategy == "trimmed_mean":
            aggregated, strategy_trust = trimmed_mean(
                passed_updates, self.config.TRIM_FRACTION
            )
            for cid, score in strategy_trust.items():
                all_trust_scores[cid] = score
            result.rejected_clients = [
                cid for cid, s in strategy_trust.items() if s == 0.0
            ]

        elif self.strategy == "coordinate_median":
            aggregated, strategy_trust = coordinate_median(passed_updates)
            for cid, score in strategy_trust.items():
                all_trust_scores[cid] = score

        elif self.strategy == "fedavg":
            aggregated = fedavg(
                passed_updates, current_round,
                self.config.STALENESS_ALPHA,
                self.config.MAX_STALENESS,
            )
            for u in passed_updates:
                all_trust_scores[u["client_id"]] = 1.0

        else:
            raise ValueError(f"Unknown aggregation strategy: {self.strategy}")

        result.aggregated_weights = aggregated
        result.trust_scores = all_trust_scores
        result.accepted_count = len(passed_updates) - len(result.rejected_clients)

        logger.info(
            "Aggregation complete: task=%s, round=%d, strategy=%s, "
            "gatekeeper_rejected=%s, strategy_rejected=%s, accepted=%d",
            task, current_round, self.strategy,
            result.gatekeeper_rejected, result.rejected_clients, result.accepted_count,
        )

        return result
