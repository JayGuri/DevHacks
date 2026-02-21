"""
aggregation/fedavg.py
=====================
Federated Averaging (FedAvg) aggregation strategy.

Contains:
- fedavg(): pure function implementing sample-weighted averaging of client
  model updates.  NOT Byzantine-robust — a single malicious client can
  corrupt the result arbitrarily (unbounded influence via gradient scaling
  or sign-flipping).  Serves as the baseline and the fallback within the
  reputation aggregator when no adversarial context is assumed.

Reference: McMahan et al., "Communication-Efficient Learning of Deep Networks
from Decentralized Data", AISTATS 2017.
"""

import logging

logger = logging.getLogger(__name__)


def fedavg(updates: list, weights: list = None) -> dict:
    """
    Compute the weighted average of client model updates.

    Formula::

        θ_agg[k] = Σ_i  w̃_i · u_i[k]

    where ``w̃_i = w_i / Σ_j w_j`` are the normalised weights and ``u_i[k]``
    is client i's update for parameter ``k``.  When ``weights`` is None,
    equal weights (``w̃_i = 1/n``) are used, recovering the unweighted mean.

    In the FL context ``weights`` are typically set to each client's local
    dataset size (``n_i / N``), so larger clients contribute proportionally
    more to the global model — the original FedAvg recipe.

    NOT Byzantine-robust
    --------------------
    One malicious client with ``scale=50`` gradient scaling inflates its
    effective weight by 50×, dominating the average regardless of the other
    clients' weights.  Use trimmed_mean or coordinate_median for robustness.

    Parameters
    ----------
    updates : list[dict[str, np.ndarray]]
        Per-client weight deltas or full state_dicts.  All dicts must share
        the same keys and array shapes.
    weights : list[float] | None
        Non-negative importance weights, one per client.  Need not sum to 1
        (normalised internally).  If None, equal weights are used.

    Returns
    -------
    dict[str, np.ndarray]
        Aggregated parameter dict; a new dict with new arrays (inputs intact).

    Raises
    ------
    ValueError
        If ``updates`` is empty.
    """
    if not updates:
        raise ValueError("fedavg: 'updates' list is empty.")

    n = len(updates)

    if weights is None:
        # Equal weights: w̃_i = 1/n
        norm_weights = [1.0 / n] * n
    else:
        if len(weights) != n:
            raise ValueError(
                f"fedavg: len(weights)={len(weights)} != len(updates)={n}."
            )
        total = sum(weights)
        if total <= 0:
            raise ValueError("fedavg: weights sum to zero or negative.")
        norm_weights = [w / total for w in weights]

    # θ_agg[k] = Σ_i w̃_i · u_i[k]
    keys   = updates[0].keys()
    result = {
        k: sum(w * u[k] for w, u in zip(norm_weights, updates))
        for k in keys
    }

    logger.debug(
        "fedavg — aggregated %d updates (equal_weights=%s).",
        n, weights is None,
    )
    return result
