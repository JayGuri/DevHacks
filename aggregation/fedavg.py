# aggregation/fedavg.py — Federated Averaging (not Byzantine-robust)
"""
aggregation/fedavg.py
=====================
Sample-weighted averaging of client model updates (FedAvg).
NOT Byzantine-robust — serves as baseline and fallback.

Reference: McMahan et al., "Communication-Efficient Learning of Deep Networks
from Decentralized Data", AISTATS 2017.
"""

import logging

logger = logging.getLogger(__name__)


def fedavg(updates: list, weights: list = None) -> dict:
    """Compute the weighted average of client model updates.

    Parameters
    ----------
    updates : list[dict[str, np.ndarray]] — per-client weight deltas
    weights : list[float] | None — importance weights (normalised internally)

    Returns
    -------
    dict[str, np.ndarray] — aggregated parameter dict
    """
    if not updates:
        raise ValueError("fedavg: 'updates' list is empty.")

    n = len(updates)

    if weights is None:
        norm_weights = [1.0 / n] * n
    else:
        if len(weights) != n:
            raise ValueError(f"fedavg: len(weights)={len(weights)} != len(updates)={n}.")
        total = sum(weights)
        if total <= 0:
            raise ValueError("fedavg: weights sum to zero or negative.")
        norm_weights = [w / total for w in weights]

    keys = updates[0].keys()
    result = {
        k: sum(w * u[k] for w, u in zip(norm_weights, updates))
        for k in keys
    }

    logger.debug("fedavg — aggregated %d updates (equal_weights=%s).", n, weights is None)
    return result
