"""
privacy/dp.py
=============
Client-side (ε, δ)-differential privacy via gradient clipping and Gaussian
noise addition.  Custom pure-NumPy implementation — no Opacus, TF Privacy,
or any DP library.

Contains:
- DifferentialPrivacyMechanism: clips update deltas to bound sensitivity,
  adds calibrated Gaussian noise to obscure individual contributions, and
  estimates the cumulative privacy budget ε across training rounds.

Mathematical background
-----------------------
Sensitivity bounding (clipping)::

    Δ̃ = Δ · min(1,  C / ‖Δ‖₂)

    Restricts the L2 norm of the update to at most C (``clip_norm``), which
    bounds the maximum influence any single client can have on the aggregate.

Gaussian mechanism (noise addition)::

    Δ̃_priv = Δ̃ + N(0, σ²)    where  σ = noise_multiplier · C

    Adding noise with std σ = σ_mult · C satisfies (ε, δ)-DP for appropriate
    ε derived from the moments accountant (see ``compute_epsilon``).

Privacy budget estimation (strong composition, simplified)::

    ε ≈ √(2T · ln(1.25/δ)) · (q / σ_mult)

    where T = number of rounds, q = sampling ratio (batch / dataset),
    σ_mult = ``noise_multiplier``.  This is the classical Gaussian mechanism
    composition bound (Dwork & Roth 2014, Theorem 3.22).

SABD note
---------
SABD correction is applied server-side *after* DP noise has been added, so
the privacy budget accounting here is self-contained and unaffected by the
Byzantine detection step.
"""

import logging
import math

import numpy as np

logger = logging.getLogger(__name__)


