# detection/sabd.py — Staleness-Aware Byzantine Detection (SABD) + Multi-Krum
"""
detection/sabd.py
=================
Contains:
- SABDCorrector: staleness-aware gradient correction for honest-but-stale clients.
- run_sabd(): legacy Multi-Krum algorithm kept for backward compatibility.
- SABDResult: dataclass for Multi-Krum results.

Core insight: in async FL, stale clients' gradients naturally drift away from
the current consensus. SABD corrects for this drift before computing divergence:
    g*_i = g_i + alpha * delta_{s->t}
"""

import math
import logging
from dataclasses import dataclass, field

import numpy as np

from server.model_history import ModelHistoryBuffer

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# SABD Corrector (from ayush — stateful, staleness-aware)
# ---------------------------------------------------------------------------

class SABDCorrector:
    """Staleness-Aware Byzantine Detection corrector.

    Parameters
    ----------
    alpha         : float — correction strength in (0, 1]. Typical: 0.5.
    model_history : ModelHistoryBuffer — used to look up theta_s for drift computation.
    """

    def __init__(self, alpha: float, model_history: ModelHistoryBuffer):
        if not (0.0 < alpha <= 1.0):
            raise ValueError(f"SABDCorrector: alpha must be in (0, 1], got {alpha}.")
        self.alpha = alpha
        self.model_history = model_history
        self._raw_divs: dict = {}
        self._corrected_divs: dict = {}
        logger.info(
            "SABDCorrector initialised (alpha=%.3f, history_capacity=%d).",
            alpha, model_history.max_size,
        )

    def correct(self, gradient: dict, client_round: int, current_weights: dict) -> dict:
        """Apply staleness correction: g*_i[k] = g_i[k] + alpha * delta_{s->t}[k]."""
        if not self.model_history.has_version(client_round):
            logger.warning(
                "SABDCorrector.correct — version %d not in history buffer "
                "(oldest=%s). Returning gradient uncorrected.",
                client_round, self.model_history.get_oldest_version(),
            )
            return {k: v.copy() for k, v in gradient.items()}

        drift = self.model_history.get_drift(client_round, current_weights)
        corrected = {k: gradient[k] + self.alpha * drift[k] for k in gradient}

        logger.debug(
            "SABDCorrector.correct — client_round=%d, alpha=%.3f, drift_norm=%.6f.",
            client_round, self.alpha,
            float(np.linalg.norm(np.concatenate([d.flatten() for d in drift.values()]))),
        )
        return corrected

    def _cosine_similarity(self, a: dict, b: dict) -> float:
        """Cosine similarity between two parameter dicts as flat vectors."""
        flat_a = np.concatenate([a[k].flatten() for k in a])
        flat_b = np.concatenate([b[k].flatten() for k in b])
        dot = float(np.dot(flat_a, flat_b))
        norm_a = float(np.linalg.norm(flat_a))
        norm_b = float(np.linalg.norm(flat_b))
        return dot / (norm_a * norm_b + 1e-8)

    def compute_raw_divergence(self, gradient: dict, consensus: dict) -> float:
        """Raw cosine divergence: 1 - cos(g_i, consensus). Values near 0 = aligned."""
        div = 1.0 - self._cosine_similarity(gradient, consensus)
        logger.debug("compute_raw_divergence — div=%.6f.", div)
        return div

    def compute_corrected_divergence(self, g_star: dict, consensus: dict) -> float:
        """Corrected cosine divergence: 1 - cos(g*_i, consensus)."""
        div = 1.0 - self._cosine_similarity(g_star, consensus)
        logger.debug("compute_corrected_divergence — div=%.6f.", div)
        return div

    def log_separation(self, raw_div: float, corrected_div: float,
                        client_id: int, round_num: int) -> None:
        """Persist raw and corrected divergence scores for analysis."""
        if client_id not in self._raw_divs:
            self._raw_divs[client_id] = []
            self._corrected_divs[client_id] = []

        self._raw_divs[client_id].append((round_num, raw_div))
        self._corrected_divs[client_id].append((round_num, corrected_div))

        separation = raw_div - corrected_div
        logger.info(
            "SABD log — client=%d, round=%d, raw_div=%.4f, "
            "corrected_div=%.4f, separation=%.4f.",
            client_id, round_num, raw_div, corrected_div, separation,
        )

    def get_divergence_logs(self) -> tuple:
        """Return (raw_divs, corrected_divs) dicts: client_id -> list[(round, score)]."""
        return self._raw_divs, self._corrected_divs


# ---------------------------------------------------------------------------
# Legacy Multi-Krum (from akshat — backward compatibility for tests)
# ---------------------------------------------------------------------------

@dataclass
class SABDResult:
    selected_indices: list = field(default_factory=list)
    rejected_indices: list = field(default_factory=list)
    krum_scores: dict = field(default_factory=dict)
    trust_scores: dict = field(default_factory=dict)


def flatten_update(weight_diff: dict) -> np.ndarray:
    """Flattens a weight_diff dict into a single 1D vector."""
    return np.concatenate([v.flatten() for v in weight_diff.values()])


def run_sabd(updates: list, byzantine_fraction: float = 0.3) -> SABDResult:
    """Multi-Krum algorithm for backward compatibility.

    1. Flatten all updates into 1D vectors.
    2. Compute pairwise Euclidean distances.
    3. f = ceil(n * byzantine_fraction), k = max(n - f - 2, 1), m = max(n - f, 1).
    4. score(i) = sum of the k smallest distances from i.
    5. Select the m lowest-scoring updates.
    """
    n = len(updates)
    result = SABDResult()

    if n == 0:
        logger.warning("SABD: No updates to process.")
        return result

    if n < 3:
        logger.warning("SABD: Only %d updates (%d < 3). Accepting all.", n, n)
        result.selected_indices = list(range(n))
        result.rejected_indices = []
        for i, update in enumerate(updates):
            cid = update.get("client_id", f"client_{i}")
            result.krum_scores[cid] = 0.0
            result.trust_scores[cid] = 1.0
        return result

    vectors = []
    client_ids = []
    for i, update in enumerate(updates):
        vec = flatten_update(update["weights"])
        vectors.append(vec)
        client_ids.append(update.get("client_id", f"client_{i}"))

    vectors = np.array(vectors)

    dist_matrix = np.zeros((n, n), dtype=np.float64)
    for i in range(n):
        for j in range(i + 1, n):
            d = float(np.linalg.norm(vectors[i] - vectors[j]))
            dist_matrix[i][j] = d
            dist_matrix[j][i] = d

    f = int(math.ceil(n * byzantine_fraction))
    k = max(n - f - 2, 1)
    m = max(n - f, 1)

    scores = np.zeros(n, dtype=np.float64)
    for i in range(n):
        dists_from_i = np.copy(dist_matrix[i])
        dists_from_i[i] = np.inf
        sorted_dists = np.sort(dists_from_i)
        scores[i] = float(np.sum(sorted_dists[:k]))

    sorted_indices = np.argsort(scores)
    selected = sorted_indices[:m].tolist()
    rejected = sorted_indices[m:].tolist()

    result.selected_indices = selected
    result.rejected_indices = rejected

    for i in range(n):
        cid = client_ids[i]
        result.krum_scores[cid] = float(scores[i])
        result.trust_scores[cid] = 1.0 if i in selected else 0.0

    logger.info(
        "SABD: n=%d, f=%d, m=%d, selected=%s, rejected=%s",
        n, f, m,
        [client_ids[i] for i in selected],
        [client_ids[i] for i in rejected],
    )
    return result
