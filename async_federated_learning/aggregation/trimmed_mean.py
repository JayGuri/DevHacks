# aggregation/trimmed_mean.py — Coordinate-wise alpha-trimmed mean (Byzantine-robust)
"""
aggregation/trimmed_mean.py
===========================
Coordinate-wise alpha-trimmed mean aggregation.

For every parameter coordinate, sorts n client values, discards k lowest and
k highest (k = floor(beta*n)), and averages the remainder.

Robustness guarantee: tolerates up to beta*n Byzantine clients.

Reference: Yin et al., "Byzantine-Robust Distributed Learning: Towards Optimal
Statistical Rates", ICML 2018.
"""

import logging

import numpy as np

logger = logging.getLogger(__name__)


def trimmed_mean(updates: list, beta: float = 0.1, _weights: list = None) -> dict:
    """Coordinate-wise alpha-trimmed mean of client updates.

    Parameters
    ----------
    updates : list[dict[str, np.ndarray]] — per-client weight deltas
    beta    : float — trim fraction in (0, 0.5); each tail removes floor(beta*n) clients
    _weights : list[float] | None — accepted for interface compat; not used

    Returns
    -------
    dict[str, np.ndarray] — trimmed-mean aggregated parameters
    """
    if not updates:
        raise ValueError("trimmed_mean: 'updates' list is empty.")

    n = len(updates)
    k = max(1, int(beta * n))

    if 2 * k >= n:
        raise ValueError(
            f"trimmed_mean: beta={beta} trims {k} clients from each tail "
            f"(2k={2*k} >= n={n}). Reduce beta or add more clients. "
            f"Minimum clients for this beta: {2*k + 1}."
        )

    result = {}
    for key in updates[0].keys():
        matrix = np.stack([u[key] for u in updates], axis=0)
        sorted_matrix = np.sort(matrix, axis=0)
        trimmed = sorted_matrix[k: n - k]
        result[key] = np.mean(trimmed, axis=0)

    logger.debug(
        "trimmed_mean — n=%d clients, beta=%.2f, k=%d trimmed each side, "
        "%d clients in average.",
        n, beta, k, n - 2 * k,
    )
    return result
