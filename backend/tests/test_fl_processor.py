# backend/tests/test_fl_processor.py — Unit tests for FLWeightProcessor
"""
Covers:
  - Weight encode/decode codec (msgpack + JSON fallback)
  - L2 norm computation
  - Layer 1 gatekeeper (accept / reject / threshold config)
  - Layer 2 SABD outlier filter (cosine distance, trust updates)
  - Trust EMA computation
  - Staleness computation and decay weight
  - process_weight_update (full Layer 1 integration)
  - Round-boundary helpers (drain, clear)
  - Message builders (rejected, trust_report, global_model)
  - Module-level processor registry (lazy create, config update, remove)
"""

import base64
import json
import uuid
import pytest
import numpy as np

from training.fl_processor import (
    FLWeightProcessor,
    get_fl_processor,
    remove_fl_processor,
    _processors,
    _SABD_THRESHOLD,
    _TRUST_EMA_ALPHA,
    _STALENESS_DECAY_BASE,
)


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _enc(weight_dict: dict) -> str:
    """Encode {layer: list} → base64 msgpack/JSON."""
    try:
        import msgpack
        packed = msgpack.packb(weight_dict)
    except ImportError:
        packed = json.dumps(weight_dict).encode("utf-8")
    return base64.b64encode(packed).decode("utf-8")


def _small_msg(client_id: str = "c1", round_num: int = 1) -> dict:
    """Valid weight_update message with small L2 norm (≈ 1.73)."""
    return {
        "client_id": client_id,
        "weights": _enc({"layer": [1.0, 1.0, 1.0]}),
        "round_num": round_num,
        "global_round_received": round_num,
        "num_samples": 50,
        "local_loss": 0.4,
        "task": "femnist",
    }


def _large_msg(client_id: str = "c1") -> dict:
    """weight_update message with large L2 norm (≈ 1000, >> threshold 10)."""
    return {
        "client_id": client_id,
        "weights": _enc({"layer": [100.0] * 100}),
        "round_num": 1,
        "global_round_received": 1,
        "num_samples": 50,
        "task": "femnist",
    }


def _make_update(client_id: str, vec: list) -> dict:
    """Build a pending-update dict for Layer 2 tests."""
    return {
        "client_id": client_id,
        "weights": {"layer": np.array(vec, dtype=np.float32)},
        "num_samples": 100,
        "norm": float(np.linalg.norm(vec)),
    }


# ──────────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def proc():
    """Fresh FLWeightProcessor with threshold 10.0."""
    return FLWeightProcessor("proj-test", {"l2GatekeeperThreshold": 10.0})


# ══════════════════════════════════════════════════════════════════════════════
# 1. Weight Codec
# ══════════════════════════════════════════════════════════════════════════════

class TestWeightCodec:

    def test_roundtrip_preserves_values(self, proc):
        original = {"fc1": [1.0, 2.0, 3.0], "fc2": [4.0, 5.0]}
        weights_np = {k: np.array(v, dtype=np.float32) for k, v in original.items()}
        encoded = proc.encode_weights(weights_np)
        decoded = proc.decode_weights(encoded)

        assert decoded is not None
        np.testing.assert_allclose(decoded["fc1"], [1.0, 2.0, 3.0], atol=1e-5)
        np.testing.assert_allclose(decoded["fc2"], [4.0, 5.0], atol=1e-5)

    def test_decode_empty_string_returns_none(self, proc):
        assert proc.decode_weights("") is None

    def test_decode_invalid_b64_returns_none(self, proc):
        assert proc.decode_weights("!!!not-valid-base64!!!") is None

    def test_decode_valid_b64_but_bad_payload_returns_none(self, proc):
        # Valid base64 but not msgpack/JSON content
        garbage = base64.b64encode(b"\x00\x01\x02\x03\x04").decode("utf-8")
        result = proc.decode_weights(garbage)
        # Either None or empty dict; must not raise
        assert result is None or isinstance(result, dict)

    def test_encode_returns_non_empty_string(self, proc):
        weights = {"layer": np.array([1.0, 2.0], dtype=np.float32)}
        encoded = proc.encode_weights(weights)
        assert isinstance(encoded, str)
        assert len(encoded) > 0

    def test_encode_empty_dict_returns_string(self, proc):
        result = proc.encode_weights({})
        assert isinstance(result, str)


# ══════════════════════════════════════════════════════════════════════════════
# 2. L2 Norm
# ══════════════════════════════════════════════════════════════════════════════