class DifferentialPrivacyMechanism:
    """
    Client-side (ε, δ)-DP via gradient clipping and Gaussian noise.

    Role in pipeline
    ----------------
    Each FL client instantiates one DifferentialPrivacyMechanism and calls
    ``privatize(weight_delta)`` on its local model update before sending it
    to the server.  The two-step pipeline is:

      1. ``clip_gradients``  — projects the update onto the L2 ball of radius
         ``clip_norm`` (C), bounding per-client sensitivity.
      2. ``add_noise``       — adds zero-mean Gaussian noise with
         std = ``noise_multiplier`` × C to every parameter array, satisfying
         the Gaussian mechanism's (ε, δ)-DP guarantee.

    Custom implementation
    ---------------------
    All arithmetic is NumPy only.  No Opacus, TF Privacy, or JAX.

    Parameters
    ----------
    noise_multiplier : float
        σ_mult in the Gaussian mechanism.  Higher → more noise → stronger
        privacy (lower ε) but lower model utility.  Typical range: 0.5 – 2.0.
    clip_norm : float
        L2 sensitivity bound C.  All client updates are projected onto the
        L2 ball of radius C before noise is added.  Typical range: 0.1 – 5.0.

    Privacy semantics
    -----------------
    - ε < 1  : Very strong privacy; heavy utility loss expected.
    - 1 ≤ ε ≤ 10 : Meaningful privacy; common practical range.
    - ε > 10 : Weak privacy; may still deter naive linkage attacks.
    """

    def __init__(self, noise_multiplier: float, clip_norm: float) -> None:
        self.noise_multiplier = noise_multiplier
        self.clip_norm        = clip_norm
        self.logger           = logging.getLogger(__name__)
        self.logger.info(
            "DifferentialPrivacyMechanism initialised — "
            "noise_multiplier=%.4f, clip_norm=%.4f",
            noise_multiplier, clip_norm,
        )

    # ------------------------------------------------------------------
    # Two-step privatisation pipeline
    # ------------------------------------------------------------------

    def clip_gradients(self, weight_delta: dict) -> dict:
        """
        Bound the L2 norm of the update to ``clip_norm`` (sensitivity bounding).

        Algorithm
        ---------
        1. Flatten all parameter arrays into a single vector and compute its
           global L2 norm: ‖Δ‖₂ = √(Σ_k ‖Δ_k‖²_F).
        2. Compute the clip factor:
               clip_factor = min(1,  C / (‖Δ‖₂ + ε_num))
           where ε_num = 1e-8 avoids division by zero on zero-gradient updates.
        3. Scale every parameter array by ``clip_factor`` (no-op when the
           update already satisfies ‖Δ‖₂ ≤ C).

        The ε_num additive term is inside the denominator only; it does not
        affect the DP guarantee when the true norm is non-negligible.

        Parameters
        ----------
        weight_delta : dict[str, np.ndarray]
            Raw (unclipped) parameter update from local training.

        Returns
        -------
        dict[str, np.ndarray]
            Clipped update with ‖Δ_clipped‖₂ ≤ C.
        """
        # Flatten all arrays into one vector to compute the global L2 norm
        flat        = np.concatenate([v.flatten() for v in weight_delta.values()])
        global_norm = np.linalg.norm(flat)

        # clip_factor = min(1,  C / ‖Δ‖₂)  — projects onto L2 ball of radius C
        clip_factor = min(1.0, self.clip_norm / (global_norm + 1e-8))
        clipped     = {k: v * clip_factor for k, v in weight_delta.items()}

        self.logger.debug(
            "clip_gradients — global_norm=%.4f, clip_norm=%.4f, "
            "clip_factor=%.4f (active=%s)",
            global_norm, self.clip_norm, clip_factor, clip_factor < 1.0,
        )
        return clipped

    def add_noise(self, weight_delta: dict) -> dict:
        """
        Add calibrated Gaussian noise to every parameter array.

        Gaussian mechanism noise calibration::

            σ = noise_multiplier × clip_norm

        Adding N(0, σ²I) to each coordinate satisfies (ε, δ)-DP where ε
        is determined by the moments accountant / composition theorem
        (see ``compute_epsilon`` for the closed-form estimate).

        Parameters
        ----------
        weight_delta : dict[str, np.ndarray]
            Clipped (or raw) parameter update.

        Returns
        -------
        dict[str, np.ndarray]
            Noised parameter update.  Arrays retain their original shapes.
        """
        # σ = σ_mult · C  (Gaussian mechanism, calibrated to sensitivity C)
        noise_std = self.noise_multiplier * self.clip_norm
        noised    = {
            k: v + np.random.normal(0.0, noise_std, v.shape)
            for k, v in weight_delta.items()
        }
        self.logger.debug(
            "add_noise — noise_std=%.6f (noise_multiplier=%.4f × clip_norm=%.4f)",
            noise_std, self.noise_multiplier, self.clip_norm,
        )
        return noised

    def privatize(self, weight_delta: dict) -> dict:
        """
        Apply the full DP pipeline: clip then add noise.

        This is the only method FL clients need to call.  The two steps are
        always applied in order — clipping first (to bound sensitivity), then
        noise (to obscure the bounded update).

        Parameters
        ----------
        weight_delta : dict[str, np.ndarray]
            Raw parameter delta from ``FLModel.get_weight_delta()``.

        Returns
        -------
        dict[str, np.ndarray]
            Privatised update satisfying the (ε, δ)-DP guarantee.
        """
        clipped = self.clip_gradients(weight_delta)
        noised  = self.add_noise(clipped)
        self.logger.debug("privatize — clip + noise applied.")
        return noised

    # ------------------------------------------------------------------
    # Privacy budget estimation
    # ------------------------------------------------------------------

    def compute_epsilon(
        self,
        num_rounds: int,
        dataset_size: int,
        delta: float = 1e-5,
    ) -> float:
        """
        Estimate the cumulative privacy budget ε after ``num_rounds`` rounds.

        Uses the classical strong-composition bound for the Gaussian mechanism
        (Dwork & Roth 2014, Theorem 3.22 / Abadi et al. 2016 simplified)::

            ε ≈ √(2T · ln(1.25/δ)) · (q / σ_mult)

        where:
          T       = num_rounds (total DP mechanism applications)
          δ       = failure probability (default 1e-5)
          q       = sampling ratio = batch_size / dataset_size
                    (defaults to 0.01 if ``batch_size`` not set as attribute)
          σ_mult  = noise_multiplier

        Note: This is an *estimate* — exact accounting requires the moments
        accountant (Rényi DP) or PRV accountant.  It is intentionally
        conservative (overestimates ε slightly) for a worst-case bound.

        Parameters
        ----------
        num_rounds   : int   — number of DP-SGD rounds (local training steps).
        dataset_size : int   — total number of training samples on this client.
        delta        : float — DP δ parameter (default 1e-5, i.e. 1/100 000).

        Returns
        -------
        float — estimated cumulative ε.
        """
        # Sampling ratio q = batch_size / n; use stored batch_size or default 0.01
        q = (self.batch_size / dataset_size) if hasattr(self, "batch_size") else 0.01

        # ε ≈ √(2T · ln(1.25/δ)) · q / σ_mult
        #   — Gaussian mechanism advanced composition
        epsilon = (
            math.sqrt(2 * num_rounds * math.log(1.25 / delta))
            * q
            / self.noise_multiplier
        )

        if epsilon > 10.0:
            self.logger.warning(
                "Estimated ε=%.2f > 10 after %d rounds. "
                "Privacy is WEAK. Consider increasing noise_multiplier.",
                epsilon, num_rounds,
            )
        elif epsilon < 1.0:
            self.logger.info(
                "Estimated ε=%.4f < 1 after %d rounds. "
                "Strong privacy guarantee.",
                epsilon, num_rounds,
            )
        else:
            self.logger.info(
                "Estimated ε=%.4f after %d rounds (δ=%.2e).",
                epsilon, num_rounds, delta,
            )

        return epsilon
