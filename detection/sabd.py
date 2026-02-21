# detection/sabd.py — SABD: Statistical Anomaly-Based Detection (Multi-Krum variant)
import numpy as np
import math
import logging
from dataclasses import dataclass, field

logger = logging.getLogger("fedbuff.detection.sabd")


@dataclass
class SABDResult:
    selected_indices: list = field(default_factory=list)  # indices accepted
    rejected_indices: list = field(default_factory=list)  # indices rejected
    krum_scores: dict = field(default_factory=dict)       # client_id -> float score
    trust_scores: dict = field(default_factory=dict)      # client_id -> float in [0.0, 1.0]


def flatten_update(weight_diff: dict) -> np.ndarray:
    """Flattens a weight_diff dict of numpy arrays into a single 1D vector."""
    return np.concatenate([v.flatten() for v in weight_diff.values()])


def run_sabd(updates: list, byzantine_fraction: float = 0.3) -> SABDResult:
    """
    Multi-Krum algorithm:
    1. For each update i, flatten all parameter arrays into a 1D vector v_i.
    2. Compute pairwise Euclidean distances: dist[i][j] = ||v_i - v_j||_2
    3. n = len(updates), f = floor(n * byzantine_fraction)
    4. score(i) = sum of the (n - f - 2) smallest distances from i to all other j.
    5. Sort updates by score ascending. Select the m = n - f lowest-scoring updates.
    6. Assign trust_score = 1.0 to selected, 0.0 to rejected.
    7. If n < 3: select all, set all trust_scores = 1.0, log a warning.

    Returns SABDResult with selected/rejected index lists, scores, and trust_scores keyed by client_id.
    """
    n = len(updates)
    result = SABDResult()

    if n == 0:
        logger.warning("SABD: No updates to process.")
        return result

    # Edge case: fewer than 3 updates — accept all
    if n < 3:
        logger.warning(
            "SABD: Only %d updates received (< 3). Accepting all without filtering.", n
        )
        result.selected_indices = list(range(n))
        result.rejected_indices = []
        for i, update in enumerate(updates):
            cid = update.get("client_id", f"client_{i}")
            result.krum_scores[cid] = 0.0
            result.trust_scores[cid] = 1.0
        return result

    # Step 1: Flatten all updates
    vectors = []
    client_ids = []
    for i, update in enumerate(updates):
        vec = flatten_update(update["weights"])
        vectors.append(vec)
        client_ids.append(update.get("client_id", f"client_{i}"))

    vectors = np.array(vectors)  # (n, d)

    # Step 2: Compute pairwise Euclidean distances
    dist_matrix = np.zeros((n, n), dtype=np.float64)
    for i in range(n):
        for j in range(i + 1, n):
            d = float(np.linalg.norm(vectors[i] - vectors[j]))
            dist_matrix[i][j] = d
            dist_matrix[j][i] = d

    # Step 3: Compute f and selection count m
    # Use ceil so that even small n with nonzero fraction assumes >= 1 Byzantine
    f = int(math.ceil(n * byzantine_fraction))
    # Number of nearest neighbors to sum for each score
    k = max(n - f - 2, 1)
    m = max(n - f, 1)

    # Step 4: Compute Krum scores
    scores = np.zeros(n, dtype=np.float64)
    for i in range(n):
        dists_from_i = np.copy(dist_matrix[i])
        dists_from_i[i] = np.inf  # exclude self
        sorted_dists = np.sort(dists_from_i)
        scores[i] = float(np.sum(sorted_dists[:k]))

    # Step 5: Sort by score, select lowest m
    sorted_indices = np.argsort(scores)
    selected = sorted_indices[:m].tolist()
    rejected = sorted_indices[m:].tolist()

    result.selected_indices = selected
    result.rejected_indices = rejected

    # Step 6: Assign scores and trust
    for i in range(n):
        cid = client_ids[i]
        result.krum_scores[cid] = float(scores[i])
        if i in selected:
            result.trust_scores[cid] = 1.0
        else:
            result.trust_scores[cid] = 0.0

    logger.info(
        "SABD: n=%d, f=%d, m=%d, selected=%s, rejected=%s",
        n, f, m,
        [client_ids[i] for i in selected],
        [client_ids[i] for i in rejected],
    )

    return result
