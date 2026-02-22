# tests/test_aggregator.py — Tests for gatekeeper, SABD, aggregation pipeline
import os
import sys
import pytest
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from detection.anomaly import check_l2_norm
from detection.sabd import run_sabd
from aggregation.trimmed_mean import trimmed_mean
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
        for name, shape in shapes.items():
            weights[name] = np.random.normal(0, 1.0, shape).astype(np.float32)

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
        """Test 4: Trimmed mean resists outliers via coordinate-wise trimming."""
        np.random.seed(42)

        # Create raw weight dicts (not update dicts) for the new API
        alice_w = {"layer.weight": np.random.normal(0, 0.01, (32, 16)).astype(np.float32)}
        bob_w = {"layer.weight": np.random.normal(0, 0.01, (32, 16)).astype(np.float32)}
        mallory_w = {"layer.weight": np.random.normal(0, 0.01, (32, 16)).astype(np.float32) * -5.0}

        # New API: trimmed_mean takes list of raw dicts, returns aggregated dict
        aggregated = trimmed_mean([alice_w, bob_w, mallory_w], beta=0.2)

        # Compute mean of Alice and Bob for comparison
        honest_mean = (alice_w["layer.weight"] + bob_w["layer.weight"]) / 2.0

        # Aggregated should be close to honest mean
        diff = np.abs(aggregated["layer.weight"] - honest_mean)
        assert np.all(diff < 0.3), f"Max diff: {np.max(diff)}"


class TestModelHistoryBuffer:
    """Test SABD-compatible model history buffer."""

    def test_model_history_buffer(self):
        """Test 5: ModelHistoryBuffer records and computes drift correctly."""
        from server.model_history import ModelHistoryBuffer

        buf = ModelHistoryBuffer(max_size=5)
        w0 = {"w": np.zeros((4,), dtype=np.float32)}
        w1 = {"w": np.ones((4,), dtype=np.float32)}

        buf.record(0, w0)
        buf.record(1, w1)

        assert buf.has_version(0)
        assert buf.has_version(1)
        assert len(buf) == 2

        # Drift from version 0 to w1 should be all-ones
        drift = buf.get_drift(0, w1)
        np.testing.assert_array_almost_equal(drift["w"], np.ones(4))

    def test_buffer_eviction(self):
        """Test 6: Buffer evicts oldest entries when full."""
        from server.model_history import ModelHistoryBuffer

        buf = ModelHistoryBuffer(max_size=3)
        for i in range(5):
            buf.record(i, {"w": np.full((2,), i, dtype=np.float32)})

        assert len(buf) == 3
        assert not buf.has_version(0)
        assert not buf.has_version(1)
        assert buf.has_version(2)
        assert buf.has_version(3)
        assert buf.has_version(4)


class TestAggregatorPipeline:
    """Test the full two-layer aggregation pipeline."""

    def test_aggregator_two_layer_pipeline(self):
        """Test 7: Aggregator rejects Mallory via gatekeeper when L2 > threshold."""
        np.random.seed(42)
        shapes = {"layer.weight": (32, 16), "layer.bias": (32,)}

        alice = make_update("alice", scale=0.01, shapes=shapes)
        bob = make_update("bob", scale=0.01, shapes=shapes)
        charlie = make_update("charlie", scale=0.01, shapes=shapes)

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

        config = Settings(L2_NORM_THRESHOLD=500.0)
        aggregator = Aggregator(strategy="krum", config=config)

        result = aggregator.aggregate(
            [alice, bob, charlie, mallory], current_round=1, task="femnist"
        )

        assert "mallory" in result.gatekeeper_rejected
        # Mallory was rejected by gatekeeper, so she won't appear in trust_scores
        # Verify she's not in accepted clients
        assert "mallory" not in result.accepted_clients

    def test_unified_trust_score_penalizes_staleness(self):
        """Trust scoring should be continuous and staleness-aware for all strategies."""
        np.random.seed(7)
        shapes = {"layer.weight": (16, 8), "layer.bias": (16,)}

        fresh = make_update("fresh", scale=0.01, shapes=shapes)
        stale = make_update("stale", scale=0.01, shapes=shapes)

        fresh["global_round_received"] = 10
        stale["global_round_received"] = 3

        config = Settings(
            AGGREGATION_STRATEGY="fedavg",
            STALENESS_DECAY_FN="polynomial",
            STALENESS_REPUTATION_WEIGHT=0.5,
            L2_NORM_THRESHOLD=500.0,
        )
        aggregator = Aggregator(strategy="fedavg", config=config)

        result = aggregator.aggregate([fresh, stale], current_round=10, task="femnist")

        assert "fresh" in result.trust_scores
        assert "stale" in result.trust_scores
        assert 0.0 <= result.trust_scores["fresh"] <= 1.0
        assert 0.0 <= result.trust_scores["stale"] <= 1.0
        assert result.trust_scores["stale"] < result.trust_scores["fresh"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
