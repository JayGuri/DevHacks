# aggregation/coordinate_median.py — Element-wise median (50% breakdown point)
"""
aggregation/coordinate_median.py
=================================
Coordinate-wise median aggregation for Byzantine robustness.
Breakdown point 50% — tolerates up to floor((n-1)/2) Byzantine clients.

Reference: Yin et al., "Byzantine-Robust Distributed Learning: Towards Optimal
Statistical Rates", ICML 2018.
"""

import logging

import numpy as np

logger = logging.getLogger(__name__)


def coordinate_median(updates: list, _weights: list = None) -> dict:
    """Element-wise median across all client updates.

    Parameters
    ----------
    updates : list[dict[str, np.ndarray]] — per-client weight deltas
    _weights : list[float] | None — accepted for interface compat; not used

    Returns
    -------
    dict[str, np.ndarray] — coordinate-wise median of all updates
    """
    if not updates:
        raise ValueError("coordinate_median: 'updates' list is empty.")

    n = len(updates)
    result = {}
    for key in updates[0].keys():
        matrix = np.stack([u[key] for u in updates], axis=0)
        result[key] = np.median(matrix, axis=0)

    logger.debug(
        "coordinate_median — aggregated %d clients (breakdown point: n=%d -> tolerates %d Byzantine).",
        n, n, (n - 1) // 2,
    )
    return result
