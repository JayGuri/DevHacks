# tests/test_privacy_engine.py — Tests for PrivacyEngine
import os
import sys
import pytest
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from privacy.dp import PrivacyEngine


def make_weight_diff(norm_target=1.0):
    """Create a weight_diff with a specific L2 norm."""
    shapes = {"layer.weight": (32, 16), "layer.bias": (32,)}
    diff = {}
    for name, shape in shapes.items():
        diff[name] = np.random.normal(0, 1.0, shape).astype(np.float32)

    # Scale to target norm
    flat = np.concatenate([v.flatten() for v in diff.values()])
    current_norm = np.linalg.norm(flat)
    if current_norm > 0:
        scale = norm_target / current_norm
        diff = {k: v * scale for k, v in diff.items()}

    return diff


class TestClipping:
    """Test gradient clipping."""

    def test_clipping_reduces_norm(self):
        """Test 1: Clipping should reduce norm to max_grad_norm."""
        engine = PrivacyEngine(max_grad_norm=1.0, noise_multiplier=0.0001, delta=1e-5)
        diff = make_weight_diff(norm_target=100.0)

        clipped = engine.clip_and_noise(diff)

        # Compute norm of clipped result (should be close to max_grad_norm,
        # plus small noise from noise_multiplier=0.0001)
        flat = np.concatenate([v.flatten() for v in clipped.values()])
        clipped_norm = np.linalg.norm(flat)

        # With near-zero noise multiplier, clipped norm should be close to 1.0
        assert clipped_norm < 5.0, f"Clipped norm too high: {clipped_norm}"


class TestNoise:
    """Test noise addition properties."""

    def test_noise_is_zero_centered(self):
        """Test 2: Noise should be approximately zero-centered over many applications."""
        engine = PrivacyEngine(max_grad_norm=10.0, noise_multiplier=1.0, delta=1e-5)

        accumulated = None
        n_trials = 500

        for _ in range(n_trials):
            diff = {
                "w": np.zeros((16, 8), dtype=np.float32),
            }
            noised = engine.clip_and_noise(diff)
            if accumulated is None:
                accumulated = noised["w"].copy()
            else:
                accumulated += noised["w"]

        mean_val = np.mean(accumulated / n_trials)
        std_val = np.std(accumulated / n_trials)

        assert abs(mean_val) < 0.1, f"Mean not near zero: {mean_val}"
        # With noise_multiplier=1.0 and max_grad_norm=10.0, sigma=10.0
        # After averaging 500 trials, std should still be noticeable but smaller
        assert std_val > 0.01, f"Std too small (noise may not be applied): {std_val}"


class TestEpsilon:
    """Test privacy budget accounting."""

    def test_monotonic_epsilon(self):
        """Test 3: Epsilon should increase monotonically with each step."""
        engine = PrivacyEngine(max_grad_norm=1.0, noise_multiplier=1.1, delta=1e-5)

        previous_epsilon = 0.0
        for i in range(20):
            diff = {"w": np.random.normal(0, 0.01, (8, 4)).astype(np.float32)}
            engine.clip_and_noise(diff)
            budget = engine.get_privacy_budget()
            assert budget["epsilon"] > previous_epsilon, \
                f"Epsilon not increasing at step {i}: {budget['epsilon']} <= {previous_epsilon}"
            previous_epsilon = budget["epsilon"]


class TestSecureMask:
    """Test secure aggregation mask."""

    def test_secure_mask_is_nonzero_and_small(self):
        """Test 4: Secure mask should add non-zero but small perturbations."""
        engine = PrivacyEngine(max_grad_norm=1.0, noise_multiplier=1.0, delta=1e-5)

        diff = {
            "w": np.zeros((32, 16), dtype=np.float32),
            "b": np.zeros((32,), dtype=np.float32),
        }

        masked = engine.apply_secure_aggregation_mask(diff)

        # At least one value should be non-zero
        all_vals = np.concatenate([v.flatten() for v in masked.values()])
        assert np.any(all_vals != 0), "All values are zero — mask not applied"

        # All values should be small (< 0.01 from Uniform(-0.001, 0.001))
        assert np.all(np.abs(all_vals) < 0.01), \
            f"Mask values too large: max={np.max(np.abs(all_vals))}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