class TestL2Norm:

    def test_pythagorean_triple(self, proc):
        weights = {"layer": np.array([3.0, 4.0], dtype=np.float32)}
        assert abs(proc.compute_l2_norm(weights) - 5.0) < 1e-4

    def test_multi_layer_concatenated(self, proc):
        # [3, 4] concat [0, 0] → norm of [3, 4, 0, 0] = 5
        weights = {
            "a": np.array([3.0, 4.0], dtype=np.float32),
            "b": np.array([0.0, 0.0], dtype=np.float32),
        }
        assert abs(proc.compute_l2_norm(weights) - 5.0) < 1e-4

    def test_all_zeros_is_zero(self, proc):
        weights = {"layer": np.zeros(10, dtype=np.float32)}
        assert proc.compute_l2_norm(weights) == 0.0

    def test_empty_dict_returns_zero(self, proc):
        # np.concatenate([]) raises → except branch returns 0.0
        assert proc.compute_l2_norm({}) == 0.0

    def test_known_vector_unit(self, proc):
        weights = {"layer": np.array([1.0, 0.0, 0.0], dtype=np.float32)}
        assert abs(proc.compute_l2_norm(weights) - 1.0) < 1e-5


# ══════════════════════════════════════════════════════════════════════════════
# 3. Layer 1 Gatekeeper
# ══════════════════════════════════════════════════════════════════════════════

class TestLayer1Gatekeeper:

    def test_passes_below_threshold(self, proc):
        weights = {"layer": np.array([1.0, 1.0, 1.0], dtype=np.float32)}  # norm ≈ 1.73
        passes, norm = proc.layer1_gatekeeper("client1", weights)
        assert passes is True
        assert norm < 10.0
        assert "client1" not in proc._gatekeeper_rejected

    def test_rejects_above_threshold(self, proc):
        weights = {"layer": np.ones(1000, dtype=np.float32)}  # norm ≈ 31.6
        passes, norm = proc.layer1_gatekeeper("client1", weights)
        assert passes is False
        assert norm > 10.0
        assert "client1" in proc._gatekeeper_rejected

    def test_exactly_at_threshold_passes(self, proc):
        # threshold = 10, vector of length 1 with value 10 → norm = 10 exactly
        weights = {"layer": np.array([10.0], dtype=np.float32)}
        passes, norm = proc.layer1_gatekeeper("c", weights)
        assert passes is True  # norm <= threshold

    def test_rejection_recorded_only_once(self, proc):
        weights = {"layer": np.ones(1000, dtype=np.float32)}
        proc.layer1_gatekeeper("client1", weights)
        proc.layer1_gatekeeper("client1", weights)  # second call same client
        assert proc._gatekeeper_rejected.count("client1") == 1

    def test_respects_custom_threshold(self):
        # Higher threshold of 100 — large norm still passes
        proc = FLWeightProcessor("proj", {"l2GatekeeperThreshold": 100.0})
        weights = {"layer": np.ones(50, dtype=np.float32)}  # norm ≈ 7.07 < 100
        passes, _ = proc.layer1_gatekeeper("c", weights)
        assert passes is True

    def test_multiple_clients_tracked_independently(self, proc):
        big = {"layer": np.ones(1000, dtype=np.float32)}
        small = {"layer": np.array([1.0], dtype=np.float32)}
        proc.layer1_gatekeeper("bad", big)
        proc.layer1_gatekeeper("good", small)
        assert "bad" in proc._gatekeeper_rejected
        assert "good" not in proc._gatekeeper_rejected


# ══════════════════════════════════════════════════════════════════════════════
# 4. Layer 2 SABD
# ══════════════════════════════════════════════════════════════════════════════

