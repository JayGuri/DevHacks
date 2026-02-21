# aggregation/trimmed_mean.py — Coordinate-wise trimmed mean (Byzantine defense)
import numpy as np
import logging

logger = logging.getLogger("fedbuff.aggregation.trimmed_mean")


def trimmed_mean(updates: list, trim_fraction: float = 0.2) -> tuple:
    """
    Coordinate-wise trimmed mean aggregation strategy.
    Second line of defense (runs after Gatekeeper, inside aggregator.py).

    For each parameter tensor:
    1. Stack into matrix (num_clients, *param_shape). Flatten to (num_clients, -1).
    2. Sort along axis=0 (across clients per coordinate).
    3. Remove bottom trim_fraction and top trim_fraction of values per coordinate.
    4. Average remaining values.

    Trust score assignment:
      A client whose update falls in the trimmed range for more than 50% of
      coordinates across all parameters receives trust_score = 0.0. Others get 1.0.

    Returns:
        (aggregated_weights: dict, trust_scores: dict)
        trust_scores: {client_id: float}
    """
    if not updates:
        logger.warning("Trimmed mean: No updates to aggregate.")
        return {}, {}

    num_clients = len(updates)
    param_names = list(updates[0]["weights"].keys())

    # Number of values to trim from each end
    trim_count = max(int(num_clients * trim_fraction), 0)

    if num_clients <= 2 * trim_count:
        logger.warning(
            "Trimmed mean: Not enough clients (%d) for trim_fraction=%.2f. "
            "Falling back to simple mean.",
            num_clients, trim_fraction,
        )
        trim_count = 0

    # Track how many coordinates each client falls in the trimmed (extreme) range
    total_coords = 0
    trimmed_counts = np.zeros(num_clients, dtype=np.int64)

    aggregated = {}
    for name in param_names:
        # Stack and flatten per parameter
        stacked = np.stack(
            [u["weights"][name].astype(np.float64).flatten() for u in updates],
            axis=0,
        )  # (num_clients, num_coords_for_this_param)
        num_coords = stacked.shape[1]
        total_coords += num_coords

        # Sort along axis=0 (per coordinate)
        sorted_indices = np.argsort(stacked, axis=0)

        if trim_count > 0:
            # Identify which client indices are in the trimmed regions
            for coord_j in range(num_coords):
                for t in range(trim_count):
                    trimmed_counts[sorted_indices[t, coord_j]] += 1  # bottom trim
                    trimmed_counts[sorted_indices[-(t + 1), coord_j]] += 1  # top trim

            # Trimmed mean: remove top and bottom, average the rest
            sorted_values = np.sort(stacked, axis=0)
            trimmed_values = sorted_values[trim_count: num_clients - trim_count, :]
            mean_vals = np.mean(trimmed_values, axis=0)
        else:
            mean_vals = np.mean(stacked, axis=0)

        # Reshape back to original param shape
        original_shape = updates[0]["weights"][name].shape
        aggregated[name] = mean_vals.reshape(original_shape)

    # Compute trust scores: trimmed for > 50% of coordinates -> trust 0.0
    trust_scores = {}
    for i, u in enumerate(updates):
        cid = u["client_id"]
        if total_coords > 0 and trimmed_counts[i] / total_coords > 0.5:
            trust_scores[cid] = 0.0
        else:
            trust_scores[cid] = 1.0

    logger.info(
        "Trimmed mean: aggregated %d updates, trim_count=%d, trust_scores=%s",
        num_clients, trim_count, trust_scores,
    )

    return aggregated, trust_scores
