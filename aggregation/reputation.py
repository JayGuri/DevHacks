# aggregation/reputation.py — Staleness-based reputation/weight scoring
import logging

logger = logging.getLogger("fedbuff.aggregation.reputation")


def compute_staleness_weight(
    global_round_received: int,
    current_global_round: int,
    alpha: float,
    max_staleness: int,
) -> float:
    """
    Computes a reputation weight for an update based on its staleness.
    staleness = current_global_round - global_round_received
    If staleness > max_staleness: return 0.0 (update rejected as too stale).
    Otherwise: return 1.0 / (1.0 + alpha * staleness)
    A fresh update (staleness=0) returns 1.0.
    """
    staleness = current_global_round - global_round_received
    if staleness > max_staleness:
        logger.debug(
            "Update too stale: staleness=%d > max=%d, weight=0.0",
            staleness, max_staleness,
        )
        return 0.0
    weight = 1.0 / (1.0 + alpha * staleness)
    logger.debug(
        "Staleness weight: staleness=%d, alpha=%.2f, weight=%.4f",
        staleness, alpha, weight,
    )
    return weight


def compute_sample_reputation_weights(updates: list) -> dict:
    """
    Returns a dict {client_id: weight} normalised so weights sum to 1.0.
    Weight for each client = num_samples_i / sum(num_samples).
    Used by FedAvg and as a component in combined staleness+sample weighting.
    """
    total_samples = sum(u["num_samples"] for u in updates)
    if total_samples == 0:
        n = len(updates)
        return {u["client_id"]: 1.0 / n for u in updates} if n > 0 else {}

    weights = {}
    for u in updates:
        weights[u["client_id"]] = u["num_samples"] / total_samples
    return weights


def compute_combined_weights(
    updates: list,
    current_round: int,
    alpha: float,
    max_staleness: int,
) -> dict:
    """
    Returns {client_id: weight} combining staleness weight and sample count.
    combined_weight_i = staleness_weight_i * num_samples_i
    Normalised so weights sum to 1.0.
    Updates with staleness_weight == 0.0 are excluded (weight set to 0.0).
    """
    raw_weights = {}
    for u in updates:
        s_weight = compute_staleness_weight(
            u.get("global_round_received", current_round),
            current_round,
            alpha,
            max_staleness,
        )
        raw_weights[u["client_id"]] = s_weight * u["num_samples"]

    total = sum(raw_weights.values())
    if total == 0:
        n = len(updates)
        return {u["client_id"]: 1.0 / n for u in updates} if n > 0 else {}

    normalized = {}
    for cid, w in raw_weights.items():
        normalized[cid] = w / total
    return normalized