class TestLayer2SABD:

    def test_empty_updates_returns_empty(self, proc):
        accepted, rejected = proc.layer2_sabd([])
        assert accepted == []
        assert rejected == []

    def test_single_update_always_passes(self, proc):
        updates = [_make_update("c1", [1.0, 0.0, 0.0])]
        accepted, rejected = proc.layer2_sabd(updates)
        assert len(accepted) == 1
        assert len(rejected) == 0

    def test_aligned_updates_all_accepted(self, proc):
        updates = [
            _make_update("c1", [1.0, 0.05, 0.0]),
            _make_update("c2", [0.98, 0.02, 0.01]),
            _make_update("c3", [0.95, 0.0, 0.05]),
        ]
        accepted, rejected = proc.layer2_sabd(updates)
        assert len(accepted) == 3
        assert len(rejected) == 0

    def test_opposite_sign_outlier_rejected(self, proc):
        # c1 and c2 point in [1, 0], c3 points in [-1, 0]
        # mean ≈ [0.33, 0], c3 cosine_sim ≈ -1 → cosine_dist ≈ 2 → clamped to 1.0 > 0.45
        updates = [
            _make_update("c1", [1.0, 0.0]),
            _make_update("c2", [1.0, 0.0]),
            _make_update("c3", [-1.0, 0.0]),
        ]
        accepted, rejected = proc.layer2_sabd(updates)
        assert "c3" in rejected
        assert len(accepted) == 2

    def test_outlier_trust_set_to_zero(self, proc):
        updates = [
            _make_update("honest1", [1.0, 0.0]),
            _make_update("honest2", [1.0, 0.0]),
            _make_update("attacker", [-1.0, 0.0]),
        ]
        proc.layer2_sabd(updates)
        assert proc._trust_scores.get("attacker", 1.0) == 0.0

    def test_outlier_rejected_tracked(self, proc):
        updates = [
            _make_update("h", [1.0, 0.0]),
            _make_update("h2", [1.0, 0.0]),
            _make_update("byz", [-1.0, 0.0]),
        ]
        proc.layer2_sabd(updates)
        assert "byz" in proc._outlier_rejected

    def test_trust_scores_updated_for_all_clients(self, proc):
        updates = [
            _make_update("c1", [1.0, 0.0]),
            _make_update("c2", [0.0, 1.0]),  # orthogonal → cosine_dist = 1.0 > 0.45
        ]
        proc.layer2_sabd(updates)
        assert "c1" in proc._trust_scores
        assert "c2" in proc._trust_scores


# ══════════════════════════════════════════════════════════════════════════════
# 5. Trust EMA
# ══════════════════════════════════════════════════════════════════════════════

class TestTrustEMA:

    def test_new_client_zero_cosine_dist_stays_one(self, proc):
        # prev = default 1.0, instant = 1 - 0 = 1.0
        # new = 0.7 * 1.0 + 0.3 * 1.0 = 1.0
        trust = proc.compute_trust_ema("new", 0.0)
        assert abs(trust - 1.0) < 1e-5

    def test_high_cosine_dist_decreases_trust(self, proc):
        proc._trust_scores["c"] = 1.0
        trust = proc.compute_trust_ema("c", 0.9)
        # instant = 1 - 0.9 = 0.1 → new = 0.7 * 1 + 0.3 * 0.1 = 0.73
        assert abs(trust - 0.73) < 1e-4

    def test_ema_uses_previous_trust(self, proc):
        proc._trust_scores["c"] = 0.5
        trust1 = proc.compute_trust_ema("c", 0.5)  # instant = 0.5, new = 0.7*0.5 + 0.3*0.5 = 0.5
        assert abs(trust1 - 0.5) < 1e-4

    def test_trust_clamped_to_zero(self, proc):
        proc._trust_scores["c"] = 0.0
        trust = proc.compute_trust_ema("c", 2.0)  # instant = max(0, -1) = 0
        assert trust >= 0.0

    def test_trust_clamped_to_one(self, proc):
        proc._trust_scores["c"] = 1.0
        trust = proc.compute_trust_ema("c", -0.5)  # instant = 1 - (-0.5) = 1.5 → clamped
        assert trust <= 1.0

    def test_trust_stored_in_dict(self, proc):
        proc.compute_trust_ema("c", 0.2)
        assert "c" in proc._trust_scores


# ══════════════════════════════════════════════════════════════════════════════
# 6. Staleness
# ══════════════════════════════════════════════════════════════════════════════

class TestStaleness:

    def test_zero_staleness_current_round(self, proc):
        proc._global_round = 5
        staleness, weight = proc.compute_staleness("c", 5)
        assert staleness == 0
        assert abs(weight - 1.0) < 1e-5

    def test_positive_staleness_old_round(self, proc):
        proc._global_round = 10
        staleness, weight = proc.compute_staleness("c", 5)
        assert staleness == 5
        # weight = 1 / (1 + 0.1 * 5) = 1 / 1.5 ≈ 0.6667
        expected_weight = 1.0 / (1.0 + _STALENESS_DECAY_BASE * 5)
        assert abs(weight - expected_weight) < 1e-5

    def test_future_round_clamped_to_zero(self, proc):
        proc._global_round = 3
        staleness, weight = proc.compute_staleness("c", 10)  # "future"
        assert staleness == 0
        assert weight == 1.0

    def test_staleness_stored(self, proc):
        proc._global_round = 7
        staleness, weight = proc.compute_staleness("client1", 4)
        assert proc._staleness_values["client1"] == staleness
        assert abs(proc._staleness_weights["client1"] - weight) < 1e-5

    def test_large_staleness_weight_approaches_zero(self, proc):
        proc._global_round = 1000
        _, weight = proc.compute_staleness("c", 0)
        assert weight < 0.05  # heavily discounted


