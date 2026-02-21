# detection/anomaly.py — AnomalyDetector (3-signal composite) + legacy check_l2_norm
"""
detection/anomaly.py
====================
Contains:
- AnomalyDetector: three-signal composite Byzantine detector (norm z-score,
  cosine divergence, loss consistency) with SABD correction support.
- check_l2_norm(): legacy static L2 norm pre-filter for backward compatibility.

The AnomalyDetector uses SABD-corrected gradients when available, so honest-but-stale
clients are not falsely flagged.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from detection.sabd import SABDCorrector

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Legacy static gatekeeper (from akshat — kept for WebSocket router compat)
# ---------------------------------------------------------------------------

def check_l2_norm(weight_diff: dict, threshold: float) -> tuple:
    """First line of defense. Flattens all arrays and checks L2 norm.

    Returns:
        (passed: bool, norm: float)
        passed = True if norm <= threshold (safe)
        passed = False if norm > threshold (reject)
    """
    flat = np.concatenate([v.flatten() for v in weight_diff.values()])
    norm = float(np.linalg.norm(flat))
    passed = norm <= threshold
    if not passed:
        logger.warning("L2 norm check FAILED: norm=%.4f > threshold=%.4f", norm, threshold)
    else:
        logger.debug("L2 norm check passed: norm=%.4f <= threshold=%.4f", norm, threshold)
    return passed, norm


# ---------------------------------------------------------------------------
# Advanced AnomalyDetector (from ayush — stateful, 3-signal composite)
# ---------------------------------------------------------------------------

class AnomalyDetector:
    """Three-signal composite Byzantine detector.

    Signals:
    1. Gradient norm z-score — catches gradient scaling attacks.
    2. Cosine divergence (SABD-corrected) — catches sign-flip/direction attacks.
    3. Loss consistency z-score — catches free riders and loss spoofing.

    Composite score = mean(z_norm, z_cos, z_loss).
    Client flagged Byzantine if composite > threshold.

    Parameters
    ----------
    threshold      : float — composite score threshold (default 2.5 sigma).
    sabd_corrector : SABDCorrector | None — if provided, cosine uses corrected gradients.
    """

    def __init__(self, threshold: float = 2.5, sabd_corrector: SABDCorrector = None):
        self.threshold = threshold
        self.sabd_corrector = sabd_corrector
        self._reputation_history: dict = defaultdict(list)
        self._round_scores: dict = {}

        logger.info(
            "AnomalyDetector initialised (threshold=%.2f, sabd=%s).",
            threshold,
            "attached" if sabd_corrector is not None else "None (legacy mode)",
        )

    def score_update(self, update, all_updates: list, current_weights: dict) -> float:
        """Compute composite Byzantine score for one client update.

        Parameters
        ----------
        update          : ClientUpdate with .client_id, .weight_delta, .round_number, .training_loss
        all_updates     : list[ClientUpdate] — all updates this round
        current_weights : dict[str, np.ndarray] — current global model weights

        Returns
        -------
        float — composite anomaly score (higher = more suspicious)
        """
        # Signal 1: Gradient norm z-score
        all_norms = [
            float(np.linalg.norm(
                np.concatenate([v.flatten() for v in u.weight_delta.values()])
            ))
            for u in all_updates
        ]
        my_norm = all_norms[all_updates.index(update)]
        norm_score = self._z_score(my_norm, all_norms)

        # Signal 2: Cosine divergence (SABD-corrected if available)
        consensus = self._compute_consensus(all_updates)

        if self.sabd_corrector is not None:
            g_star = self.sabd_corrector.correct(
                update.weight_delta, update.round_number, current_weights
            )
            raw_div = self.sabd_corrector.compute_raw_divergence(
                update.weight_delta, consensus
            )
            corrected_div = self.sabd_corrector.compute_corrected_divergence(
                g_star, consensus
            )
            self.sabd_corrector.log_separation(
                raw_div, corrected_div, update.client_id, update.round_number
            )
            cosine_score = corrected_div
        else:
            g_flat = np.concatenate([v.flatten() for v in update.weight_delta.values()])
            c_flat = np.concatenate([v.flatten() for v in consensus.values()])
            cosine_score = 1.0 - float(
                np.dot(g_flat, c_flat)
                / (np.linalg.norm(g_flat) * np.linalg.norm(c_flat) + 1e-8)
            )

        # Signal 3: Loss consistency z-score
        all_losses = [u.training_loss for u in all_updates]
        loss_score = self._z_score(update.training_loss, all_losses)

        # Composite score = mean of the three z-scores
        composite = float(np.mean([norm_score, cosine_score, loss_score]))

        self._round_scores[update.client_id] = composite
        self._update_reputation(update.client_id, composite)

        logger.debug(
            "score_update — client=%s, norm_z=%.4f, cosine=%.4f, loss_z=%.4f, "
            "composite=%.4f, flagged=%s.",
            update.client_id, norm_score, cosine_score, loss_score,
            composite, composite > self.threshold,
        )
        return composite

    def is_byzantine(self, composite_score: float) -> bool:
        """Return True if composite score exceeds the detection threshold."""
        return composite_score > self.threshold

    # ------------------------------------------------------------------
    # Reputation management
    # ------------------------------------------------------------------

    def _update_reputation(self, client_id, score: float) -> None:
        """Append composite score to client's history."""
        self._reputation_history[client_id].append(score)

    def get_reputation_history(self) -> dict:
        """Return full per-client composite score history."""
        return dict(self._reputation_history)

    def get_reputation_weights(self, client_ids: list) -> list:
        """Convert reputation histories to normalised trust weights.
        Lower composite score -> higher weight -> more trusted.
        """
        scores = []
        for cid in client_ids:
            hist = self._reputation_history.get(cid, [])
            avg_score = float(np.mean(hist[-5:])) if hist else 0.5
            scores.append(max(0.01, 1.0 / (1.0 + avg_score)))

        total = sum(scores)
        norm = [s / total for s in scores]

        logger.debug(
            "get_reputation_weights — clients=%s, weights=%s.",
            client_ids, [f"{w:.4f}" for w in norm],
        )
        return norm

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _z_score(self, value: float, population: list) -> float:
        """Absolute z-score of value within population. Returns 0.0 for <2 samples."""
        if len(population) < 2:
            return 0.0
        mean = float(np.mean(population))
        std = float(np.std(population))
        return float(abs(value - mean) / (std + 1e-8))

    def _compute_consensus(self, all_updates: list) -> dict:
        """Simple unweighted mean of all weight deltas as consensus reference."""
        keys = list(all_updates[0].weight_delta.keys())
        return {
            k: np.mean([u.weight_delta[k] for u in all_updates], axis=0)
            for k in keys
        }
