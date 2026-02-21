"""
detection/anomaly.py
====================
Three-signal composite Byzantine detector operating on SABD-corrected gradients.

Signals
-------
1. **Gradient norm z-score**: catches gradient scaling attacks where ‖g_i‖
   is a statistical outlier relative to the population of updates this round.

2. **Cosine divergence (SABD-corrected)**: catches sign-flipping and direction
   attacks.  When ``sabd_corrector`` is provided the corrected gradient g*_i
   is used instead of the raw g_i — this removes staleness artefacts so that
   honest-but-stale clients are not falsely flagged.

3. **Loss consistency z-score**: catches free riders and clients whose reported
   training loss is inconsistent with the magnitude of their gradient update
   (they claim to have trained but the loss signal is anomalous).

Composite score = arithmetic mean of the three z-scores.
Threshold (default 2.5 σ) is tunable via ``__init__``.

Key property: the cosine signal uses g_i* not g_i when SABD is attached — this
is what makes the detector staleness-aware rather than staleness-penalising.

Reputation tracking
-------------------
``_update_reputation`` accumulates composite scores per client over all rounds.
``get_reputation_weights`` converts the last-5-rounds average score into a
normalised trust weight: lower score → higher weight (more trusted).  These
weights feed directly into ``reputation_aggregated()``.
"""

import logging
from collections import defaultdict

import numpy as np

from async_federated_learning.detection.sabd import SABDCorrector

logger = logging.getLogger(__name__)


