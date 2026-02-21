# privacy/dp.py — PrivacyEngine: gradient clipping, DP noise, secure aggregation mask
import math
import numpy as np
import logging

logger = logging.getLogger("fedbuff.privacy")


class PrivacyEngine:
    """Implements local differential privacy for federated learning updates.

    Applies three operations sequentially:
    1. Global L2 gradient clipping
    2. Gaussian noise addition (calibrated to clipping norm)
    3. Secure aggregation mask simulation
    """

    def __init__(self, max_grad_norm: float = 1.0, noise_multiplier: float = 1.1,
                 delta: float = 1e-5):
        self.max_grad_norm = max_grad_norm
        self.noise_multiplier = noise_multiplier
        self.delta = delta
        self.epsilon_spent = 0.0
        self._step_count = 0

    def clip_and_noise(self, weight_diff: dict) -> dict:
        """
        Step 1 — Global L2 clipping:
          Flatten all arrays. If norm > max_grad_norm, scale all by (max_grad_norm / norm).
        Step 2 — Gaussian noise:
          sigma = noise_multiplier * max_grad_norm
          For each array: add numpy.random.normal(0, sigma, array.shape)
        Step 3 — Privacy accounting (simplified moments accountant):
          epsilon_step = 2.0 * math.log(1.0 / delta) / (noise_multiplier ** 2)
          epsilon_spent += epsilon_step
          step_count += 1
        Returns modified weight_diff.
        """
        # Step 1: Global L2 clipping
        all_flat = np.concatenate([v.flatten() for v in weight_diff.values()])
        global_norm = float(np.linalg.norm(all_flat))

        clipped = {}
        if global_norm > self.max_grad_norm:
            scale_factor = self.max_grad_norm / global_norm
            for key, val in weight_diff.items():
                clipped[key] = val * scale_factor
            logger.debug(
                "Clipped gradient: norm %.4f -> %.4f (scale %.6f)",
                global_norm, self.max_grad_norm, scale_factor
            )
        else:
            for key, val in weight_diff.items():
                clipped[key] = val.copy()

        # Step 2: Gaussian noise
        sigma = self.noise_multiplier * self.max_grad_norm
        noised = {}
        for key, val in clipped.items():
            noise = np.random.normal(0.0, sigma, val.shape)
            noised[key] = val + noise

        # Step 3: Privacy accounting (simplified moments accountant)
        epsilon_step = 2.0 * math.log(1.0 / self.delta) / (self.noise_multiplier ** 2)
        self.epsilon_spent += epsilon_step
        self._step_count += 1

        logger.debug(
            "DP applied: sigma=%.4f, epsilon_step=%.4f, total_epsilon=%.4f, steps=%d",
            sigma, epsilon_step, self.epsilon_spent, self._step_count
        )

        return noised

    def apply_secure_aggregation_mask(self, weight_diff: dict) -> dict:
        """
        Simulates Zero-Sum Masking from Secure Aggregation protocol.
        Adds pseudo-random mask from Uniform(-0.001, 0.001) to each parameter array.

        This mask is not cryptographically coupled to other clients' masks.
        It represents the masking layer for demonstration purposes only.

        Returns masked weight_diff.
        """
        masked = {}
        for key, val in weight_diff.items():
            # This mask is not cryptographically coupled to other clients' masks.
            # It represents the masking layer for demonstration purposes only.
            mask = np.random.uniform(-0.001, 0.001, val.shape)
            masked[key] = val + mask
        return masked

    def process(self, weight_diff: dict) -> dict:
        """Calls clip_and_noise() then apply_secure_aggregation_mask(). Returns result."""
        return self.apply_secure_aggregation_mask(self.clip_and_noise(weight_diff))

    def get_privacy_budget(self) -> dict:
        """Returns current privacy budget consumption."""
        return {
            "epsilon": round(self.epsilon_spent, 6),
            "delta": self.delta,
            "steps": self._step_count,
        }
