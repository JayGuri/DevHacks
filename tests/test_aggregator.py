# tests/test_aggregator.py — Tests for gatekeeper, SABD, aggregation pipeline
import os
import sys
import pytest
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from detection.anomaly import check_l2_norm
from detection.sabd import run_sabd
from aggregation.trimmed_mean import trimmed_mean
from aggregation.reputation import compute_staleness_weight
from aggregation.aggregator import Aggregator
from config import Settings


def make_update(client_id, scale=0.01, shapes=None):
    """Helper to create a synthetic update."""
    if shapes is None:
        shapes = {"layer.weight": (64, 32), "layer.bias": (64,)}
    weights = {}
    for name, shape in shapes.items():
        weights[name] = np.random.normal(0, scale, shape).astype(np.float32)
    return {
        "client_id": client_id,
        "weights": weights,
        "num_samples": 100,
        "global_round_received": 0,
        "task": "femnist",
    }


class TestGatekeeper:
    """Test L2 norm gatekeeper (first defense layer)."""

    def test_gatekeeper_blocks_l2_outlier(self):
        """Test 1: Gatekeeper blocks update with norm > threshold (2500 > 500)."""
        shapes = {"layer.weight": (64, 32), "layer.bias": (64,)}
        weights = {}
        # Create weight_diff with large norm (~2500)
        for name, shape in shapes.items():
            weights[name] = np.random.normal(0, 1.0, shape).astype(np.float32)

        # Scale to reach target norm of ~2500
        flat = np.concatenate([v.flatten() for v in weights.values()])
        current_norm = np.linalg.norm(flat)
        target_norm = 2500.0
        scale = target_norm / current_norm
        weights = {k: v * scale for k, v in weights.items()}

        passed, norm = check_l2_norm(weights, 500.0)
        assert passed is False
        assert norm > 500.0

    def test_gatekeeper_passes_honest_update(self):
        """Test 2: Gatekeeper passes honest update with norm < 100."""
        weights = {
            "layer.weight": np.random.normal(0, 0.001, (64, 32)).astype(np.float32),
            "layer.bias": np.random.normal(0, 0.001, (64,)).astype(np.float32),
        }
        passed, norm = check_l2_norm(weights, 500.0)
        assert passed is True
        assert norm < 100.0


class TestSABD:
    """Test Multi-Krum (SABD) detection."""

    def test_sabd_rejects_mallory(self):
        """Test 3: SABD rejects Mallory's sign-flip amplified update."""
        np.random.seed(42)
        shapes = {"layer.weight": (64, 32), "layer.bias": (64,)}

        alice = make_update("alice", scale=0.01, shapes=shapes)
        bob = make_update("bob", scale=0.01, shapes=shapes)

        # Mallory: sign-flip amplified
        mallory_weights = {}
        for name, shape in shapes.items():
            mallory_weights[name] = np.random.normal(0, 0.01, shape).astype(np.float32) * -5.0
        mallory = {
            "client_id": "mallory",
            "weights": mallory_weights,
            "num_samples": 100,
            "global_round_received": 0,
        }

        result = run_sabd([alice, bob, mallory], byzantine_fraction=0.3)

        assert result.trust_scores["mallory"] == 0.0
        assert result.trust_scores["alice"] == 1.0
        assert result.trust_scores["bob"] == 1.0


class TestTrimmedMean:
    """Test trimmed mean aggregation."""

    def test_trimmed_mean_resists_outlier(self):
        """Test 4: Trimmed mean aggregation resists outlier."""
        np.random.seed(42)
        shapes = {"layer.weight": (32, 16)}

        alice = make_update("alice", scale=0.01, shapes=shapes)
        bob = make_update("bob", scale=0.01, shapes=shapes)

        mallory_weights = {
            "layer.weight": np.random.normal(0, 0.01, (32, 16)).astype(np.float32) * -5.0,
        }
        mallory = {
            "client_id": "mallory",
            "weights": mallory_weights,
            "num_samples": 100,
        }

        aggregated, trust_scores = trimmed_mean([alice, bob, mallory], trim_fraction=0.2)

        # Compute mean of Alice and Bob for comparison
        honest_mean = (alice["weights"]["layer.weight"] + bob["weights"]["layer.weight"]) / 2.0

        # Aggregated should be close to honest mean (within 0.3)
        diff = np.abs(aggregated["layer.weight"] - honest_mean)
        assert np.all(diff < 0.3), f"Max diff: {np.max(diff)}"


class TestStaleness:
    """Test staleness weight computation."""

    def test_staleness_weight_formula(self):
        """Test 5: Staleness weight formula correctness."""
        # Recent update should have higher weight than older one
        weight_old = compute_staleness_weight(1, 10, 0.5, 10)
        weight_recent = compute_staleness_weight(9, 10, 0.5, 10)
        assert 0 < weight_old < 1
        assert weight_recent > weight_old

        # Too stale update should return 0.0
        weight_stale = compute_staleness_weight(0, 15, 0.5, 10)
        assert weight_stale == 0.0

        # Fresh update (staleness=0) returns 1.0
        weight_fresh = compute_staleness_weight(10, 10, 0.5, 10)
        assert weight_fresh == 1.0


class TestAggregatorPipeline:
    """Test the full two-layer aggregation pipeline."""

    def test_aggregator_two_layer_pipeline(self):
        """Test 6: Aggregator rejects Mallory via gatekeeper when L2 > threshold."""
        np.random.seed(42)
        shapes = {"layer.weight": (32, 16), "layer.bias": (32,)}

        alice = make_update("alice", scale=0.01, shapes=shapes)
        bob = make_update("bob", scale=0.01, shapes=shapes)
        charlie = make_update("charlie", scale=0.01, shapes=shapes)

        # Mallory: massive norm to trigger gatekeeper
        mallory_weights = {}
        for name, shape in shapes.items():
            w = np.random.normal(0, 0.01, shape).astype(np.float32)
            flat = w.flatten()
            current_norm = np.linalg.norm(flat)
            target_norm = 1000.0
            mallory_weights[name] = w * (target_norm / max(current_norm, 1e-8))
        mallory = {
            "client_id": "mallory",
            "weights": mallory_weights,
            "num_samples": 100,
            "global_round_received": 0,
            "task": "femnist",
        }

        config = Settings()
        config.L2_NORM_THRESHOLD = 500.0
        aggregator = Aggregator(strategy="krum", config=config)

        result = aggregator.aggregate(
            [alice, bob, charlie, mallory], current_round=1, task="femnist"
        )

        assert "mallory" in result.gatekeeper_rejected
        assert result.trust_scores.get("mallory", 1.0) == 0.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