# ══════════════════════════════════════════════════════════════════════════════
# 7. process_weight_update (Layer 1 integration)
# ══════════════════════════════════════════════════════════════════════════════

class TestProcessWeightUpdate:

    def test_accepts_valid_small_norm(self, proc):
        result = proc.process_weight_update(_small_msg())
        assert result["status"] == "accepted"
        assert "norm" in result
        assert "threshold" in result
        assert result["norm"] < 10.0

    def test_rejects_large_norm_l1(self, proc):
        result = proc.process_weight_update(_large_msg())
        assert result["status"] == "rejected_l1"
        assert result["reason"] == "l2_norm_exceeded"
        assert result["norm"] > 10.0
        assert result["threshold"] == 10.0

    def test_error_on_invalid_weights(self, proc):
        result = proc.process_weight_update({
            "client_id": "c1",
            "weights": "!!!not-valid-base64!!!",
        })
        assert result["status"] == "error"
        assert result["reason"] == "weight_decode_failed"

    def test_accepted_update_queued(self, proc):
        proc.process_weight_update(_small_msg("c1"))
        proc.process_weight_update(_small_msg("c2"))
        assert len(proc._pending_updates) == 2

    def test_rejected_update_not_queued(self, proc):
        proc.process_weight_update(_large_msg("c1"))
        assert len(proc._pending_updates) == 0

    def test_staleness_computed_on_accept(self, proc):
        proc._global_round = 5
        proc.process_weight_update(_small_msg("c1", round_num=3))
        assert "c1" in proc._staleness_values
        assert proc._staleness_values["c1"] == 2  # 5 - 3

    def test_pending_update_contains_metadata(self, proc):
        proc.process_weight_update(_small_msg("c1", round_num=1))
        upd = proc._pending_updates[0]
        assert upd["client_id"] == "c1"
        assert "weights" in upd
        assert "norm" in upd
        assert "num_samples" in upd

    def test_gatekeeper_rejected_tracked_on_l1_reject(self, proc):
        proc.process_weight_update(_large_msg("bad_client"))
        assert "bad_client" in proc._gatekeeper_rejected


# ══════════════════════════════════════════════════════════════════════════════
# 8. Round Boundary Helpers
# ══════════════════════════════════════════════════════════════════════════════

class TestRoundBoundaryHelpers:

    def test_drain_pending_returns_all_and_clears(self, proc):
        proc._pending_updates = [{"client_id": "a"}, {"client_id": "b"}]
        drained = proc.drain_pending_updates()
        assert len(drained) == 2
        assert len(proc._pending_updates) == 0

    def test_drain_empty_returns_empty(self, proc):
        drained = proc.drain_pending_updates()
        assert drained == []

    def test_get_and_clear_gatekeeper_rejected(self, proc):
        proc._gatekeeper_rejected = ["x", "y"]
        rejected = proc.get_and_clear_gatekeeper_rejected()
        assert rejected == ["x", "y"]
        assert proc._gatekeeper_rejected == []

    def test_clear_round_state_resets_outlier_rejected(self, proc):
        proc._outlier_rejected = ["c1", "c2"]
        proc.clear_round_state()
        assert proc._outlier_rejected == []

    def test_set_global_round(self, proc):
        proc.set_global_round(42)
        assert proc._global_round == 42


# ══════════════════════════════════════════════════════════════════════════════
# 9. Message Builders
# ══════════════════════════════════════════════════════════════════════════════

