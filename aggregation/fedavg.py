# aggregation/fedavg.py — FedAvg weighted averaging (baseline strategy)
import numpy as np
import logging
from aggregation.reputation import compute_combined_weights

logger = logging.getLogger("fedbuff.aggregation.fedavg")


def fedavg(
    updates: list,
    current_round: int,
    alpha: float,
    max_staleness: int,
) -> dict:
    """
    Baseline federated averaging strategy.
    Computes a sample-count and staleness weighted average of all accepted updates.
    No Byzantine defense is applied here; this is the honest baseline.

    updates: list of dicts, each with keys:
      "client_id", "weights" (dict of numpy arrays), "num_samples", "global_round_received"

    Returns: dict of parameter_name -> numpy array (the aggregated global weight diff).
    """
    if not updates:
        logger.warning("FedAvg: No updates to aggregate.")
        return {}

    weights = compute_combined_weights(updates, current_round, alpha, max_staleness)

    # Get parameter names from first update
    param_names = list(updates[0]["weights"].keys())

    aggregated = {}
    for name in param_names:
        weighted_sum = np.zeros_like(updates[0]["weights"][name], dtype=np.float64)
        for u in updates:
            cid = u["client_id"]
            w = weights.get(cid, 0.0)
            if w > 0.0:
                weighted_sum += u["weights"][name].astype(np.float64) * w
        aggregated[name] = weighted_sum

    logger.info(
        "FedAvg: aggregated %d updates, weights=%s",
        len(updates),
        {k: f"{v:.4f}" for k, v in weights.items()},
    )

    return aggregated
