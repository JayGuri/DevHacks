"""
detection/sabd.py
=================
Staleness-Aware Byzantine Detection (SABD) — custom algorithm.

Core insight
------------
In asynchronous FL, a stale client's gradient naturally *drifts* away from the
current consensus — not because the client is malicious, but because the global
model has moved on since the client started training.  Naively comparing stale
gradients to the current consensus inflates their anomaly score, causing
false-positive Byzantine rejections of slow-but-honest clients.

SABD corrects for this drift *before* computing any divergence score::

    g*_i = g_i + α · Δ_{s→t}

where

    g_i         — raw gradient / weight-delta from client i
    Δ_{s→t}    — model drift from client i's start version s to the current
                  server version t:  Δ_{s→t}[k] = θ_t[k] − θ_s[k]
    α           — correction strength ∈ (0, 1]; config.sabd_alpha

After correction the drift artefact is (partially) removed, so the cosine
divergence from consensus reflects *true* behavioural deviation (malice signal)
rather than staleness-confounded raw divergence.

Contains
--------
- SABDCorrector: applies gradient correction, computes raw and corrected
  cosine divergence, stores per-round logs for later analysis.
"""

import logging

import numpy as np

from async_federated_learning.server.model_history import ModelHistoryBuffer

logger = logging.getLogger(__name__)


