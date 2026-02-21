"""
aggregation/aggregator.py
=========================
Factory and router for aggregation strategies.

Contains:
- get_aggregator(): returns a callable matching the unified interface
  (updates, weights=None) -> dict for a given method name string.
- list_available_methods(): returns sorted list of valid method names.

All returned callables share the same signature so the FL server can swap
strategies at runtime (or via Config.aggregation_method) without any
conditional logic at the call site.
"""

import logging

from async_federated_learning.aggregation.coordinate_median import coordinate_median
from async_federated_learning.aggregation.fedavg import fedavg
from async_federated_learning.aggregation.reputation import reputation_aggregated
from async_federated_learning.aggregation.trimmed_mean import trimmed_mean

logger = logging.getLogger(__name__)

_AVAILABLE_METHODS = ["coordinate_median", "fedavg", "reputation", "trimmed_mean"]


def get_aggregator(method_name: str, config=None):
    """
    Return the aggregation callable for the requested strategy.

    All returned callables conform to the unified interface::

        aggregator(updates: list, weights: list = None) -> dict

    Strategy descriptions
    ---------------------
    ``'fedavg'``
        Weighted average.  Fast, not Byzantine-robust.  Baseline / default.
    ``'trimmed_mean'``
        Coordinate-wise α-trimmed mean.  ``beta`` read from
        ``config.trimmed_mean_beta`` (default 0.1).  Robust up to β·n
        Byzantine clients.
    ``'coordinate_median'``
        Element-wise median.  Breakdown point 50 %.  No config parameters.
    ``'reputation'``
        SABD-aware reputation-weighted average.  Falls back to trimmed_mean
        when weights are absent or uniform.

    Parameters
    ----------
    method_name : str
        One of ``list_available_methods()``.  Case-insensitive.
    config      : Config | None
        Optional Config dataclass.  Used to read strategy-specific
        hyperparameters (e.g. ``config.trimmed_mean_beta``).

    Returns
    -------
    callable
        ``fn(updates: list, weights: list = None) -> dict``

    Raises
    ------
    ValueError
        If ``method_name`` is not recognised.
    """
    name = method_name.strip().lower()

    if name == "fedavg":
        logger.info("Aggregator: fedavg (not Byzantine-robust).")
        return fedavg

    if name == "trimmed_mean":
        beta = config.trimmed_mean_beta if config is not None else 0.1
        logger.info("Aggregator: trimmed_mean (beta=%.2f).", beta)
        # Wrap to bake beta into the call; weights still forwarded
        def _trimmed(updates, weights=None):
            return trimmed_mean(updates, beta=beta, _weights=weights)
        return _trimmed

    if name == "coordinate_median":
        logger.info("Aggregator: coordinate_median (breakdown point 50%%).")
        return coordinate_median

    if name == "reputation":
        logger.info("Aggregator: reputation_aggregated (SABD-aware).")
        return reputation_aggregated

    raise ValueError(
        f"Unknown aggregation method '{method_name}'. "
        f"Available: {_AVAILABLE_METHODS}"
    )


def list_available_methods() -> list:
    """Return a sorted list of all valid aggregation method name strings."""
    return list(_AVAILABLE_METHODS)
