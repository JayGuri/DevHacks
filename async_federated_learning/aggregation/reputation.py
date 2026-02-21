# aggregation/reputation.py — SABD-aware reputation-weighted aggregation
"""
aggregation/reputation.py
=========================
Reputation-weighted average using SABD-corrected divergence scores.
Falls back to trimmed_mean when no meaningful reputation signal exists.
"""

import logging

import numpy as np

from aggregation.trimmed_mean import trimmed_mean

logger = logging.getLogger(__name__)


def reputation_aggregated(
    updates: list,
    weights: list = None,
    staleness_weights: list = None,
    rep_blend: float = 0.5,
) -> dict:
    """Reputation-weighted aggregation with optional staleness blending.

    Case 1 — staleness_weights provided: combines staleness decay and reputation
              via geometric mean blend, then does a weighted average.
    Case 2 — weights is None or all equal: falls back to trimmed_mean(beta=0.1).
    Case 3 — weights contain variation: weighted average with normalised weights.

    Parameters
    ----------
    updates           : list[dict[str, np.ndarray]] — per-client weight deltas
    weights           : list[float] | None — reputation scores (higher = more trusted)
    staleness_weights : list[float] | None — staleness decay weights from staleness.py
    rep_blend         : float in [0, 1] — 0=pure staleness, 1=pure reputation

    Returns
    -------
    dict[str, np.ndarray] — aggregated parameter dict
    """
    if not updates:
        raise ValueError("reputation_aggregated: 'updates' list is empty.")

    n = len(updates)

    # When staleness weights are provided, blend them with reputation scores
    if staleness_weights is not None and len(staleness_weights) == n:
        from aggregation.staleness import combine_trust_weights
        sample_counts = [
            u.get("num_samples", 1) if isinstance(u, dict) else 1
            for u in updates
        ]
        rep_ws = weights if weights is not None else [1.0 / n] * n
        combined = combine_trust_weights(staleness_weights, rep_ws, sample_counts, rep_blend)
        total = sum(combined)
        if total <= 0:
            logger.debug("reputation_aggregated (staleness blend) — weights sum to zero; falling back to trimmed_mean.")
            return trimmed_mean(updates, beta=0.1)
        norm_weights = [w / total for w in combined]
        result = {}
        for key in updates[0].keys():
            result[key] = sum(float(norm_weights[i]) * updates[i][key] for i in range(n))
        logger.debug(
            "reputation_aggregated (staleness blend) — %d clients, rep_blend=%.2f",
            n, rep_blend,
        )
        return result

    n = len(updates)

    if weights is None:
        logger.debug("reputation_aggregated — no weights; falling back to trimmed_mean.")
        return trimmed_mean(updates, beta=0.1)

    if len(weights) != n:
        raise ValueError(
            f"reputation_aggregated: len(weights)={len(weights)} != len(updates)={n}."
        )

    w_arr = np.array(weights, dtype=float)

    if np.allclose(w_arr, w_arr[0]):
        logger.debug(
            "reputation_aggregated — all weights equal (%.4f); falling back to trimmed_mean.",
            w_arr[0],
        )
        return trimmed_mean(updates, beta=0.1)

    total = w_arr.sum()
    if total <= 0:
        raise ValueError("reputation_aggregated: reputation weights sum to zero or negative.")

    norm_weights = w_arr / total

    result = {}
    for key in updates[0].keys():
        result[key] = sum(
            float(norm_weights[i]) * updates[i][key]
            for i in range(n)
        )

    logger.debug(
        "reputation_aggregated — %d clients, weight range [%.4f, %.4f], "
        "entropy=%.4f bits.",
        n, float(norm_weights.min()), float(norm_weights.max()),
        float(-np.sum(norm_weights * np.log2(norm_weights + 1e-12))),
    )
    return result
