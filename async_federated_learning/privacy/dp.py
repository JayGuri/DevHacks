# privacy/dp.py — DifferentialPrivacyMechanism + legacy PrivacyEngine
"""
privacy/dp.py
=============
Contains:
- DifferentialPrivacyMechanism: ayush's rigorous (epsilon, delta)-DP mechanism
  with clip_gradients, add_noise, privatize, and compute_epsilon.
- PrivacyEngine: akshat's legacy engine (backward compat for WebSocket client).
  Delegates to DifferentialPrivacyMechanism internally.
"""

import logging
import math

import numpy as np

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Advanced DP mechanism (from ayush)
# ---------------------------------------------------------------------------

class DifferentialPrivacyMechanism:
    """Client-side (epsilon, delta)-DP via gradient clipping and Gaussian noise.

    Two-step pipeline:
    1. clip_gradients — project onto L2 ball of radius clip_norm
    2. add_noise — add N(0, sigma^2 I) where sigma = noise_multiplier * clip_norm

    Parameters
    ----------
    noise_multiplier : float — sigma_mult (0.5-2.0 typical)
    clip_norm        : float — L2 sensitivity bound C (0.1-5.0 typical)
    """

    def __init__(self, noise_multiplier: float, clip_norm: float) -> None:
        self.noise_multiplier = noise_multiplier
        self.clip_norm = clip_norm
        logger.info(
            "DifferentialPrivacyMechanism initialised — "
            "noise_multiplier=%.4f, clip_norm=%.4f",
            noise_multiplier, clip_norm,
        )

    def clip_gradients(self, weight_delta: dict) -> dict:
        """Bound L2 norm of the update to clip_norm (sensitivity bounding)."""
        flat = np.concatenate([v.flatten() for v in weight_delta.values()])
        global_norm = np.linalg.norm(flat)

        clip_factor = min(1.0, self.clip_norm / (global_norm + 1e-8))
        clipped = {k: v * clip_factor for k, v in weight_delta.items()}

        logger.debug(
            "clip_gradients — global_norm=%.4f, clip_norm=%.4f, "
            "clip_factor=%.4f (active=%s)",
            global_norm, self.clip_norm, clip_factor, clip_factor < 1.0,
        )
        return clipped

    def add_noise(self, weight_delta: dict) -> dict:
        """Add calibrated Gaussian noise: sigma = noise_multiplier * clip_norm."""
        noise_std = self.noise_multiplier * self.clip_norm
        noised = {
            k: v + np.random.normal(0.0, noise_std, v.shape)
            for k, v in weight_delta.items()
        }
        logger.debug(
            "add_noise — noise_std=%.6f (noise_multiplier=%.4f * clip_norm=%.4f)",
            noise_std, self.noise_multiplier, self.clip_norm,
        )
        return noised

    def privatize(self, weight_delta: dict) -> dict:
        """Apply full DP pipeline: clip then add noise."""
        clipped = self.clip_gradients(weight_delta)
        noised = self.add_noise(clipped)
        logger.debug("privatize — clip + noise applied.")
        return noised

    def compute_epsilon(self, num_rounds: int, dataset_size: int,
                        delta: float = 1e-5) -> float:
        """Estimate cumulative privacy budget epsilon after num_rounds.

        Uses strong composition bound:
            epsilon ~= sqrt(2T * ln(1.25/delta)) * (q / sigma_mult)
        """
        q = (self.batch_size / dataset_size) if hasattr(self, "batch_size") else 0.01

        epsilon = (
            math.sqrt(2 * num_rounds * math.log(1.25 / delta))
            * q
            / self.noise_multiplier
        )

        if epsilon > 10.0:
            logger.warning(
                "Estimated epsilon=%.2f > 10 after %d rounds. Privacy is WEAK.",
                epsilon, num_rounds,
            )
        elif epsilon < 1.0:
            logger.info("Estimated epsilon=%.4f < 1 after %d rounds. Strong privacy.", epsilon, num_rounds)
        else:
            logger.info("Estimated epsilon=%.4f after %d rounds (delta=%.2e).", epsilon, num_rounds, delta)

        return epsilon


# ---------------------------------------------------------------------------
# Legacy PrivacyEngine (from akshat — backward compat for WebSocket client)
# ---------------------------------------------------------------------------

class PrivacyEngine:
    """Backward-compatible wrapper around DifferentialPrivacyMechanism.

    Provides the same API as akshat's original PrivacyEngine:
    - clip_and_noise(weight_diff) -> dict
    - apply_secure_aggregation_mask(weight_diff) -> dict
    - process(weight_diff) -> dict   (clip + noise + mask)
    - get_privacy_budget() -> dict
    """

    def __init__(self, max_grad_norm: float = 1.0, noise_multiplier: float = 1.1,
                 delta: float = 1e-5):
        self.max_grad_norm = max_grad_norm
        self.noise_multiplier = noise_multiplier
        self.delta = delta
        self.epsilon_spent = 0.0
        self._step_count = 0

        self._dp = DifferentialPrivacyMechanism(
            noise_multiplier=noise_multiplier,
            clip_norm=max_grad_norm,
        )

    def clip_and_noise(self, weight_diff: dict) -> dict:
        """Clip gradients + add Gaussian noise + update privacy accounting."""
        result = self._dp.privatize(weight_diff)

        # Privacy accounting (simplified moments accountant)
        if self.noise_multiplier > 0.0:
            epsilon_step = 2.0 * math.log(1.0 / self.delta) / (self.noise_multiplier ** 2)
        else:
            epsilon_step = float("inf")
        self.epsilon_spent += epsilon_step
        self._step_count += 1

        logger.debug(
            "DP applied: sigma=%.4f, epsilon_step=%.4f, total_epsilon=%.4f, steps=%d",
            self.noise_multiplier * self.max_grad_norm,
            epsilon_step, self.epsilon_spent, self._step_count,
        )
        return result

    def apply_secure_aggregation_mask(self, weight_diff: dict) -> dict:
        """Simulates zero-sum masking from Secure Aggregation protocol.
        
        NOTE: True zero-sum masking requires symmetric key exchange (Diffie-Hellman)
        which is not yet integrated into the client training loop.
        Adding uniform noise here is destructive and degrades the global model.
        For now, this is a pass-through until true Secure Aggregation is active.
        """
        return weight_diff

    def process(self, weight_diff: dict) -> dict:
        """Full pipeline: clip_and_noise() + apply_secure_aggregation_mask()."""
        return self.apply_secure_aggregation_mask(self.clip_and_noise(weight_diff))

    def get_privacy_budget(self) -> dict:
        """Returns current privacy budget consumption."""
        return {
            "epsilon": round(self.epsilon_spent, 6),
            "delta": self.delta,
            "steps": self._step_count,
        }