class AnomalyDetector:
    """
    Three-signal composite Byzantine detector.

    Signals (all computed per-round on the arriving batch of updates):

    1. Gradient norm z-score
       ``z_norm = |‖g_i‖ − μ_norm| / (σ_norm + ε)``
       Flags gradient-scaling attacks — a scaled gradient has a norm far
       outside the population distribution.

    2. Cosine divergence z-score
       ``z_cos = corrected_divergence_i``
       When ``sabd_corrector`` is set, uses the SABD-corrected gradient g*_i
       so that honest-but-stale clients are not penalised for drift.  Without
       SABD falls back to raw cosine divergence from consensus.

    3. Loss z-score
       ``z_loss = |loss_i − μ_loss| / (σ_loss + ε)``
       Flags clients whose reported training loss is inconsistent with the
       population (free riders, loss-spoofing Byzantine nodes).

    Composite score = mean(z_norm, z_cos, z_loss).
    A client is flagged Byzantine if composite > ``threshold``.

    Parameters
    ----------
    threshold       : float
        Composite score threshold above which a client is flagged Byzantine.
        Default 2.5 σ.  Lower → more aggressive detection (more false positives).
    sabd_corrector  : SABDCorrector | None
        If provided, the cosine signal uses SABD-corrected gradients.
        If None, raw cosine divergence from consensus is used (legacy mode).
    """

    def __init__(
        self,
        threshold: float = 2.5,
        sabd_corrector: SABDCorrector = None,
    ):
        self.threshold = threshold
        self.sabd_corrector = sabd_corrector  # None = no SABD correction (legacy mode)

        # client_id → list[float] of composite scores across all rounds
        self._reputation_history: dict = defaultdict(list)

        # composite scores for the *current* round (reset each call to score_update)
        self._round_scores: dict = {}

        logger.info(
            "AnomalyDetector initialised (threshold=%.2f, sabd=%s).",
            threshold,
            "attached" if sabd_corrector is not None else "None (legacy mode)",
        )

    # ------------------------------------------------------------------
    # Public scoring API
    # ------------------------------------------------------------------

    def score_update(
        self,
        update,
        all_updates: list,
        current_weights: dict,
    ) -> float:
        """
        Compute the composite Byzantine score for one client update.

        Three signals are combined:
        1. Gradient norm z-score       — gradient scaling detection
        2. Cosine divergence           — direction attack detection (SABD-aware)
        3. Training loss z-score       — free-rider / loss-spoofing detection

        Parameters
        ----------
        update        : ClientUpdate
            The update being scored (has ``.client_id``, ``.weight_delta``,
            ``.round_number``, ``.training_loss``, ``.num_samples``).
        all_updates   : list[ClientUpdate]
            All updates received this round, including ``update`` itself.
            Used to compute population statistics for z-scores.
        current_weights : dict[str, np.ndarray]
            Current global model weights θ_t (used by SABD correction).

        Returns
        -------
        float
            Composite anomaly score.  Higher → more suspicious.
        """
        # ── Signal 1: Gradient norm z-score ─────────────────────────────
        # ‖g_i‖ = L2 norm of the flattened weight delta
        all_norms = [
            float(np.linalg.norm(
                np.concatenate([v.flatten() for v in u.weight_delta.values()])
            ))
            for u in all_updates
        ]
        my_norm = all_norms[all_updates.index(update)]
        # z_norm = |‖g_i‖ − μ_norm| / (σ_norm + ε)
        norm_score = self._z_score(my_norm, all_norms)

        # ── Signal 2: Cosine divergence (SABD-corrected if available) ────
        consensus = self._compute_consensus(all_updates)

        if self.sabd_corrector is not None:
            # Use SABD-corrected gradient to remove staleness artefacts
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
            # Use corrected divergence as cosine signal — honest-but-stale
            # clients are not unfairly penalised
            cosine_score = corrected_div
        else:
            # Legacy mode: raw cosine divergence from consensus
            g_flat = np.concatenate(
                [v.flatten() for v in update.weight_delta.values()]
            )
            c_flat = np.concatenate([v.flatten() for v in consensus.values()])
            # 1 − cos(g_i, consensus) — higher when anti-aligned
            cosine_score = 1.0 - float(
                np.dot(g_flat, c_flat)
                / (np.linalg.norm(g_flat) * np.linalg.norm(c_flat) + 1e-8)
            )

        # ── Signal 3: Loss consistency z-score ──────────────────────────
        # z_loss = |loss_i − μ_loss| / (σ_loss + ε)
        all_losses = [u.training_loss for u in all_updates]
        loss_score = self._z_score(update.training_loss, all_losses)

        # ── Composite score ─────────────────────────────────────────────
        # arithmetic mean of the three z-scores
        composite = float(np.mean([norm_score, cosine_score, loss_score]))

        self._round_scores[update.client_id] = composite
        self._update_reputation(update.client_id, composite)

        logger.debug(
            "score_update — client=%d, norm_z=%.4f, cosine=%.4f, loss_z=%.4f, "
            "composite=%.4f, flagged=%s.",
            update.client_id,
            norm_score,
            cosine_score,
            loss_score,
            composite,
            composite > self.threshold,
        )
        return composite

    def is_byzantine(self, composite_score: float) -> bool:
        """
        Return True if the composite score exceeds the detection threshold.

        Parameters
        ----------
        composite_score : float   Output of ``score_update()``.

        Returns
        -------
        bool   True → client flagged as Byzantine suspect.
        """
        return composite_score > self.threshold

    # ------------------------------------------------------------------
    # Reputation management
    # ------------------------------------------------------------------

    def _update_reputation(self, client_id: int, score: float) -> None:
        """Append the latest composite score to the client's history."""
        self._reputation_history[client_id].append(score)

    def get_reputation_history(self) -> dict:
        """
        Return the full per-client composite score history.

        Returns
        -------
        dict[int, list[float]]
            ``client_id → [score_round_1, score_round_2, …]``
        """
        return dict(self._reputation_history)

    def get_reputation_weights(self, client_ids: list) -> list:
        """
        Convert reputation histories to normalised trust weights.

        Formula (per client i)::

            raw_i = max(0.01, 1 / (1 + avg_score_i))

        where ``avg_score_i`` is the mean of the last 5 composite scores
        (or 0.5 for clients with no history yet).

        Lower composite score → higher raw weight → higher trust.
        Weights are then L1-normalised to sum to 1.0.

        Parameters
        ----------
        client_ids : list[int]   Ordered list of client identifiers.

        Returns
        -------
        list[float]
            Normalised trust weights, same order as ``client_ids``.
        """
        scores = []
        for cid in client_ids:
            hist = self._reputation_history.get(cid, [])
            # Use last 5 rounds only — older behaviour should decay
            avg_score = float(np.mean(hist[-5:])) if hist else 0.5
            # Inverted: lower score → higher weight.  Floor at 0.01 to avoid zero.
            scores.append(max(0.01, 1.0 / (1.0 + avg_score)))

        # L1-normalise to a probability distribution
        total = sum(scores)
        norm = [s / total for s in scores]

        logger.debug(
            "get_reputation_weights — clients=%s, weights=%s.",
            client_ids,
            [f"{w:.4f}" for w in norm],
        )
        return norm

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _z_score(self, value: float, population: list) -> float:
        """
        Absolute z-score of ``value`` within ``population``.

        Formula::

            z = |value − μ| / (σ + ε)

        Returns 0.0 for populations of size < 2 (undefined standard deviation).

        Parameters
        ----------
        value      : float   The scalar to score.
        population : list    All values including ``value`` itself.

        Returns
        -------
        float   Non-negative z-score.
        """
        if len(population) < 2:
            return 0.0
        mean = float(np.mean(population))
        std = float(np.std(population))
        # z = |value − μ| / (σ + ε)
        return float(abs(value - mean) / (std + 1e-8))

    def _compute_consensus(self, all_updates: list) -> dict:
        """
        Compute the simple (unweighted) mean of all weight deltas as the
        consensus reference direction for the cosine divergence signal.

        Parameters
        ----------
        all_updates : list[ClientUpdate]
            All updates for this round.

        Returns
        -------
        dict[str, np.ndarray]
            Coordinate-wise mean update across all clients.
        """
        keys = list(all_updates[0].weight_delta.keys())
        return {
            k: np.mean([u.weight_delta[k] for u in all_updates], axis=0)
            for k in keys
        }
