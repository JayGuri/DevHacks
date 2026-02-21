# aggregation/staleness.py — Staleness decay functions and combined trust weight computation
"""
Staleness-Aware Trust Weighting for Async FL.

Core principle: updates computed from older global model versions are less
reliable. Their contribution to aggregation is down-weighted by a decay
function of their staleness.

    staleness(update) = current_round - update["global_round_received"]

Two decay functions (controlled by config.STALENESS_DECAY_FN):
  - exponential: w = exp(-lambda * staleness)
  - polynomial:  w = 1.0 / (1.0 + staleness) ** alpha

Final combined weight per update:
    combined = staleness_weight^(1-rep_blend) * reputation_weight^rep_blend * num_samples
"""

import math
import logging

logger = logging.getLogger(__name__)


def compute_staleness(update: dict, current_round: int) -> int:
    """Return staleness of an update: current_round - global_round_received.
    Clamps to 0 if negative (e.g., round counter hasn't advanced yet).
    """
    received_at = update.get("global_round_received", 0)
    return max(0, current_round - received_at)


def staleness_weight_exponential(staleness: int, lam: float = 0.1) -> float:
    """Exponential decay: w = exp(-lambda * staleness).

    staleness=0  -> w=1.0
    staleness=10, lam=0.1 -> w≈0.368
    staleness=50, lam=0.1 -> w≈0.007
    """
    return math.exp(-lam * staleness)


def staleness_weight_polynomial(staleness: int, alpha: float = 0.5) -> float:
    """Polynomial decay: w = 1 / (1 + staleness)^alpha.

    staleness=0 -> w=1.0
    staleness=9, alpha=0.5 -> w≈0.316
    staleness=99, alpha=0.5 -> w=0.1
    """
    return 1.0 / ((1.0 + staleness) ** alpha)


def compute_staleness_weights(
    updates: list,
    current_round: int,
    decay_fn: str = "polynomial",
    lam: float = 0.1,
    alpha: float = 0.5,
) -> list:
    """Compute per-update staleness weights (unnormalized, in (0, 1]).

    Parameters
    ----------
    updates       : list of update dicts (must have "global_round_received")
    current_round : server's current round counter
    decay_fn      : "exponential" | "polynomial"
    lam           : lambda for exponential decay
    alpha         : exponent for polynomial decay

    Returns
    -------
    list[float] — one weight per update
    """
    weights = []
    for u in updates:
        s = compute_staleness(u, current_round)
        if decay_fn == "exponential":
            w = staleness_weight_exponential(s, lam)
        else:
            w = staleness_weight_polynomial(s, alpha)
        weights.append(w)
        logger.debug(
            "staleness_weight: client=%s staleness=%d weight=%.4f",
            u.get("client_id", "?"), s, w,
        )
    return weights


def combine_trust_weights(
    staleness_weights: list,
    reputation_weights: list,
    sample_counts: list,
    rep_blend: float = 0.5,
) -> list:
    """Combine staleness decay, reputation score, and sample count.

    Final weight per client:
        trust_i = staleness_i^(1-rep_blend) * reputation_i^rep_blend
        combined_i = trust_i * num_samples_i

    rep_blend=0.0 -> pure staleness weighting
    rep_blend=1.0 -> pure reputation weighting
    rep_blend=0.5 -> geometric mean of both signals, scaled by samples

    The geometric mean ensures a Byzantine client must pass BOTH checks to
    receive a meaningful weight.

    Parameters
    ----------
    staleness_weights   : list[float] from compute_staleness_weights()
    reputation_weights  : list[float] from AnomalyDetector.get_reputation_weights()
    sample_counts       : list[int]
    rep_blend           : float in [0, 1]

    Returns
    -------
    list[float] — combined weights, NOT yet normalized
    """
    combined = []
    for i, (s_w, r_w, n_samples) in enumerate(
        zip(staleness_weights, reputation_weights, sample_counts)
    ):
        n = max(1, n_samples)
        trust = (s_w ** (1.0 - rep_blend)) * (r_w ** rep_blend)
        combined.append(trust * n)
        logger.debug(
            "combine_trust: i=%d staleness_w=%.4f rep_w=%.4f samples=%d combined=%.4f",
            i, s_w, r_w, n, combined[-1],
        )
    return combined
