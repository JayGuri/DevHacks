"""
aggregation/coordinate_median.py
=================================
Coordinate-wise median aggregation for Byzantine robustness.

Contains:
- coordinate_median(): takes the element-wise median across all client arrays.
  Breakdown point is 50 % — up to ⌊(n-1)/2⌋ Byzantine clients cannot move
  the median outside the range of honest values for any single coordinate.

Reference: Yin et al., "Byzantine-Robust Distributed Learning: Towards Optimal
Statistical Rates", ICML 2018.
"""

import logging

import numpy as np

logger = logging.getLogger(__name__)


def coordinate_median(updates: list, weights: list = None) -> dict:
    """
    Element-wise median across all client updates.

    For every scalar coordinate j of every parameter key k::

        result[k][j] = median( u_1[k][j],  u_2[k][j],  …,  u_n[k][j] )

    Algorithm
    ---------
    Stack client arrays into a matrix of shape ``(n, *param_shape)``, then
    call ``np.median(matrix, axis=0)`` which independently computes the
    median over the n clients for each coordinate.

    Robustness guarantee
    --------------------
    The coordinate-wise median has a breakdown point of 50 %: as long as
    strictly fewer than n/2 clients are Byzantine, the median of each
    coordinate remains within the range of the honest clients' values.
    This is the highest possible breakdown point for any equivariant
    location estimator (Donoho & Huber, 1983).

    Limitation
    ----------
    The coordinate-wise median is *not* the geometric median — it optimises
    each coordinate independently and can produce a result that is not the
    update of any single client.  The geometric median (Weiszfeld's algorithm)
    is a stronger estimator but more expensive; use this as the primary robust
    aggregator given its O(n·d) cost.

    The ``weights`` parameter is accepted for interface compatibility but is
    **ignored** — medians cannot be meaningfully weighted without losing the
    breakdown-point guarantee.

    Parameters
    ----------
    updates : list[dict[str, np.ndarray]]
        Per-client weight deltas.  All dicts must share keys and array shapes.
    weights : list[float] | None
        Accepted for interface compatibility; not used.

    Returns
    -------
    dict[str, np.ndarray]
        Coordinate-wise median of all client updates.

    Raises
    ------
    ValueError
        If ``updates`` is empty.
    """
    if not updates:
        raise ValueError("coordinate_median: 'updates' list is empty.")

    n = len(updates)
    result = {}
    for key in updates[0].keys():
        # Stack: (n, *param_shape) — one row per client
        matrix = np.stack([u[key] for u in updates], axis=0)
        # np.median operates independently on each coordinate along axis=0
        result[key] = np.median(matrix, axis=0)

    logger.debug(
        "coordinate_median — aggregated %d clients (breakdown point: n=%d → tolerates %d Byzantine).",
        n, n, (n - 1) // 2,
    )
    return result