class SABDCorrector:
    """
    Staleness-Aware Byzantine Detection corrector.

    Workflow (called once per arriving client update)
    --------------------------------------------------
    1. ``correct()``            — apply staleness correction to the gradient.
    2. ``compute_raw_divergence()``       — score the *original* gradient vs. consensus.
    3. ``compute_corrected_divergence()`` — score the *corrected* gradient vs. consensus.
    4. ``log_separation()``     — persist both scores for downstream analysis.
    5. ``get_divergence_logs()``— retrieve accumulated logs (e.g. for plotting).

    The caller (FL server) uses the *corrected* divergence as the reputation
    weight fed into ``reputation_aggregated()``: lower corrected divergence
    → more trusted → higher weight.

    Parameters
    ----------
    alpha        : float
        Correction strength α ∈ (0, 1].  Typical value: 0.5 (config.sabd_alpha).
        α = 1 fully subtracts drift; α < 1 applies a softer correction.
    model_history : ModelHistoryBuffer
        Rolling snapshot buffer from the FL server.  Used to look up θ_s
        (the model at the round the client started training) so that
        Δ_{s→t} = θ_t − θ_s can be computed.
    """

    def __init__(self, alpha: float, model_history: ModelHistoryBuffer):
        if not (0.0 < alpha <= 1.0):
            raise ValueError(
                f"SABDCorrector: alpha must be in (0, 1], got {alpha}."
            )
        self.alpha = alpha
        self.model_history = model_history

        # Per-client divergence logs keyed by client_id → list of (round, score)
        self._raw_divs: dict = {}
        self._corrected_divs: dict = {}

        logger.info(
            "SABDCorrector initialised (alpha=%.3f, history_capacity=%d).",
            alpha, model_history.max_size,
        )

    # ------------------------------------------------------------------
    # Core correction
    # ------------------------------------------------------------------

    def correct(
        self,
        gradient: dict,
        client_round: int,
        current_weights: dict,
    ) -> dict:
        """
        Apply staleness correction to a client gradient.

        Formula::

            g*_i[k] = g_i[k] + α · Δ_{s→t}[k]

        where Δ_{s→t}[k] = θ_t[k] − θ_s[k] is the model drift from the
        client's start version (``client_round``) to the current server weights.

        If ``client_round`` is not present in the history buffer (e.g. the
        buffer evicted it due to capacity limits), the gradient is returned
        unchanged and a warning is logged.  This is a safe degradation: the
        correction is skipped rather than applying an incorrect drift estimate.

        Parameters
        ----------
        gradient      : dict[str, np.ndarray]
            Raw weight delta from client i:  g_i = θ_local − θ_start.
        client_round  : int
            The server version at which client i began local training (s).
        current_weights : dict[str, np.ndarray]
            The *current* global model weights θ_t (version t).

        Returns
        -------
        dict[str, np.ndarray]
            Corrected gradient g*_i.  A new dict; ``gradient`` is not modified.
        """
        if not self.model_history.has_version(client_round):
            logger.warning(
                "SABDCorrector.correct — version %d not in history buffer "
                "(oldest=%s). Returning gradient uncorrected.",
                client_round,
                self.model_history.get_oldest_version(),
            )
            return {k: v.copy() for k, v in gradient.items()}

        # Δ_{s→t}[k] = θ_t[k] − θ_s[k]
        drift = self.model_history.get_drift(client_round, current_weights)

        # g*_i[k] = g_i[k] + α · Δ_{s→t}[k]
        corrected = {
            k: gradient[k] + self.alpha * drift[k]
            for k in gradient
        }

        logger.debug(
            "SABDCorrector.correct — client_round=%d, alpha=%.3f, "
            "drift_norm=%.6f.",
            client_round,
            self.alpha,
            float(np.linalg.norm(
                np.concatenate([d.flatten() for d in drift.values()])
            )),
        )
        return corrected

    # ------------------------------------------------------------------
    # Divergence measures
    # ------------------------------------------------------------------

    def _cosine_similarity(self, a: dict, b: dict) -> float:
        """
        Cosine similarity between two parameter dicts treated as flat vectors.

        Formula::

            cos(a, b) = (a · b) / (‖a‖ · ‖b‖ + ε)

        The 1e-8 epsilon prevents division-by-zero for zero-norm vectors
        (e.g. a zero_gradient Byzantine attack).

        Parameters
        ----------
        a, b : dict[str, np.ndarray]
            Parameter dicts with identical keys and shapes.

        Returns
        -------
        float
            Cosine similarity in [-1, 1].
        """
        flat_a = np.concatenate([a[k].flatten() for k in a])
        flat_b = np.concatenate([b[k].flatten() for k in b])

        dot = float(np.dot(flat_a, flat_b))
        norm_a = float(np.linalg.norm(flat_a))
        norm_b = float(np.linalg.norm(flat_b))

        # cos(a, b) = (a · b) / (‖a‖ · ‖b‖ + ε)
        return dot / (norm_a * norm_b + 1e-8)

    def compute_raw_divergence(self, gradient: dict, consensus: dict) -> float:
        """
        Cosine divergence of the *raw* (uncorrected) gradient from consensus.

        Formula::

            div_raw = 1 − cos(g_i, consensus)

        Values near 0 → aligned with consensus (honest signal).
        Values near 2 → anti-aligned (sign-flip attack signature).

        Parameters
        ----------
        gradient  : dict[str, np.ndarray]   Raw client gradient g_i.
        consensus : dict[str, np.ndarray]   Current aggregate / consensus gradient.

        Returns
        -------
        float   Raw divergence score in [0, 2].
        """
        # div_raw = 1 − cos(g_i, consensus)
        div = 1.0 - self._cosine_similarity(gradient, consensus)
        logger.debug("compute_raw_divergence — div=%.6f.", div)
        return div

    def compute_corrected_divergence(self, g_star: dict, consensus: dict) -> float:
        """
        Cosine divergence of the *corrected* gradient g*_i from consensus.

        Formula::

            div_corrected = 1 − cos(g*_i, consensus)

        Because g*_i has the staleness drift removed, this score reflects
        true behavioural divergence rather than staleness-confounded raw divergence.

        Parameters
        ----------
        g_star    : dict[str, np.ndarray]   Staleness-corrected gradient.
        consensus : dict[str, np.ndarray]   Current aggregate / consensus gradient.

        Returns
        -------
        float   Corrected divergence score in [0, 2].
        """
        # div_corrected = 1 − cos(g*_i, consensus)
        div = 1.0 - self._cosine_similarity(g_star, consensus)
        logger.debug("compute_corrected_divergence — div=%.6f.", div)
        return div

    # ------------------------------------------------------------------
    # Logging and retrieval
    # ------------------------------------------------------------------

    def log_separation(
        self,
        raw_div: float,
        corrected_div: float,
        client_id: int,
        round_num: int,
    ) -> None:
        """
        Persist raw and corrected divergence scores for a client in a given round.

        Scores are appended to per-client lists so that the full history of
        how well SABD separates staleness from malice can be plotted or
        analysed after training.  Use ``get_divergence_logs()`` to retrieve.

        Parameters
        ----------
        raw_div       : float   Divergence of the uncorrected gradient.
        corrected_div : float   Divergence of the staleness-corrected gradient.
        client_id     : int     Identifier of the reporting client.
        round_num     : int     Current server round number.
        """
        if client_id not in self._raw_divs:
            self._raw_divs[client_id] = []
            self._corrected_divs[client_id] = []

        self._raw_divs[client_id].append((round_num, raw_div))
        self._corrected_divs[client_id].append((round_num, corrected_div))

        # Separation: positive means correction reduced the divergence score
        # (correct direction for an honest-but-stale client).
        separation = raw_div - corrected_div
        logger.info(
            "SABD log — client=%d, round=%d, raw_div=%.4f, "
            "corrected_div=%.4f, separation=%.4f.",
            client_id, round_num, raw_div, corrected_div, separation,
        )

    def get_divergence_logs(self) -> tuple:
        """
        Return accumulated per-client divergence logs.

        Returns
        -------
        tuple[dict, dict]
            ``(raw_divs, corrected_divs)`` where each dict maps
            ``client_id → list[(round_num, score)]``.
            Lists are in insertion order (chronological).
        """
        return self._raw_divs, self._corrected_divs
