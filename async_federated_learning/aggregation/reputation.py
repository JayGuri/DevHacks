"""
aggregation/reputation.py
=========================
SABD-aware reputation-weighted aggregation.

Contains:
- reputation_aggregated(): weighted average using per-client reputation scores
  produced by SABD after staleness correction.  Falls back to trimmed_mean
  when no meaningful reputation signal exists (None or all-equal weights).

Design rationale
----------------
Reputation scores passed here are the post-SABD *corrected* divergence scores,
not raw staleness-confounded ones.  Using corrected scores means the weights
reflect true behavioural divergence from consensus (malice signal) rather than
a mix of malice + staleness artefacts.  This makes the weighted average both
more accurate for honest-but-stale clients and more discriminating for genuine
Byzantine clients.
"""

import logging

import numpy as np

from async_federated_learning.aggregation.trimmed_mean import trimmed_mean

logger = logging.getLogger(__name__)


def reputation_aggregated(updates: list, weights: list = None) -> dict:
    """
    Reputation-weighted aggregation with trimmed-mean fallback.

    Behaviour
    ---------
    Case 1 — ``weights`` is None, or all weights are equal:
        Falls back to ``trimmed_mean(updates, beta=0.1)`` with equal weighting.
        This handles the cold-start phase (first few rounds before reputation
        history is established) and the degenerate case where all clients
        behave identically.

    Case 2 — ``weights`` contains meaningful variation:
        Normalises the weights to sum to 1.0, then computes the weighted
        average::

            θ_agg[k] = Σ_i  w̃_i · u_i[k]     w̃_i = w_i / Σ_j w_j

        Higher reputation → larger weight → more influence on the aggregate.
        Lower reputation (suspected Byzantine) → down-weighted contribution.

    SABD compatibility
    ------------------
    Reputation scores from SABDCorrector are *corrected* divergence values
    (post staleness-correction), so weights here reflect true malice signal,
    not staleness-confounded raw scores.

    Parameters
    ----------
    updates : list[dict[str, np.ndarray]]
        Per-client weight deltas.  All dicts must share keys and shapes.
    weights : list[float] | None
        Per-client reputation scores (higher = more trusted).  If None or
        all equal, trimmed_mean fallback is used.

    Returns
    -------
    dict[str, np.ndarray]
        Aggregated parameter dict; inputs not modified.

    Raises
    ------
    ValueError
        If ``updates`` is empty.
    """
    if not updates:
        raise ValueError("reputation_aggregated: 'updates' list is empty.")

    n = len(updates)

    # Fall back to trimmed_mean if no reputation signal available
    if weights is None:
        logger.debug(
            "reputation_aggregated — no weights provided; falling back to "
            "trimmed_mean (beta=0.1)."
        )
        return trimmed_mean(updates, beta=0.1)

    if len(weights) != n:
        raise ValueError(
            f"reputation_aggregated: len(weights)={len(weights)} != len(updates)={n}."
        )

    w_arr = np.array(weights, dtype=float)

    # Check for all-equal weights (no discrimination signal → fall back)
    if np.allclose(w_arr, w_arr[0]):
        logger.debug(
            "reputation_aggregated — all weights equal (%.4f); falling back to "
            "trimmed_mean (beta=0.1).",
            w_arr[0],
        )
        return trimmed_mean(updates, beta=0.1)

    total = w_arr.sum()
    if total <= 0:
        raise ValueError(
            "reputation_aggregated: reputation weights sum to zero or negative. "
            "All clients may have been flagged as Byzantine."
        )

    # w̃_i = w_i / Σ_j w_j  (normalise to a probability distribution)
    norm_weights = w_arr / total

    result = {}
    for key in updates[0].keys():
        # Weighted sum: Σ_i w̃_i · u_i[k]
        result[key] = sum(
            float(norm_weights[i]) * updates[i][key]
            for i in range(n)
        )

    logger.debug(
        "reputation_aggregated — %d clients, weight range [%.4f, %.4f], "
        "entropy=%.4f bits.",
        n,
        float(norm_weights.min()),
        float(norm_weights.max()),
        float(-np.sum(norm_weights * np.log2(norm_weights + 1e-12))),
    )
    return result
