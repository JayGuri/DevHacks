"""
aggregation/trimmed_mean.py
===========================
Coordinate-wise α-trimmed mean aggregation for Byzantine robustness.

Contains:
- trimmed_mean(): for every parameter coordinate, sorts the n client values,
  discards the k lowest and k highest (k = ⌈β·n⌉), and averages the remainder.

Robustness guarantee
--------------------
If the number of Byzantine clients f satisfies f < β·n, all Byzantine updates
fall outside the trimmed window *in expectation* — the remaining average is
dominated by honest updates.  Breakdown point is β (fraction of corrupted
clients the method can tolerate).

Reference: Yin et al., "Byzantine-Robust Distributed Learning: Towards Optimal
Statistical Rates", ICML 2018.
"""

import logging

import numpy as np

logger = logging.getLogger(__name__)


def trimmed_mean(updates: list, beta: float = 0.1, _weights: list = None) -> dict:
    """
    Coordinate-wise α-trimmed mean of client updates.

    Algorithm
    ---------
    For each parameter key ``k``:

    1. Stack client arrays into a matrix of shape ``(n, *param_shape)``.
    2. Sort along ``axis=0`` (over clients, independently per coordinate).
    3. Trim ``k = max(1, ⌈β·n⌉)`` rows from each end of the sorted matrix.
    4. Average the remaining ``n - 2k`` rows along ``axis=0``.

    Formula::

        TM_β({x_i}) = mean( x_{(k+1)}, …, x_{(n-k)} )

    where ``x_{(j)}`` denotes the j-th order statistic and
    ``k = max(1, int(β · n))``.

    The ``weights`` parameter is accepted for interface compatibility but is
    **ignored** — trimmed mean does not support per-client weighting (sorting
    is the core operation and weights cannot be applied after trimming without
    breaking the statistical guarantee).

    Parameters
    ----------
    updates : list[dict[str, np.ndarray]]
        Per-client weight deltas.  All dicts must share keys and shapes.
    beta    : float
        Trim fraction in (0, 0.5).  Each tail removes ``⌈β·n⌉`` clients.
        Default 0.1 (10 % from each side → tolerates up to 10 % Byzantine).
    weights : list[float] | None
        Accepted for interface compatibility; not used.

    Returns
    -------
    dict[str, np.ndarray]
        Trimmed-mean aggregated parameters.

    Raises
    ------
    ValueError
        If ``updates`` is empty, or if ``2·k >= n`` (too few clients for β).
    """
    if not updates:
        raise ValueError("trimmed_mean: 'updates' list is empty.")

    n = len(updates)
    # k = number of clients trimmed from each tail
    # max(1, …) ensures at least one client is trimmed per side (non-trivial trim)
    k = max(1, int(beta * n))

    if 2 * k >= n:
        raise ValueError(
            f"trimmed_mean: beta={beta} trims {k} clients from each tail "
            f"(2k={2*k} >= n={n}). Reduce beta or add more clients. "
            f"Minimum clients for this beta: {2*k + 1}."
        )

    result = {}
    for key in updates[0].keys():
        # Stack into (n, *param_shape) — each row is one client's update
        matrix = np.stack([u[key] for u in updates], axis=0)

        # Sort along client axis (axis=0) independently per coordinate
        # After sorting: matrix[0] = per-coordinate minimum, matrix[-1] = maximum
        sorted_matrix = np.sort(matrix, axis=0)

        # Trim k rows from each end: keep rows k … n-k-1 (inclusive)
        # Remaining rows: n - 2k  (guaranteed ≥ 1 by the check above)
        trimmed = sorted_matrix[k: n - k]

        # Average over the trimmed client dimension
        result[key] = np.mean(trimmed, axis=0)

    logger.debug(
        "trimmed_mean — n=%d clients, beta=%.2f, k=%d trimmed each side, "
        "%d clients in average.",
        n, beta, k, n - 2 * k,
    )
    return result