class TestMessageBuilders:

    def test_rejected_msg_structure(self, proc):
        msg = proc.build_rejected_msg("c1", "femnist", 3, 15.5, 10.0)
        assert msg["type"] == "rejected"
        assert msg["client_id"] == "c1"
        assert msg["task"] == "femnist"
        assert msg["reason"] == "l2_norm_exceeded"
        assert msg["round_num"] == 3
        assert abs(msg["norm"] - 15.5) < 0.01
        assert abs(msg["threshold"] - 10.0) < 0.01

    def test_trust_report_msg_structure(self, proc):
        node_updates = [
            {"node_id": "n1", "cosine_distance": 0.1, "is_byzantine": False},
            {"node_id": "n2", "cosine_distance": 0.7, "is_byzantine": True},
        ]
        msg = proc.build_trust_report_msg("femnist", 5, node_updates, ["gk_bad"])

        assert msg["type"] == "trust_report"
        assert msg["task"] == "femnist"
        assert msg["round"] == 5
        assert "trust_scores" in msg
        assert "staleness_values" in msg
        assert "staleness_weights" in msg
        assert "rejected_clients" in msg
        assert "gatekeeper_rejected" in msg

    def test_trust_report_gatekeeper_in_msg(self, proc):
        msg = proc.build_trust_report_msg("t", 1, [], ["bad_client"])
        assert "bad_client" in msg["gatekeeper_rejected"]

    def test_trust_report_outlier_node_in_rejected(self, proc):
        node_updates = [
            {"node_id": "byz", "cosine_distance": 0.8, "is_byzantine": True},
        ]
        msg = proc.build_trust_report_msg("t", 1, node_updates, [])
        # cosine_dist 0.8 > 0.45 → byz should appear in rejected_clients
        assert "byz" in msg["rejected_clients"]

    def test_trust_report_honest_node_not_in_rejected(self, proc):
        node_updates = [
            {"node_id": "honest", "cosine_distance": 0.05, "is_byzantine": False},
        ]
        msg = proc.build_trust_report_msg("t", 1, node_updates, [])
        assert "honest" not in msg["rejected_clients"]

    def test_global_model_msg_structure(self, proc):
        weights = {"fc1": np.array([1.0, 2.0], dtype=np.float32)}
        msg = proc.build_global_model_msg("femnist", 7, weights, 0.5)

        assert msg["type"] == "global_model"
        assert msg["round_num"] == 7
        assert msg["task"] == "femnist"
        assert msg["personalization_alpha"] == 0.5
        assert "version" in msg
        assert "timestamp" in msg
        assert "weights" in msg

    def test_global_model_version_is_valid_uuid(self, proc):
        weights = {"fc1": np.zeros(4, dtype=np.float32)}
        msg = proc.build_global_model_msg("t", 1, weights)
        # Should not raise
        uuid.UUID(msg["version"])

    def test_global_model_weights_encoded(self, proc):
        weights = {"fc1": np.array([3.0, 4.0], dtype=np.float32)}
        msg = proc.build_global_model_msg("t", 1, weights)
        # weights field should be a non-empty base64 string
        assert isinstance(msg["weights"], str)
        assert len(msg["weights"]) > 0

    def test_global_model_alpha_rounded(self, proc):
        weights = {"fc1": np.zeros(2, dtype=np.float32)}
        msg = proc.build_global_model_msg("t", 1, weights, personalization_alpha=0.123456789)
        assert msg["personalization_alpha"] == round(0.123456789, 4)

    def test_trust_report_merges_real_fl_trust_scores(self, proc):
        """Real FL client trust (from _trust_scores) overrides simulated node data."""
        proc._trust_scores["real_client"] = 0.42
        msg = proc.build_trust_report_msg("t", 1, [], [])
        assert abs(msg["trust_scores"]["real_client"] - 0.42) < 0.001


# ══════════════════════════════════════════════════════════════════════════════
# 10. Processor Registry
# ══════════════════════════════════════════════════════════════════════════════

class TestProcessorRegistry:

    def test_lazy_create_on_first_call(self):
        assert "new-proj" not in _processors
        proc = get_fl_processor("new-proj", {"l2GatekeeperThreshold": 5.0})
        assert proc is not None
        assert "new-proj" in _processors

    def test_returns_same_instance(self):
        p1 = get_fl_processor("same-proj")
        p2 = get_fl_processor("same-proj")
        assert p1 is p2

    def test_updates_config_on_existing_instance(self):
        p1 = get_fl_processor("cfg-proj", {"l2GatekeeperThreshold": 5.0})
        get_fl_processor("cfg-proj", {"l2GatekeeperThreshold": 25.0})
        assert p1.config["l2GatekeeperThreshold"] == 25.0

    def test_config_none_does_not_overwrite(self):
        p1 = get_fl_processor("noop-proj", {"l2GatekeeperThreshold": 7.0})
        get_fl_processor("noop-proj", config=None)  # should not change config
        assert p1.config["l2GatekeeperThreshold"] == 7.0

    def test_remove_processor_cleans_registry(self):
        get_fl_processor("rm-proj")
        remove_fl_processor("rm-proj")
        assert "rm-proj" not in _processors

    def test_remove_nonexistent_is_safe(self):
        remove_fl_processor("does-not-exist")  # must not raise
