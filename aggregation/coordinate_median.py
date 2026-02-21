# aggregation/coordinate_median.py — Coordinate-wise median aggregation
import numpy as np
import logging

logger = logging.getLogger("fedbuff.aggregation.coordinate_median")


def coordinate_median(updates: list) -> tuple:
    """
    Coordinate-wise median aggregation strategy.
    For each parameter tensor coordinate, computes the median value across all clients.

    1. For each parameter name p:
         stack all clients' values for p into matrix shape (num_clients, *param_shape)
         compute np.median along axis=0
    2. All clients receive trust_score = 1.0 (no explicit rejection by this strategy).

    Returns:
        (aggregated_weights: dict, trust_scores: dict)
        trust_scores: {client_id: 1.0 for all}
    """
    if not updates:
        logger.warning("Coordinate median: No updates to aggregate.")
        return {}, {}

    param_names = list(updates[0]["weights"].keys())
    num_clients = len(updates)

    aggregated = {}
    for name in param_names:
        stacked = np.stack(
            [u["weights"][name].astype(np.float64) for u in updates],
            axis=0,
        )  # shape: (num_clients, *param_shape)
        aggregated[name] = np.median(stacked, axis=0)

    trust_scores = {u["client_id"]: 1.0 for u in updates}

    logger.info(
        "Coordinate median: aggregated %d updates across %d parameters.",
        num_clients, len(param_names),
    )

    return aggregated, trust_scores
